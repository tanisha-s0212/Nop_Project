"""Explicit execution modes and safe, reference-only operational configuration."""

from dataclasses import dataclass, fields

from ..semantics.common import GovernanceError


class ConfigurationError(GovernanceError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    storage_adapter: str
    identity_provider: str | None
    authorization_provider: str | None
    sqlite_path: str | None = None
    storage_approval_reference: str | None = None
    identity_approval_reference: str | None = None
    authorization_approval_reference: str | None = None
    credential_strategy: str | None = None
    secret_references: tuple[str, ...] = ()
    allow_test_providers: bool = False

    def validate(self):
        if self.mode not in ("development", "production") or not isinstance(self.storage_adapter, str) or not self.storage_adapter:
            raise ConfigurationError("invalid_execution_mode", "Explicit development/production mode and a storage adapter are required.")
        if type(self.allow_test_providers) is not bool:
            raise ConfigurationError("invalid_configuration", "Provider isolation flags must be boolean.")
        if not isinstance(self.identity_provider, str) or not self.identity_provider.strip():
            raise ConfigurationError("missing_identity_provider", "Select and configure an identity provider; no anonymous default is available.")
        if not isinstance(self.authorization_provider, str) or not self.authorization_provider.strip():
            raise ConfigurationError("missing_authorization_provider", "Select and configure an authorization provider; no allow-all default is available.")
        if self.credential_strategy not in ("secret_references", "external_identity"):
            raise ConfigurationError("missing_identity_configuration", "An explicit credential integration strategy is required.")
        if not isinstance(self.secret_references, (tuple, list)) or not all(isinstance(s, str) and s.strip() for s in self.secret_references):
            raise ConfigurationError("invalid_secret_reference", "Only explicit secret references may be configured.")
        if self.credential_strategy == "secret_references" and not self.secret_references:
            raise ConfigurationError("missing_secret_configuration", "Credential secret references are missing.")
        if self.storage_adapter == "sqlite" and not self.sqlite_path:
            raise ConfigurationError("missing_storage_path", "Local persistent execution requires an explicit SQLite path.")
        if self.mode == "production":
            if self.storage_adapter in ("sqlite", "memory") or self.sqlite_path is not None or self.allow_test_providers:
                raise ConfigurationError("unsafe_production_configuration", "Production rejects local storage and test-provider defaults.")
            if not all(isinstance(v, str) and v.strip() for v in
                       (self.storage_approval_reference, self.identity_approval_reference, self.authorization_approval_reference)):
                raise ConfigurationError("missing_integration_approval", "Production adapters require explicit deployment approval references.")
        return self

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ConfigurationError("invalid_configuration", "Unknown configuration fields; raw credentials are not accepted.")
        try:
            return cls(**value).validate()
        except TypeError:
            raise ConfigurationError("invalid_configuration", "Required runtime configuration fields are missing.") from None
