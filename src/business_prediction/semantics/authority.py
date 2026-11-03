"""Provider-neutral authority boundary. No production provider ships here."""

from abc import ABC, abstractmethod


class AuthorityProvider(ABC):
    provider_id: str
    test_only: bool = False

    @abstractmethod
    def authenticate(self, context, now):
        """Return (verified principal, safe context reference), or raise."""

    @abstractmethod
    def verify(self, context, action, subject_reference, scope, policy_reference, now):
        """Return AuthorityVerificationRecord body with provider receipt."""

    @abstractmethod
    def verify_record(self, record, now):
        """Verify archived receipt integrity/current provider trust, not job title."""

    def verify_evidence_origin(self, artifact_reference, content_digest, origin_identity):
        return False

    def verify_continuing_authority(self, verification, now):
        return False
