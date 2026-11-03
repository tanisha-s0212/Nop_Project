# Business prediction framework foundation

Implemented baseline: **2 November 2026**, package version **0.1.0**. This implements the first bounded discovery and metadata foundation of the [proposed architecture](../architecture/business_prediction_framework_architecture.md). The architecture document remains an unchanged design baseline; this document and README record the newly implemented scope.

## Implemented scope

| Component | Implemented behavior | Boundary |
| --- | --- | --- |
| Contract management | Explicit version registration, required/nested field and type checks, JSON compatibility, exact references, timestamps, cross-field consistency and structured errors | Two foundation contract types ship; other architecture contracts remain proposed. This is a small validator, not a full JSON Schema implementation |
| Source abstraction | `DataSourceAdapter` / `SourceSnapshot` read-only interfaces; in-memory, CSV and modern Excel adapters | No database, directory crawler, network connection or infrastructure. Adapters inspect only explicitly supplied sources |
| Schema discovery | Enumerate tables/worksheets, retain raw headers and positions, detect blank/duplicate headers, profile observed types/missingness and structure, identify temporal/uniqueness hypotheses and compare observed schemas | No business meaning, key, relationship, target or treatment is approved or selected |
| Metadata/evidence catalogue | Immutable versioned JSON documents, exact reference resolution, observation/evidence records, unordered atomic bundle insertion, defensive reads, exclusive JSON export/load | In-process development catalogue, not a concurrent production registry, model registry or approval authority |
| Diagnostics | Structured exceptions and library logging events without source-cell samples | No root logging configuration, log-file writes or production monitoring service |

This partly realizes architecture C01/C02 and their technical contract/evidence foundation. It does not implement C03 business approval, C04 target discovery, C05 feasibility planning, preparation, features, training, evaluation, model management, inference, LLM/MCP or UI components. `SourceConfig` owner/purpose labels are metadata supplied by the caller, **not verified authorization or business approvals**. Callers remain responsible for permission to inspect a source.

No business question list, scenario catalogue, question routing or fixed business field mapping exists. Source names, table names, layouts and headers come from adapters/configuration. Existing NOP-specific assessment implementations were inspected but not imported or modified: they contain source-specific assumptions, heavy analysis imports and report-writing workflows. Their typed-value, raw-preservation, full-count and integrity-check principles informed these independent components.

## Repository additions

```text
src/business_prediction/
    __init__.py
    errors.py
    contracts.py
    metadata.py
    discovery.py
    catalogue.py
    adapters/
        __init__.py
        base.py
        memory.py
        csv.py
        excel.py
tests/
    __init__.py
    support.py
    test_contracts.py
    test_discovery.py
    test_catalogue.py
docs/development/foundation.md
```

The [existing requirements](../../requirements.txt) are unchanged. Core contracts, CSV, in-memory discovery, logging, JSON persistence and tests use the standard library. The Excel adapter uses the already installed `openpyxl`; it is imported explicitly from its own module. No server, database, test framework or additional package is required.

## Running the tests

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -t . -v
```

The package currently uses the repository's `src` path; no editable installation or packaging infrastructure is introduced. `-B` avoids bytecode writes. Tests create only synthetic in-memory tables and temporary CSV/Excel/JSON files; they do not access the NOP datasets or rerun existing notebooks/report generators.

## Public interfaces

### Read-only adapters

[Adapter interfaces](../../src/business_prediction/adapters/base.py):

- `SourceConfig(source_id, owner_reference, purpose_scope)` records technical source identity and declared scope; all three must be nonempty strings.
- `DataSourceAdapter.source_id` identifies the source. `open_snapshot()` returns a context manager implementing `SourceSnapshot`.
- `SourceSnapshot.metadata()` returns source identity/version, reader settings, owner/purpose labels, adapter kind, locator and consistency description. `tables()` returns physical descriptors and captured rows; `iter_rows(table_id)` exposes immutable row records. `verify_unchanged()` checks source integrity as supported by the adapter.
- `RawField.position` is one-based; raw headers and header presence remain independent. `RawRow.position` is the worksheet row number or logical CSV record ordinal, not a business identifier. Quoted multiline CSV records are not treated as multiple observations.

[MemoryAdapter](../../src/business_prediction/adapters/memory.py) captures supported scalar values immutably and fingerprints the complete supplied table content, including preambles. `MemoryTable(name, rows, header_row=1)` contains the raw rows, including its header. Mutable nested cell objects are unsupported.

[CSVAdapter](../../src/business_prediction/adapters/csv.py) accepts a file path, source configuration, explicit encoding/delimiter and a header row. It uses strict parsing and does not infer a dialect. Cells remain text: `001`, `NA` and `#N/A` are not converted into numbers or missing values. Blank records and ragged rows are retained. Extra data columns without corresponding header tokens receive technical positions, not invented names.

[ExcelAdapter](../../src/business_prediction/adapters/excel.py) accepts `.xlsx` and `.xlsm` files, enumerates every worksheet, and accepts `header_rows={worksheet_name: row_or_none}` plus `default_header_row`. `None` means headerless. Unknown worksheet configurations fail. It opens captured bytes with `read_only=True`, `data_only=False`, `keep_links=False` and never saves the workbook. Formula expressions and error cells retain distinct wrappers; formulas, macros and external links are not executed. Cached formula values/freshness are not assessed. The reader exposes formatted Excel dates as native Python temporal values; raw numeric values are never guessed to be serial dates. Reader version and settings are recorded.

CSV and Excel snapshot versions hash the captured original bytes. Exit checks compare the on-disk hash before any discovery bundle is returned. A changed/missing source causes `source_changed`; this detects a mismatch at validation time, not every possible intermediate change. Source hashes prove content identity, not business authority, completeness or authenticity.

Resource settings default to 64 MiB captured file bytes, one million cells and, for Excel, 128 MiB uncompressed archive content. These are configurable technical budgets, not business feasibility thresholds. Memory limits apply per table; Excel's cell-read budget also applies across the workbook. These implementations materialize bounded snapshots: they do not claim out-of-core/database scalability or transaction isolation. Future database adapters must define authorized read operations, consistency/watermarks, physical descriptors and iteration behavior through the same interface. No connection is created here.

### Discovery and observed schema changes

[Discovery API](../../src/business_prediction/discovery.py):

```python
from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
from business_prediction.catalogue import MetadataCatalogue
from business_prediction.contracts import reference
from business_prediction.discovery import discover
from business_prediction.metadata import foundation_registry

adapter = MemoryAdapter(
    SourceConfig('demo-source', 'demo-owner', 'foundation-check'),
    [MemoryTable('unfamiliar_table', (
        ('token', 'reading', 'opaque'),
        ('a', 1, '2026-11-01'),
        ('b', '2', '03/04/2026'),
    ))],
)
bundle = discover(adapter, source_revision=1, discovery_revision=1)
catalogue = MetadataCatalogue(foundation_registry())
bundle.publish(catalogue)
schema = catalogue.get(reference(bundle.discovery_result))
assert schema['tables'][0]['name'] == 'unfamiliar_table'
assert schema['approval_status'] == 'unreviewed'
```

This synthetic example demonstrates metadata discovery, not a business scenario, target, label or transformation. No source file is implicitly discovered or processed. For multiple sources, supply an adapter per authorized source; the backend has no fixed source count or schema list.

`discover(adapter, source_revision=1, discovery_revision=1, options=None)` returns `DiscoveryBundle(source_metadata, discovery_result)`. It validates the generated contracts and source link before returning. `publish(catalogue)` explicitly inserts both documents as one validated transaction. Callers must choose new object revisions for new accepted snapshots; old revisions cannot be replaced.

`DiscoveryOptions(max_rows=None, identifier_min_nonmissing=2)` controls profiling. A row limit takes a deterministic prefix, marks incomplete profiles as `prefix_sample` and records the denominator. It does not limit file capture/layout materialization. Zero-row samples are permitted and provide no identifier evidence. Full-profile uniqueness still does not establish a business key. Distinctness uses exact typed encodings: integer `1`, float `1.0` and text `1` are distinct technical observations, not approved equivalences.

Each physical field retains its raw typed header and ordinal. Blank and exactly duplicated headers are flagged without renaming/mangling. The configured header row is always `configured_unapproved`: default row 1 is a provisional layout configuration, not automatic validated header detection. Automatic multi-row-header interpretation, merged-region semantics and grouped-record context reconstruction are not implemented.

Observed field profiles distinguish native null, empty text, whitespace-only text and structurally absent cells in ragged rows. Zero is present. Literal placeholder-like text remains present; nonfinite numbers and formula/error cells are separately reported rather than silently missing. Counts are observations only; no imputation or deletion occurs.

Temporal detection examines values, never column names. It recognizes native date/datetime/time, strict ISO date/datetime/time text, year-month periods, and numeric DMY/MDY text. Four-digit-year DMY/MDY tokens retain ambiguous versus single-calendar-reading versus impossible classifications. Two-digit years remain century-unresolved unless the day/month is impossible under any applicable leap-year bound. Periods never become fabricated first-of-month days; numeric fields never become serial dates automatically. Other formats require future explicit syntax extensions. Partial min/max dates exclude ambiguous/century-dependent tokens and periods; even a syntactically unique reading is not an approved business format or complete history.

Identifier candidates are typed-uniqueness hypotheses with evidence and missingness context. Ordinary amounts, dates and ordinals can qualify technically; no identity is confirmed. Boolean, formula, error and nonfinite columns are excluded from this uniqueness hint. Numeric-text syntax is also only a representation hypothesis; leading zeros remain intact.

`compare_schemas(previous, current)` compares discoveries for the same source ID and returns unreviewed additions/removals, table/layout changes, field/header/position changes and observed-type changes. It does not rebind names or prove continuity across reordered tables/columns. Field/table IDs are positional technical locators within a schema version. `schema_version` fingerprints observed names, positions, header layout and type sets; row counts and ordinary value changes instead affect `source_version`. Sampling can change which types are observed: comparisons of different profiling scopes are not authoritative declarations of database schema changes. Completeness/policy remain available for caller review.

### Versioned contracts and structured errors

[Contract API](../../src/business_prediction/contracts.py) provides `ContractDefinition`, `FieldSpec`, `ContractRegistry.register()` and `validate()`. The shipped [metadata definitions](../../src/business_prediction/metadata.py) implement `DataSourceMetadata@1.0` and `SchemaDiscoveryResult@1.0`.

Common envelope fields include contract type/version, object ID/revision, timezone-aware creation timestamp, owner/purpose and optional JSON `extensions`. Discovery adds an exact source reference, source/schema fingerprints, profiling policy, table/field metadata, observation evidence, unapproved hypotheses and limitations. Full validation checks references, source version, schema digest, positional IDs, evidence locations, population counts and partial ranges. New technical contract types/versions register their own schemas/checks. No business-question catalogue is involved.

References pin **contract type, contract version, object ID and object revision**. There is no implicit latest resolution. `validate(document, resolver=...)` requires actual referenced revisions. `structural_only=True` deliberately checks shape only; it is not a readiness/approval certificate. The catalogue uses that mode only for staging and then fully validates the entire bundle before committing.

| Value state | Representation / policy |
| --- | --- |
| Missing | Key omitted; rejected when required |
| Null | Explicit JSON `null`; accepted only when the field is nullable |
| Unknown | `{"$state":"unknown","reason":"Not yet established."}`; accepted only for uncertainty-enabled fields |
| Unavailable | `{"$state":"unavailable","reason":"Required evidence cannot currently be obtained."}`; separate from null/unknown |
| Present | Actual declared value, including zero and false when types permit them |

`value_state(document, key)` classifies these representations; `uncertain(state, reason)` constructs supported uncertainty tags. Classification does not replace validation. No automatic conversion from omission to null, coercion of numeric text, boolean-as-integer acceptance or default business value is allowed. Unknown fields, invalid finite-JSON data and unsupported contract versions produce structured errors. Namespaced `extensions` contain inert JSON metadata, never approvals or executable operators.

[Errors](../../src/business_prediction/errors.py) expose `FrameworkError.code`, `.message` and `.to_dict()`. `ContractValidationError` adds issue `path`, `code` and safe explanation without invalid source-cell values. `SourceError` identifies unreadable/unsupported/changed/resource-limited sources. `CatalogueError` identifies absent references, immutable-revision conflicts and export failures. Invalid adapter configuration raises `ValueError`; contract documents and runtime source/catalogue failures use the structured exception families.

### Catalogue, evidence and logging

[MetadataCatalogue](../../src/business_prediction/catalogue.py) provides:

- `add(document)` / `add_many(documents)`: validate exact references and consistency, then commit all or none. Unordered source/discovery bundles work; duplicate revisions are rejected.
- `resolve(ref)` / `get(ref)`: return defensive copies, with `None` or a structured error for an absent exact revision.
- `get_evidence(discovery_ref, evidence_id)`: resolve evidence within a specific discovery revision. Evidence IDs alone are not global source identifiers.
- `export_documents()` / `save(path)` / `load(path, registry)`: portable versioned JSON metadata; export exclusively creates a new path and refuses to overwrite. This does not write or transform source data. Disk export is single-writer development persistence; interrupted writes can leave an invalid file which load rejects.

Observation records are `observed`; interpretation records are `hypothesized` and `unreviewed`. No API approves either. Caller assertions or metadata extension keys cannot grant business/execution permission. Registering a new technical contract definition is not a business approval.

Library loggers emit `discovery.started`, `discovery.completed`, `discovery.failed` and `catalogue.bundle_added`, using `extra` metadata for source ID, table/document counts or error code. The library installs a `NullHandler`; the calling backend owns formatting, destinations, filtering and retention. Cell samples and credentials are not logged. This is operational logging, not a complete audit/monitoring service.

## Validation results and preservation

**38 synthetic tests pass with warnings treated as errors.** [Contract tests](../../tests/test_contracts.py) cover required/type/null/uncertainty/version/JSON/reference errors, unapproved status enforcement, evidence and fingerprint consistency. [Discovery tests](../../tests/test_discovery.py) cover unrelated schemas, added/removed tables/fields, mixed types, missing states, blank/duplicate/headerless layouts, temporal ambiguity/periods, hypotheses, samples, schema drift, reader settings, corrupt/unsupported files, resource limits, source changes and safe logs. [Catalogue tests](../../tests/test_catalogue.py) cover exact versions, extension identity checks, defensive copies, atomic rollback, unordered bundles and exclusive JSON round trips.

Preservation compares the pre-task hashes of existing repository artifacts, including all 17 original sources, 167 report/evidence files, seven prior data implementations, four notebooks and the architecture document/diagram. Only README is intentionally extended; no earlier report or implementation is overwritten. Source bytes are read only for preservation hashes; NOP data is not profiled, cleaned, transformed or used by these tests. Requirements remain unchanged. The workspace currently has no `.git` repository, so no commit, branch or Git convention could be applied.

## Remaining limits and next activity

The foundation does not establish source authority, source permissions, business definitions, production keys, cross-table relationships or prediction readiness. It has no approval workflow, streaming/distributed execution, automatic header semantics, legacy `.xls` reader, database adapter, contract migration engine or concurrency-safe persistent catalogue. Format settings are explicit and unknown formats fail rather than silently changing interpretation. A successful discovery is technical evidence, not authorization to clean or train.

Recommended next activity, **only after explicit approval**: review the foundation contracts and design a trusted semantic-binding/approval mechanism for discovered roles and unresolved owner decisions. Keep that mechanism separate from discovery and from the teammate's LLM/MCP integration. Actual preparation and all ML development remain separately gated.
