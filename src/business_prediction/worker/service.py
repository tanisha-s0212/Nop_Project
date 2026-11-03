"""Bounded local worker using the existing authorization/execution controller."""

from abc import ABC, abstractmethod
from uuid import uuid4
from ..adapters.base import encode_cell
from ..contracts import reference, reference_key
from ..errors import FrameworkError
from ..execution.interfaces import AdapterSourceVersionVerifier, ExecutionEvidenceVerifier
from ..execution.reconciliation import ReconciliationRegistry
from ..semantics.common import clone, digest, field_key, GovernanceError
from .operators import PreparationOperatorRegistry, WorkerReconciliation
from .storage import ArtifactStorage, LocalArtifactStorage, validate_batch


class PreparationWorker(ABC):
    development_only = False
    production_capable = False
    deployment_approval_reference = None
    @abstractmethod
    def run_next(self, request_ref, *, operation_id, fence_token, context, command_id, expected_head): ...
    @abstractmethod
    def recover(self, request_ref, *, operation_id, fence_token, context, command_id, expected_head): ...


class ProductionPreparationWorker(PreparationWorker):
    """External identity/isolation integration; no production worker is supplied."""
    @abstractmethod
    def health_check(self): ...
    @abstractmethod
    def verify_worker_evidence(self,request_reference,completed_state_reference): ...


class LocalWorkerEvidence(ExecutionEvidenceVerifier):
    provider_id = "local-registered-worker-evidence"
    development_only = True
    def __init__(self, runtime, store, operators): self.runtime,self.store,self.operators = runtime,store,operators
    @property
    def version(self): return "1.0-"+self.store.store_id+"-"+self.operators.signature
    def health_check(self): return self.store.health_check()
    def inspect_artifact(self, request_reference, artifact):
        body = self.store.read(artifact["locator"])
        if body["lineage"]["request_reference"] != request_reference: raise GovernanceError("artifact_wrong_execution", "Artifact belongs to another execution.")
        return self.store.describe(artifact["locator"],artifact["role"],self.runtime.service._now())
    def inspect_operation(self, request, authorization, state, operation, evidence_handle):
        prefix = "worker-receipt:"
        if not isinstance(evidence_handle,str) or not evidence_handle.startswith(prefix): raise GovernanceError("untrusted_worker_receipt", "A journal-issued worker receipt is required.")
        ref = {"contract_type":"PreparationWorkerReceipt","contract_version":"1.0","object_id":evidence_handle[len(prefix):],"object_revision":1}
        receipt = self.runtime.service.get(ref); attempt = self.runtime.service.get(receipt["attempt_reference"])
        if (receipt["status"] != "completed" or attempt["request_reference"] != reference(request) or
                attempt["authorization_reference"] != reference(authorization) or attempt["fence_token"] != state["fence_token"] or
                attempt["operation_digest"] != digest(operation) or attempt["operator_versions"] != self.operators.versions()):
            raise GovernanceError("worker_receipt_context_mismatch", "Receipt does not match the exact approved operation, fence, implementation and execution.")
        result = self.store.read(receipt["manifest_locator"])
        if self.store.content_digest(receipt["manifest_locator"]) != receipt["manifest_digest"] or result["attempt_reference"] != reference(attempt):
            raise GovernanceError("worker_receipt_integrity", "Durable worker receipt bytes or attempt lineage changed.")
        report = clone(result["report"])
        for artifact in report["input_artifacts"]+report["output_artifacts"]:
            body = self.store.read(artifact["locator"])
            expected = {"request_reference":reference(request),"authorization_reference":reference(authorization),"plan_reference":request["plan_reference"]}
            if any(body["lineage"][k] != v for k,v in expected.items()): raise GovernanceError("artifact_lineage_mismatch", "Artifact plan/authorization/source lineage is not exact.")
        return report


class LocalPreparationWorker(PreparationWorker):
    development_only = True
    def __init__(self, runtime, *, store, adapters, operators=None):
        if runtime.config.mode != "development": raise GovernanceError("local_worker_production_forbidden", "Local filesystem workers cannot run in production mode.")
        if not isinstance(store,LocalArtifactStorage): raise ValueError("The local worker requires explicitly configured local isolated storage.")
        self.runtime,self.service,self.store = runtime,runtime.service,store
        self.operators = operators if operators is not None else PreparationOperatorRegistry()
        self.sources = AdapterSourceVersionVerifier(adapters)
        self.evidence = LocalWorkerEvidence(runtime,store,self.operators)
        self.reconciliation = ReconciliationRegistry([WorkerReconciliation(self.operators,store,runtime.catalogue.resolve)])
        self.control = runtime.controlled_preparation_service(sources=self.sources,evidence=self.evidence,reconciliation=self.reconciliation)

    def _command(self, operation, context, command_id, expected_head, payload, build):
        return self.service.execute_metadata_command(operation,context=context,command_id=command_id,expected_head=expected_head,payload=payload,build=build)

    def publication_service(self):
        from .publication import PreparationPublicationService
        return PreparationPublicationService(self)

    def _guard(self, request, state, operation_id, fence, context, principal, now, action="execute_preparation_operator"):
        self.control._worker(request,context,action,principal,now)
        if state["fence_token"] != fence: raise GovernanceError("worker_fence_mismatch", "The worker must hold the exact active execution fence.")
        failures = self.control._running(request,state,now)
        if failures: raise GovernanceError("worker_execution_blocked", ";".join(sorted(set(failures))))
        plan = self.control.get(request["plan_reference"])
        operation = next((op for op in plan["operations"] if op["operation_id"] == operation_id),None)
        if operation is None: raise GovernanceError("unregistered_operation_id", "Operation is absent from the exact approved plan.")
        operator = self.operators.get(operation)
        attempt = next((a for a in self.service.records("PreparationWorkerAttempt") if a["request_reference"] == reference(request) and a["operation_id"] == operation_id),None)
        if attempt and attempt["limits"] != {"max_rows":self.store.max_rows,"max_bytes":self.store.max_bytes}:
            raise GovernanceError("worker_budget_configuration_changed", "Resource limits cannot change inside a claimed operation.")
        self.store.assert_isolated([self.runtime.catalogue.get(f["source_metadata_reference"]) for f in request["source_references"]])
        self.control._worker(request,context,action,principal,self.service._now())
        return plan,operation,operator

    def _claim(self, request_ref, operation_id, fence, context, command_id, expected_head):
        def build(principal,context_ref,now):
            request = self.control.get(request_ref); state = self.control.state(request_ref)
            plan,op,operator = self._guard(request,state,operation_id,fence,context,principal,now)
            existing = next((a for a in self.service.records("PreparationWorkerAttempt") if a["request_reference"] == request_ref and a["operation_id"] == operation_id),None)
            if existing: return [],{"attempt_reference":reference(existing)}
            index = len(state["operation_receipts"])
            if index >= len(plan["operations"]) or plan["operations"][index]["operation_id"] != operation_id:
                raise GovernanceError("worker_operation_order", "Only the next approved dependency-ordered operation may execute.")
            attempt = self.control._new("PreparationWorkerAttempt",principal,request["execution_scope"],self.service._now(),request_reference=request_ref,
                state_reference=reference(state),authorization_reference=state["authorization_reference"],plan_reference=request["plan_reference"],operation_id=operation_id,
                operation_digest=digest(op),implementation_reference=operator.operation_type+"@"+operator.implementation_version,
                operator_versions=self.operators.versions(),fence_token=fence,deadline=state["lease_expires_at"],started_at=self.service._now().isoformat(),
                limits={"max_rows":self.store.max_rows,"max_bytes":self.store.max_bytes})
            return [attempt],{"attempt_reference":reference(attempt)}
        outcome = self._command("claim_preparation_worker",context,command_id,expected_head,{"request":request_ref,"operation":operation_id,"fence":fence,"operators":self.operators.versions()},build)
        return self.control.get(outcome["attempt_reference"])

    def _check_now(self, request_ref, op_id, fence, context, command_id):
        def build(principal,context_ref,now):
            request = self.control.get(request_ref); state = self.control.state(request_ref)
            self._guard(request,state,op_id,fence,context,principal,now)
            return [],{"state_reference":reference(state)}
        return self._command("guard_preparation_worker",context,command_id+":fresh:"+str(uuid4()),self.service.head,{"request":request_ref,"operation":op_id,"fence":fence,"caller_check":command_id},build)

    def _capture(self, request):
        fields = request["source_references"]
        if len({(digest(f["discovery_reference"]),f["table_id"]) for f in fields}) != 1:
            raise GovernanceError("worker_multitable_unsupported", "This bounded worker captures one authorized source table; no join is inferred.")
        original = self.runtime.catalogue.get(fields[0]["source_metadata_reference"])
        discovery = self.runtime.catalogue.get(fields[0]["discovery_reference"])
        table = next(t for t in discovery["tables"] if t["table_id"] == fields[0]["table_id"])
        if table["observed_row_count"] > self.store.max_rows: raise GovernanceError("worker_budget_exceeded", "Source population exceeds the approved local worker budget.")
        schema = [{"field_id":f["field_id"],"types":sorted(next(c for c in table["fields"] if c["field_id"] == f["field_id"])["observed"]["type_counts"])} for f in fields]
        rows,ordinals = [],[]
        with self.sources.adapters[original["object_id"]].open_snapshot() as snapshot:
            if snapshot.metadata()["source_version"] != original["source_version"]: raise GovernanceError("worker_source_changed", "Source changed since authorization.")
            for row in snapshot.iter_rows(table["table_id"]):
                if len(rows) >= self.store.max_rows: raise GovernanceError("worker_budget_exceeded", "Source exceeds the row budget.")
                if any(f["field_position"] > len(row.cells) for f in fields): raise GovernanceError("ragged_source_unsupported", "Absent cells cannot be silently replaced by null values.")
                rows.append([encode_cell(row.cells[f["field_position"]-1]) for f in fields]); ordinals.append(row.position)
            snapshot.verify_unchanged()
        batch = {"schema":schema,"rows":rows,"ordinals":ordinals}; validate_batch(batch)
        return batch

    def _field_id(self, operation, plan):
        if operation["operation_type"] == "time_series_aggregation":
            resolved = {}
            for binding in operation["input_binding_references"]:
                field = self.service.get(binding)["physical_field_reference"]
                if field not in operation["source_references"]:
                    raise GovernanceError("worker_field_scope", "Every aggregation input must pin a declared physical source field.")
                resolved[reference_key(binding)] = field["field_id"]
            return resolved
        binding = operation["parameters"].get("binding_reference") or (operation["input_binding_references"][0] if operation["operation_type"] == "type_interpretation" else None)
        if not binding: return None
        field = self.service.get(binding)["physical_field_reference"]
        if field not in operation["source_references"]: raise GovernanceError("worker_field_scope", "Executable field is not explicitly declared by the operation.")
        if operation["operation_type"] == "type_interpretation" and operation["parameters"]["format"] == "canonical_integer_text":
            target = self.service.get(plan["target_reference"]); observation = self.service.get(plan["observation_reference"])
            protected = [target["semantic_binding_reference"]]+observation["entity_binding_references"]+([observation["time_binding_reference"]] if observation["time_binding_reference"] else [])
            if any(field_key(self.service.get(r)["physical_field_reference"]) == field_key(field) for r in protected):
                raise GovernanceError("protected_type_interpretation", "This conversion cannot redefine approved target, time or identity fields through an alias.")
        return field["field_id"]

    def _receipt_token(self, attempt): return "receipt-"+attempt["object_id"]
    def _receipt_locator(self, attempt): return ":".join(("artifact",self.store.store_id,attempt["request_reference"]["object_id"],"receipts",self._receipt_token(attempt)))

    def clock_now(self):
        with self.service._journal.lock: return self.service._now()

    def _register_receipt(self, attempt, locator, context, *, failed_codes=()):
        def build(principal,context_ref,now):
            request = self.control.get(attempt["request_reference"])
            self.control._worker(request,context,"execute_preparation_operator",principal,now)
            existing = next((r for r in self.service.records("PreparationWorkerReceipt") if r["attempt_reference"] == reference(attempt)),None)
            if existing: return [],{"receipt_reference":reference(existing)}
            body = self.store.read(locator) if locator else None
            receipt = self.control._new("PreparationWorkerReceipt",principal,request["execution_scope"],now,
                object_id=attempt["object_id"]+"-receipt",
                request_reference=reference(request),attempt_reference=reference(attempt),status="failed" if failed_codes else "completed",
                manifest_locator=locator,manifest_digest=self.store.content_digest(locator) if locator else None,
                artifact_locators=[a["locator"] for a in body["report"]["input_artifacts"]+body["report"]["output_artifacts"]] if body else [],
                failure_codes=list(failed_codes),completed_at=now.isoformat())
            return [receipt],{"receipt_reference":reference(receipt)}
        result = self._command("record_preparation_worker_receipt",context,"worker-receipt:"+attempt["object_id"],self.service.head,
            {"attempt":reference(attempt),"locator":locator,"failure_codes":list(failed_codes)},build)
        return self.control.get(result["receipt_reference"])

    def _checkpoint(self, attempt, context):
        receipt = self._register_receipt(attempt,self._receipt_locator(attempt),context)
        return self.control.record_operation(attempt["request_reference"],operation_id=attempt["operation_id"],
            evidence_handle="worker-receipt:"+receipt["object_id"],context=context,command_id="worker-checkpoint:"+attempt["object_id"],expected_head=self.service.head)

    def run_next(self, request_ref, *, operation_id, fence_token, context, command_id, expected_head):
        if not isinstance(command_id,str) or not command_id.strip(): raise GovernanceError("invalid_command", "An explicit operation idempotency key is required.")
        attempt = self._claim(request_ref,operation_id,fence_token,context,command_id+":claim",expected_head)
        state = self.control.state(request_ref)
        completed = [self.control.get(r) for r in state["operation_receipts"]]
        if any(r["operation_id"] == operation_id for r in completed): return state
        locator = self._receipt_locator(attempt)
        try:
            self.store.read(locator)
        except FileNotFoundError: pass
        else:
            self._check_now(request_ref,operation_id,fence_token,context,command_id+":recover-check")
            return self._checkpoint(attempt,context)
        request = self.control.get(request_ref); plan = self.control.get(request["plan_reference"])
        if attempt["limits"] != {"max_rows":self.store.max_rows,"max_bytes":self.store.max_bytes}:
            raise GovernanceError("worker_budget_configuration_changed", "A claimed operation cannot silently inherit different storage/resource limits.")
        operation = next(op for op in plan["operations"] if op["operation_id"] == operation_id); operator = self.operators.get(operation)
        # Claim is written before the pure operator is ever invoked. Existing
        # claims with no complete receipt are never automatically rerun.
        try:
            self.store.put(request["object_id"],"claims",{"attempt_reference":reference(attempt),"fence_token":fence_token},token=attempt["object_id"])
        except FileExistsError:
            raise GovernanceError("worker_attempt_incomplete", "A started operation has no complete receipt; use explicit recovery, never rerun blindly.") from None
        try:
            self._check_now(request_ref,operation_id,fence_token,context,command_id+":before-input")
            lineage = {"request_reference":request_ref,"authorization_reference":attempt["authorization_reference"],"plan_reference":request["plan_reference"],
                "source_references":request["source_references"],"operation_digest":digest(operation),"attempt_reference":reference(attempt)}
            previous = [self.control.get(r) for r in state["output_artifacts"] if self.control.get(r)["role"] == "accepted"]
            if previous:
                if len(previous) != 1: raise GovernanceError("worker_multitable_unsupported", "Only one preceding accepted partition is supported.")
                input_locator = previous[0]["locator"]; before = self.store.read(input_locator)["batch"]
            else:
                before = self._capture(request)
                input_locator = self.store.put(request["object_id"],"inputs",{"batch":before,"lineage":lineage})
            self._check_now(request_ref,operation_id,fence_token,context,command_id+":before-operator")
            accepted,rejected = operator.apply(clone(before),operation,self._field_id(operation,plan))
            validate_batch(accepted); validate_batch(rejected)
            if len(accepted["rows"])+len(rejected["rows"]) > self.store.max_rows: raise GovernanceError("worker_budget_exceeded", "Operator exceeded its bounded output population.")
            self._check_now(request_ref,operation_id,fence_token,context,command_id+":before-output")
            final = operation_id == plan["operations"][-1]["operation_id"]
            output_locators = [self.store.put(request["object_id"],"final" if final else "intermediate",{"batch":b,"lineage":lineage}) for b in (accepted,rejected)]
            self._check_now(request_ref,operation_id,fence_token,context,command_id+":before-receipt")
            now = self.clock_now()
            report = {"request_reference":request_ref,"authorization_reference":attempt["authorization_reference"],"fence_token":fence_token,
                "operation_digest":digest(operation),"started_at":attempt["started_at"],"completed_at":now.isoformat(),"complete":True,
                "accepted_count":len(accepted["rows"]),"rejected_count":len(rejected["rows"]),
                "input_artifacts":[self.store.describe(input_locator,"input",now)],
                "output_artifacts":[self.store.describe(loc,role,now) for loc,role in zip(output_locators,("accepted","rejected"))],
                "evidence_reference":"worker-receipt:"+attempt["object_id"]+"-receipt"}
            self.store.put(request["object_id"],"receipts",{"attempt_reference":reference(attempt),"report":report},token=self._receipt_token(attempt))
        except Exception as exc:
            # No transformation is repeated after an uncertain storage result.
            try: self.store.read(locator)
            except (OSError,FrameworkError):
                codes = [exc.code if isinstance(exc,FrameworkError) else "worker_operation_failed"]
                self._register_receipt(attempt,None,context,failed_codes=codes)
                def fail(principal,ctx,now):
                    current = self.control.state(request_ref)
                    self.control._worker(request,context,"record_preparation_operation",principal,now)
                    return self.control._terminal(request,current,principal,now,"failed",codes)
                outcome = self._command("fail_preparation_worker",context,command_id+":failed",self.service.head,{"attempt":reference(attempt),"codes":codes},fail)
                return self.control.get(outcome["state_reference"])
        return self._checkpoint(attempt,context)

    def recover(self, request_ref, *, operation_id, fence_token, context, command_id, expected_head):
        if not isinstance(command_id,str) or not command_id.strip(): raise GovernanceError("invalid_command", "An explicit recovery command key is required.")
        def guard(principal,ctx,now):
            request = self.control.get(request_ref); state = self.control.state(request_ref)
            self.control._authorize(context,"recover_preparation_worker",request_ref,request["execution_scope"],principal,now)
            if state["fence_token"] != fence_token: raise GovernanceError("worker_fence_mismatch", "Recovery must identify the exact original execution fence.")
            return [],{"state_reference":reference(state)}
        self._command("recover_preparation_worker",context,command_id+":guard:"+str(uuid4()),expected_head,{"request":request_ref,"operation":operation_id,"caller_recovery":command_id},guard)
        attempt = next((a for a in self.service.records("PreparationWorkerAttempt") if a["request_reference"] == request_ref and a["operation_id"] == operation_id),None)
        if attempt is None: raise GovernanceError("worker_attempt_not_found", "No started attempt exists to recover.")
        try: self.store.read(self._receipt_locator(attempt))
        except (OSError,FrameworkError):
            return self.control.interrupt(request_ref,reason="Incomplete worker attempt retained; original inputs and orphan staging were preserved.",context=context,
                command_id=command_id+":interrupt",expected_head=self.service.head)
        self._check_now(request_ref,operation_id,fence_token,context,command_id+":checkpoint-check")
        return self._checkpoint(attempt,context)

    def scan_orphans(self, request_ref, *, context, command_id, expected_head):
        def build(principal,ctx,now):
            request = self.control.get(request_ref)
            self.control._authorize(context,"recover_preparation_worker",request_ref,request["execution_scope"],principal,now)
            known = []
            for a in self.service.records("PreparationArtifact"):
                if a["request_reference"] == request_ref: known.append(a["locator"])
            for r in self.service.records("PreparationWorkerReceipt"):
                if r["request_reference"] == request_ref and r["manifest_locator"]: known.append(r["manifest_locator"])
            for a in self.service.records("PreparationWorkerAttempt"):
                if a["request_reference"] == request_ref: known.append(":".join(("artifact",self.store.store_id,request_ref["object_id"],"claims",a["object_id"])))
            for p in self.service.records("PreparationPublicationRecord"):
                if p["request_reference"] == request_ref:
                    known.append(p["manifest"]["locator"])
                    known += [v["locator"] for v in self.store.read(p["manifest"]["locator"])["versions"]]
            orphans = [r for r in self.store.orphans(known) if r["locator"].split(":")[2] == request_ref["object_id"]]
            return [],{"request_reference":request_ref,"orphans":orphans,"action":"retained_no_deletion"}
        return self._command("scan_preparation_orphans",context,command_id,expected_head,{"request":request_ref},build)
