# NOP ML model integration guide

The ML delivery contains two newly trained raw-field regression models and the two preserved monthly invoice-subset models. Every model is exploratory. The new regressors performed worse than their predefined item/quantity baseline and are not recommended for business decisions. See [the training report](../../reports/nop_actual_data_ml_training_report.md) and [model catalogue](../../models/model_catalogue.json).

## Artifacts and intended targets

| Model | Artifact | Intended target |
| --- | --- | --- |
| New Ridge regression | `models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.joblib` | Stored line `Taxable Value` for the explicitly filtered, date-resolved domestic goods population. |
| New Random Forest | `models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.joblib` | The same raw-field target. |
| Existing Linear Regression | `models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib` | Confirmed-date invoice-reference counts per observed month. |
| Existing Random Forest | `models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib` | The same monthly subset count. |

Matching `.metadata.json` files contain target definitions, provenance, feature schema, dataset fingerprints, dependencies and evaluation results. The new serialized bundles contain the complete fitted scikit-learn preprocessing/model pipeline. Neither new model is a monthly revenue, sales-total, profit, demand or inventory forecaster. No new model replaces the existing monthly artifacts.

## Environment

Run from the repository root using the interpreter that matches artifact metadata:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -c "import sklearn; print(sklearn.__version__)"
```

The verified interpreter was Python 3.12.10 with scikit-learn 1.8.0, NumPy 2.4.4, pandas 3.0.2 and joblib 1.5.3. During this task `.venv` had a different scikit-learn version; new inference rejects mismatched dependency versions before loading. No dependency was installed or upgraded. Use the sidecar metadata as the compatibility record.

## New regression interface

```python
import json
from pathlib import Path
from prediction.tabular_regression import predict_tabular_regression

root = Path.cwd()
request = json.loads(
    (root / "evaluation/actual_data_ml_training/v1/example_request.json")
    .read_text(encoding="utf-8")
)

for algorithm in ("ridge_regression", "random_forest"):
    response = predict_tabular_regression(
        request,
        model_path=(
            root / "models/business_regression/nop_domestic_invoice_line_value/v1"
            / f"{algorithm}.joblib"
        ),
    )
    print(json.dumps(response, allow_nan=False))
```

The example uses actual retained holdout rows:

```json
{
  "rows": [
    {"quantity": 4, "item_code": "FG00100"},
    {"quantity": 10, "item_code": "FG00087"}
  ],
  "expected_objective_id": "nop-domestic-confirmed-date-line-value",
  "expected_dataset_id": "nop-domestic-confirmed-date-line-value",
  "expected_dataset_version": "1.0.0"
}
```

Each row must contain exactly a positive finite native number `quantity` and a nonblank string `item_code`. Strings are preserved; item codes are not numerically converted. Missing values, numeric strings, booleans, nonfinite quantities, unknown input fields and target/identifier additions raise explicit errors. The optional expected identity/version fields reject use of an incompatible dataset or objective.

The inference function checks the model SHA-256, dependency versions, metadata/bundle identity, target definition, feature schema and feature ordering. It then uses the serialized preprocessing and fitted estimator. Unseen item codes are permitted by the declared one-hot policy and counted in the response; estimates for them have no learned item effect. Negative model estimates are clipped to the declared numerical minimum of zero. This postprocessing does not fill any missing source value.

The response includes:

- Model ID/version and exact objective/target definition.
- Dataset ID/version/hash, source references and data mode.
- `business_approved: false`.
- One finite numeric estimate per input row, identified by `row_index`.
- Unseen-category counts and known limitations.

For the first example row, the recorded Ridge estimate is approximately `197293.0661` in unspecified source amount units. Expected full responses are [Ridge](../../evaluation/actual_data_ml_training/v1/ridge_regression_example_response.json) and [Random Forest](../../evaluation/actual_data_ml_training/v1/random_forest_example_response.json). These are estimates of a stored source field, not recognized-revenue figures or approved prices.

## Model discovery and adapter contract

The existing artifact scanner discovered all four actual-source models and both prepared datasets. Verification is in [adapter_discovery_verification.json](../../evaluation/actual_data_ml_training/v1/adapter_discovery_verification.json).

New metadata declares:

```json
{
  "inference_adapter": "tabular_regression_v1",
  "problem_type": "regression",
  "prediction_frequency": "one estimate per supplied detail-row feature record",
  "supported_horizon": null
}
```

A trusted host can register `prediction.model_adapters.TabularRegressionInferenceAdapter`. It exposes the existing adapter shape:

```python
from prediction.model_adapters import TabularRegressionInferenceAdapter

adapter = TabularRegressionInferenceAdapter()
assert adapter.supports(metadata)
response = adapter.predict(model_path, request)
```

Route feature-row regression requests to this adapter or directly to `predict_tabular_regression`. The framework's current monthly forecast path supplies horizons; it does not supply tabular feature rows. A teammate-owned tabular task handler must provide the documented rows. The ML delivery does not change natural-language interpretation, MCP, APIs, UI or the query service.

## Existing monthly models

Their original artifacts and metadata were preserved without retraining:

```python
from prediction.monthly_regression import predict_monthly_objective

response = predict_monthly_objective(
    {"periods_ahead": 2},
    model_path=(
        "models/business_forecasting/nop_confirmed_date_invoice_subset/"
        "linear_regression.joblib"
    ),
)
```

Use `random_forest.joblib` for the other existing model. The forecast starts after the stored September 2026 source cutoff and refers only to confirmed-date references. It is not automatically anchored to today's date. The existing monthly adapter remains unchanged in behavior.

## Preparation and training reproduction

The delivery commands were executed against actual source data. Output versions are exclusively created; rerunning the same version intentionally refuses overwrite.

Preparation uses the supplied source-specific specification:

```powershell
python -m features.prepare_invoice_line_value `
  --root . `
  --spec data/preparation_specs/nop_domestic_invoice_line_value_v1.json `
  --output data/nop_domestic_invoice_line_value/v1
```

For a new authorized data version, copy/update the specification's version and select a new output directory. Do not change original workbooks. Then train through the reusable ML function with a new model-version directory:

```python
import json
from pathlib import Path
from training.tabular_regression import train_tabular_regressors

# Choose a newly prepared dataset and an unused output/version.
specification = json.loads(training_spec_path.read_text(encoding="utf-8"))
evaluation = train_tabular_regressors(
    dataset_path,
    specification,
    unused_model_output_directory,
    project_root=Path.cwd(),
    version=new_model_version,
    seed=20261103,
)
```

The source-specific delivery runner is `python -m training.nop_actual_data_ml --evaluation evaluation/actual_data_ml_training/v1`. Its outputs already exist; it preserves versioned outputs and catalogue files. Do not remove existing artifacts to rerun it. Generic preparation/training functions accept new paths and explicit specifications for subsequent versions.

Training uses only item code and quantity. The unit-price field is an arithmetic diagnostic and is never a predictor. Document references, source-row IDs, dates, amounts, taxes and document totals are excluded from the feature pipeline. Every reference belongs to one chronological partition; preprocessing and baselines are learned only from the permitted earlier data. Hyperparameters use validation document-macro MAE. Saved estimators fit train plus validation only, allowing their test predictions to be independently reproduced.

## Evaluation and release status

The new target has 165 retained lines, 111 references and 77 observed dates. Train/validation/test contain 101/34/30 lines and 65/25/21 references respectively. Eleven of 30 test rows have unseen item codes.

| Estimator | Test MAE | Test RMSE | Test R² | Test SMAPE |
| --- | ---: | ---: | ---: | ---: |
| Ridge | 140,357.11 | 250,029.56 | -0.0539 | 73.09% |
| Random Forest | 179,683.29 | 306,937.27 | -0.5882 | 73.13% |
| Item/quantity median baseline | 72,255.50 | 190,675.29 | 0.3871 | 31.29% |

The baseline outperformed both ML estimators. No champion was selected. Amounts are source-native numeric units; currency and recognition rules are not established. The selected population excludes unresolved dates, exports and services. These models are suitable for inspecting offline raw-field modeling and integration behavior only; prospective business performance is unverified.

Source-to-output lineage is in the prepared CSV and exclusions file. [Holdout predictions](../../models/business_regression/nop_domestic_invoice_line_value/v1/holdout_predictions.csv), [split assignments](../../models/business_regression/nop_domestic_invoice_line_value/v1/split_assignments.csv), [evaluation metrics](../../models/business_regression/nop_domestic_invoice_line_value/v1/evaluation_metrics.json) and [fresh-process verification](../../evaluation/actual_data_ml_training/v1/new_model_verification.json) provide the executed evidence.
