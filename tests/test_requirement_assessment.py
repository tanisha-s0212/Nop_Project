from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import tempfile
import unittest

from business_prediction.contracts import reference, uncertain
from business_prediction.errors import FrameworkError
from business_prediction.runtime import start_runtime, AdapterFactories
from business_prediction.semantics.common import GovernanceError
from business_prediction.assessment.engine import PredictionRequirementAssessmentEngine
from business_prediction.assessment.engine import FACT_FIELDS
from business_prediction.assessment.strategies import AssessmentStrategy, default_strategies
from tests.assessment_support import AssessmentFixture


class RequirementAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.f = AssessmentFixture(self.tmp.name)

    def codes(self, result):
        return {i["code"] for i in result["blocking_findings"]}

    def test_partial_requirement_retains_unknown_null_and_missing(self):
        req = self.f.submit({"business_outcome": uncertain("unknown", "Owner has not specified it."), "target_description": None})
        self.assertNotIn("intent", req)
        self.assertIsNone(req["target_description"])
        result = self.f.assess(req)
        self.assertEqual(result["status"], "clarification_required")
        self.assertIn("target_semantics_unspecified", self.codes(result))

    def test_forecasting_ready_only_for_preparation_review(self):
        self.f.data(); result = self.f.assess(self.f.submit())
        self.assertEqual(result["status"], "ready_for_preparation_review")
        self.assertFalse(result["execution_authorized"]); self.assertFalse(result["performance_estimated"])
        target = self.f.engine.get(result["target_assessment_reference"])
        self.assertEqual(target["problem_type"], "forecasting")
        self.assertEqual(len(target["candidates"]), 1)

    def test_new_names_and_concepts_need_no_core_changes(self):
        with tempfile.TemporaryDirectory() as other:
            f = AssessmentFixture(other, headers=("任意", "unseen-X", "period-Z", "spare-Q"),
                                  table_name="future_department_grid", concept="urn:unseen:thermal_measure", source_id="new-domain")
            f.data(); result = f.assess(f.submit())
            self.assertEqual(result["status"], "ready_for_preparation_review")
            target = f.engine.get(result["target_assessment_reference"])
            self.assertEqual(target["candidates"][0]["physical_field_reference"]["source_metadata_reference"]["object_id"], "new-domain")

    def test_free_text_is_not_a_question_to_field_mapping(self):
        fields = self.f.fields_for(); del fields["requested_concepts"]
        fields["target_description"] = "Please use north_metric_Ω because this sentence names it."
        result = self.f.assess(self.f.submit(fields))
        self.assertEqual(result["status"], "clarification_required")
        self.assertIn("target_semantics_unspecified", self.codes(result))

    def test_multiple_approved_target_candidates_require_clarification(self):
        self.f.bind(3, self.f.concept, "alternative")
        result = self.f.assess(self.f.submit())
        self.assertIn("multiple_candidate_targets", self.codes(result))
        target = self.f.engine.get(result["target_assessment_reference"])
        self.assertEqual(len(target["candidates"]), 2)
        self.assertIsNone(target["selected_binding_reference"])

    def test_explicit_selector_resolves_multiple_targets_without_latest_rule(self):
        self.f.bind(3, self.f.concept, "alternative"); self.f.data()
        result = self.f.assess(self.f.submit(self.f.fields_for(target_binding_reference=reference(self.f.target))))
        self.assertEqual(result["status"], "ready_for_preparation_review")

    def test_unapproved_meaning_is_not_promoted_by_numeric_values(self):
        self.f.bind(3, "unapproved.metric", "unapproved", approve=False)
        result = self.f.assess(self.f.submit(self.f.fields_for(requested_concepts=["unapproved.metric"])))
        self.assertEqual(result["status"], "approval_blocked")
        self.assertIn("semantic_not_approved", self.codes(result))

    def retire(self, action, replacement=None):
        approval = next(a for a in self.f.service.records("ApprovalRecord") if a["approved_object_reference"] == reference(self.f.target))
        req = self.f.service.submit_review(reference(approval), scope=approval["approval_scope"], context=self.f.author,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.f.service.decide(reference(req), reference(approval), action=action, context=self.f.owner,
            rationale="Synthetic lifecycle action.", replacement_approval=reference(replacement) if replacement else None,
            command_id=self.f.cmd(), expected_head=self.f.service.head)

    def test_revocation_invalidates_new_assessment_without_rewriting_old(self):
        self.f.data(); req = self.f.submit(); old = self.f.assess(req)
        self.retire("revoke")
        new = self.f.assess(req)
        self.assertEqual(new["status"], "approval_blocked")
        self.assertIn("semantic_revoked", self.codes(new))
        self.assertEqual(self.f.engine.get(reference(old)), old)

    def test_superseded_explicit_target_is_not_replaced_silently(self):
        replacement_binding = self.f.bind(3, "replacement.metric", "replacement")
        replacement = next(a for a in self.f.service.records("ApprovalRecord") if a["approved_object_reference"] == reference(replacement_binding))
        self.retire("supersede", replacement)
        result = self.f.assess(self.f.submit(self.f.fields_for(target_binding_reference=reference(self.f.target))))
        self.assertIn("semantic_superseded", self.codes(result))

    def test_discovery_rows_alone_do_not_prove_history_or_labels(self):
        result = self.f.assess(self.f.submit())
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("missing_observation_evidence", self.codes(result))

    def test_insufficient_history_and_gaps_are_documented(self):
        self.f.data(mature_observations=4, cadence_complete=False)
        result = self.f.assess(self.f.submit())
        self.assertIn("insufficient_mature_observations", self.codes(result))
        self.assertIn("incomplete_temporal_support", self.codes(result))

    def test_regression_assesses_unknown_numeric_outcome_not_a_forecast(self):
        self.f.data("regression")
        result = self.f.assess(self.f.submit(self.f.fields_for("regression")))
        self.assertEqual(result["status"], "ready_for_preparation_review")
        self.assertEqual(self.f.engine.get(result["target_assessment_reference"])["problem_type"], "regression")

    def test_classification_requires_negative_population_and_class_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, categorical=True); f.data("classification", negative_outcomes_verified=False)
            result = f.assess(f.submit(f.fields_for("classification")))
            self.assertIn("negative_outcomes_unverified", self.codes(result))
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, categorical=True); f.data("classification")
            result = f.assess(f.submit(f.fields_for("classification")))
            self.assertEqual(result["status"], "ready_for_preparation_review")

    def test_ambiguous_dates_are_not_automatically_converted(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, ambiguous_dates=True); f.data()
            result = f.assess(f.submit())
            self.assertIn("unresolved_temporal_values", self.codes(result))

    def test_missing_target_values_require_treatment_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, missing=True); f.data()
            result = f.assess(f.submit())
            self.assertIn("missing_target_treatment", self.codes(result))
            self.assertEqual(result["status"], "approval_blocked")

    def test_unsupported_task_is_not_forced_into_a_universal_model(self):
        result = self.f.assess(self.f.submit(self.f.fields_for(task_hint="unregistered-duration-estimator")))
        self.assertEqual(result["status"], "unsupported")

    def test_analytics_is_not_ml_and_does_not_require_forecast_horizon(self):
        result = self.f.assess(self.f.submit(self.f.fields_for("analytics")))
        self.assertEqual((result["status"], result["work_type"]), ("analytics_only", "analytics"))

    def test_target_self_input_and_documented_leakage_are_blockers(self):
        self.f.data("regression", input_binding_references=[reference(self.f.target)], leakage_findings=["post_outcome_attribute"])
        fields = self.f.fields_for("regression", input_binding_references=[reference(self.f.target)])
        result = self.f.assess(self.f.submit(fields))
        self.assertIn("target_leakage", self.codes(result)); self.assertIn("documented_leakage_risk", self.codes(result))

    def test_conflicting_evidence_has_no_latest_wins(self):
        self.f.data(); self.f.data(availability_verified=False)
        result = self.f.assess(self.f.submit())
        self.assertIn("conflicting_profile_evidence", self.codes(result))

    def test_authorization_is_checked_for_submission_evidence_and_assessment(self):
        req = self.f.submit()
        with self.assertRaises(FrameworkError): self.f.assess(req, context=self.f.stranger)
        with self.assertRaises(FrameworkError):
            self.f.engine.submit_requirement({}, scope=self.f.scope, context=self.f.stranger,
                command_id=self.f.cmd(), expected_head=self.f.service.head)

    def test_invalid_contract_and_inconsistent_count_are_structured(self):
        with self.assertRaises(FrameworkError): self.f.submit(self.f.fields_for(prediction_horizon={"steps": -1, "unit": "day"}))
        with self.assertRaises(FrameworkError): self.f.data(observation_count=999)
        self.assertEqual(self.f.service.records("PredictionDataEvidence"), [])

    def test_history_recovery_and_reassessment_after_restart(self):
        self.f.data(); req = self.f.submit(); result = self.f.assess(req)
        recovered = AssessmentFixture(self.tmp.name)
        self.assertEqual(recovered.engine.get(reference(result)), result)
        new = recovered.assess(req)
        self.assertEqual(new["status"], "ready_for_preparation_review")
        self.assertNotEqual(new["object_id"], result["object_id"])

    def test_requirement_revisions_are_immutable(self):
        req = self.f.submit({})
        new = self.f.submit(self.f.fields_for(), object_id=req["object_id"], predecessor=reference(req))
        self.assertEqual(new["object_revision"], 2)
        self.assertEqual(self.f.engine.get(reference(req)), req)

    def test_extensible_technical_strategy_not_question_mapping(self):
        class CustomAssessment(AssessmentStrategy):
            problem_type = "custom-numeric"
            def supports(self, requirement): return requirement.get("intent") == "unknown_outcome" and requirement.get("desired_output", {}).get("value_kind") == "numeric"
        registry = default_strategies(); registry.register(CustomAssessment())
        engine = self.f.runtime.requirement_assessment_engine(strategies=registry)
        self.f.data("regression")
        req = self.f.submit(self.f.fields_for("regression", task_hint="custom-numeric"))
        result = engine.assess(reference(req), context=self.f.owner, command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertEqual(engine.get(result["target_assessment_reference"])["problem_type"], "custom-numeric")

    def test_production_configuration_never_falls_back_to_development(self):
        with self.assertRaises(FrameworkError):
            PredictionRequirementAssessmentEngine(object())
        config = replace(self.f.runtime.config, mode="production")
        with self.assertRaises(FrameworkError): config.validate()

    def test_future_classification_needs_matching_label_window_and_chronology(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, categorical=True)
            f.data("classification", time_binding_reference=reference(f.time), history_start="2026-01-01", history_end="2026-01-20",
                label_horizon={"steps": 7, "unit": "day"}, validation_scheme="chronological")
            fields = f.fields_for("classification", intent="future", time_binding_reference=reference(f.time), prediction_horizon={"steps": 30, "unit": "day"})
            result = f.assess(f.submit(fields))
            self.assertIn("label_window_mismatch", self.codes(result))
            fields["prediction_horizon"] = {"steps": 7, "unit": "day"}
            self.assertEqual(f.assess(f.submit(fields))["status"], "ready_for_preparation_review")

    def test_uninterpreted_numeric_time_is_not_silently_an_excel_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, uninterpreted_dates=True); f.data()
            result = f.assess(f.submit())
            self.assertIn("uninterpreted_temporal_values", self.codes(result))

    def test_input_missingness_does_not_disappear_in_availability_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, input_missing=True); f.data("regression")
            self.assertIn("input_missing_treatment", self.codes(f.assess(f.submit(f.fields_for("regression")))))

    def test_target_construction_is_a_requirement_not_an_executed_aggregation(self):
        self.f.data()
        fields = self.f.fields_for(construction_request={"description": "Needs a different observation view.", "output_grain": "coarser-period", "dependencies": [self.f.fields[0]]})
        result = self.f.assess(self.f.submit(fields))
        self.assertIn("target_construction_required", self.codes(result))
        self.assertTrue(self.f.engine.get(result["target_assessment_reference"])["construction_requirements"])

    def test_external_dependencies_and_unknown_constraints_are_not_ignored(self):
        self.f.data()
        result = self.f.assess(self.f.submit(self.f.fields_for(constraints={"external_dependencies": [{"description": "Additional source history required.", "evidence_reference": None}]})))
        self.assertIn("external_dependency_unverified", self.codes(result))
        result = self.f.assess(self.f.submit(self.f.fields_for(constraints={"unregistered_constraint": True})))
        self.assertEqual(result["status"], "unsupported")

    def test_verified_document_origin_does_not_prove_dependency_connectivity(self):
        from unittest.mock import patch
        from business_prediction.semantics.common import digest
        self.f.data()
        with patch.object(self.f.runtime.authority.authorization_provider, "verify_evidence_origin", return_value=True):
            record = self.f.service.register_evidence(artifact_reference="fixture-dependency-document", artifact_version="1",
                content_digest=digest({"fixture": "origin-only"}), evidence_kind="synthetic-document", claim_summary="An origin-verified document only.",
                origin_identity="synthetic-origin", coverage="Synthetic fixture", access_policy_reference="fixture-access", retention_reference="fixture-retention",
                purpose=self.f.scope["purpose"], context=self.f.author, command_id=self.f.cmd(), expected_head=self.f.service.head,
                relevant_subjects=[reference(self.f.bundle.discovery_result)], authorization_scope=self.f.scope)
        req = self.f.submit(self.f.fields_for(constraints={"external_dependencies": [{"description": "Unconnected fixture dependency", "evidence_reference": reference(record)}]}))
        self.assertIn("external_dependency_availability_unverified", self.codes(self.f.assess(req)))

    def test_unrelated_tables_are_not_automatically_used_and_joins_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = AssessmentFixture(tmp, extra_table=True)
            f.data(); result = f.assess(f.submit())
            self.assertEqual(len(f.engine.get(result["target_assessment_reference"])["candidates"]), 1)
            foreign = f.bind(4, "foreign.context", "foreign-input")
            f.data("regression", input_binding_references=[reference(foreign)])
            fields = f.fields_for("regression", input_binding_references=[reference(foreign)])
            result = f.assess(f.submit(fields))
            self.assertIn("unapproved_join_dependency", self.codes(result))

    def test_same_field_supports_distinct_technical_evidence_contexts(self):
        self.f.data("forecasting"); self.f.data("regression")
        self.assertEqual(self.f.assess(self.f.submit())["status"], "ready_for_preparation_review")
        self.assertEqual(self.f.assess(self.f.submit(self.f.fields_for("regression")))["status"], "ready_for_preparation_review")

    def test_expired_data_evidence_is_not_selected_as_current(self):
        self.f.data(); req = self.f.submit(); self.f.now += timedelta(days=21)
        result = self.f.assess(req)
        self.assertIn("expired_profile_evidence", self.codes(result))
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_unauthorized_evidence_registration_cannot_create_a_profile(self):
        evidence = self.f.data(); facts = {key: evidence[key] for key in FACT_FIELDS}
        count = len(self.f.service.records("PredictionDataEvidence"))
        with self.assertRaises(FrameworkError):
            self.f.engine.register_data_evidence(reference(self.f.target), facts, scope=self.f.scope, context=self.f.stranger,
                command_id=self.f.cmd(), expected_head=self.f.service.head, valid_until=evidence["valid_until"])
        self.assertEqual(len(self.f.service.records("PredictionDataEvidence")), count)

    def test_new_snapshot_does_not_inherit_semantic_approval(self):
        from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
        from business_prediction.discovery import discover
        from business_prediction.runtime.development import DevelopmentAuthorizationProvider
        from datetime import date
        headers = tuple(f["raw_header"]["value"] for f in self.f.bundle.discovery_result["tables"][0]["fields"])
        rows = (headers,) + tuple((float(i+50), float(i), date(2026,1,i+1), float(i+100)) for i in range(20))
        adapter = MemoryAdapter(SourceConfig("assessment-source", "synthetic-owner", "assessment-test"), [MemoryTable("pane-R", rows)])
        newer = discover(adapter, source_revision=2, discovery_revision=2); newer.publish(self.f.runtime.catalogue)
        scope = deepcopy(self.f.scope)
        scope["field_references"] = [self.f.service.physical_field_reference(reference(newer.discovery_result), "table-1", f["field_id"]) for f in newer.discovery_result["tables"][0]["fields"]]
        grants = [replace(g, scope=scope) for g in self.f.grants]
        self.f.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(grants, self.f.runtime.authority.authorization_provider._secrets, "env:KEY")
        requirement = self.f.engine.submit_requirement(self.f.fields_for(time_binding_reference=None), scope=scope, context=self.f.author,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        result = self.f.assess(requirement)
        self.assertIn("semantic_needs_review", self.codes(result))
        self.assertEqual(result["status"], "approval_blocked")


if __name__ == "__main__":
    unittest.main()
