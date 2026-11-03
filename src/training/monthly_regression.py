"""Reusable chronological regression comparison for monthly series.

Input column mappings and target meaning come from an explicit JSON spec; this
module contains no NOP field names or business objective mappings.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import tempfile
import argparse

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists(): temp.unlink()


def _atomic_joblib(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
        joblib.dump(value, temp)
        with temp.open("rb+") as stream: os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists(): temp.unlink()


def _period_index(periods: list[str]) -> np.ndarray:
    return np.asarray([pd.Period(value, freq="M").ordinal for value in periods], dtype=float)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    return {"mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
            "observations": int(len(actual))}


def _model_factories(seed: int) -> dict:
    return {
        "linear_regression": (lambda: make_pipeline(StandardScaler(), LinearRegression()),
                              {"scaler": "StandardScaler", "regressor": "LinearRegression"}),
        "random_forest": (lambda: RandomForestRegressor(n_estimators=200, max_depth=2,
                              min_samples_leaf=2, random_state=seed, n_jobs=1),
                          {"n_estimators": 200, "max_depth": 2, "min_samples_leaf": 2, "random_state": seed, "n_jobs": 1}),
    }


def train_monthly_regressors(dataset_path: str | Path, spec: dict, output_dir: str | Path, *, seed: int = 20261103,
                             model_version: str = "0.1.0-exploratory") -> dict:
    """Evaluate two tabular regressors chronologically and save independent bundles.

    The latest two eligible months are test data, the preceding month is a
    one-point validation window, and earlier periods are training data. This
    modest split is intended for short exploratory series only.
    """
    required_spec = {"objective_id", "objective_name", "target_definition", "period_column", "target_column",
                     "eligibility_column", "eligible_values", "data_mode"}
    if not isinstance(spec, dict) or set(spec) != required_spec:
        raise ValueError("spec must explicitly define objective, target, period, eligibility, and data mode")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("model_version must be a nonempty string")
    if not isinstance(spec["data_mode"], str) or not spec["data_mode"].strip() or "synthetic" in spec["data_mode"].casefold():
        raise ValueError("supply an explicit non-synthetic data mode for exploratory prepared-data training")
    source = Path(dataset_path)
    output = Path(output_dir)
    if not source.is_file(): raise FileNotFoundError(source)
    frame = pd.read_csv(source)
    needed = [spec["period_column"], spec["target_column"], spec["eligibility_column"]]
    if any(name not in frame.columns for name in needed): raise ValueError("dataset does not match the explicit objective spec")
    selected = frame[frame[spec["eligibility_column"]].isin(spec["eligible_values"])].copy()
    if selected[needed].isnull().any().any(): raise ValueError("eligible rows cannot contain missing period, target, or eligibility values")
    periods = selected[spec["period_column"]].astype(str).tolist()
    parsed = [pd.Period(value, freq="M") for value in periods]
    if any(str(p) != value for p, value in zip(parsed, periods)):
        raise ValueError("periods must use canonical YYYY-MM values")
    if parsed != sorted(parsed) or len(set(parsed)) != len(parsed): raise ValueError("periods must be unique and chronological")
    if any(b.ordinal - a.ordinal != 1 for a, b in zip(parsed, parsed[1:])):
        raise ValueError("eligible monthly observations must be consecutive; missing periods are not filled")
    y = pd.to_numeric(selected[spec["target_column"]], errors="raise").to_numpy(dtype=float)
    if len(y) < 8 or not np.isfinite(y).all() or (y < 0).any():
        raise ValueError("at least eight finite non-negative monthly targets are required for this exploratory split")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0: raise ValueError("seed must be a non-negative integer")

    test_n, validation_n = 2, 1
    train_n = len(y) - test_n - validation_n
    if train_n < 5: raise ValueError("chronological training split must contain at least five periods")
    origin_ordinal = parsed[0].ordinal
    x = (_period_index(periods) - origin_ordinal).reshape(-1, 1)
    train_x, train_y = x[:train_n], y[:train_n]
    validation_x, validation_y = x[train_n:train_n + validation_n], y[train_n:train_n + validation_n]
    test_x, test_y = x[train_n + validation_n:], y[train_n + validation_n:]
    factories = _model_factories(seed)
    results = {}
    for name, (factory, parameters) in factories.items():
        validation_model = factory().fit(train_x, train_y)
        validation_prediction = np.maximum(0, validation_model.predict(validation_x))
        evaluation_model = factory().fit(np.vstack([train_x, validation_x]), np.concatenate([train_y, validation_y]))
        test_prediction = np.maximum(0, evaluation_model.predict(test_x))
        baseline_value = float(np.concatenate([train_y, validation_y])[-1])
        baseline_prediction = np.full(len(test_y), baseline_value, dtype=float)
        results[name] = {
            "algorithm": name, "parameters": parameters,
            "validation_periods": periods[train_n:train_n + validation_n],
            "validation": _metrics(validation_y, validation_prediction),
            "test_periods": periods[train_n + validation_n:],
            "test": _metrics(test_y, test_prediction),
            "test_predictions": [float(x) for x in test_prediction],
            "baseline": {"name": "last_observed_value", "test": _metrics(test_y, baseline_prediction),
                         "test_predictions": [float(x) for x in baseline_prediction]},
            "champion_selected": False,
            "selection_note": "Too few validation/test periods to select a reliable champion.",
        }

    metadata_path = source.with_name(source.stem + ".metadata.json")
    source_metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    source_hash = _digest(source)
    evaluation = {
        "objective_id": spec["objective_id"], "objective_name": spec["objective_name"],
        "target_definition": spec["target_definition"], "data_mode": spec["data_mode"],
        "business_approved": False, "dataset_path": str(source), "dataset_sha256": source_hash,
        "dataset_observations": len(selected), "dataset_periods": periods,
        "split": {"training_periods": periods[:train_n], "validation_periods": periods[train_n:train_n + validation_n],
                  "test_periods": periods[train_n + validation_n:], "training_count": train_n,
                  "validation_count": validation_n, "test_count": test_n},
        "feature_definition": {"name": "month_index", "description": "Integer calendar-month offset from the first eligible observation; known at prediction time."},
        "baseline_method": "constant last value at the validation cutoff for the full test horizon",
        "models": results,
        "not_trained": {name: {"reason": "This trainer implements only the two registered tabular regressors; no seasonal or additional-family evaluation was performed.",
            "dependency_available": importlib.util.find_spec(package) is not None}
            for name, package in (("xgboost", "xgboost"), ("sarimax", "statsmodels"), ("prophet", "prophet"))},
        "dependency_versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                                "numpy": np.__version__, "pandas": pd.__version__, "joblib": joblib.__version__},
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_provenance": source_metadata,
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, (factory, parameters) in factories.items():
        artifact_path = output / f"{name}.joblib"
        sidecar_path = output / f"{name}.metadata.json"
        if artifact_path.exists() or sidecar_path.exists(): raise FileExistsError(f"Refusing to overwrite an existing model version: {artifact_path}")
        final_model = factory().fit(x, y)
        bundle = {"artifact_format_version": 1, "model": final_model,
                  "model_identifier": f"{spec['objective_id']}-{name}", "model_version": model_version,
                  "objective_id": spec["objective_id"], "objective_name": spec["objective_name"],
                  "target_definition": spec["target_definition"], "data_mode": spec["data_mode"],
                  "business_approved": False, "feature_names": ["month_index"],
                  "feature_origin_period": periods[0], "training_end_period": periods[-1],
                  "latest_source_period": source_metadata.get("observation_period", {}).get("end", periods[-1]),
                  "dataset_sha256": source_hash, "training_periods": periods,
                  "training_data_provenance": source_metadata,
                  "known_limitations": source_metadata.get("limitations", []),
                  "postprocessing": "clip predictions below zero to zero; retain expected counts as float",
                  "parameters": parameters}
        _atomic_joblib(artifact_path, bundle)
        model_result = results[name]
        sidecar = {"inference_adapter": "monthly_regression_v1", "model_identifier": bundle["model_identifier"], "model_version": bundle["model_version"],
                   "artifact_format_version": 1, "feature_names": bundle["feature_names"], "feature_definition": evaluation["feature_definition"],
                   "algorithm": name, "parameters": parameters, "objective_id": bundle["objective_id"],
                   "target_definition": bundle["target_definition"], "data_mode": bundle["data_mode"],
                   "business_approved": False, "artifact_path": str(artifact_path),
                   "artifact_sha256": _digest(artifact_path), "dataset_sha256": source_hash,
                   "training_periods": periods, "evaluation": model_result,
                   "source_provenance": source_metadata, "dependency_versions": evaluation["dependency_versions"],
                   "training_timestamp_utc": evaluation["training_timestamp_utc"],
                   "known_limitations": bundle["known_limitations"]}
        _atomic_json(sidecar_path, sidecar)
        results[name]["artifact_path"] = str(artifact_path)
        results[name]["artifact_sha256"] = sidecar["artifact_sha256"]
    evaluation_path = output / "evaluation_metrics.json"
    if evaluation_path.exists(): raise FileExistsError(f"Refusing to overwrite evaluation results: {evaluation_path}")
    _atomic_json(evaluation_path, evaluation)
    return evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--seed", type=int, default=20261103)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    result = train_monthly_regressors(args.dataset, spec, args.output_dir, seed=args.seed)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
