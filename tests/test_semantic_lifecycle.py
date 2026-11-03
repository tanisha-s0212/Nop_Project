from copy import deepcopy
from datetime import timedelta
import json
import unittest

from business_prediction.contracts import reference
from business_prediction.errors import FrameworkError
from business_prediction.semantics.common import GovernanceError
from business_prediction.semantics.service import SemanticApprovalService, ReviewPolicy
from business_prediction.semantics.testing_authority import LocalTestAuthorityProvider
from tests.semantic_support import Fixture, evidence_ref
from tests.support import bundle


class SemanticLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def assertCode(self, code, fn):
        with self.assertRaises(FrameworkError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        json.dumps(caught.exception.to_dict())

    def test_proposed_and_versioned_bindings_preserve_discovery(self):
        original = deepcopy(self.f.bundle.discovery_result)
        first = self.f.propose()
        second = self.f.propose(predecessor=reference(first), limitations=["New explicit limitation."])
        self.assertEqual((first["object_revision"], second["object_revision"]), (1, 2))
        self.assertEqual(first["proposal_state"], "proposed")
        self.assertEqual(self.f.use(second)["lifecycle_state"], "proposed")
        self.assertEqual(self.f.catalogue.get(reference(original)), original)
        self.assertEqual(self.f.service.get(reference(first)), first)

    def test_new_revision_requires_current_predecessor(self):
        first = self.f.propose()
        self.assertCode("wrong_version", lambda: self.f.propose())
        self.f.propose(predecessor=reference(first))
        self.assertCode("wrong_version", lambda: self.f.propose(predecessor=reference(first)))

    def test_explicit_approval_and_current_use(self):
        binding, approval = self.f.approve()
        assessment = self.f.use(binding)
        self.assertEqual((assessment["result"], assessment["lifecycle_state"]), ("usable", "approved"))
        self.assertEqual(approval["approved_object_reference"], reference(binding))
        self.assertEqual(binding["proposal_state"], "proposed")
        self.assertEqual(self.f.service.records("AuthorityVerificationRecord")[0]["principal_reference"], "test-owner")

    def test_rejection_is_retained_and_new_request_can_be_approved(self):
        binding = self.f.propose(); req = self.f.review(binding)
        result = self.f.decide(req, "reject")
        self.assertIsNone(result["approval_reference"])
        self.assertEqual(self.f.use(binding)["result"], "rejected")
        new_req = self.f.review(binding, predecessor_request=reference(req), resubmission_reason="Explicit appeal with unchanged object.")
        self.f.decide(new_req)
        self.assertEqual(self.f.use(binding)["result"], "usable")
        self.assertEqual(self.f.service.get(result["decision_reference"])["action"], "reject")

    def test_clarification_does_not_approve_and_closes_request(self):
        binding = self.f.propose(); req = self.f.review(binding)
        self.f.decide(req, "request_clarification")
        self.assertEqual(self.f.use(binding)["result"], "clarification_requested")
        self.assertCode("review_closed", lambda: self.f.decide(req))
        self.assertEqual(self.f.service.records("ApprovalRecord"), [])

    def test_unauthorized_decision_records_failed_verification_only(self):
        binding = self.f.propose(); req = self.f.review(binding)
        self.assertCode("authority_denied", lambda: self.f.decide(req, context=self.f.intruder))
        self.assertEqual(self.f.service.records("ApprovalRecord"), [])
        self.assertEqual(self.f.service.records("BusinessReviewDecision"), [])
        self.assertEqual(self.f.service.records("AuthorityVerificationRecord")[-1]["verification_outcome"], "denied")

    def test_owner_label_is_not_authenticated_context(self):
        binding = self.f.propose(); req = self.f.review(binding)
        self.assertCode("unverified_principal", lambda: self.f.decide(req, context="test-owner"))

    def test_wrong_binding_revision_cannot_use_old_review(self):
        first = self.f.propose(); req = self.f.review(first)
        second = self.f.propose(predecessor=reference(first))
        self.assertCode("wrong_version", lambda: self.f.service.decide(reference(req), reference(second), action="approve",
            context=self.f.owner, rationale="Wrong exact version", command_id=self.f.cmd(), expected_head=self.f.service.head))
        self.assertEqual(self.f.service.records("ApprovalRecord"), [])

    def test_revocation_preserves_original_approval(self):
        binding, approval = self.f.approve()
        req = self.f.review(approval); self.f.decide(req, "revoke")
        self.assertEqual(self.f.use(binding)["result"], "revoked")
        self.assertEqual(self.f.service.get(reference(approval)), approval)
        self.assertEqual(approval["record_state"], "issued")

    def test_supersession_and_replacement_revocation_never_revive_old(self):
        first, approval = self.f.approve()
        second = self.f.propose(predecessor=reference(first))
        _, replacement = self.f.approve(second)
        retirement = self.f.review(approval)
        self.f.decide(retirement, "supersede", replacement_approval=reference(replacement))
        self.assertEqual(self.f.use(first)["result"], "superseded")
        self.assertEqual(self.f.use(second)["result"], "usable")
        revocation = self.f.review(replacement); self.f.decide(revocation, "revoke")
        self.assertEqual(self.f.use(second)["result"], "revoked")
        self.assertEqual(self.f.use(first)["result"], "superseded")

    def test_supersession_requires_valid_distinct_replacement(self):
        binding, approval = self.f.approve(); req = self.f.review(approval)
        self.assertCode("invalid_replacement", lambda: self.f.decide(req, "supersede", replacement_approval=reference(approval)))

    def test_scope_and_purpose_cannot_be_expanded(self):
        binding = self.f.propose()
        scope = deepcopy(self.f.scope); scope["purpose"] = "different-purpose"
        self.assertCode("scope_mismatch", lambda: self.f.review(binding, scope=scope))

    def test_same_schema_new_fingerprint_does_not_inherit_approval(self):
        binding, approval = self.f.approve()
        newer = bundle((("opaque", "measure"), ("C", 3), ("D", 4)), revision=2)
        newer.publish(self.f.catalogue)
        self.assertEqual(newer.discovery_result["schema_version"], self.f.bundle.discovery_result["schema_version"])
        new_field = self.f.service.physical_field_reference(reference(newer.discovery_result), "table-1", "table-1:field-1")
        changed = self.f.service.assess_change(reference(binding), reference(newer.discovery_result), context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertEqual(changed["impact"], "review_required")
        scope = deepcopy(self.f.scope); scope["field_references"] = [new_field]; self.f.grant(scope)
        self.assertEqual(self.f.use(binding, scope=scope, physical_field=new_field)["result"], "needs_review")
        self.assertEqual(self.f.use(binding)["result"], "usable")
        self.assertEqual(self.f.service.get(reference(approval)), approval)

    def test_header_reordering_is_incompatible_not_a_rebind(self):
        binding = self.f.propose()
        newer = bundle((("measure", "opaque"), (1, "A"), (2, "B")), revision=2); newer.publish(self.f.catalogue)
        assessment = self.f.service.assess_change(reference(binding), reference(newer.discovery_result), context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        self.assertEqual(assessment["impact"], "incompatible")
        self.assertEqual(binding["physical_field_reference"]["field_position"], 1)

    def test_expiry_and_review_due_are_enforced(self):
        binding, approval = self.f.approve(review_due_at=(self.f.now+timedelta(hours=1)).isoformat())
        self.f.now += timedelta(hours=1)
        self.assertEqual(self.f.use(binding)["result"], "expired")

    def test_conditions_are_never_assumed_fulfilled(self):
        condition = {"condition_id": "synthetic-condition", "definition": "Requires a later trusted attestation.",
                     "evaluation_method": "trusted_attestation_required", "evidence_references": []}
        binding, approval = self.f.approve(conditions=[condition])
        result = self.f.use(binding)
        self.assertEqual((result["result"], result["lifecycle_state"]), ("conditions_unverified", "approved"))

    def test_quorum_distinct_reviewers_and_frozen_terms(self):
        f = Fixture(minimum_approvers=2)
        binding = f.propose(); req = f.review(binding)
        self.assertIsNone(f.decide(req)["approval_reference"])
        self.assertEqual(f.use(binding)["result"], "not_approved")
        with self.assertRaises(GovernanceError):
            f.decide(req)
        result = f.decide(req, context=f.second)
        approval = f.service.get(result["approval_reference"])
        self.assertEqual(len(approval["approver_principal_references"]), 2)
        self.assertEqual(approval["expires_at"], req["approval_terms"]["expires_at"])

    def test_submitter_cannot_self_approve_under_independence_policy(self):
        self.f.grant(self.f.scope, "test-proposer")
        binding = self.f.propose(); req = self.f.review(binding)
        self.assertCode("independent_review_required", lambda: self.f.decide(req, context=self.f.author))

    def test_different_request_submitter_does_not_bypass_proposer_separation(self):
        self.f.grant(self.f.scope, "test-proposer")
        binding = self.f.propose(); req = self.f.review(binding, context=self.f.second)
        self.assertCode("independent_review_required", lambda: self.f.decide(req, context=self.f.author))

    def test_clock_regression_is_blocked(self):
        self.f.propose(); self.f.now -= timedelta(seconds=1)
        self.assertCode("clock_regression", lambda: self.f.propose("another"))

    def test_idempotent_replay_and_conflicting_command(self):
        binding = self.f.propose(); req = self.f.review(binding)
        command, head = self.f.cmd(), self.f.service.head
        result = self.f.decide(req, command_id=command, expected_head=head)
        later_head = self.f.service.head
        self.assertEqual(self.f.decide(req, command_id=command, expected_head=head), result)
        self.assertEqual(self.f.service.head, later_head)
        self.assertCode("command_conflict", lambda: self.f.decide(req, "reject", command_id=command, expected_head=head))

    def test_stale_head_and_exported_fake_approval_are_rejected(self):
        binding, approval = self.f.approve()
        self.assertCode("stale_governance_head", lambda: self.f.review(binding, expected_head=0))
        forged = deepcopy(approval); forged["object_id"] = "not-issued-by-service"
        self.f.catalogue.add(forged)
        self.assertCode("untrusted_record", lambda: self.f.service.get(reference(forged)))

    def test_provider_unavailability_does_not_approve(self):
        binding = self.f.propose(); req = self.f.review(binding)
        self.f.provider.available = False
        self.assertCode("authority_unavailable", lambda: self.f.decide(req))
        self.assertEqual(self.f.service.records("ApprovalRecord"), [])

    def test_conflicting_active_meanings_are_not_latest_wins(self):
        first, _ = self.f.approve()
        interpretation = deepcopy(first["interpretation"]); interpretation["definition"] = "A different declared meaning."
        second = self.f.propose("competing", interpretation=interpretation)
        self.f.approve(second)
        self.assertEqual(self.f.use(first)["result"], "conflict")

    def test_test_authority_requires_two_explicit_opt_ins(self):
        with self.assertRaises(GovernanceError):
            LocalTestAuthorityProvider()
        self.assertCode("test_provider_disabled", lambda: SemanticApprovalService(self.f.catalogue, self.f.provider, ReviewPolicy("p", "1")))

    def test_policy_flags_are_typed_and_default_deadlines_cannot_be_omitted(self):
        with self.assertRaises(ValueError):
            ReviewPolicy("policy", "1", independent_review="false")
        binding = self.f.propose()
        self.assertCode("deadline_required", lambda: self.f.review(binding, expires_at=None))

    def test_continuing_authority_is_explicit_and_does_not_rewrite_history(self):
        f = Fixture(continuing_authority=True)
        binding, approval = f.approve()
        f.provider.test_withdraw_grant(f.owner_grant)
        f.grant(f.scope, actions=["assess_use"])
        self.assertEqual(f.use(binding)["result"], "needs_review")
        self.assertEqual(f.service.get(reference(approval)), approval)

    def test_two_stale_writers_cannot_both_decide_same_head(self):
        from concurrent.futures import ThreadPoolExecutor
        binding = self.f.propose(); req = self.f.review(binding)
        head = self.f.service.head
        def attempt(index):
            try:
                self.f.decide(req, expected_head=head, command_id="writer-"+str(index))
                return "committed"
            except FrameworkError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (1, 2)))
        self.assertCountEqual(results, ["committed", "stale_governance_head"])
        self.assertEqual(len(self.f.service.records("ApprovalRecord")), 1)


if __name__ == "__main__":
    unittest.main()
