# NOP dynamic business intelligence implementation report

**Date:** 3 November 2026  
**Result:** Delivered a working dynamic request, planning, analytics and model-inference integration using actual NOP-derived data. The unrestricted natural-language and production-serving requirements remain conditional on a configured language interpreter, approved semantics and production integrations. They are not claimed complete.

## Existing implementation reused

The repository already contained source adapters, schema discovery, the metadata catalogue, requirement assessment, semantic review and approval, target/observation/preparation specifications, durable execution controls, the preparation worker, reconciliation, artifact storage and publication. It also contained a synthetic demonstration pipeline and a separate actual-source exploratory dataset with Linear Regression and Random Forest artifacts. These components were inspected and retained.

No new actual-data model was trained merely to increase model count. The two existing compatible models were loaded and used. The synthetic model and its metadata were preserved and excluded from actual-data query validation.

## Implementation delivered

| File/component | Capability |
| --- | --- |
| `src/business_prediction/query.py` | Runtime question/structured-request entry point; target resolution; structured analytical plans; model dispatch; partial answers; clarification; authenticated assessment and worker bridges; versioned prepared-data training facade. |
| `src/business_prediction/query_assets.py` | Dataset/model discovery; source/data/artifact hashes; root containment; dependency compatibility; reuse of existing catalogue discoveries or registered adapters. |
| `src/business_prediction/query_analysis.py` | Generic summaries, means, min/max, distinct stored-value counts, observed series, change, grouped comparison/ranking, anomaly checks and evidence-gated summation. |
| `src/prediction/model_adapters.py` | Trusted adapter wrapping the existing monthly regression inference function. No question-to-model routing table. |
| `src/business_prediction/runtime/factory.py` | `runtime.business_query_service(...)` shares the existing runtime and catalogue. |
| `src/training/monthly_regression.py` | Existing trainer generalized from one data-mode string to explicit non-synthetic exploratory specifications; new version metadata, feature schema and truthful dependency-availability records. Existing chronological evaluation remains in use. |
| `src/prediction/monthly_regression.py` | Existing inference retained, with generic exploratory mode validation and checks that metadata objective, target, data mode, dataset fingerprint and periods match the bundle. |
| `src/business_prediction/__main__.py` | Local JSON command interface. |
| `src/data/validate_dynamic_business_queries.py` | Reproducible actual-NOP scenario validation, source profiles, fresh-process inference and protected-file checks. Business examples here are test inputs only. |
| `tests/test_dynamic_business_query.py` | Focused query, schema, analytics, lifecycle, integrity, interpretation, governance and inference tests. |

The package exports `DynamicBusinessQueryService`, `RequestInterpreter` and `JSONRequestInterpreter`. No dependencies were installed. No existing source files, saved models, framework contracts or publication rules were replaced.

## Request interpretation and dynamic planning

The same `process(request)` entry point accepts arbitrary question strings or structured requirements. Available source schemas, prepared dataset specifications and model definitions are discovered at runtime. Explicit dataset/objective IDs select discovered assets; unmatched or ambiguous concepts receive clarification. Business questions and NOP field names are absent from reusable routing code.

The local text interpreter is deliberately limited. A provider-neutral `JSONRequestInterpreter(complete)` adapter lets the teammate connect an existing LLM callback. The callback receives the question and discovered schema context and proposes a structured request. It cannot grant approval, supply executable expressions, or introduce arbitrary import/artifact paths. Interpreter-selected targets remain provisional and yield partial exploratory results. No remote language-model provider or credentials were supplied or configured, so arbitrary natural-language understanding has not been demonstrated.

Analytical plans record the exact target, dataset version/hash, specification hash, operations, filters, grouping, requested horizon and selected model artifact hashes. Identical specifications produce identical plan IDs. `plan_only` returns this plan without execution.

Analysis validates the selected field roles from the dataset specification instead of assuming columns named `period` or `target_count`. It rejects ambiguous dates, invalid/nonfinite targets, unresolved grouping and duplicate time observations for series/change. Missing required observations fail unless exclusion is explicit and counted. No missing periods are generated or zero-filled. Summation requires explicit additive semantics and evidence; document totals are not presumed additive. Equal comparison values share a rank.

## Governance boundaries

Exploratory processing is visibly labeled `business_approved: false` and `controlled_worker_execution: false`. It uses current prepared data with recorded provenance; it does not create semantic approvals, worker receipts or publication records.

Approved processing delegates structured requirements to the existing authenticated requirement assessment engine. Submission and assessment can use separate authorized identities. Even a ready assessment returns `execution_authorized: false`.

The worker bridge advances only an already authorized execution request through existing begin, operation, reconciliation and finalize methods. It does not issue execution permission or publication. Tests verify that an unapproved request cannot run and successful preparation does not automatically publish. Production-approved model serving remains dependent on a real governed publication/access integration.

## Actual sources and data integrity

Validation reused pinned discovery evidence for **17 original files, 20 tables and 521 fields**. It recomputed all original-source hashes against the readiness manifest. It returned physical profiles for all 20 tables through the same request entry point. Existing prefix field profiles retain their coverage labels; a prefix distinct count is not represented as a full-table count. Original sources were not rescanned for new business interpretations or silently cleaned.

**Final checks: 17/17 original source hashes matched; all 3 existing model artifact hashes matched their metadata.** The existing synthetic and both actual-source models remained intact. See [final integrity verification](../evaluation/dynamic_business_intelligence/final_integrity_verification.json).

The forecast dataset is `data/nop_confirmed_date_invoice_count_exploratory.csv`, derived earlier from `dataset/Sales Invoice Details.xlsx`, `Sheet1`. Its target counts distinct invoice references whose every detail row has one consistent unambiguous day-first date. It includes **152 references** and excludes **82 unresolved references** from 234 raw references. The prepared series has **10 observed monthly buckets, December 2025–September 2026**; 8 interior months were eligible for the earlier evaluation. It is a confirmed-date subset; extraction completeness and business identity/lifecycle rules remain unapproved. See the [existing assumptions](nop_actual_data_ml_exploratory_assumptions.md).

## Actual execution results

Thirteen business scenarios were submitted through the same entry point:

| Scenario | Actual status and evidence |
| --- | --- |
| Recognized revenue forecasting | Clarification required; no validated recognized-revenue target or compatible model. |
| Profit forecasting | Clarification required; no defensible profit target or mature history. |
| Monthly sales analysis | Clarification required; sales meaning and target are not established by the prepared count series. |
| Broad monthly invoice-count forecast | Partially answered using the explicitly identified confirmed-date subset. |
| Explicitly selected confirmed-date subset forecast | Answered by both existing models with provenance and exploratory status. |
| Historical selected-target series | Answered with the 10 observed monthly values and exact target definition. |
| Highest observed selected-target period | Answered; January and May 2026 both have a stored subset count of 22 and share first rank. |
| Product/service demand | Clarification required; no validated item/unit/quantity/outcome target. |
| Inventory requirements | Clarification required; no validated demand/movement/replenishment target. |
| Repeat-purchase prediction | Clarification required; no validated customer cohort, event window or outcome labels. |
| Business-unit comparison | Clarification required; no prepared unit dimension and agreed performance measure. |
| Sales decrease explanation | Clarification required; no supported sales measure or causal evidence. |
| Unusual business-performance changes | Clarification required; no validated general performance target; generic anomaly analysis is available for explicit prepared measures. |

The run returned **3 answered scenarios, 1 partial scenario, 9 clarification responses, and 20 physical source profiles**. [Scenario requests/results](../evaluation/dynamic_business_intelligence/actual_request_results.json), [source profiles](../evaluation/dynamic_business_intelligence/actual_source_profiles.json), and [validation summary](../evaluation/dynamic_business_intelligence/validation_results.json) preserve the evidence. The ranking tie correction was verified separately in [ranking follow-up](../evaluation/dynamic_business_intelligence/ranking_followup.json).

## Model reuse and evaluation

The stored chronological evaluation used 5 training months (January–May 2026), 1 validation month (June), and 2 test months (July–August). These are existing evaluation results, not a new training run:

| Model | Test MAE | Test RMSE | Baseline MAE | Baseline RMSE |
| --- | ---: | ---: | ---: | ---: |
| Linear Regression | 8.60 | 9.57 | 7.00 | 8.06 |
| Random Forest | 7.85 | 8.81 | 7.00 | 8.06 |

Neither model beat the last-observed-value baseline. The two-month holdout cannot support a reliable champion choice. Models are returned separately; the query layer does not select on training accuracy or reuse these models for revenue, profit or demand.

Existing actual-source artifacts:

- `models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib`
- `models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib`
- Matching `.metadata.json` sidecars and existing `evaluation_metrics.json` in that directory.

Example post-cutoff estimates for October/November 2026: Linear Regression 12.142857 / 11.214286; Random Forest 14.911875 / 14.911875. The forecast origin is the stored September 2026 source cutoff. These periods are not automatically reanchored to today's date; an updated authoritative extraction and freshness policy are required for operational forecasts.

The generic training facade was tested on isolated software fixtures with unseen field names and objective IDs. It reused the existing trainer, produced versioned artifacts, refused overwrite and reproduced predictions with a fixed seed. Those tests are not actual NOP training or business-performance evidence. Current dependencies in the verified system Python include scikit-learn; XGBoost, statsmodels and Prophet are absent. No additional model families were installed or forced onto this short series.

## Validation executed

| Run | Actual result |
| --- | --- |
| Interrupted broad regression run, recovered on continuation | **173 passed**, 771.125 seconds. Covered the prior query slice plus discovery, assessment, specifications, execution, worker/publication, exploratory ML, aggregation and readiness. |
| Regression run after structured analytics and governance bridges | **51 passed**, 24.361 seconds. Covered query handling, actual exploratory ML, aggregation and discovery. |
| Final focused run | **32 passed**, 0 failures/errors/skips. `python -m unittest -v tests.test_dynamic_business_query tests.test_actual_data_ml_exploratory`. |
| Follow-up for ranking ties and omitted grouping | **2 passed**, 0 failures/errors. Only affected tests were rerun. |
| Follow-up for saved forecast target/dataset overrides | **1 passed**, 0 failures/errors. Invalid runtime overrides returned no predictions. |
| Actual-data scenario runner | Completed successfully: 13 scenarios, 20 source profiles, all source hashes matched, existing models unchanged. |
| Fresh Python process | Both existing actual-source artifacts loaded and returned finite JSON forecasts. |
| `python -m business_prediction` CLI | Completed successfully; 2 models, canonical October/November 2026 periods, finite numerical predictions. |

These runs overlap; their counts must not be added as unique tests. A complete repository test suite was not rerun after the final additions. Initial development parsing/import failures were corrected; no unresolved failure remains in the executed final checks.

Exact focused evidence: [test results](../evaluation/dynamic_business_intelligence/focused_test_results.json), [transcript](../evaluation/dynamic_business_intelligence/final_focused_tests.txt), [follow-up results](../evaluation/dynamic_business_intelligence/targeted_followup_test_results.json), [forecast constraint results](../evaluation/dynamic_business_intelligence/forecast_constraint_test_results.json), and [CLI validation](../evaluation/dynamic_business_intelligence/cli_validation.json).

## Teammate handoff

Set `PYTHONPATH=src`, then call `DynamicBusinessQueryService(root).process(request)`. A complete example is [example_request.json](../evaluation/dynamic_business_intelligence/example_request.json); [fresh_process_prediction.json](../evaluation/dynamic_business_intelligence/fresh_process_prediction.json) shows the expected response structure. The [integration guide](../docs/development/dynamic_business_query.md) covers Python/CLI use, request fields, LLM callback registration, model adapters, metadata requirements, approved assessment and controlled worker execution. The [architecture guide](../docs/architecture/business_prediction_framework_architecture.md) contains the current request flow.

## Remaining requirements and owners

| Requirement | Owner / minimum next action |
| --- | --- |
| General natural-language understanding | Teammate/application owner: register the existing LLM through `JSONRequestInterpreter(complete)` and validate its schema/evidence interpretation on unseen questions. No question catalogue is required. |
| Invoice business target | NOP process owner: confirm identity scope, lifecycle, date grammar, unresolved-date treatment and permitted target definition. |
| Data maturity | ERP/data operations: provide authoritative extraction cutoffs, closed-period completeness, zero-versus-unknown evidence and substantially longer mature history. |
| Revenue/sales meaning | Finance/business owner: distinguish line amounts, repeated document totals, taxable/GST-inclusive amounts, credit/debit adjustments and recognized revenue; approve one reconciled target. |
| Profit | Finance: supply validated recognized revenue, realized costs and attributable expense periods; inventory cost-like values alone do not establish realized costs. |
| Demand/inventory | Operations: validate product/service identity, units, quantities, returns/cancellations, dated movements, stock snapshots and applicable replenishment evidence. |
| Customer propensity | Business/data owner: define eligible cohorts, observed repeat-purchase events, negative outcomes and decision/label windows. |
| Business-approved serving | Platform/security/business owners: supply real authenticated semantic/specification/execution/publication approvals and approved model access/lifecycle integration. |

The delivered system executes useful actual-data analytics and existing-model forecasts, supports new structured schemas and targets, and exposes provider-neutral language and inference interfaces. It does not guarantee arbitrary-language understanding without a configured interpreter, fabricate missing business targets, establish causation, or claim production readiness.
