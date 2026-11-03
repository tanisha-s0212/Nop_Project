# Business prediction requirements and target feasibility

Assessment date and diagnostic cutoff: **2026-11-02** (Asia/Calcutta date; no source event timezone is assumed). Scope: 17 original files, 20 tables, 521 columns, 37 date-related fields and 135 identifier candidates. This is an assessment, not a prediction platform implementation. No source joins, cleaning, duplicate removal, label/target values, features, training, forecasts or forecasting metrics were produced.

## Executive decision

There is **no unconditionally production-ready prediction target**. Sales activity, an approved invoiced-value proxy, selected product demand proxies, reporting activity and hierarchical extensions are **Feasible with Conditions**. Customer propensity, stock/stockout forecasts, actual delivery outcomes, decision-time numerical regression, cancellation risk, settlement/recognized revenue/margin and production FX forecasts are **Not Currently Feasible** under the supplied evidence. A descriptive evidence audit is already feasible and is not ML prediction.

**First prediction capability to develop, after business/data gates:** a reusable aggregate event-count forecasting capability, initially evaluated against scoped invoice-document activity in an authoritative single invoice source. The small invoice export has 337 detail rows / 234 full invoice references, with constant observed billing party/date/document total within each reference and matching GST representation. This candidate avoids monetary-unit arithmetic and order/invoice joins, but the 10-month partial date span, 107 ambiguous dates, extraction closure, scope and production provenance must be resolved. It cannot establish annual seasonality, performance, an approved horizon or complete observation periods. More mature history is needed if honest horizon/fold evaluation cannot be supported. Invoice activity must not be silently substituted for booked orders, shipped units or recognized revenue.

The longer small-order date span does **not** justify choosing order-count forecasting first: 275 of 299 raw SO-number groups span multiple customer codes, 278 vary Posting Date and its dates use an unapproved two-digit-year convention. These are scope/representation conflicts, not a confirmed count of erroneous business documents. No winner is selected by newest/largest filename.

## Classification meaning and task boundary

- **Feasible:** the exact bounded task has directly verified evidence and no unresolved prerequisite for that stated scope; here this applies to existing structural/descriptive diagnostics, not production prediction.
- **Feasible with Conditions:** observable ingredients support a precise candidate after listed gates; this is not model readiness, sufficient history certification or permission to resolve data issues.
- **Not Currently Feasible:** a defensible outcome, population, temporal availability, required state/history or production evidence is missing/unverified. A more complex algorithm cannot supply missing labels or semantics.

The five requested use cases below are assessment examples. Additional examples and capability families explore the evidence boundary; they are not a fixed supported-question catalogue, question-to-model table or manually programmed application responses. The future system must judge previously unseen requests against evidence and an approved target contract.

## Requested business use cases and broader examples

| assessment_id | use_case | feasibility | proposed_target | evidence_and_history | priority_recommendation |
| --- | --- | --- | --- | --- | --- |
| T01 | Sales forecasting | Feasible with Conditions | Future count of distinct scoped invoice references per approved complete time bucket | Small invoice: 337 lines / 234 document references, internally constant billing party/date/total; partial full-year dates span ten months. No annual-seasonality evidence and no approved extraction boundary. | Priority 1 candidate after gates: least dependence on monetary/unit rules and joins; never substitute invoice activity for another meaning of sales. |
| T02 | Revenue forecasting | Feasible with Conditions | Future additive invoiced taxable value per approved period, currency and entity scope | 337 small invoice lines correspond to GST representation, not additional revenue. Only ten months of partial dated coverage; quantity/base and tax arithmetic exceptions remain. | Conditional follow-on after count capability and finance-owned measure contract. |
| T03 | Customer purchase propensity | Not Currently Feasible | P(purchase in (t,t+H] \| information available at t) for an eligible customer | Customer/order references and purchases-like events exist, but all 40 small-order customer codes occur in the 40-row master. No verified historical nonpurchaser/cohort/exposure panel or eligibility start/end/observation boundary. Invoice customer mapping is unapproved. | Defer model development; obtain cohort and observation history before creating either class. |
| T04 | Product/service demand forecasting | Feasible with Conditions | Future product-period reported quantity, or service-period activity/value under a separately approved unit | Small invoice has 323 G and 14 S lines; large has 99,242 G and 941 S. Small order has 36 blank product rows; repeated SO scope and service-like zero quantities prevent a universal quantity target. UOM Manual is not a confirmed physical unit. | Conditional for sufficiently supported goods series; service duration/capacity and unconstrained demand are not currently supported. |
| T05 | Inventory forecasting | Not Currently Feasible | Future stock balance or probability of stockout over an approved horizon | Large audit has 98,104 movement rows without raw item code; three grouped audits are not a confirmed regular snapshot panel. Item master stock/update date is not repeated historical stock observation. | Defer stock and stockout models; approve movement reconstruction and obtain authoritative snapshots/movement lifecycle first. |
| T06 | Unknown numerical outcomes | Not Currently Feasible | Owner-selected realized numerical outcome at an explicit event/decision horizon | Numerical fields exist, but no approved quote/decision snapshot, actual realization linkage or availability timestamps establish a leakage-free supervised dataset. | Obtain the decision process and realized outcome history before selecting predictors or algorithms. |
| T07 | Cancellation or adjustment risk | Not Currently Feasible | Future event indicator within a defensible observation window | Small order has current 44 Canceled lines, 50 Open and 1,004 Closed; these are line states, not 44 uniquely scoped historical cancellation outcomes. No transition history or verified negatives. | Defer; existing states support descriptive audit only under known scope. |
| T08 | Delivery time or delay prediction | Not Currently Feasible | Actual completion duration, or actual-versus-promised lateness | Posting Date and Delivery Date exist; large delivery field contains 15 impossible dates and values extending to 2028-04-30 under partial interpretations. | Request actual fulfilment/service milestones; do not relabel planned dates as outcomes. |
| T09 | Collections, cash flow, recognized revenue or margin | Not Currently Feasible | Future settled cash, ledger-recognized amount or realized margin under an approved finance definition | Schema lacks identified actual-payment/settlement and recognition lifecycle fields. Inventory Cost/Trans. Value are not validated invoice-line COGS. | Additional financial lifecycle sources required, not a different algorithm. |
| T10 | Tax/adjustment activity forecasting | Feasible with Conditions | Future scoped note/event count or approved additive reported tax component per period | 6-row notes have 6 scoped references; 276 nonempty larger-note rows have 243 scoped references, 33 repeats and 3 exact excess duplicates. Much larger-note coverage extends beyond assessment date. | Lower priority; likely needs more mature production reporting history before forecasting. |
| T11 | Hierarchical or segmented forecasting | Feasible with Conditions | Same approved additive/count outcome per validated hierarchy level | Customer/item and PTC/PCT classification candidates exist; 27 row-preserving raw-key directions remain conditional. Larger master duplicates and partial matching can expand or lose records. | After aggregate target approval and entity-specific support assessment; not every segment can be forecast. |
| T12 | Historical retrieval, aggregations and diagnostics | Feasible with Conditions | No prediction target; approved recorded counts/sums/rates or audit findings | 20 validated tables / 521 columns and existing quality/relationship calculations support descriptive evidence. Business measures remain conditional on authority, grain and date rules. | Use now for evidence review; do not present a historical calculation as a forecast. |
| T13 | Currency rate forecasting | Not Currently Feasible | Future observed market/contract FX rate under an approved basis | Only 7 and 22 explicitly synthetic monthly rate records, overlapping two pairs/periods; some future periods and serial-date candidates. | Obtain authorized real rate history if this capability is required. |

Complete business objectives, proposed equations, source columns, date/key needs, scope, observation frequency, horizon requirements, limitations and method suitability are in [prediction_target_mapping.xlsx](prediction_target_mapping.xlsx), its `assessment_examples`, `target_source_bindings` and `historical_date_coverage` sheets. Formulas are proposed definitions, not generated target columns. All 13 examples have verified actual-column citations. Horizons have not been supplied by NOP; H, lead time, bucket and update cadence remain requirements rather than defaults.

### What can be generalized

| capability_family | data_contract_requirement | method_family_not_fixed_algorithm | feasibility | limitation |
| --- | --- | --- | --- | --- |
| Historical retrieval / aggregation | Observed facts within approved scope | SQL/dataframe grouping or documented arithmetic | Feasible with Conditions | No model needed; dates/units/authority/grain still govern business aggregates |
| Descriptive quality diagnostics | Existing source/metadata counts | Reproducible read-only profiling | Feasible | Already verified source extents, missingness, raw duplicates and relationship fanout; this is analytics, not prediction |
| Future aggregate count process | Mature scoped events over complete buckets | Time-series candidates and non-ML count baselines | Feasible with Conditions | Invoice activity is the least measure-dependent first candidate; no annual evidence from ten months |
| Future additive numerical process | Approved additive amount/quantity and coherent time series | Time-series family chosen after diagnostics/validation | Feasible with Conditions | Entity/unit/currency and fiscal/sign semantics; no universal algorithm |
| Unknown numerical outcome at decision time | Comparable historical input/outcome pairs and as-of availability | Supervised regression when labels are defensible | Not Currently Feasible | Observed amount columns do not establish retrospective decision examples |
| Future categorical/propensity outcome | Eligible population, matured positive/negative windows | Classification or event-time family | Not Currently Feasible | No defensible negative purchase cohort or historical availability panel |
| Duration / time-to-event | Actual timed events, origins and censoring | Event-time or numerical duration family | Not Currently Feasible | Actual completion/payment lifecycle unverified |
| Hierarchical / multi-series forecasts | Approved shared target plus per-entity history and hierarchy | Per-series/pooled/hierarchical options, assessed empirically | Feasible with Conditions | Current crosswalks and memberships unapproved; global row counts do not establish series support |
| Operational stock trajectories | Validated opening state and typed flows/as-of snapshots | Balance rules for known movements; predictive inputs only where uncertain | Not Currently Feasible | Grouped movement context, replenishment and stockout outcomes missing/unconfirmed |
| Anomaly diagnostics | Approved rules or stable reference distribution | Rule-based or exploratory unsupervised diagnostics | Feasible with Conditions | A flag is not a fraud label, causal finding, probability or forecast confidence |

Schema/quality/lineage discovery, grain/identity evidence, point-in-time contracts, readiness checks, validation protocols and component interfaces can generalize. Business meanings, eligibility, time roles, units, signs, source authority, event identities and outcome windows require target-specific approved semantic configurations. Those configurations describe data and business meaning, not anticipated questions or a model chosen by keyword.

## Actual source evidence and historical suitability

All 20 tables retain the meanings and uncertainties in [granularity evidence](dataset_granularity_report.xlsx). Customer/item masters are current reference candidates, not historical eligibility or attribute panels. Sales orders and invoices contain detail rows, tax exports are reporting representations, inventory is a grouped mixed-grain report, and rate examples are explicitly synthetic. Country/product classifications are references, not predictive outcome histories. Source rows are not independent time observations, invoice totals are repeated at line grain and similar schemas do not establish identical grain.

### Dates and observation counts

The following coverage is **timestamp evidence only**, not a cleaned time series or a count of supervised examples. Calendar-resolved ranges from prior validation can depend on a two-digit-year convention. A separate conservative view includes only native/full-year, one-interpretation dates at or before 2026-11-02, excluding century-dependent tokens from that view without changing or discarding any source records. ISO strings already present in date evidence are read; raw source dates are not reinterpreted. Neither view proves actual-versus-planned meaning, completeness, decision-time availability or production legitimacy.

| file | worksheet | column | calendar_resolved_min_under_prior_convention | calendar_resolved_max_under_prior_convention | century_dependent_cells_including_ambiguous | strict_partial_history_min | strict_partial_history_max | distinct_observed_months_asof | calendar_resolved_beyond_asof | explicit_full_year_or_native_beyond_asof |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Exchange Rate 1.xlsx | INR to JPY | Rate Month   |  |  | 2 |  |  | 0 | 0 | 0 |
| Exchange Rate 1.xlsx | INR to JPY | Start Date | 2026-08-21 | 2027-01-21 | 0 | 2026-08-21 | 2026-09-21 | 2 | 3 | 3 |
| Exchange Rate 1.xlsx | INR to JPY | End Date | 2026-09-20 | 2027-03-20 | 0 | 2026-09-20 | 2026-10-20 | 2 | 4 | 4 |
| Exchange Rate.xlsx | INR to JPY | Rate Month |  |  | 22 |  |  | 0 | 0 | 0 |
| Exchange Rate.xlsx | INR to JPY | Start Date | 2024-12-21 | 2026-09-21 | 0 | 2024-12-21 | 2026-09-21 | 22 | 0 | 0 |
| Exchange Rate.xlsx | INR to JPY | End Date | 2025-01-20 | 2026-10-20 | 0 | 2025-01-20 | 2026-10-20 | 22 | 0 | 0 |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | CreditDebitNote_Date | 2026-01-29 | 2026-06-24 | 0 | 2026-01-29 | 2026-06-24 | 3 | 0 | 0 |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | Invoice_Date | 2026-01-18 | 2026-03-30 | 0 | 2026-01-18 | 2026-03-30 | 2 | 0 | 0 |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | Original_CreditDebitNote_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | Revision_Month |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | Shipping_Bill_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | CreditDebitNote_Date | 2026-04-25 | 2027-03-20 | 16 | 2026-09-21 | 2026-10-31 | 2 | 140 | 129 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | Invoice_Date | 2026-03-30 | 2027-03-17 | 0 | 2026-03-30 | 2026-10-31 | 8 | 106 | 106 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | Original_CreditDebitNote_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | Revision_Month |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | Shipping_Bill_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Invoice.csv | (CSV table) | Invoice_Date | 2025-12-21 | 2026-09-13 | 0 | 2025-12-21 | 2026-09-13 | 10 | 0 | 0 |
| GSTR1_Invoice.csv | (CSV table) | Original_Invoice_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Invoice.csv | (CSV table) | AdvanceReceipt_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Invoice.csv | (CSV table) | Shipping_Bill_Date |  |  | 0 |  |  | 0 | 0 | 0 |
| GSTR1_Invoice.csv | (CSV table) | Revision_Month |  |  | 0 |  |  | 0 | 0 | 0 |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | System Date | 2026-09-21 | 2027-03-20 | 88116 | 2026-09-21 | 2026-11-02 | 3 | 46016 | 4895 |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | Posting Date | 2026-09-21 | 2027-03-20 | 88219 | 2026-09-21 | 2026-11-02 | 3 | 45999 | 4796 |
| Inventory Audit Report as on 200926 1.xlsx | Sheet1 | System Date | 2026-08-22 | 2026-09-19 | 39 | 2026-08-22 | 2026-09-13 | 2 | 0 | 0 |
| Inventory Audit Report as on 200926 1.xlsx | Sheet1 | Posting Date | 2026-08-22 | 2026-09-15 | 41 | 2026-08-22 | 2026-09-13 | 2 | 0 | 0 |
| Inventory Audit Report as on 200926.xlsx | Sheet1 | System Date | 2026-08-22 | 2026-09-19 | 58 |  |  | 0 | 0 | 0 |
| Inventory Audit Report as on 200926.xlsx | Sheet1 | Posting Date | 2026-08-22 | 2026-09-19 | 58 |  |  | 0 | 0 | 0 |
| Item Master Lists 1.xlsx | Item Lists | Date of Udate | 2024-10-20 | 2026-09-17 | 150 |  |  | 0 | 0 | 0 |
| Item Master Lists 2.xlsx | Item Lists | Date of Udate | 2024-10-20 | 2026-09-17 | 3978 | 2024-11-25 | 2026-09-17 | 23 | 0 | 0 |
| Sales Invoice Details 1.xlsx | Sheet1 | SO Date | 2025-12-16 | 2027-03-19 | 2507 | 2025-12-16 | 2026-11-02 | 5 | 45931 | 44774 |
| Sales Invoice Details 1.xlsx | Sheet1 |  Invoice Date  | 2026-01-01 | 2027-03-20 | 2979 | 2026-01-01 | 2026-11-02 | 4 | 50771 | 49267 |
| Sales Invoice Details.xlsx | Sheet1 | SO Date | 2025-11-26 | 2026-08-25 | 0 | 2025-11-26 | 2026-08-25 | 10 | 0 | 0 |
| Sales Invoice Details.xlsx | Sheet1 | Invoice Date | 2025-12-21 | 2026-09-13 | 0 | 2025-12-21 | 2026-09-13 | 10 | 0 | 0 |
| Sales Order Report 1.xlsx | Sheet1 | Posting Date | 2024-04-13 | 2026-09-19 | 1098 |  |  | 0 | 0 | 0 |
| Sales Order Report 1.xlsx | Sheet1 | Delivery Date | 2024-04-16 | 2026-10-19 | 1098 |  |  | 0 | 0 | 0 |
| Sales Order Report 2.xlsx | Sheet1 | Posting Date   | 2026-08-13 | 2027-03-20 | 85323 | 2026-08-15 | 2026-11-02 | 4 | 47413 | 7381 |
| Sales Order Report 2.xlsx | Sheet1 | Delivery Date | 2026-08-22 | 2028-04-30 | 88063 | 2026-08-22 | 2026-11-02 | 4 | 54764 | 6693 |

- Small invoice and GST invoice `Invoice Date` / `Invoice_Date`: 337 cells each; 107 ambiguous, 230 full-year calendar-resolved, with partial 2025-12-21 to 2026-09-13 coverage over 10 observed months. These are corresponding source representations, not 674 new line observations or 20 months of history.
- Small order `Posting Date`: 1,098 cells; 417 ambiguous. Prior calendar resolution gives a partial 2024-04-13 to 2026-09-19 range, but every date depends on the century convention. Zero rows in the conservative full-year view does not mean no source dates exist. Raw SO grouping is also unstable.
- Large invoice ` Invoice Date `: 100,183 nonblank cells, 33,782 ambiguous and 2,996 possible serial candidates; its partial calendar range reaches 2027-03-20. Large order posting/delivery fields also extend beyond the assessment cutoff; a future delivery date may be a plan, not an observed outcome.
- Period labels such as rate `2027-03` remain monthly periods. Item `Date of Udate` is an update attribute, not a purchase/stock observation date. Revision month without a year cannot establish event history.
- Daily, ISO-weekly and monthly distinct timestamp support is recorded per field in the workbook, with both partial spans and unobserved months. This does not authorize daily/weekly/monthly target aggregation. Approved calendars and capture completeness are required before interpreting an empty bucket as zero. No zero filling or aggregation of business targets occurred.
- Sufficiency depends on complete mature observations at the requested entity/frequency relative to H, validation folds, seasonality and decision utility. There is no universal minimum-row threshold. Ten partial months do not establish annual seasonality; hundreds of thousands of lines over a short or future-dated interval do not establish long production history.

## Identifiers, grain and join dependencies

Existing evidence: [relationship report](dataset_relationship_report.md), [identifier and relationship matrix](identifier_relationship_matrix.xlsx), [logical business model](data_model_diagram/README.md). All 148 candidate comparisons and 69 controlled joins retain their original conditional status; no business keys/relationships are approved by this assessment.

- Invoice/order SO-only join: **100,188 -> 402,400 rows**, quantity **363,277 -> 1,472,651**. This is row replication, not growth or extra demand. Do not enrich targets through that direct detail join.
- Small GST/invoice scoped document join: **337 -> 609 rows**. Scoped invoice + raw item description aligns **337 -> 337**, with matching six numerical line fields in these specific extracts. Description is not an upstream stable line key. Use GST as reconciliation evidence, not extra sales rows; no permanent merge is performed.
- Large-order to large-customer-master raw lookup: **100,286 -> 100,898 rows**; even a master lookup can distort targets. The 27 current raw row-preserving directions still need scope, authority, completeness and temporal approvals.
- Independently rereading the small order and small invoice sources reproduces the reported within-key attribute variations. Small invoice 234 references have no observed party/date/document-total variation. Small order raw SO number cannot be treated as a globally scoped order key; adding customer/product without approval is not sufficient identity evidence.
- Inventory has **98,104 movement rows without populated raw item code** in the large audit; no forward fill is authorized. Stock movements, opening balances and cumulative fields must not be mixed into an additive demand/stock target.

For the first count candidate, no cross-source business join is necessary. Value, goods demand, customer features, adjustments and hierarchical extensions require progressively more semantic/identity/measure evidence. Targets that can be supported in a single approved source should not acquire avoidable join dependencies.

## Customer propensity: explicit outcome audit

| element | status | evidence | required_action |
| --- | --- | --- | --- |
| Positive purchase evidence | Candidate events only | Order and invoice references exist; order placement versus qualifying purchase must be approved. | Confirm purchase event and customer mapping, not just repeated customer IDs. |
| Historical negative outcomes | Not established | No verified eligible-and-fully-observed no-purchase panel; blank/zero quantities and absent transactions are not negatives. | Obtain eligibility, complete event capture and mature outcome windows before label construction. |
| Defensible prediction window | Not supplied | No approved t/H, extraction closure or label-reporting delay. | NOP must define decision cadence, future window, horizon and maturity rule. |
| Customer risk set | Not historical | Small master has 40 codes, and all 40 appear among 1098 small-order rows; current master status supplies no past eligibility. | Obtain historical entry/exit/activity and complete follow-up; do not label other-master unmatched accounts as nonpurchasers. |
| Entity identity | Unapproved | 135 ID candidates remain unconfirmed; invoice party mapping and SO scope unstable. | Approve scoped customer and event identity before partitioning windows. |
| Features at decision | Availability history absent | No approved availability timestamps or prior-state snapshots. | Specify point-in-time admissible inputs; no feature engineering in this assessment. |

The proposed label contract is only a specification: at a decision time t, an eligible customer has a positive label only after an approved purchase in (t,t+H]; a negative label requires verified full-window capture and continued eligibility with no qualifying purchase. Customers with immature follow-up, censored eligibility, missing capture or unresolved identity remain unknown. No label values or fabricated nonpurchasing records were created. Zero/negative quantities, current inactive flags, cancellation lines and unmatched master accounts are not purchase-negative examples.

## Analytics, prediction and leakage

Historical SELECT/COUNT/SUM and observed price/tax arithmetic are analytics or rules. They can be sufficient for a historical question but cannot answer a request for an unknown future value. Forecasting uses an approved ordered process; regression predicts an unknown numerical outcome with comparable historical examples; classification needs defensible outcomes/cohorts. Anomaly flags are diagnostics without validated labels and cannot be called fraud probabilities. Inventory balance rules can plan known flows, but forecast uncertainty requires supported uncertain inputs.

| risk | potential_leakage | required_chronological_control |
| --- | --- | --- |
| Current state as historical feature | Post-outcome or future updates can encode label information. | Require historical state effective/available at t; current status cannot be retrospectively treated as known. |
| Future or planned events | Future/planned entries can be mistaken for realized history. | Use source-supported actual/known-at-time roles; separate business event, planning and availability clocks; do not delete source rows. |
| Outcome arithmetic in predictors | Target components can trivially reconstruct an amount instead of predicting an unknown outcome. | Confirm which values are available at the decision; deterministic arithmetic belongs in analytics. |
| Cross-export and duplicate leakage | Same event can enter training and test or be counted twice. | Approved lineage/event identity across splits; group related records while preserving temporal order; no blind random line split. |
| Label-window overlap | Training labels may use events after validation decision time. | At fold cutoff c, require training outcome windows and reporting lag matured by c; purge/embargo as necessary. |
| Retrospective customer eligibility | Missing events are wrongly assigned negative labels. | Eligibility and complete capture for entire window required; unknown/censored windows stay unknown. |
| Future dimension joins | Latest attributes can reveal future entity state. | Approved many-to-one effective/available-time join; do not fill historical dimensions from latest state automatically. |
| Global preprocessing / selection | Future distributions or holdout outcomes contaminate fitting. | Fit on each training fold only; compare candidates within development folds; keep final chronological holdout untouched. |
| Artificial continuity / zeros | Zero-filled missing capture creates fabricated negative outcomes and demand troughs. | Approve business calendar and coverage first; missing is not zero. |
| Current financial totals | Post-decision settlements/adjustments or repeated totals distort outcomes. | Approved line/document measure, revision cutoff, sign and target maturity before aggregation. |
| Short history / unsupported seasonality | Many lines create misleading confidence about temporal observations. | Compare fold/H/season support at target grain; request more mature history where validation cannot be honest. |

For a future chronological evaluation, first approve the target contract and snapshot/availability history. At each cutoff c, only inputs available by c and training labels fully matured by c may be used. Evaluate future blocks of the requested H, allow reporting delay, purge overlapping label windows and preserve a final untouched chronological holdout. Fit all transforms and candidate selection within training/development folds. Cross-export duplicates and related lines must not leak between splits; related-event grouping must preserve temporal order. Compare appropriate naive/rule/seasonal baselines only if supported. Metrics, calibration and intervals must be measured on a real approved evaluation, never invented. No folds, features, training or accuracy values were generated now.

## Unresolved findings and new clarification needs

All **424 prior issue entries** are copied into the requirements evidence with their original identifiers, sources, columns, severity, counts and unresolved status, plus their feasibility impact. The 203,455 ambiguous dates, 28 impossible dates, 14,949 serial candidates, 3 excess exact duplicates and 972 payload-duplicate candidates remain intact. Financial exceptions, synthetic indicators, unnamed PCT_NOPJ field and 135 unconfirmed ID candidates are not resolved. Counts overlap and are not a unique count of defective records. Century dependence, future-versus-realized dates, extraction completeness and raw SO scope make these issues directly relevant to target feasibility.

The NOP team needs to confirm metric meanings; company/issuer/time scope; production provenance and authoritative versions; dates/century/epoch; current versus historical status; stable document/line/customer/product IDs; complete periods/zeros; units/currency/financial rules; observation windows/H; service units; inventory movement layout and snapshot meaning. No business horizon, valid target, key approval or relationship approval is inferred from this report.

Missing lifecycle evidence is documented in [prediction_data_requirements.xlsx](prediction_data_requirements.xlsx). Propensity requires eligibility and complete outcomes; actual delivery needs fulfilment events; stock/latent demand needs availability/receipts/stockout history; cash/recognized revenue/profit need settlement/ledger/cost allocation history. More mature real transaction history may also be required for the first invoice-count candidate. Whether these fields exist in NOP systems outside the supplied 521 columns must be established with owners; absence here is not a claim that they do not exist in the business.

## Technology-independent future architecture

```mermaid
flowchart TD
    R[Unseen authorized natural-language request] --> I[Outcome / entity / metric / time / H / grain intent draft]
    I --> E[Current authorized schema, profile and provenance evidence]
    E --> C[Grounded versioned business target and observation contract]
    C --> G[Semantic, quality, history, label, leakage and join readiness gates]
    G -->|unsupported or material ambiguity| Q[Explain missing evidence / request only necessary clarification]
    G -->|historical task supported| A[Read-only retrieval / aggregation / approved rules]
    G -->|predictive task admissible| S[Evidence-dependent strategy families and validation plan]
    S --> P[Future approved reusable preparation and candidate evaluation components]
    P --> V[Measured comparison, baseline checks and protected chronological holdout]
    V --> O[Future versioned inference with lineage, limits and empirical uncertainty]
    O --> M[Freshness, drift, scope and outcome monitoring]
    M --> E
```

| component | required_capability | contract_or_output | guardrail |
| --- | --- | --- | --- |
| Request interpretation | Extract outcome intent, entities, metric/unit, time basis, horizon, grain, scope, filters and requested action from unseen language. | Versioned intent draft; preserve original request, ambiguity and unfilled fields | No anticipated-question list; resolve only material missing details. |
| Authorized evidence discovery | Discover current schemas, types, grains, time/identifier/measure profiles, lineage, rights and approved relationships. | Versioned evidence catalogue with actual source/column bindings and validity times | Column-name resemblance is insufficient; new data triggers re-profiling and review. |
| Semantic grounding / clarification | Bind requested meaning to supported fields and business definitions with traceable alternatives. | Proposed semantic bindings, evidence and minimal clarification request | No invented columns/outcomes or silent metric substitution. |
| Target and observation contract | Specify outcome equation, entity/record grain, eligible population, event/availability clocks, H, label window/maturity, units/sign/currency, authority and permitted joins. | Human-reviewable versioned target contract independent of wording | Business-rule configurations are reusable semantic metadata, not question-to-model mappings. |
| Evidence readiness / abstention gate | Check source authenticity, complete periods, temporal integrity, support, labels/cohorts, identifiers, leakage and join conservation. | Admissible / conditional / unsupported decision with blockers and required evidence | Unsupported or ambiguous requests yield limitations or necessary questions, never fabricated values/confidence. |
| Task and strategy planning | Separate retrieval/SQL/rules, numerical forecasting, unknown-outcome regression, classification and other supported tasks. | Admissible strategy families and resource/business constraints | No single algorithm and no fixed question/model table; candidate suitability must follow the approved contract. |
| Reusable preparation interface — future only | Honor the target contract with versioned, reusable preparation and point-in-time transformation components. | Lineage-preserving execution plan and fitted-transform boundaries | Not implemented or executed in this assessment; raw evidence stays immutable. |
| Evaluation and candidate comparison — future only | Select time-respecting folds, baselines, appropriate error metrics/decision utility, calibration and interval diagnostics when relevant. | Auditable evaluation protocol and measured evidence before selection | No made-up performance; fit transforms only within training folds; protect final holdout. |
| Inference and explanation — future only | Apply approved fitted artifacts to an authorized request and supported horizon/entity scope. | Prediction versus observed fact, units, as-of time, empirical uncertainty, lineage and limitations | Block extrapolation beyond evaluated scope and unknown entities without an approved policy. |
| Monitoring, versioning and extension | Track freshness, schema/identity/semantic drift, target/availability changes, evaluation decay and access policy. | Registries of evidence/semantic contracts/components and monitored versions | New domains extend metadata/adapters/contracts; no rewrite of core or exhaustive question catalogue required. |

The contract must include the fields in `target_contract_requirements`; all predictive bindings remain unapproved. A future new dataset must be profiled and grounded without changing a question list; a new request uses the same contract/gates, with admissible method families determined by outcome/observation structure and evaluated evidence. Additional algorithms/adapters can extend components without rewriting the system. Semantic metadata and owner-approved target-specific settings are necessary; fixed column names, anticipated scenarios, manually scripted answers and single-model routing are not an acceptable platform design. An automated schema profile does not automatically approve a business relationship.

No interpreter, selector, training pipeline, prediction API or implementation of this architecture is created. The analysis code only reads evidence, performs source grain checks and renders assessment documents. The illustrative assessment rows are not executable prediction instructions.

## Recommended next activity

Conduct an evidence-led NOP requirements and source-owner review. Agree on one target/observation contract and the minimal blockers before requesting approval for preparation. Prefer aggregate invoice-event count as the first *conditional technical candidate*, because it avoids monetary-unit rules and optional joins; confirm whether it meets the actual business objective before selecting it. If the desired outcome is instead units, recognized revenue or propensity, retain that meaning and request its missing evidence rather than substitute a supported proxy silently. Establish production authenticity, source/date/key scope, complete mature history, H and acceptance criteria; acquire additional lifecycle/history sources where identified. Stop for approval before cleaning, consolidation, features or models.

## Deliverables and validation

- [Executed feasibility notebook](../../notebooks/04_business_prediction_feasibility.ipynb)
- [Prediction target mapping](prediction_target_mapping.xlsx)
- [Prediction data requirements](prediction_data_requirements.xlsx)
- [Assessment validation](feasibility_validation.json) and [notebook execution validation](feasibility_notebook_validation.json)
- Complete supporting tables are in `feasibility_evidence/`; [input preservation ledger](feasibility_evidence/preserved_input_integrity.csv) hashes original sources and all previous reports/notebooks/implementations.

Validation checks input CSV/workbook agreements, actual source/column references, all 37 date-field token totals and as-of partitions, all 13 illustrative assessments, complete 424-issue carry-forward, independently reread source grain, every cell of new CSV/Excel outputs and documentation links. Existing reports remain unchanged. Final execution results are recorded by the notebook validator after execution. Limitations are semantic/observation evidence and production readiness, not undisclosed generated forecasting metrics.
