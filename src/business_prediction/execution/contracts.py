"""Versioned, journal-issued execution and immutable provenance contracts."""

from ..contracts import ContractDefinition, FieldSpec as F, envelope_fields, envelope_check, reference
from ..errors import ValidationIssue
from ..semantics.contracts import ref, refs, texts, scope_spec, physical_spec, validate_scope, validate_field, CONTRACT_TYPES
from ..semantics.common import GovernanceError, digest, instant, field_key
from ..assessment.contracts import ASSESSMENT_TYPES
from ..specifications.contracts import SPECIFICATION_CONTRACT_TYPES

EXECUTION_TYPES = ("PreparationExecutionRequest", "PreparationExecutionDecision", "PreparationExecutionAuthorization",
    "PreparationExecutionState", "PreparationArtifact", "PreparationOperationReceipt", "PreparationReconciliationResult", "PreparationProvenanceRecord")
STATUSES = ("requested", "authorized", "running", "succeeded", "failed", "interrupted", "rejected", "revoked")
TERMINAL = ("succeeded", "failed", "interrupted", "rejected", "revoked")


def artifact_fields():
    return {"locator": F("string"), "content_digest": F("string"), "size_bytes": F("integer", minimum=0),
        "row_count": F("integer", minimum=0), "duplicate_count": F("integer", minimum=0), "missing_counts": F("object"),
        "schema": F("array", items=F("object", fields={"field_id": F("string"), "types": texts()})),
        "source_references": F("array", items=physical_spec()), "complete": F("boolean"),
        "role": F("string", choices=("input", "accepted", "rejected")), "measured_at": F("string"),
        "evidence_reference": F("string")}


def _checks(doc, resolver):
    issues = envelope_check(doc, resolver)
    try:
        validate_scope(doc["execution_scope"], resolver)
        if doc["purpose_scope"] != doc["execution_scope"]["purpose"]:
            raise GovernanceError("scope_mismatch", "Execution purpose and scope disagree.")
        kind = doc["contract_type"]
        allowed_fields = {field_key(f) for f in doc["execution_scope"]["field_references"]}
        for field in doc.get("source_references", []):
            validate_field(field, resolver)
            if field_key(field) not in allowed_fields:
                raise GovernanceError("scope_mismatch", "Execution lineage is outside its exact authorized physical scope.")
        if kind != "PreparationExecutionRequest":
            request = resolver(doc["request_reference"])
            if request["execution_scope"] != doc["execution_scope"]:
                raise GovernanceError("scope_mismatch", "Execution records must preserve the request's exact scope.")
        if kind == "PreparationExecutionRequest":
            plan = resolver(doc["plan_reference"])
            if plan["specification_scope"] != doc["execution_scope"] or digest(plan) != doc["plan_digest"] or plan["source_references"] != doc["source_references"]:
                raise GovernanceError("wrong_version", "The request must freeze the exact plan, digest, source/schema references and scope.")
            if not 1 <= doc["lease_seconds"] <= 3600:
                raise GovernanceError("invalid_lease", "The bounded prototype lease must be between 1 and 3600 seconds.")
        elif kind == "PreparationExecutionDecision":
            proof = doc["authorization_evidence"]
            action = "revoke_preparation_execution" if doc["decision"] == "revoked" else "authorize_preparation_execution"
            subject = doc["affected_authorization_reference"] if doc["decision"] == "revoked" else doc["request_reference"]
            if (proof.get("requested_action") != action or proof.get("subject_reference") != subject or proof.get("scope") != doc["execution_scope"] or
                    proof.get("principal_reference") != doc["owner_reference"] or proof.get("verification_outcome") != "verified"):
                raise GovernanceError("authority_denied", "Execution decisions need exact action/object/scope authority evidence.")
            if not instant(proof["verified_at"]) <= instant(doc["decided_at"]) < instant(proof["verification_valid_until"]):
                raise GovernanceError("authority_denied", "Execution decisions must fall within the exact authority receipt interval.")
            if (doc["decision"] == "approved") != (not doc["reasons"]):
                raise GovernanceError("inconsistent_decision", "Approval cannot retain blockers; rejection/retirement requires a reason.")
        elif kind == "PreparationExecutionAuthorization":
            decision = resolver(doc["decision_reference"])
            if decision["decision"] != "approved" or decision["request_reference"] != doc["request_reference"]:
                raise GovernanceError("authority_denied", "An execution grant requires a separate explicit approval decision.")
            if (doc["plan_reference"] != request["plan_reference"] or doc["plan_digest"] != request["plan_digest"] or
                    doc["source_references"] != request["source_references"] or doc["worker_principal_reference"] != request["worker_principal_reference"]):
                raise GovernanceError("wrong_version", "Authorization must freeze exact request dependencies and worker identity.")
            if instant(doc["expires_at"]) <= instant(doc["created_at"]):
                raise GovernanceError("invalid_timestamp", "Authorization must have a positive validity interval.")
        elif kind == "PreparationExecutionState":
            if doc["authorization_reference"] and resolver(doc["authorization_reference"])["request_reference"] != doc["request_reference"]:
                raise GovernanceError("wrong_version", "State cannot borrow another execution's authorization.")
            previous = doc["previous_state_reference"]
            if previous:
                old = resolver(previous)
                allowed = {"requested": ("authorized", "rejected"), "authorized": ("running", "failed", "revoked"),
                    "running": ("running", "succeeded", "failed", "interrupted", "revoked")}
                if (old["object_id"] != doc["object_id"] or old["object_revision"]+1 != doc["object_revision"] or
                        old["request_reference"] != doc["request_reference"] or doc["status"] not in allowed.get(old["status"], ())):
                    raise GovernanceError("invalid_execution_transition", "Execution states are sequential, append-only and terminal states cannot be reopened.")
                if old["status"] == "running" and any(old[k] != doc[k] for k in ("authorization_reference", "started_at", "fence_token", "lease_expires_at")):
                    raise GovernanceError("execution_fence_changed", "Checkpoints/terminal states cannot replace a running lease, authorization or fence.")
            elif doc["object_revision"] != 1 or doc["status"] != "requested":
                raise GovernanceError("invalid_execution_transition", "An execution starts with a requested revision, never success.")
            if doc["status"] == "succeeded":
                rec = resolver(doc["reconciliation_reference"]) if doc["reconciliation_reference"] else None
                if (doc["failure_codes"] or not rec or rec["status"] != "passed" or rec["operation_id"] is not None or rec["request_reference"] != doc["request_reference"] or
                        not doc["operation_receipts"] or not doc["output_artifacts"] or doc["started_at"] is None):
                    raise GovernanceError("incomplete_execution", "Success requires completed operation/artifact evidence and passed final reconciliation.")
                plan = resolver(request["plan_reference"])
                receipts = [resolver(r) for r in doc["operation_receipts"]]
                if [r["operation_digest"] for r in receipts] != [digest(op) for op in plan["operations"]] or any(not r["complete"] or resolver(r["reconciliation_reference"])["status"] != "passed" for r in receipts):
                    raise GovernanceError("incomplete_execution", "Success requires the complete ordered operation chain and its passed reconciliations.")
            if doc["status"] in ("authorized", "running", "succeeded", "revoked") and doc["authorization_reference"] is None:
                raise GovernanceError("authority_denied", "Active/completed execution requires a separately issued grant.")
            if doc["status"] == "running" and any(doc[k] is None for k in ("started_at", "fence_token", "lease_expires_at")):
                raise GovernanceError("invalid_execution_transition", "Running state requires an explicit start, fence and bounded lease.")
            for r in doc["operation_receipts"] + doc["input_artifacts"] + doc["output_artifacts"]:
                if resolver(r)["request_reference"] != doc["request_reference"]:
                    raise GovernanceError("wrong_version", "State cannot borrow receipts or artifacts from another execution.")
            if (doc["status"] in TERMINAL) != (doc["finished_at"] is not None):
                raise GovernanceError("invalid_timestamp", "Only terminal states carry a finish timestamp.")
        elif kind == "PreparationArtifact":
            if (len(doc["content_digest"]) != 71 or not doc["content_digest"].startswith("sha256:") or
                    any(c not in "0123456789abcdef" for c in doc["content_digest"][7:])):
                raise GovernanceError("invalid_digest", "Artifacts require a complete SHA-256 content digest.")
            ids = [c["field_id"] for c in doc["schema"]]
            if not ids or len(set(ids)) != len(ids) or set(doc["missing_counts"]) != set(ids):
                raise GovernanceError("invalid_artifact_schema", "Artifact schema and missingness must cover distinct exact fields.")
            if doc["duplicate_count"] > doc["row_count"] or any(type(n) is not int or not 0 <= n <= doc["row_count"] for n in doc["missing_counts"].values()):
                raise GovernanceError("invalid_artifact_counts", "Artifact counts must be measured nonnegative counts within the row population.")
        elif kind == "PreparationOperationReceipt":
            auth = resolver(doc["authorization_reference"])
            if auth["request_reference"] != doc["request_reference"]:
                raise GovernanceError("wrong_version", "Operation evidence must use this exact execution authorization.")
            plan = resolver(request["plan_reference"])
            operation = next((op for op in plan["operations"] if op["operation_id"] == doc["operation_id"]), None)
            reconciliation = resolver(doc["reconciliation_reference"])
            if (operation is None or digest(operation) != doc["operation_digest"] or operation["operation_version"] != doc["operation_version"] or
                    reconciliation["request_reference"] != doc["request_reference"] or reconciliation["operation_id"] != doc["operation_id"]):
                raise GovernanceError("wrong_version", "Receipt must match the exact approved operation and same-run reconciliation.")
            if any(resolver(r)["request_reference"] != doc["request_reference"] for r in doc["input_artifacts"] + doc["output_artifacts"]):
                raise GovernanceError("wrong_version", "Receipt artifacts must belong to this exact execution.")
            if doc["complete"] and (doc["completed_at"] is None or not doc["output_artifacts"]):
                raise GovernanceError("incomplete_execution", "A completed operation needs finished, observable outputs.")
            if doc["completed_at"] and instant(doc["completed_at"]) < instant(doc["started_at"]):
                raise GovernanceError("invalid_timestamp", "Operation timestamps are reversed.")
        elif kind == "PreparationReconciliationResult":
            passed = bool(doc["checks"]) and all(c["status"] == "passed" for c in doc["checks"])
            if (doc["status"] == "passed") != (passed and not doc["failure_codes"]):
                raise GovernanceError("inconsistent_reconciliation", "Unperformed, failed or unavailable checks cannot be recorded as passed.")
        elif kind == "PreparationProvenanceRecord":
            state = resolver(doc["state_reference"])
            if state["request_reference"] != doc["request_reference"] or state["status"] != doc["status"]:
                raise GovernanceError("inconsistent_provenance", "Provenance must preserve its immutable terminal state.")
            if doc["plan_reference"] != request["plan_reference"] or doc["source_references"] != request["source_references"]:
                raise GovernanceError("wrong_version", "Provenance cannot substitute source or plan versions.")
            if (any(doc[k] != state[k] for k in ("authorization_reference", "started_at", "finished_at", "input_artifacts", "output_artifacts", "operation_receipts", "failure_codes", "failure_detail")) or
                    doc["operations"] != resolver(request["plan_reference"])["operations"] or
                    (doc["artifact_disposition"] == "eligible_manifest") != (state["status"] == "succeeded")):
                raise GovernanceError("inconsistent_provenance", "Terminal provenance must preserve the exact state, operations and artifact disposition.")
            expected = [resolver(r)["reconciliation_reference"] for r in state["operation_receipts"]]
            if state["reconciliation_reference"]: expected.append(state["reconciliation_reference"])
            if {digest(r) for r in expected} != {digest(r) for r in doc["reconciliation_references"]}:
                raise GovernanceError("incomplete_provenance", "Provenance must retain every operation and final reconciliation record.")
        for key in ("expires_at", "decided_at", "started_at", "completed_at", "finished_at", "lease_expires_at", "measured_at", "assessed_at"):
            if doc.get(key) is not None: instant(doc[key])
    except GovernanceError as exc:
        issues.append(ValidationIssue("$", exc.code, exc.message))
    return issues


def register_execution_contracts(registry):
    text, nullable = F("string"), F("string", nullable=True)
    physicals = F("array", items=physical_spec())
    request_ref = ref("PreparationExecutionRequest")
    auth_ref = ref("PreparationExecutionAuthorization", nullable=True)
    artifact_refs = refs("PreparationArtifact")
    check = F("object", fields={"check": text, "status": F("string", choices=("passed", "failed", "unavailable")), "evidence": text})
    definitions = {
        "PreparationExecutionRequest": {"request_key": text, "plan_reference": ref("DataPreparationPlanSpecification"),
            "plan_digest": text, "source_references": physicals, "worker_principal_reference": text, "lease_seconds": F("integer", minimum=1), "purpose": text},
        "PreparationExecutionDecision": {"request_reference": request_ref, "decision": F("string", choices=("approved", "denied", "revoked")),
            "authorization_evidence": F("object"), "rationale": text, "reasons": texts(), "decided_at": text,
            "affected_authorization_reference": auth_ref},
        "PreparationExecutionAuthorization": {"request_reference": request_ref, "decision_reference": ref("PreparationExecutionDecision"),
            "plan_reference": ref("DataPreparationPlanSpecification"), "plan_digest": text, "source_references": physicals,
            "approval_references": refs("SpecificationApprovalRecord", "ApprovalRecord"), "worker_principal_reference": text,
            "expires_at": text, "provider_versions": F("array", items=texts()), "source_verification": F("object"),
            "validator_versions": F("array", items=texts()), "reconciler_versions": F("array", items=texts())},
        "PreparationExecutionState": {"request_reference": request_ref, "previous_state_reference": ref("PreparationExecutionState", nullable=True),
            "authorization_reference": auth_ref, "status": F("string", choices=STATUSES), "started_at": nullable, "finished_at": nullable,
            "lease_expires_at": nullable, "fence_token": nullable, "operation_receipts": refs("PreparationOperationReceipt"),
            "input_artifacts": artifact_refs, "output_artifacts": artifact_refs, "failure_codes": texts(), "failure_detail": nullable,
            "reconciliation_reference": ref("PreparationReconciliationResult", nullable=True)},
        "PreparationArtifact": {"request_reference": request_ref, "provider_reference": text, **artifact_fields()},
        "PreparationOperationReceipt": {"request_reference": request_ref, "authorization_reference": ref("PreparationExecutionAuthorization"),
            "operation_id": text, "operation_digest": text, "operation_version": text, "evidence_reference": text,
            "input_artifacts": artifact_refs, "output_artifacts": artifact_refs, "complete": F("boolean"),
            "accepted_count": F("integer", minimum=0, nullable=True), "rejected_count": F("integer", minimum=0, nullable=True),
            "started_at": text, "completed_at": nullable, "reconciliation_reference": ref("PreparationReconciliationResult")},
        "PreparationReconciliationResult": {"request_reference": request_ref, "operation_id": nullable,
            "checks": F("array", items=check), "status": F("string", choices=("passed", "failed", "incomplete")),
            "failure_codes": texts(), "method_reference": text, "assessed_at": text},
        "PreparationProvenanceRecord": {"request_reference": request_ref, "state_reference": ref("PreparationExecutionState"),
            "authorization_reference": auth_ref, "plan_reference": ref("DataPreparationPlanSpecification"), "source_references": physicals,
            "operations": F("array", items=F("object")), "input_artifacts": artifact_refs, "output_artifacts": artifact_refs,
            "operation_receipts": refs("PreparationOperationReceipt"), "reconciliation_references": refs("PreparationReconciliationResult"),
            "status": F("string", choices=TERMINAL), "started_at": nullable, "finished_at": text,
            "failure_codes": texts(), "failure_detail": nullable,
            "artifact_disposition": F("string", choices=("eligible_manifest", "quarantined", "no_registered_output")), "limitations": texts()}}
    for kind, body in definitions.items():
        registry.register(ContractDefinition(kind, "1.0", {**envelope_fields(),
            "contract_type": F("string", choices=(kind,)), "contract_version": F("string", choices=("1.0",)),
            "execution_scope": scope_spec(), "dependency_versions": refs("DataSourceMetadata", "SchemaDiscoveryResult", *CONTRACT_TYPES,
                *ASSESSMENT_TYPES, *SPECIFICATION_CONTRACT_TYPES, *EXECUTION_TYPES), **body}, (_checks,)))
    return registry
