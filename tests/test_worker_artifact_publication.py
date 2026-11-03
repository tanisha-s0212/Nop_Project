"""Synthetic operator, isolation, publication and recovery tests."""

from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from business_prediction.contracts import reference
from business_prediction.errors import FrameworkError
from business_prediction.persistence.base import PersistenceError
from business_prediction.runtime.development import DevelopmentAuthorizationProvider
from business_prediction.worker.storage import LocalArtifactStorage
from tests.worker_support import WorkerFixture


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.store = LocalArtifactStorage(self.root/"store")
        self.payload = {"batch":{"schema":[{"field_id":"opaque","types":["integer"]}],"rows":[[{"type":"integer","value":1}],[{"type":"integer","value":1}]],"ordinals":[1,2]},"lineage":{"source_references":[]}}
    def tearDown(self): self.tmp.cleanup()
    def test_seals_statistics_and_immutable_return_values(self):
        uri = self.store.put("execution-a","inputs",self.payload)
        original = self.store.read(uri); changed = self.store.read(uri); changed["batch"]["rows"].clear()
        self.assertEqual(self.store.read(uri),original)
        from datetime import datetime,timezone
        desc = self.store.describe(uri,"input",datetime.now(timezone.utc))
        self.assertEqual(desc["row_count"],2); self.assertEqual(desc["duplicate_count"],1)
        self.assertEqual(desc["missing_counts"],{"opaque":0})
    def test_original_directory_overlap_and_locator_escape_are_rejected(self):
        with self.assertRaises(FrameworkError): LocalArtifactStorage(self.root/"originals"/"store",protected_paths=[self.root/"originals"])
        with self.assertRaises(FrameworkError): self.store.read("artifact:"+self.store.store_id+":../outside:inputs:bad")
        with self.assertRaises(FrameworkError): self.store.read("artifact:other-store:execution-a:inputs:bad")
    def test_partial_and_tampered_files_never_verify(self):
        uri = self.store.put("execution-a","inputs",self.payload)
        path = self.store._file(uri); os.chmod(path,stat.S_IWRITE); path.write_bytes(b'{"partial":true}')
        with self.assertRaises(FrameworkError): self.store.read(uri)
        self.assertEqual(self.store.orphans([])[0]["status"],"partial_or_corrupt")
    def test_exclusive_creation_and_hardlink_isolation(self):
        uri = self.store.put("execution-a","inputs",self.payload,token="same")
        with self.assertRaises(FileExistsError): self.store.put("execution-a","inputs",self.payload,token="same")
        alias = self.root/"alias.json"
        os.link(self.store._file(uri),alias)
        with self.assertRaises(FrameworkError): self.store.read(uri)
    def test_budgets_reject_unbounded_rows_and_bytes(self):
        limited = LocalArtifactStorage(self.root/"limited",max_rows=1,max_bytes=2048)
        with self.assertRaises(FrameworkError): limited.put("execution-a","inputs",self.payload)
    def test_restart_reopens_sealed_versions(self):
        uri = self.store.put("execution-a","inputs",self.payload)
        reopened = LocalArtifactStorage(self.root/"store")
        self.assertEqual(reopened.read(uri),self.payload)
        self.assertEqual(reopened.content_digest(uri),self.store.content_digest(uri))
    def test_ambiguous_interpretations_and_executable_parser_strings_are_rejected(self):
        from business_prediction.worker.operators import ApprovedTypeInterpretation
        op = ApprovedTypeInterpretation()
        declaration = {"parameters":{"value_type":"integer","format":"canonical_integer_text"},"input_binding_references":[{"unresolved":"synthetic-placeholder"}],"information_role":"validation"}
        for token in ("001","03/04/2026","1,000"," 1","1.0"):
            batch = {"schema":[{"field_id":"opaque","types":["text"]}],"rows":[[{"type":"text","value":token}]],"ordinals":[1]}
            with self.assertRaises(FrameworkError): op.apply(batch,declaration,"opaque")
        declaration["parameters"]["format"] = "__import__('os')"
        with self.assertRaises(FrameworkError): op.validate(declaration)
    def test_unknown_registration_and_unsupported_grain_are_rejected(self):
        from business_prediction.worker.operators import PreparationOperatorRegistry,InspectNativeRows
        registry = PreparationOperatorRegistry()
        with self.assertRaises(ValueError): registry.register(InspectNativeRows())
        op = InspectNativeRows(); op.changes_grain = True
        with self.assertRaises(ValueError): PreparationOperatorRegistry([op])
    def test_blank_missing_values_keep_original_tokens_and_unknown_schema(self):
        from datetime import datetime,timezone
        payload = {"batch":{"schema":[{"field_id":"empty-field","types":[]}],"rows":[[{"type":"text","value":"  "}]],"ordinals":[1]},"lineage":{"source_references":[]}}
        uri = self.store.put("execution-a","inputs",payload)
        self.assertEqual(self.store.describe(uri,"input",datetime.now(timezone.utc))["missing_counts"],{"empty-field":1})
        self.assertEqual(self.store.read(uri)["batch"],payload["batch"])


class WorkerPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TemporaryDirectory(); f = WorkerFixture(cls.template.name)
        f.runtime.close()
    @classmethod
    def tearDownClass(cls): cls.template.cleanup()
    def setUp(self):
        self.tmp = TemporaryDirectory()
        with closing(sqlite3.connect(str(Path(self.template.name)/"metadata.sqlite3"))) as src, closing(sqlite3.connect(str(Path(self.tmp.name)/"metadata.sqlite3"))) as dest: src.backup(dest)
        self.f = WorkerFixture(self.tmp.name)
    def tearDown(self): self.f.runtime.close(); self.tmp.cleanup()
    def execute(self):
        request = self.f.start(); self.assertEqual(self.f.run(request)["status"],"running")
        self.assertEqual(self.f.finish(request)["status"],"succeeded"); return request
    def proposal(self, request, key=None):
        return self.f.publisher.request(reference(request),publication_key=key or self.f.cmd(),context=self.f.author,command_id=self.f.cmd(),expected_head=self.f.service.head)
    def publish_proposal(self, proposal, **changes):
        args = {"context":self.f.owner,"command_id":self.f.cmd(),"expected_head":self.f.service.head}; args.update(changes)
        return self.f.publisher.publish(reference(proposal),**args)
    def test_native_worker_requires_separate_publication_permission(self):
        request = self.execute()
        self.assertEqual(self.f.service.records("PreparationPublicationRecord"),[])
        proposal = self.proposal(request)
        with self.assertRaises(FrameworkError): self.publish_proposal(proposal,context=self.f.stranger)
        published = self.publish_proposal(proposal)
        view = self.f.publisher.read(reference(published),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(len(view["versions"]),2)
        self.assertEqual({v["role"] for v in view["versions"]},{"accepted","rejected"})
    def test_registered_filter_retains_rejected_records_and_exact_grain(self):
        operation = self.f.operation(operation_type="filtering_eligibility",source_references=[self.f.fields[1]],input_binding_references=[reference(self.f.input)],
            parameters={"binding_reference":reference(self.f.input),"operator":"gte","value":10.0})
        self.f.set_operations([operation]); request = self.execute()
        receipt = self.f.service.records("PreparationOperationReceipt")[-1]
        self.assertEqual((receipt["accepted_count"],receipt["rejected_count"]),(10,10))
        self.assertEqual(len(self.f.publish(request)["artifact_references"]),2)
    def test_type_interpretation_and_filter_chain_have_complete_lineage(self):
        with TemporaryDirectory() as directory:
            f = WorkerFixture(directory,text_input=True,headers=("outcome-Z","token-K","tick-U","aux-V"))
            try:
                cast = f.operation(operation_id="cast",operation_type="type_interpretation",source_references=[f.fields[1]],input_binding_references=[reference(f.input)],
                    parameters={"value_type":"integer","format":"canonical_integer_text"},information_role="predictor",availability="before_decision")
                select = f.operation(operation_id="filter",operation_type="filtering_eligibility",source_references=[f.fields[1]],input_binding_references=[reference(f.input)],
                    parameters={"binding_reference":reference(f.input),"operator":"gte","value":10},depends_on=["cast"])
                f.set_operations([cast,select]); request = f.start(); f.run(request); f.run(request); self.assertEqual(f.finish(request)["status"],"succeeded")
                self.assertEqual(len(f.publish(request)["artifact_references"]),3)
                self.assertEqual(f.service.records("PreparationArtifact")[-2]["schema"][1]["types"],["integer"])
            finally: f.runtime.close()
    def test_csv_source_and_original_bytes_remain_unchanged(self):
        with TemporaryDirectory() as directory:
            f = WorkerFixture(directory,csv_source=True,headers=("category-Q","value-D","day-W","other-N"))
            try:
                before = f.source_file.read_bytes(); request = f.start(); f.run(request); self.assertEqual(f.finish(request)["status"],"succeeded"); f.publish(request)
                self.assertEqual(f.source_file.read_bytes(),before)
            finally: f.runtime.close()
    def test_denied_execution_and_unknown_operator_cannot_write_staging(self):
        operation = self.f.operation(operation_type="invalid_values",parameters={"method":"flag","rule_definition":"An unimplemented declared rule."})
        self.f.set_operations([operation]); request = self.f.start()
        self.assertEqual(self.f.control.state(reference(request))["status"],"rejected")
        self.assertEqual(list(self.f.store.root.glob("*/*/*.json")),[])
    def test_fencing_and_identity_are_verified_before_operator_runs(self):
        request = self.f.start()
        with self.assertRaises(FrameworkError): self.f.run(request,fence_token="wrong-fence")
        with self.assertRaises(FrameworkError): self.f.run(request,context=self.f.stranger)
        self.assertEqual(self.f.service.records("PreparationWorkerAttempt"),[])
    def test_source_changes_block_worker_claim(self):
        from business_prediction.adapters import MemoryAdapter,MemoryTable,SourceConfig
        request = self.f.start()
        self.f.worker.sources.adapters[self.f.adapter.source_id] = MemoryAdapter(SourceConfig(self.f.adapter.source_id,"synthetic-owner","assessment-test"),[MemoryTable("changed",(("x",),(1,)))])
        with self.assertRaises(FrameworkError): self.f.run(request)
        self.assertEqual(self.f.service.records("PreparationWorkerAttempt"),[])
    def test_lease_expiry_during_operator_blocks_output_and_publication(self):
        request = self.f.start(); operator = self.f.worker.operators.get(self.f.plan["operations"][0]); original = operator.apply
        def slow(*args):
            result = original(*args); self.f.now += timedelta(seconds=121); return result
        with patch.object(operator,"apply",slow): state = self.f.run(request)
        self.assertEqual(state["status"],"failed")
        with self.assertRaises(FrameworkError): self.proposal(request)
    def test_revocation_during_operation_prevents_success(self):
        request = self.f.start(); operator = self.f.worker.operators.get(self.f.plan["operations"][0]); original = operator.apply
        approval = next(a for a in self.f.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == reference(self.f.plan))
        def revoke(*args):
            result = original(*args)
            self.f.specs.retire(reference(approval),action="revoke",rationale="Synthetic owner withdrew the plan.",context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
            return result
        with patch.object(operator,"apply",revoke): self.assertEqual(self.f.run(request)["status"],"failed")
    def test_bad_operator_output_fails_independent_reconciliation(self):
        request = self.f.start(); operator = self.f.worker.operators.get(self.f.plan["operations"][0]); original = operator.apply
        def bad(*args):
            accepted,rejected = original(*args); accepted["rows"][0][0]["value"] = 999.0; return accepted,rejected
        with patch.object(operator,"apply",bad): state = self.f.run(request)
        self.assertEqual(state["status"],"failed"); self.assertIn("operator_specific_reconciliation",state["failure_codes"])
    def test_interruption_keeps_partial_staging_and_never_reruns_operator(self):
        class Crash(BaseException): pass
        request = self.f.start(); original = self.f.store.put; op = self.f.worker.operators.get(self.f.plan["operations"][0])
        def partial(run,category,payload,**kw):
            result = original(run,category,payload,**kw)
            if category == "final": raise Crash()
            return result
        with patch.object(op,"apply",wraps=op.apply) as counter:
            with patch.object(self.f.store,"put",partial):
                with self.assertRaises(Crash): self.f.run(request)
            state = self.f.control.state(reference(request))
            self.f.worker.recover(reference(request),operation_id=self.f.plan["operations"][0]["operation_id"],fence_token=state["fence_token"],context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
            self.assertEqual(counter.call_count,1)
        self.assertEqual(self.f.control.state(reference(request))["status"],"interrupted")
        report = self.f.worker.scan_orphans(reference(request),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertTrue(report["orphans"]); self.assertEqual(report["action"],"retained_no_deletion")
    def test_restart_recovers_complete_worker_receipt_without_reexecution(self):
        request = self.f.start(); op = self.f.worker.operators.get(self.f.plan["operations"][0])
        with patch.object(op,"apply",wraps=op.apply) as count:
            with patch.object(self.f.control,"record_operation",side_effect=PersistenceError("synthetic_lost_ack","Checkpoint not acknowledged.")):
                with self.assertRaises(FrameworkError): self.f.run(request)
            self.assertEqual(count.call_count,1)
        state = self.f.control.state(reference(request)); self.f.runtime.close(); self.f = WorkerFixture(self.tmp.name)
        recovered = self.f.worker.recover(reference(request),operation_id=self.f.plan["operations"][0]["operation_id"],fence_token=state["fence_token"],context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(recovered["status"],"running"); self.assertEqual(self.f.finish(request)["status"],"succeeded")
    def test_corruption_after_execution_denies_publication(self):
        request = self.execute(); artifact = self.f.control.get(self.f.control.state(reference(request))["output_artifacts"][0]); path = self.f.store._file(artifact["locator"])
        os.chmod(path,stat.S_IWRITE); path.write_bytes(b'{"corrupted":true}')
        with self.assertRaises(FrameworkError): self.f.publish(request)
        self.assertEqual(self.f.service.records("PreparationPublicationRecord"),[])
    def test_duplicate_publication_and_previous_versions_are_preserved(self):
        request = self.execute(); proposal = self.proposal(request,"unique-key"); published = self.publish_proposal(proposal)
        same = self.f.publisher.request(reference(request),publication_key="unique-key",context=self.f.author,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(same,proposal); self.assertEqual(self.publish_proposal(same),published)
        with self.assertRaises(FrameworkError): self.proposal(request,"different-key")
        second = self.execute(); new = self.f.publish(second)
        self.assertNotEqual(new["manifest"]["version_id"],published["manifest"]["version_id"])
        self.assertEqual(self.f.control.get(reference(published)),published)
    def test_publication_failure_is_invisible_until_explicit_recovery(self):
        request = self.execute(); proposal = self.proposal(request)
        with patch.object(self.f.store,"promote",side_effect=OSError("Synthetic storage outage")):
            with self.assertRaises(OSError): self.publish_proposal(proposal)
        self.assertEqual(self.f.service.records("PreparationPublicationRecord"),[])
        self.assertTrue(self.f.service.records("PreparationPublicationRecovery"))
        record = self.f.publisher.recover(reference(proposal),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(record["contract_type"],"PreparationPublicationRecord")
    def test_partial_promotion_recovers_only_verified_complete_bytes(self):
        request = self.execute(); proposal = self.proposal(request); original = self.f.store._exclusive; failures = [0]
        def partial(path,body):
            if path.suffix == ".seal" and path.parent.name == "published" and failures[0] == 0:
                failures[0] += 1; raise OSError("Synthetic lost seal write")
            return original(path,body)
        with patch.object(self.f.store,"_exclusive",partial):
            with self.assertRaises(OSError): self.publish_proposal(proposal)
        self.assertEqual(self.f.service.records("PreparationPublicationRecord"),[])
        self.assertEqual(self.f.publisher.recover(reference(proposal),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)["contract_type"],"PreparationPublicationRecord")
    def test_lost_publication_acknowledgement_does_not_duplicate_versions(self):
        request = self.execute(); proposal = self.proposal(request); original = self.f.publisher._command
        def lost(name,*args,**kwargs):
            result = original(name,*args,**kwargs)
            if name == "commit_preparation_publication": raise PersistenceError("synthetic_unknown_commit","Acknowledgement lost.")
            return result
        with patch.object(self.f.publisher,"_command",lost):
            with self.assertRaises(FrameworkError): self.publish_proposal(proposal)
        self.assertEqual(len(self.f.service.records("PreparationPublicationRecord")),1)
        record = self.f.publisher.recover(reference(proposal),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(reference(record),reference(self.f.service.records("PreparationPublicationRecord")[0]))
    def test_production_mode_rejects_local_worker_and_store(self):
        self.f.runtime.config = replace(self.f.runtime.config,mode="production")
        with self.assertRaises(FrameworkError): self.f.runtime.local_preparation_worker(store=self.f.store,adapters={self.f.adapter.source_id:self.f.adapter})
    def test_approval_revoked_during_promotion_prevents_publication_commit(self):
        request = self.execute(); proposal = self.proposal(request); original = self.f.store.promote
        approval = next(a for a in self.f.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == reference(self.f.plan))
        def revoked(*args):
            manifest = original(*args)
            self.f.specs.retire(reference(approval),action="revoke",rationale="Synthetic approval withdrawn during promotion.",context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
            return manifest
        with patch.object(self.f.store,"promote",revoked):
            with self.assertRaises(FrameworkError): self.publish_proposal(proposal)
        self.assertEqual(self.f.service.records("PreparationPublicationRecord"),[])
        self.assertTrue(self.f.service.records("PreparationPublicationIntent"))
    def test_publication_recovery_survives_process_restart(self):
        request = self.execute(); proposal = self.proposal(request)
        with patch.object(self.f.store,"promote",side_effect=OSError("Synthetic promotion interrupted")):
            with self.assertRaises(OSError): self.publish_proposal(proposal)
        self.f.runtime.close(); self.f = WorkerFixture(self.tmp.name)
        result = self.f.publisher.recover(reference(proposal),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(result["contract_type"],"PreparationPublicationRecord")
    def test_execution_rights_do_not_grant_publication_rights(self):
        request = self.execute(); proposal = self.proposal(request)
        grants = [replace(g,actions=tuple(a for a in g.actions if a != "publish_preparation_artifacts")) for g in self.f.grants]
        previous = self.f.runtime.authority.authorization_provider
        self.f.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(grants,previous._secrets,"env:KEY")
        with self.assertRaises(FrameworkError): self.publish_proposal(proposal)
        self.assertEqual(self.f.control.state(reference(request))["status"],"succeeded")
        self.assertEqual(self.f.service.records("PreparationPublicationRecord"),[])
    def test_tampered_published_bytes_are_not_returned_to_readers(self):
        request = self.execute(); record = self.f.publish(request)
        manifest = self.f.store.read(record["manifest"]["locator"])
        path = self.f.store._file(manifest["versions"][0]["locator"])
        os.chmod(path,stat.S_IWRITE); path.write_bytes(b'{"tampered":true}')
        with self.assertRaises(FrameworkError):
            self.f.publisher.read(reference(record),context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        self.assertEqual(self.f.control.get(reference(record)),record)
    def test_replayed_read_never_bypasses_revoked_business_approval(self):
        request = self.execute(); record = self.f.publish(request); command = self.f.cmd()
        self.f.publisher.read(reference(record),context=self.f.owner,command_id=command,expected_head=self.f.service.head)
        approval = next(a for a in self.f.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == reference(self.f.plan))
        self.f.specs.retire(reference(approval),action="revoke",rationale="Business approval revoked after first read.",context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        with self.assertRaises(FrameworkError): self.f.publisher.read(reference(record),context=self.f.owner,command_id=command,expected_head=self.f.service.head)
    def test_replayed_publication_never_bypasses_revoked_permission(self):
        request = self.execute(); proposal = self.proposal(request); command = self.f.cmd()
        self.publish_proposal(proposal,command_id=command)
        grants = [replace(g,actions=tuple(a for a in g.actions if a != "publish_preparation_artifacts")) for g in self.f.grants]
        previous = self.f.runtime.authority.authorization_provider
        self.f.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(grants,previous._secrets,"env:KEY")
        with self.assertRaises(FrameworkError): self.publish_proposal(proposal,command_id=command)
        self.assertEqual(len(self.f.service.records("PreparationPublicationRecord")),1)
    def test_worker_access_checks_are_fresh_after_revocation(self):
        request = self.f.start(); state = self.f.control.state(reference(request)); command = self.f.cmd(); op = self.f.plan["operations"][0]["operation_id"]
        self.f.worker._check_now(reference(request),op,state["fence_token"],self.f.owner,command)
        approval = next(a for a in self.f.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == reference(self.f.plan))
        self.f.specs.retire(reference(approval),action="revoke",rationale="Approval revoked after the first safety check.",context=self.f.owner,command_id=self.f.cmd(),expected_head=self.f.service.head)
        with self.assertRaises(FrameworkError): self.f.worker._check_now(reference(request),op,state["fence_token"],self.f.owner,command)
    def test_replayed_recovery_still_requires_recovery_permission(self):
        request = self.execute(); proposal = self.proposal(request); self.publish_proposal(proposal); command = self.f.cmd()
        self.f.publisher.recover(reference(proposal),context=self.f.owner,command_id=command,expected_head=self.f.service.head)
        grants = [replace(g,actions=tuple(a for a in g.actions if a != "recover_preparation_publication")) for g in self.f.grants]
        previous = self.f.runtime.authority.authorization_provider
        self.f.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(grants,previous._secrets,"env:KEY")
        with self.assertRaises(FrameworkError): self.f.publisher.recover(reference(proposal),context=self.f.owner,command_id=command,expected_head=self.f.service.head)


if __name__ == "__main__": unittest.main()
