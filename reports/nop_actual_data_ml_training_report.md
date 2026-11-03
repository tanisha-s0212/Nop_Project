# NOP actual-data ML training and assessment report

**Date:** 3 November 2026  
**Delivery:** Seven actual-source predictors: four retained ML models, one newly assessed ML candidate, and two newly serialized baselines. All remain exploratory. No business-approved champion or reliable new forecasting capability is claimed.

## 1. Existing work and scope

Before this assessment, the repository already contained the full source inventory and quality evidence, controlled monthly preparation, two actual-source monthly count models, an actual-source line-value preparation/training pipeline with two saved regressors, generic feature validation, chronological evaluation, independent inference, artifact discovery and adapters, and a separate synthetic demonstration. Those components were inspected and reused. Four analysis notebooks contain source analysis rather than additional model-training workflows; see [notebook audit](../evaluation/actual_data_ml_assessment/v2/notebook_audit.json).

The prior [training report](../evaluation/actual_data_ml_assessment/v2/prior_nop_actual_data_ml_training_report.md), [integration guide](../evaluation/actual_data_ml_assessment/v2/prior_nop_ml_model_integration_guide.md), and model catalogue JSON/CSV were snapshotted before updating the delivery indexes. None of the four original actual-source artifacts, their sidecars, original sources, prepared datasets, or existing Python source modules was changed. The synthetic artifact and metadata also remain unchanged.

This task added only ML assessment, deployable estimators, evaluation evidence, tests and delivery documentation. It did not implement or modify language interpretation, MCP, APIs, UI, governance or the dynamic query service. Existing discovery/adapters were exercised read-only for compatibility verification.

## 2. Existing model audit

| Retained model | Actual training dataset and target | Historical test MAE / RMSE | Finding |
| --- | --- | ---: | --- |
| Monthly Linear Regression, 0.1.0-exploratory | `data/nop_confirmed_date_invoice_count_exploratory.csv`; confirmed-date raw-reference count subset | 8.60 / 9.57 | Worse than last-value baseline; two test months |
| Monthly Random Forest, 0.1.0-exploratory | Same monthly subset | 7.85 / 8.81 | Worse than baseline; two test months |
| Ridge, 1.0.0 | `data/nop_domestic_invoice_line_value/v1/observations.csv`; restricted stored line-value field | 140,357.11 / 250,029.56 | Worse than item/quantity baseline |
| Random Forest, 1.0.0 | Same line-value dataset | 179,683.29 / 306,937.27 | Worse than item/quantity baseline |

All four artifacts passed hash/sidecar checks and fresh-process prediction. Their original paths and evaluation evidence remain intact. Monthly counts and raw line-value units are different targets; their metrics must not be compared across rows as a ranking. Full paths are in the [model catalogue](nop_ml_model_catalogue.md).

The earlier tabular models used quantity scaling plus one-hot item codes, group-weighted training, disjoint reference groups and chronological date partitions. The monthly models used calendar-month index on eight eligible observations and a recursive-safe fixed holdout. The v1 tabular artifacts were fitted on the original 135 development rows; their 30 test rows were excluded. The monthly deployment artifacts were refitted on all eight eligible observations after the original evaluation. Neither training set establishes complete business history.

Legacy synthetic and actual-source pipelines are intentionally separate. Older historical reports describe earlier implementation states; they were retained as evidence rather than removed or treated as current catalogues. No duplicate preparation pipeline or new prepared copy was necessary in this assessment.

## 3. Actual source inventory and integrity

The current source inventory is **17 files: 14 Excel workbooks and three CSV files, containing 20 previously inventoried tables and 521 fields**. All 17 current SHA-256 values match the original readiness manifest. Existing full inventory, schema, quality, relationship and readiness findings were reused against those exact hashes instead of rescanning unchanged large workbooks. Current physical files and the complete selected CSV/source-row lineage were checked directly. This assessment does not claim to have freshly reprofiled every cell of every large workbook.

See the [source inventory](../evaluation/actual_data_ml_training/v1/source_inventory.json), [source-linked target assessment](../evaluation/actual_data_ml_training/v1/target_assessment.json), and current [source/CSV verification](../evaluation/actual_data_ml_assessment/v2/source_lineage_audit.json). The prior evidence flags the exchange-rate workbooks and an order-workbook title as synthetic; none was used for actual-data training. Independent ERP/business-owner source authenticity remains an external requirement.

A protected manifest covered **123 preexisting files**, including all original source files, prepared datasets, original model files and existing Python modules. All match their before-task hashes. Mutable root catalogue indexes and requested documentation were updated with prior versions preserved. No dependencies were installed or upgraded.

## 4. New CSV: verified meaning and profile

The inspected CSV is an existing prepared dataset, not a new independent source or additional historical sample:

`data/nop_domestic_invoice_line_value/v1/observations.csv`

**Dataset ID:** `nop-domestic-confirmed-date-line-value`  
**Dataset version:** `1.0.0`  
**SHA-256:** `c177d1d76b8695ea41c88995b0782ad2a37545321df419ed30e758341fb8dd8e`

All 165 rows were matched back to `dataset/Sales Invoice Details.xlsx`, worksheet `Sheet1`, by preserved source-row lineage. Quantity, raw reference, item code, target and resolved date match their source values. The source hash is `e36c7b8338e80353e6ccf5b452fd9c9be0834fc3a3890841c60fd3fe644fad56`.

| CSV field | Source-supported interpretation | Unresolved meaning |
| --- | --- | --- |
| `source_row` | Retained physical source-row lineage | Not a predictor |
| `document_id` | Raw source `Invoice Num`, used to isolate reference groups | Global document identity, issuer/series scope and lifecycle completeness unapproved |
| `event_date` | Strictly calendar-resolved source `Invoice Date` | Full business-event and capture/completeness interpretation unapproved |
| `quantity` | Native source quantity value | Physical unit compatibility and forecast-time availability unapproved |
| `item_code` | Raw source item code; internally consistent description/HSN/UOM within the selected rows | Product identity across all datasets or business-approved product grain unverified |
| `target_value` | Native source `Taxable Value` cell | Currency, recognition, tax/additivity policy and business use unapproved; not recognized revenue or profit |

The retained population is literal `GST Tax Invoice`, `G`, `Domestic`, `Manual` rows whose entire reference has a single, consistently unambiguous date. `Manual` is a source label, not a verified physical measurement unit. Existing preparation excluded 120 unresolved-date-reference rows, 42 export rows and 10 service rows from the 337-row workbook, leaving 165. No new source join, deduplication, date repair, imputation, aggregation or zero filling was applied.

| Property | Finding |
| --- | --- |
| Shape | 165 rows, six columns; no missing/blank values in selected fields |
| References | 111; 35 have multiple detail rows, maximum three rows per reference |
| Duplicate checks | Zero repeated source rows, exact rows, rows excluding lineage, or excess document/item pairs |
| Dates | 77 observed dates, 22 December 2025 to 13 September 2026; ten observed months |
| Item coverage | 92 raw codes; 48 occur once; median one observed month per item, maximum four |
| Quantity distribution | Minimum 1, median 2, maximum 10 |
| Target distribution | Minimum 3,375; median 116,640; mean 243,653.27; maximum 2,310,000 |
| Arithmetic diagnostic | All retained target values match quantity times the raw source unit-price value within diagnostic tolerance |

That arithmetic check supports a raw-field estimation experiment; it does not establish pricing policy or revenue. Source unit price is excluded from all predictors. Detail rows are never counted as unique documents. No duplicate deletion was needed. Absence of duplicates in this selected subset does not certify the complete source system.

Profiles: [CSV profile](../evaluation/actual_data_ml_assessment/v2/csv_profile.json), [per-item coverage](../evaluation/actual_data_ml_assessment/v2/item_coverage.csv), [observed monthly coverage](../evaluation/actual_data_ml_assessment/v2/observed_monthly_coverage.csv). Monthly coverage records observed rows only; completeness is unknown and no absent periods were generated.

## 5. Target feasibility

| Candidate | Status | Evidence and minimum missing requirement |
| --- | --- | --- |
| Monthly document-volume forecasting | Insufficient historical data | Ten observed/eight eligible subset months, only two old test months. Confirm global identity/event/lifecycle and complete mature periods. A modest nonseasonal 12/6/6 split would require at least 24 complete monthly observations; two annual cycles plus meaningful evaluation require more. This is an assessment design, not a universal training threshold. |
| Monthly aggregate quantity forecasting | Blocked pending business clarification | Quantities exist but compatible physical units, included lifecycle events and complete capture are unverified. Mixed quantities cannot defensibly be summed. |
| Item-level quantity forecasting | Insufficient historical data | Maximum four observed months per item, median one. Requires validated identity/units and longer complete per-item histories; unobserved periods cannot become zeros. |
| Monthly target-value forecasting | Blocked pending business clarification | Raw field identified, but currency/tax/recognition, additive grain, adjustments and full-period capture remain unresolved. Ten observed subset months are also too weak for reliable forecast evaluation. |
| Item-level target-value forecasting | Insufficient historical data | Sparse per-item histories and unresolved value semantics/completeness. Future quantities are unknown and cannot be supplied as if forecast outcomes were known. |
| Offline stored line-value estimation | Feasible with conditions | 165 rows/111 reference groups support a limited retrospective regression experiment with supplied quantity/item. Not a future-period or verified financial forecast. |

The wider existing source assessment still blocks recognized revenue, profit, inventory, demand and customer propensity. Profit requires recognized revenue plus aligned realized costs and attributable expenses, not inventory cost-like fields. Inventory requires verified opening/snapshot state and signed dated movements. Customer propensity requires stable customer/cohort identity, eligible observation windows and matured purchase outcomes. Unverified joins were not introduced to manufacture these labels. Detailed conditions are in the [machine-readable feasibility matrix](../evaluation/actual_data_ml_assessment/v2/prediction_target_feasibility.json) and catalogue.

## 6. Improvement experiment and leakage controls

Only the supported offline raw-field experiment was extended. A quantity-normalized Ridge predicts training target/quantity from the same validated quantity/item schema, then multiplies by the caller-supplied quantity. This tests a source-supported arithmetic relationship without reading unit price or post-outcome attributes. Shared feature validation, numeric scaling and unknown-safe one-hot encoding are reused by training and inference. All fitted transformations are inside each saved estimator.

Before fitting, [the frozen evaluation plan](../evaluation/actual_data_ml_assessment/v2/evaluation_plan.json) excluded every original v1 test source row. The original test labels and scores were already known before this task, so v2 scores on those rows are explicitly **retrospective audits, not a new independent test**. No model promotion is justified from those scores.

Development has 135 rows/90 reference groups through 25 June 2026. Three expanding-origin folds use whole observed dates and disjoint reference groups:

| Fold | Training dates | Training rows / groups | Validation dates | Validation rows / groups |
| --- | --- | ---: | --- | ---: |
| 1 | 22 Dec 2025?28 Feb 2026 | 56 / 38 | 18 Mar?17 Apr 2026 | 27 / 16 |
| 2 | 22 Dec 2025?17 Apr 2026 | 83 / 54 | 18 Apr?26 May 2026 | 28 / 17 |
| 3 | 22 Dec 2025?26 May 2026 | 111 / 71 | 28 May?25 Jun 2026 | 24 / 19 |

These are observed-date ranges, not fabricated continuous daily observations. The 79 unique validation rows span 52 reference groups. The primary comparison is pooled reference-macro MAE; row MAE/RMSE are also recorded. Ridge uses inverse detail-row-count weights per reference. The baseline uses unweighted within-item median target/quantity, falling back to a development-only global median; it reproduces the preexisting comparator exactly.

Only two modest Ridge strengths (alpha 1 and 10) were compared using development folds. This limited experiment is exploratory, not broad reliable hyperparameter optimization. Training is deterministic; the recorded seed is 20261103, and these estimators have no stochastic fit stage. No random time-series split or future target feedback is used.

## 7. Actual evaluation and selection

### Expanding-origin development comparison

| Candidate | Row MAE | RMSE | Reference-macro MAE | R? | SMAPE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Item/quantity median baseline | 87,661.96 | 244,564.17 | 77,135.63 | 0.4537 | 56.11% |
| Normalized Ridge, alpha 1 | 154,126.17 | 283,564.77 | 139,302.56 | 0.2655 | 82.73% |
| Normalized Ridge, alpha 10 | 172,679.24 | 296,721.07 | 158,271.75 | 0.1958 | 90.58% |

Alpha 1 was selected only within the Ridge family. It lost to the baseline on all three folds. **The candidate is rejected as a baseline replacement**, with its artifact retained for reproducibility. The baseline is the strongest available exploratory reference, not a business-approved champion.

### Previously inspected test-period audit

All rows below use the original 30 test rows/21 reference groups from 27 June to 13 September 2026. v1 figures are the original recorded test evaluation; v2 figures are subsequent retrospective audits. These roles must not be merged into a claim of independent improvement.

| Predictor | Evidence role | MAE | RMSE | R? | SMAPE |
| --- | --- | ---: | ---: | ---: | ---: |
| Item/quantity median baseline | v2 audit; reproduces prior comparator | 72,255.50 | 190,675.29 | 0.3871 | 31.29% |
| Normalized Ridge v2 | Retrospective audit | 131,795.20 | 238,800.71 | 0.0387 | 58.79% |
| Ridge v1 | Original historical test | 140,357.11 | 250,029.56 | -0.0539 | 73.09% |
| Random Forest v1 | Original historical test | 179,683.29 | 306,937.27 | -0.5882 | 73.13% |

On the 19 audit rows with development-seen item codes, baseline MAE is 16,550.79; on 11 unseen-code rows it is 168,472.73. Large values and sparse/unseen items dominate error. Reference-group splitting does not remove every possible product/customer dependence. No artificial outlier deletion was used. See [error analysis](../evaluation/actual_data_ml_assessment/v2/error_analysis.json).

### Monthly baseline assessment

The same historical June 2026 cutoff predicts July and August counts (16 and 8) without feeding back either actual. This is the same tiny, already inspected test used by the existing models.

| Method | MAE | RMSE |
| --- | ---: | ---: |
| Last observed value, 19 at evaluation cutoff | 7.00 | 8.06 |
| Trailing two-month mean | 8.50 | 9.39 |
| Trailing three-month mean | 8.00 | 8.94 |
| Existing Linear Regression | 8.60 | 9.57 |
| Existing Random Forest | 7.85 | 8.81 |

No method beats last value. Seasonal naive with lag 12 and seasonal/statistical forecasting development are unjustified with eight eligible months. No XGBoost, SARIMA/SARIMAX or Prophet was trained or installed; their dependencies are absent in the verified interpreter, and no new validated seasonal target warrants installation. No production accuracy or meaningful R? conclusion is claimed from two monthly test observations.

## 8. New artifacts and reusable implementation

The existing dataset/version was reused byte-for-byte. No synthetic records or artificial periods were added. Three new independently loadable artifacts were saved with matching metadata:

- `models/business_regression/nop_domestic_invoice_line_value/v2/item_quantity_median_baseline.joblib`
- `models/business_regression/nop_domestic_invoice_line_value/v2/quantity_normalized_ridge.joblib`
- `models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/last_observed_value.joblib`

The two tabular states fit only the original 135 development rows and exclude all 30 test rows. The monthly deployment baseline uses all eight eligible months, ending August 2026 with value 8; its interface starts after the stored September source cutoff. Deployment example October/November estimates are therefore 8, whereas historical evaluation repeated 19. Metadata records this refit distinction. The software permits 1?24 periods but no reliable business horizon has been validated.

Each new bundle has a sidecar with hash, identity/version, target, dataset fingerprint/provenance, feature order, parameters, training/evaluation periods and counts, dependency versions, input/output schema, exploratory status and limitations. Prediction preprocessing is contained in the fitted estimators. The new custom estimator module must ship with the artifact.

New implementation:

| File | Responsibility |
| --- | --- |
| `src/prediction/tabular_estimators.py` | Deployable quantity-normalized Ridge and learned item/quantity median baseline |
| `src/training/improve_tabular_models.py` | Frozen-plan expanding-origin assessment, audit and version-safe persistence |
| `src/training/evaluate_monthly_baselines.py` | Comparable fixed-cutoff baseline evaluation and independent deployment state |
| `src/training/finalize_ml_assessment.py` | Read-only model discovery, fresh-process audit, delivery indexing/evidence |
| `tests/test_ml_assessment_v2.py` | Thirteen focused actual-data/integrity/reproducibility/compatibility checks |

Existing `features.tabular_regression`, `training.tabular_regression`, monthly training persistence helpers, both independent prediction functions, both inference adapters, preparation specifications and source discovery were reused unchanged. Output directories must be unused; original registered versions are never replaced. Root `models/model_catalogue.json` and `.csv` are mutable delivery indexes with their previous contents preserved under evaluation evidence. They retain compatibility fields while distinguishing baselines from ML and audits from independent tests.

## 9. Inference and artifact verification

**All seven actual-source predictors were loaded and used in separate fresh Python processes.** Hashes, expected identities/versions, dependency compatibility, finite values and JSON output were checked. Four feature-row predictors each reproduced their recorded 30-row test/audit predictions. Three monthly predictors returned two ordered future periods. The new estimators load without importing training orchestration. Existing feature validation rejects missing/extra fields, invalid values and mismatched expected dataset identities.

Evidence: [all-model fresh-process verification](../evaluation/actual_data_ml_assessment/v2/all_model_inference_verification.json), [delivery verification](../evaluation/actual_data_ml_assessment/v2/final_delivery_verification.json), and [integration guide](../docs/development/nop_ml_model_integration_guide.md).

Use `prediction.tabular_regression.predict_tabular_regression(request, model_path=...)` for supplied feature rows. Use `prediction.monthly_regression.predict_monthly_objective(request, model_path=...)` for monthly count estimates only. The former cannot answer a future-period financial forecast. Actual-derived request/response examples are in `evaluation/actual_data_ml_assessment/v2/`.

The verified environment is Python 3.12.10, scikit-learn 1.8.0, NumPy 2.4.4, pandas 3.0.2 and joblib 1.5.3. The existing `.venv` has a different scikit-learn version and is not interchangeable with this artifact environment. No environment was changed.

## 10. Tests: exact outcomes and integration gap

Run from the repository root with `PYTHONPATH=src` and the matching system interpreter:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest -v tests.test_ml_assessment_v2 tests.test_tabular_ml tests.test_actual_data_ml_exploratory tests.test_invoice_volume_model tests.test_discovery
```

The initial selected run completed **50 tests: 50 passed, zero failures/errors/skips**. The subsequent new version-preservation test passed. After making newly generated metadata reproducible, two affected reproduction checks passed (one rerun and one additional monthly check). Thus **52 distinct ML/discovery checks passed across those recorded runs**; the displayed combined command was not rerun wholesale after adding the final two tests. Transcripts and machine-readable results are retained under `evaluation/actual_data_ml_assessment/v2/`.

Four relevant preexisting dynamic-query integration tests were also executed and **all four failed their fixed-count assertions** (`3 != 2`), with zero execution errors:

- `test_unseen_invoice_forecast_uses_all_compatible_actual_models`
- `test_plan_is_reproducible_and_includes_dataset_and_model_hashes`
- `test_dependency_mismatch_blocks_before_unpickling`
- `test_fresh_process_uses_same_entry_point_and_json_output`

Their discovery now legitimately includes the serialized monthly baseline as a third compatible artifact. A separate unchanged-service request completed with `partially_answered` status and three model forecasts, saved as [runtime response](../evaluation/actual_data_ml_assessment/v2/framework_inventory_response.json). The four failures are an unresolved test-contract gap, not reported as passes. No teammate-owned code or test was changed. The integration owner should replace fixed model counts with expectations derived from eligible artifact identities, retaining dependency/integrity assertions. See [failure results](../evaluation/actual_data_ml_assessment/v2/framework_inventory_regression_results.json) and [full transcript](../evaluation/actual_data_ml_assessment/v2/framework_inventory_regression_transcript.txt).

The complete repository regression suite was not executed. Passing ML/inference checks does not imply that all framework tests pass or business approval exists.

## 11. Deliverable index and remaining requirements

- [Human model catalogue](nop_ml_model_catalogue.md)
- [Machine-readable model catalogue](../models/model_catalogue.json) and [CSV index](../models/model_catalogue.csv)
- [Integration guide and runnable independent inference examples](../docs/development/nop_ml_model_integration_guide.md)
- [Prepared observations](../data/nop_domestic_invoice_line_value/v1/observations.csv), [dataset metadata](../data/nop_domestic_invoice_line_value/v1/observations.metadata.json), and [training specification](../data/nop_domestic_invoice_line_value/v1/training_spec.json)
- [Tabular evaluation](../models/business_regression/nop_domestic_invoice_line_value/v2/evaluation_metrics.json), [development predictions](../models/business_regression/nop_domestic_invoice_line_value/v2/rolling_origin_predictions.csv), and [audit predictions](../models/business_regression/nop_domestic_invoice_line_value/v2/retrospective_audit_predictions.csv)
- [Monthly baseline evaluation](../models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/evaluation_metrics.json) and [historical actual/predicted rows](../models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/historical_baseline_predictions.csv)

**Next ML action:** Obtain a genuinely unseen future source extract with the same recorded schema/population, confirmed quantity/amount meaning and stable identities; freeze prospective evaluation before inspecting labels. Do not promote normalized Ridge on this assessment.

**Business/data owners:** Confirm financial field/currency/tax/additivity semantics, physical units, document/product identity and lifecycle treatment; provide reconciled complete mature history, with explicit zero-versus-missing evidence. Supply realized costs/expenses for profit, signed inventory history for stock, and matured customer cohorts for propensity.

**Integration teammate:** Consume the documented target-specific adapters with matching dependencies, show exploratory limitations, and resolve the four fixed-count integration assertions. These are the exact remaining external actions; no broader framework implementation is included in this ML delivery.
