"""Additive worker claims and independently authorized publication records."""

from ..contracts import ContractDefinition, FieldSpec as F, envelope_fields, envelope_check, reference
from ..errors import ValidationIssue
from ..semantics.contracts import ref, refs, texts, scope_spec, CONTRACT_TYPES
from ..semantics.common import digest, GovernanceError, instant
from ..assessment.contracts import ASSESSMENT_TYPES
from ..specifications.contracts import SPECIFICATION_CONTRACT_TYPES
from ..execution.contracts import EXECUTION_TYPES

WORKER_TYPES = ("PreparationWorkerAttempt", "PreparationWorkerReceipt", "PreparationPublicationRequest",
                "PreparationPublicationIntent", "PreparationPublicationRecord", "PreparationPublicationRecovery")


def _checks(doc, resolver):
    issues = envelope_check(doc,resolver)
    try:
        request = resolver(doc["request_reference"])
        if request["execution_scope"] != doc["execution_scope"] or doc["purpose_scope"] != request["purpose_scope"]:
            raise GovernanceError("worker_scope_mismatch", "Worker/publication records must preserve the exact execution request context.")
        kind = doc["contract_type"]
        if kind == "PreparationWorkerAttempt":
            state = resolver(doc["state_reference"])
            if (state["request_reference"] != doc["request_reference"] or state["status"] != "running" or
                    state["authorization_reference"] != doc["authorization_reference"] or state["fence_token"] != doc["fence_token"]):
                raise GovernanceError("worker_claim_mismatch", "Attempt requires the exact active authorization, state and fence.")
            plan = resolver(request["plan_reference"])
            if doc["plan_reference"] != reference(plan) or not any(op["operation_id"] == doc["operation_id"] and digest(op) == doc["operation_digest"] for op in plan["operations"]):
                raise GovernanceError("worker_operation_mismatch", "Worker claim cannot substitute an operation or plan version.")
        elif kind == "PreparationWorkerReceipt":
            attempt = resolver(doc["attempt_reference"])
            if attempt["request_reference"] != doc["request_reference"]: raise GovernanceError("worker_receipt_mismatch", "Receipt must belong to its exact attempt.")
            if doc["status"] == "completed" and (doc["failure_codes"] or not doc["manifest_locator"] or not doc["manifest_digest"] or not doc["artifact_locators"]):
                raise GovernanceError("incomplete_worker_receipt", "Completed worker receipts require immutable measured artifact evidence.")
            if doc["status"] == "failed" and not doc["failure_codes"]:
                raise GovernanceError("incomplete_worker_failure", "A failed receipt must retain a structured reason.")
            if instant(doc["completed_at"]) < instant(attempt["started_at"]):
                raise GovernanceError("worker_time_mismatch", "A worker receipt cannot finish before its attempt starts.")
        elif kind == "PreparationPublicationRequest":
            state = resolver(doc["completed_state_reference"]); provenance = resolver(doc["provenance_reference"])
            if (state["request_reference"] != doc["request_reference"] or state["status"] != "succeeded" or
                    provenance["state_reference"] != reference(state) or provenance["status"] != "succeeded"):
                raise GovernanceError("publication_execution_incomplete", "Only an exact successful execution and matching immutable provenance may be proposed for publication.")
        elif kind in ("PreparationPublicationIntent","PreparationPublicationRecord"):
            proposal = resolver(doc["publication_request_reference"])
            if proposal["request_reference"] != doc["request_reference"]: raise GovernanceError("publication_version_mismatch", "Publication request and execution do not agree.")
            if any(resolver(r)["request_reference"] != doc["request_reference"] for r in doc["artifact_references"]):
                raise GovernanceError("publication_artifact_scope", "Publication cannot borrow artifacts from another execution.")
            proof = doc["authorization_evidence"]
            if (proof.get("requested_action") != "publish_preparation_artifacts" or proof.get("subject_reference") != reference(proposal) or
                    proof.get("scope") != doc["execution_scope"] or proof.get("principal_reference") != doc["owner_reference"] or proof.get("verification_outcome") != "verified"):
                raise GovernanceError("publication_authority_denied", "Publication requires its own exact-scope, authenticated authorization.")
            if not instant(proof["verified_at"]) <= instant(doc["created_at"]) < instant(proof["verification_valid_until"]):
                raise GovernanceError("publication_authority_expired", "Publication issuance must be within its authorization receipt interval.")
            if kind == "PreparationPublicationRecord":
                intent = resolver(doc["intent_reference"])
                if intent["publication_request_reference"] != reference(proposal) or doc["artifact_references"] != intent["artifact_references"] or doc["store_reference"] != intent["store_reference"]:
                    raise GovernanceError("publication_version_mismatch", "A published version must preserve its immutable promotion intent.")
                if not doc["checks"] or any(c["status"] != "passed" for c in doc["checks"]):
                    raise GovernanceError("publication_reconciliation_failed", "Incomplete publication verification cannot create a published record.")
                if doc["manifest"]["version_id"] != intent["object_id"]:
                    raise GovernanceError("publication_version_mismatch", "Published object versions must identify the exact immutable intent.")
        for key in ("started_at","completed_at","deadline","published_at","recorded_at"):
            if doc.get(key): instant(doc[key])
    except GovernanceError as exc: issues.append(ValidationIssue("$",exc.code,exc.message))
    return issues


def register_worker_contracts(registry):
    text,nullable = F("string"),F("string",nullable=True)
    checks = F("array",items=F("object",fields={"check":text,"status":F("string",choices=("passed","failed","unavailable")),"evidence":text}))
    definitions = {
        "PreparationWorkerAttempt": {"state_reference": ref("PreparationExecutionState"), "authorization_reference": ref("PreparationExecutionAuthorization"),
            "plan_reference": ref("DataPreparationPlanSpecification"), "operation_id": text, "operation_digest": text,
            "implementation_reference": text, "operator_versions": F("array",items=texts()), "fence_token": text,
            "deadline": text, "started_at": text, "limits": F("object",fields={"max_rows":F("integer",minimum=1),"max_bytes":F("integer",minimum=1)})},
        "PreparationWorkerReceipt": {"attempt_reference": ref("PreparationWorkerAttempt"), "status":F("string",choices=("completed","failed")),
            "manifest_locator":nullable,"manifest_digest":nullable,"artifact_locators":texts(),"failure_codes":texts(),"completed_at":text},
        "PreparationPublicationRequest": {"publication_key":text,"completed_state_reference":ref("PreparationExecutionState"),"provenance_reference":ref("PreparationProvenanceRecord")},
        "PreparationPublicationIntent": {"publication_request_reference":ref("PreparationPublicationRequest"),"artifact_references":refs("PreparationArtifact"),
            "store_reference":text,"authorization_evidence":F("object"),"checks":checks},
        "PreparationPublicationRecord": {"publication_request_reference":ref("PreparationPublicationRequest"),"intent_reference":ref("PreparationPublicationIntent"),
            "artifact_references":refs("PreparationArtifact"),"store_reference":text,"authorization_evidence":F("object"),
            "manifest":F("object",fields={"locator":text,"content_digest":text,"store_id":text,"version_id":text}),
            "checks":checks,"published_at":text},
        "PreparationPublicationRecovery": {"publication_request_reference":ref("PreparationPublicationRequest"),"intent_reference":ref("PreparationPublicationIntent",nullable=True),
            "failure_codes":texts(),"known_locators":texts(),"recorded_at":text,"reason":text}}
    for kind,body in definitions.items():
        registry.register(ContractDefinition(kind,"1.0",{**envelope_fields(),"contract_type":F("string",choices=(kind,)),
            "contract_version":F("string",choices=("1.0",)),"request_reference":ref("PreparationExecutionRequest"),"execution_scope":scope_spec(),
            "dependency_versions":refs("DataSourceMetadata","SchemaDiscoveryResult",*CONTRACT_TYPES,*ASSESSMENT_TYPES,*SPECIFICATION_CONTRACT_TYPES,*EXECUTION_TYPES,*WORKER_TYPES),**body},(_checks,)))
    return registry
