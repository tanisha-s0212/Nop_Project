"""Eight governance contracts extending the existing foundation registry.

Validation proves structure/references, never authenticated approval. Governance
records influence lifecycle only when issued through the service journal.
"""

from datetime import date

from ..contracts import ContractDefinition, FieldSpec as F, REFERENCE_FIELDS, envelope_fields, envelope_check
from ..errors import ValidationIssue
from ..metadata import foundation_registry
from .common import digest, instant, field_key, scope_contains, GovernanceError

CONTRACT_TYPES = ("SemanticBinding", "BusinessReviewRequest", "AuthorityVerificationRecord",
                  "BusinessReviewDecision", "ApprovalRecord", "SupportingEvidenceRecord",
                  "BindingChangeAssessment", "BindingUseAssessment")


def ref(*kinds, nullable=False):
    return F("object", nullable=nullable, fields=REFERENCE_FIELDS, reference_types=tuple(kinds))


def texts():
    return F("array", items=F("string"))


def refs(*kinds):
    return F("array", items=ref(*kinds))


def physical_spec():
    return F("object", fields={"source_metadata_reference": ref("DataSourceMetadata"),
        "discovery_reference": ref("SchemaDiscoveryResult"), "source_version": F("string"),
        "schema_version": F("string"), "table_id": F("string"), "field_id": F("string"),
        "field_position": F("integer", minimum=1)})


def scope_spec():
    return F("object", fields={"purpose": F("string"), "namespace": F("string"),
        "record_grain": F("string"), "assertion_use": F("string", choices=("semantic_interpretation",)),
        "field_references": F("array", items=physical_spec()),
        "business_period": F("object", nullable=True, fields={"start": F("string"), "end": F("string"),
                                                               "calendar_reference": F("string")}),
        "period_not_applicable_reason": F("string", nullable=True)})


def evidence_spec():
    return F("object", fields={"kind": F("string", choices=("observation", "hypothesis", "documentary", "approved_assertion")),
        "discovery_reference": ref("SchemaDiscoveryResult", nullable=True),
        "evidence_id": F("string", nullable=True), "field_id": F("string", nullable=True),
        "hypothesis_id": F("string", nullable=True), "record_reference": ref("SupportingEvidenceRecord", nullable=True),
        "binding_reference": ref("SemanticBinding", nullable=True), "approval_reference": ref("ApprovalRecord", nullable=True)})


def conditions_spec():
    return F("array", items=F("object", fields={"condition_id": F("string"), "definition": F("string"),
        "evaluation_method": F("string", choices=("trusted_attestation_required",)),
        "evidence_references": F("array", items=evidence_spec())}))


def validate_field(field, resolver):
    discovery = resolver(field["discovery_reference"])
    if (discovery["source_reference"] != field["source_metadata_reference"] or
            discovery["source_version"] != field["source_version"] or discovery["schema_version"] != field["schema_version"]):
        raise GovernanceError("field_context_mismatch", "Physical field source/schema references do not agree.")
    for table in discovery["tables"]:
        if table["table_id"] == field["table_id"]:
            for item in table["fields"]:
                if item["field_id"] == field["field_id"] and item["position"] == field["field_position"]:
                    return item
    raise GovernanceError("field_context_mismatch", "Physical field/position is absent from the exact discovery.")


def validate_scope(scope, resolver):
    if not scope["field_references"]:
        raise GovernanceError("scope_mismatch", "An explicit nonempty field scope is required.")
    keys = [field_key(f) for f in scope["field_references"]]
    if len(set(keys)) != len(keys):
        raise GovernanceError("scope_mismatch", "Scope contains duplicate field references.")
    for field in scope["field_references"]:
        validate_field(field, resolver)
    period = scope["business_period"]
    if period is None:
        if not scope["period_not_applicable_reason"]:
            raise GovernanceError("scope_mismatch", "Unbounded business applicability requires an explicit reason.")
    else:
        try:
            if date.fromisoformat(period["start"]) >= date.fromisoformat(period["end"]) or scope["period_not_applicable_reason"] is not None:
                raise ValueError
        except ValueError:
            raise GovernanceError("scope_mismatch", "Business period must be a valid half-open calendar interval.") from None


def validate_evidence(evidence, resolver):
    """Check exact reference and shape; origin/approval trust belongs to service."""
    kind = evidence["kind"]
    required = {"observation": {"discovery_reference", "evidence_id", "field_id"},
                "hypothesis": {"discovery_reference", "field_id", "hypothesis_id"},
                "documentary": {"record_reference"},
                "approved_assertion": {"binding_reference", "approval_reference"}}[kind]
    present = {k for k, v in evidence.items() if k != "kind" and v is not None}
    if present != required:
        raise GovernanceError("unresolved_evidence", "Evidence variant fields are inconsistent.")
    if kind in ("observation", "hypothesis"):
        d = resolver(evidence["discovery_reference"])
        fields = [f for t in d["tables"] for f in t["fields"] if f["field_id"] == evidence["field_id"]]
        if not fields:
            raise GovernanceError("unresolved_evidence", "Evidence field is absent.")
        if kind == "observation":
            matches = [e for e in d["evidence"] if e["evidence_id"] == evidence["evidence_id"] and e["field_id"] == evidence["field_id"]]
        else:
            matches = [h for h in fields[0]["hypotheses"] if h["hypothesis_id"] == evidence["hypothesis_id"]]
        if not matches:
            raise GovernanceError("unresolved_evidence", "Evidence ID is absent from the exact discovery field.")
    if kind == "approved_assertion":
        if resolver(evidence["approval_reference"])["approved_object_reference"] != evidence["binding_reference"]:
            raise GovernanceError("unresolved_evidence", "Prior assertion binding and approval disagree.")


def _checks(doc, resolver):
    issues = envelope_check(doc, resolver)
    try:
        for dependency in doc["dependency_versions"]:
            if resolver(dependency) is None:
                raise GovernanceError("unresolved_reference", "Dependency revision is absent.")
        for evidence in doc["evidence_references"]:
            validate_evidence(evidence, resolver)
        for evidence in doc.get("evidence_snapshot_references", []):
            validate_evidence(evidence, resolver)
        condition_groups = [doc.get("conditions", [])]
        if doc.get("approval_terms"):
            condition_groups.append(doc["approval_terms"]["conditions"])
        for group in condition_groups:
            for condition in group:
                for evidence in condition["evidence_references"]:
                    validate_evidence(evidence, resolver)
        for key in ("interpretation_scope", "requested_scope", "scope", "decision_scope", "approval_scope"):
            if key in doc:
                validate_scope(doc[key], resolver)
                if doc[key]["purpose"] != doc["purpose_scope"]:
                    raise GovernanceError("scope_mismatch", "Scope purpose must match the record purpose.")
        kind = doc["contract_type"]
        if kind == "SemanticBinding":
            validate_field(doc["physical_field_reference"], resolver)
            for f in doc["supporting_field_references"]:
                validate_field(f, resolver)
            if field_key(doc["physical_field_reference"]) not in {field_key(f) for f in doc["interpretation_scope"]["field_references"]}:
                raise GovernanceError("scope_mismatch", "Binding field must belong to its interpretation scope.")
            if not doc["evidence_references"]:
                raise GovernanceError("unresolved_evidence", "A proposed interpretation requires supporting evidence.")
            physical = doc["physical_field_reference"]
            locations = {(digest(f["discovery_reference"]), f["field_id"]) for f in
                         [physical] + doc["supporting_field_references"]}
            primary_evidence = False
            for evidence in doc["evidence_references"]:
                if evidence["kind"] in ("observation", "hypothesis"):
                    location = (digest(evidence["discovery_reference"]), evidence["field_id"])
                    if location not in locations:
                        raise GovernanceError("unresolved_evidence", "Observation evidence is outside the binding/supporting field context.")
                    primary_evidence |= location == (digest(physical["discovery_reference"]), physical["field_id"])
                elif evidence["kind"] == "approved_assertion":
                    parent = resolver(evidence["approval_reference"])
                    if parent["approval_purpose"] != doc["purpose_scope"]:
                        raise GovernanceError("scope_mismatch", "Prior approved assertions cannot be reused for a different approval purpose.")
            if not primary_evidence:
                raise GovernanceError("unresolved_evidence", "Explicit discovery evidence for the bound physical field is required.")
            for qualifier in doc["qualifiers"]:
                if qualifier["status"] == "known" and (qualifier["value"] is None or isinstance(qualifier["value"], dict) and "$state" in qualifier["value"]):
                    raise GovernanceError("unresolved_semantics", "Known qualifiers require an actual value.")
                if qualifier["status"] != "known" and not qualifier["reason"]:
                    raise GovernanceError("unresolved_semantics", "Uncertain/not-applicable qualifiers require a reason.")
            predecessor = doc["predecessor_binding_reference"]
            if predecessor:
                prior = resolver(predecessor)
                if prior["object_id"] != doc["object_id"] or prior["object_revision"] + 1 != doc["object_revision"]:
                    raise GovernanceError("wrong_version", "Binding revisions require their exact immediate predecessor.")
            elif doc["object_revision"] != 1:
                raise GovernanceError("wrong_version", "First binding revision must be one.")
        if kind == "BusinessReviewRequest":
            subject = resolver(doc["subject_reference"])
            scope = subject.get("interpretation_scope", subject.get("approval_scope"))
            if digest(subject) != doc["subject_digest"] or not scope_contains(scope, doc["requested_scope"]):
                raise GovernanceError("scope_mismatch", "Review request does not match its frozen subject/scope.")
            if doc["review_purpose"] != doc["purpose_scope"]:
                raise GovernanceError("scope_mismatch", "Review purpose must match the scope.")
            if doc["evidence_snapshot_references"] != subject["evidence_references"]:
                raise GovernanceError("unresolved_evidence", "Review evidence must freeze the subject's exact evidence basis.")
            is_binding = subject["contract_type"] == "SemanticBinding"
            if is_binding != (doc["requested_review_kind"] == "interpretation_review") or is_binding != (doc["approval_terms"] is not None):
                raise GovernanceError("wrong_subject_type", "Review kind and frozen approval terms must match the subject.")
            if doc["approval_terms"]:
                for bound in ("expires_at", "review_due_at"):
                    if doc["approval_terms"][bound] is not None:
                        instant(doc["approval_terms"][bound])
        if kind == "AuthorityVerificationRecord":
            if doc["verification_outcome"] == "verified":
                if doc["authority_reference"] is None or doc["verification_valid_until"] is None:
                    raise GovernanceError("authority_denied", "Verified authority requires an exact grant and freshness limit.")
                if instant(doc["verification_valid_until"]) <= instant(doc["verified_at"]):
                    raise GovernanceError("invalid_timestamp", "Authority verification interval must be positive.")
        if kind == "BusinessReviewDecision":
            request = resolver(doc["review_request_reference"])
            if (request["subject_reference"] != doc["subject_reference"] or request["subject_digest"] != doc["subject_digest"] or
                    not scope_contains(request["requested_scope"], doc["decision_scope"])):
                raise GovernanceError("wrong_version", "Decision must match the frozen request and exact version.")
            verification = resolver(doc["authority_verification_reference"])
            if (verification["verification_outcome"] != "verified" or verification["subject_reference"] != doc["subject_reference"] or
                    verification["requested_action"] != doc["action"] or verification["principal_reference"] != doc["reviewer_principal_reference"] or
                    verification["scope"] != doc["decision_scope"]):
                raise GovernanceError("authority_denied", "Decision lacks matching authority evidence.")
            if not instant(verification["verified_at"]) <= instant(doc["decided_at"]) < instant(verification["verification_valid_until"]):
                raise GovernanceError("authority_denied", "Decision is outside its authority receipt validity.")
            lifecycle_action = doc["action"] in ("revoke", "supersede")
            if lifecycle_action != (doc["affected_approval_reference"] is not None) or (doc["action"] == "supersede") != (doc["replacement_approval_reference"] is not None):
                raise GovernanceError("invalid_action", "Lifecycle actions require exact affected/replacement approval references.")
        if kind == "ApprovalRecord":
            target = resolver(doc["approved_object_reference"])
            if digest(target) != doc["approved_object_digest"] or not scope_contains(target["interpretation_scope"], doc["approval_scope"]):
                raise GovernanceError("wrong_version", "Approval object digest/version/scope disagree.")
            if not doc["approval_decision_references"]:
                raise GovernanceError("authority_denied", "Approval requires explicit approve decisions.")
            for decision in doc["approval_decision_references"]:
                item = resolver(decision)
                if (item["action"] != "approve" or item["subject_reference"] != doc["approved_object_reference"]
                        or item["review_request_reference"] != doc["review_request_reference"] or item["decision_scope"] != doc["approval_scope"]):
                    raise GovernanceError("authority_denied", "Approval decisions must explicitly approve this revision.")
            decisions = [resolver(d) for d in doc["approval_decision_references"]]
            if (doc["approver_principal_references"] != [d["reviewer_principal_reference"] for d in decisions] or
                    doc["authority_verification_references"] != [d["authority_verification_reference"] for d in decisions]
                    or len(set(doc["approver_principal_references"])) != len(decisions)):
                raise GovernanceError("authority_denied", "Approval principals and receipts must match distinct review decisions.")
            request = resolver(doc["review_request_reference"])
            terms = request["approval_terms"]
            if terms is None or any(doc[k] != terms[k] for k in ("expires_at", "review_due_at", "no_deadline_reasons", "conditions", "limitations")):
                raise GovernanceError("scope_mismatch", "Issued approval must preserve the frozen reviewed terms.")
            if instant(doc["valid_from"]) < instant(doc["issued_at"]):
                raise GovernanceError("invalid_timestamp", "Approval cannot backdate execution validity.")
            for bound in ("expires_at", "review_due_at"):
                if doc[bound] is None:
                    if not doc["no_deadline_reasons"].get(bound):
                        raise GovernanceError("invalid_timestamp", "Null deadlines require a policy reason.")
                elif instant(doc[bound]) <= instant(doc["valid_from"]):
                    raise GovernanceError("invalid_timestamp", "Approval deadline must follow issuance.")
        for key in ("verified_at", "verification_valid_until", "decided_at", "recorded_at", "issued_at", "valid_from",
                    "expires_at", "review_due_at", "received_at", "valid_until", "detected_at", "assessed_at", "due_at"):
            if doc.get(key) is not None:
                instant(doc[key])
    except GovernanceError as exc:
        issues.append(ValidationIssue("$", exc.code, exc.message))
    return issues


def register_semantic_contracts(registry):
    """Register new types once; no existing definition is changed."""
    text = F("string"); nullable_text = F("string", nullable=True)
    policy = F("object", fields={"policy_id": text, "policy_version": text})
    authority = F("object", nullable=True, fields={"provider_id": text, "grant_id": text, "grant_version": text})
    interpretation = F("object", fields={"concept": text, "definition": text, "definition_version": text,
                                            "definition_reference": ref("SupportingEvidenceRecord", nullable=True)})
    definitions = {
        "SemanticBinding": {"physical_field_reference": physical_spec(), "interpretation": interpretation,
            "interpretation_scope": scope_spec(), "qualifiers": F("array", items=F("object", fields={
                "name": text, "value": F("any", nullable=True, uncertain=True), "status": F("string", choices=("known", "not_applicable", "unknown", "unavailable")), "reason": nullable_text})),
            "supporting_field_references": F("array", items=physical_spec()),
            "interpretation_provenance": F("object", fields={"proposed_by": text, "method": text, "method_version": text, "context_reference": text}),
            "uncertainties": F("array", items=F("object", fields={"description": text, "blocking": F("boolean")})),
            "limitations": texts(), "alternatives": texts(), "predecessor_binding_reference": ref("SemanticBinding", nullable=True),
            "proposal_state": F("string", choices=("proposed",))},
        "BusinessReviewRequest": {"subject_reference": ref("SemanticBinding", "ApprovalRecord"), "requested_review_kind": F("string", choices=("interpretation_review", "approval_lifecycle_review")),
            "requested_scope": scope_spec(), "review_purpose": text, "submitted_by_context_reference": text,
            "subject_digest": text, "evidence_snapshot_references": F("array", items=evidence_spec()), "review_policy_reference": policy,
            "predecessor_request_reference": ref("BusinessReviewRequest", nullable=True), "resubmission_reason": nullable_text,
            "expected_governance_head": F("integer", minimum=0), "due_at": nullable_text,
            "approval_terms": F("object", nullable=True, fields={"expires_at": nullable_text, "review_due_at": nullable_text,
                "no_deadline_reasons": F("object"), "conditions": conditions_spec(), "limitations": texts()})},
        "AuthorityVerificationRecord": {"principal_reference": text, "authentication_context_reference": text,
            "authority_reference": authority, "policy_reference": policy, "requested_action": text,
            "subject_reference": ref("SemanticBinding", "ApprovalRecord"), "scope": scope_spec(),
            "verified_by": text, "verified_at": text, "verification_valid_until": nullable_text,
            "grant_validity": F("object", fields={"valid_from": nullable_text, "valid_until": nullable_text}),
            "delegation_chain": texts(), "verification_outcome": F("string", choices=("verified", "denied", "unavailable")),
            "reason_codes": texts(), "verification_receipt_reference": text},
        "BusinessReviewDecision": {"review_request_reference": ref("BusinessReviewRequest"),
            "subject_reference": ref("SemanticBinding", "ApprovalRecord"), "subject_digest": text,
            "action": F("string", choices=("approve", "reject", "request_clarification", "revoke", "supersede")),
            "reviewer_principal_reference": text, "authority_verification_reference": ref("AuthorityVerificationRecord"),
            "decision_scope": scope_spec(), "review_policy_reference": policy, "decided_at": text, "recorded_at": text,
            "rationale": text, "conditions": conditions_spec(), "limitations": texts(),
            "affected_approval_reference": ref("ApprovalRecord", nullable=True), "replacement_approval_reference": ref("ApprovalRecord", nullable=True),
            "expected_governance_head": F("integer", minimum=0), "command_id": text, "record_receipt_reference": text},
        "ApprovalRecord": {"approved_object_reference": ref("SemanticBinding"), "approved_object_digest": text,
            "review_request_reference": ref("BusinessReviewRequest"), "approval_decision_references": refs("BusinessReviewDecision"),
            "approver_principal_references": texts(), "authority_verification_references": refs("AuthorityVerificationRecord"),
            "approval_purpose": text, "approval_scope": scope_spec(), "policy_reference": policy,
            "conditions": conditions_spec(), "limitations": texts(), "issued_by": text, "issued_at": text, "valid_from": text,
            "expires_at": nullable_text, "review_due_at": nullable_text, "no_deadline_reasons": F("object"),
            "record_state": F("string", choices=("issued",)), "record_receipt_reference": text},
        "SupportingEvidenceRecord": {"artifact_reference": text, "artifact_version": text, "content_digest": text,
            "digest_scheme": F("string", choices=("sha256",)), "evidence_kind": text, "claim_summary": text,
            "relevant_subject_references": refs("DataSourceMetadata", "SchemaDiscoveryResult", "SemanticBinding"),
            "origin_identity_reference": nullable_text, "received_by": text, "received_at": text,
            "origin_verification": F("string", choices=("verified_origin", "unverified", "unavailable")),
            "limitations": texts(), "coverage": text, "access_policy_reference": text, "retention_reference": text,
            "valid_until": nullable_text, "predecessor_evidence_reference": ref("SupportingEvidenceRecord", nullable=True)},
        "BindingChangeAssessment": {"binding_reference": ref("SemanticBinding"), "approval_references": refs("ApprovalRecord"),
            "previous_context_references": F("array", items=physical_spec()), "new_context_references": F("array", items=physical_spec()),
            "trigger_kind": text, "trigger_reference": ref("SchemaDiscoveryResult"), "detected_at": text,
            "observed_changes": F("array", items=F("object")), "comparison_method_reference": text,
            "dependency_paths": F("array", items=refs("SemanticBinding", "ApprovalRecord", "SupportingEvidenceRecord")),
            "impact": F("string", choices=("no_effect_original_scope", "review_required", "incompatible")),
            "required_actions": texts(), "assessed_by": text, "assessment_method": text, "limitations": texts()},
        "BindingUseAssessment": {"binding_reference": ref("SemanticBinding"), "candidate_approval_references": refs("ApprovalRecord"),
            "requested_context": F("object", fields={"scope": scope_spec(), "physical_field_reference": physical_spec(), "caller_reference": text}),
            "assessed_at": text, "trusted_governance_head": F("integer", minimum=0), "authority_context_reference": text,
            "resolved_dependencies": refs("SemanticBinding", "ApprovalRecord", "DataSourceMetadata", "SchemaDiscoveryResult", "SupportingEvidenceRecord"),
            "condition_results": F("array", items=F("object")), "change_assessment_references": refs("BindingChangeAssessment"),
            "result": F("string", choices=("usable", "not_approved", "rejected", "clarification_requested", "conditions_unverified", "needs_review", "expired", "revoked", "superseded", "conflict", "access_denied", "authority_unavailable", "invalid_reference")),
            "lifecycle_state": F("string", choices=("proposed", "approved", "rejected", "clarification_requested", "revoked", "superseded", "expired", "needs_review", "blocked")),
            "reason_codes": texts(), "required_evidence_or_action": texts(), "valid_until": text,
            "recheck_triggers": texts(), "assessment_receipt_reference": text}}
    for kind in CONTRACT_TYPES:
        fields = {**envelope_fields(), "contract_type": F("string", choices=(kind,)),
                  "contract_version": F("string", choices=("1.0",)),
                  "evidence_references": F("array", items=evidence_spec()),
                  "dependency_versions": refs("DataSourceMetadata", "SchemaDiscoveryResult", *CONTRACT_TYPES),
                  **definitions[kind]}
        registry.register(ContractDefinition(kind, "1.0", fields, (_checks,)))
    return registry


def semantic_registry():
    return register_semantic_contracts(foundation_registry())
