"""AUTOMATED TESTS ONLY. Never a production identity or authorization provider.

Credentials, grants and receipts live in memory and disappear on process exit.
Explicit opt-in is required both here and at the service boundary.
"""

from datetime import timedelta
from secrets import token_urlsafe
from uuid import uuid4

from .authority import AuthorityProvider
from .common import GovernanceError, clone, digest, instant, scope_contains


class LocalTestAuthorityProvider(AuthorityProvider):
    test_only = True

    def __init__(self, *, test_mode=False):
        if test_mode is not True:
            raise GovernanceError("test_provider_disabled", "Local authority is available only in explicit automated-test mode.")
        self.provider_id = "local-test:" + str(uuid4())
        self.available = True
        self._sessions, self._grants, self._receipts, self._evidence = {}, {}, {}, set()

    def test_session(self, principal):
        if not isinstance(principal, str) or not principal.strip():
            raise ValueError("Test principal must be a nonempty string.")
        credential = token_urlsafe(32)
        self._sessions[credential] = (principal, "test-context:" + str(uuid4()))
        return credential

    def test_grant(self, principal, actions, scope, *, valid_from, valid_until, subjects=None):
        start, end = instant(valid_from), instant(valid_until)
        if start >= end:
            raise ValueError("Test grant interval must be nonempty.")
        grant_id = "test-grant:" + str(uuid4())
        self._grants[grant_id] = {"principal": principal, "actions": frozenset(actions), "scope": clone(scope),
            "valid_from": valid_from, "valid_until": valid_until, "subjects": clone(subjects) if subjects else None,
            "withdrawn": False}
        return grant_id

    def test_withdraw_grant(self, grant_id):
        self._grants[grant_id]["withdrawn"] = True

    def test_attest_evidence(self, artifact_reference, content_digest, origin_identity):
        self._evidence.add((artifact_reference, content_digest, origin_identity))

    def authenticate(self, context, now):
        try:
            return self._sessions[context]
        except (KeyError, TypeError):
            raise GovernanceError("unverified_principal", "A provider-authenticated context is required; owner labels are not credentials.") from None

    def verify(self, context, action, subject_reference, scope, policy_reference, now):
        principal, context_ref = self.authenticate(context, now)
        matched_id, matched = None, None
        if self.available:
            for grant_id, grant in self._grants.items():
                if (not grant["withdrawn"] and grant["principal"] == principal and action in grant["actions"]
                        and instant(grant["valid_from"]) <= now < instant(grant["valid_until"])
                        and scope_contains(grant["scope"], scope)
                        and (grant["subjects"] is None or subject_reference in grant["subjects"])):
                    matched_id, matched = grant_id, grant
                    break
        outcome = "verified" if matched else "denied" if self.available else "unavailable"
        receipt = "test-receipt:" + str(uuid4())
        body = {"principal_reference": principal, "authentication_context_reference": context_ref,
            "authority_reference": {"provider_id": self.provider_id, "grant_id": matched_id, "grant_version": "1"} if matched else None,
            "policy_reference": clone(policy_reference), "requested_action": action, "subject_reference": clone(subject_reference),
            "scope": clone(scope), "verified_by": self.provider_id, "verified_at": now.isoformat(),
            "verification_valid_until": min(now + timedelta(minutes=5), instant(matched["valid_until"])).isoformat() if matched else None,
            "grant_validity": {"valid_from": matched["valid_from"] if matched else None,
                               "valid_until": matched["valid_until"] if matched else None},
            "delegation_chain": [], "verification_outcome": outcome,
            "reason_codes": [] if matched else ["no_matching_test_grant" if self.available else "test_provider_unavailable"],
            "verification_receipt_reference": receipt}
        self._receipts[receipt] = clone(body)
        return body

    def verify_record(self, record, now):
        if not self.available:
            raise GovernanceError("authority_unavailable", "Authority receipt trust cannot currently be checked.")
        expected = self._receipts.get(record.get("verification_receipt_reference"))
        return expected is not None and digest(expected) == digest({key: record.get(key) for key in expected})

    def verify_evidence_origin(self, artifact_reference, content_digest, origin_identity):
        return self.available and (artifact_reference, content_digest, origin_identity) in self._evidence

    def verify_continuing_authority(self, verification, now):
        authority = verification.get("authority_reference")
        grant = self._grants.get(authority["grant_id"]) if authority else None
        return bool(self.available and grant and not grant["withdrawn"] and
                    instant(grant["valid_from"]) <= now < instant(grant["valid_until"]))
