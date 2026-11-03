# NOP prediction objective assessment

> A later exploratory run used a generic monthly distinct-count operator to evaluate a confirmed-date invoice subset. This assessment remains valid for business approval and production readiness; see `reports/nop_actual_data_ml_exploratory_completion_report.md` for results and a raw date-cell count discrepancy.

Assessment: 3 November 2026. **No candidate is approved or training-ready.** Existing evidence was revalidated against current source hashes and physical layouts. This document reuses the earlier feasibility conclusions; it does not invent requirements, target values, labels or model metrics. The earlier diagnostic time cutoff remains 2 November 2026.

## Decision

Discuss scoped invoice-document volume first. The small invoice extract provides 337 detail lines / 234 consistent raw references; it avoids financial/unit calculations and business joins. However, unresolved dates, incomplete ten-month coverage, unapproved source/key/event scope, missing lifecycle/zero/completeness rules and an unspecified horizon block a business-approved target. A later generic operator can construct the monthly distinct-count shape, but this does not supply the missing definitions or execution approval. This remains a priority for clarification, not an authorized business target.

## Technical problem families

| Family | Evidence-backed assessment |
| --- | --- |
| Historical analytics | Structural profiling and existing diagnostics are supported; business counts/sums still need approved grain/date/measure definitions. A historical calculation is not ML. |
| Time-series forecasting | Conditional event-count/value/quantity ingredients exist; no complete approved time series, horizon or evaluation history is established. |
| Regression | Numeric fields exist, but a decision-time unknown outcome and historically available inputs are not established. Monetary identities computed from the same outcome are not evidence of predictive usefulness. |
| Classification/propensity | No verified eligible historical cohort with positive/negative purchase outcomes or defensible prediction window; present-day master/status labels are not historical outcomes. |
| Other families | Require an appropriate registered assessment strategy and actual outcomes/time-at-risk/availability evidence. No unsupported problem family is treated as ready. |

Existing pure engine components recognize these task characteristics. Full authenticated engine assessment is blocked; technical family recognition cannot validate a target. No model family or algorithm was selected.

## Evidence-backed candidates

The following are previously investigated evidence examples, not predefined supported questions or framework routes. Required source/identifier/date names below are facts in project evidence, not names embedded in reusable framework code. All joins remain unapproved; invoice-count scope needs no join. Conditional enrichment requires explicit relationship approval and point-in-time cardinality validation.

### T01 - Sales forecasting

**Observed fields (proposed roles only):** Sales Invoice Details.xlsx / Sheet1: `Invoice Date` (position 8, event / document / scope), `Invoice Num` (position 7, event / document / scope), `TransType` (position 2, event / document / scope); Sales Order Report 1.xlsx / Sheet1: `Posting Date` (position 9, Alternative order activity, not interchangeable with invoices), `SO No` (position 7, Alternative order activity, not interchangeable with invoices), `Customer Code` (position 2, Alternative order activity, not interchangeable with invoices), `Status` (position 8, Alternative order activity, not interchangeable with invoices).

**Classification:** Feasible with Conditions; no training readiness or execution authorization.

- **Proposed target:** Future count of distinct scoped invoice references per approved complete time bucket
- **Definition (proposal only):** Proposed only: COUNT DISTINCT(Invoice Num at owner-confirmed issuer/series/year scope) by approved Invoice Date bucket; count documents, not lines. No count series generated. Issuer/scope is a required semantic rule, not an invented source column.
- **Source/history evidence:** Small invoice: 337 lines / 234 document references, internally constant billing party/date/total; partial full-year dates span ten months. No annual-seasonality evidence and no approved extraction boundary.
- **Observation grain:** Aggregate issuer-level first; customer/product breakdown requires separate stable entities and adequate observations.
- **Identifier dependencies:** Owner-confirmed issuer/series/year scope for Invoice Num; persistent line IDs needed for line-based alternatives, not fabricated document identities.
- **Date/availability dependencies:** Invoice Date as actual approved issuance event; Posting Date is an alternative order event and is not interchangeable.
- **Missing evidence and conditions:** Source authenticity, invoice scope/date rules, complete periods and cancellation/void policy; additional mature history if folds/horizon cannot be supported.
- **Approach boundary:** Time-series count forecasting after source/time gates; compare simple count/seasonal baselines only when supported. Historical COUNT is analytics.
- **Observed source shapes:** Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns); Sales Order Report 1.xlsx / Sheet1 (1098 rows, 26 columns).
- **Partial date coverage:** Sales Invoice Details.xlsx / Sheet1 / `Invoice Date`: 2025-12-21 to 2026-09-13; 10 observed months; Sales Order Report 1.xlsx / Sheet1 / `Posting Date`: unestablished to unestablished; 0 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** No join inherently required for the discussion-first single-source count. Source/key/date/target/grain approvals absent; alternatives must be independently scoped.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T02 - Revenue forecasting

**Observed fields (proposed roles only):** Sales Invoice Details.xlsx / Sheet1: `Taxable Value` (position 22, Proposed proxy measure; document total is not line-additive), `Invoice Date` (position 8, Proposed proxy measure; document total is not line-additive), `Invoice Num` (position 7, Proposed proxy measure; document total is not line-additive), `Total Value` (position 32, Proposed proxy measure; document total is not line-additive), `Invoice Total Include GST` (position 37, Proposed proxy measure; document total is not line-additive), `Invoice Discount %` (position 38, Proposed proxy measure; document total is not line-additive), `FreightAmt` (position 23, Proposed proxy measure; document total is not line-additive); GSTR1_Invoice.csv / (CSV table): `Invoice_Date` (position 1, Reconciliation representation; never stack with invoice source), `Invoice_Number` (position 2, Reconciliation representation; never stack with invoice source), `Doc_Series` (position 57, Reconciliation representation; never stack with invoice source), `Doc_Series_Prefix` (position 58, Reconciliation representation; never stack with invoice source), `Doc_Series_Suffix` (position 59, Reconciliation representation; never stack with invoice source), `Item_Taxable_Value` (position 16, Reconciliation representation; never stack with invoice source), `Invoice_Value` (position 51, Reconciliation representation; never stack with invoice source); GSTR1_Credit_Debit_Note 2.csv / (CSV table): `CreditDebitNote_Date` (position 1, Adjustment scope/sign unresolved), `CreditDebitNote_Number` (position 2, Adjustment scope/sign unresolved), `Type_Credit_or_Debit` (position 3, Adjustment scope/sign unresolved), `Invoice_Number` (position 5, Adjustment scope/sign unresolved), ` Item_Taxable_Value` (position 18, Adjustment scope/sign unresolved), `Credit_Debit_Note_Value` (position 46, Adjustment scope/sign unresolved).

**Classification:** Feasible with Conditions; no training readiness or execution authorization.

- **Proposed target:** Future additive invoiced taxable value per approved period, currency and entity scope
- **Definition (proposal only):** Proposed only: SUM(reported Taxable Value) on approved invoice lines in a period; discount/freight/tax/sign and currency policies unresolved. Net adjustments require separate approved allocation and note sign rules. Invoice Total Include GST repeats per line.
- **Source/history evidence:** 337 small invoice lines correspond to GST representation, not additional revenue. Only ten months of partial dated coverage; quantity/base and tax arithmetic exceptions remain.
- **Observation grain:** Issuer/currency/period; no product/customer split until keys, units and series support pass.
- **Identifier dependencies:** Scoped Invoice Num plus stable line identity and scoped adjustment references; currency/entity scope must be confirmed.
- **Date/availability dependencies:** Approved invoice/adjustment accounting event dates; ledger recognition timestamps are not established.
- **Missing evidence and conditions:** Actual revenue recognition, collections and profit cannot be inferred from invoice values. Obtain ledger recognition/settlement history for those outcomes.
- **Approach boundary:** Time-series value forecasting conditional on a reconciled additive measure; historical SUM/SQL is analytics, not a prediction.
- **Observed source shapes:** Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns); GSTR1_Invoice.csv / (CSV table) (337 rows, 68 columns); GSTR1_Credit_Debit_Note 2.csv / (CSV table) (279 rows, 64 columns).
- **Partial date coverage:** Sales Invoice Details.xlsx / Sheet1 / `Invoice Date`: 2025-12-21 to 2026-09-13; 10 observed months; GSTR1_Invoice.csv / (CSV table) / `Invoice_Date`: 2025-12-21 to 2026-09-13; 10 observed months; GSTR1_Credit_Debit_Note 2.csv / (CSV table) / `CreditDebitNote_Date`: 2026-09-21 to 2026-10-31; 2 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T03 - Customer purchase propensity

**Observed fields (proposed roles only):** Customer Master Report 1.xlsx / Sheet1: `CUSTOMER CODE` (position 2, Snapshot party attributes; no eligibility history), `ACTIVE` (position 13, Snapshot party attributes; no eligibility history), `INACTIVE` (position 14, Snapshot party attributes; no eligibility history), `GSTIN` (position 25, Snapshot party attributes; no eligibility history); Sales Order Report 1.xlsx / Sheet1: `Customer Code` (position 2, Possible positive event evidence; keys/time/purchase meaning unapproved), `Posting Date` (position 9, Possible positive event evidence; keys/time/purchase meaning unapproved), `SO No` (position 7, Possible positive event evidence; keys/time/purchase meaning unapproved), `Status` (position 8, Possible positive event evidence; keys/time/purchase meaning unapproved); Sales Invoice Details.xlsx / Sheet1: `Customer Billing Name` (position 9, Party mapping cannot be assumed), `Customer Billing GSTIN` (position 40, Party mapping cannot be assumed), `Invoice Date` (position 8, Party mapping cannot be assumed), `Invoice Num` (position 7, Party mapping cannot be assumed).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** P(purchase in (t,t+H] | information available at t) for an eligible customer
- **Definition (proposal only):** Proposed definition only: positive if approved purchase event occurs in the complete outcome window; negative only if eligible and fully observed with no qualifying purchase. Censored/unknown is not negative. No labels made.
- **Source/history evidence:** Customer/order references and purchases-like events exist, but all 40 small-order customer codes occur in the 40-row master. No verified historical nonpurchaser/cohort/exposure panel or eligibility start/end/observation boundary. Invoice customer mapping is unapproved.
- **Observation grain:** Eligible customer at cutoff t; customer identity, H and repeat-scoring interval require approval.
- **Identifier dependencies:** Historical stable customer identity, eligibility history, qualifying purchase event/document identity and approved invoice-party mapping.
- **Date/availability dependencies:** Decision t, purchase time, eligibility intervals, availability/capture cutoff and full mature window t+H; these clocks are not supplied as a verified panel.
- **Missing evidence and conditions:** Approved customer crosswalk; onboarding/eligibility/activity history, complete event capture, extraction closure, outcome maturity and decision-time availability.
- **Approach boundary:** Supervised classification or event-time approach only after cohort, historical positive/negative outcomes and label maturity are defensible.
- **Observed source shapes:** Customer Master Report 1.xlsx / Sheet1 (40 rows, 35 columns); Sales Order Report 1.xlsx / Sheet1 (1098 rows, 26 columns); Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns).
- **Partial date coverage:** Sales Order Report 1.xlsx / Sheet1 / `Posting Date`: unestablished to unestablished; 0 observed months; Sales Invoice Details.xlsx / Sheet1 / `Invoice Date`: 2025-12-21 to 2026-09-13; 10 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T04 - Product/service demand forecasting

**Observed fields (proposed roles only):** Sales Invoice Details.xlsx / Sheet1: `Invoice Date` (position 8, Observed goods/service class and quantity/unit fields), `Part Code SAP Code` (position 14, Observed goods/service class and quantity/unit fields), `Item Foreign Code` (position 15, Observed goods/service class and quantity/unit fields), `Item Type G or S` (position 13, Observed goods/service class and quantity/unit fields), `Quantity` (position 19, Observed goods/service class and quantity/unit fields), `UOM` (position 20, Observed goods/service class and quantity/unit fields), `Taxable Value` (position 22, Observed goods/service class and quantity/unit fields); Sales Order Report 1.xlsx / Sheet1: `Posting Date` (position 9, Booked detail proxy; status-at-time and blank items unresolved), `Item No` (position 11, Booked detail proxy; status-at-time and blank items unresolved), `Quantity` (position 15, Booked detail proxy; status-at-time and blank items unresolved), `Unit Price` (position 16, Booked detail proxy; status-at-time and blank items unresolved), `Status` (position 8, Booked detail proxy; status-at-time and blank items unresolved); Item Master Lists 1.xlsx / Item Lists: `Item No.` (position 2, Candidate reference; current master is not historical dimension), `foreign Code` (position 8, Candidate reference; current master is not historical dimension), `Pricing unit` (position 18, Candidate reference; current master is not historical dimension), `Item Group` (position 15, Candidate reference; current master is not historical dimension), `Product Segment` (position 13, Candidate reference; current master is not historical dimension), `Lead Time` (position 14, Candidate reference; current master is not historical dimension).

**Classification:** Feasible with Conditions; no training readiness or execution authorization.

- **Proposed target:** Future product-period reported quantity, or service-period activity/value under a separately approved unit
- **Definition (proposal only):** Proposed only: SUM(Quantity) for approved product/UOM and event scope. Goods/service flags identify separate line classes; do not add incompatible units or infer latent unmet demand. Service hours/jobs are not provided.
- **Source/history evidence:** Small invoice has 323 G and 14 S lines; large has 99,242 G and 941 S. Small order has 36 blank product rows; repeated SO scope and service-like zero quantities prevent a universal quantity target. UOM Manual is not a confirmed physical unit.
- **Observation grain:** Product + approved unit + period; service category/metric requires an owner-approved definition.
- **Identifier dependencies:** Approved product/service identity, unit, issuer/agency scope and stable source event/line identity; classification joins require separate approval.
- **Date/availability dependencies:** Approved order/invoice event according to the chosen observed-demand proxy; actual demand/stockout and service completion histories are absent/unverified.
- **Missing evidence and conditions:** Approved item/foreign-code crosswalks, returns/cancellations, pricing units, complete entity history, stockout/lost-sales data for latent demand and actual service units/history.
- **Approach boundary:** Per-series or pooled time-series strategy depends on each entity history, intermittency, cold starts and hierarchy validity; not one algorithm for every product.
- **Observed source shapes:** Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns); Sales Order Report 1.xlsx / Sheet1 (1098 rows, 26 columns); Item Master Lists 1.xlsx / Item Lists (150 rows, 19 columns).
- **Partial date coverage:** Sales Invoice Details.xlsx / Sheet1 / `Invoice Date`: 2025-12-21 to 2026-09-13; 10 observed months; Sales Order Report 1.xlsx / Sheet1 / `Posting Date`: unestablished to unestablished; 0 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T05 - Inventory forecasting

**Observed fields (proposed roles only):** Inventory Audit Report as on 200327.xlsx / Sheet1: ` Item No. ` (position 2, Grouped movement and cumulative fields; not a validated stock panel), `System Date` (position 4, Grouped movement and cumulative fields; not a validated stock panel), `Posting Date` (position 5, Grouped movement and cumulative fields; not a validated stock panel), `Document` (position 6, Grouped movement and cumulative fields; not a validated stock panel), `Doc. Row` (position 7, Grouped movement and cumulative fields; not a validated stock panel), `Whse` (position 8, Grouped movement and cumulative fields; not a validated stock panel), `Quantity` (position 9, Grouped movement and cumulative fields; not a validated stock panel), `Trans. Value` (position 11, Grouped movement and cumulative fields; not a validated stock panel), `Cumulative Qty` (position 12, Grouped movement and cumulative fields; not a validated stock panel), `Cumulative Value  ` (position 13, Grouped movement and cumulative fields; not a validated stock panel); Item Master Lists 1.xlsx / Item Lists: `In Stock` (position 4, Current extract quantities do not create past snapshots), `Order to Supllier` (position 5, Current extract quantities do not create past snapshots), `Order by Customer` (position 6, Current extract quantities do not create past snapshots), `Minimum Inventory` (position 17, Current extract quantities do not create past snapshots), `Date of Udate` (position 19, Current extract quantities do not create past snapshots).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** Future stock balance or probability of stockout over an approved horizon
- **Definition (proposal only):** Desired balance identity only: approved opening stock + signed receipts - signed issues +/- approved adjustments. Movement signs/types, grouping and opening/cumulative semantics are unvalidated; no stock series calculated.
- **Source/history evidence:** Large audit has 98,104 movement rows without raw item code; three grouped audits are not a confirmed regular snapshot panel. Item master stock/update date is not repeated historical stock observation.
- **Observation grain:** Product/warehouse/availability time; forecast horizon should reflect replenishment decisions, not an arbitrary fixed period.
- **Identifier dependencies:** Product + warehouse + company and stable typed movement/snapshot identity; raw item group labels cannot be inherited without approval.
- **Date/availability dependencies:** Actual posting/effective movement time, availability clock and authoritative stock as-of time; master update date is not a stock panel.
- **Missing evidence and conditions:** Opening balances, stable movement/product/warehouse IDs, receipt/issue/adjustment semantics, as-of snapshots, reservations, purchase orders and actual receipt/stockout history.
- **Approach boundary:** Inventory balance planning/rules may be sufficient when future movements are known; uncertain inputs may later require forecasts. Stockout classification needs availability/outcome history.
- **Observed source shapes:** Inventory Audit Report as on 200327.xlsx / Sheet1 (108129 rows, 13 columns); Item Master Lists 1.xlsx / Item Lists (150 rows, 19 columns).
- **Partial date coverage:** Inventory Audit Report as on 200327.xlsx / Sheet1 / `System Date`: 2026-09-21 to 2026-11-02; 3 observed months; Inventory Audit Report as on 200327.xlsx / Sheet1 / `Posting Date`: 2026-09-21 to 2026-11-02; 3 observed months; Item Master Lists 1.xlsx / Item Lists / `Date of Udate`: unestablished to unestablished; 0 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T06 - Unknown numerical outcomes

**Observed fields (proposed roles only):** Sales Invoice Details.xlsx / Sheet1: `Quantity` (position 19, Observed amounts, no approved decision-time labels), `Unit Price` (position 21, Observed amounts, no approved decision-time labels), `Taxable Value` (position 22, Observed amounts, no approved decision-time labels), `Invoice Date` (position 8, Observed amounts, no approved decision-time labels).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** Owner-selected realized numerical outcome at an explicit event/decision horizon
- **Definition (proposal only):** No approved realized-outcome/decision-time pair supplied. Existing invoice amounts and quantities are observed fields, not automatically regression labels for an unseen transaction.
- **Source/history evidence:** Numerical fields exist, but no approved quote/decision snapshot, actual realization linkage or availability timestamps establish a leakage-free supervised dataset.
- **Observation grain:** Decision/event row with stable identity and outcome linkage, not arbitrary missing-cell imputation.
- **Identifier dependencies:** Stable historical decision and realized-outcome identity; no validated decision/realization pair has been supplied.
- **Date/availability dependencies:** Actual decision time, each input availability time and realized outcome/maturity date; observed invoice date alone does not establish this contract.
- **Missing evidence and conditions:** Decision records, effective/available timestamps, realized outcome definition, scope, training eligibility and outcome delay.
- **Approach boundary:** Supervised regression is conditional on historical feature availability, comparable decisions and outcome capture; deterministic quantity/price arithmetic remains analytics.
- **Observed source shapes:** Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns).
- **Partial date coverage:** Sales Invoice Details.xlsx / Sheet1 / `Invoice Date`: 2025-12-21 to 2026-09-13; 10 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T07 - Cancellation or adjustment risk

**Observed fields (proposed roles only):** Sales Order Report 1.xlsx / Sheet1: `Status` (position 8, Current state only), `Posting Date` (position 9, Current state only), `SO No` (position 7, Current state only); GSTR1_Credit_Debit_Note 2.csv / (CSV table): `CreditDebitNote_Date` (position 1, Observed adjustments, not a cohort of negative outcomes), `Invoice_Number` (position 5, Observed adjustments, not a cohort of negative outcomes), `Type_Credit_or_Debit` (position 3, Observed adjustments, not a cohort of negative outcomes).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** Future event indicator within a defensible observation window
- **Definition (proposal only):** Current Status and existing notes are observed states/events, not future labels. Need order/invoice-at-t cohort plus event timestamps and complete non-event windows.
- **Source/history evidence:** Small order has current 44 Canceled lines, 50 Open and 1,004 Closed; these are line states, not 44 uniquely scoped historical cancellation outcomes. No transition history or verified negatives.
- **Observation grain:** Eligible document at cutoff with unambiguous company/year/series/line scope.
- **Identifier dependencies:** Scoped order/invoice and lifecycle event identity, with original document links and full non-event follow-up.
- **Date/availability dependencies:** Decision cutoff, actual status-transition or adjustment time, availability and complete outcome-window closure; current Status has no validated transition timestamp.
- **Missing evidence and conditions:** Status event log, decision-time state/features, cancellation/credit dates, original document keys and full follow-up.
- **Approach boundary:** Classification or event-time analysis only with matured outcomes and approved temporal document linkage.
- **Observed source shapes:** Sales Order Report 1.xlsx / Sheet1 (1098 rows, 26 columns); GSTR1_Credit_Debit_Note 2.csv / (CSV table) (279 rows, 64 columns).
- **Partial date coverage:** Sales Order Report 1.xlsx / Sheet1 / `Posting Date`: unestablished to unestablished; 0 observed months; GSTR1_Credit_Debit_Note 2.csv / (CSV table) / `CreditDebitNote_Date`: 2026-09-21 to 2026-10-31; 2 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T08 - Delivery time or delay prediction

**Observed fields (proposed roles only):** Sales Order Report 1.xlsx / Sheet1: `Posting Date` (position 9, Actual versus planned event role unconfirmed), `Delivery Date` (position 10, Actual versus planned event role unconfirmed), `SO No` (position 7, Actual versus planned event role unconfirmed), `Item No` (position 11, Actual versus planned event role unconfirmed); Sales Order Report 2.xlsx / Sheet1: `Posting Date  ` (position 9, Invalid/future dates constrain duration labels), `Delivery Date` (position 10, Invalid/future dates constrain duration labels).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** Actual completion duration, or actual-versus-promised lateness
- **Definition (proposal only):** No verified actual delivery/completion timestamp. Delivery Date role is unconfirmed; subtracting it from Posting Date yields a reported interval, not necessarily realized delivery performance.
- **Source/history evidence:** Posting Date and Delivery Date exist; large delivery field contains 15 impossible dates and values extending to 2028-04-30 under partial interpretations.
- **Observation grain:** Scoped order/line/service event and promised-versus-actual event history.
- **Identifier dependencies:** Scoped order/line or service, shipment/completion identity and partial-fulfilment references.
- **Date/availability dependencies:** Actual versus promised dispatch/delivery/completion timestamps and censoring; Delivery Date role remains unconfirmed.
- **Missing evidence and conditions:** Promise revisions, actual shipment/delivery/completion events, partial quantities, censoring and stable line references.
- **Approach boundary:** Regression/survival only with actual events, censoring and decision-time evidence; a planned-date difference is analytics.
- **Observed source shapes:** Sales Order Report 1.xlsx / Sheet1 (1098 rows, 26 columns); Sales Order Report 2.xlsx / Sheet1 (100286 rows, 26 columns).
- **Partial date coverage:** Sales Order Report 1.xlsx / Sheet1 / `Posting Date`: unestablished to unestablished; 0 observed months; Sales Order Report 1.xlsx / Sheet1 / `Delivery Date`: unestablished to unestablished; 0 observed months; Sales Order Report 2.xlsx / Sheet1 / `Posting Date  `: 2026-08-15 to 2026-11-02; 4 observed months; Sales Order Report 2.xlsx / Sheet1 / `Delivery Date`: 2026-08-22 to 2026-11-02; 4 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T09 - Collections, cash flow, recognized revenue or margin

**Observed fields (proposed roles only):** Sales Order Report 1.xlsx / Sheet1: `Payment Terms` (position 23, Payment terms do not prove settlement), `Total (LC)` (position 18, Payment terms do not prove settlement); Inventory Audit Report as on 200327.xlsx / Sheet1: `Cost` (position 10, Movement valuation is not validated realized sales margin), `Trans. Value` (position 11, Movement valuation is not validated realized sales margin).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** Future settled cash, ledger-recognized amount or realized margin under an approved finance definition
- **Definition (proposal only):** No actual settlement/recognition/COGS allocation outcome established. Payment Terms, invoice totals and inventory costs are not substitute labels.
- **Source/history evidence:** Schema lacks identified actual-payment/settlement and recognition lifecycle fields. Inventory Cost/Trans. Value are not validated invoice-line COGS.
- **Observation grain:** Customer/invoice/ledger period with actual settlement and cost allocation scope.
- **Identifier dependencies:** Party/invoice, payment allocation, recognition ledger and realized cost allocation identities; relevant finance lifecycle records not supplied.
- **Date/availability dependencies:** Actual settlement/due/recognition/COGS effective and available times, depending on the requested outcome; no verified outcome clocks in supplied schema.
- **Missing evidence and conditions:** Receivables/payments, allocations, general ledger recognition, realized COGS, currency and adjustment policies.
- **Approach boundary:** Forecasting, regression or classification depends on the outcome; no approach is admissible without labels/financial semantics.
- **Observed source shapes:** Sales Order Report 1.xlsx / Sheet1 (1098 rows, 26 columns); Inventory Audit Report as on 200327.xlsx / Sheet1 (108129 rows, 13 columns).
- **Partial date coverage:** No verified outcome chronology established.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T10 - Tax/adjustment activity forecasting

**Observed fields (proposed roles only):** GSTR1_Credit_Debit_Note 2.csv / (CSV table): `CreditDebitNote_Date` (position 1, Scoped counts/measure proposal only), `CreditDebitNote_Number` (position 2, Scoped counts/measure proposal only), `Doc_Series` (position 51, Scoped counts/measure proposal only), `Doc_Series_Prefix` (position 52, Scoped counts/measure proposal only), `Doc_Series_Suffix` (position 53, Scoped counts/measure proposal only), `Type_Credit_or_Debit` (position 3, Scoped counts/measure proposal only), `IGST_Amount` (position 20, Scoped counts/measure proposal only), `CGST_Amount` (position 22, Scoped counts/measure proposal only), `SGST_Amount` (position 24, Scoped counts/measure proposal only).

**Classification:** Feasible with Conditions; no training readiness or execution authorization.

- **Proposed target:** Future scoped note/event count or approved additive reported tax component per period
- **Definition (proposal only):** Proposed only: distinct scoped note counts or separately approved line tax sums; respect CN/DN series, sign and filing/revision scope. Do not add overlapping invoice/GST representations.
- **Source/history evidence:** 6-row notes have 6 scoped references; 276 nonempty larger-note rows have 243 scoped references, 33 repeats and 3 exact excess duplicates. Much larger-note coverage extends beyond assessment date.
- **Observation grain:** Issuer/reporting-period/note type; H and tax-accounting meaning require owner approval.
- **Identifier dependencies:** Issuer/year/series/type-scoped note reference and original invoice identity; stable line key required for line measures.
- **Date/availability dependencies:** CreditDebitNote_Date, approved reporting period/revision and publication/maturity cutoff; month-without-year does not establish time scope.
- **Missing evidence and conditions:** Filing versions, dates, note scope/sign, completeness, authority and enough mature reporting periods.
- **Approach boundary:** Time-series aggregate strategy if mature history and stable filing scope exist; current tax arithmetic is diagnostic analytics.
- **Observed source shapes:** GSTR1_Credit_Debit_Note 2.csv / (CSV table) (279 rows, 64 columns).
- **Partial date coverage:** GSTR1_Credit_Debit_Note 2.csv / (CSV table) / `CreditDebitNote_Date`: 2026-09-21 to 2026-10-31; 2 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T11 - Hierarchical or segmented forecasting

**Observed fields (proposed roles only):** Item Master Lists 1.xlsx / Item Lists: `Item No.` (position 2, Hierarchy candidates require approved scope/history), `Item Group` (position 15, Hierarchy candidates require approved scope/history), `Segment` (position 12, Hierarchy candidates require approved scope/history), `Product Segment` (position 13, Hierarchy candidates require approved scope/history); Sales Invoice Details.xlsx / Sheet1: `Territory` (position 42, Segment fields observed but memberships/time semantics unknown), `Sales Employee` (position 41, Segment fields observed but memberships/time semantics unknown), `Country` (position 12, Segment fields observed but memberships/time semantics unknown), `Part Code SAP Code` (position 14, Segment fields observed but memberships/time semantics unknown).

**Classification:** Feasible with Conditions; no training readiness or execution authorization.

- **Proposed target:** Same approved additive/count outcome per validated hierarchy level
- **Definition (proposal only):** No new target invented: inherit an approved outcome contract; aggregate only along approved many-to-one dimensions and compatible units.
- **Source/history evidence:** Customer/item and PTC/PCT classification candidates exist; 27 row-preserving raw-key directions remain conditional. Larger master duplicates and partial matching can expand or lose records.
- **Observation grain:** Approved customer/product/territory/category hierarchy and time bucket.
- **Identifier dependencies:** Approved base-target identity plus historical entity/hierarchy version and membership scope.
- **Date/availability dependencies:** Base target event/availability clocks plus hierarchy effective/available intervals; current master membership cannot be applied retrospectively without approval.
- **Missing evidence and conditions:** Validated hierarchy, time-varying memberships, entity identity, unit consistency, enough history per series and treatment of new/discontinued entities.
- **Approach boundary:** Pooled/per-series/hierarchical strategy requires individual-series coverage, cold-start and reconciliation evaluation; not guaranteed by global row count.
- **Observed source shapes:** Item Master Lists 1.xlsx / Item Lists (150 rows, 19 columns); Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns).
- **Partial date coverage:** No verified outcome chronology established.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T12 - Historical retrieval, aggregations and diagnostics

**Observed fields (proposed roles only):** Sales Invoice Details.xlsx / Sheet1: `Invoice Date` (position 8, Historical quantities/values are analytics), `Quantity` (position 19, Historical quantities/values are analytics), `Taxable Value` (position 22, Historical quantities/values are analytics).

**Classification:** Feasible with Conditions; no training readiness or execution authorization.

- **Proposed target:** No prediction target; approved recorded counts/sums/rates or audit findings
- **Definition (proposal only):** Read-only retrieval, grouping or rules at verified grain. Source structure/missingness/duplicate counts already reproducible; business SUM/COUNT semantics still need approval.
- **Source/history evidence:** 20 validated tables / 521 columns and existing quality/relationship calculations support descriptive evidence. Business measures remain conditional on authority, grain and date rules.
- **Observation grain:** Requested historical scope; preserve raw-versus-diagnostic interpretations and unresolved dates.
- **Identifier dependencies:** Depends on requested historical grain; use approved event/document identity for business counts, or source row position only for structural audit counts.
- **Date/availability dependencies:** Requested historical event/as-of basis, or no time dimension for a source-structure audit; actual field roles must be distinguished.
- **Missing evidence and conditions:** Clarify metric, scope, time basis and join safety. Fraud/causal claims would need independent labels or intervention evidence.
- **Approach boundary:** SQL/dataframe aggregation or documented rules; ML is unnecessary for observed facts. Anomaly flags are diagnostic, not fraud probabilities or predictive accuracy.
- **Observed source shapes:** Sales Invoice Details.xlsx / Sheet1 (337 rows, 43 columns).
- **Partial date coverage:** Sales Invoice Details.xlsx / Sheet1 / `Invoice Date`: 2025-12-21 to 2026-09-13; 10 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

### T13 - Currency rate forecasting

**Observed fields (proposed roles only):** Exchange Rate.xlsx / INR to JPY: `Rate Month` (position 1, Explicit synthetic source), `Start Date` (position 2, Explicit synthetic source), `End Date` (position 3, Explicit synthetic source), `From Currency` (position 4, Explicit synthetic source), `To Currency` (position 5, Explicit synthetic source), `Exchange Rate (1 INR = ? JPY)` (position 6, Explicit synthetic source).

**Classification:** Not Currently Feasible; no training readiness or execution authorization.

- **Proposed target:** Future observed market/contract FX rate under an approved basis
- **Definition (proposal only):** No production target from marked synthetic examples. Rate Month is a period; start/end applicability and rate fixing basis remain unapproved.
- **Source/history evidence:** Only 7 and 22 explicitly synthetic monthly rate records, overlapping two pairs/periods; some future periods and serial-date candidates.
- **Observation grain:** Currency pair, fixing basis, timezone and requested horizon.
- **Identifier dependencies:** Currency pair + fixing basis + period/instant as an approved scope; supplied synthetic period keys are not production identifiers.
- **Date/availability dependencies:** Rate Month, Start Date and End Date are synthetic period evidence; production fixing/publication time and calendar required.
- **Missing evidence and conditions:** Production market/contract rates, fixing calendar, publication timestamps, currency convention and approved conversion policy.
- **Approach boundary:** Time-series methods cannot establish production validity from synthetic examples; no FX forecast or financial advice produced.
- **Observed source shapes:** Exchange Rate.xlsx / INR to JPY (22 rows, 7 columns).
- **Partial date coverage:** Exchange Rate.xlsx / INR to JPY / `Rate Month`: unestablished to unestablished; 0 observed months; Exchange Rate.xlsx / INR to JPY / `Start Date`: 2024-12-21 to 2026-09-21; 22 observed months; Exchange Rate.xlsx / INR to JPY / `End Date`: 2025-01-20 to 2026-10-20; 22 observed months.
- **Horizon:** Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.
- **Relationships and approvals:** Use only required source scope; any cross-source dependency needs an exact approved relationship. No business relationship or target approval was supplied.
- **Leakage controls:** Prove actual outcome and input availability at the decision cutoff; exclude future/revised information from historical inputs under approved rules. Preserve related-document identity across later validation boundaries. See the shared controls below.

## Shared dependencies and leakage controls

[Leakage and validation evidence](feasibility_evidence/leakage_and_validation_controls.csv) requires event/availability-time separation, mature history, point-in-time master/hierarchy states, explicit source overlap handling, document/line grouping, target-safe financial inputs and chronological evaluation appropriate to H. No feature or split is generated here. No assertion is made that business semantics can be recovered from a column name.

[Relationship dependency evidence](feasibility_evidence/relationship_dependency_evidence.csv) and [controlled join evidence](controlled_join_validation.csv) document cardinality and financial distortion risks. For the first candidate, do not join orders/GST/customer/product tables merely because values overlap. Customer/product splits activate additional identity/coverage decisions; recognized revenue needs ledger/recognition sources, inventory needs approved historical snapshots/movements/group semantics, propensity needs population/outcome history and FX needs genuine production rate history.

All 17 unresolved owner decisions and original rule IDs, affected file/fields and evidence requirements are in [approval blockers](nop_readiness_evidence/approval_blockers.json). D01-D13 are core to the recommended scope, with D14-D17 conditional. The [readiness report](nop_dataset_readiness_report.md) distinguishes business decisions, authenticated runtime records and unsupported worker capabilities as of that assessment.

## Recommendation and stop boundary

Do not choose a native numerical field as a replacement target merely because it bypasses aggregation. Obtain scoped business answers first, confirm sufficient complete history for the agreed bucket/H, and then request approval for the exact supported execution path. No candidate is currently cleared for a training dataset. Additional history or outcome sources depend on the agreed objective. Preserve the general-purpose schema-aware backend: no fixed question catalogue, NOP mappings in reusable components or universal training dataset was introduced.
