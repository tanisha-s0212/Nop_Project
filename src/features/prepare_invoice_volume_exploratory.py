"""Prepare an explicitly exploratory confirmed-date invoice subset from NOP data.

This source-specific exploratory entry point is deliberately not a business-approved
preparation plan and does not create semantic approvals or worker receipts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "dataset" / "Sales Invoice Details.xlsx"
OUTPUT = ROOT / "data" / "nop_confirmed_date_invoice_count_exploratory.csv"
METADATA = ROOT / "data" / "nop_confirmed_date_invoice_count_exploratory.metadata.json"

sys.path.insert(0, str(ROOT / "src"))
from business_prediction.contracts import reference_key
from business_prediction.worker.operators import ApprovedTimeSeriesAggregation


def _date_if_unambiguous(value: object) -> date | None:
    """Accept only canonical-looking D/M/Y strings whose day exceeds 12."""
    if not isinstance(value, str):
        return None
    token = value.strip()
    parts = token.split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    day, month, year = map(int, parts)
    if not 12 < day <= 31 or not 1 <= month <= 12 or len(parts[2]) != 4:
        return None
    try:
        parsed = datetime.strptime(token, "%d/%m/%Y").date()
    except ValueError:
        return None
    return parsed if parsed.strftime("%d/%m/%Y") == token else None


def prepare(source: Path = SOURCE, output: Path = OUTPUT, metadata: Path = METADATA) -> dict:
    source = Path(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    workbook = load_workbook(source, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    sheet_name = sheet.title
    iterator = sheet.iter_rows(values_only=True)
    headers = next(iterator)
    column = {str(value).strip(): index for index, value in enumerate(headers) if value is not None}
    required = {"Invoice Num", "Invoice Date", "TransType"}
    if not required <= set(column):
        raise ValueError(f"Required source fields are missing: {sorted(required - set(column))}")

    details: dict[str, list[tuple[object, object, object]]] = defaultdict(list)
    missing_reference_rows = 0
    lifecycle_values = Counter()
    for source_row_number, row in enumerate(iterator, start=2):
        ref = row[column["Invoice Num"]]
        raw_date = row[column["Invoice Date"]]
        transaction_type = row[column["TransType"]]
        lifecycle_values[str(transaction_type)] += 1
        if ref is None or not str(ref).strip():
            missing_reference_rows += 1
            continue
        details[str(ref).strip()].append((raw_date, transaction_type, source_row_number))
    workbook.close()
    if lifecycle_values != Counter({"GST Tax Invoice": sum(lifecycle_values.values())}):
        raise ValueError("The source contains additional transaction types; the exploratory population must be reviewed.")

    eligible: dict[str, date] = {}
    ambiguous_rows = missing_date_rows = invalid_rows = unresolved_references = 0
    resolved_rows = 0
    included_source_rows: list[int] = []
    for ref, lines in details.items():
        dates: list[date] = []
        has_unresolved = False
        for raw_date, _, _ in lines:
            parsed = _date_if_unambiguous(raw_date)
            if parsed is None:
                has_unresolved = True
                if raw_date is None or not str(raw_date).strip():
                    missing_date_rows += 1
                elif isinstance(raw_date, str) and len(raw_date.strip().split("/")) == 3:
                    first = raw_date.strip().split("/")[0]
                    if first.isdigit() and int(first) <= 12:
                        ambiguous_rows += 1
                    else:
                        invalid_rows += 1
                else:
                    invalid_rows += 1
            else:
                dates.append(parsed)
                resolved_rows += 1
        if has_unresolved or len(set(dates)) != 1 or len(dates) != len(lines):
            unresolved_references += 1
            continue
        eligible[ref] = dates[0]

    # Keep every detail row for a document only when every row has one same,
    # unambiguous date. This prevents partial line inclusion from changing counts.
    date_ref = {"contract_type": "ExploratoryFieldReference", "contract_version": "1.0", "object_id": "source-date", "object_revision": 1}
    invoice_ref = {"contract_type": "ExploratoryFieldReference", "contract_version": "1.0", "object_id": "source-invoice-identity", "object_revision": 1}
    operation = {
        "operation_type": "time_series_aggregation", "operation_version": "1.0",
        "input_grain": "invoice-detail-line", "output_grain": "month",
        "input_binding_references": [date_ref, invoice_ref],
        "parameters": {
            "dimensions": [{"binding_reference": date_ref, "output_field_id": "period", "bucket": "month"}],
            "measures": [{"binding_references": [invoice_ref], "output_field_id": "target_count", "method": "count_distinct"}],
            "reconciliation_checks": ["source detail row count", "distinct source invoice references"],
            "missing_period_policy": "observed_only"}}
    batch = {"schema": [{"field_id": "invoice_date", "types": ["date"]}, {"field_id": "invoice_num", "types": ["text"]}],
             "rows": [], "ordinals": []}
    ordinal = 0
    for ref, lines in details.items():
        if ref not in eligible:
            continue
        for _, _, source_row_number in lines:
            ordinal += 1
            batch["rows"].append([
                {"type": "date", "value": eligible[ref].isoformat()},
                {"type": "text", "value": ref}])
            batch["ordinals"].append(ordinal)
            included_source_rows.append(source_row_number)
    field_ids = {reference_key(date_ref): "invoice_date", reference_key(invoice_ref): "invoice_num"}
    operator = ApprovedTimeSeriesAggregation()
    operator.validate(operation)
    aggregated, rejected = operator.apply(batch, operation, field_ids)
    if rejected["rows"]:
        raise AssertionError("The aggregation operator must not silently reject prepared records.")
    reconciliation_passed = operator.reconcile(batch, aggregated, rejected, operation, field_ids)
    if not reconciliation_passed:
        raise AssertionError("Independent aggregation reconciliation failed.")

    periods = [(row[0]["value"], row[1]["value"]) for row in aggregated["rows"]]
    if not periods:
        raise ValueError("No fully resolved document dates were available for the exploratory dataset.")
    first_period, last_period = periods[0][0], periods[-1][0]
    records = []
    for period, count in periods:
        boundary = "partial_calendar_boundary" if period in (first_period, last_period) else "interior_calendar_month"
        records.append({"period": period, "target_count": count, "calendar_boundary_status": boundary})

    output, metadata = Path(output), Path(metadata)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open(mode="x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["period", "target_count", "calendar_boundary_status"])
        writer.writeheader(); writer.writerows(records)
    output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    try:
        source_label = str(source.relative_to(ROOT))
    except ValueError:
        source_label = str(source)
    body = {
        "dataset_id": "nop-confirmed-date-invoice-count-exploratory", "dataset_version": "1.0.0",
        "dataset_sha256": output_hash, "source_file": source_label, "source_file_sha256": source_hash,
        "source_sheet": sheet_name, "source_row_count": sum(lifecycle_values.values()),
        "source_fields": {"document_reference": "Invoice Num", "event_date": "Invoice Date", "population": "TransType"},
        "target_definition": "Distinct invoice references with a fully consistent and unambiguously day-first date, grouped by observed calendar month in this workbook.",
        "data_mode": "actual_nop_exploratory_subset", "business_approved": False,
        "controlled_worker_execution": False,
        "preparation_operator": {"operation_type": "time_series_aggregation", "operation_version": "1.0", "implementation_version": operator.implementation_version,
            "specification": operation["parameters"], "input_eligible_detail_rows": len(batch["rows"]),
            "aggregate_row_count": len(aggregated["rows"]), "rejected_count": 0,
            "independent_reconciliation_passed": reconciliation_passed},
        "observations": len(records), "observation_period": {"start": first_period, "end": last_period},
        "detail_rows_with_unambiguous_dates": resolved_rows,
        "ambiguous_date_rows_excluded": ambiguous_rows, "blank_date_rows_excluded": missing_date_rows,
        "invalid_or_unsupported_date_rows_excluded": invalid_rows,
        "distinct_references_without_fully_resolved_date_excluded": unresolved_references,
        "missing_invoice_reference_rows": missing_reference_rows,
        "distinct_references_in_source": len(details), "distinct_references_included": len(eligible),
        "included_source_row_numbers": included_source_rows,
        "calendar_months_with_observations": [r["period"] for r in records],
        "period_completeness": "unknown; no extraction watermark or closed-period evidence was available",
        "assumptions_document": "reports/nop_actual_data_ml_exploratory_assumptions.md",
        "limitations": ["This is a confirmed-date subset, not total invoice volume.",
            "The exact invoice reference is assumed unique within this workbook only.",
            "Unresolved dates are excluded and may create month-dependent undercounts.",
            "No zero periods were inserted; absent months mean unknown, not zero.",
            "No semantic approval, execution authorization, or publication receipt was created."]}
    metadata.parent.mkdir(parents=True, exist_ok=True)
    with metadata.open("x", encoding="utf-8") as stream:
        json.dump(body, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return body


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--metadata", type=Path, default=METADATA)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.metadata), indent=2))
