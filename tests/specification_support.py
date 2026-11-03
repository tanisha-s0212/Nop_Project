"""Synthetic specification fixture; no original business source is read."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

from business_prediction.contracts import reference
from business_prediction.runtime.development import DevelopmentAuthorizationProvider
from tests.assessment_support import AssessmentFixture


class SpecificationFixture(AssessmentFixture):
    def __init__(self, directory, *, record_grain="source-record", **kwargs):
        super().__init__(directory, **kwargs)
        actions = {"author": ("propose_specification", "submit_specification_review"),
            "owner": ("approve_specification", "reject_specification", "request_clarification_specification",
                      "revoke_specification_approval", "supersede_specification_approval", "validate_preparation_plan")}
        self.grants = [replace(g, actions=g.actions+actions[g.principal_reference]) for g in self.grants]
        old = self.runtime.authority.authorization_provider
        self.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(self.grants, old._secrets, "env:KEY")
        if record_grain != self.scope["record_grain"]:
            self.scope["record_grain"] = record_grain
            self.grants = [replace(g, scope=deepcopy(self.scope)) for g in self.grants]
            self.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(self.grants, old._secrets, "env:KEY")
            self.target = self.bind(0, self.concept, "grain-target")
            self.input = self.bind(1, "context.new-grain", "grain-input")
            self.time = self.bind(2, "clock.new-grain", "grain-time")
        self.specs = self.runtime.specification_service()

    def propose(self, kind, fields, **changes):
        return self.specs.propose(kind, fields, scope=self.scope, evidence=self.target["evidence_references"],
            context=self.author, command_id=self.cmd(), expected_head=self.service.head, **changes)

    def review(self, subject, **changes):
        args = {"context": self.author, "command_id": self.cmd(), "expected_head": self.service.head,
                "expires_at": (self.now+timedelta(days=15)).isoformat(), "review_due_at": (self.now+timedelta(days=10)).isoformat()}
        args.update(changes)
        return self.specs.submit_review(reference(subject), **args)

    def decision(self, request, subject, action="approve", **changes):
        args = {"context": self.owner, "command_id": self.cmd(), "expected_head": self.service.head,
                "rationale": "Explicit synthetic owner review only."}
        args.update(changes)
        return self.specs.decide(reference(request), reference(subject), action=action, **args)

    def approve_spec(self, subject, **changes):
        result = self.decision(self.review(subject, **changes), subject)
        return self.specs.get(result["approval_reference"]) if result["approval_reference"] else None

    def target_fields(self, **changes):
        fields = {"requirement_reference": None, "business_meaning": self.target["interpretation"]["definition"],
            "semantic_binding_reference": reference(self.target), "physical_field_reference": self.fields[0],
            "target_grain": self.scope["record_grain"], "value_type": "boolean" if self.bundle.discovery_result["tables"][0]["fields"][0]["observed"]["type_counts"].get("boolean") else "float",
            "value_characteristics": {"interpretation": "Explicit synthetic numerical/label field; no primary key claim."},
            "eligibility": [], "inclusion_criteria": [], "exclusion_criteria": [],
            "historical_boundaries": {"start": "2026-01-01", "end": "2026-01-21", "calendar_reference": "synthetic-calendar"},
            "history_not_applicable_reason": None,
            "prediction_horizon": {"steps": 2, "unit": "day"}, "construction_requirements": None,
            "required_approvals": ["target_definition_and_eligibility"], "limitations": ["Synthetic reviewed specification, not training permission."]}
        fields.update(changes); return deepcopy(fields)

    def observation_fields(self, target, **changes):
        fields = {"target_reference": reference(target), "observation_grain": self.scope["record_grain"], "entity_binding_references": [],
            "time_binding_reference": reference(self.time), "time_basis": "Explicit synthetic observation time.",
            "time_not_applicable_reason": None,
            "observation_period": deepcopy(target["historical_boundaries"]), "eligibility": [], "expected_frequency": "day",
            "alignment": {"mode": "native", "definition": "One native source row per candidate observation; no identity/independence certification."},
            "historical_boundaries": deepcopy(target["historical_boundaries"]),
            "future_boundaries": {"start": "2026-01-21", "end": "2026-01-23", "calendar_reference": "synthetic-calendar"},
            "relationship_references": [], "required_approvals": ["observation_grain_and_time"], "limitations": ["No row alignment was executed."]}
        fields.update(changes); return deepcopy(fields)

    def operation(self, **changes):
        op = {"operation_id": "inspect-quality", "operation_type": "data_quality_validation", "operation_version": "1.0",
            "purpose": "Specify later quality checks without executing them.", "source_references": self.fields,
            "input_binding_references": [reference(self.target), reference(self.time), reference(self.input)],
            "parameters": {"checks": ["Count and reconcile rows, missing values, eligibility and temporal coverage."]},
            "input_grain": self.scope["record_grain"], "output_grain": self.scope["record_grain"], "depends_on": [], "assumptions": [],
            "evidence_references": self.target["evidence_references"], "risks": ["Declared checks have not run."],
            "required_approvals": ["bounded_preparation_policy"], "relationship_references": [],
            "information_role": "validation", "availability": "not_applicable"}
        op.update(changes); return deepcopy(op)

    def plan_fields(self, target, observation, **changes):
        fields = {"target_reference": reference(target), "observation_reference": reference(observation),
            "source_references": self.fields, "input_grain": self.scope["record_grain"], "output_grain": self.scope["record_grain"],
            "operations": [self.operation()], "relationship_references": [],
            "quality_checks": ["Verify immutable sources and before/after counts in a separately approved executor."],
            "leakage_controls": ["Permit only information available at the explicitly approved decision time."],
            "unresolved_decisions": [], "required_approvals": ["bounded_preparation_policy"], "limitations": ["No execution authorization."]}
        fields.update(changes); return deepcopy(fields)

    def base_specs(self):
        target = self.propose("PredictionTargetSpecification", self.target_fields()); self.approve_spec(target)
        observation = self.propose("ObservationSpecification", self.observation_fields(target)); self.approve_spec(observation)
        return target, observation

    def inspect(self, subject):
        return self.specs.inspect_for_review(reference(subject), context=self.owner, command_id=self.cmd(), expected_head=self.service.head)

    def validate(self, plan):
        return self.specs.validate_plan(reference(plan), context=self.owner, command_id=self.cmd(), expected_head=self.service.head)
