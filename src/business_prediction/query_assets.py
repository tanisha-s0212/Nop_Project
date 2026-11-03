"""Read-only query asset discovery built on existing discovery contracts."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

from .contracts import reference
from .discovery import discover


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return value


def within(path, root):
    result = Path(path).resolve()
    if not result.is_relative_to(Path(root).resolve()):
        raise ValueError("asset path escapes its registered root")
    return result


def source_issues(metadata, root):
    provenance = metadata.get("source_provenance", metadata)
    sources = provenance.get("source_files", [])
    if provenance.get("source_file"):
        sources = [*sources, {"path": provenance["source_file"], "sha256": provenance.get("source_file_sha256")}]
    issues = []
    for source in sources:
        try:
            path = within(Path(root) / str(source["path"]).replace("\\", "/"), root)
            if not source.get("sha256") or sha256(path) != source["sha256"]:
                issues.append("source_integrity_failed:" + str(source["path"]))
        except (OSError, ValueError, KeyError, TypeError):
            issues.append("source_unavailable_or_invalid:" + str(source))
    return issues


def dependency_issues(metadata):
    recorded = metadata.get("dependency_versions")
    if not isinstance(recorded, dict) or not recorded:
        return ["model_dependency_versions_missing"]
    current_python = ".".join(map(str, sys.version_info[:3]))
    issues = []
    if recorded.get("python") and recorded["python"] != current_python:
        issues.append(f"python: trained={recorded['python']}, current={current_python}")
    for key, expected in recorded.items():
        if key == "python" or not expected:
            continue
        package = {"scikit_learn": "scikit-learn"}.get(key, key)
        try:
            current = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            current = "unavailable"
        if current != expected:
            issues.append(f"{package}: trained={expected}, current={current}")
    return issues


def dataset_assets(data_root, project_root):
    assets, failures = [], []
    for sidecar in sorted(Path(data_root).rglob("*.metadata.json")):
        try:
            metadata = read_json(sidecar)
            if not metadata.get("dataset_id"):
                continue
            path = within(sidecar.with_name(sidecar.name.removesuffix(".metadata.json") + ".csv"), data_root)
            if not metadata.get("dataset_sha256") or sha256(path) != metadata["dataset_sha256"]:
                raise ValueError("dataset_integrity_failed")
            issues = source_issues(metadata, project_root)
            if issues:
                raise ValueError("; ".join(issues))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = list(reader.fieldnames or [])
                rows = list(reader)
            if not fields or len(set(fields)) != len(fields) or any(not field for field in fields):
                raise ValueError("dataset_header_invalid")
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError("dataset_ragged_rows")
            spec_path = sidecar.with_name(sidecar.name.removesuffix(".metadata.json") + ".spec.json")
            spec = read_json(spec_path) if spec_path.is_file() else metadata.get("query_schema", {})
            if not isinstance(spec, dict):
                raise ValueError("dataset_query_schema_invalid")
            for key in ("target_column", "period_column"):
                if spec.get(key) and spec[key] not in fields:
                    raise ValueError("dataset_specification_schema_mismatch:" + key)
            assets.append({"metadata": metadata, "path": path, "fields": fields, "rows": rows,
                           "spec": spec, "spec_sha256": sha256(spec_path) if spec_path.is_file() else None})
        except (OSError, ValueError, TypeError, KeyError, csv.Error) as exc:
            failures.append({"asset": str(sidecar), "reason": str(exc)})
    return assets, failures


def model_assets(model_root, project_root):
    assets, failures = [], []
    for sidecar in sorted(Path(model_root).rglob("*.metadata.json")):
        try:
            metadata = read_json(sidecar)
            if not metadata.get("objective_id"):
                continue
            artifact_ref = metadata.get("artifact_path")
            path = Path(str(artifact_ref).replace("\\", "/")) if artifact_ref else sidecar.with_name(sidecar.name.removesuffix(".metadata.json") + ".joblib")
            if not path.is_absolute():
                path = Path(project_root) / path
            path = within(path, model_root)
            if not metadata.get("artifact_sha256") or sha256(path) != metadata["artifact_sha256"]:
                raise ValueError("model_integrity_failed")
            issues = source_issues(metadata, project_root)
            if issues:
                raise ValueError("; ".join(issues))
            assets.append({"metadata": metadata, "path": path, "sidecar": sidecar,
                           "dependency_issues": dependency_issues(metadata)})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            failures.append({"asset": str(sidecar), "reason": str(exc)})
    return assets, failures


def source_context(adapters=(), catalogue=None, project_root=None):
    """Reuse pinned catalogue discoveries when their source bytes still match."""
    documents = catalogue.export_documents() if catalogue else []
    bundles, failures = [], []
    by_reference = {json.dumps(reference(d), sort_keys=True): d for d in documents}
    for document in documents:
        if document.get("contract_type") != "SchemaDiscoveryResult":
            continue
        source = by_reference.get(json.dumps(document["source_reference"], sort_keys=True))
        if source:
            bundles.append((source, document))
    for adapter in adapters:
        try:
            bundle = discover(adapter)
            bundles.append((bundle.source_metadata, bundle.discovery_result))
        except Exception as exc:
            failures.append({"source_id": adapter.source_id, "reason": getattr(exc, "code", str(exc))})
    tables = []
    for source, result in bundles:
        if source["adapter_kind"] != "memory":
            try:
                path = within(str(source["resource_locator"]).replace("\\", "/"), project_root)
                if "sha256:" + sha256(path) != source["source_version"]:
                    raise ValueError("stale_source_discovery")
            except (OSError, ValueError, TypeError) as exc:
                failures.append({"source_id": source["object_id"], "reason": str(exc)})
                continue
        for table in result["tables"]:
            fields = []
            for field in table["fields"]:
                fields.append({"field_id": field["field_id"], "name": field["raw_header"].get("value"),
                    "position": field["position"], "observed": field["observed"],
                    "physical_field_reference": {"source_metadata_reference": reference(source),
                        "discovery_reference": reference(result), "source_version": source["source_version"],
                        "schema_version": result["schema_version"], "table_id": table["table_id"],
                        "field_id": field["field_id"], "field_position": field["position"]}})
            tables.append({"source_id": source["object_id"], "source_version": source["source_version"],
                "table_id": table["table_id"], "name": table["name"], "row_count": table["observed_row_count"],
                "profile_complete": table["profile_complete"], "scanned_rows": table["scanned_row_count"],
                "fields": fields, "semantic_status": "unreviewed_observation"})
    return tables, failures
