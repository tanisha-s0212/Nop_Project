# Data quality assessment

Review date: 2026-10-30. This assessment covers 14 Excel workbooks, 17 Excel worksheets and 3 GST CSV tables: **20 tables and 521 columns**. All source files match the validated inventory hashes. The executed notebook checks that source files and every inventory report/evidence file remain unchanged.

## Executive assessment

The sources are available for continued investigation, but preparation for forecasting requires approved rules for dates, source versions, record grain and identifiers. The assessment records **424 source/column/rule findings**: 0 Critical, 102 High, 218 Moderate and 104 Low. These are overlapping review findings, not a count of distinct bad business records. No universal quality score is assigned because required fields, valid domains and business tolerances are unconfirmed.

- Date investigation reproduces all **203,455 ambiguous day/month cells, 28 impossible calendar dates and 14,949 unconfirmed numeric Excel serial candidates** from inventory. Ambiguous dates remain raw; both possible readings are retained in the date evidence.
- Duplicate checks find **3 excess exact full rows** and **972 excess rows with identical business payload after excluding structural row ordinals**. These totals count within-source signatures. Repeated lines can be legitimate; no records were deleted.
- All **135 identifier candidates** were checked over full columns, and **101 candidate matching comparisons** were recomputed. Their metrics agree with inventory. No identifier or relationship is declared a confirmed business key or referential constraint.
- **56 columns** have at least 50% blanks on nonempty rows while requiredness is unconfirmed. Optional/conditional candidates are reported separately rather than automatically treated as defects.
- Numerical and financial flags use diagnostic interpretations and explicit tolerances. Their correctness depends on units, document grain, discounts, return/adjustment conventions and the tax calculation basis.
- The unnamed `PCT_NOPJ` column contains 33 `NOPJ` values. Context suggests an agency/source marker, but its name remains unassigned. Explicit synthetic-data titles in both exchange-rate sheets and the reference customer sheet also need provenance confirmation.

## Scope, preservation and methods

The starting reference is `reports/data_inventory/validation/inventory_validation_evidence.xlsx`, including validated headers, table counts, 37 date-related fields, 135 identifier candidates and 101 matching comparisons. Every table was read in full. Examples are limited to ten locations per finding; counts and statistics use complete applicable columns/rows. Completely empty rows remain represented.

Source data was read without rewriting, cleaning, imputation, record deletion, ambiguous-date conversion, source joins or model training. Numeric parsing, whitespace/case comparisons and possible date readings exist only in diagnostic copies and reports. inventory evidence is preserved. [Source integrity](source_integrity.csv) and [inventory artifact integrity](inventory_integrity.csv) record before/after SHA-256 evidence.

| file | worksheet | rows_below_header | nonempty_rows | empty_rows | columns |
| --- | --- | --- | --- | --- | --- |
| Customer Master Report 1.xlsx | Sheet1 | 40 | 40 | 0 | 35 |
| Customer Master Report 2.xlsx | Sheet1 | 5,015 | 5,012 | 3 | 35 |
| Exchange Rate 1.xlsx | INR to JPY | 7 | 7 | 0 | 7 |
| Exchange Rate.xlsx | INR to JPY | 22 | 22 | 0 | 7 |
| GSTR1_Credit_Debit_Note 1.csv | (CSV table) | 6 | 6 | 0 | 64 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | 279 | 276 | 3 | 64 |
| GSTR1_Invoice.csv | (CSV table) | 337 | 337 | 0 | 68 |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | 108,129 | 108,124 | 5 | 13 |
| Inventory Audit Report as on 200926 1.xlsx | Sheet1 | 162 | 162 | 0 | 13 |
| Inventory Audit Report as on 200926.xlsx | Sheet1 | 162 | 162 | 0 | 13 |
| Item Master Lists 1.xlsx | Item Lists | 150 | 150 | 0 | 19 |
| Item Master Lists 2.xlsx | Item Lists | 5,015 | 5,012 | 3 | 19 |
| Sales Invoice Details 1.xlsx | Sheet1 | 100,188 | 100,183 | 5 | 43 |
| Sales Invoice Details.xlsx | Sheet1 | 337 | 337 | 0 | 43 |
| Sales Order Report 1.xlsx | Sheet1 | 1,098 | 1,098 | 0 | 26 |
| Sales Order Report 2.xlsx | Sheet1 | 100,286 | 100,280 | 6 | 26 |
| Sales_Order_Data_202609.xlsx | Customer list | 43 | 43 | 0 | 4 |
| Sales_Order_Data_202609.xlsx | Country master | 11 | 11 | 0 | 5 |
| Sales_Order_Data_202609.xlsx | PTC_NOPI | 60 | 60 | 0 | 8 |
| Sales_Order_Data_202609.xlsx | PCT_NOPJ | 33 | 33 | 0 | 9 |

## Severity and issue interpretation

- **Critical:** loss of source integrity, missing assessment scope or unreadable sources preventing a trustworthy assessment. These conditions stop execution; none were detected in the completed run.
- **High:** substantial risk to dates, identity, linkage, representation of measures, source suitability or double counting. Business confirmation may establish that a pattern is legitimate.
- **Moderate:** plausible formatting, chronology, distribution, category or arithmetic concern whose meaning depends on context.
- **Low:** structural empty rows, optional-field candidates or numerical conventions that merit documentation without an automatic error conclusion.

Every finding in [issue_register.csv](issue_register.csv) includes source, worksheet, column, affected count and unit, denominator where applicable, row examples, impact, recommended resolution and whether business confirmation is required. Some coverage findings count calendar months rather than records. Counts from different rules must not be added as distinct affected records.

## Missing values and applicability

There are **25 completely empty rows** below the validated headers. Missing percentages are supplied both over all source rows and over nonempty rows, so empty structural rows do not inflate business-field missingness unnoticed. Blanks mean `None` or empty/whitespace-only text; placeholders such as `NA`, `#N/A`, `null` and `-` are separately counted and preserved.

Original/amendment fields, advance-receipt details, export/shipping fields, supplementary contact fields and transaction-dependent GST/HSN/SAC fields are marked as **conditional/optional candidates**, not confirmed optional fields. Requiredness remains a business decision. Sparse item labels in inventory audits are marked as a grouped-layout possibility; no fill-down is applied. No missing value is silently assigned a zero or substitute.

Examples with >=50% missingness and unconfirmed requiredness:

| file | worksheet | column_name | blanks_on_nonempty_rows | blank_percent_nonempty_rows |
| --- | --- | --- | --- | --- |
| Customer Master Report 1.xlsx | Sheet1 | TEL 1 | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | TEL 2 | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | WEBSITE | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | SHIPPING TYPE | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | STREET / PO BOX | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | Bill-to Block | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | STREET NO. | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | ACCOUNT NO. | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | BANK ACCOUNT NAME | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | BRANCH | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | SWIFT CODE / IFS CODE | 40 | 100 |
| Customer Master Report 1.xlsx | Sheet1 | PROPERTIES 1 | 40 | 100 |

Complete results: [missing_values.csv](missing_values.csv), one row per source column, including empty-column flags, placeholder counts, applicability explanations and original observed types. Requiredness/applicability should be confirmed before prioritizing blank fields for any cleaning.

## Duplicate records and transaction grain

Three comparisons are separated: all raw typed fields; all fields excluding `#`/`S.No` row ordinals; and an explicitly proposed transaction-line signature where document/item/date/quantity/price fields support it. Raw whitespace and source value types remain significant in exact comparisons. Within-source duplicate hash groups are verified by comparing their typed values.

| file | worksheet | comparison | duplicate_groups | duplicate_excess_rows | rows_in_duplicate_groups |
| --- | --- | --- | --- | --- | --- |
| Customer Master Report 2.xlsx | Sheet1 | all_fields_excluding_row_ordinal | 15 | 15 | 30 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | all_raw_fields | 3 | 3 | 6 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | all_fields_excluding_row_ordinal | 3 | 3 | 6 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | proposed_transaction_line_signature | 3 | 3 | 6 |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | all_fields_excluding_row_ordinal | 417 | 799 | 1,216 |
| Inventory Audit Report as on 200926 1.xlsx | Sheet1 | all_fields_excluding_row_ordinal | 2 | 8 | 10 |
| Inventory Audit Report as on 200926.xlsx | Sheet1 | all_fields_excluding_row_ordinal | 1 | 15 | 16 |
| Item Master Lists 2.xlsx | Item Lists | all_fields_excluding_row_ordinal | 12 | 12 | 24 |
| Sales Invoice Details 1.xlsx | Sheet1 | all_fields_excluding_row_ordinal | 60 | 60 | 120 |
| Sales Invoice Details 1.xlsx | Sheet1 | proposed_transaction_line_signature | 60 | 60 | 120 |
| Sales Order Report 2.xlsx | Sheet1 | all_fields_excluding_row_ordinal | 60 | 60 | 120 |
| Sales Order Report 2.xlsx | Sheet1 | proposed_transaction_line_signature | 60 | 60 | 120 |

Repeated customer/product codes in line tables and repeated document numbers can represent valid granularity. Master/reference codes and diagnostic name variants are separately inspected for repeated identities and differing attributes. Similar names do not prove that entities are identical. Cross-source same-schema payload overlap is reported only as evidence of possible overlapping exports; versions are kept separate and precedence is unconfirmed.

See [duplicate summaries](duplicate_analysis.csv), [duplicate groups and source locations](duplicate_groups.csv), [master/reference entity analysis](entity_duplicate_analysis.csv), and [cross-source payload overlap](cross_source_duplicate_coverage.csv). Confirm document series/fiscal scope/line identifiers and source precedence before considering deduplication.

## Date quality, representations and chronology

All 37 fields include original types, representative untouched values, format/status counts, interpretations, partial coverage and gap evidence in [date_quality.csv](date_quality.csv). [date_value_evidence.csv](date_value_evidence.csv) preserves every observed distinct raw token with its count, original type, candidate readings, interpretation notes and example locations. [date_cell_exceptions.csv](date_cell_exceptions.csv) enumerates incomplete/invalid/serial candidate cells with source coordinates.

- Ambiguous DMY/MDY values retain two alternatives. No one alternative becomes the source date or the accepted date for chronology checks.
- Impossible dates are separately distinguished from ambiguity. All 28 impossible calendar cells are represented in the exception report, including `31/02/27` and `31/02/26`.
- Numeric values are investigated using each workbook's actual epoch and supplied as **unconfirmed Excel serial candidates**. They remain excluded from accepted chronology and coverage.
- `Exchange Rate 1.xlsx` retains the corrected `2027-03` period. The seven observed month periods run September 2026 through March 2027. Month periods are tracked at monthly resolution; a candidate first day is a display convention, not an observed transaction day.
- `Revision_Month` numbers without years remain incomplete period attributes. Two-digit-year interpretations retain inventory's explicitly conditional century convention; source confirmation is still required.
- Chronological coverage and gaps use only calendar-unambiguous values (and explicit monthly periods for month coverage). Excluded ambiguous/serial dates can explain apparent gaps. Calendar gaps do not prove missing business activity, because no working calendar or expected transaction cadence is supplied.
- Proposed order/delivery, order/invoice and exchange-period start/end checks evaluate only pairs with unambiguous readings. Unevaluable counts are reported. Future dates are compared with 2026-10-30; planning dates can legitimately be future dates.

| file | column | ambiguous_values | invalid_calendar_values | possible_serial_values | unambiguous_min | unambiguous_max |
| --- | --- | --- | --- | --- | --- | --- |
| Sales Invoice Details 1.xlsx | SO Date | 34,065 | 0 | 2,397 | 2025-12-16 | 2027-03-19 |
| Inventory Audit Report as on 200327.xlsx | Posting Date | 33,850 | 0 | 1,915 | 2026-09-21 | 2027-03-20 |
| Sales Invoice Details 1.xlsx |  Invoice Date  | 33,782 | 0 | 2,996 | 2026-01-01 | 2027-03-20 |
| Inventory Audit Report as on 200327.xlsx | System Date | 33,743 | 8 | 1,995 | 2026-09-21 | 2027-03-20 |
| Sales Order Report 2.xlsx | Posting Date   | 33,242 | 0 | 2,975 | 2026-08-13 | 2027-03-20 |
| Sales Order Report 2.xlsx | Delivery Date | 31,699 | 15 | 2,455 | 2026-08-22 | 2028-04-30 |
| Item Master Lists 2.xlsx | Date of Udate | 1,571 | 5 | 205 | 2024-10-20 | 2026-09-17 |
| Sales Order Report 1.xlsx | Posting Date | 417 | 0 | 0 | 2024-04-13 | 2026-09-19 |
| Sales Order Report 1.xlsx | Delivery Date | 402 | 0 | 0 | 2024-04-16 | 2026-10-19 |
| Sales Invoice Details.xlsx | SO Date | 124 | 0 | 0 | 2025-11-26 | 2026-08-25 |
| GSTR1_Invoice.csv | Invoice_Date | 107 | 0 | 0 | 2025-12-21 | 2026-09-13 |
| Sales Invoice Details.xlsx | Invoice Date | 107 | 0 | 0 | 2025-12-21 | 2026-09-13 |

See [coverage gaps](date_coverage_gaps.csv) and [chronology checks](chronology_checks.csv). Confirm source-specific format, century, epoch and event semantics before approving any chronological dataset.

## Identifier quality and candidate referential coverage

All 135 inventory candidates have full-column null, duplicate and distinct counts, uniqueness percentages, semantic roles, candidate matching coverage status and explicit unconfirmed-key flags in [identifier_quality.csv](identifier_quality.csv). Uniqueness percentage is distinct nonblank values divided by nonblank values; null percentage is reported separately. Both all-row and nonempty-row denominators are provided.

Ordinals, measures, dates and classification/contact attributes are not promoted to entity keys merely because values are unique. Candidate document references may repeat legitimately on lines. All 101 inventory value-overlap comparisons are recomputed from full raw values in [identifier_matching_coverage.csv](identifier_matching_coverage.csv). Case and whitespace remain significant. Each unmatched transaction-to-master count is an **unconfirmed referential risk**, not a proved foreign-key violation. Unused master values are not automatically defects. Candidates without a supported comparison are explicitly marked unmapped/not applicable instead of receiving fabricated coverage.

| file | worksheet | column_name | null_or_blank_rows | distinct_nonblank_values | duplicate_excess_rows | nonblank_uniqueness_percent |
| --- | --- | --- | --- | --- | --- | --- |
| Inventory Audit Report as on 200327.xlsx | Sheet1 |  Item No.  | 103,119 | 5,010 | 0 | 100 |
| Sales Order Report 2.xlsx | Sheet1 | BP Catalog No | 100,286 | 0 | 0 |  |
| Sales Invoice Details 1.xlsx | Sheet1 | Item Foreign Code | 30,696 | 4,651 | 64,841 | 6.6929 |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | Document | 5,015 | 92,102 | 11,012 | 89.3206 |
| Item Master Lists 2.xlsx | Item Lists | foreign Code | 2,072 | 2,938 | 5 | 99.8301 |
| Sales Order Report 1.xlsx | Sheet1 | BP Catalog No | 1,098 | 0 | 0 |  |
| Sales Order Report 2.xlsx | Sheet1 | Item No | 1,027 | 7,363 | 91,896 | 7.418 |
| Sales Invoice Details 1.xlsx | Sheet1 | Part Code SAP Code | 946 | 7,339 | 91,903 | 7.3951 |
| GSTR1_Invoice.csv | (CSV table) | Shipping_Bill_Number | 337 | 0 | 0 |  |
| GSTR1_Invoice.csv | (CSV table) | Original_Invoice_Number | 337 | 0 | 0 |  |
| GSTR1_Invoice.csv | (CSV table) | AdvanceReceipt_Document_Number | 337 | 0 | 0 |  |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | Shipping_Bill_No | 279 | 0 | 0 |  |

Confirm authoritative customer/item/product masters, code systems, document series and source scope before approving any join or business primary key.

## Numerical, quantity and financial investigation

[numerical_quality.csv](numerical_quality.csv) profiles 114 measure columns, including observed types, parse statuses, negative/zero/fractional counts, min/max, percentiles, mean/std and outer-IQR candidates. Raw strings remain unchanged. Diagnostic parsing recognizes explicit numeric strings, validated thousands grouping, currency wrappers, percentage signs and accounting parentheses, with the rule recorded. Unknown grouping, boolean measures and malformed text remain unevaluable; they are not replaced by zero. `Stock_Impact` is a flag. `Pricing unit` is profiled as categorical/unit metadata based on its observed encodings; its business meaning requires confirmation. Mixed-unit lead-time strings require unit confirmation and are not automatically called invalid quantities.

Negative values may be returns or adjustments, zeros may be genuine or cancelled lines, and fractional quantities may be valid under some UOMs. [Numerical context](numerical_context.csv) breaks signs, zeros and fractional values down by available transaction type, credit/debit indicator, status, UOM and inventory document prefix. Prefixes are diagnostic groupings, not approved document semantics. Statistical flags use all interpreted finite values and **Q1/Q3 ± 3 × IQR**; the rule is withheld where IQR is zero or there are fewer than eight values. Product/unit/price mix can explain extreme values. [Numerical token exceptions](numerical_token_issues.csv) preserve representation failures.

Provisional financial screening checks quantity × unit price, explicitly named line discounts, GST component amount versus taxable base × rate/100, and supported CSV line-total component arithmetic. A mismatch exceeds **max(1 monetary unit, 0.5% of the projected value)**. These tolerances are diagnostic parameters, not business-approved materiality or statutory rules. Rates are explicitly interpreted in percentage points for these checks. All operands must be present and interpretable; blanks are not substituted with zero. Document-level invoice/note totals are not summed or compared as if every repeated line were an independent document total.

| file | worksheet | check | evaluable_rows | unevaluable_rows | outside_tolerance_rows |
| --- | --- | --- | --- | --- | --- |
| Sales Order Report 2.xlsx | Sheet1 | quantity × unit price × (1-discount/100) versus Total (LC) | 100,280 | 0 | 1,021 |
| Sales Invoice Details 1.xlsx | Sheet1 | quantity × unit price versus taxable value | 100,181 | 2 | 941 |
| GSTR1_Credit_Debit_Note 2.csv | (CSV table) | quantity × unit price versus taxable value | 276 | 0 | 118 |
| GSTR1_Invoice.csv | (CSV table) | taxable value + GST/CESS components + non-GST taxes versus line total | 337 | 0 | 40 |
| Sales Order Report 1.xlsx | Sheet1 | quantity × unit price × (1-discount/100) versus Total (LC) | 1,098 | 0 | 36 |
| GSTR1_Invoice.csv | (CSV table) | IGST taxable value × rate/100 versus amount | 337 | 0 | 22 |
| Sales Invoice Details.xlsx | Sheet1 | IGST taxable value × rate/100 versus amount | 337 | 0 | 22 |
| GSTR1_Invoice.csv | (CSV table) | quantity × unit price versus taxable value | 337 | 0 | 14 |
| Sales Invoice Details.xlsx | Sheet1 | quantity × unit price versus taxable value | 337 | 0 | 14 |
| GSTR1_Invoice.csv | (CSV table) | SGST taxable value × rate/100 versus amount | 337 | 0 | 11 |
| GSTR1_Invoice.csv | (CSV table) | CGST taxable value × rate/100 versus amount | 337 | 0 | 11 |
| Sales Invoice Details.xlsx | Sheet1 | SGST taxable value × rate/100 versus amount | 337 | 0 | 11 |
| Sales Invoice Details.xlsx | Sheet1 | CGST taxable value × rate/100 versus amount | 337 | 0 | 11 |
| Sales Invoice Details 1.xlsx | Sheet1 | CGST taxable value × rate/100 versus amount | 100,183 | 0 | 3 |
| Sales Invoice Details 1.xlsx | Sheet1 | SGST taxable value × rate/100 versus amount | 100,183 | 0 | 3 |
| Sales Invoice Details 1.xlsx | Sheet1 | IGST taxable value × rate/100 versus amount | 100,183 | 0 | 1 |

Every supported check, its inputs, eligibility, assumptions, tolerance and examples appears in [financial_consistency.csv](financial_consistency.csv). Discounts, freight, pack/pricing units, rounding, document grain, currency and credit/debit sign conventions must be confirmed before interpreting mismatches as accounting errors. This is arithmetic screening, not a determination of GST legal compliance.

## Categories, spelling and representation

[categorical_consistency.csv](categorical_consistency.csv) profiles string-bearing columns for outer/internal spaces, case variants and diagnostic Unicode/spacing/case collisions. Original values remain separate. The raw-to-proposed representation evidence is in [categorical_variants.csv](categorical_variants.csv); it is not an approved mapping.

Potential spelling pairs are restricted to small category domains, exclude codes/entity names/descriptions/free-text reasons and values containing digits, and use a stated text-similarity threshold of 0.84. [spelling_candidates.csv](spelling_candidates.csv) lists review candidates; resemblance does not establish a typo. [categorical_values.csv](categorical_values.csv) records observed category levels and types. [Flag encoding representations](flag_encoding_representations.csv) separates yes/no, Y/N, boolean, numeric and text encodings without assuming equivalence. The proposed Active/Inactive binary encodings are screened separately; an approved business catalogue is still needed to determine which other category values are invalid or unexpected. No observed-value set is silently treated as an approved domain.

## Dataset-specific findings and confirmation requests

- `PCT_NOPJ` has a blank first-column header but actual data in all 33 rows (`NOPJ`). `PTC_NOPI` provides surrounding agency context; the unnamed column remains positional pending owner confirmation.
- Both exchange-rate sheets and the reference customer table carry explicit synthetic-data markers. Their intended role and whether other sources are synthetic require confirmation; file names and example-looking records alone do not establish authenticity or authority.
- Reference `Customer Code` and `BP_CODE` differ in completeness and code systems. They remain separate candidates.
- Sparse inventory item labels may be group-level context. Forward filling or declaring those blank cells erroneous requires report-layout confirmation.
- Repeated document totals and transaction identifiers need verified document/line grain and source precedence before any aggregation or deduplication.

See [dataset_specific.csv](dataset_specific.csv), the full issue register, and the original inventory validation report for context.

## Priority review queue

The following is an excerpt; the complete register is authoritative. Review priority does not certify that every flagged pattern is erroneous.

| issue_id | severity | source_file | worksheet | affected_column | rule | affected_records |
| --- | --- | --- | --- | --- | --- | --- |
| DQ-0160 | High | Inventory Audit Report as on 200327.xlsx | Sheet1 |  Item No.  | Excessive blank values (>=50% of nonempty rows) | 103,114 |
| DQ-0163 | High | Inventory Audit Report as on 200327.xlsx | Sheet1 | Description | Excessive blank values (>=50% of nonempty rows) | 103,114 |
| DQ-0392 | High | Sales Order Report 2.xlsx | Sheet1 | BP Catalog No | Excessive blank values (>=50% of nonempty rows) | 100,280 |
| DQ-0393 | High | Sales Order Report 2.xlsx | Sheet1 | BP Catalog No | Blank candidate entity/document reference on nonempty rows | 100,280 |
| DQ-0416 | High | Sales Order Report 2.xlsx | Sheet1 |  Customer Code  | Unmatched values against candidate master: Customer Master Report 1.xlsx | 99,667 |
| DQ-0420 | High | Sales Order Report 2.xlsx | Sheet1 | Item No | Unmatched values against candidate master: Item Master Lists 1.xlsx | 96,871 |
| DQ-0419 | High | Sales Invoice Details 1.xlsx | Sheet1 | Part Code SAP Code | Unmatched values against candidate master: Item Master Lists 1.xlsx | 96,847 |
| DQ-0269 | High | Sales Invoice Details 1.xlsx | Sheet1 | SO Date | Ambiguous day/month dates | 34,065 |
| DQ-0168 | High | Inventory Audit Report as on 200327.xlsx | Sheet1 | Posting Date | Ambiguous day/month dates | 33,850 |
| DQ-0278 | High | Sales Invoice Details 1.xlsx | Sheet1 |  Invoice Date  | Ambiguous day/month dates | 33,782 |
| DQ-0164 | High | Inventory Audit Report as on 200327.xlsx | Sheet1 | System Date | Ambiguous day/month dates | 33,743 |
| DQ-0380 | High | Sales Order Report 2.xlsx | Sheet1 | Posting Date   | Ambiguous day/month dates | 33,242 |
| DQ-0384 | High | Sales Order Report 2.xlsx | Sheet1 | Delivery Date | Ambiguous day/month dates | 31,699 |
| DQ-0293 | High | Sales Invoice Details 1.xlsx | Sheet1 | Item Foreign Code | Blank candidate entity/document reference on nonempty rows | 30,691 |
| DQ-0418 | High | Sales Order Report 2.xlsx | Sheet1 |  Customer Code  | Unmatched values against candidate master: Customer Master Report 2.xlsx | 9,756 |
| DQ-0424 | High | Sales Order Report 2.xlsx | Sheet1 | Item No | Unmatched values against candidate master: Item Master Lists 2.xlsx | 8,953 |
| DQ-0421 | High | Sales Invoice Details 1.xlsx | Sheet1 | Part Code SAP Code | Unmatched values against candidate master: Item Master Lists 2.xlsx | 8,869 |
| DQ-0040 | High | Customer Master Report 2.xlsx | Sheet1 | STREET NO. | Excessive blank values (>=50% of nonempty rows) | 5,012 |
| DQ-0043 | High | Customer Master Report 2.xlsx | Sheet1 | ACCOUNT NO. | Excessive blank values (>=50% of nonempty rows) | 5,012 |
| DQ-0046 | High | Customer Master Report 2.xlsx | Sheet1 | SWIFT CODE / IFS CODE | Excessive blank values (>=50% of nonempty rows) | 5,012 |

## Recommended next steps, pending approval

1. Obtain source provenance/version precedence and confirm the forecasting use of synthetic/reference data.
2. Approve date format, century, serial-date and monthly-period rules; obtain corrected source evidence for impossible dates.
3. Confirm requiredness, conditional applicability, business grain, stable identifiers and reference/master mappings.
4. Review duplicate groups and financial exceptions with document, UOM, pricing, tax and accounting context.
5. Approve explicit raw-to-canonical category/numeric policies and a documented exception workflow before applying any cleaning.

Data preparation requires review and approval. No source corrections or modeling steps have been applied.

## Execution and validation

The assessment validates all 20 table extents, 135 identifier metrics and 37 date-field metrics against inventory, including the three headline date counts. All 17 source hashes and all 23 inventory artifact hashes are checked. [assessment_validation.json](assessment_validation.json) records scope, settings and export checks; [export_validation.csv](export_validation.csv) records CSV/Excel read-back verification. Detailed CSVs are complete; the [Excel evidence workbook](data_quality_evidence.xlsx) contains complete aggregate tables, with detailed row/token evidence explicitly kept in CSVs.

Notebook: [02_data_quality_analysis.ipynb](../../notebooks/02_data_quality_analysis.ipynb). Reusable implementation: [assess_data_quality.py](../../src/data/assess_data_quality.py).

```powershell
.\.venv\Scripts\python.exe src\data\assess_data_quality.py
```

All reports contain source-derived business information and should follow the dataset's handling rules.

Repository maintenance: descriptive artifact names and references were updated after assessment execution. Analysis values and findings were retained. `inventory_integrity.csv` stores the original assessment digests separately from current metadata baselines, and `notebook_execution_validation.json` retains original execution hashes alongside current file hashes. Naming, links, code syntax/imports, notebook cells and CSV/Excel consistency were revalidated without rerunning the data assessment.
