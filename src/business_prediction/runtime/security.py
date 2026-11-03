"""Independent authentication/authorization interfaces and a compatibility bridge."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ..semantics.authority import AuthorityProvider
from ..semantics.common import GovernanceError, instant, clone

PROOF_FIELDS = {"principal_reference", "authentication_context_reference", "authority_reference", "policy_reference",
    "requested_action", "subject_reference", "scope", "verified_by", "verified_at", "verification_valid_until",
    "grant_validity", "delegation_chain", "verification_outcome", "reason_codes", "verification_receipt_reference"}


@dataclass(frozen=True)
class AuthenticatedIdentity:
    principal_reference: str
    context_reference: str
    issuer: str
    valid_until: str


class IdentityProvider(ABC):
    provider_id: str
    development_only = False
    test_only = False
    production_capable = False
    approval_reference = None

    @abstractmethod
    def authenticate(self, credential, now: datetime) -> AuthenticatedIdentity: ...

    @abstractmethod
    def health_check(self): ...


class AuthorizationProvider(ABC):
    provider_id: str
    development_only = False
    test_only = False
    production_capable = False
    approval_reference = None

    @abstractmethod
    def authorize(self, identity, action, subject_reference, scope, policy_reference, now): ...

    @abstractmethod
    def verify_record(self, record, now): ...

    @abstractmethod
    def health_check(self): ...

    def verify_evidence_origin(self, artifact_reference, content_digest, origin_identity):
        return False

    def verify_continuing_authority(self, verification, now):
        return False


class ComposedAuthorityProvider(AuthorityProvider):
    """Existing semantic lifecycle receives one bridge; identities stay separate."""

    def __init__(self, identity_provider, authorization_provider):
        self.identity_provider, self.authorization_provider = identity_provider, authorization_provider
        self.provider_id = identity_provider.provider_id + "+" + authorization_provider.provider_id
        self.test_only = identity_provider.test_only or authorization_provider.test_only
        self.development_only = identity_provider.development_only or authorization_provider.development_only

    def _identity(self, context, now):
        try:
            identity = self.identity_provider.authenticate(context, now)
            if (not isinstance(identity, AuthenticatedIdentity) or identity.issuer != self.identity_provider.provider_id
                    or not isinstance(identity.principal_reference, str) or not identity.principal_reference.strip()
                    or not isinstance(identity.context_reference, str) or not identity.context_reference.strip()
                    or identity.context_reference == context
                    or now >= instant(identity.valid_until)):
                raise ValueError
            return identity
        except GovernanceError:
            raise
        except Exception:
            raise GovernanceError("identity_unavailable", "Identity could not be verified by the configured provider.") from None

    def authenticate(self, context, now):
        identity = self._identity(context, now)
        return identity.principal_reference, identity.context_reference

    def verify(self, context, action, subject_reference, scope, policy_reference, now):
        identity = self._identity(context, now)
        try:
            proof = clone(self.authorization_provider.authorize(identity, action, subject_reference, scope, policy_reference, now))
            if (set(proof) != PROOF_FIELDS or proof["principal_reference"] != identity.principal_reference
                    or proof["authentication_context_reference"] != identity.context_reference
                    or proof["requested_action"] != action or proof["subject_reference"] != subject_reference
                    or proof["scope"] != scope or proof["policy_reference"] != policy_reference
                    or proof["verified_by"] != self.authorization_provider.provider_id
                    or proof["verification_outcome"] not in ("verified", "denied", "unavailable")):
                raise GovernanceError("authority_denied", "Authorization response did not match the authenticated exact request.")
            if self.authorization_provider.verify_record(proof, now) is not True:
                raise GovernanceError("unverified_authority_receipt", "Authorization receipt could not be verified.")
            if proof["verification_outcome"] == "verified":
                grant = proof["authority_reference"]
                if (not grant or grant["provider_id"] != self.authorization_provider.provider_id or
                        not instant(proof["verified_at"]) <= now < instant(proof["verification_valid_until"])):
                    raise GovernanceError("authority_denied", "Authority response has invalid issuer or freshness.")
            return proof
        except GovernanceError:
            raise
        except Exception:
            raise GovernanceError("authority_unavailable", "Authorization provider could not verify the requested authority.") from None

    def verify_record(self, record, now):
        try:
            return self.authorization_provider.verify_record(record, now) is True
        except GovernanceError:
            raise
        except Exception:
            raise GovernanceError("authority_unavailable", "Archived authority evidence could not be verified.") from None

    def verify_evidence_origin(self, *args):
        return self.authorization_provider.verify_evidence_origin(*args) is True

    def verify_continuing_authority(self, *args):
        return self.authorization_provider.verify_continuing_authority(*args) is True
