# NOP actual-data exploratory completion report

**Date:** 3 November 2026  
**Outcome:** Prepared an exploratory dataset from actual NOP source rows, trained and evaluated two regression models, saved separate model artifacts, and verified inference in a fresh Python process. This demonstration does **not** model total NOP invoice volume and is not approved for business use. The tiny holdout did not support a champion selection.

## Source and target

Used `dataset/Sales Invoice Details.xlsx`, `Sheet1`, fields `Invoice Num`, `Invoice Date`, and `TransType`. The workbook has 337 detail rows, 234 distinct nonblank invoice references, and all rows have `TransType = GST Tax Invoice`.

The exploratory target is **distinct invoice references per observed month among references whose every detail row has one consistent, unambiguously day-first date**. The exact `Invoice Num` string is treated as identity within this workbook only. This is a confirmed-date subset proxy, not total invoice volume.

A fresh raw-cell inspection found 217 unambiguous date rows and 120 ambiguous date cells, with no blank dates. After requiring every detail row for a reference to be date-resolved, 152 references were included and 82 excluded. The prior readiness report reported 107 ambiguous cells; the discrepancy is documented in [the assumptions report](nop_actual_data_ml_exploratory_assumptions.md) for reconciliation. Ambiguous dates were not parsed and no source values were changed.

The dataset contains 10 observed monthly buckets from December 2025 through September 2026. December and September are partial calendar boundaries. The eight interior months January–August 2026 were eligible for the model split; source extract completeness is unknown, so these are not certified closed periods. No absent month was filled with zero.

Artifacts describing the prepared dataset:

- Dataset: [nop_confirmed_date_invoice_count_exploratory.csv](/D:/Aroha_Files/NOP_Project/data/nop_confirmed_date_invoice_count_exploratory.csv), 10 rows × 3 fields, SHA-256 `807bb312577bb595cdb22d28dd227c0fc23e52898ab42dbe73b99f7d4f444b95`.
- Provenance: [dataset metadata](/D:/Aroha_Files/NOP_Project/data/nop_confirmed_date_invoice_count_exploratory.metadata.json).
- Reusable trainer input specification: [objective spec](/D:/Aroha_Files/NOP_Project/data/nop_confirmed_date_invoice_count_exploratory.spec.json).
- Source SHA-256: `e36c7b8338e80353e6ccf5b452fd9c9be0834fc3a3890841c60fd3fe644fad56`.

Preparation reused `time_series_aggregation@1.0` for observed-month bucketing and distinct counting. No semantic bindings or preparation execution approvals were available. The source-specific script therefore ran the trusted operator implementation in isolation using explicitly labeled exploratory field references; it did **not** create a controlled-worker receipt or publication. Its metadata records `business_approved: false` and `controlled_worker_execution: false`. No business approval was fabricated.

## Training and evaluation

The reusable trainer accepts the dataset and a structured column/target specification; it contains no NOP-specific source mappings. It used one prediction-time feature: calendar month index from the first eligible observation. No lags or seasonality were inferred from this short series.

| Split | Periods | Count |
|---|---|---:|
| Train | 2026-01–2026-05 | 5 |
| Validation | 2026-06 | 1 |
| Test | 2026-07–2026-08 | 2 |

The test baseline repeats the last value at the validation cutoff (19) for both test months; actual test values were 16 and 8.

| Model | Validation MAE / RMSE (n=1) | Test MAE | Test RMSE | Baseline MAE / RMSE (n=2) | Test result |
|---|---:|---:|---:|---:|---|
| Linear Regression | 2.10 / 2.10 | 8.60 | 9.57 | 7.00 / 8.06 | Worse than baseline |
| Random Forest Regressor | 0.49 / 0.49 | 7.85 | 8.81 | 7.00 / 8.06 | Worse than baseline |

No champion was selected. The validation has one period and the test has two, making metrics highly unstable. Serialized models were refit on all eight eligible periods for interface demonstration; reported test scores use only the chronological holdout.

XGBoost was not trained because `xgboost` is unavailable. SARIMA/SARIMAX and Prophet were not trained: eight eligible observations cannot support meaningful seasonal evaluation, and `statsmodels` and `prophet` are unavailable. No packages were installed. Recorded runtime versions: Python 3.12.10, scikit-learn 1.8.0, NumPy 2.4.4, pandas 3.0.2, joblib 1.5.3.

## Model artifacts and teammate interface

Each saved bundle has a matching metadata file with the model identity, feature schema, target, training/test periods, metrics, dependency versions, source provenance, approval status, and artifact hash.

- Linear Regression: [linear_regression.joblib](/D:/Aroha_Files/NOP_Project/models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib), SHA-256 `e13668b5a9b4dceaf7ff751e9bbe47e9d476687d032c166e315be0ff37068cf4`.
- Random Forest: [random_forest.joblib](/D:/Aroha_Files/NOP_Project/models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib), SHA-256 `e556ed1111c352248f11fa270aee8503ac37633c3fc09adbe13faa2f01dc76e4`.
- Evaluation and baseline metrics: [evaluation_metrics.json](/D:/Aroha_Files/NOP_Project/models/business_forecasting/nop_confirmed_date_invoice_subset/evaluation_metrics.json).
- Generic training module: [monthly_regression.py](/D:/Aroha_Files/NOP_Project/src/training/monthly_regression.py).
- Inference function: [predict_monthly_objective](/D:/Aroha_Files/NOP_Project/src/prediction/monthly_regression.py), signature `predict_monthly_objective(input_data, model_path=...)`.
- Integration instructions: [nop_actual_data_ml_exploratory_usage.md](/D:/Aroha_Files/NOP_Project/docs/development/nop_actual_data_ml_exploratory_usage.md).
- Example request and response: `evaluation/nop_invoice_subset_exploratory_example_request.json` and `evaluation/nop_invoice_subset_exploratory_example_response.json`.

The request is `{"periods_ahead": 2}`. Fresh-process inference loaded both artifacts, checked their sidecar SHA-256, and returned finite JSON predictions for 2026-10 and 2026-11. Linear Regression predicted 12.14 and 11.21; Random Forest predicted 14.91 and 14.91. These values refer only to the confirmed-date subset.

## Tests and source integrity

- Final focused run: `PYTHONPATH=src python -m unittest -v tests.test_actual_data_ml_exploratory tests.test_time_series_aggregation_operator tests.test_preparation_specifications.SpecificationTests.test_aggregation_cannot_silently_change_grain_or_create_derived_target tests.test_worker_artifact_publication.StorageTests.test_unknown_registration_and_unsupported_grain_are_rejected` — **11 passed**.
- Additional existing worker regression `test_registered_filter_retains_rejected_records_and_exact_grain` passed in the preceding focused run.
- Focused tests cover strict date rejection, distinct document aggregation, chronological splitting, artifact serialization, integrity checks, request validation, and fresh-process import/inference.
- All **17/17 original source hashes** matched the readiness manifest after implementation.
- Earlier broad combined preparation/worker run had one failure in a process that imported the pre-fix grain-registration guard; the exact regression passed after the fix. The entire broad suite was not rerun after that fix.

## Limitations and next action

82 references are omitted because their dates cannot be resolved safely; their true months are unknown and the resulting undercount may vary by month. The source extraction watermark and closed-period completeness are unknown. Only eight monthly observations were eligible, both models lost to the simple baseline, and no seasonal or long-horizon claim is supported. This is a functional exploratory demonstration, not a production-ready forecasting service.

For governed integration, the business/process owner must confirm document identity, lifecycle, date interpretation, forecast horizon, and evaluation criteria. ERP/data operations must supply authoritative extract completeness and substantially longer mature history. Then create authenticated semantic, target, preparation, execution, and publication approvals and retrain against the complete approved target. Revenue/profit require separately validated accounting data, adjustments, and realized costs/expenses.
