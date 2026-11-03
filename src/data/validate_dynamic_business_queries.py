"""Actual-source query scenarios; examples here are validation data, not routing rules."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from business_prediction import DynamicBusinessQueryService
from business_prediction.catalogue import MetadataCatalogue
from business_prediction.metadata import foundation_registry
from business_prediction.query_assets import sha256


def validate(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Use a new validation output directory; prior evidence is preserved.")
    evidence = root / "reports/analysis/nop_readiness_evidence"
    manifest = json.loads((evidence / "source_manifest_before.json").read_text(encoding="utf-8"))

    def integrity():
        return [{"relative_path": item["relative_path"], "sha256": sha256(root / "dataset" / item["relative_path"]),
                 "matches_readiness_manifest": sha256(root / "dataset" / item["relative_path"]) == item["sha256"]}
                for item in manifest]

    before = integrity()
    if not all(item["matches_readiness_manifest"] for item in before):
        raise ValueError("Original-source integrity check failed; stale profiling cannot be reused.")
    protected = {str(path.relative_to(root)): sha256(path) for path in (root / "models").rglob("*") if path.is_file()}
    catalogue = MetadataCatalogue(foundation_registry())
    bundles = json.loads((evidence / "discovery_bundles.json").read_text(encoding="utf-8"))
    catalogue.add_many([document for bundle in bundles for document in (bundle["source_metadata"], bundle["discovery_result"])])
    service = DynamicBusinessQueryService(root, catalogue=catalogue)
    discovered = service.discover()
    if discovered["discovery_failures"]:
        raise ValueError("Source or artifact discovery failed: " + json.dumps(discovered["discovery_failures"]))
    selected = [dataset for dataset in discovered["datasets"] if dataset["business_approved"] is False]
    if len(selected) != 1:
        raise ValueError("Select one explicit validation dataset; this runner will not guess between targets.")
    dataset = selected[0]
    objective = dataset["query_schema"]["objective_id"]
    period_column, target_column = (dataset["query_schema"][key] for key in ("period_column", "target_column"))
    scenarios = [
        ("financial_forecast", "What will recognized revenue be over the next three months?"),
        ("profit_forecast", "When is profit expected to increase?"),
        ("sales_analysis", "Show monthly sales trend"),
        ("broad_invoice_forecast", "Forecast monthly invoice count for the next three months"),
        ("selected_exploratory_forecast", {"question": "Forecast the explicitly selected confirmed-date subset", "intent": "forecast", "objective_id": objective, "periods_ahead": 3}),
        ("historical_subset", {"question": "Show the observed target series", "intent": "historical_analysis", "dataset_id": dataset["dataset_id"], "analysis": {"operation": "series", "measure": target_column}}),
        ("rank_observed_periods", {"question": "Which observed period has the highest stored target?", "intent": "historical_analysis", "dataset_id": dataset["dataset_id"], "analysis": {"operation": "rank", "measure": target_column, "dimensions": [period_column]}}),
        ("product_demand", "Which products are showing increasing demand?"),
        ("inventory", "How much inventory might be required?"),
        ("customer_behavior", "Which customers may purchase again?"),
        ("performance_comparison", "Compare the performance of different business units"),
        ("diagnostic", "Why did sales decrease?"),
        ("unusual_changes", "Identify unusual changes in business performance"),
    ]
    responses = [{"scenario_id": identifier, "request": request, "response": service.process(request)} for identifier, request in scenarios]
    profiles = [service.process({"question": "Inspect observed source structure", "intent": "profile",
                               "source_reference": {"source_id": table["source_id"], "table_id": table["table_id"]}})
                for table in discovered["source_tables"]]
    request = {"question": "Forecast selected target", "intent": "forecast", "objective_id": objective, "periods_ahead": 2}
    code = "import json,sys; from business_prediction import DynamicBusinessQueryService; print(json.dumps(DynamicBusinessQueryService(sys.argv[1]).process(json.loads(sys.argv[2])),allow_nan=False))"
    process = subprocess.run([sys.executable, "-c", code, str(root), json.dumps(request)], env={**os.environ, "PYTHONPATH": str(root / "src")},
                             capture_output=True, text=True, check=True)
    fresh = json.loads(process.stdout)
    if fresh["status"] != "answered" or not fresh.get("predictions"):
        raise AssertionError("Fresh-process forecast did not return valid model results: " + json.dumps(fresh))
    after = integrity()
    unchanged_models = all(sha256(root / path) == digest for path, digest in protected.items())
    summary = {"validated_at_utc": datetime.now(timezone.utc).isoformat(), "python_executable": sys.executable,
               "source_files": len(before), "source_tables": len(discovered["source_tables"]),
               "source_columns": sum(len(table["fields"]) for table in discovered["source_tables"]),
               "source_hashes_match": all(item["matches_readiness_manifest"] for item in after), "sources_unchanged": before == after,
               "existing_models_unchanged": unchanged_models, "scenario_count": len(responses),
               "scenario_statuses": {item["scenario_id"]: item["response"]["status"] for item in responses},
               "source_profiles_returned": len(profiles), "fresh_process_status": fresh["status"],
               "fresh_process_models": len(fresh["predictions"]), "actual_models_reused": [model["model_identifier"] for model in discovered["models"]],
               "new_actual_models_trained": 0, "synthetic_models_used": False,
               "production_approved": False, "limitation": "Prefix field profiles remain prefix observations; source hashes and full physical counts are pinned to prior discovery."}
    if not summary["sources_unchanged"] or not unchanged_models:
        raise AssertionError("Protected source or model changed")
    output.mkdir(parents=True, exist_ok=False)
    for filename, payload in (("actual_request_results.json", responses), ("actual_source_profiles.json", profiles),
                              ("fresh_process_prediction.json", fresh), ("validation_results.json", summary), ("source_integrity.json", after)):
        with (output / filename).open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    validate(arguments.root, arguments.output)
