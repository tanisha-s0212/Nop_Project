"""Transport-neutral errors that do not expose source values."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str


class FrameworkError(Exception):
    """Stable code and safe explanation for a caller or structured log."""

    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)

    def to_dict(self):
        return {"status": "error", "code": self.code, "message": self.message}


class ContractValidationError(FrameworkError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("invalid_contract", "Contract validation failed.")

    def to_dict(self):
        return {**super().to_dict(), "issues": [asdict(i) for i in self.issues]}


class SourceError(FrameworkError):
    """Unreadable, unsupported, changed or resource-limited source."""


class CatalogueError(FrameworkError):
    """Invalid reference, mutation attempt or conflicting immutable revision."""
