"""Contract, authorization and read-only plan validation over unrelated schemas."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from business_prediction.contracts import reference
from business_prediction.errors import FrameworkError, ContractValidationError
from business_prediction.specifications.operations import OperationValidator, default_operation_registry
from business_prediction.runtime.development import DevelopmentAuthorizationProvider
from tests.specification_support import SpecificationFixture


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.f = SpecificationFixture(self.directory.name)

    def tearDown(self):
        self.f.runtime.close(); self.directory.cleanup()

    def codes(self, result): return {i["code"] for i in result["findings"]}

    def plan(self, **changes):
        target, observation = self.f.base_specs()
        return self.f.propose("DataPreparationPlanSpecification", self.f.plan_fields(target, observation, **changes))

    def test_valid_reviewed_plan_never_authorizes_execution(self):
        plan = self.plan()
        self.assertIn("specification_proposed", self.codes(self.f.validate(plan)))
        approval = self.f.approve_spec(plan)
        result = self.f.validate(plan)
        self.assertTrue(result["valid_specification"])
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(approval["execution_authorized"])

    def test_revisions_preserve_history_and_do_not_inherit_approval(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields())
        approval = self.f.approve_spec(target)
        newer = self.f.propose("PredictionTargetSpecification", self.f.target_fields(limitations=["A new exact proposal."]), predecessor=reference(target))
        self.assertEqual(newer["object_revision"], 2)
        self.assertEqual(self.f.specs.specification_state(reference(newer), self.f.now)["state"], "proposed")
        self.assertEqual(self.f.specs.get(reference(target)), target)
        self.assertEqual(self.f.specs.get(reference(approval)), approval)
        with self.assertRaises(FrameworkError):
            self.f.propose("PredictionTargetSpecification", self.f.target_fields(), predecessor=reference(target))

    def test_missing_fields_and_invalid_references_are_structured(self):
        fields = self.f.target_fields(); del fields["eligibility"]
        with self.assertRaises(ContractValidationError) as error:
            self.f.propose("PredictionTargetSpecification", fields)
        self.assertTrue(any(i.code == "missing_field" for i in error.exception.issues))
        fields = self.f.target_fields(); fields["physical_field_reference"]["schema_version"] = "not-the-pinned-schema"
        with self.assertRaises(ContractValidationError): self.f.propose("PredictionTargetSpecification", fields)

    def test_target_conflict_and_unapproved_semantics_block_approval(self):
        binding = self.f.bind(3, "unseen.other.metric", "unapproved-field", approve=False)
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields(
            semantic_binding_reference=reference(binding), physical_field_reference=self.f.fields[3], business_meaning="Conflicts with the pinned interpretation."))
        codes = self.codes(self.f.inspect(target))
        self.assertIn("semantic_not_approved", codes); self.assertIn("conflicting_target_meaning", codes)
        with self.assertRaises(FrameworkError): self.f.approve_spec(target)

    def test_wrong_version_and_unauthorized_decisions_fail_closed(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields())
        req = self.f.review(target)
        newer = self.f.propose("PredictionTargetSpecification", self.f.target_fields(), predecessor=reference(target))
        with self.assertRaises(FrameworkError): self.f.decision(req, newer)
        with self.assertRaises(FrameworkError): self.f.decision(req, target, context=self.f.stranger)
        self.assertEqual(self.f.service.records("SpecificationApprovalRecord"), [])

    def test_rejection_and_clarification_are_immutable_and_close_review(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields())
        for action, state in (("reject", "rejected"), ("request_clarification", "clarification_requested")):
            req = self.f.review(target)
            self.f.decision(req, target, action)
            self.assertEqual(self.f.specs.specification_state(reference(target), self.f.now)["state"], state)
            with self.assertRaises(FrameworkError): self.f.decision(req, target)
        self.assertEqual(len(self.f.service.records("SpecificationReviewDecision")), 2)

    def test_revocation_blocks_dependent_plan_and_preserves_history(self):
        plan = self.plan(); approval = self.f.approve_spec(plan)
        before = self.f.specs.get(reference(approval))
        self.f.specs.retire(reference(approval), action="revoke", rationale="Synthetic review withdrawn.", context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertIn("specification_revoked", self.codes(self.f.validate(plan)))
        self.assertEqual(self.f.specs.get(reference(approval)), before)

    def test_supersession_does_not_transfer_to_new_target(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields()); old = self.f.approve_spec(target)
        newer = self.f.propose("PredictionTargetSpecification", self.f.target_fields(), predecessor=reference(target))
        self.assertEqual(self.f.specs.specification_state(reference(newer), self.f.now)["state"], "proposed")
        replacement = self.f.approve_spec(newer)
        self.f.specs.retire(reference(old), action="supersede", replacement=reference(replacement), rationale="Reviewed replacement version.",
            context=self.f.owner, command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertEqual(self.f.specs.specification_state(reference(target), self.f.now)["state"], "superseded")
        self.assertEqual(self.f.specs.specification_state(reference(newer), self.f.now)["state"], "approved")

    def test_unknown_operations_invalid_parameters_and_dependencies_are_blocked(self):
        op = self.f.operation(operation_type="unregistered-analysis", operation_version="9", depends_on=["future"])
        plan = self.plan(operations=[op])
        codes = self.codes(self.f.inspect(plan))
        self.assertIn("unsupported_operation", codes); self.assertIn("invalid_operation_dependencies", codes)
        fields = self.f.plan_fields(self.f.specs.get(plan["target_reference"]), self.f.specs.get(plan["observation_reference"]),
            operations=[self.f.operation(operation_type="missing_values", parameters={"method": "invent_default"})])
        newer = self.f.propose("DataPreparationPlanSpecification", fields, predecessor=reference(plan))
        self.assertIn("invalid_operation_parameters", self.codes(self.f.inspect(newer)))

    def test_leakage_and_unresolved_business_decisions_are_blocked(self):
        plan = self.plan(operations=[self.f.operation(information_role="predictor", availability="after_decision")], unresolved_decisions=["Unconfirmed eligibility."])
        codes = self.codes(self.f.inspect(plan))
        self.assertTrue({"target_as_predictor", "predictor_availability_unverified", "unresolved_business_decisions"} <= codes)

    def test_aggregation_cannot_silently_change_grain_or_create_derived_target(self):
        op = self.f.operation(operation_type="aggregation", output_grain="entity-period",
            parameters={"group_bindings": [reference(self.f.time)], "measure_bindings": [reference(self.f.target)], "method": "sum", "reconciliation_checks": []})
        plan = self.plan(operations=[op], output_grain="entity-period")
        codes = self.codes(self.f.inspect(plan))
        self.assertIn("missing_reconciliation", codes); self.assertIn("plan_observation_grain_mismatch", codes)
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields(target_grain="entity-period", construction_requirements={
            "definition": "A proposed derived measure.", "method_reference": "unverified-symbolic-sum", "input_binding_references": [reference(self.f.target)]}))
        self.assertIn("target_construction_unverified", self.codes(self.f.inspect(target)))

    def test_join_requires_explicit_reviewed_relationship(self):
        op = self.f.operation(operation_type="join", parameters={"relationship_reference": reference(self.f.target), "join_type": "left", "reconciliation_checks": []})
        plan = self.plan(operations=[op])
        codes = self.codes(self.f.inspect(plan))
        self.assertIn("invalid_operation_parameters", codes); self.assertIn("join_without_relationship", codes)

    def test_temporal_overlap_and_boundary_conflicts(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields()); self.f.approve_spec(target)
        obs = self.f.propose("ObservationSpecification", self.f.observation_fields(target,
            future_boundaries={"start": "2026-01-19", "end": "2026-01-25", "calendar_reference": "synthetic-calendar"},
            observation_grain="different-grain"))
        codes = self.codes(self.f.inspect(obs))
        self.assertIn("temporal_boundary_overlap", codes); self.assertIn("target_observation_grain_mismatch", codes)

    def test_expired_and_conditional_approvals_are_not_ready(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields())
        self.f.approve_spec(target, conditions=["Requires future owner confirmation of eligibility."])
        self.assertEqual(self.f.specs.specification_state(reference(target), self.f.now)["state"], "conditions_unverified")
        self.f.now += timedelta(days=11)
        self.assertEqual(self.f.specs.specification_state(reference(target), self.f.now)["state"], "expired")

    def test_persistence_restart_and_source_preservation(self):
        plan = self.plan(); self.f.approve_spec(plan); result = self.f.validate(plan)
        before = deepcopy(self.f.bundle.discovery_result)
        self.f.runtime.close()
        self.f = SpecificationFixture(self.directory.name)
        self.assertEqual(self.f.specs.get(reference(result)), result)
        self.assertTrue(self.f.validate(plan)["valid_specification"])
        self.assertEqual(self.f.runtime.catalogue.get(reference(before)), before)
        self.assertTrue(any(e["event"] == "specification.authorized" for e in self.f.runtime.audit_history()))

    def test_production_rejects_development_default_at_service_construction(self):
        self.f.runtime.config = replace(self.f.runtime.config, mode="production")
        with self.assertRaises(FrameworkError): self.f.runtime.specification_service()

    def test_new_schema_names_boolean_target_and_other_native_grain(self):
        with TemporaryDirectory() as directory:
            f = SpecificationFixture(directory, categorical=True, headers=("flag-Q", "signal_72", "tick-A", "unused"),
                table_name="unfamiliar_observation_grid", source_id="another-department-source", concept="owner.unknown-concept", record_grain="event-instance")
            try:
                target, obs = f.base_specs()
                plan = f.propose("DataPreparationPlanSpecification", f.plan_fields(target, obs)); f.approve_spec(plan)
                self.assertTrue(f.validate(plan)["valid_specification"])
                self.assertEqual(target["value_type"], "boolean")
                self.assertEqual(obs["observation_grain"], "event-instance")
                self.assertEqual(obs["entity_binding_references"], [])  # No invented key.
            finally: f.runtime.close()

    def test_ambiguous_dates_block_observation_approval(self):
        with TemporaryDirectory() as directory:
            f = SpecificationFixture(directory, ambiguous_dates=True)
            try:
                target = f.propose("PredictionTargetSpecification", f.target_fields()); f.approve_spec(target)
                obs = f.propose("ObservationSpecification", f.observation_fields(target))
                self.assertIn("unresolved_observation_dates", self.codes(f.inspect(obs)))
                with self.assertRaises(FrameworkError): f.approve_spec(obs)
            finally: f.runtime.close()

    def test_schema_and_source_revisions_require_new_review(self):
        from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
        from business_prediction.discovery import discover
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields()); self.f.approve_spec(target)
        adapter = MemoryAdapter(SourceConfig("assessment-source", "synthetic-owner", "assessment-test"),
            [MemoryTable("different-layout", (("unknown-col", "added-col"), (12, 24)))])
        newer = discover(adapter, source_revision=2, discovery_revision=2); newer.publish(self.f.runtime.catalogue)
        codes = self.codes(self.f.inspect(target))
        self.assertTrue({"source_snapshot_changed", "schema_snapshot_changed"} & codes)
        self.assertEqual(self.f.specs.get(reference(target)), target)

    def test_semantic_revocation_and_supersession_block_existing_specifications(self):
        plan = self.plan(); self.f.approve_spec(plan)
        approval = next(a for a in self.f.service.records("ApprovalRecord") if a["approved_object_reference"] == reference(self.f.target))
        request = self.f.service.submit_review(reference(approval), scope=approval["approval_scope"], context=self.f.author,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.f.service.decide(reference(request), reference(approval), action="revoke", context=self.f.owner,
            rationale="Synthetic semantic approval revoked.", command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertIn("semantic_revoked", self.codes(self.f.validate(plan)))

    def test_supported_declarations_do_not_change_discovery_or_source(self):
        before = deepcopy(self.f.bundle.discovery_result)
        examples = [
            ("type_interpretation", {"value_type": "float", "format": None}),
            ("missing_values", {"method": "flag", "constant": None}),
            ("invalid_values", {"method": "flag", "rule_definition": "Owner-supplied range rule; no zero assumption."}),
            ("duplicate_handling", {"method": "flag", "key_bindings": []}),
            ("date_time_interpretation", {"format": "ISO-8601", "timezone": "UTC", "calendar": "synthetic-calendar", "ambiguous_policy": "reject", "rule_reference": None}),
            ("filtering_eligibility", {"binding_reference": reference(self.f.input), "operator": "not_null", "value": None})]
        ops = []
        for i, (name, params) in enumerate(examples):
            ops.append(self.f.operation(operation_id=str(i), operation_type=name, parameters=params, depends_on=[str(i-1)] if i else []))
        plan = self.plan(operations=ops); self.f.approve_spec(plan)
        self.assertTrue(self.f.validate(plan)["valid_specification"])
        self.assertEqual(self.f.runtime.catalogue.get(reference(before)), before)

    def test_operation_extensions_require_explicit_trusted_validator(self):
        class ExtraValidator(OperationValidator):
            operation_type = "new-technical-contract-check"
            def validate(self, operation, context): return []
        plan = self.plan(operations=[self.f.operation(operation_type=ExtraValidator.operation_type)])
        self.assertIn("unsupported_operation", self.codes(self.f.inspect(plan)))
        registry = default_operation_registry(); registry.register(ExtraValidator())
        self.f.specs = self.f.runtime.specification_service(operations=registry)
        self.assertEqual(self.f.inspect(plan)["findings"], [])
        self.f.approve_spec(plan)
        self.assertTrue(self.f.validate(plan)["valid_specification"])

    def test_fitted_treatments_require_separate_fold_specification(self):
        plan = self.plan(operations=[self.f.operation(operation_type="missing_values", parameters={"method": "model_based", "constant": None})])
        self.assertIn("fitted_treatment_requires_fold_contract", self.codes(self.f.inspect(plan)))

    def test_stale_commands_direct_import_and_unavailable_authority_are_blocked(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields())
        with self.assertRaises(FrameworkError): self.f.runtime.catalogue.add(target)
        with self.assertRaises(FrameworkError):
            self.f.specs.submit_review(reference(target), context=self.f.author, command_id=self.f.cmd(), expected_head=0,
                expires_at=(self.f.now+timedelta(days=2)).isoformat(), review_due_at=(self.f.now+timedelta(days=1)).isoformat())
        provider = self.f.runtime.authority.authorization_provider
        def unavailable(*args): raise RuntimeError("Synthetic provider outage; no credentials.")
        provider.authorize = unavailable
        with self.assertRaises(FrameworkError): self.f.inspect(target)
        self.assertEqual(self.f.service.records("SpecificationApprovalRecord"), [])

    def test_non_temporal_numeric_outcome_is_not_forced_into_forecasting(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields(historical_boundaries=None,
            history_not_applicable_reason="Owner-reviewed cross-sectional source snapshot, not a dated business history.", prediction_horizon=None))
        self.f.approve_spec(target)
        obs = self.f.propose("ObservationSpecification", self.f.observation_fields(target, observation_period=None,
            time_binding_reference=None, time_basis=None, expected_frequency=None, future_boundaries=None,
            time_not_applicable_reason="Unknown numerical outcomes on independent source observations; no future time request."))
        self.f.approve_spec(obs)
        plan = self.f.propose("DataPreparationPlanSpecification", self.f.plan_fields(target, obs)); self.f.approve_spec(plan)
        self.assertTrue(self.f.validate(plan)["valid_specification"])

    def test_semantic_supersession_and_dependent_target_revocation(self):
        plan = self.plan(); self.f.approve_spec(plan)
        original = next(a for a in self.f.service.records("ApprovalRecord") if a["approved_object_reference"] == reference(self.f.target))
        replacement = self.f.bind(0, self.f.concept, "replacement-semantic-target")
        approved = next(a for a in self.f.service.records("ApprovalRecord") if a["approved_object_reference"] == reference(replacement))
        req = self.f.service.submit_review(reference(original), scope=original["approval_scope"], context=self.f.author,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.f.service.decide(reference(req), reference(original), action="supersede", replacement_approval=reference(approved), context=self.f.owner,
            rationale="Explicit semantic replacement, not automatic rebinding.", command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertIn("semantic_superseded", self.codes(self.f.validate(plan)))
        approval = next(a for a in self.f.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == plan["target_reference"])
        self.f.specs.retire(reference(approval), action="revoke", rationale="Target acceptance withdrawn.", context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertIn("specification_revoked", self.codes(self.f.validate(plan)))

    def test_relationship_review_and_explicit_join_declaration(self):
        from business_prediction.semantics.common import digest
        from tests.semantic_support import evidence_ref
        with TemporaryDirectory() as directory:
            f = SpecificationFixture(directory, extra_table=True)
            try:
                right = f.bind(4, "owner.right-key-scope", "right-key")
                artifact, content, owner = "synthetic-relationship-evidence", digest({"synthetic": "owner-reviewed scoped relationship"}), "synthetic-business-owner"
                f.runtime.authority.authorization_provider.verify_evidence_origin = lambda a,d,o: (a,d,o) == (artifact,content,owner)
                doc = f.service.register_evidence(artifact_reference=artifact, artifact_version="1", content_digest=content,
                    evidence_kind="owner-relationship-attestation", claim_summary="Explicit synthetic key scope, cardinality and reconciliation requirements; no real business approval.",
                    origin_identity=owner, coverage="Exact two-table synthetic discovery.", access_policy_reference="synthetic-private", retention_reference="test-only",
                    purpose=f.scope["purpose"], relevant_subjects=[reference(f.bundle.discovery_result)], valid_until=(f.now+timedelta(days=20)).isoformat(),
                    authorization_scope=f.scope, context=f.author, command_id=f.cmd(), expected_head=f.service.head)
                fields = {"left_key_bindings": [reference(f.input)], "right_key_bindings": [reference(right)],
                    "left_grain": "source-record", "right_grain": "source-record", "result_grain": "source-record", "cardinality": "many_to_one",
                    "null_key_policy": "Reject undeclared null identity, never fill.", "unmatched_policy": "Retain unmatched left records with explicit evidence.",
                    "expansion_policy": "No left-row expansion permitted; execution must stop on a cardinality violation.",
                    "reconciliation_checks": ["Before/after rows, unmatched records, distinct keys and measure totals."],
                    "evidence_definition": "Accountable owner attestation on exact snapshots, not a field-name match.",
                    "required_approvals": ["scoped_relationship_and_reconciliation"], "limitations": ["No join was executed."]}
                relation = f.specs.propose("RelationshipSpecification", fields, scope=f.scope,
                    evidence=[evidence_ref("documentary", record_reference=reference(doc))], context=f.author, command_id=f.cmd(), expected_head=f.service.head)
                self.assertEqual(f.inspect(relation)["findings"], [])
                approval = f.approve_spec(relation)
                target, obs = f.base_specs()
                op = f.operation(operation_type="join", input_binding_references=[reference(f.input), reference(right)],
                    relationship_references=[reference(relation)], parameters={"relationship_reference": reference(relation), "join_type": "left",
                    "reconciliation_checks": ["Require rows, distinct keys, unmatched counts and financial/quantity totals to reconcile."]})
                plan = f.propose("DataPreparationPlanSpecification", f.plan_fields(target, obs, operations=[op], relationship_references=[reference(relation)]))
                f.approve_spec(plan)
                self.assertTrue(f.validate(plan)["valid_specification"])
                f.specs.retire(reference(approval), action="revoke", rationale="Synthetic relationship withdrawn.", context=f.owner,
                    command_id=f.cmd(), expected_head=f.service.head)
                self.assertIn("specification_revoked", self.codes(f.validate(plan)))
            finally: f.runtime.close()

    def test_daily_horizon_calendar_and_temporal_boundaries_must_agree(self):
        target = self.f.propose("PredictionTargetSpecification", self.f.target_fields()); self.f.approve_spec(target)
        obs = self.f.propose("ObservationSpecification", self.f.observation_fields(target,
            future_boundaries={"start": "2026-01-21", "end": "2026-01-28", "calendar_reference": "unconfirmed-other-calendar"}))
        codes = self.codes(self.f.inspect(obs))
        self.assertIn("horizon_boundary_mismatch", codes); self.assertIn("calendar_mismatch", codes)

    def test_approval_receipts_and_validation_contracts_cannot_be_forged(self):
        plan = self.plan(); approval = self.f.approve_spec(plan); result = self.f.validate(plan)
        forged = deepcopy(result); forged["execution_authorized"] = True
        with self.assertRaises(ContractValidationError): self.f.runtime.catalogue.registry.validate(forged, resolver=self.f.runtime.catalogue.resolve)
        forged = deepcopy(approval); forged["approved_object_digest"] = "sha256:forged"
        with self.assertRaises(ContractValidationError): self.f.runtime.catalogue.registry.validate(forged, resolver=self.f.runtime.catalogue.resolve)


if __name__ == "__main__": unittest.main()
