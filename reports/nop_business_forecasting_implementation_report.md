# NOP business forecasting implementation report

> This records the controlled aggregation capability stage. It is superseded for the end-to-end exploratory result by [the actual-data completion report](nop_actual_data_ml_exploratory_completion_report.md).

**Run date:** 3 November 2026  
**Outcome:** Generic controlled monthly grouping and explicit aggregation are now supported by the existing preparation worker. No defensible NOP forecast dataset or trained actual-data model was produced because the available source evidence still does not establish an authorized invoice identity, date, lifecycle, period-completeness, or mature-history definition.

## Existing functionality reused

The implementation extends the existing specification registry, preparation operator registry, authorized worker, sealed artifact storage, lineage receipts, and worker reconciliation. Existing review, semantic approval, target, plan, execution, and publication controls remain in force. Aggregation cannot be run by calling a model helper or bypassing the existing authorized execution path. Existing synthetic invoice forecasting code and its artifact were not changed.

The 17 source files (14 Excel and 3 CSV) were rechecked against `reports/analysis/nop_readiness_evidence/source_manifest_before.json`; all 17 hashes matched. The existing evidence inventory describes 20 tables and 521 columns. No original source was modified.

## New controlled preparation capability

Added versioned `time_series_aggregation@1.0` support to the existing operation declaration and worker registries. The operation accepts explicit semantic binding references, output field identifiers, grouping bucket definitions, measure definitions, reconciliation declarations, and `missing_period_policy: observed_only`.

Supported operations:

- Group by explicitly bound native scalar fields.
- Bucket only canonical native date cells into month, quarter, or year. Ambiguous text dates and native datetimes are rejected; they need a separately reviewed interpretation.
- Aggregate an explicit numeric field with sum, mean, minimum, or maximum.
- Count rows or count distinct explicit identity tuples. Composite identities are supported when their components are separately bound.
- Recompute the aggregation during reconciliation and verify the exact output and schema.
- Emit only observed buckets. No missing period is converted to zero.

Null group keys, null measure or identity components, nonnumeric measures, invalid dates, duplicate output identifiers, undeclared bindings, absent fields, and unsupported grain changes fail closed. A grain-changing operation must be the last worker step. Its output must be rediscovered and receive new semantic bindings before downstream use. Existing local storage retains content digests and operation/source/authorization lineage; immutable publication still requires its existing lifecycle.

The capability does **not** add implicit joins, arbitrary Python expressions, arbitrary date parsing, automatic missing-period completion, or generic lag-feature construction. Joins continue to require explicit reviewed relationships and the current worker does not execute multi-table joins. Point-in-time predictor declarations remain governed by existing plan availability and leakage checks. These operations need a separately approved plan and suitable evidence before they can be used for business data.

## NOP objective assessment

Invoice/document volume remains the strongest owner-discussion candidate, but not a trainable target. Existing evidence for `Sales Invoice Details.xlsx` records 337 detail rows, 234 nonblank invoice references, 107 ambiguous invoice-date cells, and only ten months of calendar-resolved observations. The evidence does not approve:

- The issuer/series/year scope defining one document.
- Which lifecycle events count, including voids, cancellations, returns, or adjustments.
- The prediction-event date interpretation for unresolved values.
- Extraction watermark, mature history, closed-period completeness, or forecast horizon.
- Whether a period with no rows is truly zero activity or incomplete/missing data.

The new operation makes an approved monthly distinct-count construction technically expressible. It does not resolve these business and source decisions. No NOP aggregation was run, and no prepared NOP dataset was created.

Sales/order volume and item demand remain blocked by unresolved event/identity/UOM/lifecycle and completeness semantics. Monetary fields remain unsuitable as verified revenue: document totals repeat across detail lines and alternate GST representations exist. Profit remains blocked because linked recognized revenue, realized cost of goods sold, and operating expenses on aligned period/entity/currency bases are unavailable. No candidate passed target and history evidence review.

## Training and model artifacts

No algorithm was trained on actual NOP data. There is no defensible target dataset on which to compare models or evaluate a baseline, so this implementation created no business forecasting model artifact, evaluation metrics, or prediction interface. This avoids treating the existing synthetic Random Forest model as an NOP result. It remains separately identified by its existing synthetic-only metadata.

Model families are not reported as evaluated. The existing environment evidence reports scikit-learn/joblib available, while XGBoost, statsmodels, and Prophet were unavailable; no dependency was installed because no eligible target existed.

## Tests and verification

- `PYTHONPATH=src python -m unittest -v tests.test_time_series_aggregation_operator tests.test_preparation_specifications tests.test_worker_artifact_publication`: **68 tests ran; 67 passed and 1 failed** in the initial combined process. The failure was the existing custom-operator grain-change guard; the process had imported the implementation before its compatibility fix.
- Post-fix: `PYTHONPATH=src python -m unittest -v tests.test_worker_artifact_publication.StorageTests.test_unknown_registration_and_unsupported_grain_are_rejected tests.test_time_series_aggregation_operator`: **6 passed**. This re-ran the exact failed regression and all five final aggregation tests.
- Source integrity check against the readiness manifest: **17/17 hashes matched**.

The focused operator tests cover deterministic monthly distinct-document counts, observed-bucket-only output, reconciliation, registry integration, rejection of text/ambiguous dates, noncanonical native dates, and null identity values. The existing specification and worker publication suites were included to catch lifecycle and governance regressions. The post-fix verification covered the exact initial failure and all aggregation tests; the full 68-test combined suite was not rerun after the fix.

## Remaining decisions and next action

The business/process owner and ERP/data-operations owner must answer the existing invoice-volume clarification decisions (D01–D13): document identity scope, included lifecycle events, authoritative date interpretation, source authority, complete-period watermark, zero-versus-missing semantics, forecast horizon, and evaluation acceptance criteria. They must also provide sufficient mature history for a chronological holdout. Record authenticated semantic and target decisions, approve the preparation plan and execution, and then run the new operation through the controlled worker. A separate re-discovery and target approval is required before model training or business publication.

Until those inputs exist, the supported next action is to obtain the documented owner decisions and authoritative source completeness evidence; no actual NOP forecast should be trained or presented.
