"""Independent inference for versioned explicit-schema tabular regressors."""

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform

import joblib

from features.tabular_regression import feature_frame, feature_names


def _dependencies(metadata):
    versions = metadata.get("dependency_versions")
    if not isinstance(versions, dict) or not versions.get("scikit_learn"):
        raise ValueError("model dependency versions are missing")
    for key, expected in versions.items():
        if key == "python":
            current = platform.python_version()
        else:
            package = {"scikit_learn":"scikit-learn"}.get(key,key)
            try:
                current = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                raise ValueError("required model dependency is unavailable: " + package) from None
        if current != expected:
            raise ValueError(f"incompatible dependency {key}: trained={expected}, current={current}")


def predict_tabular_regression(input_data, *, model_path):
    allowed = {"rows","expected_objective_id","expected_dataset_id","expected_dataset_version"}
    if not isinstance(input_data, dict) or set(input_data)-allowed or "rows" not in input_data:
        raise ValueError("input must contain rows and only documented optional compatibility identifiers")
    model_path = Path(model_path)
    metadata_path = model_path.with_name(model_path.stem+".metadata.json")
    if not model_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("the model and matching metadata are both required")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    if metadata.get("inference_adapter") != "tabular_regression_v1" or metadata.get("problem_type") != "regression":
        raise ValueError("incompatible inference artifact family")
    if metadata.get("business_approved") is not False or "synthetic" in metadata.get("data_mode", "").casefold():
        raise ValueError("this inference interface requires an explicitly exploratory actual-source model")
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != metadata.get("artifact_sha256"):
        raise ValueError("model artifact integrity failed")
    _dependencies(metadata)
    for input_key, metadata_key in (("expected_objective_id","objective_id"),("expected_dataset_id","dataset_id"),("expected_dataset_version","dataset_version")):
        if input_key in input_data and input_data[input_key] != metadata.get(metadata_key):
            raise ValueError("requested " + input_key + " does not match the model")
    features = feature_frame(input_data["rows"], metadata["feature_schema"])
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or bundle.get("artifact_format_version") != 1 or "model" not in bundle:
        raise ValueError("unsupported or incomplete model bundle")
    for key in ("model_identifier","model_version","objective_id","target_definition","feature_schema","feature_names",
                "dataset_id","dataset_version","dataset_sha256","data_mode","business_approved","prediction_minimum","dependency_versions"):
        if key not in metadata or bundle.get(key) != metadata[key]:
            raise ValueError("model and metadata contract mismatch: " + key)
    names = feature_names(bundle["feature_schema"])
    if names != bundle["feature_names"] or list(getattr(bundle["model"],"feature_names_in_",[])) != names:
        raise ValueError("fitted feature names or ordering are incompatible")
    predictions = bundle["model"].predict(features)
    if len(predictions) != len(features):
        raise ValueError("model prediction count is inconsistent")
    output=[]
    for index, prediction in enumerate(predictions):
        raw_value=float(prediction)
        if not math.isfinite(raw_value):
            raise ValueError("model produced a nonfinite estimate")
        value=max(float(bundle["prediction_minimum"]),raw_value)
        output.append({"row_index":index,"prediction":value})
    unseen=sum(any(row[name] not in bundle["known_categories"][name] for name in bundle["feature_schema"]["categorical_features"]) for row in input_data["rows"])
    result={"model_identifier":bundle["model_identifier"],"model_version":bundle["model_version"],"objective_id":bundle["objective_id"],
        "target_definition":bundle["target_definition"],"dataset_id":bundle["dataset_id"],"dataset_version":bundle["dataset_version"],
        "dataset_sha256":bundle["dataset_sha256"],"data_mode":bundle["data_mode"],"business_approved":False,"predictions":output,
        "unseen_categorical_rows":unseen,"unknown_category_policy":"unseen one-hot categories are ignored and explicitly counted",
        "source_provenance":{key:bundle["source_provenance"].get(key) for key in ("source_file","source_file_sha256","source_sheet","dataset_id","dataset_version","dataset_sha256")},
        "known_limitations":bundle["known_limitations"]}
    json.dumps(result,allow_nan=False)
    return result
