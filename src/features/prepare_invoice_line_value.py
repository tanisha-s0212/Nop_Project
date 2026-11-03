"""Specification-driven source-row preparation for an exploratory line-value proxy.

NOP field mappings and literal population filters live in the supplied JSON.
No joins, monetary aggregation, date imputation or source mutation is performed.
"""

from collections import Counter, defaultdict
from datetime import date
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from business_prediction.adapters import SourceConfig
from business_prediction.adapters.excel import ExcelAdapter
from business_prediction.adapters.base import encode_cell
from features.prepare_invoice_volume_exploratory import _date_if_unambiguous
from features.tabular_regression import feature_frame


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def prepare_line_value(root, specification_path, output_dir):
    root, specification_path, output_dir = Path(root).resolve(), Path(specification_path), Path(output_dir)
    specification = json.loads(specification_path.read_text(encoding="utf-8-sig"))
    if specification.get("business_approved") is not False or "synthetic" in specification.get("data_mode", "").casefold():
        raise ValueError("this preparation path requires an explicitly exploratory non-synthetic source specification")
    source = (root / specification["source_file"]).resolve()
    if not source.is_relative_to(root):
        raise ValueError("source must be inside the selected repository")
    if output_dir.exists():
        raise FileExistsError("preparation requires a new dataset version directory")
    source_hash = digest(source)
    config = SourceConfig("ml-line-value-source", "unverified-source-owner", "exploratory-ml-source-review")
    adapter = ExcelAdapter(source, config, header_rows={specification["source_sheet"]: specification["header_row"]})
    excluded, groups, fingerprints = [], defaultdict(list), Counter()
    date_kinds = Counter()
    with adapter.open_snapshot() as snapshot:
        table = next(table for table in snapshot.tables() if table.name == specification["source_sheet"])
        fields = {}
        for alias, source_header in specification["columns"].items():
            found = [field.position - 1 for field in table.fields if field.header == source_header]
            if len(found) != 1:
                raise ValueError("source schema has missing or ambiguous configured field: " + source_header)
            fields[alias] = found[0]
        for row in snapshot.iter_rows(table.table_id):
            values = {alias: row.cells[position] if position < len(row.cells) else None for alias, position in fields.items()}
            fingerprints[json.dumps([encode_cell(value) for value in row.cells], sort_keys=True)] += 1
            raw = values["event_date"]
            parsed = _date_if_unambiguous(raw)
            date_kinds["resolved" if parsed else "unresolved"] += 1
            record = {"source_row": row.position, "values": values, "date": parsed}
            reference = values["document_id"]
            if not isinstance(reference, str) or not reference.strip():
                excluded.append({"source_row": row.position, "reason": "missing_or_nontext_reference"})
            else:
                groups[reference].append(record)
    cutoff = date.fromisoformat(specification["as_of_date_exclusive"])
    rows, unresolved_documents, future_documents = [], 0, 0
    arithmetic_evaluable, arithmetic_mismatch = 0, 0
    for reference, details in groups.items():
        dates = [detail["date"] for detail in details]
        if any(value is None for value in dates) or len(set(dates)) != 1:
            unresolved_documents += 1
            excluded.extend({"source_row": detail["source_row"], "reason": "reference_has_unresolved_or_inconsistent_dates"} for detail in details)
            continue
        if dates[0] >= cutoff:
            future_documents += 1
            excluded.extend({"source_row": detail["source_row"], "reason": "not_before_explicit_cutoff"} for detail in details)
            continue
        for detail in details:
            values = detail["values"]
            population_failure = next((key for key, value in specification["population"].items() if values[key] != value), None)
            if population_failure:
                excluded.append({"source_row": detail["source_row"], "reason": "outside_literal_population:" + population_failure})
                continue
            record = {name: values[name] for name in [*specification["features"]["numeric_features"], *specification["features"]["categorical_features"]]}
            try:
                feature_frame([record], specification["features"])
                target = values["target_value"]
                if type(target) not in {int, float} or not math.isfinite(target) or target <= 0:
                    raise ValueError("invalid_native_positive_target")
            except ValueError as exc:
                excluded.append({"source_row": detail["source_row"], "reason": str(exc)})
                continue
            price = values["unit_price_diagnostic"]
            if type(price) in {int, float} and math.isfinite(price):
                arithmetic_evaluable += 1
                arithmetic_mismatch += abs(values["quantity"] * price - target) > max(1.0, 0.005 * abs(target))
            # Arithmetic is diagnostic only and never filters observations.
            rows.append({"source_row": detail["source_row"], "document_id": reference,
                         "event_date": dates[0].isoformat(), **record, "target_value": target})
    rows.sort(key=lambda row: (row["event_date"], row["document_id"], row["source_row"]))
    if not rows:
        raise ValueError("no observations passed the explicit preparation specification")
    if len(rows) + len(excluded) != len(table.rows):
        raise AssertionError("source-to-output row reconciliation failed")
    if digest(source) != source_hash:
        raise ValueError("source changed during preparation")
    output_dir.mkdir(parents=True, exist_ok=False)
    dataset_path = output_dir / "observations.csv"
    with dataset_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    metadata = {key: specification[key] for key in ("dataset_id", "dataset_version", "objective_id", "objective_name", "target_definition", "data_mode", "business_approved", "assumptions", "limitations")}
    metadata.update(dataset_sha256=digest(dataset_path), source_file=specification["source_file"], source_file_sha256=source_hash,
        source_sheet=specification["source_sheet"], source_fields=specification["columns"], source_rows=len(table.rows),
        source_references=len(groups), included_rows=len(rows), included_references=len({row["document_id"] for row in rows}),
        observation_days=len({row["event_date"] for row in rows}), observation_period={"start":rows[0]["event_date"], "end":rows[-1]["event_date"]},
        exclusion_counts=dict(Counter(item["reason"] for item in excluded)), excluded_rows=len(excluded),
        unresolved_references=unresolved_documents, future_references=future_documents, date_row_counts=dict(date_kinds),
        duplicate_source_rows_preserved=sum(max(0, count - 1) for count in fingerprints.values()),
        arithmetic_diagnostic={"evaluable_rows":arithmetic_evaluable, "outside_tolerance_rows":arithmetic_mismatch,
                               "used_for_filtering":False, "input_excluded_from_features":"unit_price_diagnostic"},
        observation_grain="one retained source detail row; document grouping is for exclusion and split isolation only",
        feature_schema=specification["features"], preparation_specification_sha256=digest(specification_path),
        transformations=["read raw cells without formula evaluation", "require every reference detail date resolved consistently",
            "filter explicit cutoff and literal population", "reject invalid required native values with row lineage",
            "retain duplicate source rows", "project source row features and stored target", "sort chronologically"],
        row_reconciliation_passed=True, joins_performed=False, missing_values_imputed=False, period_completeness="not established; no period totals are modeled")
    write_json(output_dir / "observations.metadata.json", metadata)
    write_json(output_dir / "observations.spec.json", {"objective_id": specification["objective_id"], "objective_name": specification["objective_name"],
        "target_definition":specification["target_definition"], "target_column":"target_value", "period_column":"event_date"})
    write_json(output_dir / "excluded_records.json", excluded)
    training_specification = {"objective_id":specification["objective_id"], "objective_name":specification["objective_name"],
        "target_definition":specification["target_definition"], "data_mode":specification["data_mode"],
        "features":specification["features"], "target_column":"target_value", "date_column":"event_date", "group_column":"document_id",
        "lineage_column":"source_row", "split_day_fractions":[0.6,0.2,0.2],
        "minimum_groups":{"train":60,"validation":20,"test":20}, "minimum_days":{"train":30,"validation":12,"test":12},
        "baseline":{"quantity_field":"quantity", "category_field":"item_code"}, "prediction_minimum":0.0,
        "forbidden_features":["source_row","document_id","event_date","target_value","unit_price_diagnostic"]}
    write_json(output_dir / "training_spec.json", training_specification)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_line_value(args.root, args.spec, args.output), indent=2))
