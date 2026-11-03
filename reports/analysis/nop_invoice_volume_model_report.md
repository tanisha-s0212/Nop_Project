# Monthly invoice-volume forecasting model report

**Run date:** 3 November 2026  
**Model:** `nop-monthly-invoice-volume-rf` version `1.0.0`  
**Data mode:** Synthetic only. This model is an integration prototype and does not represent actual NOP invoice forecasting performance.

## Dataset provenance

The approved-data review found no prepared, approved NOP training dataset. Existing readiness evidence also records unresolved invoice dates and business approvals, so no original NOP source was used or changed.

The training workflow generated `data/synthetic_monthly_invoice_volume.csv` reproducibly with NumPy seed `20261103`. It contains 180 consecutive monthly observations from January 2011 through December 2025. Each target is a non-negative integer count generated from a base of 145, a linear increase of 0.14 counts per month, annual and semiannual sinusoidal components, and seeded Normal noise with standard deviation 3.5; the result is rounded and floored at zero. Every row is marked `data_mode=synthetic` and identifies the generator. The dataset is illustrative and has no NOP source lineage.

## Features and leakage controls

Reusable feature code is in `src/features/invoice_volume.py`. For each prediction month it creates calendar year, quarter, 12 month-of-year indicators, and lagged counts at 1, 3, 6 and 12 months. A feature row requires at least 12 consecutive earlier months; missing periods, negative counts, non-finite counts and non-numeric values are rejected. Training and inference call the same feature builder.

The chronological evaluation used the first 144 observations (January 2011–December 2022) as the training-history cutoff and the last 36 months (January 2023–December 2025) as the holdout. The model forecast the whole holdout recursively: after the first prediction, its prediction—not the unknown actual holdout target—was used as the later lag value. The naive baseline follows the same recursive rule, starting from the final pre-holdout count.

The evaluation estimator was fit on the 132 supervised training rows available after the initial 12-month lag warmup. Once holdout evaluation was recorded, a deployment estimator with the same configuration was refit on all 168 supervised rows, using observations through December 2025. The saved model history ends at that same date, so default inference starts in January 2026. Holdout metrics remain those from the pre-holdout estimator.

## Model and evaluation

Algorithm: `sklearn.ensemble.RandomForestRegressor`, configured with 300 trees, maximum depth 8, minimum leaf size 2, `max_features=0.9`, seed `20261103` and `n_jobs=-1`.

| Recursive 36-month holdout | MAE | RMSE |
| --- | ---: | ---: |
| Random forest | 4.3530 | 5.2300 |
| Previous-period recursive baseline | 11.5556 | 14.1008 |
| Model minus baseline | -7.2025 | -8.8708 |

These results apply only to the generated synthetic series. They are not actual NOP performance estimates, model acceptance criteria, or evidence that the model is suitable for business use. Full values, period boundaries and policy are in `evaluation/evaluation_metrics.json` and `evaluation/baseline_comparison.json`.

## Example prediction

Request in `evaluation/example_request.json`:

```json
{"periods_ahead": 3}
```

The independently loaded model returned non-negative numeric forecasts for January–March 2026. The exact structured response, including provenance and limitations, is saved at `evaluation/example_response.json`. These are synthetic-model outputs, not NOP operational forecasts.

## Validation performed

- Executed deterministic dataset generation and the complete training/evaluation command.
- Ran four focused unit tests covering reproducible synthetic generation, feature order/lags, short or gapped histories, chronological training, artifact round-trip, inference validation and recursive multi-period output. All four passed.
- In a separate Python process, imported `prediction.predict_invoice_volume`, loaded the saved `.joblib`, generated three future predictions and checked JSON serialization, response shape, numeric/non-negative values and synthetic provenance.
- Compared all 17 original source file hashes with the existing readiness SHA-256 manifest: all 17 matched. Hashed all existing `src/business_prediction/` files before and after validation: no changes.

## Artifacts

- Synthetic data: `data/synthetic_monthly_invoice_volume.csv`
- Trained bundle: `models/nop_invoice_volume_model.joblib`
- Model metadata and feature definitions: `models/model_metadata.json`
- Holdout metrics: `evaluation/evaluation_metrics.json`
- Baseline comparison: `evaluation/baseline_comparison.json`
- Example request/response: `evaluation/example_request.json`, `evaluation/example_response.json`
- Reusable features: `src/features/invoice_volume.py`
- Training and generation: `src/training/train_invoice_volume.py`
- Inference API: `src/prediction/invoice_volume.py`, exported by `src/prediction/__init__.py`
- Focused tests: `tests/test_invoice_volume_model.py`
- Integration instructions: `docs/development/nop_invoice_volume_model_usage.md`

## Limitations and intended use

This implementation demonstrates an importable monthly forecasting workflow for teammate integration. It is not a production NOP model. Synthetic data does not represent invoice scope, invoice lifecycle, source completeness, cancellations, reporting delay, holidays, operational changes or business meaning. No invoice dates from the source dataset were interpreted. The model uses only calendar and past-count information, supplies no prediction intervals, and recursively propagated errors may grow with horizon. A random forest is not a reliable long-term trend extrapolator. Caller-supplied history is shape-checked but remains unverified and unapproved. Actual NOP use requires approved target/source semantics, sufficient mature history, a suitable evaluation protocol and a separately authorized training run.
