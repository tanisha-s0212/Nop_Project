"""Controlled metadata orchestration, never a data transformation dispatcher."""

from datetime import timedelta
from uuid import uuid4

from ..contracts import reference
from ..errors import FrameworkError
from ..semantics.common import clone, digest, field_key, GovernanceError, instant
from ..specifications.service import exact_references
from .contracts import TERMINAL, artifact_fields
from .interfaces import SourceVersionVerifier, ExecutionEvidenceVerifier
from .reconciliation import ReconciliationRegistry, check


class ControlledPreparationService:
    def __init__(self, runtime, *, sources=None, evidence=None, operations=None, reconciliation=None):
        self.runtime, self.service = runtime, runtime.service
        self.specs = runtime.specification_service(operations=operations)  # shared mode/security checks
        if sources is not None and not isinstance(sources, SourceVersionVerifier): raise ValueError("Use a trusted source-verification interface.")
        if evidence is not None and not isinstance(evidence, ExecutionEvidenceVerifier): raise ValueError("Use a trusted execution-evidence interface.")
        self.sources, self.evidence = sources, evidence
        self.reconciliation = reconciliation if reconciliation is not None else ReconciliationRegistry()
        self._providers()  # unsafe production adapters are rejected at construction

    def _providers(self):
        missing = []
        for name, provider in (("source_verifier", self.sources), ("execution_evidence_verifier", self.evidence)):
            if provider is None: missing.append(name+"_missing"); continue
            if self.runtime.config.mode == "production" and (provider.development_only or not provider.production_capable or not provider.deployment_approval_reference):
                raise GovernanceError("unsafe_production_execution_provider", "Production rejects local/unapproved execution evidence adapters.")
            try:
                if provider.health_check().get("ready") is not True: missing.append(name+"_unavailable")
            except Exception:
                missing.append(name+"_unavailable")
        return missing

    def _versions(self):
        return [[p.provider_id, p.version] for p in (self.sources, self.evidence) if p is not None]

    def _new(self, kind, principal, scope, now, **body):
        document = {"contract_type": kind, "contract_version": "1.0", "object_id": str(uuid4()), "object_revision": 1,
            "created_at": now.isoformat(), "owner_reference": principal, "purpose_scope": scope["purpose"], "execution_scope": clone(scope), **clone(body)}
        document["dependency_versions"] = list({digest(r): r for r in exact_references(body)}.values())
        return document

    def _command(self, operation, context, command_id, expected_head, payload, build):
        return self.service.execute_metadata_command(operation, context=context, command_id=command_id,
            expected_head=expected_head, payload=payload, build=build)

    def _authorize(self, context, action, subject, scope, principal, now):
        proof = self.specs._authorize(context, action, subject, scope, now)
        if proof["principal_reference"] != principal:
            raise GovernanceError("execution_identity_changed", "Authenticated principal changed within the execution-control command.")
        return proof

    def get(self, ref):
        """Trusted-backend history access; an external API must enforce read ACLs."""
        return self.service.get(ref)

    def state(self, request_ref):
        with self.service._journal.lock:
            states = [s for s in self.service.records("PreparationExecutionState") if s["request_reference"] == request_ref]
            if not states: raise GovernanceError("execution_not_found", "No journal-issued state exists for this exact request.")
            return states[-1]

    def _next(self, request, principal, now, status, old=None, **changes):
        body = {"request_reference": reference(request), "previous_state_reference": reference(old) if old else None,
            "authorization_reference": None, "status": status, "started_at": None, "finished_at": None,
            "lease_expires_at": None, "fence_token": None, "operation_receipts": [], "input_artifacts": [], "output_artifacts": [],
            "failure_codes": [], "failure_detail": None, "reconciliation_reference": None}
        if old:
            body.update({k: clone(old[k]) for k in body if k not in ("request_reference", "previous_state_reference", "status")})
        body.update(changes)
        if status in TERMINAL: body["finished_at"] = now.isoformat()
        new = self._new("PreparationExecutionState", principal, request["execution_scope"], now, **body)
        new["object_id"] = old["object_id"] if old else request["object_id"]+":state"
        new["object_revision"] = old["object_revision"]+1 if old else 1
        return new

    def _provenance(self, request, state, principal, now):
        plan = self.get(request["plan_reference"])
        receipts = [self.get(r) for r in state["operation_receipts"] if self.runtime.catalogue.resolve(r)]
        reconciliations = [r["reconciliation_reference"] for r in receipts]
        if state["reconciliation_reference"]: reconciliations.append(state["reconciliation_reference"])
        return self._new("PreparationProvenanceRecord", principal, request["execution_scope"], now,
            request_reference=reference(request), state_reference=reference(state), authorization_reference=state["authorization_reference"],
            plan_reference=request["plan_reference"], source_references=request["source_references"], operations=plan["operations"],
            input_artifacts=state["input_artifacts"], output_artifacts=state["output_artifacts"], operation_receipts=state["operation_receipts"],
            reconciliation_references=reconciliations, status=state["status"], started_at=state["started_at"], finished_at=state["finished_at"],
            failure_codes=state["failure_codes"], failure_detail=state["failure_detail"],
            artifact_disposition="eligible_manifest" if state["status"] == "succeeded" else "quarantined" if state["output_artifacts"] else "no_registered_output",
            limitations=["Operator implementation and evidence are provided by the configured worker/verifier; this controller does not dispatch transformations.",
                "Only a successful committed terminal manifest makes outputs eligible; file publication is not performed by this service.",
                "Uncheckpointed external staging remains untrusted and requires provider-controlled orphan recovery."])

    def _terminal(self, request, old, principal, now, status, codes, **changes):
        new = self._next(request, principal, now, status, old, failure_codes=sorted(set(codes)), **changes)
        return [new, self._provenance(request, new, principal, now)], {"state_reference": reference(new)}

    def request(self, plan_ref, *, request_key, worker_principal_reference, lease_seconds, purpose, context, command_id, expected_head):
        payload = {"plan": plan_ref, "request_key": request_key, "worker": worker_principal_reference, "lease_seconds": lease_seconds, "purpose": purpose}
        def build(principal, context_ref, now):
            plan = self.get(plan_ref)
            if plan["contract_type"] != "DataPreparationPlanSpecification": raise GovernanceError("wrong_subject_type", "Execution requires an exact preparation-plan revision.")
            request = self._new("PreparationExecutionRequest", principal, plan["specification_scope"], now, request_key=request_key,
                plan_reference=plan_ref, plan_digest=digest(plan), source_references=plan["source_references"],
                worker_principal_reference=worker_principal_reference, lease_seconds=lease_seconds, purpose=purpose)
            self.runtime.catalogue.registry.validate(request, resolver=self.runtime.catalogue.resolve)
            old = next((r for r in self.service.records("PreparationExecutionRequest") if r["request_key"] == request_key
                and r["execution_scope"]["namespace"] == request["execution_scope"]["namespace"] and r["purpose_scope"] == request["purpose_scope"]), None)
            self._authorize(context, "request_preparation_execution", reference(old or request), request["execution_scope"], principal, now)
            if old:
                if old["owner_reference"] != principal or any(old[k] != request[k] for k in payload_keys()):
                    raise GovernanceError("duplicate_execution_conflict", "A request key is already bound to another exact intent; use replay, never silently rerun.")
                return [], {"request_reference": reference(old)}
            state = self._next(request, principal, now, "requested")
            return [request, state], {"request_reference": reference(request)}
        result = self._command("request_preparation_execution", context, command_id, expected_head, payload, build)
        return self.get(result["request_reference"])

    def _current(self, request, now, authorization=None):
        plan = self.get(request["plan_reference"])
        checked = self.specs.validator.inspect(plan, self.specs, now)
        failures = [f["code"] for f in checked["findings"]] + self._providers()
        if not plan["operations"]: failures.append("no_executable_operations")
        if any(self.reconciliation.select(op) is None for op in plan["operations"]): failures.append("reconciliation_strategy_unavailable")
        verified = {}
        if not failures:
            try:
                verified = clone(self.sources.verify(request["source_references"], self.runtime.catalogue))
                expected = [{"source_reference": f["source_metadata_reference"], "discovery_reference": f["discovery_reference"],
                             "source_version": f["source_version"], "schema_version": f["schema_version"]} for f in request["source_references"]]
                if (set(verified) != {"provider_reference", "verified_snapshots"} or verified["provider_reference"] != self.sources.provider_id+"@"+self.sources.version or
                        {digest(s) for s in verified["verified_snapshots"]} != {digest(s) for s in expected}):
                    failures.append("source_verification_incomplete")
            except FrameworkError as exc: failures.append(exc.code)
            except Exception: failures.append("source_verification_unavailable")
        # Verifiers may perform I/O. Re-evaluate time-sensitive approval state
        # after it completes instead of using a stale command-start timestamp.
        refreshed = self.service._now()
        if refreshed > now:
            checked = self.specs.validator.inspect(plan, self.specs, refreshed)
            failures += [f["code"] for f in checked["findings"]]
        now = refreshed
        if authorization:
            decision = self.get(authorization["decision_reference"])
            if now >= instant(authorization["expires_at"]): failures.append("execution_authorization_expired")
            if any(d["affected_authorization_reference"] == reference(authorization) for d in self.service.records("PreparationExecutionDecision")):
                failures.append("execution_authorization_revoked")
            if (not self.runtime.authority.verify_record(decision["authorization_evidence"], now) or
                    not self.runtime.authority.verify_continuing_authority(decision["authorization_evidence"], now)):
                failures.append("execution_authority_not_current")
            if authorization["provider_versions"] != self._versions() or authorization["validator_versions"] != self.specs.operations.versions() or authorization["reconciler_versions"] != self.reconciliation.versions():
                failures.append("execution_provider_configuration_changed")
            for ref in authorization["approval_references"]:
                a = self.get(ref)
                state = self.specs._approval_status(a, now) if a["contract_type"] == "SpecificationApprovalRecord" else self.service._approval_state(a, now)
                if state not in ("approved", "usable"): failures.append("pinned_approval_"+state)
        return sorted(set(failures)), checked["approval_references"], verified

    def authorize(self, request_ref, *, approve, expires_at, rationale, context, command_id, expected_head):
        if type(approve) is not bool: raise GovernanceError("invalid_decision", "Approve must be an explicit boolean decision.")
        payload = {"request": request_ref, "approve": approve, "expires_at": expires_at, "rationale": rationale}
        def build(principal, context_ref, now):
            request = self.get(request_ref); old = self.state(request_ref)
            proof = self._authorize(context, "authorize_preparation_execution", request_ref, request["execution_scope"], principal, now)
            if self.service._policy.independent_review and principal == request["owner_reference"]:
                raise GovernanceError("independent_execution_authorizer_required", "The execution requester cannot authorize their own request.")
            if old["status"] != "requested": raise GovernanceError("execution_already_decided", "Each request has one execution decision; terminal or authorized requests cannot be silently rerun.")
            failures, candidates, verified = self._current(request, now) if approve else (["explicit_execution_denial"], [], {})
            now = self.service._now()
            proof = self._authorize(context, "authorize_preparation_execution", request_ref, request["execution_scope"], principal, now)
            if approve and instant(expires_at) <= now: failures.append("execution_authorization_expired")
            accepted = approve and not failures
            decision = self._new("PreparationExecutionDecision", principal, request["execution_scope"], now,
                request_reference=request_ref, decision="approved" if accepted else "denied", authorization_evidence=proof,
                rationale=rationale, reasons=sorted(set(failures)), decided_at=now.isoformat(), affected_authorization_reference=None)
            if not accepted:
                docs, result = self._terminal(request, old, principal, now, "rejected", failures)
                return [decision]+docs, {**result, "authorization_reference": None, "decision_reference": reference(decision)}
            approvals = []
            deadlines = [instant(expires_at), instant(proof["verification_valid_until"])]
            for ref in candidates:
                a = self.get(ref)
                status = self.specs._approval_status(a, now) if a["contract_type"] == "SpecificationApprovalRecord" else self.service._approval_state(a, now)
                if status not in ("approved", "usable"): continue
                approvals.append(ref)
                deadlines += [instant(a[k]) for k in ("expires_at", "review_due_at") if a.get(k)]
            authorization = self._new("PreparationExecutionAuthorization", principal, request["execution_scope"], now,
                request_reference=request_ref, decision_reference=reference(decision), plan_reference=request["plan_reference"], plan_digest=request["plan_digest"],
                source_references=request["source_references"], approval_references=approvals, worker_principal_reference=request["worker_principal_reference"],
                expires_at=min(deadlines).isoformat(), provider_versions=self._versions(), source_verification=verified,
                validator_versions=self.specs.operations.versions(), reconciler_versions=self.reconciliation.versions())
            state = self._next(request, principal, now, "authorized", old, authorization_reference=reference(authorization))
            return [decision, authorization, state], {"state_reference": reference(state), "authorization_reference": reference(authorization), "decision_reference": reference(decision)}
        return self._command("authorize_preparation_execution", context, command_id, expected_head, payload, build)

    def _worker(self, request, context, action, principal, now):
        self._authorize(context, action, reference(request), request["execution_scope"], principal, now)
        if principal != request["worker_principal_reference"]:
            raise GovernanceError("wrong_execution_worker", "Only the authenticated worker pinned by explicit authorization may advance execution.")

    def begin(self, request_ref, *, context, command_id, expected_head):
        def build(principal, context_ref, now):
            request, old = self.get(request_ref), self.state(request_ref)
            self._worker(request, context, "begin_preparation_execution", principal, now)
            if old["status"] != "authorized": raise GovernanceError("execution_not_startable", "Starting requires unconsumed explicit execution authorization.")
            auth = self.get(old["authorization_reference"])
            failures, _, _ = self._current(request, now, auth)
            now = self.service._now()
            self._worker(request, context, "begin_preparation_execution", principal, now)
            if failures: return self._terminal(request, old, principal, now, "failed", failures)
            state = self._next(request, principal, now, "running", old, started_at=now.isoformat(),
                lease_expires_at=min(now+timedelta(seconds=request["lease_seconds"]), instant(auth["expires_at"])).isoformat(), fence_token=str(uuid4()))
            return [state], {"state_reference": reference(state)}
        result = self._command("begin_preparation_execution", context, command_id, expected_head, {"request": request_ref}, build)
        return self.get(result["state_reference"])

    def _running(self, request, old, now):
        if old["status"] != "running": raise GovernanceError("execution_not_running", "Terminal or unstarted work cannot report successful outputs.")
        failures, _, _ = self._current(request, now, self.get(old["authorization_reference"]))
        now = self.service._now()
        if now >= instant(old["lease_expires_at"]): failures.append("execution_lease_expired")
        return failures

    def _artifact(self, descriptor, request, principal, now):
        if not isinstance(descriptor, dict) or set(descriptor) != set(artifact_fields()):
            raise GovernanceError("invalid_artifact_evidence", "Artifacts require a complete measured descriptor; no counts are fabricated.")
        if instant(descriptor["measured_at"]) > now: raise GovernanceError("invalid_artifact_timestamp", "Artifact evidence cannot be from the future.")
        if not descriptor["source_references"] or not {field_key(f) for f in descriptor["source_references"]} <= {field_key(f) for f in request["source_references"]}:
            raise GovernanceError("artifact_source_mismatch", "Artifact lineage is outside the authorized source manifest.")
        for field in request["source_references"]:
            if descriptor["locator"] == self.runtime.catalogue.get(field["source_metadata_reference"])["resource_locator"]:
                raise GovernanceError("protected_source_destination", "Original source resources cannot be used as derived output artifacts.")
        document = self._new("PreparationArtifact", principal, request["execution_scope"], now,
            request_reference=reference(request), provider_reference=self.evidence.provider_id+"@"+self.evidence.version, **descriptor)
        self.runtime.catalogue.registry.validate(document, resolver=self.runtime.catalogue.resolve)
        return document

    def _inputs(self, request, old, artifacts):
        if old["operation_receipts"]:
            expected = [self.get(r) for r in old["output_artifacts"] if self.get(r)["role"] == "accepted"]
            return {a["locator"]: a["content_digest"] for a in artifacts} == {a["locator"]: a["content_digest"] for a in expected}
        groups = {}
        for f in request["source_references"]: groups.setdefault((digest(f["discovery_reference"]), f["table_id"]), []).append(f)
        covered = set()
        for a in artifacts:
            fields = a["source_references"]
            if not fields: return False
            key = (digest(fields[0]["discovery_reference"]), fields[0]["table_id"])
            if key not in groups or key in covered or {field_key(f) for f in fields} != {field_key(f) for f in groups[key]}: return False
            covered.add(key)
            discovery = self.runtime.catalogue.get(fields[0]["discovery_reference"])
            table = next(t for t in discovery["tables"] if t["table_id"] == key[1])
            schema = [{"field_id": f["field_id"], "types": sorted(next(x for x in table["fields"] if x["field_id"] == f["field_id"])["observed"]["type_counts"])} for f in groups[key]]
            if a["row_count"] != table["observed_row_count"] or a["schema"] != schema: return False
        return covered == set(groups)

    def record_operation(self, request_ref, *, operation_id, evidence_handle, context, command_id, expected_head):
        payload = {"request": request_ref, "operation_id": operation_id, "evidence_handle": evidence_handle}
        def build(principal, context_ref, now):
            request, old = self.get(request_ref), self.state(request_ref)
            self._worker(request, context, "record_preparation_operation", principal, now)
            failures = self._running(request, old, now)
            if failures: return self._terminal(request, old, principal, now, "failed", failures)
            plan, auth = self.get(request["plan_reference"]), self.get(old["authorization_reference"])
            index = len(old["operation_receipts"])
            if index >= len(plan["operations"]) or plan["operations"][index]["operation_id"] != operation_id:
                raise GovernanceError("unexpected_operation", "Only the next exact approved operation may be checkpointed once.")
            operation = plan["operations"][index]
            try:
                result = clone(self.evidence.inspect_operation(request, auth, old, operation, evidence_handle))
                now = self.service._now()
                required = {"request_reference", "authorization_reference", "fence_token", "operation_digest", "started_at", "completed_at", "complete",
                            "accepted_count", "rejected_count", "input_artifacts", "output_artifacts", "evidence_reference"}
                if set(result) != required or result["request_reference"] != request_ref or result["authorization_reference"] != reference(auth) or result["fence_token"] != old["fence_token"] or result["operation_digest"] != digest(operation):
                    raise GovernanceError("operation_evidence_mismatch", "Worker evidence does not match exact execution, authorization, operation and fence.")
                if type(result["complete"]) is not bool or any(value is not None and (type(value) is not int or value < 0) for value in (result["accepted_count"], result["rejected_count"])):
                    raise GovernanceError("invalid_operation_statistics", "Completion and nullable observed counts require exact types; missing counts are not zeros.")
                if result["complete"] and (result["completed_at"] is None or not result["output_artifacts"]):
                    raise GovernanceError("incomplete_operation_evidence", "A completion claim without finished measurable output is invalid.")
                if instant(result["started_at"]) < instant(old["started_at"]) or result["completed_at"] and (instant(result["completed_at"]) < instant(result["started_at"]) or instant(result["completed_at"]) > now):
                    raise GovernanceError("operation_time_mismatch", "Operation evidence is outside this execution's observed time boundaries.")
                inputs = [self._artifact(a, request, principal, now) for a in result["input_artifacts"]]
                outputs = [self._artifact(a, request, principal, now) for a in result["output_artifacts"]]
                # Inspect every locator again; reporting a digest is not proof.
                for a in inputs+outputs:
                    current = self.evidence.inspect_artifact(request_ref, a)
                    if any(current[k] != a[k] for k in artifact_fields() if k not in ("measured_at", "evidence_reference")):
                        raise GovernanceError("artifact_integrity_mismatch", "Artifact content, statistics, scope or completeness changed.")
            except FrameworkError as exc: return self._terminal(request, old, principal, now, "failed", [exc.code])
            except Exception: return self._terminal(request, old, principal, now, "failed", ["operation_evidence_unavailable"])
            now = self.service._now()
            current_failures = self._running(request, old, now)
            now = self.service._now()
            self._worker(request, context, "record_preparation_operation", principal, now)
            checks = [check("operation_complete", result["complete"] is True and result["completed_at"] is not None, "Completion must be observed; absence is not success."),
                check("current_authorization_after_evidence", not current_failures, "Verification completion must remain within the exact current authorization and lease."),
                check("artifacts_complete", bool(inputs) and bool(outputs) and all(a["complete"] for a in inputs+outputs), "All input/output artifacts must be sealed and complete."),
                check("input_lineage", self._inputs(request, old, inputs), "Inputs must match the pinned source population or preceding accepted artifact digests."),
                check("source_lineage_preserved", {field_key(f) for a in inputs for f in a["source_references"]} == {field_key(f) for a in outputs for f in a["source_references"]},
                      "Output lineage must retain all contributing exact source/schema field references."),
                check("artifact_roles", all(a["role"] == "input" for a in inputs) and all(a["role"] in ("accepted", "rejected") for a in outputs), "Input and accepted/rejected roles are explicit."),
                check("distinct_artifacts", len({a["locator"] for a in inputs+outputs}) == len(inputs+outputs), "Output artifacts cannot overwrite inputs or duplicate another output locator.")]
            strategy = self.reconciliation.select(operation)
            try: checks += strategy.validate(operation, result) if strategy else [check("supported_reconciliation", None, "No unique reconciler supports the operation.")]
            except Exception: checks.append(check("reconciliation_available", None, "The configured reconciler could not verify observed results."))
            codes = sorted(set(current_failures + [c["check"] for c in checks if c["status"] != "passed"]))
            reconciliation = self._new("PreparationReconciliationResult", principal, request["execution_scope"], now, request_reference=request_ref,
                operation_id=operation_id, checks=checks, status="failed" if codes else "passed", failure_codes=codes,
                method_reference=strategy.strategy_id+"@"+strategy.version if strategy else "unavailable", assessed_at=now.isoformat())
            receipt = self._new("PreparationOperationReceipt", principal, request["execution_scope"], now, request_reference=request_ref,
                authorization_reference=reference(auth), operation_id=operation_id, operation_digest=digest(operation), operation_version=operation["operation_version"],
                evidence_reference=result["evidence_reference"], input_artifacts=[reference(a) for a in inputs], output_artifacts=[reference(a) for a in outputs],
                complete=result["complete"], accepted_count=result["accepted_count"], rejected_count=result["rejected_count"], started_at=result["started_at"],
                completed_at=result["completed_at"], reconciliation_reference=reference(reconciliation))
            # Staged bundle validation also checks nullable/unperformed statistics.
            docs = inputs+outputs+[reconciliation, receipt]
            changes = {"input_artifacts": old["input_artifacts"] or [reference(a) for a in inputs], "output_artifacts": [reference(a) for a in outputs],
                       "operation_receipts": old["operation_receipts"]+[reference(receipt)]}
            if codes:
                terminal, response = self._terminal(request, old, principal, now, "failed", codes, **changes)
                # Newly staged receipt is not yet readable through the journal.
                terminal[-1]["reconciliation_references"].append(reference(reconciliation))
                terminal[-1]["dependency_versions"].append(reference(reconciliation))
                return docs+terminal, response
            state = self._next(request, principal, now, "running", old, **changes)
            return docs+[state], {"state_reference": reference(state)}
        outcome = self._command("record_preparation_operation", context, command_id, expected_head, payload, build)
        return self.get(outcome["state_reference"])

    def finalize(self, request_ref, *, context, command_id, expected_head):
        def build(principal, context_ref, now):
            request, old = self.get(request_ref), self.state(request_ref)
            self._worker(request, context, "finalize_preparation_execution", principal, now)
            failures = self._running(request, old, now)
            plan = self.get(request["plan_reference"])
            receipts = [self.get(r) for r in old["operation_receipts"]]
            checks = [check("execution_complete", bool(receipts) and len(receipts) == len(plan["operations"]), "Every approved operation requires a durable receipt."),
                check("operation_reconciliation", bool(receipts) and all(r["complete"] and self.get(r["reconciliation_reference"])["status"] == "passed" for r in receipts), "Every operation must be complete and reconciled."),
                check("current_authorization", not failures, "Exact pinned approvals, source snapshots, authorization, configuration and lease must remain current.")]
            integrity = True
            try:
                artifacts = {digest(ref): ref for r in receipts for ref in r["input_artifacts"]+r["output_artifacts"]}
                for ref in artifacts.values():
                    a = self.get(ref); current = self.evidence.inspect_artifact(request_ref, a)
                    if any(current[k] != a[k] for k in artifact_fields() if k not in ("measured_at", "evidence_reference")): integrity = False
            except Exception: integrity = False
            checks.append(check("output_integrity", integrity and bool(old["output_artifacts"]), "Artifacts must still match independently measured immutable content and statistics."))
            now = self.service._now()
            final_failures = self._running(request, old, now)
            now = self.service._now()
            self._worker(request, context, "finalize_preparation_execution", principal, now)
            failures += final_failures
            checks.append(check("current_authorization_after_integrity", not final_failures, "A slow integrity check cannot outlive the authorization or execution lease."))
            failures += [c["check"] for c in checks if c["status"] != "passed"]
            reconciliation = self._new("PreparationReconciliationResult", principal, request["execution_scope"], now, request_reference=request_ref,
                operation_id=None, checks=checks, status="failed" if failures else "passed", failure_codes=sorted(set(failures)), method_reference="execution-completeness-v1", assessed_at=now.isoformat())
            docs, result = self._terminal(request, old, principal, now, "failed" if failures else "succeeded", failures,
                reconciliation_reference=reference(reconciliation))
            return [reconciliation]+docs, result
        result = self._command("finalize_preparation_execution", context, command_id, expected_head, {"request": request_ref}, build)
        return self.get(result["state_reference"])

    def interrupt(self, request_ref, *, reason, context, command_id, expected_head):
        def build(principal, context_ref, now):
            request, old = self.get(request_ref), self.state(request_ref)
            self._authorize(context, "recover_preparation_execution", request_ref, request["execution_scope"], principal, now)
            if old["status"] != "running": raise GovernanceError("execution_not_running", "Only active work can be interrupted; history cannot be reopened.")
            if not isinstance(reason, str) or not reason.strip(): raise GovernanceError("interruption_reason_required", "Record an explicit recovery reason.")
            return self._terminal(request, old, principal, now, "interrupted", ["explicit_interruption"], failure_detail=reason)
        result = self._command("interrupt_preparation_execution", context, command_id, expected_head, {"request": request_ref, "reason": reason}, build)
        return self.get(result["state_reference"])

    def revoke(self, authorization_ref, *, rationale, context, command_id, expected_head):
        def build(principal, context_ref, now):
            auth = self.get(authorization_ref); request = self.get(auth["request_reference"]); old = self.state(reference(request))
            proof = self._authorize(context, "revoke_preparation_execution", authorization_ref, request["execution_scope"], principal, now)
            if old["status"] not in ("authorized", "running"): raise GovernanceError("execution_terminal", "Completed execution cannot be rewritten or reopened.")
            decision = self._new("PreparationExecutionDecision", principal, request["execution_scope"], now, request_reference=reference(request),
                decision="revoked", authorization_evidence=proof, rationale=rationale, reasons=["explicit_execution_revocation"], decided_at=now.isoformat(), affected_authorization_reference=authorization_ref)
            docs, result = self._terminal(request, old, principal, now, "revoked", ["explicit_execution_revocation"])
            return [decision]+docs, result
        result = self._command("revoke_preparation_execution", context, command_id, expected_head, {"authorization": authorization_ref, "rationale": rationale}, build)
        return self.get(result["state_reference"])


def payload_keys():
    return ("plan_reference", "plan_digest", "source_references", "worker_principal_reference", "lease_seconds", "purpose")
