# NOP business forecasting model comparison

**Assessment date:** 3 November 2026  
**Status:** Two actual-NOP exploratory subset regressors were trained and evaluated. Neither beats the baseline, and the tiny holdout does not support selecting a champion or claiming total invoice-volume accuracy.

## Confirmed-date invoice-reference subset

The prepared source dataset contains 10 observed monthly buckets from `Sales Invoice Details.xlsx`; December and September are partial calendar boundaries. Evaluation uses the 8 interior buckets from January through August 2026. Target: distinct references with fully consistent, unambiguous day-first dates only. 82 of 234 references were excluded because their date could not be fully resolved. The target is not total invoice volume and source completeness is unknown.

Chronological split: train Jan–May (5), validation Jun (1), test Jul–Aug (2). Feature: calendar month index from the first eligible month. The baseline repeats the last observed value at the validation cutoff (19) for both test months. All values below come from executed holdout evaluation.

| Model | Validation MAE / RMSE (n=1) | Test MAE | Test RMSE | Baseline MAE / RMSE (n=2) | Result |
|---|---:|---:|---:|---:|---|
| Linear Regression | 2.10 / 2.10 | 8.60 | 9.57 | 7.00 / 8.06 | Worse than baseline |
| Random Forest Regressor | 0.49 / 0.49 | 7.85 | 8.81 | 7.00 / 8.06 | Worse than baseline |

No champion was selected. The validation sample has one month and the test has two; metrics are highly unstable. The final serialized models were refit on all eight eligible periods for demonstration inference, not for the reported holdout scores.

| Model | Artifact | Artifact SHA-256 |
|---|---|---|
| Linear Regression | `models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib` | `e13668b5a9b4dceaf7ff751e9bbe47e9d476687d032c166e315be0ff37068cf4` |
| Random Forest | `models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib` | `e556ed1111c352248f11fa270aee8503ac37633c3fc09adbe13faa2f01dc76e4` |

## Other objectives and algorithms

| Candidate/model | Status |
|---|---|
| Total monthly invoice volume | Not established; confirmed-date subset may have month-dependent undercounts |
| Sales/order activity | Not prepared; order identity, event semantics, lifecycle, and coverage unresolved |
| Revenue / sales value | Not prepared; repeated totals, alternate representations, adjustments, currency, and recognition basis unresolved |
| Monthly profit | Blocked; linked realized costs and expenses unavailable |
| Product/service demand | Not prepared; identity, units, returns, event scope, and series coverage unresolved |
| Inventory/stockout and customer propensity | No validated repeated snapshots, outcomes, or historical cohorts |
| XGBoost | Not trained; package unavailable in active environment |
| SARIMA/SARIMAX | Not trained; only 8 eligible observations, and `statsmodels` unavailable |
| Prophet | Not trained; only 8 eligible observations, and `prophet` unavailable |

The exact assumptions and unresolved decisions are in [the exploratory assumptions document](nop_actual_data_ml_exploratory_assumptions.md). The prior synthetic artifact `models/nop_invoice_volume_model.joblib` remains separate and was not used in this comparison.
