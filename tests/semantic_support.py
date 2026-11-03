"""Synthetic-only fixtures for the explicitly non-production governance layer."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from business_prediction.catalogue import MetadataCatalogue
from business_prediction.contracts import reference
from business_prediction.semantics import semantic_registry, SemanticApprovalService, ReviewPolicy
from business_prediction.semantics.testing_authority import LocalTestAuthorityProvider
from tests.support import bundle


def evidence_ref(kind, **values):
    return {"kind": kind, "discovery_reference": None, "evidence_id": None, "field_id": None,
            "hypothesis_id": None, "record_reference": None, "binding_reference": None, "approval_reference": None, **values}


class Fixture:
    def __init__(self, **policy_options):
        self.now = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
        self.catalogue = MetadataCatalogue(semantic_registry())
        self.bundle = bundle(); self.bundle.publish(self.catalogue)
        self.provider = LocalTestAuthorityProvider(test_mode=True)
        self.author = self.provider.test_session("test-proposer")
        self.owner = self.provider.test_session("test-owner")
        self.second = self.provider.test_session("test-second-owner")
        self.intruder = self.provider.test_session("test-unprivileged")
        self.service = SemanticApprovalService(self.catalogue, self.provider,
            ReviewPolicy("synthetic-policy", "1", **policy_options), allow_test_authority=True, clock=lambda: self.now)
        self.field = self.service.physical_field_reference(reference(self.bundle.discovery_result), "table-1", "table-1:field-1")
        self.scope = {"purpose": "unit-test", "namespace": "synthetic-namespace", "record_grain": "synthetic-record",
            "assertion_use": "semantic_interpretation", "field_references": [self.field],
            "business_period": None, "period_not_applicable_reason": "Synthetic fixture has no asserted business period."}
        self.evidence = [evidence_ref("observation", discovery_reference=reference(self.bundle.discovery_result),
            field_id="table-1:field-1", evidence_id="table-1:field-1:profile")]
        self.counter = 0
        self.owner_grant = self.grant(self.scope, "test-owner")
        self.grant(self.scope, "test-second-owner")

    def grant(self, scope, principal="test-owner", actions=None):
        return self.provider.test_grant(principal, actions or
            ("approve", "reject", "request_clarification", "revoke", "supersede", "assess_use", "assess_change"), scope,
            valid_from=(self.now-timedelta(days=1)).isoformat(), valid_until=(self.now+timedelta(days=100)).isoformat())

    def cmd(self):
        self.counter += 1
        return "test-command-"+str(self.counter)

    def propose(self, object_id="binding", **kwargs):
        params = {"object_id": object_id, "physical_field_reference": self.field,
            "interpretation": {"concept": "synthetic-concept", "definition": "Explicit proposed meaning for a synthetic field.",
                               "definition_version": "1", "definition_reference": None},
            "scope": self.scope, "evidence": self.evidence, "context": self.author,
            "command_id": self.cmd(), "expected_head": self.service.head}
        params.update(kwargs)
        return self.service.propose_binding(**params)

    def review(self, subject, **kwargs):
        scope = subject.get("interpretation_scope", subject.get("approval_scope"))
        params = {"scope": scope, "context": self.author, "command_id": self.cmd(), "expected_head": self.service.head}
        if subject["contract_type"] == "SemanticBinding":
            params.update(expires_at=(self.now+timedelta(days=7)).isoformat(), review_due_at=(self.now+timedelta(days=5)).isoformat())
        params.update(kwargs)
        return self.service.submit_review(reference(subject), **params)

    def decide(self, request, action="approve", **kwargs):
        params = {"action": action, "context": self.owner, "rationale": "Explicit synthetic owner decision.",
                  "command_id": self.cmd(), "expected_head": self.service.head}
        params.update(kwargs)
        return self.service.decide(reference(request), request["subject_reference"], **params)

    def approve(self, binding=None, **review_options):
        binding = binding or self.propose()
        request = self.review(binding, **review_options)
        result = self.decide(request)
        return binding, self.service.get(result["approval_reference"])

    def use(self, binding, **kwargs):
        params = {"scope": binding["interpretation_scope"], "context": self.owner,
                  "physical_field": binding["physical_field_reference"],
                  "command_id": self.cmd(), "expected_head": self.service.head}
        params.update(kwargs)
        return self.service.assess_use(reference(binding), **params)
