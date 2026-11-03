# NOP ML model integration guide

## Current collection and selection status

The collection contains **seven actual-source predictors: five ML models and two fitted baselines**. The synthetic demonstration remains separate. All actual-source predictors are exploratory and `business_approved: false`. No production champion was selected.

- Four prior actual-source models are preserved: two monthly count models and two v1 raw line-value regressors.
- The newly persisted item/quantity median and monthly last-value baselines are the preferred exploratory reference methods on available evidence.
- A quantity-normalized Ridge v2 candidate was assessed and retained as a research artifact. It lost to the item/quantity baseline on all three rolling-origin development folds.

See [the model catalogue](../../reports/nop_ml_model_catalogue.md), [machine-readable index](../../models/model_catalogue.json), and [assessment report](../../reports/nop_actual_data_ml_training_report.md). The index distinguishes ML from baselines and historical tests from previously inspected audit periods.

## Artifact paths

| Predictor | Artifact |
| --- | --- |
| Item/quantity median baseline, v2 | `models/business_regression/nop_domestic_invoice_line_value/v2/item_quantity_median_baseline.joblib` |
| Quantity-normalized Ridge, v2 | `models/business_regression/nop_domestic_invoice_line_value/v2/quantity_normalized_ridge.joblib` |
| Original Ridge, v1 | `models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.joblib` |
| Original Random Forest, v1 | `models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.joblib` |
| Monthly last-value baseline, v1 | `models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/last_observed_value.joblib` |
| Original monthly Linear Regression | `models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib` |
| Original monthly Random Forest | `models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib` |

Each artifact has a matching `.metadata.json`. Preserve model identifiers, versions, target definitions, dataset versions/fingerprints, dependency records, evaluation roles and limitations when displaying results. Newly added custom estimators require `src/prediction/tabular_estimators.py` alongside the existing inference and feature modules; all fitted preprocessing and learned state are inside the bundle. Inference does not import the training orchestration modules or require the training session.

## Environment

From the repository root:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -c "import sklearn; print(sklearn.__version__)"
```

The verified artifacts use Python 3.12.10, scikit-learn 1.8.0, NumPy 2.4.4, pandas 3.0.2 and joblib 1.5.3. Match the selected sidecar rather than assuming the project environment matches. No packages were installed or upgraded in this assessment.

## Raw line-value inference

The target is the stored native `Taxable Value` field in a restricted source-row population. It is not an approved revenue, profit, price-policy, demand or monthly-total measure. Source amount units and physical quantity units remain unverified. Callers must supply records within the documented population.

```python
import json
from pathlib import Path
from prediction.tabular_regression import predict_tabular_regression

root = Path.cwd()
request = json.loads(
    (root / "evaluation/actual_data_ml_assessment/v2/example_tabular_request.json")
    .read_text(encoding="utf-8")
)

for name in ("item_quantity_median_baseline", "quantity_normalized_ridge"):
    response = predict_tabular_regression(
        request,
        model_path=(
            root / "models/business_regression/nop_domestic_invoice_line_value/v2"
            / f"{name}.joblib"
        ),
    )
    print(json.dumps(response, allow_nan=False))
```

The supplied example contains actual retained rows:

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

Model version 2.0.0 still uses dataset version 1.0.0. Each row must contain exactly the declared features: positive finite native numeric quantity and a nonblank raw item-code string. There is no date, amount, unit-price or document-ID input. Missing values, numeric strings, extra fields and mismatched expected identities/versions fail validation.

The v2 baseline learns median target/quantity per item code from development rows and a training-only global median fallback. Normalized Ridge learns target/quantity using the existing numeric scaler and one-hot encoder, then multiplies by the supplied quantity. The unit-price source field is never an input. Unseen item codes are counted in the response. Negative Ridge estimates are bounded at zero according to the declared prediction minimum; source records are never zero-filled.

Responses contain model ID/version, objective/target, dataset ID/version/hash, data mode, provenance, limitations, `business_approved: false`, unseen-category counts, and one finite `prediction` per `row_index`.

Actual examples: [baseline response](../../evaluation/actual_data_ml_assessment/v2/item_quantity_median_baseline_example_response.json) and [normalized Ridge response](../../evaluation/actual_data_ml_assessment/v2/quantity_normalized_ridge_example_response.json). The same function continues to support both retained v1 regressors.

## Monthly count baseline and retained models

```python
from prediction.monthly_regression import predict_monthly_objective

response = predict_monthly_objective(
    {"periods_ahead": 2},
    model_path=(
        "models/business_forecasting/nop_confirmed_date_invoice_subset/"
        "baselines/v1/last_observed_value.joblib"
    ),
)
```

The baseline's deployment state uses the last eligible source month, August 2026, with count 8. The interface starts after the stored September source cutoff, so the example returns October and November 2026 estimates of 8. It does not automatically anchor forecasts to today's date. [Actual response](../../evaluation/actual_data_ml_assessment/v2/example_monthly_baseline_response.json).

Its historical two-step evaluation used a June 2026 cutoff and repeated 19 for July/August. That evaluation state differs from the later deployment state. Do not recompute old test accuracy using the refitted deployment state. The two-test-month MAE/RMSE of 7.00/8.06 is weak historical evidence, not independent validation from this assessment. Seasonal-naive forecasting is unsupported with only eight eligible months.

The existing monthly Linear Regression and Random Forest remain callable with the same interface and their original artifact paths. The software horizon is 1–24 months; a reliable business horizon has not been validated.

## Discovery and adapter contract

The existing model scanner discovers metadata; it is not necessary to add question-to-model mappings. Enumerate current metadata rather than assuming a fixed number of models. The current collection has three monthly predictors and four feature-row predictors.

- `MonthlyRegressionQueryAdapter` supports declared `monthly_regression_v1` artifacts.
- `TabularRegressionInferenceAdapter` supports declared `tabular_regression_v1` artifacts.
- Both expose `supports(metadata)` and `predict(path, inputs)`.

Feature-row requests require `rows`; they cannot be invoked using a future-period horizon. The teammate owns routing, language interpretation, MCP, APIs and UI. No such component was implemented or modified during this ML assessment.

## Evaluation interpretation

Three development folds produced 79 predictions across 52 reference groups. Pooled document-macro MAE was **77,135.63** for the item/quantity baseline and **139,302.56** for normalized Ridge with alpha 1. The candidate won zero folds.

On the previously inspected 30-row test period, baseline MAE/RMSE was **72,255.50/190,675.29** and normalized Ridge **131,795.20/238,800.71**. These v2 scores are retrospective audits, not a new untouched test. The normalized candidate's lower audit error than v1 Ridge does not justify promotion. No model or baseline is approved for business decisions.

The saved v2 tabular states use only the original 135 development rows through 25 June 2026. All 30 original test rows are excluded. Baseline errors are substantially higher on unseen item codes (11/30 audit rows). Sparse items, unresolved source dates, incomplete extraction, units/currency uncertainty and repeated product/customer dependence restrict generalization.

## Reproduce the assessment without overwriting versions

The source dataset is frozen. The plan was saved before fitting:

```python
import json
from pathlib import Path
from training.improve_tabular_models import assess_and_improve

root = Path.cwd()
data = root / "data/nop_domestic_invoice_line_value/v1"
spec = json.loads((data / "training_spec.json").read_text(encoding="utf-8"))
new_model_version = "2.0.1"
unused_output_directory = (
    root / "models/business_regression/nop_domestic_invoice_line_value/v2_0_1"
)
assert not unused_output_directory.exists(), "Choose an unused version/directory"
result = assess_and_improve(
    data / "observations.csv",
    spec,
    root / "models/business_regression/nop_domestic_invoice_line_value/v1/split_assignments.csv",
    root / "evaluation/actual_data_ml_assessment/v2/evaluation_plan.json",
    unused_output_directory,
    project_root=root,
    version=new_model_version,
)
```

Choose an unused output/version. Existing destinations are rejected. The monthly baseline reproduction function is `training.evaluate_monthly_baselines.evaluate_monthly_baselines`; its arguments are the existing dataset/specification, prior evaluation path, unused baseline directory and project root. No source rows or missing periods are generated.

The six requested aggregate/item prediction candidates and their missing requirements are in the [feasibility matrix](../../evaluation/actual_data_ml_assessment/v2/prediction_target_feasibility.json). Their unresolved semantics or history must be supplied before new forecasting development. A new untouched prospective dataset is required before treating any v2 optimization result as independently validated performance.

## Open integration-test expectation

Four existing `tests.test_dynamic_business_query` assertions expect exactly two monthly artifacts and now fail with `3 != 2`, since discovery includes the legitimate saved monthly baseline. The unchanged service returned three forecasts in the recorded runtime check. These tests and teammate-owned modules were left unchanged. The integration owner should derive expected results from eligible artifact IDs, preserving integrity and dependency checks. See the [recorded failures](../../evaluation/actual_data_ml_assessment/v2/framework_inventory_regression_results.json). The full repository suite has not been claimed to pass.
