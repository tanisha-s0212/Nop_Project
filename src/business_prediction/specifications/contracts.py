"""Additive versioned specifications and immutable review records.

Contract validity is structural consistency, never trusted business approval.
Only journal-issued decisions evaluated at use time establish reviewed status.
"""

from datetime import date

from ..contracts import ContractDefinition, FieldSpec as F, envelope_fields, envelope_check, reference
from ..errors import ValidationIssue
from ..semantics.contracts import (ref, refs, texts, scope_spec, physical_spec, evidence_spec,
                                  validate_scope, validate_field, validate_evidence, CONTRACT_TYPES)
from ..semantics.common import GovernanceError, digest, field_key, scope_contains, instant
from ..assessment.contracts import ASSESSMENT_TYPES

SPECIFICATION_TYPES = ("PredictionTargetSpecification", "ObservationSpecification",
                       "RelationshipSpecification", "DataPreparationPlanSpecification")
RECORD_TYPES = ("SpecificationReviewRequest", "SpecificationReviewDecision",
                "SpecificationApprovalRecord", "PreparationPlanValidation")
SPECIFICATION_CONTRACT_TYPES = SPECIFICATION_TYPES + RECORD_TYPES


def interval_spec():
    return F("object", nullable=True, fields={"start": F("string"), "end": F("string"),
        "calendar_reference": F("string")})


def horizon_spec():
    return F("object", nullable=True, fields={"steps": F("integer", minimum=1), "unit": F("string")})


def clause_spec():
    return F("object", fields={"clause_id": F("string"), "definition": F("string"),
        "binding_references": refs("SemanticBinding")})


def operation_spec():
    text = F("string")
    return F("object", fields={"operation_id": text, "operation_type": text, "operation_version": text,
        "purpose": text, "source_references": F("array", items=physical_spec()),
        "input_binding_references": refs("SemanticBinding"), "parameters": F("object"),
        "input_grain": text, "output_grain": text, "depends_on": texts(),
        "assumptions": texts(), "evidence_references": F("array", items=evidence_spec()),
        "risks": texts(), "required_approvals": texts(),
        "relationship_references": refs("RelationshipSpecification"),
        "information_role": F("string", choices=("target", "predictor", "identifier", "time", "validation")),
        "availability": F("string", choices=("before_decision", "after_decision", "unknown", "not_applicable"))})


def _checks(doc, resolver):
    issues = envelope_check(doc, resolver)
    try:
        validate_scope(doc["specification_scope"], resolver)
        if doc["purpose_scope"] != doc["specification_scope"]["purpose"]:
            raise GovernanceError("scope_mismatch", "Specification purpose differs from its exact review scope.")
        allowed = {field_key(f) for f in doc["specification_scope"]["field_references"]}
        for item in doc["evidence_references"]:
            validate_evidence(item, resolver)
        kind = doc["contract_type"]
        if kind in SPECIFICATION_TYPES:
            prior = doc["predecessor_reference"]
            if prior:
                old = resolver(prior)
                if old["contract_type"] != kind or old["object_id"] != doc["object_id"] or old["object_revision"]+1 != doc["object_revision"]:
                    raise GovernanceError("wrong_version", "Specifications require an exact immediate predecessor of the same type/identity.")
            elif doc["object_revision"] != 1:
                raise GovernanceError("wrong_version", "An initial specification revision must be one.")
            if not doc["required_approvals"] or len(set(doc["required_approvals"])) != len(doc["required_approvals"]):
                raise GovernanceError("approval_requirements_missing", "Declare distinct business approval requirements; none are granted by a proposal.")
        fields = []
        bindings = []
        if kind == "PredictionTargetSpecification":
            fields.append(doc["physical_field_reference"])
            bindings.append(doc["semantic_binding_reference"])
            if resolver(doc["semantic_binding_reference"])["physical_field_reference"] != doc["physical_field_reference"]:
                raise GovernanceError("field_context_mismatch", "Target must pin its semantic binding's exact physical snapshot.")
            for clauses in (doc["eligibility"], doc["inclusion_criteria"], doc["exclusion_criteria"]):
                bindings += [r for c in clauses for r in c["binding_references"]]
            if doc["construction_requirements"]:
                bindings += doc["construction_requirements"]["input_binding_references"]
        elif kind == "ObservationSpecification":
            bindings += doc["entity_binding_references"] + ([doc["time_binding_reference"]] if doc["time_binding_reference"] else [])
            bindings += [r for c in doc["eligibility"] for r in c["binding_references"]]
        elif kind == "RelationshipSpecification":
            bindings += doc["left_key_bindings"] + doc["right_key_bindings"]
            if not doc["left_key_bindings"] or len(doc["left_key_bindings"]) != len(doc["right_key_bindings"]):
                raise GovernanceError("invalid_relationship", "Relationship sides need nonempty aligned key tuples; uniqueness is not inferred.")
        elif kind == "DataPreparationPlanSpecification":
            fields += doc["source_references"]
            for op in doc["operations"]:
                fields += op["source_references"]
                bindings += op["input_binding_references"]
                for e in op["evidence_references"]:
                    validate_evidence(e, resolver)
        for r in bindings:
            fields.append(resolver(r)["physical_field_reference"])
        for field in fields:
            validate_field(field, resolver)
            if field_key(field) not in allowed:
                raise GovernanceError("scope_mismatch", "A specification dependency is outside its exact authorized field context.")
        for key in ("historical_boundaries", "observation_period", "future_boundaries"):
            value = doc.get(key)
            if value and date.fromisoformat(value["start"]) >= date.fromisoformat(value["end"]):
                raise GovernanceError("invalid_interval", "Calendar boundaries are half-open and must have increasing ISO dates.")
        if kind == "SpecificationReviewRequest":
            subject = resolver(doc["subject_reference"])
            if digest(subject) != doc["subject_digest"] or subject["specification_scope"] != doc["specification_scope"]:
                raise GovernanceError("wrong_version", "Review must freeze the exact specification version, digest and scope.")
            if doc["approval_requirements"] != subject["required_approvals"]:
                raise GovernanceError("wrong_version", "Review must preserve all subject approval requirements.")
            if doc["evidence_references"] != subject["evidence_references"]:
                raise GovernanceError("wrong_version", "Review evidence must freeze the subject's exact evidence basis.")
            if instant(doc["expires_at"]) <= instant(doc["created_at"]) or instant(doc["review_due_at"]) <= instant(doc["created_at"]):
                raise GovernanceError("invalid_timestamp", "Review terms must define future expiry and review deadlines.")
        elif kind == "SpecificationReviewDecision":
            request = resolver(doc["review_request_reference"])
            proof = doc["authorization"]
            if (request["subject_reference"] != doc["subject_reference"] or request["subject_digest"] != doc["subject_digest"] or
                    request["specification_scope"] != doc["specification_scope"]):
                raise GovernanceError("wrong_version", "Decision must concern the exact frozen specification revision.")
            reviewing = doc["action"] in ("approve", "reject", "request_clarification")
            action = doc["action"] + ("_specification" if reviewing else "_specification_approval")
            subject = doc["subject_reference"] if reviewing else doc["affected_approval_reference"]
            if (proof.get("verification_outcome") != "verified" or proof.get("requested_action") != action or
                    proof.get("subject_reference") != subject or proof.get("scope") != doc["specification_scope"] or
                    proof.get("principal_reference") != doc["owner_reference"] or
                    not instant(proof["verified_at"]) <= instant(doc["decided_at"]) < instant(proof["verification_valid_until"])):
                raise GovernanceError("authority_denied", "Decision needs a matching exact-object, scope, action and principal authority receipt.")
            retirement = doc["action"] in ("revoke", "supersede")
            if retirement != (doc["affected_approval_reference"] is not None) or (doc["action"] == "supersede") != (doc["replacement_approval_reference"] is not None):
                raise GovernanceError("invalid_action", "Retirement decisions require exact affected/replacement approval references.")
        elif kind == "SpecificationApprovalRecord":
            request = resolver(doc["review_request_reference"])
            subject = resolver(doc["approved_object_reference"])
            if (request["subject_reference"] != reference(subject) or request["subject_digest"] != digest(subject) or
                    doc["approved_object_digest"] != digest(subject) or doc["specification_scope"] != subject["specification_scope"] or
                    doc["approval_requirements"] != subject["required_approvals"] or
                    any(doc[k] != request[k] for k in ("expires_at", "review_due_at", "conditions", "limitations"))):
                raise GovernanceError("wrong_version", "Approval must preserve exact object, scope, requirements and frozen review terms.")
            decisions = [resolver(r) for r in doc["decision_references"]]
            if not decisions or any(d["action"] != "approve" or d["review_request_reference"] != doc["review_request_reference"] for d in decisions):
                raise GovernanceError("authority_denied", "Approval requires explicit decisions on its review request.")
            principals = [d["owner_reference"] for d in decisions]
            if principals != doc["approver_references"] or len(set(principals)) != len(principals):
                raise GovernanceError("authority_denied", "Approval requires distinct identified reviewers.")
        elif kind == "PreparationPlanValidation":
            if (doc["valid_specification"] != (not doc["findings"]) or
                    doc["status"] != ("valid_specification" if doc["valid_specification"] else "blocked") or
                    resolver(doc["plan_reference"])["specification_scope"] != doc["specification_scope"]):
                raise GovernanceError("inconsistent_validation", "A valid specification cannot contain unresolved findings.")
        for key in ("expires_at", "review_due_at", "decided_at", "assessed_at", "valid_until"):
            if doc.get(key) is not None:
                instant(doc[key])
    except (GovernanceError, ValueError) as exc:
        issues.append(ValidationIssue("$", getattr(exc, "code", "invalid_interval"), str(exc)))
    return issues


def register_specification_contracts(registry):
    text, nullable = F("string"), F("string", nullable=True)
    ev = F("array", items=evidence_spec())
    clauses = F("array", items=clause_spec())
    definitions = {
        "PredictionTargetSpecification": {
            "requirement_reference": ref("PredictionRequirementSpecification", nullable=True),
            "business_meaning": text, "semantic_binding_reference": ref("SemanticBinding"),
            "physical_field_reference": physical_spec(), "target_grain": text,
            "value_type": text, "value_characteristics": F("object"), "eligibility": clauses,
            "inclusion_criteria": clauses, "exclusion_criteria": clauses,
            "historical_boundaries": interval_spec(), "history_not_applicable_reason": nullable, "prediction_horizon": horizon_spec(),
            "construction_requirements": F("object", nullable=True, fields={"definition": text,
                "method_reference": text, "input_binding_references": refs("SemanticBinding")})},
        "ObservationSpecification": {"target_reference": ref("PredictionTargetSpecification"),
            "observation_grain": text, "entity_binding_references": refs("SemanticBinding"),
            "time_binding_reference": ref("SemanticBinding", nullable=True), "time_basis": nullable, "time_not_applicable_reason": nullable,
            "observation_period": interval_spec(), "eligibility": clauses, "expected_frequency": nullable,
            "alignment": F("object", fields={"mode": F("string", choices=("native", "construction_required")), "definition": text}),
            "historical_boundaries": interval_spec(), "future_boundaries": interval_spec(),
            "relationship_references": refs("RelationshipSpecification")},
        "RelationshipSpecification": {"left_key_bindings": refs("SemanticBinding"), "right_key_bindings": refs("SemanticBinding"),
            "left_grain": text, "right_grain": text, "result_grain": text,
            "cardinality": F("string", choices=("one_to_one", "many_to_one", "one_to_many", "many_to_many", "unknown")),
            "null_key_policy": text, "unmatched_policy": text, "expansion_policy": text,
            "reconciliation_checks": texts(), "evidence_definition": text},
        "DataPreparationPlanSpecification": {"target_reference": ref("PredictionTargetSpecification"),
            "observation_reference": ref("ObservationSpecification"), "source_references": F("array", items=physical_spec()),
            "input_grain": text, "output_grain": text, "operations": F("array", items=operation_spec()),
            "relationship_references": refs("RelationshipSpecification"), "quality_checks": texts(),
            "leakage_controls": texts(), "unresolved_decisions": texts()},
        "SpecificationReviewRequest": {"subject_reference": ref(*SPECIFICATION_TYPES), "subject_digest": text,
            "approval_requirements": texts(), "expires_at": text, "review_due_at": text,
            "conditions": texts(), "limitations": texts(), "policy_reference": F("object")},
        "SpecificationReviewDecision": {"review_request_reference": ref("SpecificationReviewRequest"),
            "subject_reference": ref(*SPECIFICATION_TYPES), "subject_digest": text,
            "action": F("string", choices=("approve", "reject", "request_clarification", "revoke", "supersede")),
            "authorization": F("object"), "rationale": text, "decided_at": text,
            "affected_approval_reference": ref("SpecificationApprovalRecord", nullable=True),
            "replacement_approval_reference": ref("SpecificationApprovalRecord", nullable=True)},
        "SpecificationApprovalRecord": {"approved_object_reference": ref(*SPECIFICATION_TYPES), "approved_object_digest": text,
            "review_request_reference": ref("SpecificationReviewRequest"), "decision_references": refs("SpecificationReviewDecision"),
            "approver_references": texts(), "approval_requirements": texts(), "expires_at": text, "review_due_at": text,
            "conditions": texts(), "limitations": texts(), "execution_authorized": F("boolean", choices=(False,))},
        "PreparationPlanValidation": {"plan_reference": ref("DataPreparationPlanSpecification"),
            "valid_specification": F("boolean"), "status": F("string", choices=("valid_specification", "blocked")),
            "findings": F("array", items=F("object", fields={"code": text,
                "category": F("string", choices=("specification", "approval", "evidence", "unsupported", "leakage")),
                "message": text, "subject_reference": ref(*SPECIFICATION_CONTRACT_TYPES, "SemanticBinding", nullable=True),
                "operation_id": nullable})), "approval_references": refs("SpecificationApprovalRecord", "ApprovalRecord"),
            "validator_versions": F("array", items=texts()), "assessed_at": text, "valid_until": text,
            "governance_head": F("integer", minimum=0), "execution_authorized": F("boolean", choices=(False,)),
            "limitations": texts()}}
    for kind, body in definitions.items():
        common = {**envelope_fields(), "contract_type": F("string", choices=(kind,)),
            "contract_version": F("string", choices=("1.0",)), "specification_scope": scope_spec(),
            "evidence_references": ev,
            "dependency_versions": refs("DataSourceMetadata", "SchemaDiscoveryResult", *CONTRACT_TYPES, *ASSESSMENT_TYPES, *SPECIFICATION_CONTRACT_TYPES)}
        if kind in SPECIFICATION_TYPES:
            common.update(predecessor_reference=ref(kind, nullable=True), required_approvals=texts(), limitations=texts())
        registry.register(ContractDefinition(kind, "1.0", {**common, **body}, (_checks,)))
    return registry
