"""Load and recursively apply the invoice-volume forecasting artifact."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import joblib
import numpy as np
import pandas as pd

from features.invoice_volume import FEATURE_COLUMNS, build_feature_row

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = ROOT / "models" / "nop_invoice_volume_model.joblib"
MAX_FORECAST_PERIODS = 36


def _validate_request(input_data: Any) -> tuple[int, list[str] | None, list[float] | None]:
    if not isinstance(input_data, dict):
        raise ValueError("input_data must be a JSON object")
    unknown = set(input_data) - {"periods_ahead", "historical_monthly_counts"}
    if unknown:
        raise ValueError(f"unsupported input fields: {', '.join(sorted(unknown))}")
    periods_ahead = input_data.get("periods_ahead")
    if isinstance(periods_ahead, bool) or not isinstance(periods_ahead, int):
        raise ValueError("periods_ahead must be an integer")
    if not 1 <= periods_ahead <= MAX_FORECAST_PERIODS:
        raise ValueError(f"periods_ahead must be between 1 and {MAX_FORECAST_PERIODS}")

    observations = input_data.get("historical_monthly_counts")
    if observations is None:
        return periods_ahead, None, None
    if not isinstance(observations, list):
        raise ValueError("historical_monthly_counts must be a list of {period, invoice_count} objects")
    periods: list[str] = []
    counts: list[float] = []
    for index, row in enumerate(observations):
        if not isinstance(row, dict) or set(row) != {"period", "invoice_count"}:
            raise ValueError(f"history item {index} must contain exactly period and invoice_count")
        if not isinstance(row["period"], str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", row["period"]):
            raise ValueError(f"history item {index} period must use YYYY-MM format")
        try:
            parsed_period = pd.Period(row["period"], freq="M")
            if pd.isna(parsed_period):
                raise ValueError
            period = str(parsed_period)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"history item {index} has an invalid monthly period") from exc
        value = row["invoice_count"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"history item {index} invoice_count must be a finite non-negative number")
        try:
            count = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"history item {index} invoice_count must be a finite non-negative number") from exc
        if not math.isfinite(count) or count < 0:
            raise ValueError(f"history item {index} invoice_count must be a finite non-negative number")
        periods.append(period)
        counts.append(count)
    if len(periods) < 12:
        raise ValueError("at least 12 historical monthly observations are required")
    if any(pd.Period(b, freq="M").ordinal - pd.Period(a, freq="M").ordinal != 1 for a, b in zip(periods, periods[1:])):
        raise ValueError("historical_monthly_counts must be strictly consecutive and in ascending order")
    return periods_ahead, periods, counts


def predict_invoice_volume(
    input_data: dict[str, Any],
    *,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return recursive monthly forecasts as JSON-serializable Python values.

    Caller-supplied history is treated as unverified input; this function does
    not establish its authority or business meaning.
    """
    periods_ahead, override_periods, override_counts = _validate_request(input_data)
    model_path = Path(model_path)
    if not model_path.is_file():
        raise FileNotFoundError(f"model artifact not found: {model_path}")
    metadata_explicit = metadata_path is not None
    metadata_path = Path(metadata_path) if metadata_explicit else model_path.with_name("model_metadata.json")
    metadata: dict[str, Any] | None = None
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("model metadata is unreadable or invalid JSON") from exc
        if not isinstance(metadata, dict):
            raise ValueError("model metadata must be a JSON object")
        expected_digest = metadata.get("model_artifact_sha256")
        actual_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if not isinstance(expected_digest, str) or expected_digest != actual_digest:
            raise ValueError("model artifact SHA-256 does not match its metadata")
    elif metadata_explicit or model_path.resolve() == DEFAULT_MODEL_PATH.resolve():
        raise FileNotFoundError(f"model metadata not found: {metadata_path}")
    bundle = joblib.load(model_path)
    required = {"artifact_format_version", "model", "model_identifier", "model_version", "feature_columns", "history_periods", "history_counts", "training_data_provenance", "data_mode", "known_limitations", "target_description"}
    if not isinstance(bundle, dict) or not required.issubset(bundle):
        raise ValueError("model artifact is incomplete or has an unsupported format")
    if bundle["artifact_format_version"] != 1:
        raise ValueError("model artifact format version is unsupported")
    if not isinstance(bundle["model_identifier"], str) or not bundle["model_identifier"] or not isinstance(bundle["model_version"], str) or not bundle["model_version"]:
        raise ValueError("model artifact identity is invalid")
    if metadata is not None and (metadata.get("model_identifier") != bundle["model_identifier"] or metadata.get("model_version") != bundle["model_version"]):
        raise ValueError("model metadata identity does not match the serialized artifact")
    if bundle["data_mode"] != "synthetic" or not isinstance(bundle["training_data_provenance"], dict) or bundle["training_data_provenance"].get("actual_nop_data_used") is not False:
        raise ValueError("model artifact provenance is missing or not explicitly synthetic")
    if not callable(getattr(bundle["model"], "predict", None)):
        raise ValueError("model artifact does not contain a prediction estimator")
    if tuple(bundle["feature_columns"]) != FEATURE_COLUMNS:
        raise ValueError("model artifact feature definition is incompatible with this inference module")
    if hasattr(bundle["model"], "feature_names_in_") and tuple(bundle["model"].feature_names_in_) != FEATURE_COLUMNS:
        raise ValueError("serialized estimator feature order does not match the current feature definition")

    if override_periods is None:
        if not isinstance(bundle["history_periods"], list) or not isinstance(bundle["history_counts"], list) or len(bundle["history_periods"]) != len(bundle["history_counts"]):
            raise ValueError("model artifact history is malformed")
        history_periods = list(bundle["history_periods"])
        history_counts = [float(value) for value in bundle["history_counts"]]
        history_source = "bundled model-fit history"
    else:
        history_periods, history_counts = override_periods, override_counts
        history_source = "caller-supplied history (unverified; approval not asserted)"
    if len(history_counts) < 12:
        raise ValueError("model history must contain at least 12 monthly observations")
    next_period = str(pd.Period(history_periods[-1], freq="M") + 1)
    build_feature_row(next_period, history_periods, history_counts)

    predictions: list[dict[str, Any]] = []
    for _ in range(periods_ahead):
        next_period = str(pd.Period(history_periods[-1], freq="M") + 1)
        row = build_feature_row(next_period, history_periods, history_counts)
        raw_prediction = np.asarray(bundle["model"].predict(pd.DataFrame([row], columns=FEATURE_COLUMNS)), dtype=float)
        if raw_prediction.shape != (1,) or not np.isfinite(raw_prediction[0]):
            raise ValueError("model returned an invalid non-finite prediction")
        value = max(0.0, float(raw_prediction[0]))
        predictions.append({"period": next_period, "predicted_invoice_volume": value})
        history_periods.append(next_period)
        history_counts.append(value)

    return {
        "model_identifier": bundle["model_identifier"],
        "model_version": bundle["model_version"],
        "prediction_target": bundle["target_description"],
        "prediction_periods": predictions,
        "data_provenance": {
            "training_data_mode": bundle["data_mode"],
            "training_data": bundle["training_data_provenance"],
            "prediction_history_source": history_source,
        },
        "known_limitations": list(bundle["known_limitations"]),
    }
