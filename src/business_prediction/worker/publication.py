"""Separate publication permission and recoverable immutable promotion.

Physical promotion alone is not publication. Readers require both a verified
storage manifest and a journal-issued publication record with fresh access.
"""

from ..contracts import reference
from uuid import uuid4
from ..errors import FrameworkError
from ..execution.reconciliation import check
from ..semantics.common import digest, GovernanceError
from .storage import ProductionArtifactStorage
from .service import ProductionPreparationWorker


class PreparationPublicationService:
    def __init__(self, worker):
        self.worker,self.control,self.runtime,self.store = worker,worker.control,worker.runtime,worker.store
        self.service = self.runtime.service
        if self.runtime.config.mode == "production" and (not isinstance(worker,ProductionPreparationWorker) or worker.development_only or not worker.production_capable or
                not worker.deployment_approval_reference or worker.health_check().get("ready") is not True or not isinstance(self.store,ProductionArtifactStorage) or
                not self.store.production_capable or not self.store.deployment_approval_reference):
            raise GovernanceError("unsafe_production_publication", "Production requires approved worker isolation, immutable storage and publication integrations.")

    def _command(self, name, context, command_id, head, payload, build):
        return self.service.execute_metadata_command(name,context=context,command_id=command_id,expected_head=head,payload=payload,build=build)

    def request(self, request_ref, *, publication_key, context, command_id, expected_head):
        def build(principal,ctx,now):
            request = self.control.get(request_ref); state = self.control.state(request_ref)
            self.control._authorize(context,"request_preparation_publication",reference(state),request["execution_scope"],principal,now)
            if state["status"] != "succeeded": raise GovernanceError("publication_execution_incomplete", "Failed, partial or unfinalized work cannot be published.")
            existing = [r for r in self.service.records("PreparationPublicationRequest") if r["purpose_scope"] == request["purpose_scope"] and r["execution_scope"]["namespace"] == request["execution_scope"]["namespace"]]
            same = next((r for r in existing if r["publication_key"] == publication_key or r["request_reference"] == request_ref),None)
            if same:
                if same["request_reference"] != request_ref or same["publication_key"] != publication_key: raise GovernanceError("duplicate_publication_conflict", "A publication key/execution is already bound to a different immutable intent.")
                return [],{"record_reference":reference(same)}
            provenance = next(p for p in self.service.records("PreparationProvenanceRecord") if p["state_reference"] == reference(state))
            record = self.control._new("PreparationPublicationRequest",principal,request["execution_scope"],now,request_reference=request_ref,
                publication_key=publication_key,completed_state_reference=reference(state),provenance_reference=reference(provenance))
            return [record],{"record_reference":reference(record)}
        outcome = self._command("request_preparation_publication",context,command_id,expected_head,{"request":request_ref,"publication_key":publication_key},build)
        return self.control.get(outcome["record_reference"])

    def _verify(self, proposal, now):
        request = self.control.get(proposal["request_reference"]); state = self.control.state(reference(request))
        if state["status"] != "succeeded" or reference(state) != proposal["completed_state_reference"]:
            raise GovernanceError("publication_execution_incomplete", "Publication must use the exact committed successful state.")
        if self.runtime.config.mode == "production" and self.worker.verify_worker_evidence(reference(request),reference(state)) is not True:
            raise GovernanceError("publication_worker_isolation_unverified", "Production worker identity/isolation evidence could not be verified.")
        failures,_,_ = self.control._current(request,now,self.control.get(state["authorization_reference"]))
        if failures: raise GovernanceError("publication_dependencies_stale", ";".join(failures))
        plan = self.control.get(request["plan_reference"])
        receipts = [self.control.get(r) for r in state["operation_receipts"]]
        if len(receipts) != len(plan["operations"]): raise GovernanceError("publication_execution_incomplete", "Every planned operation must have a completed receipt.")
        artifact_refs,checks,rejected = [],[],[]
        for op,receipt in zip(plan["operations"],receipts):
            if not receipt["complete"] or receipt["operation_digest"] != digest(op): raise GovernanceError("publication_receipt_mismatch", "Operation receipt version/completeness differs from the plan.")
            report = self.worker.evidence.inspect_operation(request,self.control.get(state["authorization_reference"]),state,op,receipt["evidence_reference"])
            for ref in receipt["input_artifacts"]+receipt["output_artifacts"]:
                artifact = self.control.get(ref); current = self.worker.evidence.inspect_artifact(reference(request),artifact)
                if any(current[k] != artifact[k] for k in current if k not in ("measured_at","evidence_reference")):
                    raise GovernanceError("publication_artifact_corrupt", "Artifact bytes, schema, counts or source lineage changed after execution.")
            strategy = self.worker.reconciliation.select(op)
            if strategy is None: raise GovernanceError("publication_reconciler_missing", "Publication requires the exact supported reconciliation implementation.")
            operation_checks = strategy.validate(op,report)
            if not operation_checks or any(c["status"] != "passed" for c in operation_checks): raise GovernanceError("publication_reconciliation_failed", "Independent operation reconciliation did not pass.")
            checks += operation_checks
            rejected += [ref for ref in receipt["output_artifacts"] if self.control.get(ref)["role"] == "rejected"]
        accepted = [r for r in state["output_artifacts"] if self.control.get(r)["role"] == "accepted"]
        if len(state["input_artifacts"]) != 1 or len(accepted) != 1: raise GovernanceError("publication_grain_unsupported", "This bounded publisher requires one native source/accepted partition.")
        original = self.store.read(self.control.get(state["input_artifacts"][0])["locator"])["batch"]
        final = self.store.read(self.control.get(accepted[0])["locator"])["batch"]
        rejected_batches = [self.store.read(self.control.get(r)["locator"])["batch"] for r in rejected]
        all_ordinals = final["ordinals"]+[n for b in rejected_batches for n in b["ordinals"]]
        closure = len(all_ordinals) == len(set(all_ordinals)) and set(all_ordinals) == set(original["ordinals"])
        checks.append(check("end_to_end_partition",closure,"Final accepted plus every rejection partition must cover each original physical record exactly once."))
        if not closure: raise GovernanceError("publication_partition_failed", "End-to-end accepted/rejected lineage does not reconcile.")
        artifact_refs = accepted+rejected
        # Long inspection cannot silently outlive approval or operational grants.
        failures,_,_ = self.control._current(request,self.service._now(),self.control.get(state["authorization_reference"]))
        if failures: raise GovernanceError("publication_dependencies_stale", ";".join(failures))
        return artifact_refs,checks

    @property
    def store_reference(self): return self.store.provider_id+"@"+self.store.version+":"+self.store.store_id

    def publish(self, proposal_ref, *, context, command_id, expected_head):
        if not isinstance(command_id,str) or not command_id.strip(): raise GovernanceError("invalid_command", "An explicit publication idempotency key is required.")
        def fresh_access(principal,ctx,now):
            proposal = self.control.get(proposal_ref); request = self.control.get(proposal["request_reference"])
            self.control._authorize(context,"publish_preparation_artifacts",proposal_ref,request["execution_scope"],principal,now)
            refs,_ = self._verify(proposal,now)
            if self.runtime.config.mode == "production" and self.store.authorize_access(principal,"publish",request["execution_scope"],refs,None) is not True:
                raise GovernanceError("publication_storage_access_denied", "Production storage did not authorize this publication attempt.")
            return [],{"proposal_reference":proposal_ref,"checked_at":self.service._now().isoformat()}
        # Write replay remains idempotent. Permission/integrity checks are never
        # replayed from a cached outcome, including reads and recovery calls.
        self._command("prepare_preparation_publication",context,command_id+":access:"+str(uuid4()),expected_head,
            {"proposal":proposal_ref,"caller_publication":command_id,"fresh_access":True},fresh_access)
        def prepare(principal,ctx,now):
            proposal = self.control.get(proposal_ref); request = self.control.get(proposal["request_reference"])
            self.control._authorize(context,"publish_preparation_artifacts",proposal_ref,request["execution_scope"],principal,now)
            refs,checks = self._verify(proposal,now)
            if self.runtime.config.mode == "production" and self.store.authorize_access(principal,"publish",request["execution_scope"],refs,None) is not True:
                raise GovernanceError("publication_storage_access_denied", "Production artifact storage did not authorize this publication scope.")
            proof = self.control._authorize(context,"publish_preparation_artifacts",proposal_ref,request["execution_scope"],principal,self.service._now())
            existing = next((i for i in self.service.records("PreparationPublicationIntent") if i["publication_request_reference"] == proposal_ref),None)
            if existing:
                if existing["artifact_references"] != refs or existing["store_reference"] != self.store_reference: raise GovernanceError("publication_conflict", "Existing promotion intent cannot be changed.")
                return [],{"intent_reference":reference(existing)}
            intent = self.control._new("PreparationPublicationIntent",principal,request["execution_scope"],self.service._now(),request_reference=reference(request),
                publication_request_reference=proposal_ref,artifact_references=refs,store_reference=self.store_reference,authorization_evidence=proof,checks=checks)
            return [intent],{"intent_reference":reference(intent)}
        result = self._command("prepare_preparation_publication",context,command_id+":prepare",self.service.head,{"proposal":proposal_ref,"store":self.store_reference},prepare)
        intent = self.control.get(result["intent_reference"])
        existing = next((p for p in self.service.records("PreparationPublicationRecord") if p["intent_reference"] == reference(intent)),None)
        if existing: return existing  # historical idempotent response, never a read grant
        try:
            descriptors = [self.control.get(r) for r in intent["artifact_references"]]
            manifest = self.store.promote(intent["object_id"],intent["request_reference"]["object_id"],descriptors)
            def commit(principal,ctx,now):
                proposal = self.control.get(proposal_ref); request = self.control.get(proposal["request_reference"])
                self.control._authorize(context,"publish_preparation_artifacts",proposal_ref,request["execution_scope"],principal,now)
                refs,checks = self._verify(proposal,now)
                if self.runtime.config.mode == "production" and self.store.authorize_access(principal,"publish",request["execution_scope"],refs,None) is not True:
                    raise GovernanceError("publication_storage_access_denied", "Storage authority must remain current through publication commit.")
                if refs != intent["artifact_references"]: raise GovernanceError("publication_conflict", "Publication inputs changed after intent creation.")
                body = self.store.read(manifest["locator"])
                expected = [(a["locator"],a["content_digest"],a["role"]) for a in descriptors]
                actual = [(v["original_locator"],v["content_digest"],v["role"]) for v in body["versions"]]
                if (body["intent_id"] != intent["object_id"] or actual != expected or self.store.content_digest(manifest["locator"]) != manifest["content_digest"]):
                    raise GovernanceError("publication_manifest_corrupt", "Physical promotion manifest differs from the immutable intent.")
                for version in body["versions"]:
                    if self.store.content_digest(version["locator"]) != version["content_digest"]: raise GovernanceError("publication_artifact_corrupt", "A promoted artifact failed integrity verification.")
                proof = self.control._authorize(context,"publish_preparation_artifacts",proposal_ref,request["execution_scope"],principal,self.service._now())
                previous = next((p for p in self.service.records("PreparationPublicationRecord") if p["intent_reference"] == reference(intent)),None)
                if previous: return [],{"record_reference":reference(previous)}
                record = self.control._new("PreparationPublicationRecord",principal,request["execution_scope"],self.service._now(),request_reference=reference(request),
                    publication_request_reference=proposal_ref,intent_reference=reference(intent),artifact_references=refs,store_reference=self.store_reference,
                    authorization_evidence=proof,manifest=manifest,checks=checks,published_at=self.service._now().isoformat())
                return [record],{"record_reference":reference(record)}
            outcome = self._command("commit_preparation_publication",context,command_id+":commit",self.service.head,{"intent":reference(intent),"manifest":manifest},commit)
            return self.control.get(outcome["record_reference"])
        except Exception as exc:
            self._record_failure(intent,context,command_id+":failure",exc.code if isinstance(exc,FrameworkError) else "publication_storage_failed")
            raise

    def _record_failure(self, intent, context, command_id, code):
        def build(principal,ctx,now):
            proposal = self.control.get(intent["publication_request_reference"]); request = self.control.get(proposal["request_reference"])
            self.control._authorize(context,"publish_preparation_artifacts",reference(proposal),request["execution_scope"],principal,now)
            event = self.control._new("PreparationPublicationRecovery",principal,request["execution_scope"],now,request_reference=reference(request),
                publication_request_reference=reference(proposal),intent_reference=reference(intent),failure_codes=[code],known_locators=[],recorded_at=now.isoformat(),
                reason="Publication attempt acknowledgement failed; visibility requires a committed publication record and verified immutable manifest.")
            return [event],{"record_reference":reference(event)}
        try: self._command("record_publication_recovery",context,command_id,self.service.head,{"intent":reference(intent),"code":code},build)
        except FrameworkError: pass  # main failure/audit remains authoritative; never synthesize success

    def recover(self, proposal_ref, *, context, command_id, expected_head):
        if not isinstance(command_id,str) or not command_id.strip(): raise GovernanceError("invalid_command", "An explicit recovery idempotency key is required.")
        proposal = self.control.get(proposal_ref)
        def authorize(principal,ctx,now):
            request = self.control.get(proposal["request_reference"])
            self.control._authorize(context,"recover_preparation_publication",proposal_ref,request["execution_scope"],principal,now)
            return [],{"proposal":proposal_ref}
        self._command("record_publication_recovery",context,command_id+":authorize:"+str(uuid4()),expected_head,{"proposal":proposal_ref,"action":"explicit_recovery","caller_recovery":command_id},authorize)
        return self.publish(proposal_ref,context=context,command_id=command_id+":publication",expected_head=self.service.head)

    def read(self, record_ref, *, context, command_id, expected_head):
        if not isinstance(command_id,str) or not command_id.strip(): raise GovernanceError("invalid_command", "An explicit read audit correlation key is required.")
        def build(principal,ctx,now):
            record = self.control.get(record_ref); request = self.control.get(record["request_reference"])
            self.control._authorize(context,"read_preparation_publication",record_ref,request["execution_scope"],principal,now)
            if record["contract_type"] != "PreparationPublicationRecord": raise GovernanceError("publication_not_committed", "Only a journal-issued publication record can expose a version.")
            if self.runtime.config.mode == "production" and self.store.authorize_access(principal,"read",request["execution_scope"],record["artifact_references"],None) is not True:
                raise GovernanceError("publication_storage_access_denied", "Production storage did not authorize this read scope.")
            plan = self.control.get(request["plan_reference"])
            findings = self.control.specs.validator.inspect(plan,self.control.specs,now)["findings"]
            if findings: raise GovernanceError("publication_use_blocked", "Current business approvals or schema evidence no longer permit use.")
            manifest = record["manifest"]
            if self.store.content_digest(manifest["locator"]) != manifest["content_digest"]: raise GovernanceError("publication_manifest_corrupt", "Published manifest changed.")
            body = self.store.read(manifest["locator"])
            for version in body["versions"]:
                if self.store.content_digest(version["locator"]) != version["content_digest"]: raise GovernanceError("publication_artifact_corrupt", "Published object changed.")
            return [],{"publication_reference":record_ref,"manifest":manifest,"versions":body["versions"]}
        return self._command("read_preparation_publication",context,command_id+":fresh:"+str(uuid4()),expected_head,{"record":record_ref,"caller_read":command_id},build)
