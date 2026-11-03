# NOP actual-data exploratory assumptions and unresolved decisions

**Status:** Exploratory data and models only; no business or production approval is implied.

## Verified source facts

- Source: `dataset/Sales Invoice Details.xlsx`, first worksheet. The source hash is recorded in the generated dataset provenance.
- 337 detail rows contain `TransType = GST Tax Invoice`.
- There are 234 distinct nonblank `Invoice Num` values. Repeated detail rows for each reference have a consistent raw `Invoice Date` string in this extract.
- All invoice-date cells are text. The observed format is slash separated. Rows with a first component greater than 12 can be interpreted unambiguously as day/month/year; rows with a first component of 12 or less are not parsed.
- A fresh raw-cell count found 217 rows with unambiguous dates and 120 ambiguous date cells; it found no blank date cells. This differs from the earlier readiness report's count of 107 ambiguous cells, so the source-level count in this report supersedes that prior summary for this workbook and should be reconciled in the evidence report. After requiring every detail row for a reference to have one same unambiguous date, 152 distinct references remain; 82 references have no fully resolved date.
- The retained documents span 21 December 2025 through 13 September 2026. Ten months have observed confirmed-date documents. December 2025 and September 2026 are partial calendar boundaries. January through August have calendar-month boundaries in the available file, but source extraction completeness is not independently established.

## Explicit assumptions for the exploratory run

1. The exact `Invoice Num` string is the document identity within this one workbook. Its visible series/year tokens and consistency across detail rows support this technical grouping, but the issuer and identity scope are not business-approved.
2. The target is **the number of distinct invoice references in this workbook with a fully consistent, unambiguously day-first date, by calendar month**. It is a confirmed-date subset count, not total invoice volume.
3. All rows in the workbook are included as supplied because the observed `TransType` is uniformly `GST Tax Invoice`. The extract does not establish whether source-side cancellations, voids, or omitted events exist.
4. Ambiguous date documents are excluded from the target. They are not assigned a date, removed from the original data, imputed, or converted to zero. Their counts and included source rows are recorded in provenance.
5. The eight interior calendar months January–August 2026 are eligible for the small exploratory model comparison. December and September are retained in the prepared dataset but excluded from model evaluation because the observed date span starts and ends inside those months.
6. A single chronological time index is the only model feature. No seasonal pattern or lag feature is inferred from ten observed months.

## Unresolved business and data decisions

- Authoritative source owner, extract watermark, reporting cut-off, and whether every period is complete.
- Confirmed issuer/series/year identity scope and whether reference strings remain unique across source exports.
- Lifecycle treatment for canceled, voided, returned, amended, or otherwise excluded documents.
- Business-approved date grammar and resolution of the 120 ambiguous cells.
- Whether the confirmed-date subset is representative enough to forecast any operational volume. The distribution of unresolved documents by month is unknowable from the unresolved dates.
- Forecast horizon, cadence, acceptance criteria, and permitted business use.
- Authenticated semantic, target, preparation, execution, and publication approvals for controlled use.

These assumptions authorize only the exploratory analysis requested for this task. They do not replace existing approval records or make the output suitable for operational decisions.
