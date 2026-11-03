"""Schema-neutral physical profiling and explicitly unapproved hypotheses."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
import itertools
import json
import logging
import math
import re

from .adapters.base import cell_type, encode_cell
from .contracts import reference, uncertain
from .errors import FrameworkError, SourceError
from .metadata import foundation_registry, schema_digest, schema_shape

logger = logging.getLogger(__name__)
ABSENT = object()


@dataclass(frozen=True)
class DiscoveryOptions:
    max_rows: int | None = None
    identifier_min_nonmissing: int = 2

    def __post_init__(self):
        if self.max_rows is not None and (type(self.max_rows) is not int or self.max_rows < 0):
            raise ValueError("Row limit must be a nonnegative integer or None.")
        if type(self.identifier_min_nonmissing) is not int or self.identifier_min_nonmissing < 2:
            raise ValueError("Identifier evidence requires at least two nonmissing values.")


@dataclass(frozen=True)
class DiscoveryBundle:
    source_metadata: dict
    discovery_result: dict

    def publish(self, catalogue):
        catalogue.add_many([self.source_metadata, self.discovery_result])


def _missing(value):
    if value is ABSENT:
        return "structurally_absent"
    if value is None:
        return "null"
    if isinstance(value, str):
        if value == "":
            return "empty_text"
        if not value.strip():
            return "whitespace_text"
    return None


def _temporal(value):
    """Candidate syntax evidence only; never rewrite a source value.

    Two-digit years and ambiguous day/month tokens stay unresolved. Numeric
    values are not guessed to be Excel dates. Range includes only native or
    full-year tokens with one calendar interpretation, not complete history.
    """
    if isinstance(value, datetime):
        return "native_datetime", value.date().isoformat()
    if isinstance(value, date):
        return "native_date", value.isoformat()
    if isinstance(value, time):
        return "native_time", None
    if not isinstance(value, str):
        return None, None
    token = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}", token):
        year, month = map(int, token.split("-"))
        return ("year_month_period_text" if year >= 1 and 1 <= month <= 12 else "invalid_period_token"), None
    if re.fullmatch(r"\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", token):
        try:
            time.fromisoformat(token)
            return "iso_time_text", None
        except ValueError:
            return "invalid_time_token", None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
        try:
            return "iso_date_text", date.fromisoformat(token).isoformat()
        except ValueError:
            return "invalid_calendar_token", None
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", token):
        try:
            return "iso_datetime_text", datetime.fromisoformat(token).date().isoformat()
        except ValueError:
            return "invalid_calendar_token", None
    match = re.fullmatch(r"(\d{1,2})([/-])(\d{1,2})\2(\d{2}|\d{4})", token)
    if not match:
        return None, None
    first, _, second, year = match.groups()
    if len(year) == 2:
        # A leap-year upper bound can reject an impossible day/month without
        # choosing a century; 29 February still needs century confirmation.
        possible = False
        for day, month in ((first, second), (second, first)):
            try:
                date(2000, int(month), int(day))
                possible = True
            except ValueError:
                pass
        if not possible:
            return "invalid_calendar_token", None
        return "century_unresolved_text", None
    candidates = set()
    for day, month in ((first, second), (second, first)):
        try:
            candidates.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            pass
    if not candidates:
        return "invalid_calendar_token", None
    if len(candidates) > 1:
        return "ambiguous_day_month_text", None
    return "single_calendar_reading_text", next(iter(candidates))


def _profile(values):
    missing = Counter({key: 0 for key in ("null", "empty_text", "whitespace_text", "structurally_absent")})
    types, temporal, distinct, dates = Counter(), Counter(), set(), []
    numeric_text = nonfinite = 0
    for value in values:
        miss = _missing(value)
        if miss:
            missing[miss] += 1
            continue
        types[cell_type(value)] += 1
        distinct.add(json.dumps(encode_cell(value), sort_keys=True, ensure_ascii=False))
        kind, resolved_date = _temporal(value)
        if kind:
            temporal[kind] += 1
        if resolved_date:
            dates.append(resolved_date)
        if isinstance(value, str) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
            numeric_text += 1
        if (isinstance(value, float) and not math.isfinite(value)
                or isinstance(value, Decimal) and not value.is_finite()):
            nonfinite += 1
    return {"missing_counts": dict(missing), "nonmissing_count": sum(types.values()),
            "distinct_nonmissing_count": len(distinct), "type_counts": dict(types),
            "mixed_types": len(types) > 1, "nonfinite_numeric_count": nonfinite,
            "temporal_token_counts": dict(temporal), "numeric_text_count": numeric_text,
            "unambiguous_date_min": min(dates) if dates else None,
            "unambiguous_date_max": max(dates) if dates else None}


def _hypotheses(observed, field_id, evidence_id, complete, options):
    hypotheses = []
    def add(kind, explanation):
        hypotheses.append({"hypothesis_id": field_id+":"+kind, "kind": kind,
                           "status": "hypothesized", "approval_status": "unreviewed",
                           "evidence_ids": [evidence_id], "explanation": explanation})
    n = observed["nonmissing_count"]
    types = set(observed["type_counts"])
    if (n >= options.identifier_min_nonmissing and n == observed["distinct_nonmissing_count"]
            and not types.intersection({"formula", "cell_error", "boolean"}) and not observed["nonfinite_numeric_count"]):
        add("unique_value_candidate", "Distinct typed nonmissing values in "+("the full scan" if complete else "a prefix sample")+
            "; may be an ordinary measure, date or ordinal. No business identity, stability or scope is approved; missing cells remain explicit.")
    if observed["temporal_token_counts"]:
        add("temporal_candidate", "Native temporal values or date-like syntax observed; ambiguous formats, centuries and invalid tokens remain unresolved. No business time role or complete historical coverage is established.")
    if observed["numeric_text_count"]:
        add("numeric_representation_candidate", "Some raw text follows numeric syntax; identity, units and permission to parse are unknown. Text and leading zeros remain unchanged.")
    return hypotheses


def discover(adapter, *, source_revision=1, discovery_revision=1, options=None):
    """Return validated contracts; publish explicitly to a catalogue if desired.

    This reads only the supplied adapter, never an implicit project directory.
    A row limit samples profiling, not file capture or physical-layout discovery.
    """
    options = options or DiscoveryOptions()
    logger.info("discovery.started", extra={"source_id": adapter.source_id})
    try:
        with adapter.open_snapshot() as snapshot:
            metadata = snapshot.metadata()
            if metadata["source_id"] != adapter.source_id:
                raise SourceError("source_identity_mismatch", "Adapter and snapshot source identities differ.")
            stamp = datetime.now(timezone.utc).isoformat()
            common = {"contract_version": "1.0", "created_at": stamp,
                      "owner_reference": metadata["owner_reference"], "purpose_scope": metadata["purpose_scope"],
                      "approval_status": "unreviewed"}
            source = {**common, "contract_type": "DataSourceMetadata", "object_id": adapter.source_id,
                      "object_revision": source_revision,
                      **{key: metadata[key] for key in ("source_version", "adapter_kind", "adapter_settings", "resource_locator", "consistency")},
                      "authority": uncertain("unknown", "Production authority and business use are not approved by discovery.")}
            tables, evidence = [], []
            for table in snapshot.tables():
                rows = tuple(itertools.islice(snapshot.iter_rows(table.table_id), options.max_rows))
                complete = len(rows) == len(table.rows)
                header_counts = Counter(json.dumps(encode_cell(f.header), sort_keys=True)
                                        for f in table.fields if f.header_present and _missing(f.header) is None)
                fields = []
                for f in table.fields:
                    field_id = f"{table.table_id}:field-{f.position}"
                    evidence_id = field_id+":profile"
                    observed = _profile(r.cells[f.position-1] if f.position <= len(r.cells) else ABSENT for r in rows)
                    fields.append({"field_id": field_id, "position": f.position, "raw_header": encode_cell(f.header),
                        "header_present": f.header_present, "blank_header": _missing(f.header) is not None,
                        "duplicate_header": f.header_present and header_counts[json.dumps(encode_cell(f.header), sort_keys=True)] > 1,
                        "evidence_ids": [evidence_id], "observed": observed,
                        "hypotheses": _hypotheses(observed, field_id, evidence_id, complete, options)})
                    evidence.append({"evidence_id": evidence_id, "status": "observed", "table_id": table.table_id,
                        "field_id": field_id, "method": "typed_scalar_profile_v1",
                        "coverage": "full" if complete else "prefix_sample", "denominator": len(rows)})
                tables.append({"table_id": table.table_id, "name": table.name, "header_row": table.header_row,
                    "header_interpretation": "configured_unapproved", "schema_field_count": len(fields),
                    "observed_row_count": len(table.rows), "scanned_row_count": len(rows), "profile_complete": complete,
                    "completely_empty_rows": sum(all(_missing(v) is not None for v in r.cells) for r in rows),
                    "ragged_rows": sum(len(r.cells) != len(table.fields) for r in rows), "fields": fields})
            result = {**common, "contract_type": "SchemaDiscoveryResult", "object_id": adapter.source_id+":discovery",
                "object_revision": discovery_revision, "source_reference": reference(source),
                "source_version": source["source_version"], "schema_version": "pending",
                "profile_policy": {"max_rows": options.max_rows, "identifier_min_nonmissing": options.identifier_min_nonmissing},
                "tables": tables, "evidence": evidence,
                "limitations": ["Headers are configured layout interpretations, not business-approved definitions.",
                    "Physical positions identify fields only within a schema version; no semantic identity is inferred across changes.",
                    "Date syntax and partial ranges do not approve formats, epochs, centuries, time roles or complete history.",
                    "Identifier hypotheses use typed uniqueness only; no primary key, relationship or business meaning is approved.",
                    "Excel readers expose formatted native dates; formulas are inert and formula-cache freshness is not assessed.",
                    "Row limits bound profiles only; file bytes/layout remain subject to adapter resource budgets."]}
            result["schema_version"] = schema_digest(result)
            registry = foundation_registry()
            registry.validate(source)
            registry.validate(result, resolver=lambda ref: source if ref == reference(source) else None)
        # File snapshot exit verifies source integrity before any result escapes.
        logger.info("discovery.completed", extra={"source_id": adapter.source_id, "table_count": len(tables)})
        return DiscoveryBundle(source, result)
    except FrameworkError as exc:
        logger.warning("discovery.failed", extra={"source_id": adapter.source_id, "error_code": exc.code})
        raise


def compare_schemas(previous, current):
    """Report observed drift, never automatically rebind renamed/reordered fields."""
    registry = foundation_registry()
    for document in (previous, current):
        registry.validate(document, structural_only=True)
    if previous["source_reference"]["object_id"] != current["source_reference"]["object_id"]:
        raise SourceError("incompatible_comparison", "Schema comparison requires the same source identity.")
    before, after = ({t["table_id"]: t for t in schema_shape(d)} for d in (previous, current))
    changes = []
    def add(kind, table_id, field_id=None):
        changes.append({"kind": kind, "table_id": table_id, "field_id": field_id,
                        "approval_status": "unreviewed"})
    for table_id in sorted(before.keys() | after.keys()):
        if table_id not in before:
            add("table_added", table_id); continue
        if table_id not in after:
            add("table_removed", table_id); continue
        a, b = before[table_id], after[table_id]
        if (a["name"], a["header_row"]) != (b["name"], b["header_row"]):
            add("table_identity_or_layout_changed", table_id)
        old, new = ({f["field_id"]: f for f in t["fields"]} for t in (a, b))
        for field_id in sorted(old.keys() | new.keys()):
            if field_id not in old: add("field_added", table_id, field_id)
            elif field_id not in new: add("field_removed", table_id, field_id)
            else:
                if any(old[field_id][k] != new[field_id][k] for k in ("raw_header", "header_present", "position")):
                    add("field_identity_or_position_changed", table_id, field_id)
                if old[field_id]["observed_types"] != new[field_id]["observed_types"]:
                    add("observed_types_changed", table_id, field_id)
    return changes
