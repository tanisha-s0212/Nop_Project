"""Durable specification proposals, explicit reviews and validation snapshots."""

from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

from ..contracts import reference
from ..runtime.factory import AuthorizationFailure
from ..semantics.common import clone, digest, GovernanceError, instant
from .contracts import SPECIFICATION_TYPES
from .operations import default_operation_registry
from .validation import PreparationPlanValidator


def exact_references(value):
    """Collect pinned dependencies, never infer a latest revision."""
    if isinstance(value, dict):
        if set(value) == {"contract_type", "contract_version", "object_id", "object_revision"}:
            yield value
        else:
            for child in value.values(): yield from exact_references(child)
    elif isinstance(value, list):
        for child in value: yield from exact_references(child)


class SpecificationService:
    def __init__(self, runtime, *, operations=None):
        from ..runtime.factory import FrameworkRuntime
        if not isinstance(runtime, FrameworkRuntime):
            raise GovernanceError("runtime_required", "Use an explicitly configured, startup-validated runtime.")
        runtime.config.validate()
        if runtime.config.mode == "production" and (runtime.authority.development_only or runtime.authority.test_only or not runtime.store.capabilities.production_approved):
            raise GovernanceError("unsafe_production_configuration", "Specifications cannot downgrade production security or persistence.")
        self.runtime, self.service = runtime, runtime.service
        self.operations = operations if operations is not None else default_operation_registry()
        self.validator = PreparationPlanValidator(self.operations)

    def _new(self, kind, principal, scope, now, **body):
        return {"contract_type": kind, "contract_version": "1.0", "object_id": str(uuid4()), "object_revision": 1,
            "owner_reference": principal, "created_at": now.isoformat(), "purpose_scope": scope["purpose"],
            "specification_scope": clone(scope), "evidence_references": [], "dependency_versions": [], **clone(body)}

    def _authorize(self, context, action, ref, scope, now):
        proof = self.runtime.authority.verify(context, action, ref, scope, self.service._policy.reference(), now)
        if proof["verification_outcome"] != "verified":
            raise AuthorizationFailure("authority_denied" if proof["verification_outcome"] == "denied" else "authority_unavailable", proof)
        if not self.runtime.authority.verify_record(proof, now):
            raise GovernanceError("authority_unavailable", "The exact scoped authority receipt cannot be verified.")
        self.runtime.coordinator.audit_event("specification.authorized", operation=action, authorization=proof)
        return proof

    def _command(self, operation, context, command_id, expected_head, payload, build):
        return self.service.execute_metadata_command(operation, context=context, command_id=command_id,
            expected_head=expected_head, payload=payload, build=build)

    def propose(self, kind, fields, *, scope, evidence, context, command_id, expected_head,
                object_id=None, predecessor=None):
        """Create a proposal only. Required approval labels convey no authority."""
        reserved = {"contract_type", "contract_version", "object_id", "object_revision", "owner_reference", "created_at",
                    "purpose_scope", "specification_scope", "evidence_references", "dependency_versions", "predecessor_reference"}
        if kind not in SPECIFICATION_TYPES or not isinstance(fields, dict) or set(fields) & reserved:
            raise GovernanceError("invalid_specification_fields", "Supply a supported specification body; provenance/version fields are server-owned.")
        payload = {"kind": kind, "fields": fields, "scope": scope, "evidence": evidence,
                   "object_id": object_id, "predecessor": predecessor}
        def build(principal, context_ref, now):
            prior = self.service.get(predecessor) if predecessor else None
            if prior and (prior["contract_type"] != kind or object_id is not None and prior["object_id"] != object_id):
                raise GovernanceError("wrong_version", "Predecessor must be an exact revision of the same specification lineage.")
            document = self._new(kind, principal, scope, now, **fields)
            document.update(object_id=prior["object_id"] if prior else object_id or document["object_id"],
                object_revision=prior["object_revision"]+1 if prior else 1, predecessor_reference=predecessor,
                evidence_references=clone(evidence))
            self._authorize(context, "propose_specification", reference(document), scope, now)
            if any(d["object_id"] == document["object_id"] and d["object_revision"] >= document["object_revision"] for d in self.service.records(kind)):
                raise GovernanceError("wrong_version", "A specification revision cannot be replaced or forked from an outdated revision.")
            dependencies = list(exact_references(fields)) + list(exact_references(evidence)) + ([predecessor] if predecessor else [])
            document["dependency_versions"] = list({digest(r): r for r in dependencies}.values())
            self.runtime.catalogue.registry.validate(document, resolver=self.runtime.catalogue.resolve)
            return [document], {"record_reference": reference(document)}
        result = self._command("propose_specification", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def submit_review(self, subject_ref, *, context, command_id, expected_head, expires_at, review_due_at,
                      conditions=(), limitations=()):
        payload = {"subject": subject_ref, "expires_at": expires_at, "review_due_at": review_due_at,
                   "conditions": list(conditions), "limitations": list(limitations)}
        def build(principal, context_ref, now):
            subject = self.get(subject_ref)
            if subject["contract_type"] not in SPECIFICATION_TYPES:
                raise GovernanceError("wrong_subject_type", "Only exact specification revisions can be submitted for business review.")
            scope = subject["specification_scope"]
            self._authorize(context, "submit_specification_review", subject_ref, scope, now)
            request = self._new("SpecificationReviewRequest", principal, scope, now,
                subject_reference=subject_ref, subject_digest=digest(subject), approval_requirements=subject["required_approvals"],
                expires_at=expires_at, review_due_at=review_due_at, conditions=list(conditions), limitations=list(limitations),
                policy_reference={**self.service._policy.reference(), "policy_digest": digest(asdict(self.service._policy))},
                evidence_references=subject["evidence_references"], dependency_versions=[subject_ref])
            self.runtime.catalogue.registry.validate(request, resolver=self.runtime.catalogue.resolve)
            return [request], {"record_reference": reference(request)}
        result = self._command("submit_specification_review", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def _retirement(self, approval_ref):
        return next((d["action"] for d in self.service.records("SpecificationReviewDecision")
                     if d["affected_approval_reference"] == approval_ref), None)

    def _approval_status(self, approval, now):
        retired = self._retirement(reference(approval))
        if retired: return "revoked" if retired == "revoke" else "superseded"
        if now >= min(instant(approval["expires_at"]), instant(approval["review_due_at"])): return "expired"
        if approval["conditions"]: return "conditions_unverified"
        request = self.get(approval["review_request_reference"])
        if request["policy_reference"]["policy_digest"] != digest(asdict(self.service._policy)): return "needs_review"
        decisions = [self.get(r) for r in approval["decision_references"]]
        if any(not self.runtime.authority.verify_record(d["authorization"], now) for d in decisions): return "authority_unavailable"
        if self.service._policy.continuing_authority and any(not self.runtime.authority.verify_continuing_authority(d["authorization"], now) for d in decisions):
            return "needs_review"
        return "approved"

    def specification_state(self, subject_ref, now):
        """Trusted-backend projection, not authorization or a lasting approval token."""
        with self.service._journal.lock:
            approvals = [a for a in self.service.records("SpecificationApprovalRecord") if a["approved_object_reference"] == subject_ref]
            states = [self._approval_status(approval, now) for approval in approvals]
            # Conflicting active review terms do not select an arbitrary approval.
            current = [a for a, state in zip(approvals, states) if state == "approved"]
            if len({digest({k:a[k] for k in ("conditions", "limitations", "approval_requirements")}) for a in current}) > 1:
                state = "conflict"
            elif "approved" in states: state = "approved"
            elif states: state = states[-1]
            else:
                decisions = [d for d in self.service.records("SpecificationReviewDecision") if d["subject_reference"] == subject_ref]
                last = decisions[-1]["action"] if decisions else None
                state = {"reject": "rejected", "request_clarification": "clarification_requested"}.get(last, "proposed")
            return {"state": state, "approval_references": [reference(a) for a in approvals]}

    def decide(self, request_ref, subject_ref, *, action, context, command_id, expected_head, rationale):
        if action not in ("approve", "reject", "request_clarification"):
            raise GovernanceError("invalid_action", "Use explicit review or retirement actions.")
        payload = {"request": request_ref, "subject": subject_ref, "action": action, "rationale": rationale,
                   "validator_versions": self.operations.versions()}
        def build(principal, context_ref, now):
            request = self.get(request_ref)
            if request["contract_type"] != "SpecificationReviewRequest" or request["subject_reference"] != subject_ref:
                raise GovernanceError("wrong_version", "Decision requires the review's exact frozen subject revision.")
            subject = self.get(subject_ref); scope = subject["specification_scope"]
            proof = self._authorize(context, action+"_specification", subject_ref, scope, now)
            if request["policy_reference"]["policy_digest"] != digest(asdict(self.service._policy)):
                raise GovernanceError("policy_changed", "The frozen review policy differs; submit a new review.")
            if now >= min(instant(request["expires_at"]), instant(request["review_due_at"])):
                raise GovernanceError("review_expired", "Frozen review terms have expired.")
            voters = [d for d in self.service.records("SpecificationReviewDecision") if d["review_request_reference"] == request_ref]
            if any(d["action"] in ("reject", "request_clarification") for d in voters) or any(a["review_request_reference"] == request_ref for a in self.service.records("SpecificationApprovalRecord")):
                raise GovernanceError("review_closed", "Completed review history cannot be reopened; submit a new review.")
            if any(d["owner_reference"] == principal for d in voters):
                raise GovernanceError("duplicate_reviewer", "Each authenticated reviewer may decide once per request.")
            if self.service._policy.independent_review and principal in (subject["owner_reference"], request["owner_reference"]):
                raise GovernanceError("independent_review_required", "A proposer/submitter cannot approve or review their own specification.")
            if action == "approve":
                checked = self.validator.inspect(subject, self, now, require_approval=False)
                if checked["findings"]:
                    raise GovernanceError("specification_not_approvable", "Resolve structured specification-validation findings before approval.")
                if any(not self.runtime.authority.verify_record(d["authorization"], now) for d in voters):
                    raise GovernanceError("authority_unavailable", "Earlier votes lack verifiable authority receipts.")
            decision = self._new("SpecificationReviewDecision", principal, scope, now,
                review_request_reference=request_ref, subject_reference=subject_ref, subject_digest=digest(subject), action=action,
                authorization=proof, rationale=rationale, decided_at=now.isoformat(), affected_approval_reference=None,
                replacement_approval_reference=None, dependency_versions=[request_ref, subject_ref], evidence_references=subject["evidence_references"])
            docs, approval = [decision], None
            voters.append(decision)
            if action == "approve" and len(voters) >= self.service._policy.minimum_approvers:
                approval = self._new("SpecificationApprovalRecord", principal, scope, now,
                    approved_object_reference=subject_ref, approved_object_digest=digest(subject), review_request_reference=request_ref,
                    decision_references=[reference(v) for v in voters], approver_references=[v["owner_reference"] for v in voters],
                    approval_requirements=subject["required_approvals"],
                    **{k: request[k] for k in ("expires_at", "review_due_at", "conditions", "limitations")},
                    execution_authorized=False, evidence_references=subject["evidence_references"],
                    dependency_versions=[subject_ref, request_ref]+[reference(v) for v in voters])
                docs.append(approval)
            return docs, {"decision_reference": reference(decision), "approval_reference": reference(approval) if approval else None}
        return self._command("decide_specification", context, command_id, expected_head, payload, build)

    def retire(self, approval_ref, *, action, rationale, context, command_id, expected_head, replacement=None):
        if action not in ("revoke", "supersede"):
            raise GovernanceError("invalid_action", "Retirement requires revoke or supersede.")
        payload = {"approval": approval_ref, "action": action, "rationale": rationale, "replacement": replacement}
        def build(principal, context_ref, now):
            approval = self.get(approval_ref)
            if approval["contract_type"] != "SpecificationApprovalRecord":
                raise GovernanceError("wrong_subject_type", "Retire an exact specification approval, not a proposal or semantic approval.")
            scope = approval["specification_scope"]
            proof = self._authorize(context, action+"_specification_approval", approval_ref, scope, now)
            if self._retirement(approval_ref): raise GovernanceError("approval_retired", "A retired approval cannot be retired again or revived.")
            if action == "supersede":
                if replacement is None or replacement == approval_ref:
                    raise GovernanceError("invalid_replacement", "Supersession needs an independently approved replacement.")
                new = self.get(replacement); subject = self.get(new["approved_object_reference"])
                prior = self.get(approval["approved_object_reference"])
                if (new["contract_type"] != "SpecificationApprovalRecord" or subject["contract_type"] != prior["contract_type"] or
                        subject["object_id"] != prior["object_id"] or new["specification_scope"] != scope or
                        self._approval_status(new, now) != "approved" or self.specification_state(reference(subject), now)["state"] != "approved" or
                        now >= min(instant(new["expires_at"]), instant(new["review_due_at"]))):
                    raise GovernanceError("invalid_replacement", "Replacement must be a currently approved compatible exact lineage/scope revision.")
                if self.validator.inspect(subject, self, now, require_approval=False)["findings"]:
                    raise GovernanceError("invalid_replacement", "Replacement dependencies no longer pass current specification validation.")
            elif replacement is not None:
                raise GovernanceError("invalid_replacement", "Revocation cannot silently install a replacement.")
            decision = self._new("SpecificationReviewDecision", principal, scope, now,
                review_request_reference=approval["review_request_reference"], subject_reference=approval["approved_object_reference"],
                subject_digest=approval["approved_object_digest"], action=action, authorization=proof, rationale=rationale,
                decided_at=now.isoformat(), affected_approval_reference=approval_ref, replacement_approval_reference=replacement,
                dependency_versions=[approval_ref]+([replacement] if replacement else []), evidence_references=approval["evidence_references"])
            return [decision], {"decision_reference": reference(decision)}
        return self._command("retire_specification_approval", context, command_id, expected_head, payload, build)

    def validate_plan(self, plan_ref, *, context, command_id, expected_head):
        payload = {"plan": plan_ref, "validator_versions": self.operations.versions()}
        def build(principal, context_ref, now):
            plan = self.get(plan_ref)
            if plan["contract_type"] != "DataPreparationPlanSpecification":
                raise GovernanceError("wrong_subject_type", "Plan validation requires an exact preparation-plan revision.")
            scope = plan["specification_scope"]
            self._authorize(context, "validate_preparation_plan", plan_ref, scope, now)
            checked = self.validator.inspect(plan, self, now)
            approvals = checked["approval_references"]
            deadlines = [now+timedelta(seconds=self.service._policy.assessment_ttl_seconds)]
            for ref in approvals:
                approval = self.get(ref)
                deadlines += [instant(approval[k]) for k in ("expires_at", "review_due_at") if approval.get(k) and instant(approval[k]) > now]
            valid = not checked["findings"]
            document = self._new("PreparationPlanValidation", principal, scope, now, plan_reference=plan_ref,
                valid_specification=valid, status="valid_specification" if valid else "blocked", **checked,
                validator_versions=self.operations.versions(), assessed_at=now.isoformat(), valid_until=min(deadlines).isoformat(),
                governance_head=self.service.head, execution_authorized=False,
                limitations=["A point-in-time specification review, not execution authorization or proof of prepared data quality.",
                    "No operation, join, aggregation, condition, target or feature was executed.",
                    "Business rules, eligibility and relationship claims are accountable owner assertions; raw outcomes are not independently recalculated."],
                dependency_versions=[plan_ref]+approvals)
            return [document], {"record_reference": reference(document)}
        result = self._command("validate_preparation_plan", context, command_id, expected_head, payload, build)
        return self.get(result["record_reference"])

    def inspect_for_review(self, subject_ref, *, context, command_id, expected_head):
        """Persist an authorized review diagnosis for any specification type."""
        payload = {"subject": subject_ref, "validator_versions": self.operations.versions()}
        def build(principal, context_ref, now):
            subject = self.get(subject_ref)
            if subject["contract_type"] not in SPECIFICATION_TYPES:
                raise GovernanceError("wrong_subject_type", "Inspect a specification revision.")
            self._authorize(context, "validate_preparation_plan", subject_ref, subject["specification_scope"], now)
            findings = self.validator.inspect(subject, self, now, require_approval=False)
            # Findings are durably bound to this idempotent command's outcome.
            return [], {"subject_reference": subject_ref, "assessed_at": now.isoformat(),
                        "governance_head": self.service.head, "execution_authorized": False, **findings}
        return self._command("inspect_specification", context, command_id, expected_head, payload, build)

    def get(self, ref):
        """Trusted in-process exact-history read; an external API needs read ACLs."""
        return self.service.get(ref)
