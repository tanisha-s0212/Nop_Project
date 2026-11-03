"""Local prototype credentials and HMAC receipts. NEVER production identity.

Stable operator-managed secret references allow development receipt verification
after restart. No bearer credential or HMAC key is stored in the database.
"""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
from uuid import uuid4

from ..semantics.common import clone, digest, instant, scope_contains, GovernanceError
from .security import IdentityProvider, AuthorizationProvider, AuthenticatedIdentity


class DevelopmentIdentityProvider(IdentityProvider):
    development_only = True

    def __init__(self, credentials, secrets, *, provider_id="development-local-identity"):
        if not credentials:
            raise GovernanceError("missing_identity_configuration", "Development credential references must be explicitly configured.")
        self._credentials, self._secrets = dict(credentials), secrets
        self.provider_id = provider_id

    def authenticate(self, credential, now):
        if not isinstance(credential, str):
            raise GovernanceError("unverified_principal", "Opaque configured development credentials are required.")
        for principal, secret_ref in self._credentials.items():
            expected = self._secrets.resolve(secret_ref).expose()
            if hmac.compare_digest(credential.encode(), expected.encode()):
                return AuthenticatedIdentity(principal, "development-context:"+str(uuid4()),
                                             self.provider_id, (now+timedelta(minutes=5)).isoformat())
        raise GovernanceError("unverified_principal", "Credential did not match a configured development identity.")

    def health_check(self):
        for ref in self._credentials.values():
            self._secrets.resolve(ref)
        return {"ready": True, "development_only": True, "provider": self.provider_id}


@dataclass(frozen=True)
class DevelopmentGrant:
    grant_id: str
    principal_reference: str
    actions: tuple
    scope: dict
    valid_from: str
    valid_until: str
    grant_version: str = "1"
    subject_references: tuple | None = None


class DevelopmentAuthorizationProvider(AuthorizationProvider):
    development_only = True

    def __init__(self, grants, secrets, signing_key_reference, *, provider_id="development-local-authorization"):
        self._grants = tuple(DevelopmentGrant(g.grant_id, g.principal_reference, tuple(g.actions), clone(g.scope),
            g.valid_from, g.valid_until, g.grant_version, tuple(clone(list(g.subject_references))) if g.subject_references else None) for g in grants)
        self._secrets, self._key_reference = secrets, signing_key_reference
        self.provider_id = provider_id
        for g in self._grants:
            if instant(g.valid_from) >= instant(g.valid_until):
                raise GovernanceError("invalid_grant", "Development grant validity must be nonempty.")

    def _key(self):
        value = self._secrets.resolve(self._key_reference).expose()
        if len(value.encode()) < 32:
            raise GovernanceError("weak_development_key", "Development receipt key must contain at least 32 bytes.")
        return value.encode()

    def _signature(self, body):
        return "development-hmac-v1:" + hmac.new(self._key(), digest(body).encode(), hashlib.sha256).hexdigest()

    def authorize(self, identity, action, subject_reference, scope, policy_reference, now):
        match = next((g for g in self._grants if g.principal_reference == identity.principal_reference and action in g.actions
            and instant(g.valid_from) <= now < instant(g.valid_until) and scope_contains(g.scope, scope)
            and (g.subject_references is None or subject_reference in g.subject_references)), None)
        body = {"principal_reference": identity.principal_reference, "authentication_context_reference": identity.context_reference,
            "authority_reference": {"provider_id": self.provider_id, "grant_id": match.grant_id, "grant_version": match.grant_version} if match else None,
            "policy_reference": clone(policy_reference), "requested_action": action, "subject_reference": clone(subject_reference),
            "scope": clone(scope), "verified_by": self.provider_id, "verified_at": now.isoformat(),
            "verification_valid_until": min(now+timedelta(minutes=5), instant(match.valid_until)).isoformat() if match else None,
            "grant_validity": {"valid_from": match.valid_from if match else None, "valid_until": match.valid_until if match else None},
            "delegation_chain": [], "verification_outcome": "verified" if match else "denied",
            "reason_codes": [] if match else ["no_matching_development_grant"]}
        return {**body, "verification_receipt_reference": self._signature(body)}

    def verify_record(self, record, now):
        keys = ("principal_reference", "authentication_context_reference", "authority_reference", "policy_reference",
            "requested_action", "subject_reference", "scope", "verified_by", "verified_at", "verification_valid_until",
            "grant_validity", "delegation_chain", "verification_outcome", "reason_codes")
        if record.get("verified_by") != self.provider_id:
            return False
        expected = self._signature({key: record.get(key) for key in keys})
        return hmac.compare_digest(expected, record.get("verification_receipt_reference", ""))

    def verify_continuing_authority(self, verification, now):
        authority = verification.get("authority_reference")
        return bool(authority and any(g.grant_id == authority["grant_id"] and g.grant_version == authority["grant_version"]
            and g.principal_reference == verification["principal_reference"] and verification["requested_action"] in g.actions
            and instant(g.valid_from) <= now < instant(g.valid_until) and scope_contains(g.scope, verification["scope"]) for g in self._grants))

    def health_check(self):
        self._key()
        return {"ready": True, "development_only": True, "provider": self.provider_id}
