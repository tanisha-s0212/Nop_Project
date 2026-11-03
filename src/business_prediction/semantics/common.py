"""Versioned JSON digests and exact, finite semantic scopes."""

from datetime import date, datetime
import hashlib
import json

from ..contracts import reference_key
from ..errors import FrameworkError


class GovernanceError(FrameworkError):
    """Structured governance failure; never a production authorization claim."""


def clone(value):
    try:
        result = json.loads(json.dumps(value, allow_nan=False))
        if result != value:
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise GovernanceError("invalid_json", "Expected finite JSON values without key or container coercion.") from None


def digest(value):
    """json-sort-compact-utf8-v1; integrity encoding, not an authority proof."""
    payload = json.dumps(clone(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def instant(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise GovernanceError("invalid_timestamp", "Expected a timezone-aware ISO timestamp.") from None


def field_key(field):
    return (reference_key(field["source_metadata_reference"]), reference_key(field["discovery_reference"]),
            field["source_version"], field["schema_version"], field["table_id"],
            field["field_id"], field["field_position"])


def scope_contains(outer, inner):
    """No fuzzy scope equivalence, wildcards or executable selectors."""
    if any(outer[k] != inner[k] for k in ("purpose", "namespace", "record_grain", "assertion_use")):
        return False
    if not {field_key(f) for f in inner["field_references"]} <= {field_key(f) for f in outer["field_references"]}:
        return False
    a, b = outer["business_period"], inner["business_period"]
    if a is None or b is None:
        return a == b and outer["period_not_applicable_reason"] == inner["period_not_applicable_reason"]
    return (a["calendar_reference"] == b["calendar_reference"] and
            date.fromisoformat(a["start"]) <= date.fromisoformat(b["start"]) and
            date.fromisoformat(b["end"]) <= date.fromisoformat(a["end"]))


def scope_overlaps(a, b):
    if any(a[k] != b[k] for k in ("purpose", "namespace", "record_grain", "assertion_use")):
        return False
    if not {field_key(f) for f in a["field_references"]} & {field_key(f) for f in b["field_references"]}:
        return False
    x, y = a["business_period"], b["business_period"]
    if x is None or y is None:
        return x == y
    return x["calendar_reference"] == y["calendar_reference"] and x["start"] < y["end"] and y["start"] < x["end"]
