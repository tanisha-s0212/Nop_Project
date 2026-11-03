"""Explicit semantic review and lifecycle operations over immutable metadata.

This is an in-process development foundation, not a production authorization
service. No semantic inference, data preparation or ML execution occurs here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from ..contracts import reference
from ..discovery import compare_schemas
from .authority import AuthorityProvider
from .common import GovernanceError, clone, digest, field_key, instant, scope_contains, scope_overlaps
from .contracts import validate_field, validate_scope, validate_evidence
from .journal import GovernanceJournal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewPolicy:
    policy_id: str
    policy_version: str
    minimum_approvers: int = 1
    independent_review: bool = True
    allow_no_deadline: bool = False
    continuing_authority: bool = False
    assessment_ttl_seconds: int = 60

    def __post_init__(self):
        if (not isinstance(self.policy_id, str) or not self.policy_id.strip() or
                not isinstance(self.policy_version, str) or not self.policy_version.strip() or
                any(type(v) is not bool for v in (self.independent_review, self.allow_no_deadline, self.continuing_authority)) or
                type(self.minimum_approvers) is not int
                or self.minimum_approvers < 1 or type(self.assessment_ttl_seconds) is not int or self.assessment_ttl_seconds < 1):
            raise ValueError("Policy identity, positive reviewer count and assessment lifetime are required.")

    def reference(self):
        return {"policy_id": self.policy_id, "policy_version": self.policy_version}


class SemanticApprovalService:
    def __init__(self, catalogue, authority_provider: AuthorityProvider, policy: ReviewPolicy,
                 *, allow_test_authority=False, clock=None, journal=None, operation_guard=None):
        if authority_provider.test_only and allow_test_authority is not True:
            raise GovernanceError("test_provider_disabled", "A test-only authority provider needs explicit service opt-in.")
        self._catalogue, self._provider, self._policy = catalogue, authority_provider, policy
        self._journal = journal if journal is not None else GovernanceJournal(catalogue)
        if self._journal.catalogue is not catalogue:
            raise GovernanceError("journal_catalogue_mismatch", "Journal and service must share the same catalogue.")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_clock = None
        self._operation_guard = operation_guard

    @property
    def head(self):
        return self._journal.head

    def _now(self):
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise GovernanceError("invalid_timestamp", "Service clock must return an aware datetime.")
        persisted = getattr(self._journal, "last_clock", None)
        floor = instant(persisted) if persisted else self._last_clock
        if floor is not None and now < floor:
            raise GovernanceError("clock_regression", "Clock moved backwards; governance operation was blocked.")
        self._last_clock = now
        if hasattr(self._journal, "record_clock"):
            self._journal.record_clock(now)
        return now

    def get(self, ref):
        with self._journal.lock:
            return self._journal.get(ref)

    def records(self, kind=None):
        with self._journal.lock:
            return self._journal.documents(kind)

    def history(self):
        with self._journal.lock:
            return self._journal.history()

    def _new(self, kind, principal, purpose, now, *, object_id=None, revision=1, evidence=(), dependencies=(), **body):
        return {"contract_type": kind, "contract_version": "1.0", "object_id": object_id or str(uuid4()),
            "object_revision": revision, "created_at": now.isoformat(), "owner_reference": principal,
            "purpose_scope": purpose, "evidence_references": clone(list(evidence)),
            "dependency_versions": clone(list(dependencies)), **clone(body)}

    def _receipt(self):
        return self._journal.instance_id + ":" + str(uuid4())

    def _run(self, operation, context, command_id, expected_head, payload, build):
        if not isinstance(command_id, str) or not command_id.strip():
            raise GovernanceError("invalid_command", "A nonempty idempotency command ID is required.")
        try:
            with self._journal.lock:
                now = self._now()
                principal, context_ref = self._provider.authenticate(context, now)
                command_digest = digest({"operation": operation, "principal": principal, "payload": payload})
                outcome = self._journal.replay(command_id, command_digest)
                if outcome is None:
                    self._journal.check_head(expected_head)
                    try:
                        docs, outcome = build(principal, context_ref, now)
                    except (KeyError, TypeError, IndexError, ValueError):
                        raise GovernanceError("invalid_governance_input", "Input does not match the structured governance interface.") from None
                    if self._operation_guard is not None:
                        self._operation_guard(operation, context, payload, docs, outcome, now)
                    outcome = self._journal.commit(docs, expected_head=expected_head, command_id=command_id,
                                                    command_digest=command_digest, outcome=outcome)
            # A denied action's audit/verification must commit before raising.
            if "error_code" in outcome:
                raise GovernanceError(outcome["error_code"], "Authority verification did not authorize this action; verification was recorded.")
            logger.info("governance.operation_recorded", extra={"operation": operation, "governance_head": self.head})
            return outcome
        except GovernanceError as exc:
            logger.warning("governance.operation_blocked", extra={"operation": operation, "error_code": exc.code})
            if hasattr(self._journal, "record_failure"):
                self._journal.record_failure(operation, exc.code, authorization=getattr(exc, "audit_authorization", None))
            raise

    def _authorization(self, context, action, subject_ref, scope, principal, now):
        body = self._provider.verify(context, action, subject_ref, scope, self._policy.reference(), now)
        record = self._new("AuthorityVerificationRecord", principal, scope["purpose"], now, **body)
        if body["verification_outcome"] == "verified" and not self._provider.verify_record(record, now):
            raise GovernanceError("unverified_authority_receipt", "Provider receipt could not be verified.")
        if body["verification_outcome"] != "verified":
            return record, {"error_code": "authority_unavailable" if body["verification_outcome"] == "unavailable" else "authority_denied",
                            "verification_reference": reference(record)}
        if (body["principal_reference"] != principal or body["scope"] != scope or body["subject_reference"] != subject_ref
                or body["requested_action"] != action or body["policy_reference"] != self._policy.reference()
                or instant(body["verified_at"]) > now or now >= instant(body["verification_valid_until"])):
            raise GovernanceError("authority_denied", "Provider verification does not match this action or validity window.")
        return record, None

    def physical_field_reference(self, discovery_ref, table_id, field_id):
        discovery = self._catalogue.get(discovery_ref)
        self._catalogue.registry.validate(discovery, resolver=self._catalogue.resolve)
        for table in discovery["tables"]:
            if table["table_id"] == table_id:
                for field in table["fields"]:
                    if field["field_id"] == field_id:
                        return {"source_metadata_reference": discovery["source_reference"], "discovery_reference": reference(discovery),
                            "source_version": discovery["source_version"], "schema_version": discovery["schema_version"],
                            "table_id": table_id, "field_id": field_id, "field_position": field["position"]}
        raise GovernanceError("field_context_mismatch", "Field is absent from the exact discovery table.")

    def _field(self, field):
        for ref in (field["source_metadata_reference"], field["discovery_reference"]):
            self._catalogue.registry.validate(self._catalogue.get(ref), resolver=self._catalogue.resolve)
        return validate_field(field, self._catalogue.resolve)

    def _evidence(self, items):
        for item in items:
            validate_evidence(item, self._catalogue.resolve)
            if item["kind"] in ("observation", "hypothesis"):
                self._catalogue.registry.validate(self._catalogue.get(item["discovery_reference"]), resolver=self._catalogue.resolve)
            elif item["kind"] == "documentary":
                self.get(item["record_reference"])
            else:
                self.get(item["binding_reference"])
                self.get(item["approval_reference"])

    def propose_binding(self, *, object_id, physical_field_reference, interpretation, scope, evidence,
                        context, command_id, expected_head, predecessor=None, qualifiers=(),
                        supporting_fields=(), uncertainties=(), limitations=(), alternatives=(), provenance=None):
        payload = {"object_id": object_id, "field": physical_field_reference, "interpretation": interpretation,
            "scope": scope, "evidence": evidence, "predecessor": predecessor, "qualifiers": list(qualifiers),
            "supporting_fields": list(supporting_fields), "uncertainties": list(uncertainties),
            "limitations": list(limitations), "alternatives": list(alternatives), "provenance": provenance}
        def build(principal, context_ref, now):
            self._field(physical_field_reference)
            validate_scope(scope, self._catalogue.resolve)
            self._evidence(evidence)
            definition_ref = interpretation.get("definition_reference")
            if definition_ref is not None:
                self.get(definition_ref)
                if not any(e["kind"] == "documentary" and e["record_reference"] == definition_ref for e in evidence):
                    raise GovernanceError("unresolved_evidence", "A referenced meaning definition must be part of the frozen documentary evidence.")
            for field in supporting_fields:
                self._field(field)
            existing = [d for d in self.records("SemanticBinding") if d["object_id"] == object_id]
            revision = len(existing) + 1
            if existing:
                if predecessor != reference(existing[-1]):
                    raise GovernanceError("wrong_version", "A new binding revision must name the exact current predecessor.")
            elif predecessor is not None:
                raise GovernanceError("wrong_version", "New binding lineage cannot name a predecessor.")
            document = self._new("SemanticBinding", principal, scope["purpose"], now, object_id=object_id,
                revision=revision, evidence=evidence,
                dependencies=[physical_field_reference["source_metadata_reference"], physical_field_reference["discovery_reference"]],
                physical_field_reference=physical_field_reference, interpretation=interpretation, interpretation_scope=scope,
                qualifiers=list(qualifiers), supporting_field_references=list(supporting_fields),
                interpretation_provenance=provenance or {"proposed_by": principal, "method": "explicit_structured_proposal",
                    "method_version": "1", "context_reference": context_ref},
                uncertainties=list(uncertainties), limitations=list(limitations), alternatives=list(alternatives),
                predecessor_binding_reference=predecessor, proposal_state="proposed")
            return [document], {"record_reference": reference(document)}
        result = self._run("propose_binding", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def register_evidence(self, *, artifact_reference, artifact_version, content_digest, evidence_kind,
                          claim_summary, origin_identity, coverage, access_policy_reference, retention_reference,
                          purpose, context, command_id, expected_head, relevant_subjects=(), limitations=(),
                          valid_until=None, predecessor=None, authorization_scope=None):
        payload = {"artifact": artifact_reference, "version": artifact_version, "digest": content_digest,
            "kind": evidence_kind, "claim": claim_summary, "origin": origin_identity, "coverage": coverage,
            "access": access_policy_reference, "retention": retention_reference, "purpose": purpose,
            "relevant": list(relevant_subjects), "limitations": list(limitations), "valid_until": valid_until, "predecessor": predecessor,
            "authorization_scope": authorization_scope}
        def build(principal, context_ref, now):
            if not isinstance(content_digest, str) or not content_digest.startswith("sha256:") or len(content_digest) != 71:
                raise GovernanceError("invalid_digest", "Document evidence requires a complete sha256 digest.")
            origin_verified = self._provider.verify_evidence_origin(artifact_reference, content_digest, origin_identity)
            prior = self.get(predecessor) if predecessor else None
            document = self._new("SupportingEvidenceRecord", principal, purpose, now,
                object_id=prior["object_id"] if prior else None, revision=prior["object_revision"]+1 if prior else 1,
                dependencies=list(relevant_subjects), artifact_reference=artifact_reference, artifact_version=artifact_version,
                content_digest=content_digest, digest_scheme="sha256", evidence_kind=evidence_kind, claim_summary=claim_summary,
                relevant_subject_references=list(relevant_subjects), origin_identity_reference=origin_identity,
                received_by=principal, received_at=now.isoformat(), origin_verification="verified_origin" if origin_verified else "unverified",
                limitations=list(limitations), coverage=coverage, access_policy_reference=access_policy_reference,
                retention_reference=retention_reference, valid_until=valid_until, predecessor_evidence_reference=predecessor)
            return [document], {"record_reference": reference(document)}
        result = self._run("register_evidence", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def submit_review(self, subject_ref, *, scope, context, command_id, expected_head,
                      expires_at=None, review_due_at=None, no_deadline_reasons=None, conditions=(), limitations=(),
                      predecessor_request=None, resubmission_reason=None, due_at=None):
        terms = {"expires_at": expires_at, "review_due_at": review_due_at, "no_deadline_reasons": no_deadline_reasons or {},
                 "conditions": list(conditions), "limitations": list(limitations)}
        payload = {"subject": subject_ref, "scope": scope, "terms": terms, "predecessor": predecessor_request,
                   "reason": resubmission_reason, "due_at": due_at}
        def build(principal, context_ref, now):
            subject = self.get(subject_ref)
            validate_scope(scope, self._catalogue.resolve)
            binding_review = subject["contract_type"] == "SemanticBinding"
            if subject["contract_type"] not in ("SemanticBinding", "ApprovalRecord"):
                raise GovernanceError("wrong_subject_type", "Review requires a binding or approval reference.")
            original_scope = subject["interpretation_scope"] if binding_review else subject["approval_scope"]
            if not scope_contains(original_scope, scope) or not binding_review and original_scope != scope:
                raise GovernanceError("scope_mismatch", "Review scope exceeds its subject or attempts partial retirement.")
            if binding_review:
                for bound in ("expires_at", "review_due_at"):
                    if terms[bound] is None:
                        if not self._policy.allow_no_deadline or not terms["no_deadline_reasons"].get(bound):
                            raise GovernanceError("deadline_required", "Review policy requires explicit approval deadlines.")
                    elif instant(terms[bound]) <= now:
                        raise GovernanceError("invalid_timestamp", "Approval deadlines must be in the future.")
            if predecessor_request:
                self.get(predecessor_request)
                if not resubmission_reason:
                    raise GovernanceError("resubmission_reason_required", "A continued review needs a recorded reason.")
            document = self._new("BusinessReviewRequest", principal, scope["purpose"], now,
                evidence=subject["evidence_references"], dependencies=[subject_ref], subject_reference=subject_ref,
                requested_review_kind="interpretation_review" if binding_review else "approval_lifecycle_review",
                requested_scope=scope, review_purpose=scope["purpose"], submitted_by_context_reference=context_ref,
                subject_digest=digest(subject), evidence_snapshot_references=subject["evidence_references"],
                review_policy_reference=self._policy.reference(), predecessor_request_reference=predecessor_request,
                resubmission_reason=resubmission_reason, expected_governance_head=self.head, due_at=due_at,
                approval_terms=terms if binding_review else None)
            return [document], {"record_reference": reference(document)}
        result = self._run("submit_review", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def _request_decisions(self, request_ref):
        return [d for d in self.records("BusinessReviewDecision") if d["review_request_reference"] == request_ref]

    def _retirement(self, approval_ref):
        for decision in reversed(self.records("BusinessReviewDecision")):
            if decision["affected_approval_reference"] == approval_ref and decision["action"] in ("revoke", "supersede"):
                return "revoked" if decision["action"] == "revoke" else "superseded"
        return None

    def _approval_state(self, approval, now, seen=None):
        retired = self._retirement(reference(approval))
        if retired:
            return retired
        for bound in ("expires_at", "review_due_at"):
            if approval[bound] is not None and now >= instant(approval[bound]):
                return "expired"
        if now < instant(approval["valid_from"]):
            return "conditions_unverified"
        for ref in approval["authority_verification_references"]:
            verification = self.get(ref)
            if not self._provider.verify_record(verification, now):
                return "authority_unavailable"
            if self._policy.continuing_authority and not self._provider.verify_continuing_authority(verification, now):
                return "needs_review"
        if approval["conditions"]:
            return "conditions_unverified"  # No unimplemented attestation is assumed true.
        binding = self.get(approval["approved_object_reference"])
        self._field(binding["physical_field_reference"])
        seen = set() if seen is None else set(seen)
        key = digest(reference(approval))
        if key in seen:
            return "needs_review"
        seen.add(key)
        for e in binding["evidence_references"]:
            if e["kind"] == "documentary":
                document = self.get(e["record_reference"])
                if document["origin_verification"] != "verified_origin" or document["valid_until"] and now >= instant(document["valid_until"]):
                    return "needs_review"
            elif e["kind"] == "approved_assertion":
                if self._approval_state(self.get(e["approval_reference"]), now, seen) != "usable":
                    return "needs_review"
        return "usable"

    def decide(self, request_ref, subject_ref, *, action, context, rationale, command_id, expected_head,
               replacement_approval=None):
        payload = {"request": request_ref, "subject": subject_ref, "action": action, "rationale": rationale,
                   "replacement": replacement_approval}
        def build(principal, context_ref, now):
            request, subject = self.get(request_ref), self.get(subject_ref)
            if request["subject_reference"] != subject_ref or request["subject_digest"] != digest(subject):
                raise GovernanceError("wrong_version", "Decision must name the exact submitted object revision.")
            if request["review_policy_reference"] != self._policy.reference():
                raise GovernanceError("policy_changed", "Review policy version no longer matches.")
            if request["due_at"] and now >= instant(request["due_at"]):
                raise GovernanceError("review_expired", "Review deadline has passed.")
            decisions = self._request_decisions(request_ref)
            if (any(d["action"] != "approve" for d in decisions)
                    or any(a["review_request_reference"] == request_ref for a in self.records("ApprovalRecord"))):
                raise GovernanceError("review_closed", "Review already has a terminal disposition.")
            binding_review = subject["contract_type"] == "SemanticBinding"
            if action not in (("approve", "reject", "request_clarification") if binding_review else ("revoke", "supersede")):
                raise GovernanceError("invalid_action", "Action does not apply to this review subject.")
            scope = request["requested_scope"]
            verification, denied = self._authorization(context, action, subject_ref, scope, principal, now)
            if denied:
                return [verification], denied
            if binding_review and self._policy.independent_review and principal in (request["owner_reference"], subject["owner_reference"]):
                raise GovernanceError("independent_review_required", "The submitter cannot decide their own interpretation under this policy.")
            if any(d["reviewer_principal_reference"] == principal for d in decisions):
                raise GovernanceError("duplicate_reviewer", "An additional vote must come from a distinct reviewer.")
            if action == "approve":
                for bound in ("expires_at", "review_due_at"):
                    if request["approval_terms"][bound] and now >= instant(request["approval_terms"][bound]):
                        raise GovernanceError("review_expired", "The proposed approval limits expired before this decision.")
                if any(u["blocking"] for u in subject["uncertainties"]) or any(q["status"] in ("unknown", "unavailable") for q in subject["qualifiers"]):
                    raise GovernanceError("unresolved_semantics", "Blocking uncertainties or qualifiers remain unresolved.")
                self._evidence(subject["evidence_references"])
                for e in subject["evidence_references"]:
                    if e["kind"] == "documentary":
                        evidence = self.get(e["record_reference"])
                        if evidence["origin_verification"] != "verified_origin" or evidence["valid_until"] and now >= instant(evidence["valid_until"]):
                            raise GovernanceError("unverified_evidence", "Required documentary evidence has no current verified origin.")
                        field = subject["physical_field_reference"]
                        relevant = [subject_ref, field["source_metadata_reference"], field["discovery_reference"]]
                        if not any(r in relevant for r in evidence["relevant_subject_references"]):
                            raise GovernanceError("unresolved_evidence", "Documentary evidence is not linked to this exact binding/source context.")
                    if e["kind"] == "approved_assertion" and self._approval_state(self.get(e["approval_reference"]), now) != "usable":
                        raise GovernanceError("dependency_not_usable", "A required prior approved assertion is not usable.")
            elif not binding_review:
                if self._retirement(subject_ref):
                    raise GovernanceError("approval_retired", "Retired approvals cannot be silently revived or retired again.")
                if action == "supersede":
                    replacement = self.get(replacement_approval) if replacement_approval else None
                    if (replacement is None or reference(replacement) == subject_ref or replacement["contract_type"] != "ApprovalRecord"
                            or self._approval_state(subject, now) == "expired" or self._approval_state(replacement, now) != "usable"
                            or any(subject["approval_scope"][k] != replacement["approval_scope"][k] for k in ("purpose", "namespace", "record_grain"))):
                        raise GovernanceError("invalid_replacement", "Supersession requires an independently usable compatible replacement.")
            terms = request["approval_terms"] or {"conditions": [], "limitations": []}
            decision = self._new("BusinessReviewDecision", principal, scope["purpose"], now,
                evidence=request["evidence_snapshot_references"], dependencies=[request_ref, subject_ref, reference(verification)],
                review_request_reference=request_ref, subject_reference=subject_ref, subject_digest=request["subject_digest"], action=action,
                reviewer_principal_reference=principal, authority_verification_reference=reference(verification), decision_scope=scope,
                review_policy_reference=self._policy.reference(), decided_at=now.isoformat(), recorded_at=now.isoformat(), rationale=rationale,
                conditions=terms["conditions"], limitations=terms["limitations"],
                affected_approval_reference=None if binding_review else subject_ref,
                replacement_approval_reference=replacement_approval if action == "supersede" else None,
                expected_governance_head=self.head, command_id=command_id, record_receipt_reference=self._receipt())
            docs, approval = [verification, decision], None
            voters = decisions + [decision]
            if action == "approve" and len(voters) >= self._policy.minimum_approvers:
                for voter in decisions:
                    if not self._provider.verify_record(self.get(voter["authority_verification_reference"]), now):
                        raise GovernanceError("authority_unavailable", "A required earlier vote no longer has verifiable authority provenance.")
                approval = self._new("ApprovalRecord", principal, scope["purpose"], now,
                    evidence=request["evidence_snapshot_references"], dependencies=[subject_ref, request_ref] + [reference(v) for v in voters],
                    approved_object_reference=subject_ref, approved_object_digest=digest(subject), review_request_reference=request_ref,
                    approval_decision_references=[reference(v) for v in voters],
                    approver_principal_references=[v["reviewer_principal_reference"] for v in voters],
                    authority_verification_references=[v["authority_verification_reference"] for v in voters],
                    approval_purpose=scope["purpose"], approval_scope=scope, policy_reference=self._policy.reference(),
                    conditions=terms["conditions"], limitations=terms["limitations"], issued_by=self._journal.instance_id,
                    issued_at=now.isoformat(), valid_from=now.isoformat(), expires_at=terms["expires_at"], review_due_at=terms["review_due_at"],
                    no_deadline_reasons=terms["no_deadline_reasons"], record_state="issued", record_receipt_reference=self._receipt())
                docs.append(approval)
            return docs, {"verification_reference": reference(verification), "decision_reference": reference(decision),
                          "approval_reference": reference(approval) if approval else None}
        return self._run("decide", context, command_id, expected_head, payload, build)

    def assess_change(self, binding_ref, new_discovery_ref, *, context, command_id, expected_head, new_field=None):
        payload = {"binding": binding_ref, "discovery": new_discovery_ref, "new_field": new_field}
        def build(principal, context_ref, now):
            binding = self.get(binding_ref)
            original = binding["physical_field_reference"]
            self._field(original)
            new_discovery = self._catalogue.get(new_discovery_ref)
            self._catalogue.registry.validate(new_discovery, resolver=self._catalogue.resolve)
            verification, denied = self._authorization(context, "assess_change", binding_ref,
                                                       binding["interpretation_scope"], principal, now)
            if denied:
                return [verification], denied
            old_discovery = self._catalogue.get(original["discovery_reference"])
            same_source = old_discovery["source_reference"]["object_id"] == new_discovery["source_reference"]["object_id"]
            changes = compare_schemas(old_discovery, new_discovery) if same_source else [{"kind": "different_source_identity"}]
            candidate = new_field
            if candidate is None and same_source:
                try:
                    candidate = self.physical_field_reference(new_discovery_ref, original["table_id"], original["field_id"])
                except GovernanceError:
                    candidate = None
            if candidate is not None and candidate["discovery_reference"] != new_discovery_ref:
                raise GovernanceError("field_context_mismatch", "Candidate field must belong to the new exact discovery.")
            impact = "review_required"
            if candidate is None or not same_source:
                impact = "incompatible"
            else:
                old_field, proposed_field = self._field(original), self._field(candidate)
                if field_key(original) == field_key(candidate):
                    impact = "no_effect_original_scope"
                elif original["field_position"] != candidate["field_position"] or old_field["raw_header"] != proposed_field["raw_header"]:
                    impact = "incompatible"
            approvals = [reference(a) for a in self.records("ApprovalRecord") if a["approved_object_reference"] == binding_ref]
            document = self._new("BindingChangeAssessment", principal, binding["purpose_scope"], now,
                evidence=binding["evidence_references"], dependencies=[binding_ref, new_discovery_ref],
                binding_reference=binding_ref, approval_references=approvals, previous_context_references=[original],
                new_context_references=[candidate] if candidate else [],
                trigger_kind="source_or_discovery_context_change", trigger_reference=new_discovery_ref,
                detected_at=now.isoformat(), observed_changes=changes, comparison_method_reference="foundation.compare_schemas/v1-plus-exact-context",
                dependency_paths=[[binding_ref, a] for a in approvals], impact=impact,
                required_actions=[] if impact == "no_effect_original_scope" else ["Review exact new physical context and create a new binding/approval; do not inherit the old approval."],
                assessed_by=principal, assessment_method="exact_context_comparison",
                limitations=["An unchanged observed schema does not prove stable meaning or grant approval to a new snapshot."])
            return [verification, document], {"record_reference": reference(document)}
        result = self._run("assess_change", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def execute_metadata_command(self, operation, *, context, command_id, expected_head, payload, build):
        """Trusted in-process extension point; callbacks are never external input.

        Assessment components authorize their exact action/scope before scanning
        metadata, then reuse the same journal/transaction/replay machinery.
        """
        if operation not in ("submit_requirement", "register_prediction_evidence", "assess_requirement",
                             "propose_specification", "submit_specification_review", "decide_specification",
                             "retire_specification_approval", "validate_preparation_plan", "inspect_specification",
                             "request_preparation_execution", "authorize_preparation_execution", "begin_preparation_execution",
                             "record_preparation_operation", "finalize_preparation_execution", "interrupt_preparation_execution",
                             "revoke_preparation_execution",
                             "claim_preparation_worker", "guard_preparation_worker", "record_preparation_worker_receipt",
                             "fail_preparation_worker", "recover_preparation_worker", "scan_preparation_orphans",
                             "request_preparation_publication", "prepare_preparation_publication", "commit_preparation_publication",
                             "record_publication_recovery", "read_preparation_publication"):
            raise GovernanceError("unsupported_metadata_operation", "Unregistered metadata command operation.")
        return self._run(operation, context, command_id, expected_head, payload, build)

    def inspect_binding_use(self, binding_ref, *, scope, physical_field, now):
        """Internal metadata inspection, not access authorization or approval.

        Callers must already be authorized for the requested fields/purpose.
        This shares the existing semantic lifecycle with requirement assessment.
        """
        with self._journal.lock:
            binding = self.get(binding_ref)
            field = physical_field
            self._field(field)
            validate_scope(scope, self._catalogue.resolve)
            approvals = [a for a in self.records("ApprovalRecord") if a["approved_object_reference"] == binding_ref]
            compatible = [a for a in approvals if scope_contains(a["approval_scope"], scope)]
            if field_key(field) != field_key(binding["physical_field_reference"]):
                result = "needs_review"
            elif field_key(field) not in {field_key(f) for f in scope["field_references"]} or not scope_contains(binding["interpretation_scope"], scope):
                result = "access_denied"
            else:
                states = [self._approval_state(a, now) for a in compatible]
                result = "usable" if "usable" in states else next((s for s in
                    ("authority_unavailable", "needs_review", "conditions_unverified", "revoked", "superseded", "expired") if s in states), "not_approved")
                if result == "not_approved":
                    decisions = [d for d in self.records("BusinessReviewDecision")
                                 if d["subject_reference"] == binding_ref and scope_contains(d["decision_scope"], scope)]
                    if decisions and decisions[-1]["action"] in ("reject", "request_clarification"):
                        result = "rejected" if decisions[-1]["action"] == "reject" else "clarification_requested"
                if result == "usable":
                    for other in self.records("ApprovalRecord"):
                        if other["approved_object_reference"] == binding_ref:
                            continue
                        other_binding = self.get(other["approved_object_reference"])
                        if (field_key(other_binding["physical_field_reference"]) == field_key(field)
                                and scope_overlaps(other["approval_scope"], scope) and self._approval_state(other, now) == "usable"
                                and (other_binding["interpretation"] != binding["interpretation"] or other_binding["qualifiers"] != binding["qualifiers"])):
                            result = "conflict"
                            break
            return {"result": result, "approvals": approvals, "compatible_approvals": compatible}

    def assess_use(self, binding_ref, *, scope, physical_field, context, command_id, expected_head):
        payload = {"binding": binding_ref, "scope": scope, "physical_field": physical_field}
        def build(principal, context_ref, now):
            binding = self.get(binding_ref)
            field = physical_field
            self._field(field)
            validate_scope(scope, self._catalogue.resolve)
            verification, denied = self._authorization(context, "assess_use", binding_ref, scope, principal, now)
            if denied:
                return [verification], denied
            state = self.inspect_binding_use(binding_ref, scope=scope, physical_field=field, now=now)
            result, approvals, compatible = state["result"], state["approvals"], state["compatible_approvals"]
            changes = [reference(d) for d in self.records("BindingChangeAssessment") if d["binding_reference"] == binding_ref]
            deadlines = [now + timedelta(seconds=self._policy.assessment_ttl_seconds)]
            for approval in compatible:
                for bound in ("expires_at", "review_due_at"):
                    if approval[bound] and instant(approval[bound]) > now:
                        deadlines.append(instant(approval[bound]))
            lifecycle = {"usable": "approved", "conditions_unverified": "approved", "not_approved": "proposed"}.get(result, result)
            if lifecycle not in ("proposed", "approved", "rejected", "clarification_requested", "revoked", "superseded", "expired", "needs_review"):
                lifecycle = "blocked"
            conditions = [{"condition_id": c["condition_id"], "status": "unverified", "reason": "Trusted condition fulfillment is not implemented."}
                          for a in compatible for c in a["conditions"]]
            document = self._new("BindingUseAssessment", principal, scope["purpose"], now,
                evidence=binding["evidence_references"], dependencies=[binding_ref], binding_reference=binding_ref,
                candidate_approval_references=[reference(a) for a in approvals],
                requested_context={"scope": scope, "physical_field_reference": field, "caller_reference": principal},
                assessed_at=now.isoformat(), trusted_governance_head=self.head, authority_context_reference=context_ref,
                resolved_dependencies=[binding_ref, field["source_metadata_reference"], field["discovery_reference"]] + [reference(a) for a in compatible],
                condition_results=conditions, change_assessment_references=changes, result=result, lifecycle_state=lifecycle,
                reason_codes=[] if result == "usable" else [result],
                required_evidence_or_action=[] if result == "usable" else ["Resolve the recorded semantic/authority/context blocker; no execution is authorized."],
                valid_until=min(deadlines).isoformat(), recheck_triggers=["source_or_schema_change", "authority_change", "revocation", "expiry", "evidence_change"],
                assessment_receipt_reference=self._receipt())
            return [verification, document], {"record_reference": reference(document)}
        result = self._run("assess_use", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])
