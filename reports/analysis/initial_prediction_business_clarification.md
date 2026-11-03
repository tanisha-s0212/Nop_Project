# Initial prediction: business clarification brief

**Purpose:** obtain scoped NOP business, ERP, finance and data-owner decisions before preparation. This is a meeting document, not approval or a catalogue of end-user prediction questions. No source data is cleaned, transformed, joined or aggregated; no labels, features or models are generated.

## Discuss this candidate first

Discuss **future scoped invoice-document volume**: one approved invoice document per approved time bucket and horizon. This is a proposed aggregate event-count capability, not an agreed target or chosen model. Confirm usefulness first; invoice count is not order booking, shipped units, invoiced value or recognized revenue.

Evidence anchor: `Sales Invoice Details.xlsx / Sheet1` has **337 detail lines / 234 nonblank raw invoice references**, with consistent observed party/date/document total within each reference. That does not approve a global business key. `Invoice Date` has **107 ambiguous values**; 230 calendar-resolved full-year values span **2025-12-21–2026-09-13**, ten observed months with completeness unconfirmed. These are not 337 temporal observations and do not establish annual seasonality or enough holdout history. The smaller extract is a discussion anchor, not the chosen authority.

| Priority | Candidate | Missing evidence / limitation |
| --- | --- | --- |
| 1 | Scoped invoice-document volume: consistent observed references; can avoid business joins and monetary/unit rules | Authority/version, actual event, identity/date/lifecycle scope, complete mature periods, H and evaluation support |
| 2 | Approved invoiced-value proxy: reported financial fields exist | Same source/time issues plus additivity, currency/sign/discount/freight/tax/adjustments; recognition needs ledger evidence |
| 3 | Observed goods/product quantity: item/quantity fields and 323 G / 14 S small-invoice lines | Product identity, compatible units and per-series history; Manual UOM unapproved; service hours/latent demand unsupported |

All three are **Feasible with Conditions; none is ready for training**. Propensity/inventory remain deferred under existing feasibility findings. The longer small-order range is not a better first count by default: 275/299 raw SO groups vary customer, 278 vary Posting Date and its dates depend on an unapproved century convention.

## Scope the discussion tightly

Proposed minimum: `Invoice Num`, `Invoice Date`, qualifying type/event semantics (`TransType` where relevant) and confirmed issuer/source metadata. No customer/product master, order or inventory join, financial calculation or GST join is inherently required for issuer-level document count. Request missing metadata; do not invent it.

Lifecycle is a core population decision, but gross issuance does not automatically require net-revenue or GST tax/note-allocation rules. Activate only dependencies triggered by the accepted source/outcome.

The [readiness workbook](initial_prediction_readiness_checklist.xlsx) contains all 17 decisions with exact file/worksheet/fields, owner roles, existing evidence, why/impact and required confirmation. **D01–D13 are core; D14–D17 conditional.** D12 is Proposed; other decisions are Unresolved. No business decision is Confirmed. Answer, approver and date placeholders remain blank; owner roles are not appointed people.

## Core owner questions

| Decision / original rules | Exact owner question |
| --- | --- |
| D01 / BR-005; BR-034 | Which exact invoice extract/version is authoritative for the intended issuer/company/branch and history, and is it complete production data rather than a filtered, sample or synthetic extract? |
| D02 / BR-006 | Does forecasting issued invoice-document volume support the actual business decision, and which event/transaction types qualify? If the need is units, orders or value, what is that outcome instead? |
| D03 / BR-010; BR-025 | Within what issuer/company, series and financial-year scope does Invoice Num identify one invoice? Can it be reused or reformatted, and must case, spaces, punctuation and leading zeros be preserved? |
| D04 / BR-010; BR-023 | Are rows invoice detail lines and should the count be once per approved scoped invoice regardless of line count? What verified policy applies if a later record has missing keys/dates or conflicting document dates? |
| D05 / BR-016; BR-018 | What source/version-specific formats and business meaning does Invoice Date have, and is it the correct count-event date? Please verify ambiguous examples using ERP/export evidence, not a guessed global DD/MM or MM/DD default. |
| D06 / BR-007 | Should we count gross issued invoices, valid/nonvoid invoices or another lifecycle outcome? How do cancellations, returns, credit/debit adjustments and reissues affect it, as of when? If lifecycle evidence is absent, is labelled gross issuance acceptable? |
| D07 / BR-019; BR-032 | Are records actual issued events, plans or tests? What extraction watermark, revision/reporting delay and latest complete cutoff apply, and what shows history was available at each forecast decision time? |
| D08 / BR-018; BR-020 | Which calendar and reporting boundaries apply, which periods are closed and fully captured, and how is a true no-invoice period distinguished from incomplete, unobserved or out-of-scope data? |
| D09 / BR-005; BR-024 | Will one approved source/version supply history? If repeat exports, amendments or recurring records appear, which are the same occurrence and what precedence rule applies? Please distinguish valid detail lines from duplicate extracts. |
| D10 / BR-006; BR-032 | Who uses the forecast, for which decision, at what issuer-level scope, time bucket, future horizon H and update cadence? What lead time is useful, and are customer/product splits actually required? |
| D11 / BR-020; BR-033 | Can NOP provide complete mature authoritative history for the agreed horizon, bucket and validation periods, with closure and scope-change evidence? If an honest holdout is unsupported, what additional history can be supplied? |
| D12 / BR-033 | Can we agree chronological evaluation for H with mature training observations, protected holdout periods and suitable simple baselines? Which error costs and acceptance criteria match the decision? |
| D13 / BR-002; BR-012; BR-036 | Who owns each applicable decision/exception, and will they approve the exact source/version, treatment and checks before execution? Please authorize cleaning, dataset construction, feature work and training as distinct bounded activities. |

## Ask only when triggered

| Decision / original rules | Exact owner question |
| --- | --- |
| D14 / BR-008; BR-009; BR-030 | Only if a customer/product split or filter is requested: which scoped identities and historical crosswalks are authoritative, and how are shared/missing codes and memberships handled at decision time? |
| D15 / BR-013; BR-014; BR-015; BR-021; BR-022; BR-029 | Only for a value, quantity or net-financial outcome: what measure, currency/unit and tax/freight/discount/sign/adjustment basis is intended? Is recognized revenue needed rather than an invoiced-value proxy? |
| D16 / BR-028; BR-029; BR-030 | Only if GST is primary or an owner requires reconciliation: what issuer/series/prefix/suffix and version rules define the document, and what reconciliation grain/exceptions are approved? Is a business join needed at all? |
| D17 / BR-016; BR-017; BR-019 | If an alternate mixed-date source is chosen, what formats, century and workbook epoch/domain rules apply to its relevant date field, and which future/planned entries are actual history? Can source-verified examples support each interpretation? |

All 36 original rules are reviewed, not modified. BR-026/027 (inventory) and BR-035 (PCT_NOPJ) are deferred for this count. BR-008/009 apply to requested entity splits/filters; BR-013–015/021–022 to relevant measures/filters; BR-028/029 and BR-030 to required GST/source/reconciliation/join dependencies. BR-031 is evidence, not a requirement to approve 148 relationships. BR-032 applies to cutoff/H/maturity, not a propensity positive/negative cohort. No rule is generally waived or resolved.

## Readiness by stage

All execution stages remain **not authorized / not ready**. The workbook provides 15 checkable items.

| Before this activity | Minimum evidence and approval |
| --- | --- |
| Establish target/observation grain | Authority and accepted business use; scoped identity/grain; lifecycle, date, calendar/complete periods, zero policy and t/H/cadence |
| Clean relevant fields only | Exact version/projection and approved key/date/exception/occurrence policy; immutable raw/change lineage and explicit treatment authorization. H/evaluation need not block an otherwise approved bounded parser, but still block later dependent work |
| Construct first training dataset | Accepted outputs from later authorized preparation; signed observation contract and mature history for H/folds; record/document/exception conservation and provenance; explicit build permission. No joins by default |
| Prepared-data EDA/features | Accepted derivative and scoped permission; known-at-cutoff inputs/features and fold-local fitting. Reviewing existing audits now does not permit new source analysis or features |
| Train/evaluate | Adequate mature temporal support; approved H/utility/metrics/baselines and chronological development/final holdout; compatible input/target/model scope, related-event leakage checks and explicit authorization |

## Evidence is not approval

- Small source has **zero exact/payload-excess duplicates** in prior checks. Repeated references are detail structure; do not delete them as duplicate invoices.
- GST is an alternate representation: prior document join expands 337 to 609; scoped invoice+description aligns 337, with no approved stable line key/relationship. No reconciliation is performed or imposed here.
- Large Invoice Date has 33,782 ambiguous values, 2,996 serial candidates and future-dated partial coverage. A source switch needs its own relevant decisions, not preference by size.
- Project-wide 424 issues, 203,455 ambiguous dates, 28 impossible dates, 14,949 serial candidates and duplicate findings remain unresolved. Address dependencies affecting this scope, not the entire project by default.

## Meeting outcome and next action

Record owner answer, source/rule version, scope, evidence, approver and date in `decision_response_log`. Move Unresolved/Proposed to Confirmed only on explicit recorded owner confirmation. Non-triggered items are not applicable **to this scope**, not globally approved. Consistent values or completed documents are not business approval or execution permission.

If invoice activity does not meet the objective, re-scope against actual evidence rather than substitute it. This is one proposed contract in the general-purpose schema-aware backend, not fixed prediction questions, question-to-dataset/model routes or a universal model. No UI, LLM or MCP functionality is implemented.

**Next:** hold the scoped owner review, then seek explicit authorization for the next bounded activity once its applicable checklist is satisfied. Stop here; preparation/model development does not start automatically.

## References

[Preparation strategy](data_preparation_strategy.md), [36-rule register](business_rule_register.xlsx), [cleaning specification](data_cleaning_specification.xlsx), [dataset blueprint](training_dataset_blueprint.xlsx), [prediction feasibility](business_prediction_feasibility_report.md), [target mapping](prediction_target_mapping.xlsx), [relationship evidence](identifier_relationship_matrix.xlsx), [document context](document_context.csv), [date evidence](../data_quality/date_quality.csv).

[Readiness/response workbook](initial_prediction_readiness_checklist.xlsx), [validation record](initial_prediction_clarification_validation.json), [preservation ledger](initial_prediction_clarification_evidence/preserved_input_integrity.csv).
