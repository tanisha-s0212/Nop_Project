# Dataset inventory validation

Review date: 2026-10-30. Project: `D:\Aroha_Files\NOP_Project`.

## Assessment

The inventory is sufficiently reliable to begin data quality assessment **as a source and structure inventory**, subject to approval. All sources are accounted for, and the original Excel report counts and samples agree with the source files. Date interpretation, business keys, source precedence, and several field meanings still require confirmation. These findings should be carried into the Data Quality Assessment; forecasting readiness has not been established.

All 17 source files remained unchanged during this audit, verified using SHA-256, file size, and modification time. The 14 Excel hashes also match the hashes saved during the initial inventory. No sources were cleaned, merged, rewritten, or recalculated. This report records the inventory review preceding the data quality assessment.

## 1. Dataset completeness

A recursive scan, including hidden filenames, found **17 files: 14 `.xlsx` workbooks and 3 `.csv` files**. There are no `.xls`, `.xlsm`, or other-format files in the dataset directory at review time.

The initial notebook discovered 14 workbooks because its discovery filter accepted only `.xlsx`, `.xls`, and `.xlsm`. Thirteen workbooks each contain one worksheet; `Sales_Order_Data_202609.xlsx` contains four. Therefore, **13 + 4 = 17 Excel worksheets**. CSV files are tables, not Excel workbooks or worksheets.

The following census lists every file and table. Rows below the header include completely blank rows. Excel scanned rows also include title, metadata, and header rows. CSV row numbers refer to logical CSV records, with the header counted as record 1. These counts describe source layout, not confirmed business transaction counts.

| File | Worksheet/table | Header row | Rows below header | Columns |
|---|---|---:|---:|---:|
| Customer Master Report 1.xlsx | Sheet1 | 1 | 40 | 35 |
| Customer Master Report 2.xlsx | Sheet1 | 1 | 5,015 | 35 |
| Exchange Rate 1.xlsx | INR to JPY | 4 | 7 | 7 |
| Exchange Rate.xlsx | INR to JPY | 4 | 22 | 7 |
| GSTR1_Credit_Debit_Note 1.csv | CSV table | 1 | 6 | 64 |
| GSTR1_Credit_Debit_Note 2.csv | CSV table | 1 | 279 | 64 |
| GSTR1_Invoice.csv | CSV table | 1 | 337 | 68 |
| Inventory Audit Report as on 200327.xlsx | Sheet1 | 1 | 108,129 | 13 |
| Inventory Audit Report as on 200926 1.xlsx | Sheet1 | 1 | 162 | 13 |
| Inventory Audit Report as on 200926.xlsx | Sheet1 | 1 | 162 | 13 |
| Item Master Lists 1.xlsx | Item Lists | 1 | 150 | 19 |
| Item Master Lists 2.xlsx | Item Lists | 1 | 5,015 | 19 |
| Sales Invoice Details 1.xlsx | Sheet1 | 1 | 100,188 | 43 |
| Sales Invoice Details.xlsx | Sheet1 | 1 | 337 | 43 |
| Sales Order Report 1.xlsx | Sheet1 | 1 | 1,098 | 26 |
| Sales Order Report 2.xlsx | Sheet1 | 1 | 100,286 | 26 |
| Sales_Order_Data_202609.xlsx | Customer list | 3 | 43 | 4 |
| Sales_Order_Data_202609.xlsx | Country master | 3 | 11 | 5 |
| Sales_Order_Data_202609.xlsx | PTC_NOPI | 5 | 60 | 8 |
| Sales_Order_Data_202609.xlsx | PCT_NOPJ | 5 | 33 | 9 |

The complete scope is **20 tables and 521 worksheet/table columns**: 17 Excel worksheets with 325 columns, plus 3 CSV tables with 196 columns. Excel contains 320,758 rows below the selected headers, including 22 empty rows; CSV contains 622 rows below headers, including 3 empty rows.

### Relevance of the remaining CSV files

- `GSTR1_Invoice.csv` contains invoice dates and numbers, customer and item details, quantities, taxable amounts, GST rates/amounts, invoice values, and shipping/billing fields.
- `GSTR1_Credit_Debit_Note 1.csv` and `GSTR1_Credit_Debit_Note 2.csv` contain credit/debit note dates and numbers, invoice references, items, quantities, tax amounts, and note values/reasons.
- All three decode as UTF-8 and parse using comma-delimited CSV with quoted fields. No nonempty records have an inconsistent field count. The 279 rows in the second credit/debit file include 3 completely empty rows, leaving 276 nonempty rows.

These are relevant business sources and are included in this audit. Their earlier exclusion was a documented Excel-only scope limitation, not a relevance decision. No potentially relevant file remains excluded from the review. File suffixes such as `1` and `2` do not establish that sources are replacements, duplicates, or authoritative versions.

Evidence: [source manifest and hashes](validation/source_completeness.csv), [table counts](validation/table_counts.csv), [all column metadata](validation/column_validation.csv).

## 2. Header validation

The table above records the reviewed header row for every worksheet and CSV table. The source header values, preamble, and first data rows agree with the selected headers. No header-row corrections to the final saved inventory notebook were required by this audit.

- Both exchange-rate sheets have a title and instructions above a single table header at row 4. Row 1 is not the table header.
- The customer and country reference tables in `Sales_Order_Data_202609.xlsx` use row 3 as the table header. Both product reference tables use row 5. Product-sheet update metadata at cell B3 contains `2026-09-01`; it is preamble metadata, not a date attached to every product record.
- The other 11 Excel worksheets use row 1 as the table header.
- No merged cell ranges or convincing multi-row table headers were found in any of the 17 Excel worksheets. All 17 worksheets are visible. Header comparison found no duplicate labels after ignoring label case, surrounding whitespace, and punctuation for comparison only.
- **Manual confirmation required:** `PCT_NOPJ!A5` is blank, while A6:A38 contains `NOPJ`. The inventory retains `<blank column 1>`. The neighboring `PTC_NOPI` sheet has a `Sales agency` column, but that does not authorize assigning the same meaning here.
- Seven worksheet XML files lack a declared dimension. Streaming the actual rows/cells and checking XML extents reproduced the saved row and column counts. A missing dimension did not cause a worksheet to be skipped.
- The inventory audit sheets have a grouped-looking layout with sparse item numbers and descriptions, including `Opening Balance` text. A blank item number on a transaction row may reflect report layout. Whether a group value applies to subsequent rows needs business confirmation; no fill-down was applied.

Original header whitespace and misspellings, including `Date of Udate`, remain represented in the metadata. Header label comparison did not rename source fields.

Evidence: [every header, blank-header position, merged-range check, and first ten rows](validation/header_validation.csv).

## 3. Date validation

All 22 originally identified Excel date/period columns were rechecked across every row. The CSV review adds 15 date/period fields, including empty optional date columns, for **37 fields** in total.

The original minimum and maximum dates are reproducible under the notebook's documented parser. Reproducing that parser does not establish the intended business date format. The reviewed date evidence therefore separates unambiguous values, alternative day/month readings, month periods, possible serial dates, and failures.

### Observed interpretations

The following totals count field values; the same source row can contribute more than one date-field value.

| Result | Nonblank field values | Interpretation |
|---|---:|---|
| Native Excel dates/datetimes | 15,126 | Calendar date is encoded as an Excel date |
| Explicit year-month-day text | 14,843 | Year-first syntax fixes the field order |
| Numeric text that only permits DMY | 339,036 | A day greater than 12 rules out MDY |
| Same date under DMY and MDY | 18,900 | Day and month are equal |
| Ambiguous DMY/MDY text | 203,455 | Two different calendar dates remain possible |
| Month/year periods | 29 | Periods, not exact day-level observations |
| Numeric values that may be Excel serial dates | 14,949 | Retained as numeric; possible dates are diagnostic alternatives only |
| Revision month numbers without a year | 282 | Month-like attributes, not complete dates |
| Impossible calendar dates | 28 | Calendar parsing fails under both orders |
| Other unresolved text | 11 | `NA`, `#N/A`, or `-` in delivery-date fields |

There are 387,905 values with an unambiguous calendar reading under the documented rules, 29 month periods, 203,455 ambiguous day/month values, and 15,270 values without an accepted complete date. A calendar reading is not proof that the business value itself is correct.

### Format ambiguity and parsing failures

- A value such as `10/09/26` permits 10 September 2026 or 9 October 2026. The previous parser selected day-first. The audited evidence stores both alternatives and does not silently choose one.
- Values with a day greater than 12 provide strong evidence that DMY is used in these exports. No audited numeric date text uniquely required MDY. This supports, but does not prove, a DMY rule for every ambiguous value or every source version. The source owner should confirm formats per file and column.
- Two-digit years use the explicitly reported conventional pivot (00–68 maps to 2000–2068; 69–99 to 1969–1999) only to describe candidate dates. The intended century still needs confirmation. Native Excel dates already encode a full year.
- All 14,949 unclassified numeric date-field values fall in a plausible Excel serial range. The evidence supplies candidate dates using the relevant workbook's epoch, but excludes those candidates from accepted date coverage until their meaning is confirmed. Their omission makes the initial coverage incomplete; they are neither business zeros nor automatically missing dates.
- **Correction:** `Exchange Rate 1.xlsx!A11` contains the valid month period `2027-03`. The initial parser did not recognize it, so its reported `Rate Month` maximum stopped at February 2027. The reviewed period coverage includes March 2027, represented by March 1 solely for display. Other `Rate Month` periods also use day 1 as a display convention.
- CSV `Revision_Month` values such as `1`, `3`, and `12` lack a year. They are reported as incomplete period attributes, rather than being labeled impossible dates or assigned an inferred year.

The impossible calendar values are fully enumerated below. The detailed token report gives occurrence counts and the first five source row locations for each distinct problem value.

| File | Column | Raw value | Occurrences |
|---|---|---|---:|
| Inventory Audit Report as on 200327.xlsx | System Date | `31/02/27` | 8 |
| Item Master Lists 2.xlsx | Date of Udate | `31/02/26` | 5 |
| Sales Order Report 2.xlsx | Delivery Date | `31/02/27` | 15 |

The original blanket date-range statement should therefore be read as conditional on the original parsing assumptions. Future delivery dates, including those beyond the review date, require confirmation of business meaning and format. Use the audited per-column unambiguous ranges and possible bounds instead of treating the original date chart as verified coverage.

Evidence: [reviewed date coverage and per-column totals](validation/date_validation.csv), [5,611 distinct issue/confirmation tokens with counts and locations](validation/date_token_issues.csv). The token report includes ambiguous values, two-digit-year values, numeric serial candidates, and parsing failures; 5,611 is not a count of failed source rows.

## 4. Identifier validation

**135 candidate/previously flagged columns were assessed across their entire tables**, including all 90 candidates from the initial report. Exact observed values were counted using full-column counters, rather than sampled hashes. Text case and whitespace were preserved; numeric equality treats an integer and the equivalent floating-point number as the same numeric value. Empty and whitespace-only values are reported separately.

Every candidate has counts of nulls, nulls on nonempty rows, nonblank values, distinct values, duplicate groups, duplicate excess rows, and rows participating in duplicates. Duplicate excess means nonblank count minus distinct count. Entirely empty rows are included in the total null count and identified separately.

| File / field | Rows below header | Blank/null rows | Distinct nonblank values | Duplicate excess rows |
|---|---:|---:|---:|---:|
| Customer Master Report 1 / CUSTOMER CODE | 40 | 0 | 40 | 0 |
| Customer Master Report 2 / CUSTOMER CODE | 5,015 | 3 | 4,997 | 15 |
| Item Master Lists 1 / Item No. | 150 | 0 | 150 | 0 |
| Item Master Lists 2 / Item No. | 5,015 | 3 | 5,000 | 12 |
| Sales Invoice Details 1 / Invoice Num | 100,188 | 5 | 35,683 | 64,500 |
| Sales Order Report 2 / SO No | 100,286 | 6 | 32,234 | 68,046 |
| Reference Customer list / Customer Code | 43 | 40 | 3 | 0 |
| Reference Customer list / BP_CODE | 43 | 6 | 37 | 0 |

The three blanks in each larger master are entirely empty rows; their code fields have no additional blanks on nonempty rows. Repeated document numbers can legitimately occur on line-level exports. These duplicate counts do not establish that business records should be deleted.

### Meaning and primary-key status

- `#` and `S.No` are row ordinals. Uniqueness does not establish a business key.
- Rates, dates, amounts, descriptions, names, and contact information can happen to be unique. HSN/SAC codes, postal codes, state/port codes, and product classification codes describe attributes or categories. They are not thereby row identifiers.
- Of the original 90 flags, 56 were classified as row ordinals, classification/contact/tax attributes, date/period attributes, or measures/descriptions rather than entity/document references. This corrects the interpretation of sampled uniqueness; it does not remove those fields from the inventory.
- Examples of complete, unique, semantically plausible candidates are the customer code in the small customer master, item number in the small item master, country code in the country reference, and product codes in both product reference sheets. They still need business confirmation of scope and stability.
- `Customer Code` in the reference customer sheet is populated in only the first three records with values 50001–50003, while `BP_CODE` uses C-prefixed strings and is populated in 37 records. Their meanings must be confirmed separately.
- Inventory item numbers are sparse: the large inventory audit has 5,010 populated item numbers and 103,119 blank item-number positions across 108,129 rows. The grouped report layout prevents treating item number as a complete row key.

**No business primary key has been declared confirmed.** Full-column uniqueness is a necessary diagnostic, not sufficient evidence of identity, grain, or validity across files.

### Candidate matching coverage

101 comparisons quantify full-column value overlap among label-based customer, item, product/foreign-code, invoice-number, sales-order-number, and customer-reference candidates. These are exploratory comparisons, not confirmed relationships or source joins. Matching preserves observed text case and whitespace. Nulls are excluded from the match denominator and separately counted in the identifier report.

| Candidate comparison | Result |
|---|---|
| Small customer master ↔ Sales Order Report 1 customer codes | 40 of 40 distinct codes overlap on both sides |
| Larger customer master ↔ Sales Order Report 2 customer codes | 4,129 shared codes; 60.765% of the order file's 6,795 distinct codes match the master's observed values |
| Small item master ↔ Sales Order Report 1 item numbers | All 120 distinct nonblank order item numbers occur among the master's 150 numbers |
| Reference BP_CODE ↔ small customer master | All 37 distinct nonblank BP codes occur in the master; the reference field also has 6 nulls |
| Reference Customer Code ↔ small customer master | No exact overlap: numeric reference codes and C-prefixed master strings differ |

Differences in versions, formatting, code systems, and scope can affect overlap. The audit does not select a master, normalize identifiers, infer missing links, or establish a prediction target.

Evidence: [full-column identifier checks](validation/identifier_validation.csv), [candidate matching coverage with both-direction distinct and row counts](validation/identifier_matching_coverage.csv).

## 5. Formula and cache validation

Every worksheet XML was scanned for formula cells, including shared formula elements and serialized cached values. **There are zero stored worksheet formula cells across all 14 workbooks and 17 worksheets.** Thus no missing, erroneous, or stale worksheet formula caches were identified; cache availability and freshness are not applicable to the current files.

Workbook calculation metadata requests a full calculation on load, but that flag alone does not prove stale values, particularly when there are no worksheet formulas. Values exported as constants cannot be checked for business freshness by inspecting formula caches. No recalculation or zero substitution was performed.

Evidence: [formula, cache, dimension, and calculation metadata checks for all worksheets](validation/formula_validation.csv). Empty finding tables explicitly say `No findings`.

## 6. Report consistency and corrections

**1,917 comparison checks passed with zero mismatches.** They cover:

- 14 workbook records and 17 worksheet records against discovery.
- Scanned worksheet rows/columns against source data and independent worksheet XML extents, including missing declared dimensions.
- Rows below headers, blank rows/columns, and missing-cell totals.
- All 325 original Excel column labels, nonblank/missing counts, observed type counts, and empty-column flags.
- All 170 original sample records: the first and last five nonempty rows per worksheet, including source row positions and values in column order.
- All 22 original date/period fields' parsed counts and min/max values reproduced under the original parser. This is a computational consistency check, not confirmation of the parser's business assumptions.

The initial deliverables consisted of five Excel reports and two PNG charts; no original generated CSV reports existed to compare. The audit adds CSV evidence and one consolidated Excel evidence workbook. All 12 evidence tables were read back from both formats and checked against the audit records. Text, whitespace, leading zeros, and literal error-like tokens are preserved; numeric cells allow equivalent numeric serialization.

One export discrepancy was caught and fixed: the literal `#N/A` in the audit token report was initially stored as an Excel error cell and was read back as missing by pandas. It is now stored as text, and the export writer explicitly preserves error-like and formula-like audit literals as text. All CSV/Excel export content checks now pass.

### Corrections and additions

1. Added all three relevant CSV sources to the reviewed scope, with their counts, metadata, dates, and identifiers.
2. Separated ambiguous day/month values from unambiguous dates and exposed parsing failures, serial-date candidates, missing-year month numbers, and century assumptions.
3. Recognized the previously omitted `2027-03` period and documented first-day display conventions for month periods.
4. Replaced sampled identifier interpretation with full-column counts, semantic roles, and explicit unconfirmed-key status.
5. Quantified candidate cross-source code matching without joining sources.
6. Identified the unnamed `PCT_NOPJ` field, grouped inventory layout, source-version uncertainty, and product update metadata.
7. Verified formula absence and corrected the audit workbook's literal-text export behavior.
8. Added a visible validation notice to the inventory notebook. Its original code and saved outputs, and the original five Excel reports and two charts, are retained for traceability. The audited evidence supersedes unconditional interpretations of their date ranges and identifier flags. Rerunning the original notebook alone still produces the original exploratory outputs; rerun the audit afterward.

No row-count, column-count, missing-count, type-count, header-row, or sample-value correction to the original Excel reports was required.

Evidence: [all original-report comparisons](validation/report_consistency.csv), [CSV/Excel export verification](validation/export_verification.csv), [machine-readable audit summary](validation/audit_summary.json).

## 7. Outstanding confirmations and data quality assessment recommendation

Business/source-owner confirmation is required for:

1. Which source versions and snapshots are authoritative, and whether the explicitly synthetic reference workbook is appropriate for the intended project.
2. Date formats and century conventions per source/column; whether numeric date-field values are Excel serial dates; the year/context for revision month numbers; and the meaning of future delivery dates.
3. The missing `PCT_NOPJ` first-column header, the distinction between reference `Customer Code` and `BP_CODE`, and the grouped inventory layout.
4. Transaction grain and stable keys, including document-series scope and legitimate repeated document/item references.
5. Which candidate code comparisons represent real relationships, and how unmatched values should be investigated.

These uncertainties are documented rather than silently resolved. The source census and structural inventory are dependable enough to scope data quality assessment over **all 17 files / 20 tables**, while treating dates, keys, source versions, and business relationships as open findings. No claim of perfect accuracy is made. See the data quality report for the subsequent assessment.

## Deliverables and reproducibility

- [Consolidated validation evidence workbook](validation/inventory_validation_evidence.xlsx), with matching CSV tables in `validation/`.
- [Audit summary](validation/audit_summary.json), [read-failure log](validation/validation_failures.csv), and [export verification](validation/export_verification.csv).
- [Reusable read-only audit script](../../src/data/validate_inventory.py).
- [Inventory notebook with validation notice](../../notebooks/01_data_inventory.ipynb).

From the project root, evidence can be regenerated using:

```powershell
.\.venv\Scripts\python.exe src\data\validate_inventory.py
```

The script reads all source files, compares the saved initial inventory reports, and writes only audit evidence under `reports/data_inventory/validation/`. This Markdown report records the reviewed findings above and should be revisited if sources or interpretation rules change. Source examples and evidence contain business information and should follow the same handling rules as the dataset.
