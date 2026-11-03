"""Additive assessment contracts; existing business/semantic contracts stay intact."""

from datetime import date

from ..contracts import ContractDefinition, FieldSpec as F, REFERENCE_FIELDS, envelope_fields, envelope_check, reference
from ..errors import ValidationIssue
from ..semantics.contracts import (ref, refs, texts, physical_spec, scope_spec, evidence_spec,
                                  validate_scope, validate_field, CONTRACT_TYPES as SEMANTIC_TYPES)
from ..semantics.common import GovernanceError, field_key, scope_contains, instant

ASSESSMENT_TYPES = ("PredictionRequirementSpecification", "PredictionDataEvidence", "TargetAssessment", "FeasibilityReadinessAssessment")
STATUSES = ("ready_for_preparation_review", "analytics_only", "clarification_required", "approval_blocked", "insufficient_evidence", "unsupported")


def optional(kind, **kwargs):
    return F(kind, required=False, nullable=True, uncertain=True, **kwargs)


def _check(doc, resolver):
    issues = envelope_check(doc, resolver)
    try:
        validate_scope(doc["assessment_scope"], resolver)
        if doc["assessment_scope"]["purpose"] != doc["purpose_scope"]:
            raise GovernanceError("scope_mismatch", "Assessment purpose must match its authorized scope.")
        for dependency in doc["dependency_versions"]:
            if resolver(dependency) is None:
                raise GovernanceError("unresolved_reference", "An exact assessment dependency is missing.")
        kind = doc["contract_type"]
        if kind == "PredictionRequirementSpecification":
            constraints = doc.get("constraints")
            if isinstance(constraints, dict) and "$state" not in constraints:
                fraction = constraints.get("maximum_target_missing_fraction")
                if fraction is not None and (type(fraction) not in (int, float) or not 0 <= fraction <= 1):
                    raise GovernanceError("invalid_constraint", "Missingness tolerance must be a fraction between zero and one.")
                dependencies = constraints.get("external_dependencies", [])
                identifiers = constraints.get("required_identifier_bindings", [])
                if not isinstance(dependencies, list) or not isinstance(identifiers, list):
                    raise GovernanceError("invalid_constraint", "Dependency/identifier constraints must be arrays.")
                for item in dependencies:
                    if (not isinstance(item, dict) or set(item) != {"description", "evidence_reference"} or
                            not isinstance(item["description"], str) or not item["description"].strip()):
                        raise GovernanceError("invalid_constraint", "External dependencies require description and exact evidence reference or null.")
                    if item["evidence_reference"] is not None:
                        resolved = resolver(item["evidence_reference"])
                        if resolved is None or resolved["contract_type"] != "SupportingEvidenceRecord":
                            raise GovernanceError("unresolved_reference", "External dependency evidence must resolve to a supporting-evidence revision.")
                for item in identifiers:
                    resolved = resolver(item)
                    if resolved is None or resolved["contract_type"] != "SemanticBinding" or field_key(resolved["physical_field_reference"]) not in {field_key(f) for f in doc["assessment_scope"]["field_references"]}:
                        raise GovernanceError("scope_mismatch", "Required identifier bindings must resolve inside the authorized scope.")
            previous = doc["predecessor_reference"]
            if previous:
                old = resolver(previous)
                if old["object_id"] != doc["object_id"] or old["object_revision"]+1 != doc["object_revision"]:
                    raise GovernanceError("wrong_version", "Requirement revisions require their exact immediate predecessor.")
            elif doc["object_revision"] != 1:
                raise GovernanceError("wrong_version", "Initial requirement revision must be one.")
            for key in ("target_binding_reference", "time_binding_reference"):
                value = doc.get(key)
                if value is not None and not (isinstance(value, dict) and "$state" in value):
                    binding = resolver(value)
                    if field_key(binding["physical_field_reference"]) not in {field_key(f) for f in doc["assessment_scope"]["field_references"]}:
                        raise GovernanceError("scope_mismatch", "Requirement refers to a field outside the assessment scope.")
            inputs = doc.get("input_binding_references")
            if isinstance(inputs, list):
                for value in inputs:
                    if field_key(resolver(value)["physical_field_reference"]) not in {field_key(f) for f in doc["assessment_scope"]["field_references"]}:
                        raise GovernanceError("scope_mismatch", "Input binding lies outside the assessment scope.")
        if kind == "PredictionDataEvidence":
            field = validate_field(doc["physical_field_reference"], resolver)
            binding = resolver(doc["binding_reference"])
            if binding["physical_field_reference"] != doc["physical_field_reference"]:
                raise GovernanceError("field_context_mismatch", "Data evidence must pin the binding's exact physical snapshot.")
            allowed = {field_key(f) for f in doc["assessment_scope"]["field_references"]}
            dependencies = [doc["binding_reference"]] + doc["input_binding_references"] + ([doc["time_binding_reference"]] if doc["time_binding_reference"] else [])
            if any(field_key(resolver(r)["physical_field_reference"]) not in allowed for r in dependencies):
                raise GovernanceError("scope_mismatch", "Evidence target/time/input bindings must all be within its authorized field scope.")
            discovery = resolver(doc["physical_field_reference"]["discovery_reference"])
            table = next(t for t in discovery["tables"] if t["table_id"] == doc["physical_field_reference"]["table_id"])
            if (not table["profile_complete"] or doc["observation_count"] != table["scanned_row_count"] or
                    doc["nonmissing_count"] != field["observed"]["nonmissing_count"] or doc["mature_observations"] > doc["nonmissing_count"]):
                raise GovernanceError("inconsistent_evidence", "Evidence population/counts must agree with the complete discovery profile.")
            classes = doc["class_counts"]
            if classes:
                keys = [(c["value_type"], c["value_repr"]) for c in classes]
                if (len(set(keys)) != len(keys) or sum(c["count"] for c in classes) != doc["nonmissing_count"] or
                        len(classes) != field["observed"]["distinct_nonmissing_count"] or
                        any(c["value_type"] not in field["observed"]["type_counts"] for c in classes)):
                    raise GovernanceError("inconsistent_evidence", "Class counts must agree with the observed population and distinct count.")
            if (doc["history_start"] is None) != (doc["history_end"] is None):
                raise GovernanceError("inconsistent_evidence", "Both historical bounds or neither must be supplied.")
            if doc["history_start"] is not None:
                if date.fromisoformat(doc["history_start"]) > date.fromisoformat(doc["history_end"]):
                    raise GovernanceError("inconsistent_evidence", "Historical interval is reversed.")
            proof = doc["authorization"]
            if (proof.get("verification_outcome") != "verified" or proof.get("subject_reference") != reference(doc) or
                    proof.get("requested_action") != "register_prediction_evidence" or proof.get("scope") != doc["assessment_scope"] or
                    proof.get("principal_reference") != doc["owner_reference"]):
                raise GovernanceError("authority_denied", "Data evidence requires matching scoped authority attribution.")
            instant(doc["valid_until"])
        if kind in ("TargetAssessment", "FeasibilityReadinessAssessment"):
            requirement = resolver(doc["requirement_reference"])
            if requirement["assessment_scope"] != doc["assessment_scope"]:
                raise GovernanceError("scope_mismatch", "Assessment must preserve the exact requirement scope.")
        if kind == "FeasibilityReadinessAssessment":
            target = resolver(doc["target_assessment_reference"])
            if target["requirement_reference"] != doc["requirement_reference"]:
                raise GovernanceError("wrong_version", "Target and feasibility assessments must concern the same requirement revision.")
            if doc["status"] in ("ready_for_preparation_review", "analytics_only") and doc["blocking_findings"]:
                raise GovernanceError("inconsistent_assessment", "Readiness cannot coexist with unresolved blocking findings.")
    except (GovernanceError, ValueError) as exc:
        issues.append(ValidationIssue("$", getattr(exc, "code", "invalid_evidence"), getattr(exc, "message", "Assessment evidence is inconsistent.")))
    return issues


def register_assessment_contracts(registry):
    text = F("string"); nullable_text = F("string", nullable=True)
    evidence_items = F("array", items=evidence_spec())
    requirement = {
        "predecessor_reference": ref("PredictionRequirementSpecification", nullable=True),
        "business_outcome": optional("string"), "target_description": optional("string"),
        "business_context": optional("string"), "organizational_context": optional("string"),
        "intent": optional("string"), "task_hint": optional("string"),
        "requested_concepts": optional("array", items=text),
        "target_binding_reference": F("object", required=False, nullable=True, uncertain=True,
                                      fields=REFERENCE_FIELDS,
                                      reference_types=("SemanticBinding",)),
        "time_binding_reference": F("object", required=False, nullable=True, uncertain=True,
                                      fields=REFERENCE_FIELDS,
                                      reference_types=("SemanticBinding",)),
        "input_binding_references": optional("array", items=ref("SemanticBinding")),
        "observation_granularity": optional("string"), "decision_time_basis": optional("string"),
        "history_requirements": optional("object", fields={
            "minimum_observations": F("integer", required=False, minimum=1),
            "validation_observations": F("integer", required=False, minimum=1),
            "minimum_per_class": F("integer", required=False, minimum=1)}),
        "prediction_horizon": optional("object", fields={"steps": F("integer", minimum=1), "unit": text}),
        "desired_output": optional("object", fields={"value_kind": text, "unit": F("string", required=False)}),
        "construction_request": optional("object", fields={"description": text, "output_grain": text,
                                                            "dependencies": F("array", items=physical_spec())}),
        "constraints": optional("object"), "additional_context": optional("object")}
    data = {"binding_reference": ref("SemanticBinding"), "physical_field_reference": physical_spec(),
        "time_binding_reference": ref("SemanticBinding", nullable=True), "input_binding_references": refs("SemanticBinding"),
        "observation_grain": text, "observation_frequency": nullable_text,
        "observation_count": F("integer", minimum=0), "nonmissing_count": F("integer", minimum=0),
        "mature_observations": F("integer", minimum=0), "history_start": nullable_text, "history_end": nullable_text,
        "class_counts": F("array", items=F("object", fields={"value_type": text, "value_repr": text, "count": F("integer", minimum=1)})),
        **{key: F("boolean") for key in ("target_observable", "grain_verified", "cadence_complete", "chronology_verified",
            "population_verified", "negative_outcomes_verified", "availability_verified", "validation_verified", "independence_verified")},
        "input_mode": F("string", choices=("history_only", "explicit_inputs")),
        "decision_time_basis": text, "validation_scheme": F("string", choices=("chronological", "grouped_independent")),
        "label_horizon": F("object", nullable=True, fields={"steps": F("integer", minimum=1), "unit": text}),
        "leakage_findings": texts(), "limitations": texts(), "method_reference": text,
        "supporting_evidence_references": refs("SupportingEvidenceRecord"), "valid_until": text, "authorization": F("object")}
    candidate = F("object", fields={"candidate_id": text, "physical_field_reference": physical_spec(),
        "binding_reference": ref("SemanticBinding", nullable=True), "semantic_state": text,
        "approval_references": refs("ApprovalRecord"),
        "relevance_basis": text, "observed_metadata": F("object"), "data_evidence_references": refs("PredictionDataEvidence"),
        "supporting_evidence": evidence_items, "limitations": texts()})
    finding = F("object", fields={"code": text, "category": F("string", choices=("clarification", "approval", "evidence", "unsupported")),
        "message": text, "binding_reference": ref("SemanticBinding", nullable=True)})
    target = {"requirement_reference": ref("PredictionRequirementSpecification"), "problem_type": text,
        "strategy_reference": nullable_text, "candidates": F("array", items=candidate),
        "selected_binding_reference": ref("SemanticBinding", nullable=True),
        "construction_requirements": texts(), "limitations": texts()}
    result = {"requirement_reference": ref("PredictionRequirementSpecification"), "target_assessment_reference": ref("TargetAssessment"),
        "status": F("string", choices=STATUSES), "work_type": F("string", choices=("analytics", "predictive", "unsupported", "undetermined")),
        "blocking_findings": F("array", items=finding), "risks": texts(), "missing_information": texts(),
        "required_approvals": texts(), "clarification_requirements": texts(), "recommended_next_action": text,
        "limitations": texts(), "supporting_evidence_references": refs("PredictionDataEvidence"),
        "execution_authorized": F("boolean", choices=(False,)), "performance_estimated": F("boolean", choices=(False,)),
        "assessed_at": text, "valid_until": text, "governance_head": F("integer", minimum=0)}
    for kind, fields in zip(ASSESSMENT_TYPES, (requirement, data, target, result)):
        registry.register(ContractDefinition(kind, "1.0", {**envelope_fields(),
            "contract_type": F("string", choices=(kind,)), "contract_version": F("string", choices=("1.0",)),
            "assessment_scope": scope_spec(), "dependency_versions": refs("DataSourceMetadata", "SchemaDiscoveryResult", *SEMANTIC_TYPES, *ASSESSMENT_TYPES),
            "evidence_references": evidence_items, **fields}, (_check,)))
    return registry
