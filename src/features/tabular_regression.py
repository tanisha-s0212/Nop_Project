"""Shared explicit-schema features for prepared tabular regression."""

import math
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def feature_names(schema):
    if not isinstance(schema, dict) or set(schema) - {"numeric_features", "categorical_features", "numeric_minimums"}:
        raise ValueError("unsupported feature specification")
    numeric, categorical = schema.get("numeric_features", []), schema.get("categorical_features", [])
    if not isinstance(numeric, list) or not isinstance(categorical, list):
        raise ValueError("feature lists must be arrays")
    names = numeric + categorical
    if not names or any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError("features must be distinct nonempty names")
    if set(schema.get("numeric_minimums", {})) - set(numeric):
        raise ValueError("numeric constraints must name numeric features")
    return names


def feature_frame(rows, schema):
    names = feature_names(schema)
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows must be a nonempty array")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != set(names):
            raise ValueError(f"row {index} must contain exactly the declared feature names")
        for name in schema.get("numeric_features", []):
            value = row[name]
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError(f"row {index} feature {name} must be a finite native number")
            if name in schema.get("numeric_minimums", {}) and value < schema["numeric_minimums"][name]:
                raise ValueError(f"row {index} feature {name} is below its documented minimum")
        for name in schema.get("categorical_features", []):
            if not isinstance(row[name], str) or not row[name].strip():
                raise ValueError(f"row {index} feature {name} must be a nonblank string")
    return pd.DataFrame(rows, columns=names)


def preprocessor(schema):
    feature_names(schema)
    transforms = []
    if schema.get("numeric_features"):
        transforms.append(("numeric", StandardScaler(), schema["numeric_features"]))
    if schema.get("categorical_features"):
        transforms.append(("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), schema["categorical_features"]))
    return ColumnTransformer(transforms, remainder="drop")
