"""Synthetic execution-control tests; no NOP preparation or model work."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
from business_prediction.contracts import reference
from business_prediction.errors import FrameworkError, ContractValidationError
from business_prediction.execution.interfaces import ExecutionEvidenceVerifier
from business_prediction.persistence.base import PersistenceError
from tests.execution_support import ExecutionFixture


class ControlledExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(); self.f = ExecutionFixture(self.directory.name)

    def tearDown(self):
        self.f.runtime.close(); self.directory.cleanup()

    def test_explicit_authorization_and_measured_success_manifest(self):
        request = self.f.request_execution()
        self.assertEqual(self.f.control.state(reference(request))["status"], "requested")
        with self.assertRaises(FrameworkError): self.f.advance("begin", request)
        self.f.authorize_execution(request); self.f.advance("begin", request)
        self.f.record(request)
        result = self.f.advance("finalize", request)
        self.assertEqual(result["status"], "succeeded")
        provenance = self.f.service.records("PreparationProvenanceRecord")[-1]
        self.assertEqual(provenance["source_references"], self.f.plan["source_references"])
        self.assertEqual(provenance["operations"], self.f.plan["operations"])
        self.assertEqual(provenance["artifact_disposition"], "eligible_manifest")
        artifacts = [self.f.control.get(r) for r in result["output_artifacts"]]
        self.assertEqual(artifacts[0]["row_count"], 20)
        self.assertEqual(self.f.control.get(result["reconciliation_reference"])["status"], "passed")
        with self.assertRaises(FrameworkError): self.f.advance("begin", request)

    def test_missing_execution_integrations_never_authorize(self):
        self.f.control = self.f.runtime.controlled_preparation_service()
        request = self.f.request_execution(); outcome = self.f.authorize_execution(request)
        self.assertIsNone(outcome["authorization_reference"])
        self.assertEqual(self.f.control.state(reference(request))["status"], "rejected")
        self.assertEqual(self.f.service.records("PreparationArtifact"), [])

    def test_authorization_denial_and_wrong_worker_are_enforced(self):
        request = self.f.request_execution()
        with self.assertRaises(FrameworkError): self.f.authorize_execution(request, context=self.f.stranger)
        self.assertEqual(self.f.service.records("PreparationExecutionAuthorization"), [])
        self.f.authorize_execution(request)
        with self.assertRaises(FrameworkError): self.f.advance("begin", request, context=self.f.author)
        self.assertEqual(self.f.control.state(reference(request))["status"], "authorized")

    def test_explicit_rejection_has_reason_and_no_execution_results(self):
        request = self.f.request_execution(); self.f.authorize_execution(request, approve=False, expires_at=None)
        state = self.f.control.state(reference(request))
        self.assertEqual(state["status"], "rejected"); self.assertIsNone(state["started_at"])
        self.assertIn("explicit_execution_denial", state["failure_codes"])
        self.assertEqual(self.f.service.records("PreparationReconciliationResult"), [])

    def test_duplicate_request_keys_and_command_replay_do_not_rerun(self):
        request = self.f.request_execution(request_key="one-durable-intent")
        same = self.f.request_execution(request_key="one-durable-intent")
        self.assertEqual(reference(request), reference(same))
        with self.assertRaises(FrameworkError): self.f.request_execution(request_key="one-durable-intent", lease_seconds=15)
        self.f.authorize_execution(request)
        args = {"context": self.f.owner, "command_id": self.f.cmd(), "expected_head": self.f.service.head}
        first = self.f.control.begin(reference(request), **args)
        self.assertEqual(self.f.control.begin(reference(request), **args), first)
        with self.assertRaises(FrameworkError): self.f.advance("begin", request)
        self.assertEqual(len(self.f.service.records("PreparationExecutionRequest")), 1)

    def test_revoked_plan_approval_invalidates_previously_granted_execution(self):
        request = self.f.request_execution(); self.f.authorize_execution(request)
        approval = next(a for a in self.f.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == reference(self.f.plan))
        self.f.specs.retire(reference(approval), action="revoke", rationale="Synthetic owner withdrew plan approval.", context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertEqual(self.f.advance("begin", request)["status"], "failed")

    def test_authorization_revocation_terminates_active_work(self):
        request = self.f.start(); state = self.f.control.state(reference(request))
        self.f.control.revoke(state["authorization_reference"], rationale="Synthetic execution grant withdrawn.", context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertEqual(self.f.control.state(reference(request))["status"], "revoked")
        with self.assertRaises(FrameworkError): self.f.advance("finalize", request)

    def test_live_source_change_blocks_start_without_publishing_a_new_schema(self):
        request = self.f.request_execution(); self.f.authorize_execution(request)
        changed = MemoryAdapter(SourceConfig(self.f.adapter.source_id, "synthetic-owner", "assessment-test"), [MemoryTable("changed-layout", (("renamed",), (17,)))])
        self.f.source_verifier.adapters[self.f.adapter.source_id] = changed
        result = self.f.advance("begin", request)
        self.assertEqual(result["status"], "failed"); self.assertIn("source_snapshot_changed", result["failure_codes"])

    def test_expired_authorization_and_lease_are_not_success(self):
        request = self.f.start(); self.f.now += timedelta(minutes=11)
        result = self.f.advance("finalize", request)
        self.assertEqual(result["status"], "failed")
        self.assertTrue({"execution_authorization_expired", "execution_lease_expired"} <= set(result["failure_codes"]))

    def test_partial_outputs_are_preserved_as_failed_quarantined_evidence(self):
        request = self.f.start(); result = self.f.record(request, complete=False)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["output_artifacts"])
        self.assertFalse(self.f.control.get(result["output_artifacts"][0])["complete"])
        self.assertEqual(self.f.service.records("PreparationProvenanceRecord")[-1]["artifact_disposition"], "quarantined")
        with self.assertRaises(FrameworkError): self.f.advance("finalize", request)

    def test_unperformed_operation_has_no_invented_success(self):
        request = self.f.start()
        result = self.f.advance("record_operation", request, operation_id=self.f.plan["operations"][0]["operation_id"], evidence_handle="not-executed")
        self.assertEqual(result["status"], "failed")
        self.assertIn("operation_not_observed", result["failure_codes"])
        self.assertEqual(self.f.service.records("PreparationOperationReceipt"), [])

    def test_missing_counts_are_unavailable_not_fabricated_zeros(self):
        request = self.f.start(); result = self.f.record(request, null_counts=True)
        self.assertEqual(result["status"], "failed")
        receipt = self.f.service.records("PreparationOperationReceipt")[-1]
        self.assertIsNone(receipt["accepted_count"]); self.assertIsNone(receipt["rejected_count"])
        reconciliation = self.f.control.get(receipt["reconciliation_reference"])
        self.assertTrue(any(c["status"] == "unavailable" for c in reconciliation["checks"]))

    def test_record_loss_and_incomplete_reconciliation_prevent_success(self):
        request = self.f.start(); result = self.f.record(request, drop_row=True)
        self.assertEqual(result["status"], "failed")
        self.assertIn("input_partition", result["failure_codes"])
        self.assertIn("row_preservation", result["failure_codes"])

    def test_tampering_after_checkpoint_is_detected_before_success(self):
        request = self.f.start(); state = self.f.record(request)
        artifact = self.f.control.get(state["output_artifacts"][0])
        path = self.f.evidence.path(artifact["locator"], reference(request))
        body = json.loads(path.read_text(encoding="utf-8")); body["rows"].pop()
        path.write_text(json.dumps(body), encoding="utf-8")
        result = self.f.advance("finalize", request)
        self.assertEqual(result["status"], "failed"); self.assertIn("output_integrity", result["failure_codes"])

    def test_stale_fencing_token_is_rejected(self):
        request = self.f.start(); result = self.f.record(request, bad_fence=True)
        self.assertEqual(result["status"], "failed"); self.assertIn("operation_evidence_mismatch", result["failure_codes"])

    def test_no_operation_receipts_cannot_be_finalized(self):
        request = self.f.start(); result = self.f.advance("finalize", request)
        self.assertEqual(result["status"], "failed"); self.assertIn("execution_complete", result["failure_codes"])

    def test_interruption_and_restart_keep_history_and_block_automatic_resume(self):
        request = self.f.start(); checkpoint = self.f.record(request)
        self.f.runtime.close(); self.f = ExecutionFixture(self.directory.name)
        self.assertEqual(self.f.control.state(reference(request)), checkpoint)
        interrupted = self.f.advance("interrupt", request, reason="Recovered stopped synthetic worker; do not retry automatically.")
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertIn("Recovered stopped", interrupted["failure_detail"])
        with self.assertRaises(FrameworkError): self.f.advance("begin", request)
        self.assertEqual(self.f.control.get(reference(checkpoint)), checkpoint)

    def test_persistence_failure_rolls_back_checkpoint_and_never_records_success(self):
        request = self.f.start(); handle = self.f.evidence.emit(self.f, request)
        args = {"operation_id": self.f.plan["operations"][0]["operation_id"], "evidence_handle": handle,
                "context": self.f.owner, "command_id": self.f.cmd(), "expected_head": self.f.service.head}
        original = self.f.runtime.store._transaction
        @contextmanager
        def fail_before_commit():
            with original() as unit:
                yield unit
                raise PersistenceError("injected_write_failure", "Synthetic persistence failure.")
        with patch.object(self.f.runtime.store, "_transaction", fail_before_commit):
            with self.assertRaises(FrameworkError): self.f.control.record_operation(reference(request), **args)
        self.assertEqual(self.f.control.state(reference(request))["status"], "running")
        self.assertEqual(self.f.service.records("PreparationOperationReceipt"), [])
        self.assertEqual(self.f.service.records("PreparationProvenanceRecord"), [])
        self.assertEqual(self.f.advance("interrupt", request, reason="Recovered after a failed state write.")["status"], "interrupted")

    def test_production_rejects_development_execution_providers(self):
        with self.assertRaises(FrameworkError):
            self.f.runtime.config = replace(self.f.runtime.config, mode="production")
            self.f.runtime.controlled_preparation_service(sources=self.f.source_verifier, evidence=self.f.evidence)

    def test_contracts_and_provenance_cannot_claim_success_without_evidence(self):
        request = self.f.start(); state = self.f.control.state(reference(request))
        fake = deepcopy(state); fake.update(status="succeeded", finished_at=self.f.now.isoformat())
        with self.assertRaises(ContractValidationError): self.f.runtime.catalogue.registry.validate(fake, resolver=self.f.runtime.catalogue.resolve)
        with self.assertRaises(FrameworkError): self.f.runtime.catalogue.add(state)
        self.assertEqual(self.f.service.records("PreparationProvenanceRecord"), [])

    def test_duplicate_operation_report_is_idempotent_and_cannot_run_twice(self):
        request = self.f.start(); handle = self.f.evidence.emit(self.f, request)
        args = {"operation_id": self.f.plan["operations"][0]["operation_id"], "evidence_handle": handle,
            "context": self.f.owner, "command_id": self.f.cmd(), "expected_head": self.f.service.head}
        state = self.f.control.record_operation(reference(request), **args)
        self.assertEqual(self.f.control.record_operation(reference(request), **args), state)
        with self.assertRaises(FrameworkError): self.f.advance("record_operation", request, operation_id=args["operation_id"], evidence_handle=handle)
        self.assertEqual(len(self.f.service.records("PreparationOperationReceipt")), 1)

    def test_unknown_or_missing_reconciler_blocks_operational_authorization(self):
        from business_prediction.execution.reconciliation import ReconciliationRegistry
        self.f.control = self.f.runtime.controlled_preparation_service(sources=self.f.source_verifier, evidence=self.f.evidence,
            reconciliation=ReconciliationRegistry([]))
        request = self.f.request_execution(); result = self.f.authorize_execution(request)
        self.assertIsNone(result["authorization_reference"])
        self.assertIn("reconciliation_strategy_unavailable", self.f.control.state(reference(request))["failure_codes"])

    def test_schema_discovery_revision_does_not_inherit_execution_permission(self):
        from business_prediction.discovery import discover
        request = self.f.request_execution(); self.f.authorize_execution(request)
        newer = discover(self.f.adapter, source_revision=2, discovery_revision=2); newer.publish(self.f.runtime.catalogue)
        result = self.f.advance("begin", request)
        self.assertEqual(result["status"], "failed")
        self.assertTrue({"source_snapshot_changed", "schema_snapshot_changed"} & set(result["failure_codes"]))

    def test_artifact_schema_changes_require_explicit_reconciliation_support(self):
        request = self.f.start(); handle = self.f.evidence.emit(self.f, request)
        output = self.f.evidence.reports[handle]["output_artifacts"][0]
        path = self.f.evidence.path(output["locator"], reference(request))
        body = json.loads(path.read_text(encoding="utf-8")); body["field_ids"][0] = "unapproved-new-physical-field"
        path.write_text(json.dumps(body), encoding="utf-8")
        self.f.evidence.reports[handle]["output_artifacts"] = [self.f.evidence.inspect_artifact(reference(request), output)]
        state = self.f.advance("record_operation", request, operation_id=self.f.plan["operations"][0]["operation_id"], evidence_handle=handle)
        self.assertEqual(state["status"], "failed"); self.assertIn("schema_consistency", state["failure_codes"])

    def test_unfamiliar_schema_and_boolean_target_use_the_same_controller(self):
        with TemporaryDirectory() as directory:
            f = ExecutionFixture(directory, categorical=True, headers=("flag-x9", "measurement_B", "tick12", "context_zzz"),
                table_name="unseen_department_grid", source_id="fresh-source-domain", concept="owner.dynamic.label")
            try:
                request = f.start(); f.record(request)
                self.assertEqual(f.advance("finalize", request)["status"], "succeeded")
            finally: f.runtime.close()

    def test_lost_commit_acknowledgement_recovers_by_same_command_replay(self):
        request = self.f.start(); handle = self.f.evidence.emit(self.f, request)
        args = {"operation_id": self.f.plan["operations"][0]["operation_id"], "evidence_handle": handle,
                "context": self.f.owner, "command_id": self.f.cmd(), "expected_head": self.f.service.head}
        original = self.f.runtime.store._transaction
        @contextmanager
        def lost_acknowledgement():
            with original() as unit: yield unit
            raise PersistenceError("injected_unknown_ack", "Synthetic commit acknowledgement was lost.")
        with patch.object(self.f.runtime.store, "_transaction", lost_acknowledgement):
            with self.assertRaises(FrameworkError): self.f.control.record_operation(reference(request), **args)
        recovered = self.f.control.record_operation(reference(request), **args)
        self.assertEqual(recovered["status"], "running")
        self.assertEqual(len(self.f.service.records("PreparationOperationReceipt")), 1)
        self.assertEqual(self.f.advance("finalize", request)["status"], "succeeded")

    def test_contract_rejects_cross_request_authorization_and_receipts(self):
        request = self.f.start(); other = self.f.request_execution()
        state = deepcopy(self.f.control.state(reference(request))); state["request_reference"] = reference(other)
        with self.assertRaises(ContractValidationError): self.f.runtime.catalogue.registry.validate(state, resolver=self.f.runtime.catalogue.resolve)

    def test_verifier_measurements_after_command_start_are_accepted(self):
        request = self.f.start(); handle = self.f.evidence.emit(self.f, request)
        original = self.f.evidence.inspect_operation
        def later_measurement(*args):
            self.f.now += timedelta(seconds=1)
            result = original(*args); result["completed_at"] = self.f.now.isoformat()
            for artifact in result["input_artifacts"]+result["output_artifacts"]: artifact["measured_at"] = self.f.now.isoformat()
            return result
        with patch.object(self.f.evidence, "inspect_operation", later_measurement):
            state = self.f.advance("record_operation", request, operation_id=self.f.plan["operations"][0]["operation_id"], evidence_handle=handle)
        self.assertEqual(state["status"], "running")
        self.assertEqual(self.f.advance("finalize", request)["status"], "succeeded")

    def test_slow_operation_verification_cannot_outlive_lease(self):
        request = self.f.start(); original = self.f.evidence.inspect_artifact
        handle = self.f.evidence.emit(self.f, request)
        def delayed(*args):
            result = original(*args); self.f.now += timedelta(seconds=121); return result
        with patch.object(self.f.evidence, "inspect_artifact", delayed):
            state = self.f.advance("record_operation", request, operation_id=self.f.plan["operations"][0]["operation_id"], evidence_handle=handle)
        self.assertEqual(state["status"], "failed"); self.assertIn("execution_lease_expired", state["failure_codes"])

    def test_slow_final_verification_cannot_outlive_lease(self):
        request = self.f.start(); self.f.record(request)
        original = self.f.evidence.inspect_artifact
        def delayed(*args):
            result = original(*args); self.f.now += timedelta(seconds=121); return result
        with patch.object(self.f.evidence, "inspect_artifact", delayed): state = self.f.advance("finalize", request)
        self.assertEqual(state["status"], "failed"); self.assertIn("execution_lease_expired", state["failure_codes"])

    def test_slow_source_verification_cannot_issue_an_expired_grant(self):
        request = self.f.request_execution(); deadline = (self.f.now+timedelta(seconds=2)).isoformat()
        original = self.f.source_verifier.verify
        def delayed(*args):
            result = original(*args); self.f.now += timedelta(seconds=3); return result
        with patch.object(self.f.source_verifier, "verify", delayed): outcome = self.f.authorize_execution(request, expires_at=deadline)
        self.assertIsNone(outcome["authorization_reference"])
        self.assertEqual(self.f.control.state(reference(request))["status"], "rejected")

    def test_principal_changes_during_authorization_fail_closed(self):
        from business_prediction.runtime.development import DevelopmentAuthorizationProvider
        request = self.f.request_execution(); self.f.authorize_execution(request)
        provider = self.f.runtime.authority.authorization_provider
        grant = next(g for g in self.f.grants if g.principal_reference == "owner")
        self.f.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(
            self.f.grants+[replace(grant, grant_id="second-authorized-worker", principal_reference="stranger")], provider._secrets, "env:KEY")
        original = self.f.runtime.authority.identity_provider.authenticate
        calls = [0]
        def changes_identity(*args):
            identity = original(*args); calls[0] += 1
            return identity if calls[0] == 1 else replace(identity, principal_reference="stranger")
        with patch.object(self.f.runtime.authority.identity_provider, "authenticate", changes_identity):
            with self.assertRaises(FrameworkError) as error: self.f.advance("begin", request)
        self.assertEqual(error.exception.code, "execution_identity_changed")
        self.assertEqual(self.f.control.state(reference(request))["status"], "authorized")


if __name__ == "__main__": unittest.main()
