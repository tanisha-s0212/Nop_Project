# NOP dataset readiness assessment

Assessment: 3 November 2026. **Status: blocked before preparation; no training dataset published.**

## Verified scope and method

Fresh recursive discovery found **17 source files: 14 Excel workbooks and 3 CSV files**, containing **17 worksheets plus 3 CSV tables (20 tables, 521 physical columns)**. No additional format or unreadable source was found in `dataset/`. All 17 source hashes match the recorded source-integrity evidence and remained identical before/after this assessment. Counts were measured, not assumed from earlier instructions.

The existing Excel/CSV adapters and discovery implementation reopened every source. All 20 physical row/column counts and raw headers match the validated inventory. Header-row configurations come from the prior inventory only when the source hash is identical. Full source extent discovery is distinct from the new 32-row prefix profiles. Existing full-table missingness, duplicates, dates, identifier and relationship evidence is reused because exact source bytes and physical layouts are unchanged; prefix results are not extrapolated.

Date evidence retains its original 2 November 2026 diagnostic cutoff. It is not reclassified as complete history as of today. Native, inferred and ambiguous dates remain separate. No source values were cleaned, coerced, joined, deleted, aggregated into targets or replaced with zero. The root-level `dataset.zip` contains 17 members whose SHA-256 hashes all match the 17 discovered source files. It is a byte-identical packaged copy, preserved without extraction and not counted as additional independent history; see the [archive review](nop_readiness_evidence/archive_review.json).

## Every discovered table

Rows are physical rows below the configured header, including empty rows. Grain labels are existing hypotheses, not approved definitions. Missingness is the prior full-profile blank-cell percentage for the identical file.

| Source | Worksheet/table | Rows | Columns | Empty rows | Blank cells % | Candidate grain |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Customer Master Report 1.xlsx | Sheet1 | 40 | 35 | 0 | 45.1429 | Customer-master record candidate; repeated codes in some extracts |
| Customer Master Report 2.xlsx | Sheet1 | 5015 | 35 | 3 | 44.8477 | Customer-master record candidate; repeated codes in some extracts |
| Exchange Rate 1.xlsx | INR to JPY | 7 | 7 | 0 | 14.2857 | Monthly currency-pair period record candidate |
| Exchange Rate.xlsx | INR to JPY | 22 | 7 | 0 | 6.4935 | Monthly currency-pair period record candidate |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | 6 | 64 | 0 | 7.8125 | Credit/debit reporting detail candidate; observed rows per scoped note assessed separately |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | 279 | 64 | 3 | 11.0887 | Credit/debit reporting detail candidate; observed rows per scoped note assessed separately |
| GSTR1_Invoice.csv | (CSV table) | 337 | 68 | 0 | 21.0421 | Tax reporting line candidate, scoped invoice number repeated across lines |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | 108129 | 13 | 5 | 18.5962 | Mixed item labels, opening-balance lines and movement details |
| Inventory Audit Report as on 200926 1.xlsx | Sheet1 | 162 | 13 | 0 | 37.6068 | Mixed item labels, opening-balance lines and movement details |
| Inventory Audit Report as on 200926.xlsx | Sheet1 | 162 | 13 | 0 | 37.6068 | Mixed item labels, opening-balance lines and movement details |
| Item Master Lists 1.xlsx | Item Lists | 150 | 19 | 0 | 6.7018 | Item-master record candidate with stock and commercial attributes |
| Item Master Lists 2.xlsx | Item Lists | 5015 | 19 | 3 | 4.9714 | Item-master record candidate with stock and commercial attributes |
| Sales Invoice Details 1.xlsx | Sheet1 | 100188 | 43 | 5 | 9.7232 | Invoice goods/service detail candidate with repeated document totals |
| Sales Invoice Details.xlsx | Sheet1 | 337 | 43 | 0 | 9.9234 | Invoice goods/service detail candidate with repeated document totals |
| Sales Order Report 1.xlsx | Sheet1 | 1098 | 26 | 0 | 8.0706 | Order item/service-like detail record; not one row per order |
| Sales Order Report 2.xlsx | Sheet1 | 100286 | 26 | 6 | 7.8474 | Order item/service-like detail record; not one row per order |
| Sales_Order_Data_202609.xlsx | Customer list | 43 | 4 | 0 | 26.7442 | Reference customer row with sparse alternate code and BP_CODE |
| Sales_Order_Data_202609.xlsx | Country master | 11 | 5 | 0 | 0.0 | Country-code row with multilingual names and segment |
| Sales_Order_Data_202609.xlsx | PTC_NOPI | 60 | 8 | 0 | 0.0 | Product-code row in agency/product classification list |
| Sales_Order_Data_202609.xlsx | PCT_NOPJ | 33 | 9 | 0 | 0.0 | Product-code row in agency/product classification list |

Raw field names, physical positions, source SHA-256 versions, current discovery/schema digests, prefix type/missingness/temporal observations and unreviewed hypotheses are in [discovery bundles](nop_readiness_evidence/discovery_bundles.json). Full missingness and empty columns are referenced through [source table profiles](../data_quality/source_tables.csv), [column missingness](../data_quality/missing_values.csv), [date coverage](feasibility_evidence/historical_date_coverage.csv), [135 identifier candidates](../data_quality/identifier_quality.csv) and [duplicate analysis](../data_quality/duplicate_analysis.csv). Physical identifier/date candidates do not establish business keys or clocks.

## Strongest candidate for owner discussion

**Scoped invoice-document volume** remains the best-supported first discussion candidate, conditionally feasible but not ready for training. `Sales Invoice Details.xlsx / Sheet1` contains 337 detail lines and 234 nonblank raw invoice references, with consistent observed party/date/document total within each raw reference. These observations support investigating a document-level event count; they do not approve global identity, source authority or event semantics.

Relevant observed fields include `Invoice Num`, `Invoice Date` and `TransType`; issuer/series/year scope must come from approved source metadata or evidence, not an invented source column. Proposed observation grain is one approved scope/time bucket; proposed target is qualifying distinct scoped invoice documents in that bucket. No target series was calculated.

There are 107 ambiguous invoice-date cells; 230 calendar-resolved full-year cells span 2025-12-21 to 2026-09-13, with 103 resolved dates and ten observed months. This is partial date evidence, not 337 training observations, ten complete periods or annual-seasonality support. The horizon, bucket, lifecycle population, extraction maturity and zero-versus-missing rule remain unconfirmed.

No customer/product, order, inventory or GST join is inherently required for this scope. The small invoice source is an evidence anchor, not a selected authoritative export. Larger extracts and GST representations must not be unioned as additional history.

## Exact preparation blockers

1. **Business approvals absent:** the existing response log has 17 decisions, zero recorded confirmations. D01-D13 are core to the proposed count scope; D12 is Proposed, the other core decisions Unresolved. D14-D17 are conditional. No old decision register was changed.
2. **Governed assessment unavailable:** no authenticated NOP runtime or exact approved NOP binding/evidence/specification revisions were supplied. No operational database was found in the repository outside the virtual environment. External approval stores were not connected or checked; their absence globally is not asserted. Synthetic test accounts/approvals are not NOP authorization.
3. **Target construction unsupported by the current local worker:** an invoice-document/time-bucket target requires approved date interpretation and document-grain/period construction. The registered worker supports native inspection, filtering and narrow type interpretation, and explicitly rejects aggregation, derived targets and grain changes. An approved declaration alone cannot execute them. This capability was not implemented or bypassed.
4. **Data evidence insufficient for training:** complete mature history, point-in-time availability, stable document scope and an approved useful horizon/evaluation design are not established. More authoritative history may be required after the owner specifies the prediction need.

The existing readiness workbook independently agrees with the CSV response log: **zero confirmed decisions and zero recorded approval flags**. The 36-rule register also contains zero approved business definitions and zero authorized corrections. Seven relevant workbooks were inspected read-only; [workbook checks](nop_readiness_evidence/reviewed_workbook_checks.json) preserve the sheet/count and approval-state checks. Approval absence is therefore not inferred only from prose or one export.

The existing assessment engine's pure intake/strategy/target components were exercised. They recognize analytics, forecasting, regression and classification characteristics and reject unsupported output types. With no approved target, target grounding fails. **The governed runtime assessment engine was not executed and no authorized readiness record was issued.** No development grants were manufactured to make the assessment or preparation pass. See [component results](nop_readiness_evidence/assessment_components.json).

## Required owner decisions

These are the existing questions and rule IDs, preserved verbatim in [machine-readable approval requirements](nop_readiness_evidence/approval_blockers.json), together with affected files/fields, evidence and required confirmation.

| Decision | Original rules | Owner role | Required answer |
| --- | --- | --- | --- |
| D01 | BR-005; BR-034 | ERP/source owner; business owner | Which exact invoice extract/version is authoritative for the intended issuer/company/branch and history, and is it complete production data rather than a filtered, sample or synthetic extract? |
| D02 | BR-006 | NOP sales/process owner | Does forecasting issued invoice-document volume support the actual business decision, and which event/transaction types qualify? If the need is units, orders or value, what is that outcome instead? |
| D03 | BR-010; BR-025 | ERP/document owner | Within what issuer/company, series and financial-year scope does Invoice Num identify one invoice? Can it be reused or reformatted, and must case, spaces, punctuation and leading zeros be preserved? |
| D04 | BR-010; BR-023 | ERP/report owner; data owner | Are rows invoice detail lines and should the count be once per approved scoped invoice regardless of line count? What verified policy applies if a later record has missing keys/dates or conflicting document dates? |
| D05 | BR-016; BR-018 | ERP/process owner | What source/version-specific formats and business meaning does Invoice Date have, and is it the correct count-event date? Please verify ambiguous examples using ERP/export evidence, not a guessed global DD/MM or MM/DD default. |
| D06 | BR-007 | Sales/process owner; finance owner for lifecycle scope | Should we count gross issued invoices, valid/nonvoid invoices or another lifecycle outcome? How do cancellations, returns, credit/debit adjustments and reissues affect it, as of when? If lifecycle evidence is absent, is labelled gross issuance acceptable? |
| D07 | BR-019; BR-032 | ERP/data operations owner | Are records actual issued events, plans or tests? What extraction watermark, revision/reporting delay and latest complete cutoff apply, and what shows history was available at each forecast decision time? |
| D08 | BR-018; BR-020 | Reporting/business owner; data operations owner | Which calendar and reporting boundaries apply, which periods are closed and fully captured, and how is a true no-invoice period distinguished from incomplete, unobserved or out-of-scope data? |
| D09 | BR-005; BR-024 | ERP/data owner | Will one approved source/version supply history? If repeat exports, amendments or recurring records appear, which are the same occurrence and what precedence rule applies? Please distinguish valid detail lines from duplicate extracts. |
| D10 | BR-006; BR-032 | NOP process/decision owner | Who uses the forecast, for which decision, at what issuer-level scope, time bucket, future horizon H and update cadence? What lead time is useful, and are customer/product splits actually required? |
| D11 | BR-020; BR-033 | ERP/data owner; business owner | Can NOP provide complete mature authoritative history for the agreed horizon, bucket and validation periods, with closure and scope-change evidence? If an honest holdout is unsupported, what additional history can be supplied? |
| D12 | BR-033 | NOP process owner; ML/data owner | Can we agree chronological evaluation for H with mature training observations, protected holdout periods and suitable simple baselines? Which error costs and acceptance criteria match the decision? |
| D13 | BR-002; BR-012; BR-036 | Project/business owner; ERP/data owner | Who owns each applicable decision/exception, and will they approve the exact source/version, treatment and checks before execution? Please authorize cleaning, dataset construction, feature work and training as distinct bounded activities. |

D14 (entity splits), D15 (value/quantity definitions), D16 (GST reconciliation) and D17 (alternate mixed-date source) apply only when triggered by the agreed scope. Unrelated inventory/GST decisions are not mandatory for issuer-level invoice count.

## Exact framework evidence required before execution

| Gate | Required record/evidence | Current state |
| --- | --- | --- |
| Source and authority | Named accountable source owner; authoritative extraction definition/version, production authenticity, issuer scope, watermark and closure evidence | Not supplied |
| Semantic approval | Exact `SemanticBinding` + current `ApprovalRecord` for required identity, event/date and target roles; exact source fingerprint, discovery/schema, table/physical field positions | Not available for this NOP scope |
| Target readiness | Attributable `PredictionDataEvidence`, agreed `PredictionRequirementSpecification`, current `FeasibilityReadinessAssessment` | No governed assessment executed |
| Observation/target | Owner-approved `PredictionTargetSpecification`, `ObservationSpecification`, applicable `SpecificationApprovalRecord`; explicit grain, population, dates, cutoff/H and completeness | Not available |
| Preparation | Supported registered implementations, exact `DataPreparationPlanSpecification`, `PreparationPlanValidation`, current scoped plan/operation approvals | Not available; count construction unsupported |
| Execution | Authenticated identity/authority, exact `PreparationExecutionRequest` and `PreparationExecutionAuthorization`, source versions, worker identity/lease/fence | No NOP execution requested or authorized |
| Publication | Verified operation receipts, reconciliation and terminal provenance; separate publication authorization and committed `PreparationPublicationRecord` | No execution/artifact/publication exists |

A valid specification or this conditional user request is not business sign-off or execution authorization. Revoked, superseded, expired, stale or wrong-version approvals remain unusable. New source bytes/schema versions need review, never silent approval transfer.

## Unresolved quality and relationship evidence retained

The earlier 424 issues, 203,455 ambiguous date values, 28 impossible dates, 14,949 serial-date candidates, 3 excess exact duplicate rows and 972 payload-duplicate candidates remain unresolved. These counts can overlap and must not be added into a total of affected records. Financial exceptions, synthetic-data indicators, unconfirmed identifiers and the unnamed PCT_NOPJ field remain recorded. None was corrected or discarded.

For the small invoice anchor, prior full checks found no exact or payload-excess duplicate rows. Repeated invoice references are detail structure, not permission to drop lines. Document totals repeated across lines cannot be summed as revenue. The larger invoice source has 33,782 ambiguous invoice-date values and 2,996 serial candidates and is not chosen by size.

Prior invoice/GST document joins can expand 337 to 609 rows; scoped invoice-plus-description evidence aligning 337 rows is not an approved stable line key. Order/invoice joins and overlapping extracts can multiply labels and financial values. No relationship is approved automatically and no new join was run. Consult the [relationship report](dataset_relationship_report.md) and [matrix](identifier_relationship_matrix.xlsx).

## Leakage, chronology and training-ready boundary

Approval must establish actual event versus planning dates, extraction/availability time, lifecycle revision delay and complete observation periods. Current master/status values cannot be assumed known historically. Overlapping representations or related invoice lines cannot become independent target observations. Missing periods cannot be synthesized as zeros without completeness evidence.

For a future count target, specify H and chronological development/holdout requirements using mature periods available at each decision cutoff. Do not fit on later periods or discard inconvenient ambiguous rows to claim clean history. No split, feature engineering, label generation, training or model evaluation was performed. A future published dataset would need validated observations and target values suitable for subsequent ML preparation; publication alone would not prove predictive performance.

## Deliverables and stop outcome

Created this report, the [prediction objective assessment](nop_prediction_objective_assessment.md), [workflow guide](../../docs/development/nop_first_training_dataset_workflow.md) and [supporting JSON evidence](nop_readiness_evidence/readiness_assessment.json). Evidence includes before/after hashes, discovery bundles, exact approval questions, reused candidate assessments, component findings and a hash manifest of prior references.

The [reviewed-input manifest](nop_readiness_evidence/reviewed_evidence_manifest.json) pins 30 prior evidence/document files by SHA-256; it grants no authority over them.

**Not created:** `nop_training_dataset_validation_report.md` or a published dataset. No artifact location/hash, prepared schema/row count, successful reconciliation or publication receipt is claimed because no preparation ran. Prior reports and source files remain preserved.

## Completed validation

- **244 tests passed (237 existing and 7 new)** in **1,325.442 seconds**, with warnings treated as errors. Existing tests cover insufficient history, leakage, integrity, authorization, interruption/restart recovery and production fail-closed behavior; the seven new tests cover the read-only evidence runner. No existing test or framework module was modified.
- All **17 original source hashes** match the recorded integrity report and remained identical at task completion. The archive's 17 member hashes also match those sources. Every one of the 20 table layouts matches prior full-profile evidence.
- All **118 candidate field/position references** match the discovered raw schemas. Candidate source-shape references match; no broken README/report/guide file link was found. Twelve supporting JSON files parse successfully, and both new Python files parse.
- Against the **284-file** starting preservation snapshot, **283 files remain unchanged**, **README alone was modified**, **17 files were added**, and **none were removed**. Existing source files, reports, notebooks, tests, architecture documents, framework code and requirements remain unchanged. No dependency, operational NOP database or preparation artifact store was added.
- Four existing notebooks and two architecture documents were inspected structurally and preserved; seven relevant evidence workbooks were checked read-only. Existing notebook outputs contain no recorded errors, but no notebook was re-executed or certified as current training evidence in this milestone.

Commands executed: the read-only `assess_sources.py --root . --output reports/analysis/nop_readiness_evidence` runner, focused evidence-tool tests, and `.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -t . -v` with `PYTHONPATH=src`. Full machine-readable results and explicit incomplete activities are in [assessment validation](nop_readiness_evidence/assessment_validation.json).

**Stop outcome:** readiness evidence and documentation are complete; governed runtime assessment, preparation and publication remain blocked. Obtain D01-D13 scoped owner answers and attributable approvals, then seek separate approval for any required execution capability. Do not begin real-data preparation, feature engineering or model development.
