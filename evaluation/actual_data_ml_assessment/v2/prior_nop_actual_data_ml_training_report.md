# NOP actual-data ML training report

**Date:** 3 November 2026  
**Outcome:** Two additional models were genuinely trained, evaluated, saved and verified from actual repository source rows. Both predict a narrowly defined stored line-value proxy and both underperform the predefined item/quantity baseline. No business-ready champion is claimed. The two existing actual-source monthly models and the synthetic demonstration remain intact.

## 1. Work present before this task

The repository already contained read-only source adapters and discovery, full source-quality/relationship evidence, an actual-source confirmed-date monthly count dataset, a generic monthly regression trainer/inference implementation, the two saved monthly Linear Regression/Random Forest artifacts, a separate synthetic demonstration, and model-discovery/inference-adapter contracts. Those components were inspected and reused. Neither existing monthly artifact was retrained or overwritten.

The teammate's query service, language interpretation, MCP, APIs, UI and governance code were outside this task. SHA-256 protection covered their existing `src/business_prediction/` Python modules as well as original sources and existing model files; all 81 protected files remained unchanged. The only existing code file modified was the ML adapter module, which gained a tabular regression adapter.

## 2. Current source inventory

All original files were reopened through the existing Excel/CSV adapters using previously recorded physical layouts only when the source hash matched. The current inventory is **17 files: 14 Excel workbooks, 3 CSVs, 20 tables, 521 fields**. All 17 original hashes match the readiness manifest. Physical worksheet/table counts and headers were read again; full prior quality findings were reused only against matching hashes. New prefix profiles are labeled as 32-row profiles, not full scans.

| Source | Current physical rows × fields / tables |
| --- | --- |
| Customer Master Report 1.xlsx | 40 × 35 |
| Customer Master Report 2.xlsx | 5,015 × 35 |
| Exchange Rate 1.xlsx | 7 × 7 |
| Exchange Rate.xlsx | 22 × 7 |
| GSTR1_Credit_Debit_Note 1.csv | 6 × 64 |
| GSTR1_Credit_Debit_Note 2.csv | 279 × 64 |
| GSTR1_Invoice.csv | 337 × 68 |
| Inventory Audit Report as on 200327.xlsx | 108,129 × 13 |
| Inventory Audit Report as on 200926 1.xlsx | 162 × 13 |
| Inventory Audit Report as on 200926.xlsx | 162 × 13 |
| Item Master Lists 1.xlsx | 150 × 19 |
| Item Master Lists 2.xlsx | 5,015 × 19 |
| Sales Invoice Details 1.xlsx | 100,188 × 43, including 5 blank rows |
| Sales Invoice Details.xlsx | 337 × 43 |
| Sales Order Report 1.xlsx | 1,098 × 26 |
| Sales Order Report 2.xlsx | 100,286 × 26 |
| Sales_Order_Data_202609.xlsx | Four tables: 43 × 4, 11 × 5, 60 × 8, 33 × 9 |

Source-authenticity evidence explicitly marks the exchange-rate workbooks and a title in `Sales_Order_Data_202609.xlsx` as synthetic. They were excluded from actual-data training. Example-domain patterns in customer masters remain warnings about provenance, not fabricated labels or a conclusion that every record is synthetic. The training source was the unmarked invoice workbook; independent ERP/business-owner authenticity is not established by this execution.

[Current inventory](../evaluation/actual_data_ml_training/v1/source_inventory.json) and [source-linked target assessment](../evaluation/actual_data_ml_training/v1/target_assessment.json) provide machine-readable evidence.

## 3. Selected new target and intended use

**Objective ID:** `nop-domestic-confirmed-date-line-value`  
**Source:** `dataset/Sales Invoice Details.xlsx`, `Sheet1`  
**Observation grain:** One retained source detail row.  
**Target:** The native numeric `Taxable Value` cell for a row literally marked `GST Tax Invoice`, `G`, `Domestic` and `Manual`, from a reference whose every detail row has one consistent, unambiguously day-first date.  
**Task:** Exploratory offline estimation of that stored field from supplied raw quantity and item code.

The target has a literal source definition and line-grain arithmetic evidence. On all 165 retained rows, native quantity × native unit price agrees with the target within the declared screening tolerance. Unit price is used only for that diagnostic; arithmetic agreement never filters observations and unit price is never a predictor.

The target does not establish recognized revenue, profit, total sales, demand, physical units or a verified currency. The `Manual` unit label is retained as a literal population condition. There is no aggregation or currency conversion. Inputs are attributes supplied for offline field estimation; their availability before a future business decision is unverified. The model therefore makes no prospective quotation, price-policy or business-forecast claim.

Row-value modeling uses observed retained labels. Forecasting a total requires complete event capture and mature periods, which remain unavailable. This distinction allowed a limited regression experiment without inventing missing invoice events, accounting definitions or future labels.

## 4. Actual-data preparation and lineage

Preparation is reproducible through `src/features/prepare_invoice_line_value.py` and the external specification `data/preparation_specs/nop_domestic_invoice_line_value_v1.json`. Raw mappings are outside reusable feature/training modules. It reuses the existing strict date parser and read-only Excel adapter.

- Read all 337 source detail rows without formula evaluation.
- Group the exact raw reference string within this workbook for date consistency and split isolation; this does not approve an issuer-wide identity.
- Require every row of a reference to have the same canonical unambiguous four-digit-year day-first date. Ambiguous references are excluded as a whole.
- Apply the explicit date cutoff before 3 November 2026 and literal population conditions.
- Require valid native positive quantity/target and a nonblank item code. No missing values are imputed and numeric strings are not silently accepted as native values.
- Preserve source-row lineage and duplicate source content; no automatic deduplication is performed.
- Project the raw fields and sort by date/reference/source row. No joins or period aggregation are performed.

| Reconciliation | Rows |
| --- | ---: |
| Original source detail rows | 337 |
| Excluded: unresolved/inconsistent reference dates | 120 |
| Excluded: export population | 42 |
| Excluded: service population | 10 |
| Retained | **165** |
| Total excluded | **172** |

The retained dataset contains **111 reference groups, 77 observed dates, and 92 item codes**, spanning **22 December 2025–13 September 2026**. Every projected feature and target is present. Quantity ranges from 1 to 10. Stored target values range from 3,375 to 2,310,000; the median is 116,640. Heavy-tail values were preserved. No source period was invented, inferred complete, or filled with zero.

- Dataset: `data/nop_domestic_invoice_line_value/v1/observations.csv`
- Dataset SHA-256: `c177d1d76b8695ea41c88995b0782ad2a37545321df419ed30e758341fb8dd8e`
- Source SHA-256: `e36c7b8338e80353e6ccf5b452fd9c9be0834fc3a3890841c60fd3fe644fad56`
- Metadata, query specification, training specification and excluded source-row reasons are adjacent to the dataset.
- [Dataset summary](../evaluation/actual_data_ml_training/v1/dataset_summary.json) records distributions and reconciliation.

## 5. Features, chronological evaluation and leakage controls

Features are exactly `quantity` and `item_code`. Shared feature validation and fitted preprocessing are in `src/features/tabular_regression.py`. The serialized pipeline contains `StandardScaler` for quantity and `OneHotEncoder(handle_unknown="ignore")` for item code. Missing-value imputation is absent.

Document/reference IDs, source-row IDs, dates, unit price, monetary components, taxes, document totals and the target are excluded from model features. Preprocessing is fitted only on the permitted earlier split. All rows from a reference share one date and one partition. Reference counts are split-isolation groups; additional dependence across dates, customers or products may remain.

The predeclared split uses the first 60%, next 20% and final 20% of distinct observed dates. Minimum gates were 60/20/20 references and 30/12/12 distinct dates. Dates are not randomly split.

| Split | Period | Lines | Reference groups | Dates |
| --- | --- | ---: | ---: | ---: |
| Train | 2025-12-22–2026-05-19 | 101 | 65 | 46 |
| Validation | 2026-05-23–2026-06-25 | 34 | 25 | 15 |
| Test | 2026-06-27–2026-09-13 | 30 | 21 | 16 |

Ridge alpha was selected from 1, 10 and 100. Random Forest compared two modest depth/leaf configurations. Hyperparameters were selected using validation document-macro MAE; the test set was not used for tuning. Each reference receives total training weight one, preventing multi-line references from dominating solely through line count.

The saved estimators fit **train plus validation: 135 lines, 90 references, through 25 June 2026**. They were not refit on test rows. This allowed fresh-process predictions from the saved artifacts to reproduce all stored test predictions. Random seed: **20261103**.

Selected parameters: Ridge alpha **1.0** with the existing sparse-compatible least-squares solver; Random Forest **200 trees, depth 6, minimum leaf 3, one worker**. The fitted pipeline and metadata retain the transformations and configuration. Predictions are bounded below by the declared numerical minimum of zero; source data is not zero-filled.

## 6. Executed results and model selection

All figures below are executed holdout results from actual retained NOP-source rows, measured in unspecified source amount units.

| Estimator | Validation MAE | Test MAE | Test RMSE | Test R² | Test SMAPE | Test reference-macro MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ridge regression | 109,745.73 | 140,357.11 | 250,029.56 | -0.0539 | 73.09% | 125,635.76 |
| Random Forest | 119,775.98 | 179,683.29 | 306,937.27 | -0.5882 | 73.13% | 155,652.33 |
| Constant training-median baseline | 165,819.41 | 148,474.17 | 264,424.76 | -0.1787 | 81.91% | 106,747.62 |
| Quantity-scaled item-median baseline | 35,521.47 | **72,255.50** | **190,675.29** | **0.3871** | **31.29%** | **56,477.40** |

The item/quantity baseline learns median target-per-quantity values from permitted earlier labels by item code, using a training-only global median fallback for unseen items. It never reads requested holdout targets. Both baselines were frozen on train for validation and train plus validation for the test.

Neither ML model beat the predefined stronger baseline on validation or test. **No model was selected as a champion or recommended for business use.** Eleven of 30 test lines (36.67%) have item codes absent from the fitted population. The sample is small, selected by date resolvability, contains a heavy-tailed target and has unverified business units. Performance is unsuitable for a reliability claim or broad future business use. Test results will not be reused for undisclosed tuning.

[Evaluation metrics](../models/business_regression/nop_domestic_invoice_line_value/v1/evaluation_metrics.json), [actual versus predicted rows](../models/business_regression/nop_domestic_invoice_line_value/v1/holdout_predictions.csv), and [split assignments](../models/business_regression/nop_domestic_invoice_line_value/v1/split_assignments.csv) retain all executed values.

## 7. Model catalogue and artifacts

The consolidated catalogue includes four actual-source exploratory models, their datasets/counts, metrics, baseline comparisons, artifact paths, prediction interfaces and limitations. Blocked candidates have reasons and no placeholder artifacts. The synthetic demonstration is explicitly excluded from actual-data model counts.

- [Machine-readable catalogue](../models/model_catalogue.json)
- [Tabular catalogue](../models/model_catalogue.csv)

New trained artifacts, model version **1.0.0**:

1. `models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.joblib`
2. `models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.joblib`

Each has matching metadata, input schema, dataset version/hash, source provenance, selected parameters, seed, dependency versions, chronological periods, metrics, target definition, exploratory status and limitations. New metadata declares `inference_adapter: tabular_regression_v1` and `problem_type: regression`. Its frequency is per supplied feature row; a future-period horizon is not applicable. Artifact paths are repository-relative for discovery and delivery.

The original monthly artifacts remain at:

- `models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib`
- `models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib`

They were loaded and their stored test evidence recalculated without training. Existing test MAE/RMSE remain **8.60/9.57** and **7.85/8.81** respectively, against a last-value baseline **7.00/8.06**. Their two-month test remains too small for reliable forecasting. Their original metadata and bytes are unchanged. [Existing-model verification](../evaluation/actual_data_ml_training/v1/existing_model_verification.json) and [reconstructed stored holdout rows](../evaluation/actual_data_ml_training/v1/existing_monthly_holdout_predictions.csv) document this check.

## 8. Targets not newly trained

| Candidate | Source evidence / blocker | Minimum external action |
| --- | --- | --- |
| Larger-source line-value model | The large invoice source has 100,183 nonblank rows but only 37 strictly historical, fully reference-consistent resolved dates in the executed probe. Row count does not satisfy temporal-diversity gates. | At least 60 such dates for the predeclared split, 23 more than available, plus target-quality/source-scope confirmation. No unauthorized merging with the small export. |
| Complete invoice/transaction volume | Only the confirmed-date subset exists; identity scope, lifecycle, completeness and unresolved dates remain open. | Resolve the 82 unresolved references in the small workbook, confirm event/identity/completeness, and provide mature regular history. A nonseasonal monthly comparison needs at least 24 complete months for 12/6/6 train/validation/test; seasonal evaluation needs longer history. |
| Sales/order volume | Order details are not unique orders; dates, lifecycle, repeated exports and complete periods are unresolved. | Validate order identity, dates, lifecycle and mature complete period capture. |
| Recognized revenue / monthly sales value | Repeated document totals, alternate representations, tax/currency bases, recognition and credit/debit adjustments are unreconciled. | Finance-confirmed target/grain, source authority, currency/tax/recognition/adjustment rules and a complete time series. |
| Profit/margin | Realized costs and attributable expenses aligned to recognized revenue are absent. | Supply validated revenue, realized costs and expense history with period/entity/currency alignment. |
| Product/service demand | `Manual` is not a validated physical unit; item/service identities, quantities, returns and cancellations are unresolved. | Validate units and identity, event capture, lifecycle and complete item-level histories. |
| Inventory/stockout | Mixed cumulative/movement extracts, many missing item codes, unknown opening balances and movement signs. | Stable item/warehouse keys, opening balances, dated signed movements and repeated stock snapshots. |
| Customer propensity | No eligible historical cohort, matured positive/negative labels or point-in-time features. | Supply identity links, cohort and decision/label windows, complete outcomes and mature follow-up. |
| Cancellation/delivery | Current line states and promised dates are not observed status transitions or actual delivery outcomes. | Stable event identities, dated lifecycle/actual outcomes, maturity/censoring and pre-outcome feature snapshots. |
| Currency rates | Exchange workbooks have explicit synthetic title markers. | Genuine timestamped historical rate data; no synthetic substitution. |

The detailed source-linked assessment and blocked catalogue entries record relevant tables, fields and existing date-quality evidence. No source date ambiguity, missing value, realized cost, negative classification outcome, relationship or business approval was invented. No additional algorithms were installed to increase model count.

The [environment record](../evaluation/actual_data_ml_training/v1/environment.json) identifies the exact verified interpreter and installed packages. The system Python matched the saved artifacts; the project `.venv` has a different scikit-learn version. XGBoost, statsmodels and Prophet were unavailable in the verified interpreter. No package was installed or upgraded, and no unsuitable time-series dataset was created to exercise those libraries.

## 9. Fresh-process inference and integration

All **four actual-source artifacts** loaded in new Python processes and returned JSON-compatible finite predictions for their intended targets. For each new artifact, all 30 saved test predictions were reproduced and MAE/RMSE/R²/SMAPE/reference-macro MAE recalculated against actual labels. SHA-256, metadata/bundle schema, dataset/target identity and version checks passed. Invalid values, missing features, wrong target IDs, semantic relabeling and tampering were tested.

New callable interface: `prediction.tabular_regression.predict_tabular_regression(input_data, model_path=...)`. A reusable adapter was added to `src/prediction/model_adapters.py`, exposing `supports(metadata)` and `predict(path, inputs)`. Existing discovery found all **four actual models and two prepared datasets** with one matching adapter family per model. New feature-row regression requests must use the tabular adapter; the teammate's existing monthly horizon path does not supply row features. No query-service change was made.

[Fresh-process verification](../evaluation/actual_data_ml_training/v1/new_model_verification.json), [adapter/discovery verification](../evaluation/actual_data_ml_training/v1/adapter_discovery_verification.json), [example request](../evaluation/actual_data_ml_training/v1/example_request.json), [Ridge response](../evaluation/actual_data_ml_training/v1/ridge_regression_example_response.json), and [Random Forest response](../evaluation/actual_data_ml_training/v1/random_forest_example_response.json) provide the handoff evidence.

## 10. Tests and preservation

**41 selected tests passed; 0 failed, 0 errored, 0 skipped.** The run covered new tabular preparation/training/inference, existing actual-source monthly ML, the synthetic demonstration, discovery and two relevant dynamic-routing regressions. A subsequent **2-test follow-up passed** after repository-relative artifact-path handling and preservation checks. These counts overlap and are not a unique-suite total. The complete governance/application test suite was not rerun because those components were unchanged.

Coverage includes strict date rejection, whole-reference exclusions, native feature types, duplicate retention, missing/invalid inputs, target/identifier exclusion, document-disjoint chronology, no future-label baseline use, minimum independent sample gates, zero-safe metrics, fixed-seed reproducibility, overwrite rejection, complete pipeline serialization, fresh-process loading, target/schema consistency, tampering and protected-file hashes.

- [Test results](../evaluation/actual_data_ml_training/v1/ml_test_results.json)
- [Test transcript](../evaluation/actual_data_ml_training/v1/ml_test_transcript.txt)
- [Follow-up results](../evaluation/actual_data_ml_training/v1/portability_followup_test_results.json)
- [Delivery and artifact checks](../evaluation/actual_data_ml_training/v1/delivery_verification.json)
- [Protected-file baseline](../evaluation/actual_data_ml_training/v1/protected_manifest_before.json)
- [Final preservation and model/data integrity check](../evaluation/actual_data_ml_training/v1/final_integrity_verification.json)

The source inventory, preparation, actual training, fresh-process inference and tests all executed. All reported model metrics are from executed evaluations or explicitly identified preserved evaluation predictions. Software fixtures were temporary test inputs only and are not included in actual-source training outputs or catalogue metrics.

## 11. Exact implementation and deliverable paths

New ML source files:

- `src/features/prepare_invoice_line_value.py`
- `src/features/tabular_regression.py`
- `src/training/ml_inventory.py`
- `src/training/tabular_regression.py`
- `src/training/nop_actual_data_ml.py`
- `src/prediction/tabular_regression.py`
- `tests/test_tabular_ml.py`

Existing ML source modified: `src/prediction/model_adapters.py` only. The existing monthly and synthetic trainers/inference modules were not modified in this task.

Data/specifications: `data/preparation_specs/nop_domestic_invoice_line_value_v1.json` and `data/nop_domestic_invoice_line_value/v1/` (CSV, metadata, query/training specifications and exclusions). New artifacts and evaluation files are under `models/business_regression/nop_domestic_invoice_line_value/v1/`. The consolidated catalogue is `models/model_catalogue.json` and `.csv`. Source audit, verification, examples and tests are under `evaluation/actual_data_ml_training/v1/`.

Handoff instructions: [docs/development/nop_ml_model_integration_guide.md](../docs/development/nop_ml_model_integration_guide.md).

## 12. Completion and remaining dependencies

The feasible ML lifecycle was executed for the newly supported raw-field proxy and the existing artifacts were verified without retraining. It yielded two new exploratory models with honest negative baseline comparisons. There is no additional defensible, sufficiently mature complete business forecasting/classification target established by the current evidence.

Next business-use work requires better representative history, validated monetary/unit semantics, confirmed feature availability at a real decision time and a new untouched prospective evaluation set. Finance/process/data owners must resolve the target-specific requirements above. Teammate-owned application integration should consume the explicit model/target schemas and keep exploratory status visible. Training success, saved artifacts and passing software tests do not establish production readiness.
