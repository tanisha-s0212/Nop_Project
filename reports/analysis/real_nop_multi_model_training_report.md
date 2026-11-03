# Real NOP multi-model training status report

**Assessment date:** 3 November 2026  
**Outcome:** No real-NOP model was trained. The repository evidence does not establish any approved, sufficiently prepared target dataset. No requested real-NOP `.joblib` artifact was created. The existing synthetic random-forest artifact is not counted as a real-NOP model.

## Data and approval decision

The current readiness evidence covers 17 original files (14 Excel workbooks and 3 CSVs), 20 physical tables and 521 columns. All 17 current source hashes match `reports/analysis/nop_readiness_evidence/source_manifest_before.json`. Original source files were preserved and not used for model training.

The only file under `data/` is `synthetic_monthly_invoice_volume.csv`. `models/` contains the versioned synthetic random-forest bundle `nop_invoice_volume_model.joblib` and its metadata; it records `data_mode: synthetic` and `actual_nop_data_used: false`. The existing training entry point regenerates and verifies that synthetic series and rejects data that does not match the generator. It is not an actual-data training workflow.

The readiness assessment records `training_ready: false`, `artifact_published: false`, and status `blocked`. The response log has 17 decisions and **zero confirmed business approvals**; D01–D13 are core to the recommended invoice-volume discussion, with D12 still proposed. The readiness evidence also lacks an authenticated NOP runtime and exact approved semantic, target, observation and preparation records. No external approval store was connected, so this report does not claim none exists outside the repository; no usable approval evidence was supplied to this workspace.

## Candidate objectives

| Candidate | Available evidence | Why it is not a trainable real-NOP target now |
| --- | --- | --- |
| Sales / invoice-document volume | `Sales Invoice Details.xlsx` has 337 detail lines and 234 consistent raw invoice references. `Invoice Date` evidence has 107 ambiguous cells and only ten observed months among calendar-resolved full-year dates. | Best candidate for owner discussion, but no approved authoritative source/version, invoice identity scope, event/lifecycle rule, date interpretation, closed-period completeness, zero-versus-missing rule, horizon or target specification. The observed references are not a validated monthly target series. |
| Revenue / financial value | Invoice and GST representations contain value fields; GST is an alternate representation, not additional history. Document totals repeat across detail lines; the report records quantity/base and tax arithmetic exceptions. | No approved recognized-revenue, taxable-value, currency, adjustment/sign, line/document aggregation or lifecycle definition. Partial date history and repeated totals make direct field regression or summation invalid without owner-approved semantics. |
| Product/service demand | Invoice/order lines contain product/service-like rows and quantities; master and classification tables are available. | Units and service quantities are not consistently established; product identity/crosswalk, returns/cancellations, event/date scope and per-series history are unapproved or incomplete. Order rows are detail-grain, not one row per order. No validated join/target dataset exists. |
| Inventory / stockout | Inventory audits contain movement-like fields; item masters include current stock-related values. | The large audit has 98,104 movement rows without a raw item code; grouped audit extracts are not a regular snapshot panel and cover only three observed months under current date evidence. Opening balance, movement signs/types, item/warehouse identity, as-of stock and stockout outcomes are unverified. |
| Customer propensity / classification | Customer masters and purchase-like order/invoice references exist. | No authorized eligible-customer cohort, historical exposure window, mature positive/negative outcomes or point-in-time customer features. Current master snapshots do not create historical labels; customer mapping is unapproved. |

Other assessed candidates (cancellation risk, delivery delay, unknown numerical outcomes, collections/recognized revenue, tax/adjustment activity and FX) are also not training-ready. The objective assessment documents source fields, date coverage, grain, candidate relationships and unresolved evidence for each. Tax/adjustment and segmented forecasting are only conditionally feasible and still lack approvals, sufficient mature periods and an approved target.

## Status of the five requested models

“Training completed”, “evaluation completed”, “real-data artifact saved” and “artifact independently loaded” refer only to **approved real-NOP data**. A synthetic artifact does not satisfy those gates.

| Requested model | Implementation/dependency status | Real data selected | Target approved | Dataset prepared | Training | Evaluation | Real-NOP artifact saved | Fresh-process real-NOP load |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Linear Regression | No reusable regression trainer found. scikit-learn is installed. | No | No | No | Not run | Not run | No | No |
| Random Forest | Existing `src/training/train_invoice_volume.py` implements synthetic-only Random Forest training; it rejects non-generator data. | No | No | No | Not run on NOP data | Not run on NOP data | No. Existing `nop_invoice_volume_model.joblib` is synthetic only. | No real-NOP model to load |
| XGBoost | No XGBoost trainer found; `xgboost` is unavailable in the active Python environment. | No | No | No | Not run | Not run | No | No |
| SARIMA/SARIMAX | No time-series trainer found; `statsmodels` is declared in `requirements.txt` but unavailable in the active Python environment. | No | No | No | Not run | Not run | No | No |
| Prophet | No Prophet trainer found; `prophet` is unavailable and is not listed in the current requirements. | No | No | No | Not run | Not run | No | No |

Current dependency discovery used the available Python 3.12.10 environment: `scikit-learn` and `joblib` are importable; `xgboost`, `statsmodels` and `prophet` are not. No dependency was installed. Dependency availability does not change target/data readiness.

All five required real-NOP artifact filenames are absent: `linear_regression_model.joblib`, `random_forest_model.joblib`, `xgboost_model.joblib`, `sarima_model.joblib`, and `prophet_model.joblib`. No score, baseline comparison, champion selection or validation claim is made for them.

## Minimum actions to unblock

1. **NOP process/business owner:** answer the core D01–D13 questions in `reports/analysis/initial_prediction_business_clarification.md`; choose the decision, target, entity scope, bucket, horizon, cadence and acceptance/evaluation design.
2. **ERP/source and data operations owners:** identify and supply an authoritative production extract with source/version, issuer and document scope, date/event semantics, extraction watermark, closed-period completeness and enough mature history for chronological training and holdout. Resolve ambiguous dates from source evidence; do not infer a global date format.
3. **ERP/document and finance/process owners as applicable:** approve invoice identity, line-to-document count rules, event population and void/cancellation/return/adjustment treatment. For revenue or quantities, separately approve the measure, additivity, units, currency and lifecycle basis. For product/inventory/propensity objectives, provide the missing stable identities, history/cohort or stock snapshots and outcome evidence described above.
4. **Authorized project/business approvers:** record exact, scoped approvals for source semantics, target/observation definitions, preparation operations and execution/training purpose through the configured authenticated approval/runtime boundary. No response-log flag or owner-role label substitutes for an authenticated approval record.
5. After approval, create and validate the target dataset through supported operations (or separately authorize the smallest required generic capability), then reevaluate per-model dependency and task suitability. Install only model dependencies needed for the approved workflow and rerun chronological baseline comparisons before producing versioned artifacts.

## Integrity and scope

This assessment made no changes to original source files, business-prediction framework modules, existing model artifacts or approval records. Current source SHA-256 hashes match all 17 entries in the readiness manifest. No real-data preparation or model fitting was attempted because it would violate the task’s approval and target requirements. No synthetic results are presented as NOP results.

Evidence references:

- `reports/analysis/nop_dataset_readiness_report.md`
- `reports/analysis/nop_prediction_objective_assessment.md`
- `reports/analysis/nop_readiness_evidence/readiness_assessment.json`
- `reports/analysis/nop_readiness_evidence/approval_blockers.json`
- `reports/analysis/initial_prediction_clarification_evidence/decision_response_log.csv`
- `docs/development/nop_first_training_dataset_workflow.md`
- `src/training/train_invoice_volume.py` and `models/model_metadata.json` (synthetic model provenance)
