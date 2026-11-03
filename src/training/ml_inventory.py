"""Current source inventory using existing read-only adapters and discovery."""

import hashlib
import json
from pathlib import Path

from business_prediction.adapters import SourceConfig, CSVAdapter
from business_prediction.adapters.excel import ExcelAdapter
from business_prediction.discovery import DiscoveryOptions, discover


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_sources(source_directory, previous_bundles_path, recorded_manifest_path):
    directory = Path(source_directory).resolve()
    bundles = json.loads(Path(previous_bundles_path).read_text(encoding="utf-8"))
    recorded = {row["relative_path"]:row for row in json.loads(Path(recorded_manifest_path).read_text(encoding="utf-8"))}
    previous = {}
    for bundle in bundles:
        source = bundle["source_metadata"]
        path = Path(source["resource_locator"].replace("\\","/")).resolve()
        previous[path.relative_to(directory).as_posix()] = source
    files=[]
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        relative = path.relative_to(directory).as_posix()
        source_hash = digest(path)
        same = relative in recorded and recorded[relative]["sha256"] == source_hash
        row={"relative_path":relative,"sha256":source_hash,"size_bytes":path.stat().st_size,"matches_recorded_hash":same,"tables":[]}
        old=previous.get(relative)
        if not old or not same:
            row.update(status="layout_review_required",reason="Changed or unrecorded source cannot silently reuse an old physical-layout specification")
            files.append(row);continue
        settings=old["adapter_settings"]
        config=SourceConfig(old["object_id"],"unverified-source-owner","actual-source-ml-review")
        limits={"max_bytes":64*1024*1024,"max_cells":6_000_000}
        if path.suffix.lower() in {".xlsx",".xlsm"}:
            adapter=ExcelAdapter(path,config,header_rows=settings.get("header_rows",{}),default_header_row=settings.get("default_header_row",1),
                max_uncompressed_bytes=256*1024*1024,**limits)
        elif path.suffix.lower()==".csv":
            adapter=CSVAdapter(path,config,encoding=settings["encoding"],delimiter=settings["delimiter"],header_row=settings["header_row"],**limits)
        else:
            row.update(status="unsupported_format",reason="No existing source adapter supports this format");files.append(row);continue
        try:
            result=discover(adapter,options=DiscoveryOptions(max_rows=32)).discovery_result
            for table in result["tables"]:
                row["tables"].append({"table_id":table["table_id"],"name":table["name"],"header_row":table["header_row"],
                    "rows":table["observed_row_count"],"columns":table["schema_field_count"],
                    "headers":[field["raw_header"]["value"] for field in table["fields"]],
                    "profile_rows":table["scanned_row_count"],"profile_complete":table["profile_complete"]})
            row["status"]="inspected_read_only"
        except Exception as exc:
            row.update(status="inspection_failed",reason=str(exc))
        row["unchanged_during_inspection"]=digest(path)==source_hash
        files.append(row)
    return {"source_directory":str(directory),"source_file_count":len(files),
        "excel_workbooks":sum(Path(row["relative_path"]).suffix.lower() in {".xlsx",".xlsm"} for row in files),
        "csv_files":sum(Path(row["relative_path"]).suffix.lower()==".csv" for row in files),
        "table_count":sum(len(row["tables"]) for row in files),"field_count":sum(table["columns"] for row in files for table in row["tables"]),
        "all_recorded_hashes_match":all(row["matches_recorded_hash"] for row in files),
        "all_sources_inspected":all(row["status"]=="inspected_read_only" for row in files),"files":files,
        "profile_policy":"Full physical worksheet/table counts and headers reopened; 32-row profiles. Prior full quality evidence applies only to matching source hashes."}
