"""Chronological, group-isolated regression for explicitly prepared targets."""

from collections import defaultdict
from datetime import date, datetime, timezone
from io import BytesIO
import csv
import hashlib
import json
import math
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

from features.tabular_regression import feature_frame, feature_names, preprocessor
from training.monthly_regression import _atomic_json, _atomic_joblib


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(actual, prediction, groups):
    actual, prediction = np.asarray(actual, dtype=float), np.asarray(prediction, dtype=float)
    if len(actual) != len(prediction) or not len(actual) or not np.isfinite(actual).all() or not np.isfinite(prediction).all():
        raise ValueError("evaluation requires equal nonempty finite arrays")
    absolute = np.abs(actual - prediction)
    denominator = np.abs(actual) + np.abs(prediction)
    smape = np.divide(200.0 * absolute, denominator, out=np.zeros_like(absolute), where=denominator != 0)
    variance = float(np.sum((actual - actual.mean()) ** 2))
    by_group = defaultdict(list)
    for group, error in zip(groups, absolute):
        by_group[str(group)].append(float(error))
    return {"mae": float(absolute.mean()), "rmse": float(np.sqrt(np.mean((actual - prediction) ** 2))),
            "r2": 1.0 - float(np.sum((actual - prediction) ** 2)) / variance if len(actual) >= 2 and variance > 0 else None,
            "smape_percent": float(smape.mean()), "observations": len(actual), "independent_groups": len(by_group),
            "document_macro_mae": float(np.mean([np.mean(values) for values in by_group.values()]))}


def split_chronologically(frame, specification):
    day_field, group_field = specification["date_column"], specification["group_column"]
    values = frame[day_field].tolist()
    for value in values:
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("dates must be canonical YYYY-MM-DD; ambiguous dates cannot be interpreted")
    if (frame[group_field].astype(str).str.strip() == "").any():
        raise ValueError("split grouping references must be nonblank")
    if frame.groupby(group_field)[day_field].nunique().max() != 1:
        raise ValueError("a grouping reference must have one consistent observation date")
    lineage = specification["lineage_column"]
    if frame[lineage].duplicated().any():
        raise ValueError("source-row lineage must be unique; duplicate source content is retained with distinct lineage")
    days = sorted(set(values))
    fractions = specification["split_day_fractions"]
    if not isinstance(fractions, list) or len(fractions) != 3 or any(type(x) not in {int, float} or x <= 0 for x in fractions) or not math.isclose(sum(fractions), 1.0):
        raise ValueError("three positive chronological fractions must sum to one")
    first, second = int(len(days) * fractions[0]), int(len(days) * (fractions[0] + fractions[1]))
    bounds = {"train": days[:first], "validation": days[first:second], "test": days[second:]}
    splits, descriptions = {}, {}
    for label, selected_days in bounds.items():
        selected = frame[frame[day_field].isin(selected_days)].copy()
        n_groups = selected[group_field].nunique()
        if n_groups < specification["minimum_groups"][label] or len(selected_days) < specification["minimum_days"][label]:
            raise ValueError(f"insufficient independent observations for {label}: {n_groups} references, {len(selected_days)} dates")
        splits[label] = selected
        descriptions[label] = {"rows":len(selected), "independent_groups":int(n_groups), "days":len(selected_days), "start":selected_days[0], "end":selected_days[-1]}
    if not descriptions["train"]["end"] < descriptions["validation"]["start"] <= descriptions["validation"]["end"] < descriptions["test"]["start"]:
        raise AssertionError("chronological partitions overlap")
    group_sets = [set(splits[label][group_field]) for label in ("train", "validation", "test")]
    if any(group_sets[a] & group_sets[b] for a, b in ((0,1),(0,2),(1,2))):
        raise AssertionError("grouping references cross partition boundaries")
    return splits, descriptions


def _weights(frame, group_field):
    counts = frame[group_field].value_counts()
    return np.asarray([1.0 / counts[group] for group in frame[group_field]], dtype=float)


def _baseline(training, requested, specification):
    target, quantity, category = specification["target_column"], specification["baseline"]["quantity_field"], specification["baseline"]["category_field"]
    if (training[quantity] <= 0).any() or (requested[quantity] <= 0).any():
        raise ValueError("quantity-scaled baseline requires strictly positive quantities")
    rates = training[target] / training[quantity]
    grouped = rates.groupby(training[category]).median().to_dict()
    global_rate = float(rates.median())
    return {"constant_training_median":np.full(len(requested), float(training[target].median())),
            "quantity_scaled_item_median":np.asarray([float(quantity_value) * grouped.get(code, global_rate)
                for quantity_value, code in zip(requested[quantity], requested[category])])}


def _pipeline(schema, algorithm, parameters, seed):
    estimator = Ridge(solver="lsqr", **parameters) if algorithm == "ridge_regression" else RandomForestRegressor(random_state=seed, n_jobs=1, **parameters)
    return Pipeline([("features", preprocessor(schema)), ("regressor", estimator)])


def _source_matches(metadata, root):
    source = (Path(root) / metadata["source_file"]).resolve()
    if not source.is_relative_to(Path(root).resolve()) or digest(source) != metadata["source_file_sha256"]:
        raise ValueError("raw source integrity failed")


def train_tabular_regressors(dataset_path, specification, output_dir, *, project_root, version="1.0.0", seed=20261103):
    if type(seed) is not int or seed < 0 or not isinstance(version, str) or not version:
        raise ValueError("an explicit version and nonnegative integer seed are required")
    source, output = Path(dataset_path), Path(output_dir)
    if not output.resolve().is_relative_to(Path(project_root).resolve()):
        raise ValueError("model output must remain inside the selected project root")
    if output.exists():
        raise FileExistsError("a registered model version cannot be overwritten")
    payload = source.read_bytes()
    dataset_hash = hashlib.sha256(payload).hexdigest()
    metadata = json.loads(source.with_name(source.stem + ".metadata.json").read_text(encoding="utf-8-sig"))
    if metadata.get("dataset_sha256") != dataset_hash or metadata.get("business_approved") is not False:
        raise ValueError("training requires integrity-verified exploratory prepared data")
    if not metadata.get("data_mode") or "synthetic" in metadata["data_mode"].casefold():
        raise ValueError("synthetic data cannot be supplied to the actual-data trainer")
    if any(specification.get(key) != metadata.get(key) for key in ("objective_id", "target_definition", "data_mode")):
        raise ValueError("objective specification and dataset metadata do not agree")
    _source_matches(metadata, project_root)
    names = feature_names(specification["features"])
    if set(names) & set(specification["forbidden_features"]):
        raise ValueError("target, identities, dates and post-outcome fields cannot be input features")
    categorical = specification["features"]["categorical_features"]
    frame = pd.read_csv(BytesIO(payload), keep_default_na=False, dtype={name:str for name in [*categorical, specification["group_column"], specification["date_column"]]})
    required = set(names + [specification[key] for key in ("target_column", "date_column", "group_column", "lineage_column")])
    if not required <= set(frame.columns):
        raise ValueError("prepared dataset does not match its input specification")
    feature_frame(frame[names].to_dict("records"), specification["features"])
    target, groups = specification["target_column"], specification["group_column"]
    frame[target] = pd.to_numeric(frame[target], errors="raise")
    if not np.isfinite(frame[target]).all() or (frame[target] < specification["prediction_minimum"]).any():
        raise ValueError("target is nonfinite or outside the specified target range")
    splits, descriptions = split_chronologically(frame, specification)
    training, validation, test = (splits[key] for key in ("train", "validation", "test"))
    choices = {"ridge_regression":[{"alpha":1.0},{"alpha":10.0},{"alpha":100.0}],
               "random_forest":[{"n_estimators":200,"max_depth":6,"min_samples_leaf":3}, {"n_estimators":200,"max_depth":None,"min_samples_leaf":5}]}
    floor = specification["prediction_minimum"]
    baseline_validation = _baseline(training, validation, specification)
    fitted_data = pd.concat([training, validation], ignore_index=True)
    baseline_test = _baseline(fitted_data, test, specification)
    results, records, trained = {}, [], {}
    for algorithm, candidates in choices.items():
        trials = []
        for parameters in candidates:
            model = _pipeline(specification["features"], algorithm, parameters, seed)
            model.fit(training[names], training[target], regressor__sample_weight=_weights(training, groups))
            prediction = np.maximum(floor, model.predict(validation[names]))
            trials.append((metrics(validation[target], prediction, validation[groups]), parameters, prediction))
        chosen = min(trials, key=lambda trial:trial[0]["document_macro_mae"])
        final_model = _pipeline(specification["features"], algorithm, chosen[1], seed)
        final_model.fit(fitted_data[names], fitted_data[target], regressor__sample_weight=_weights(fitted_data, groups))
        test_prediction = np.maximum(floor, final_model.predict(test[names]))
        trained[algorithm] = final_model
        results[algorithm] = {"algorithm":algorithm,"parameters":chosen[1], "validation":chosen[0],
            "test":metrics(test[target], test_prediction, test[groups]),
            "training":metrics(fitted_data[target], np.maximum(floor,final_model.predict(fitted_data[names])), fitted_data[groups]),
            "validation_trials":[{"parameters":trial[1],"validation":trial[0]} for trial in trials],
            "baselines":{"validation":{name:metrics(validation[target], prediction, validation[groups]) for name,prediction in baseline_validation.items()},
                         "test":{name:metrics(test[target],prediction,test[groups]) for name,prediction in baseline_test.items()}},
            "test_unseen_category_rows":int((~test[categorical[0]].isin(fitted_data[categorical[0]])).sum()) if categorical else 0,
            "test_unseen_category_fraction":float((~test[categorical[0]].isin(fitted_data[categorical[0]])).mean()) if categorical else 0.0}
        for label, data, predictions, baselines in (("validation",validation,chosen[2],baseline_validation),("test",test,test_prediction,baseline_test)):
            for position, (_, row) in enumerate(data.iterrows()):
                records.append({"algorithm":algorithm,"split":label,"source_row":row[specification["lineage_column"]],
                    "document_id":row[groups],"event_date":row[specification["date_column"]],"actual":float(row[target]),"prediction":float(predictions[position]),
                    **{name:float(values[position]) for name,values in baselines.items()}})
    selected = min(results, key=lambda name:results[name]["validation"]["document_macro_mae"])
    baseline_score = results[selected]["baselines"]["validation"]["quantity_scaled_item_median"]["document_macro_mae"]
    selected_if_better = selected if results[selected]["validation"]["document_macro_mae"] < baseline_score else None
    evaluation = {"objective_id":specification["objective_id"],"target_definition":specification["target_definition"],
        "dataset_id":metadata["dataset_id"],"dataset_version":metadata["dataset_version"],"dataset_sha256":dataset_hash,
        "eligible_observations":len(frame),"eligible_independent_groups":int(frame[groups].nunique()),"split":descriptions,
        "saved_fit":{"rows":len(fitted_data),"independent_groups":int(fitted_data[groups].nunique()),"through":descriptions["validation"]["end"]},
        "models":results,"validation_selected_model":selected_if_better,"business_champion":None,
        "selection_rule":"lowest validation document-macro MAE, only if below the predefined quantity-scaled item-median baseline; test is not used for tuning",
        "test_use":"one chronological holdout; saved estimator is fitted on train plus validation only",
        "group_weighting":"inverse detail-row count per reference", "feature_schema":specification["features"],
        "seed":seed,"model_version":version,"business_approved":False,"data_mode":metadata["data_mode"],
        "dependency_versions":{"python":platform.python_version(),"scikit_learn":sklearn.__version__,"numpy":np.__version__,"pandas":pd.__version__,"joblib":joblib.__version__},
        "training_timestamp_utc":datetime.now(timezone.utc).isoformat()}
    if digest(source) != dataset_hash:
        raise ValueError("prepared dataset changed during training")
    _source_matches(metadata, project_root)
    output.mkdir(parents=True, exist_ok=False)
    for algorithm, model in trained.items():
        model_id = f"{specification['objective_id']}-{algorithm}-v{version}"
        bundle = {"artifact_format_version":1,"model":model,"model_identifier":model_id,"model_version":version,
            "objective_id":specification["objective_id"],"target_definition":specification["target_definition"],
            "feature_schema":specification["features"],"feature_names":names,"prediction_minimum":floor,
            "dataset_id":metadata["dataset_id"],"dataset_version":metadata["dataset_version"],"dataset_sha256":dataset_hash,
            "data_mode":metadata["data_mode"],"business_approved":False,"known_limitations":metadata["limitations"],
            "source_provenance":metadata,"dependency_versions":evaluation["dependency_versions"],
            "known_categories":{name:sorted(set(fitted_data[name])) for name in categorical}}
        artifact = output / (algorithm + ".joblib")
        _atomic_joblib(artifact,bundle)
        sidecar = {key:value for key,value in bundle.items() if key not in {"model","known_categories"}}
        sidecar.update(algorithm=algorithm,parameters=results[algorithm]["parameters"],inference_adapter="tabular_regression_v1",problem_type="regression",
            artifact_path=artifact.resolve().relative_to(Path(project_root).resolve()).as_posix(),artifact_sha256=digest(artifact),training_configuration={"seed":seed,"split":descriptions,"sample_weighting":evaluation["group_weighting"]},
            training_observations=len(fitted_data),training_independent_groups=int(fitted_data[groups].nunique()),training_date_range={"start":descriptions["train"]["start"],"end":descriptions["validation"]["end"]},
            evaluation=results[algorithm],training_timestamp_utc=evaluation["training_timestamp_utc"],
            prediction_frequency="one estimate per supplied detail-row feature record",supported_horizon=None,
            horizon_not_applicable_reason="tabular field estimation; this model does not forecast monthly totals",
            intended_use="exploratory offline raw-field estimation only",recommended_for_business_use=False)
        _atomic_json(output/(algorithm+".metadata.json"),sidecar)
        results[algorithm].update(artifact_path=sidecar["artifact_path"],artifact_sha256=sidecar["artifact_sha256"])
    _atomic_json(output/"evaluation_metrics.json",evaluation)
    with (output/"holdout_predictions.csv").open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    assignments=[]
    for label,data in splits.items():
        assignments.extend({"source_row":row[specification["lineage_column"]],"document_id":row[groups],"event_date":row[specification["date_column"]],"split":label} for _,row in data.iterrows())
    with (output/"split_assignments.csv").open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(assignments[0]));writer.writeheader();writer.writerows(assignments)
    _atomic_json(output/"training_specification.json",specification)
    return evaluation
