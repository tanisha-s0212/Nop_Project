# NOP ML model catalogue

**Version:** 2.0.0. All entries are exploratory; no business-approved champion exists.

Seven actual-source predictors comprise five ML models and two fitted baselines. The existing synthetic demonstration is preserved and excluded from these counts.

| Algorithm / version | Family | Target / dataset | Evaluation | MAE | RMSE | Artifact | Status |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| last_observed_value_baseline / 1.0.0 | baseline | confirmed-date monthly reference count; nop-confirmed-date-invoice-count-exploratory | historical fixed-cutoff baseline already inspected before this task | 7.00 | 8.06 | [last_observed_value.joblib](../models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/last_observed_value.joblib) | Exploratory reference baseline; business use unapproved |
| linear_regression / 0.1.0-exploratory | ML | confirmed-date monthly reference count; nop-confirmed-date-invoice-count-exploratory | original historical test evidence | 8.60 | 9.57 | [linear_regression.joblib](../models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib) | Retained; did not beat its documented baseline |
| random_forest / 0.1.0-exploratory | ML | confirmed-date monthly reference count; nop-confirmed-date-invoice-count-exploratory | original historical test evidence | 7.85 | 8.81 | [random_forest.joblib](../models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib) | Retained; did not beat its documented baseline |
| random_forest / 1.0.0 | ML | stored line-value proxy; nop-domestic-confirmed-date-line-value | original historical test evidence | 179,683.29 | 306,937.27 | [random_forest.joblib](../models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.joblib) | Retained; did not beat its documented baseline |
| ridge_regression / 1.0.0 | ML | stored line-value proxy; nop-domestic-confirmed-date-line-value | original historical test evidence | 140,357.11 | 250,029.56 | [ridge_regression.joblib](../models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.joblib) | Retained; did not beat its documented baseline |
| item_quantity_median_baseline / 2.0.0 | baseline | stored line-value proxy; nop-domestic-confirmed-date-line-value | retrospective audit; labels and v1 results were previously inspected | 72,255.50 | 190,675.29 | [item_quantity_median_baseline.joblib](../models/business_regression/nop_domestic_invoice_line_value/v2/item_quantity_median_baseline.joblib) | Exploratory reference baseline; business use unapproved |
| quantity_normalized_ridge / 2.0.0 | ML | stored line-value proxy; nop-domestic-confirmed-date-line-value | retrospective audit; labels and v1 results were previously inspected | 131,795.20 | 238,800.71 | [quantity_normalized_ridge.joblib](../models/business_regression/nop_domestic_invoice_line_value/v2/quantity_normalized_ridge.joblib) | Rejected versus baseline on rolling-origin development; research artifact retained |

## Evaluation interpretation

The v1 original test results were evaluated before this assessment. New v2 line-value scores on those same 30 rows are retrospective audits, not a new independent test. The v2 primary comparison uses three expanding-origin development folds: 79 predictions across 52 reference groups. The monthly comparison has only two test months and cannot support a reliability claim. Scores across line-value units and monthly counts are not comparable.

## Requested prediction-target feasibility

| Candidate | Status | Required evidence |
| --- | --- | --- |
| Monthly document-volume forecasting | Insufficient historical data | Confirmed document identity/event/lifecycle and complete mature periods; at least 24 complete monthly observations for a modest 12/6/6 split; existing eight months are not certified complete. |
| Monthly aggregate quantity forecasting | Blocked pending business clarification | Physical units, source coverage, lifecycle, compatible aggregation and sufficient complete history. Manual is not a confirmed unit. |
| Item-level quantity forecasting | Insufficient historical data | Validated item identity/units and substantially longer complete per-item series; no zero insertion for unobserved periods. |
| Monthly target-value forecasting | Blocked pending business clarification | Target meaning, currency/tax/recognition basis, additive grain, adjustments, completeness and longer history. |
| Item-level target-value forecasting | Insufficient historical data | Long regular per-item history, approved value meaning and period completeness; future quantity is not available as a forecasting feature. |
| Offline stored line-value estimation | Feasible with conditions | Exploratory use only; currency/units/decision-time availability and prospective performance remain unapproved. Baseline outperforms ML candidates. |

## Inference and limitations

Use `prediction.tabular_regression.predict_tabular_regression` for raw line-value predictors and `prediction.monthly_regression.predict_monthly_objective` for monthly predictors. All saved preprocessing/state is in the bundles. Match model/dataset versions and dependency metadata. Tabular requests contain positive numeric quantity and a raw item-code string. Monthly requests contain `periods_ahead` and start after the stored source cutoff.

Currency, physical units, global document/product identity, complete source capture and business meanings are not approved. Reference groups are split-isolation units; wider statistical dependence can remain. Unseen item codes, sparse history and previously inspected holdouts restrict conclusions. See the [training report](nop_actual_data_ml_training_report.md) and [integration guide](../docs/development/nop_ml_model_integration_guide.md).

## Preserved synthetic demonstration

The separate [synthetic invoice-volume artifact](../models/nop_invoice_volume_model.joblib), [metadata](../models/model_metadata.json) and [synthetic dataset](../data/synthetic_monthly_invoice_volume.csv) remain unchanged. Its interface is `prediction.invoice_volume.predict_invoice_volume`. It is a software demonstration, excluded from actual-source model counts and business-performance comparisons. This assessment did not generate or train synthetic data.

## Validation status

All seven actual-source predictors passed fresh-process loading and prediction. Fifty-two distinct selected ML/discovery checks passed across recorded runs. Four existing integration assertions failed because they expect exactly two monthly artifacts and discovery now finds three; no framework code or integration tests were modified. These failures remain open for the integration owner. The full repository suite was not run.

[Machine-readable catalogue](../models/model_catalogue.json) · [Fresh-process evidence](../evaluation/actual_data_ml_assessment/v2/all_model_inference_verification.json)
