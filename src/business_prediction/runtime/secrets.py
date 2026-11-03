"""Secret references only in configuration; no secret values in repr/logging."""

from abc import ABC, abstractmethod
import os

from ..semantics.common import GovernanceError


class SecretValue:
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def expose(self):
        """Trusted connector use only. Never log the returned value."""
        return self._value

    def __repr__(self):
        return "<redacted-secret>"

    __str__ = __repr__


class SecretResolver(ABC):
    @abstractmethod
    def resolve(self, reference) -> SecretValue: ...


class EnvironmentSecrets(SecretResolver):
    def __init__(self, environ=None):
        self._environ = os.environ if environ is None else environ

    def resolve(self, reference):
        if not isinstance(reference, str) or not reference.startswith("env:") or not reference[4:]:
            raise GovernanceError("invalid_secret_reference", "Expected a named environment secret reference.")
        value = self._environ.get(reference[4:])
        if not isinstance(value, str) or not value:
            raise GovernanceError("secret_unavailable", "Required secret is unavailable; no value or default was substituted.")
        return SecretValue(value)
