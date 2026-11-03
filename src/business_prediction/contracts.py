"""Explicit JSON-contract validation, not a general JSON Schema engine.

Technical contract versions extend by registration, never business questions.
No coercion, inferred approval, default values or implicit latest references.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import math
from types import MappingProxyType
from typing import Callable, Mapping

from .errors import ContractValidationError, ValidationIssue


class ValueState(str, Enum):
    MISSING = "missing"
    NULL = "null"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    PRESENT = "present"


def value_state(document, key):
    """Omission, explicit null and tagged uncertainty are different states."""
    if key not in document:
        return ValueState.MISSING
    value = document[key]
    if value is None:
        return ValueState.NULL
    if isinstance(value, dict) and value.get("$state") in ("unknown", "unavailable"):
        return ValueState(value["$state"])
    return ValueState.PRESENT


def uncertain(state: str, reason: str):
    if state not in ("unknown", "unavailable") or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Uncertainty requires a supported state and nonempty reason.")
    return {"$state": state, "reason": reason}


@dataclass(frozen=True)
class FieldSpec:
    kind: str
    required: bool = True
    nullable: bool = False
    uncertain: bool = False
    choices: tuple | None = None
    minimum: int | float | None = None
    fields: Mapping[str, "FieldSpec"] | None = None
    items: "FieldSpec | None" = None
    reference_types: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in {"string", "integer", "number", "boolean", "object", "array", "any"}:
            raise ValueError("Unsupported specification kind.")
        if self.fields is not None:
            object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        if self.choices is not None:
            object.__setattr__(self, "choices", tuple(self.choices))
        object.__setattr__(self, "reference_types", tuple(self.reference_types))
        if self.reference_types and self.kind != "object":
            raise ValueError("References require an object specification.")


@dataclass(frozen=True)
class ContractDefinition:
    contract_type: str
    contract_version: str
    fields: Mapping[str, FieldSpec]
    checks: tuple[Callable, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "checks", tuple(self.checks))


REFERENCE_FIELDS = {
    "contract_type": FieldSpec("string"), "contract_version": FieldSpec("string"),
    "object_id": FieldSpec("string"), "object_revision": FieldSpec("integer", minimum=1),
}


def reference(document):
    return {name: document[name] for name in REFERENCE_FIELDS}


def reference_key(ref):
    return tuple(ref[name] for name in REFERENCE_FIELDS)


class ContractRegistry:
    """Immutable definitions, exact references and explicit JSON extensions.

    Resolver returns an exact referenced document or None. Unknown fields are
    rejected; namespaced additions can use an explicitly declared extensions
    object. A referenced object must exist even when its ID looks plausible.
    """

    def __init__(self):
        self._definitions = {}

    def register(self, definition: ContractDefinition):
        key = (definition.contract_type, definition.contract_version)
        if key in self._definitions:
            raise ValueError("Contract definition already registered.")
        self._definitions[key] = definition

    def validate(self, document, resolver=None, *, structural_only=False):
        """Full validation by default; structural_only does not certify references.

        Structural validation is useful for staging unordered document bundles.
        The catalogue always performs full validation before committing them.
        """
        issues = []
        if not isinstance(document, dict):
            raise ContractValidationError([ValidationIssue("$", "type", "Expected object.")])
        try:
            _json_tree(document)
        except (ValueError, TypeError, RecursionError):
            raise ContractValidationError([ValidationIssue("$", "json_value", "Expected finite JSON values with string object keys.")]) from None
        kind, version = document.get("contract_type"), document.get("contract_version")
        if not isinstance(kind, str) or not isinstance(version, str):
            issues.append(ValidationIssue("$", "contract_identity", "String contract type and version required."))
            definition = None
        else:
            definition = self._definitions.get((kind, version))
            if definition is None:
                issues.append(ValidationIssue("$", "unsupported_version", "Unregistered contract type/version."))
        if definition:
            syntax_resolver = (lambda ref: dict(ref)) if structural_only else resolver
            self._validate_object(document, definition.fields, "$", issues, syntax_resolver)
            if not issues and not structural_only:
                for check in definition.checks:
                    issues.extend(check(document, resolver))
        if issues:
            raise ContractValidationError(issues)
        return json.loads(json.dumps(document, allow_nan=False))

    def _validate_object(self, value, fields, path, issues, resolver):
        for name in value:
            if name not in fields:
                issues.append(ValidationIssue(f"{path}.{name}", "unexpected_field", "Field is not declared."))
        for name, spec in fields.items():
            child = f"{path}.{name}"
            if name not in value:
                if spec.required:
                    issues.append(ValidationIssue(child, "missing_field", "Required field is missing."))
                continue
            self._validate_value(value[name], spec, child, issues, resolver)

    def _validate_value(self, value, spec, path, issues, resolver):
        def error(code, message):
            issues.append(ValidationIssue(path, code, message))
        if value is None:
            if not spec.nullable:
                error("null_not_allowed", "Explicit null is not allowed here.")
            return
        if isinstance(value, dict) and "$state" in value:
            if not spec.uncertain:
                error("uncertainty_not_allowed", "An actual value is required here.")
            elif (set(value) != {"$state", "reason"} or value.get("$state") not in ("unknown", "unavailable")
                  or not isinstance(value.get("reason"), str) or not value["reason"].strip()):
                error("invalid_value_state", "Use unknown/unavailable with a nonempty reason only.")
            return
        kinds = {"string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
                 "number": lambda: type(value) is int or type(value) is float and math.isfinite(value),
                 "boolean": lambda: type(value) is bool, "object": lambda: isinstance(value, dict),
                 "array": lambda: isinstance(value, list), "any": lambda: True}
        if not kinds[spec.kind]():
            error("type", f"Expected {spec.kind}.")
            return
        if spec.kind == "string" and not value.strip():
            error("empty_string", "Expected a nonempty string.")
        if spec.choices is not None and value not in spec.choices:
            error("choice", "Value is outside the declared choices.")
        if spec.minimum is not None and type(value) in (int, float) and value < spec.minimum:
            error("minimum", "Value is below the declared minimum.")
        before = len(issues)
        if spec.kind == "object" and spec.fields is not None:
            self._validate_object(value, spec.fields, path, issues, resolver)
        if spec.kind == "array" and spec.items:
            for i, item in enumerate(value):
                self._validate_value(item, spec.items, f"{path}[{i}]", issues, resolver)
        if spec.reference_types and len(issues) == before:
            if value.get("contract_type") not in spec.reference_types:
                error("reference_type", "Reference targets an incompatible contract type.")
            else:
                resolved = resolver(value) if resolver else None
                if (not isinstance(resolved, dict) or not all(k in resolved for k in REFERENCE_FIELDS)
                        or reference(resolved) != value):
                    error("unresolved_reference", "Exact referenced revision is unavailable.")
        try:
            json.dumps(value, allow_nan=False)
        except (ValueError, TypeError, OverflowError):
            error("json_value", "Expected finite JSON-compatible data.")


def envelope_fields():
    return {**REFERENCE_FIELDS, "created_at": FieldSpec("string"),
            "purpose_scope": FieldSpec("string"), "owner_reference": FieldSpec("string"),
            "extensions": FieldSpec("object", required=False)}


def _json_tree(value):
    """Reject silent JSON key/tuple coercion and nonfinite extension data."""
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ValueError
        for v in value.values():
            _json_tree(v)
        return
    if isinstance(value, list):
        for v in value:
            _json_tree(v)
        return
    raise ValueError


def envelope_check(document, resolver):
    try:
        stamp = datetime.fromisoformat(document["created_at"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
    except ValueError:
        return [ValidationIssue("$.created_at", "timestamp", "Expected timezone-aware ISO timestamp.")]
    return []
