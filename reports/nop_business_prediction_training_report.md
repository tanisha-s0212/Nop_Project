# NOP business-prediction training report

> This was the prior actual-data readiness result. An exploratory confirmed-date subset and two models have since been evaluated; see [the final completion report](nop_actual_data_ml_exploratory_completion_report.md). The results are not business-approved and do not forecast total invoice volume.

**Run date:** 3 November 2026  
**Result:** No actual-NOP training dataset passed the target, history and semantic evidence review. **Zero models were trained or evaluated on actual NOP data.** The implementation did not alter source files, invent approval, or convert the existing synthetic model into a real-data result.

## Source and workflow review

The reviewed source inventory contains 17 original files (14 Excel workbooks and 3 CSV files), 20 tables and 521 physical columns. Existing readiness evidence re-opened all sources via the project adapters; current hashes match all 17 recorded source hashes. Existing inventory, quality, relationship, date-coverage, objective-feasibility, business clarification, preparation-specification, semantic approval, controlled-execution, worker/publication and synthetic-model docs/tests were reviewed.

The framework already provides schema discovery, evidence/semantic contracts, objective assessment, target/observation/preparation specifications, controlled execution, reconciliation and publication gates. These controls were not changed or bypassed. A versioned, approved-worker monthly grouping and aggregation operation has since been added; arbitrary derived expressions and lag-feature generation are not implemented. The standalone invoice model workflow is intentionally synthetic-only and verifies data against its generator. It is not connected to NOP approvals or actual-data preparation.

The current NOP target readiness and candidate-by-candidate source evidence are documented in [objective readiness](nop_prediction_objective_readiness.md) and the existing [NOP prediction objective assessment](analysis/nop_prediction_objective_assessment.md).

## Preparation and training results

| Deliverable/status | Actual-NOP result |
| --- | --- |
| Original sources inspected | 17 files; 14 Excel and 3 CSV, covering 20 tables. All 17 source hashes match the readiness manifest. |
| Approved actual training data available | No. The existing readiness JSON reports `training_ready: false`, `artifact_published: false`, status `blocked`. |
| Actual exploratory datasets prepared | 0. All candidates need unresolved target meaning, date/source completeness, usable grain/history, missing relationships, or outcomes. No data was silently filtered, zero-filled, joined or aggregated. |
| Actual NOP models trained | 0. No model metrics or champion can be reported. |
| Actual NOP `.joblib` artifacts created | 0. None of the five requested real-data artifact files exists. |
| Existing synthetic models | One existing demo: `models/nop_invoice_volume_model.joblib`, Random Forest 1.0.0 trained on 180 reproducible synthetic months. Its metadata explicitly says `data_mode: synthetic` and `actual_nop_data_used: false`; it is not counted as an NOP model and was not overwritten. |

### Requested algorithms

| Model | Existing code / dependency state | Training decision and status |
| --- | --- | --- |
| Linear Regression | No reusable linear-regression trainer; scikit-learn is available. | No valid approved or defensible regression target/dataset. Not trained; no metrics or artifact. |
| Random Forest Regressor | Existing implementation is restricted to the reproducible synthetic invoice-volume dataset. | No NOP target series passed readiness. Existing synthetic artifact is not real-NOP. Not trained on NOP data. |
| XGBoost Regressor | No trainer found; `xgboost` is not importable in the active environment. | No eligible target, so no install was attempted. Not trained; no artifact. |
| SARIMA/SARIMAX | No time-series trainer found; `statsmodels` is declared but unavailable in the active environment. | No regular, sufficiently long, validated actual series. Not trained; no artifact. |
| Prophet | No Prophet trainer found; `prophet` is unavailable and absent from the current requirements. | No suitable actual series; no install was attempted. Not trained; no artifact. |

The active Python environment is 3.12.10. `scikit-learn` and `joblib` are available; `xgboost`, `statsmodels`, and `prophet` are not. The repository virtual-environment interpreter is not present at its documented path, and no global dependencies were installed.

## Objective comparison and outcomes

No objective is sufficiently training-ready, so no model-comparison metrics or baseline scores exist for actual NOP data. “Feasible with conditions” in existing assessment reports is a discussion/readiness classification, not permission or evidence that a target dataset can be built today.

| Candidate objective | Feasibility evidence | Training result |
| --- | --- | --- |
| Invoice/document volume | Strongest discussion candidate: 337 lines / 234 raw references; 107 ambiguous dates; only ten observed months; source, scoped key, lifecycle, completeness, horizon and approval unresolved. | Not prepared or trained. A generic approved-worker time-bucket/count operation is now available, but no defensible target specification, complete series, or execution approval exists. |
| Sales/order volume | Large detail exports exist, but they are not one row per order; order date coverage/completeness and order lifecycle are not established. | Not prepared or trained. |
| Revenue / value | Invoice, GST and note amounts include repeated document totals and alternate representations; accounting recognition, aggregation, currency and adjustment rules unresolved. | No verified revenue dataset. Not trained. |
| Monthly profit/margin | No aligned validated actual revenue, realized COGS and expense series; inventory cost-like values are not validated invoice costs. | Blocked. Do not equate sales/revenue with profit. |
| Product/service demand | Goods/service lines and item tables exist, but units, keys/crosswalks, returns/cancellations and complete per-item chronology are unresolved. | No defensible target panel. Not trained. |
| Inventory / stockout | Audit has 108,129 rows, 98,104 movements without raw item code, and three observed months; no validated snapshot panel/opening balance/sign rules. | Not prepared or trained. |
| Customer propensity / classification | No historical eligible cohort, exposure/time-at-risk, mature positive/negative outcomes, or approved customer mapping. | No classification target. Not trained. |
| Other assessed targets | Cancellation/delivery, settlement/recognized revenue, tax adjustments and currency rates each lack required event history, mature periods, authority or genuine production sources; exchange-rate files are explicitly synthetic. | No eligible actual target. Not trained. |

Detailed sources, candidate features/fields, temporal and join caveats, and objective-specific missing evidence are listed in `reports/nop_prediction_objective_readiness.md` and the existing analysis evidence. No score is reported where a model did not run.

## Artifact status

The following actual-NOP artifacts were **not created** because no objective met the data gates:

- `models/linear_regression_model.joblib`
- `models/random_forest_model.joblib`
- `models/xgboost_model.joblib`
- `models/sarima_model.joblib`
- `models/prophet_model.joblib`

No actual dataset fingerprint, training period, feature schema, metric, baseline, or artifact verification can be claimed. The existing synthetic artifact and its metadata remain explicitly separate.

## Tests and integrity checks

Executed from the repository root with `PYTHONPATH=src`:

```text
python -m unittest -v tests.test_discovery tests.test_nop_readiness_evidence tests.test_invoice_volume_model
Ran 30 tests: OK
```

The 30 passed tests cover source adapters/discovery, synthetic readiness/approval gates, feature/training reproducibility and the existing synthetic inference path. They do not establish NOP target readiness or evaluate a real-NOP model. A final integrity check found 17/17 original sources match their recorded hashes; the existing `src/business_prediction/` files and synthetic `.joblib` artifact remained unchanged by the tests. No actual-data training was attempted because the readiness checks fail before a defensible target dataset exists.

## Exact unblocking actions

1. NOP business/process owners answer and approve the core D01–D13 decisions in `reports/analysis/initial_prediction_business_clarification.md`, including objective, target population, entity scope, time bucket, horizon, cadence and evaluation criteria.
2. ERP/source and data-operations owners provide the authoritative production source/version, owner, extraction watermark, closed-period completeness and enough mature history for chronological training and protected validation. For invoice volume, verify invoice identity, source-specific event-date interpretation, lifecycle population and missing-period policy from source evidence.
3. For revenue/profit, provide linked recognized revenue and actual cost/expense components with period, entity, currency and adjustment/settlement definitions. For demand, inventory and propensity, provide the validated units/keys, repeated snapshots or eligible cohorts and outcomes described in the objective-readiness report.
4. Obtain authenticated semantic, target/observation, preparation, execution and any required publication approvals through the configured runtime. The local response-log booleans and synthetic test authority are not approvals.
5. After data gates pass, add only the missing generic approved preparation operator if needed, then compare suitable algorithms in an isolated environment with the required dependencies and record versioned, provenance-bound artifacts.

No production or business-approved readiness is claimed. Until these actions are complete, the safe outcome is to retain the evidence and keep the synthetic demonstration clearly labeled synthetic.
