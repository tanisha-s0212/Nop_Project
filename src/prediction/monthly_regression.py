"""Integrity-checked inference for objective-specific monthly regression artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import joblib
import numpy as np

MAX_PERIODS_AHEAD = 24


def _month_ordinal(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("period must use canonical YYYY-MM format")
    year, month = map(int, value.split("-"))
    return year * 12 + month - 1


def predict_monthly_objective(input_data: dict[str, Any], *, model_path: str | Path) -> dict:
    """Predict future periods for the exact objective encoded in a model bundle."""
    if not isinstance(input_data, dict) or set(input_data) != {"periods_ahead"}:
        raise ValueError("input_data must contain exactly periods_ahead")
    horizon = input_data["periods_ahead"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= MAX_PERIODS_AHEAD:
        raise ValueError(f"periods_ahead must be an integer from 1 to {MAX_PERIODS_AHEAD}")
    model_path = Path(model_path)
    metadata_path = model_path.with_name(model_path.stem + ".metadata.json")
    if not model_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("model artifact and matching metadata must both exist")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("model metadata is unreadable") from exc
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if metadata.get("artifact_sha256") != actual_hash:
        raise ValueError("model artifact integrity check failed")
    bundle = joblib.load(model_path)
    required = {"artifact_format_version", "model", "model_identifier", "model_version", "objective_id",
                "objective_name", "target_definition", "data_mode", "business_approved", "feature_names",
                "feature_origin_period", "latest_source_period", "known_limitations"}
    if not isinstance(bundle, dict) or not required <= set(bundle) or bundle["artifact_format_version"] != 1:
        raise ValueError("model artifact has an unsupported or incomplete bundle")
    if (not isinstance(bundle["data_mode"], str) or not bundle["data_mode"].strip()
            or "synthetic" in bundle["data_mode"].casefold() or bundle["business_approved"] is not False):
        raise ValueError("artifact is not an explicitly exploratory prepared-data model")
    if metadata.get("model_identifier") != bundle["model_identifier"] or metadata.get("model_version") != bundle["model_version"]:
        raise ValueError("metadata and model identity do not match")
    for key in ("objective_id", "target_definition", "data_mode", "business_approved", "dataset_sha256", "training_periods"):
        if metadata.get(key) != bundle.get(key):
            raise ValueError("metadata and model contract do not match: " + key)
    if bundle["feature_names"] != ["month_index"] or not callable(getattr(bundle["model"], "predict", None)):
        raise ValueError("artifact feature schema or estimator is incompatible")
    origin, latest = bundle["feature_origin_period"], bundle["latest_source_period"]
    origin_n, latest_n = _month_ordinal(origin), _month_ordinal(latest)
    predictions = []
    for step in range(1, horizon + 1):
        ordinal = latest_n + step
        year, month0 = divmod(ordinal, 12)
        period = f"{year:04d}-{month0 + 1:02d}"
        feature = np.asarray([[float(ordinal - origin_n)]])
        value = float(bundle["model"].predict(feature)[0])
        if not math.isfinite(value): raise ValueError("model returned a nonfinite prediction")
        predictions.append({"period": period, "prediction": max(0.0, value)})
    provenance = bundle.get("training_data_provenance", {})
    public_provenance = {key: provenance[key] for key in ("dataset_id", "dataset_version", "dataset_sha256",
        "source_file", "source_file_sha256", "source_sheet", "observations", "observation_period",
        "distinct_references_included", "distinct_references_without_fully_resolved_date_excluded") if key in provenance}
    return {"objective_id": bundle["objective_id"], "objective_name": bundle["objective_name"],
            "target_definition": bundle["target_definition"], "model_identifier": bundle["model_identifier"],
            "model_version": bundle["model_version"], "data_mode": bundle["data_mode"],
            "business_approved": False, "predictions": predictions,
            "data_provenance": public_provenance,
            "known_limitations": list(bundle["known_limitations"])}
