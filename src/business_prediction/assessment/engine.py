"""Authenticated, durable assessment of structured objectives and evidence.

No request text interpretation, source transformation, label generation, model
selection or performance estimation. External profilers supply attributed facts.
"""

from datetime import timedelta
from uuid import uuid4

from ..contracts import reference
from ..runtime.factory import AuthorizationFailure
from ..semantics.common import clone, digest, GovernanceError, instant, field_key, scope_contains
from ..semantics.contracts import validate_scope
from .intake import supplied, finding, intake_findings
from .relevance import DataRelevanceAssessor, narrow_scope
from .feasibility import FeasibilityEvaluator
from .target import TargetAssessor
from .strategies import default_strategies

REQUIREMENT_FIELDS = {"business_outcome", "target_description", "business_context", "organizational_context", "intent", "task_hint",
    "requested_concepts", "target_binding_reference", "time_binding_reference", "input_binding_references", "observation_granularity",
    "decision_time_basis", "history_requirements", "prediction_horizon", "desired_output", "construction_request", "constraints", "additional_context"}
FACT_FIELDS = {"time_binding_reference", "input_binding_references", "observation_grain", "observation_frequency",
    "observation_count", "nonmissing_count", "mature_observations", "history_start", "history_end", "class_counts",
    "target_observable", "grain_verified", "cadence_complete", "chronology_verified", "population_verified", "negative_outcomes_verified",
    "availability_verified", "validation_verified", "independence_verified", "input_mode", "leakage_findings", "limitations", "method_reference"}
FACT_FIELDS |= {"decision_time_basis", "validation_scheme", "label_horizon"}


class PredictionRequirementAssessmentEngine:
    def __init__(self, runtime, *, strategies=None):
        # Construction is through an explicit runtime, never a development fallback.
        from ..runtime.factory import FrameworkRuntime
        if not isinstance(runtime, FrameworkRuntime):
            raise GovernanceError("runtime_required", "Use an explicitly configured, startup-validated runtime.")
        runtime.config.validate()
        if runtime.config.mode == "production" and (runtime.authority.development_only or runtime.authority.test_only or not runtime.store.capabilities.production_approved):
            raise GovernanceError("unsafe_production_configuration", "Assessment cannot downgrade production security/storage.")
        self.runtime, self.service, self.catalogue = runtime, runtime.service, runtime.catalogue
        self.strategies = strategies if strategies is not None else default_strategies()
        self.relevance, self.feasibility = DataRelevanceAssessor(), FeasibilityEvaluator()
        self.target_assessor = TargetAssessor()

    def _new(self, kind, principal, scope, now, **body):
        return {"contract_type": kind, "contract_version": "1.0", "object_id": str(uuid4()), "object_revision": 1,
            "created_at": now.isoformat(), "owner_reference": principal, "purpose_scope": scope["purpose"],
            "assessment_scope": clone(scope), "dependency_versions": [], "evidence_references": [], **clone(body)}

    def _prove(self, context, action, subject_ref, scope, now):
        validate_scope(scope, self.catalogue.resolve)
        proof = self.runtime.authority.verify(context, action, subject_ref, scope, self.service._policy.reference(), now)
        if proof["verification_outcome"] != "verified":
            raise AuthorizationFailure("authority_denied" if proof["verification_outcome"] == "denied" else "authority_unavailable", proof)
        self.runtime.coordinator.audit_event("assessment.authorized", operation=action, authorization=proof)
        return proof

    def submit_requirement(self, fields, *, scope, context, command_id, expected_head, object_id=None, predecessor=None):
        if not isinstance(fields, dict) or set(fields) - REQUIREMENT_FIELDS:
            raise GovernanceError("invalid_requirement_fields", "Only declared structured requirement fields are accepted; envelope/approval fields are server-owned.")
        payload = {"fields": fields, "scope": scope, "object_id": object_id, "predecessor": predecessor}
        def build(principal, context_ref, now):
            prior = self.service.get(predecessor) if predecessor else None
            if prior and (prior["contract_type"] != "PredictionRequirementSpecification" or object_id is not None and prior["object_id"] != object_id):
                raise GovernanceError("wrong_version", "Requirement predecessor must belong to the same requirement lineage.")
            document = self._new("PredictionRequirementSpecification", principal, scope, now,
                object_id=prior["object_id"] if prior else object_id or str(uuid4()),
                object_revision=prior["object_revision"]+1 if prior else 1, predecessor_reference=predecessor, **fields)
            if any(d["object_id"] == document["object_id"] and d["object_revision"] >= document["object_revision"]
                   for d in self.service.records("PredictionRequirementSpecification")):
                raise GovernanceError("wrong_version", "An existing requirement revision cannot be replaced.")
            self._prove(context, "submit_requirement", reference(document), scope, now)
            self.catalogue.registry.validate(document, resolver=self.catalogue.resolve)
            return [document], {"record_reference": reference(document)}
        result = self.service.execute_metadata_command("submit_requirement", context=context, command_id=command_id,
            expected_head=expected_head, payload=payload, build=build)
        return self.service.get(result["record_reference"])

    def register_data_evidence(self, binding_ref, facts, *, scope, context, command_id, expected_head,
                               valid_until, supporting_evidence=()):
        if not isinstance(facts, dict) or set(facts) != FACT_FIELDS:
            raise GovernanceError("invalid_evidence_fields", "Supply the complete typed evidence summary; no missing facts are fabricated.")
        payload = {"binding": binding_ref, "facts": facts, "scope": scope, "valid_until": valid_until,
                   "supporting_evidence": list(supporting_evidence)}
        def build(principal, context_ref, now):
            binding = self.service.get(binding_ref)
            if binding["contract_type"] != "SemanticBinding":
                raise GovernanceError("wrong_subject_type", "Prediction evidence must identify a semantic binding.")
            field = binding["physical_field_reference"]
            document = self._new("PredictionDataEvidence", principal, scope, now, binding_reference=binding_ref,
                physical_field_reference=field, valid_until=valid_until, supporting_evidence_references=list(supporting_evidence), **facts)
            document["authorization"] = self._prove(context, "register_prediction_evidence", reference(document), scope, now)
            if instant(valid_until) <= now:
                raise GovernanceError("expired_evidence", "Evidence validity must extend beyond registration.")
            for ref in supporting_evidence:
                evidence = self.service.get(ref)
                if evidence["origin_verification"] != "verified_origin" or evidence["valid_until"] and now >= instant(evidence["valid_until"]):
                    raise GovernanceError("unverified_evidence", "Documentary support lacks current verified origin.")
            document["dependency_versions"] = [binding_ref, field["source_metadata_reference"], field["discovery_reference"]] + list(supporting_evidence)
            self.catalogue.registry.validate(document, resolver=self.catalogue.resolve)
            return [document], {"record_reference": reference(document)}
        result = self.service.execute_metadata_command("register_prediction_evidence", context=context, command_id=command_id,
            expected_head=expected_head, payload=payload, build=build)
        return self.service.get(result["record_reference"])

    def _data(self, requirement, candidate, now):
        valid, issues, excluded = [], [], []
        for ref in candidate["data_evidence_references"]:
            evidence = self.service.get(ref)
            if not scope_contains(requirement["assessment_scope"], evidence["assessment_scope"]):
                continue
            if now >= instant(evidence["valid_until"]):
                excluded.append(finding("expired_profile_evidence", "evidence", "Candidate evidence has expired.", candidate["binding_reference"]))
                continue
            if not self.runtime.authority.verify_record(evidence["authorization"], now):
                excluded.append(finding("unverified_profile_attribution", "evidence", "Evidence authority attribution could not be verified.", candidate["binding_reference"]))
                continue
            supporting_current = True
            for support in evidence["supporting_evidence_references"]:
                record = self.service.get(support)
                if record["origin_verification"] != "verified_origin" or record["valid_until"] and now >= instant(record["valid_until"]):
                    supporting_current = False
            if not supporting_current:
                excluded.append(finding("expired_supporting_evidence", "evidence", "A supporting evidence dependency is no longer valid.", candidate["binding_reference"]))
                continue
            valid.append(evidence)
        # Select by the requested technical contract, never by recency or wording.
        applicable = []
        for evidence in valid:
            if any(supplied(requirement, key) is not None and requirement[key] != evidence[key]
                   for key in ("input_binding_references", "time_binding_reference", "decision_time_basis")):
                continue
            applicable.append(evidence)
        if applicable:
            valid = applicable
        if not valid:
            issues.extend(excluded)
        if len({digest({key: e[key] for key in FACT_FIELDS}) for e in valid}) > 1:
            issues.append(finding("conflicting_profile_evidence", "evidence", "Current evidence summaries conflict; no newest/largest profile wins.", candidate["binding_reference"]))
            return None, valid, issues
        return valid[0] if valid else None, valid, issues

    def assess(self, requirement_ref, *, context, command_id, expected_head):
        payload = {"requirement": requirement_ref, "strategy_versions": self.strategies.versions()}
        def build(principal, context_ref, now):
            requirement = self.service.get(requirement_ref)
            if requirement["contract_type"] != "PredictionRequirementSpecification":
                raise GovernanceError("wrong_subject_type", "Assessment requires an exact requirement revision.")
            scope = requirement["assessment_scope"]
            self._prove(context, "assess_requirement", requirement_ref, scope, now)
            self.catalogue.registry.validate(requirement, resolver=self.catalogue.resolve)
            issues = intake_findings(requirement)
            strategy, strategy_issues = self.strategies.select(requirement)
            issues.extend(strategy_issues)
            candidates = self.relevance.candidates(requirement, self.service, self.catalogue, now)
            target_state = self.target_assessor.assess(requirement, candidates, self.relevance, self.service)
            selected = target_state["selected"]
            issues.extend(target_state["findings"])
            risks, construction, valid_data = [], target_state["construction_requirements"], []
            if selected is not None:
                data, valid_data, data_issues = self._data(requirement, selected, now)
                issues.extend(data_issues)
                checks, risks, extra_construction = self.feasibility.evaluate(requirement, selected, strategy, data, self.service, now)
                construction.extend(extra_construction)
                issues.extend(checks)
            target = self._new("TargetAssessment", principal, scope, now, requirement_reference=requirement_ref,
                problem_type=strategy.problem_type if strategy else "undetermined", strategy_reference=(strategy.problem_type+"@"+strategy.version) if strategy else None,
                candidates=candidates, selected_binding_reference=selected["binding_reference"] if selected else None,
                construction_requirements=construction,
                limitations=["Candidates are evidence bindings, never computed targets or business approvals.",
                             "Free text is retained but not interpreted by an LLM or a question catalogue."])
            categories = {i["category"] for i in issues}
            status = next((state for category, state in (("unsupported", "unsupported"), ("clarification", "clarification_required"),
                ("approval", "approval_blocked"), ("evidence", "insufficient_evidence")) if category in categories),
                "analytics_only" if strategy and strategy.work_type == "analytics" else "ready_for_preparation_review")
            binding_dependencies = ([selected["binding_reference"]] if selected and selected["binding_reference"] else [])
            for profile in valid_data:
                binding_dependencies += profile["input_binding_references"] + ([profile["time_binding_reference"]] if profile["time_binding_reference"] else [])
            approval_dependencies = [a for a in self.service.records("ApprovalRecord") if a["approved_object_reference"] in binding_dependencies]
            deadlines = [now+timedelta(seconds=60)] + [instant(e["valid_until"]) for e in valid_data]
            for approval in approval_dependencies:
                deadlines += [instant(approval[k]) for k in ("expires_at", "review_due_at") if approval[k] and instant(approval[k]) > now]
            result = self._new("FeasibilityReadinessAssessment", principal, scope, now,
                requirement_reference=requirement_ref, target_assessment_reference=reference(target), status=status,
                work_type=strategy.work_type if strategy else "unsupported" if "unsupported" in categories else "undetermined",
                blocking_findings=issues, risks=sorted(set(risks)),
                missing_information=[i["code"] for i in issues if i["category"] in ("clarification", "evidence")],
                required_approvals=[i["code"] for i in issues if i["category"] == "approval"],
                clarification_requirements=[i["message"] for i in issues if i["category"] == "clarification"],
                recommended_next_action={"ready_for_preparation_review": "Review a target-specific preparation/validation specification and obtain separate execution approval.",
                    "analytics_only": "Use an authorized historical analytical calculation path; no ML is required by these characteristics.",
                    "clarification_required": "Resolve the necessary structured requirement ambiguities.", "approval_blocked": "Resolve exact-scope semantic/treatment approvals without altering the source data.",
                    "insufficient_evidence": "Obtain missing source/profile/label/history/availability evidence and reassess.", "unsupported": "Explain the unsupported characteristics or register an appropriate evidence-based assessment extension."}[status],
                limitations=["Assessment readiness is not data preparation, training authorization or evidence of future model performance.",
                    "External profiling summaries are authorized attestations checked for metadata consistency, not independently recomputed raw-data facts.",
                    "No source join, parsing correction, aggregation, label, feature, algorithm or metric is generated."] + [x for e in valid_data for x in e["limitations"]],
                supporting_evidence_references=[reference(e) for e in valid_data], execution_authorized=False, performance_estimated=False,
                assessed_at=now.isoformat(), valid_until=min(deadlines).isoformat(),
                governance_head=self.service.head)
            target["dependency_versions"] = [requirement_ref] + binding_dependencies + [reference(a) for a in approval_dependencies]
            result["dependency_versions"] = [requirement_ref, reference(target)] + [reference(e) for e in valid_data] + [reference(a) for a in approval_dependencies]
            return [target, result], {"target_assessment_reference": reference(target), "assessment_reference": reference(result)}
        outcome = self.service.execute_metadata_command("assess_requirement", context=context, command_id=command_id,
            expected_head=expected_head, payload=payload, build=build)
        return self.service.get(outcome["assessment_reference"])

    def get(self, ref):
        """Trusted-backend exact-history read; external read ACLs remain required."""
        return self.service.get(ref)
