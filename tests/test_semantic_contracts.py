from copy import deepcopy
from datetime import timedelta
import unittest

from business_prediction.contracts import reference
from business_prediction.errors import ContractValidationError, FrameworkError
from business_prediction.semantics.contracts import CONTRACT_TYPES
from business_prediction.semantics.common import digest
from tests.semantic_support import Fixture, evidence_ref


class SemanticContractTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def test_missing_fields_and_unsupported_contract_versions_are_structured(self):
        binding = self.f.propose()
        for kind in CONTRACT_TYPES:
            with self.subTest(kind=kind), self.assertRaises(ContractValidationError) as caught:
                self.f.catalogue.registry.validate({"contract_type": kind, "contract_version": "1.0"})
            self.assertTrue(any(i.code == "missing_field" for i in caught.exception.issues))
        binding["contract_version"] = "99.0"
        with self.assertRaises(ContractValidationError):
            self.f.catalogue.registry.validate(binding, resolver=self.f.catalogue.resolve)

    def test_public_interface_rejects_non_json_without_coercion(self):
        for value in ({1: "integer key"}, {"bad": float("nan")}, {"bad": object()}):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(FrameworkError) as caught:
                self.f.propose(provenance=value)
            self.assertEqual(caught.exception.code, "invalid_json")

    def test_wrong_schema_digest_field_position_and_evidence_id_are_rejected(self):
        for mutate in (lambda f: f.update(schema_version="not-the-discovered-schema"), lambda f: f.update(field_position=99)):
            field = deepcopy(self.f.field); mutate(field)
            with self.assertRaises(FrameworkError):
                self.f.propose(physical_field_reference=field)
        evidence = deepcopy(self.f.evidence); evidence[0]["evidence_id"] = "not-found"
        with self.assertRaises(FrameworkError):
            self.f.propose(evidence=evidence)

    def test_unrelated_field_observation_cannot_support_binding(self):
        evidence = [evidence_ref("observation", discovery_reference=reference(self.f.bundle.discovery_result),
            field_id="table-1:field-2", evidence_id="table-1:field-2:profile")]
        with self.assertRaises(ContractValidationError):
            self.f.propose(evidence=evidence)

    def test_hypothesis_evidence_remains_inferred_after_explicit_owner_review(self):
        evidence = [evidence_ref("hypothesis", discovery_reference=reference(self.f.bundle.discovery_result),
            field_id="table-1:field-1", hypothesis_id="table-1:field-1:unique_value_candidate")]
        binding = self.f.propose(evidence=evidence); self.f.approve(binding)
        source = self.f.catalogue.get(reference(self.f.bundle.discovery_result))
        self.assertEqual(source["tables"][0]["fields"][0]["hypotheses"][0]["status"], "hypothesized")
        self.assertEqual(source["approval_status"], "unreviewed")

    def test_unknown_qualifier_cannot_be_hidden_as_known(self):
        with self.assertRaises(ContractValidationError):
            self.f.propose(qualifiers=[{"name": "unit", "status": "known", "value": {"$state": "unknown", "reason": "Not supplied"}, "reason": None}])
        binding = self.f.propose(qualifiers=[{"name": "unit", "status": "unknown", "value": None, "reason": "Owner must confirm."}])
        req = self.f.review(binding)
        with self.assertRaises(FrameworkError):
            self.f.decide(req)
        self.assertEqual(self.f.service.records("ApprovalRecord"), [])

    def make_documentary(self, *, attest, expiry=None):
        content_digest = digest({"synthetic-document": "owner statement"})
        if attest:
            self.f.provider.test_attest_evidence("test-artifact:1", content_digest, "test-origin")
        return self.f.service.register_evidence(artifact_reference="test-artifact:1", artifact_version="1",
            content_digest=content_digest, evidence_kind="synthetic-owner-document", claim_summary="Synthetic interpretation evidence.",
            origin_identity="test-origin", coverage="Synthetic fixture only", access_policy_reference="test-access:1",
            retention_reference="test-retention:1", purpose="unit-test", context=self.f.author,
            command_id=self.f.cmd(), expected_head=self.f.service.head,
            relevant_subjects=[reference(self.f.bundle.discovery_result)], valid_until=expiry)

    def test_documentary_origin_is_not_a_caller_approved_flag(self):
        document = self.make_documentary(attest=False)
        self.assertEqual(document["origin_verification"], "unverified")
        binding = self.f.propose(evidence=self.f.evidence+[evidence_ref("documentary", record_reference=reference(document))])
        req = self.f.review(binding)
        with self.assertRaises(FrameworkError) as caught:
            self.f.decide(req)
        self.assertEqual(caught.exception.code, "unverified_evidence")

    def test_verified_documentary_evidence_and_expiry_affect_current_use(self):
        document = self.make_documentary(attest=True, expiry=(self.f.now+timedelta(hours=1)).isoformat())
        binding = self.f.propose(evidence=self.f.evidence+[evidence_ref("documentary", record_reference=reference(document))])
        self.f.approve(binding)
        self.assertEqual(self.f.use(binding)["result"], "usable")
        self.f.now += timedelta(hours=1)
        self.assertEqual(self.f.use(binding)["result"], "needs_review")
        self.assertEqual(self.f.service.get(reference(document)), document)

    def test_definition_reference_must_be_in_frozen_evidence(self):
        document = self.make_documentary(attest=True)
        interpretation = {"concept": "synthetic-concept", "definition": "A documentary proposal.",
                          "definition_version": "1", "definition_reference": reference(document)}
        with self.assertRaises(FrameworkError) as caught:
            self.f.propose(interpretation=interpretation)
        self.assertEqual(caught.exception.code, "unresolved_evidence")

    def test_prior_assertion_revocation_blocks_dependent_binding(self):
        parent, parent_approval = self.f.approve()
        child = self.f.propose("dependent", evidence=self.f.evidence+[evidence_ref("approved_assertion",
            binding_reference=reference(parent), approval_reference=reference(parent_approval))])
        self.f.approve(child)
        req = self.f.review(parent_approval); self.f.decide(req, "revoke")
        self.assertEqual(self.f.use(child)["result"], "needs_review")

    def test_prior_assertion_cannot_silently_transfer_to_another_purpose(self):
        parent, approval = self.f.approve()
        scope = deepcopy(self.f.scope); scope["purpose"] = "another-purpose"
        with self.assertRaises(ContractValidationError):
            self.f.propose("other-purpose", scope=scope, evidence=self.f.evidence+[evidence_ref("approved_assertion",
                binding_reference=reference(parent), approval_reference=reference(approval))])

    def test_all_eight_contract_types_are_emitted_and_fully_validate(self):
        self.make_documentary(attest=True)
        binding, _ = self.f.approve(); self.f.use(binding)
        self.f.service.assess_change(reference(binding), reference(self.f.bundle.discovery_result), context=self.f.owner,
            command_id=self.f.cmd(), expected_head=self.f.service.head)
        emitted = self.f.service.records()
        self.assertEqual({d["contract_type"] for d in emitted}, set(CONTRACT_TYPES))
        for document in emitted:
            self.f.catalogue.registry.validate(document, resolver=self.f.catalogue.resolve)

    def test_decision_and_approval_cross_reference_tampering_is_rejected(self):
        binding, approval = self.f.approve()
        altered = deepcopy(approval); altered["approver_principal_references"] = ["invented-owner"]
        with self.assertRaises(ContractValidationError):
            self.f.catalogue.registry.validate(altered, resolver=self.f.catalogue.resolve)
        altered = deepcopy(approval); altered["expires_at"] = (self.f.now+timedelta(days=99)).isoformat()
        with self.assertRaises(ContractValidationError):
            self.f.catalogue.registry.validate(altered, resolver=self.f.catalogue.resolve)

    def test_negative_authority_outcome_and_history_survive_replay(self):
        binding = self.f.propose(); request = self.f.review(binding)
        command, head = self.f.cmd(), self.f.service.head
        for _ in range(2):
            with self.assertRaises(FrameworkError):
                self.f.decide(request, context=self.f.intruder, command_id=command, expected_head=head)
        self.assertEqual(len(self.f.service.records("AuthorityVerificationRecord")), 1)
        history = self.f.service.history(); history.clear()
        self.assertGreater(len(self.f.service.history()), 0)


if __name__ == "__main__":
    unittest.main()
