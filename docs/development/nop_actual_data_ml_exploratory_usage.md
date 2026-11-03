# NOP confirmed-date invoice subset integration guide

This is an actual-source exploratory demonstration. Its target is a count of **confirmed-date invoice references in one workbook**, not total NOP invoice volume. It is not business-approved and should not be used for operational decisions.

## Prepare and train

From the repository root, run:

```powershell
python src/features/prepare_invoice_volume_exploratory.py
python src/training/monthly_regression.py `
  data/nop_confirmed_date_invoice_count_exploratory.csv `
  data/nop_confirmed_date_invoice_count_exploratory.spec.json `
  models/business_forecasting/nop_confirmed_date_invoice_subset
```

Preparation uses `Sales Invoice Details.xlsx`, includes a document only when all its detail rows share one date that can be read unambiguously as day/month/year, and calls the registered monthly distinct-count operator. Ambiguous dates are excluded and recorded. No missing months are filled. The source workbook is read only. The exploratory script does not create semantic approvals, a controlled worker receipt, or a publication record.

Both commands use exclusive output creation to protect prior versions. For another run, specify new dataset/metadata destinations through `--output` and `--metadata`, and a new model output directory.

Training filters to the eight observed interior calendar months January–August 2026. The chronological split is five training months, one validation month, and two test months. Linear Regression and Random Forest are saved separately. The latest two periods are an extremely small holdout; neither model is selected as a champion.

## Python prediction interface

```python
from prediction.monthly_regression import predict_monthly_objective

result = predict_monthly_objective(
    {"periods_ahead": 2},
    model_path=(
        "models/business_forecasting/nop_confirmed_date_invoice_subset/"
        "linear_regression.joblib"
    ),
)
```

The request schema is exactly `{"periods_ahead": integer}` with a value from 1 through 24. The selected model is the explicit `model_path`; the interface validates the matching metadata and SHA-256 before loading. The response contains objective/model identity, future monthly values, source and dataset provenance, approval mode, and known limitations. Predictions are expected counts as floats and are clipped at zero.

The prepared dataset ends with a partial September observation; the model does not train on it. The interface begins forecasts at October 2026. Example files are in `evaluation/nop_invoice_subset_exploratory_example_request.json` and `evaluation/nop_invoice_subset_exploratory_example_response.json`.

## Teammate integration

A Python MCP tool can call `predict_monthly_objective` directly and return its dictionary as JSON. Pass a trusted, configured artifact path; do not accept arbitrary filesystem paths from an end user. Keep `business_approved: false` visible in the response. Do not market this as invoice-volume forecasting: 82 of 234 source references have no fully resolved date, source completeness is unknown, and the target is only the resolvable subset.

Before business use, obtain owner decisions for invoice identity, lifecycle, date grammar, source completeness, missing-date treatment, horizon, and acceptance criteria; then create real semantic/target/preparation approvals and rerun through the controlled worker and publication lifecycle. No approval is included in these exploratory artifacts.
