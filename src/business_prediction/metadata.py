"""Version 1.0 source/discovery contracts: observations never grant approval."""

from datetime import date
import hashlib
import json

from .contracts import (ContractDefinition, ContractRegistry, FieldSpec as F,
                        REFERENCE_FIELDS, envelope_check, envelope_fields)
from .errors import ValidationIssue


def _count():
    return F("integer", minimum=0)


def _text_list():
    return F("array", items=F("string"))


def schema_shape(document):
    """Observed shape only; counts and source data versions are not schema."""
    return [{"table_id": t["table_id"], "name": t["name"], "header_row": t["header_row"],
             "fields": [{"field_id": f["field_id"], "position": f["position"],
                         "raw_header": f["raw_header"], "header_present": f["header_present"],
                         "observed_types": sorted(f["observed"]["type_counts"])} for f in t["fields"]]}
            for t in document["tables"]]


def schema_digest(document):
    return "sha256:"+hashlib.sha256(json.dumps(schema_shape(document), sort_keys=True).encode()).hexdigest()


def _discovery_check(doc, resolver):
    issues = []
    def check(condition, path, message):
        if not condition:
            issues.append(ValidationIssue(path, "inconsistent_metadata", message))
    source = resolver(doc["source_reference"]) if resolver else None
    check(source is not None and source.get("source_version") == doc["source_version"],
          "$.source_version", "Snapshot version must match the referenced source metadata.")
    check(doc["schema_version"] == schema_digest(doc), "$.schema_version", "Observed schema fingerprint is inconsistent.")
    table_ids = [t["table_id"] for t in doc["tables"]]
    check(len(set(table_ids)) == len(table_ids), "$.tables", "Table IDs must be unique within the snapshot.")
    evidence_ids = [e["evidence_id"] for e in doc["evidence"]]
    check(len(set(evidence_ids)) == len(evidence_ids), "$.evidence", "Evidence IDs must be unique.")
    evidence_set = set(evidence_ids)
    field_locations = {(t["table_id"], f["field_id"]): t["scanned_row_count"]
                       for t in doc["tables"] for f in t["fields"]}
    for i, evidence in enumerate(doc["evidence"]):
        location = (evidence["table_id"], evidence["field_id"])
        check(location in field_locations and evidence["denominator"] == field_locations.get(location),
              f"$.evidence[{i}]", "Evidence must reference a discovered field and its inspected population.")
    evidence_by_id = {e["evidence_id"]: e for e in doc["evidence"]}
    for i, table in enumerate(doc["tables"]):
        p = f"$.tables[{i}]"
        total, scanned = table["observed_row_count"], table["scanned_row_count"]
        check(scanned <= total and table["profile_complete"] == (scanned == total), p, "Profiling scope is inconsistent.")
        check(table["completely_empty_rows"] <= scanned, p, "Empty rows exceed inspected rows.")
        check(table["ragged_rows"] <= scanned, p, "Ragged rows exceed inspected rows.")
        check(table["schema_field_count"] == len(table["fields"]), p, "Field count must match metadata.")
        positions = [f["position"] for f in table["fields"]]
        field_ids = [f["field_id"] for f in table["fields"]]
        check(positions == list(range(1, len(positions)+1)) and len(set(field_ids)) == len(field_ids),
              p, "Field positions/IDs must be complete and unambiguous.")
        for j, field in enumerate(table["fields"]):
            fp = f"{p}.fields[{j}]"
            obs = field["observed"]
            counts = obs["missing_counts"]
            missing = sum(counts.values())
            check(missing + obs["nonmissing_count"] == scanned, fp, "Missingness denominator is inconsistent.")
            type_counts = obs["type_counts"]
            check(all(type(n) is int and n >= 0 for n in type_counts.values()), fp, "Type counts must be nonnegative integers.")
            if all(type(n) is int for n in type_counts.values()):
                check(sum(type_counts.values()) == obs["nonmissing_count"], fp, "Type counts must cover nonmissing cells.")
            temporal_counts = obs["temporal_token_counts"]
            check(all(type(n) is int and n >= 0 for n in temporal_counts.values()), fp, "Temporal counts must be nonnegative integers.")
            if all(type(n) is int for n in temporal_counts.values()):
                check(sum(temporal_counts.values()) <= obs["nonmissing_count"], fp, "Temporal counts exceed inspected nonmissing cells.")
            text_count = type_counts.get("text", 0)
            valid_representations = (type(text_count) is int and
                obs["nonfinite_numeric_count"] <= obs["nonmissing_count"] and
                obs["numeric_text_count"] <= text_count)
            check(valid_representations, fp, "Representation counts exceed their population.")
            low, high = obs["unambiguous_date_min"], obs["unambiguous_date_max"]
            try:
                valid_range = low is None and high is None or low is not None and high is not None and date.fromisoformat(low) <= date.fromisoformat(high)
            except ValueError:
                valid_range = False
            check(valid_range, fp, "Partial calendar range is invalid.")
            check(obs["distinct_nonmissing_count"] <= obs["nonmissing_count"], fp, "Distinct count exceeds its population.")
            check(obs["mixed_types"] == (len(type_counts) > 1), fp, "Mixed-type flag disagrees with observed types.")
            check(set(field["evidence_ids"]) <= evidence_set, fp, "Field evidence reference does not exist.")
            for evidence_id in field["evidence_ids"]:
                e = evidence_by_id.get(evidence_id)
                check(e is not None and (e["table_id"], e["field_id"]) == (table["table_id"], field["field_id"]),
                      fp, "Observation evidence must refer to this physical field.")
            for hypothesis in field["hypotheses"]:
                check(bool(hypothesis["evidence_ids"]) and set(hypothesis["evidence_ids"]) <= evidence_set,
                      fp, "Hypotheses require existing observation evidence.")
    return issues


def foundation_registry():
    """Create an extensible registry; only two technical contract types ship now."""
    registry = ContractRegistry()
    source_fields = {**envelope_fields(),
        "contract_type": F("string", choices=("DataSourceMetadata",)),
        "contract_version": F("string", choices=("1.0",)),
        "source_version": F("string"), "adapter_kind": F("string"),
        "adapter_settings": F("object"),
        "resource_locator": F("string"), "consistency": F("string"),
        "authority": F("string", uncertain=True),
        "approval_status": F("string", choices=("unreviewed",))}
    registry.register(ContractDefinition("DataSourceMetadata", "1.0", source_fields, (envelope_check,)))
    observation = F("object", fields={
        "missing_counts": F("object", fields={k: _count() for k in
            ("null", "empty_text", "whitespace_text", "structurally_absent")}),
        "nonmissing_count": _count(), "distinct_nonmissing_count": _count(),
        "type_counts": F("object"), "mixed_types": F("boolean"),
        "nonfinite_numeric_count": _count(), "temporal_token_counts": F("object"),
        "numeric_text_count": _count(),
        "unambiguous_date_min": F("string", nullable=True),
        "unambiguous_date_max": F("string", nullable=True)})
    hypothesis = F("object", fields={
        "hypothesis_id": F("string"), "kind": F("string"),
        "status": F("string", choices=("hypothesized",)),
        "approval_status": F("string", choices=("unreviewed",)),
        "evidence_ids": _text_list(), "explanation": F("string")})
    field = F("object", fields={
        "field_id": F("string"), "position": F("integer", minimum=1),
        "raw_header": F("object", fields={"type": F("string"), "value": F("any", nullable=True)}),
        "header_present": F("boolean"), "blank_header": F("boolean"),
        "duplicate_header": F("boolean"), "evidence_ids": _text_list(),
        "observed": observation, "hypotheses": F("array", items=hypothesis)})
    table = F("object", fields={
        "table_id": F("string"), "name": F("string"),
        "header_row": F("integer", minimum=1, nullable=True),
        "header_interpretation": F("string", choices=("configured_unapproved",)),
        "schema_field_count": _count(), "observed_row_count": _count(), "scanned_row_count": _count(),
        "profile_complete": F("boolean"), "completely_empty_rows": _count(),
        "ragged_rows": _count(), "fields": F("array", items=field)})
    evidence = F("object", fields={
        "evidence_id": F("string"), "status": F("string", choices=("observed",)),
        "table_id": F("string"), "field_id": F("string"), "method": F("string"),
        "coverage": F("string", choices=("full", "prefix_sample")), "denominator": _count()})
    discovery_fields = {**envelope_fields(),
        "contract_type": F("string", choices=("SchemaDiscoveryResult",)),
        "contract_version": F("string", choices=("1.0",)),
        "source_reference": F("object", fields=REFERENCE_FIELDS, reference_types=("DataSourceMetadata",)),
        "source_version": F("string"), "schema_version": F("string"),
        "approval_status": F("string", choices=("unreviewed",)),
        "profile_policy": F("object", fields={
            "max_rows": F("integer", minimum=0, nullable=True),
            "identifier_min_nonmissing": F("integer", minimum=2)}),
        "tables": F("array", items=table), "evidence": F("array", items=evidence),
        "limitations": _text_list()}
    registry.register(ContractDefinition("SchemaDiscoveryResult", "1.0", discovery_fields,
                                          (envelope_check, _discovery_check)))
    return registry
