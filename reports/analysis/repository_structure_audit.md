# Repository structure and reusability audit

**Repository:** `D:\Aroha_Files\NOP_Project`  
**Audit date:** 3 November 2026  
**Scope:** Read-only inspection of repository files and references. The only file created for this request is this report.

## Executive assessment

The repository has two distinct bodies of work that should remain recognizable: a schema-aware, approval-oriented `business_prediction` backend and a set of NOP-specific data analysis workflows with durable evidence and reports. The backend is the strongest reusable component. It has versioned contracts, adapters, discovery, governance, assessment, specification, execution, worker and publication packages, with a synthetic unit-test suite. It is not an ML training or serving system.

There is **no implemented feature engineering, training, evaluation, model loading or prediction API**, and no saved model or prepared training dataset. `src/features/`, `src/training/`, `src/prediction/`, `models/`, `model_ready/`, `processed/` and `evaluation/` are empty. Their presence reflects intended/future roles, not delivered capabilities.

The repository is workable as a research and evidence workspace, but its layout has grown in layers. Empty root output directories overlap with populated `reports/` subdirectories; analysis code and generated evidence are mixed in places; the package uses a `src/` layout without install/build metadata; and the README contains both current implementation notes and stale baseline statements. No cleanup is necessary to continue safely. Consolidation should be a separately reviewed migration because scripts, notebooks, reports and validation code refer to current paths.

## Inspection basis

The inventory covered 280 non-source-data files discoverable outside `.venv` and Python caches, plus all 17 files under `dataset/`; it included 64 files under `src/`, 19 test/support files, four notebooks, 11 documents and 182 files under `reports/`. The two text logs were also read. The recursive listing excluded environment internals and did not open every binary cell or image; spreadsheet/report contents were inspected through the existing textual evidence and summaries where applicable. No tests or workflows were executed for this read-only audit.

## Current structure assessment

| Location | Observed contents and role | Assessment / disposition |
| --- | --- | --- |
| `dataset/` | 17 original Excel/CSV sources used by analyses. | **Keep as the current raw-source location.** Preserve source files. README warns that their Git inclusion needs an approval decision, but `.gitignore` does not exclude this directory. |
| `dataset.zip` | Archive review records 17 members whose hashes match the corresponding `dataset/` files. | **Duplicate source package.** Keep both only if the archive has a distribution/backup purpose; otherwise select one canonical handoff after checking consumers. Do not delete during a structure-only cleanup. |
| `data/` | Empty. README lists it without defining a present workflow. | **Clarify intended role.** Do not remove solely because empty. It could become a configured location for derived data, but should not silently replace `dataset/`. |
| `processed/`, `model_ready/` | Empty future-stage locations. | **Keep as placeholders only if actively useful.** No current outputs or loaders use them. Prefer one documented derived-data convention when implementation begins. |
| `models/`, `evaluation/` | Empty. | **Keep as intended future artifact destinations** or consolidate into a single documented artifact convention after a model workflow exists. No model artifacts/evaluation results are present. |
| `analysis/`, `data_inventory/`, `data_quality/` (root) | Empty. Corresponding reports/evidence are under `reports/analysis`, `reports/data_inventory` and `reports/data_quality`. | **Likely redundant, not proven obsolete.** Their content is currently represented in `reports/`; first check path references and intended future use, then remove or redirect only with approval. |
| `notebooks/` | Four numbered workflow notebooks: inventory; data quality; relationships; feasibility. The latter three call corresponding `src/data` workflows for much of the work; the first contains a substantial self-contained inventory workflow. Notebook outputs and narrative are part of the inspected files. | **Keep as analysis and presentation entry points.** Avoid duplicating full workflow logic in more notebooks; consider moving reusable helpers into importable modules only when a real second consumer exists. |
| `src/data/` | Seven procedural modules: inventory/quality/relationship/feasibility/preparation-specification workflows and three validation scripts. They use pandas, NumPy, openpyxl, nbformat and plotting/parsing dependencies and write evidence to repository-relative report paths. | **Reuse for the existing NOP analyses.** These are repository workflows, not yet a general-purpose data/feature package. Their hard-coded repository paths and validators make them sensitive to moves. |
| `src/business_prediction/` | Reusable package with adapters, discovery, contracts/catalogue, assessment, semantics, runtime, persistence, specifications, execution, worker, storage and publication. | **Keep as the framework boundary.** Modules are schema/evidence-oriented and avoid NOP-specific field routing. See reusable components below. |
| `src/features/`, `src/training/`, `src/prediction/` | Present but empty; no files, importable modules or referenced implementation found. | **Missing capabilities, not duplicate code.** Preserve the intended separation if ML work is approved; do not claim these directories implement it. |
| `reports/` | 182 files across analysis, inventory and quality reports, evidence CSV/JSON, workbooks, diagrams and plots. `reports/analysis` also contains evidence subfolders and two helper scripts (`assess_sources.py`, `build_documents.py`). | **Keep as the canonical report/evidence area.** It is the most populated area and has internal consumers. Separate maintained scripts from generated output in a future migration. |
| `logs/` | Two text logs for data quality and relationship analysis. `.gitignore` excludes `logs/*.log` and `*.log`. | **Keep for run diagnostics.** Logs are transient and currently ignored as expected. |
| `tests/` | 19 Python test/support files. `unittest` tests cover contracts, discovery, assessments, semantic lifecycle, persistence, specifications, execution, worker/publication and NOP readiness evidence. Most fixtures are synthetic. | **Keep.** The test organization tracks the framework package reasonably well; no training/inference tests exist because those implementations do not exist. |
| `docs/` | Architecture and development guides covering both proposed architecture and implemented backend milestones. | **Keep.** Some documents explicitly label historical baselines and current implementation boundaries; preserve those distinctions when updating docs. |
| `.vscode/` | Workspace interpreter and notebook root settings. | **Keep as editor configuration.** The interpreter path is local-environment-specific but workspace-relative. |
| `requirements.txt` | Unpinned direct dependency names for notebooks and analysis; includes scientific/ML libraries as well as Jupyter and Excel dependencies. | **Keep for current environment setup; improve later.** There is no `pyproject.toml`, setup metadata, lock file or declared optional dependency groups. Installed packages alone do not imply ML functionality exists. |
| `.gitignore` | Ignores `.venv`, caches, logs and `/local_state/`, but not `dataset/`, `dataset.zip` or report artifacts. | **Review data/artifact policy before changing.** The README already cautions against committing business sources without permission. |
| `README.md` | Setup, workflows, evidence links and implementation history. | **Update for consistency.** The early project description/tree and statements such as “no prediction engine” are not aligned precisely with the later implemented assessment/specification/execution sections. It also omits the `business_prediction` subpackage tree from its initial project-structure diagram. |

## Existing reusable modules and files

### Reuse directly

- `src/business_prediction/adapters/`: reusable in-memory, CSV and modern Excel source adapters with explicit parsing/configuration boundaries. The framework guides document source versioning, raw field positions and preservation; these are the appropriate source-ingestion interfaces for future approved consumers.
- `src/business_prediction/discovery.py`, `contracts.py`, `metadata.py`, and `catalogue.py`: reusable schema discovery, versioned contract validation, exact references and evidence catalogue.
- `assessment/`: reusable intake, relevance, target and feasibility assessment with extensible problem-family strategies. Assessment is not a training pipeline.
- `semantics/`, `runtime/`, and `persistence/`: approval lifecycle, development/production boundaries, and durable local persistence. Documentation says production identity/storage integrations remain external.
- `specifications/`, `execution/`, and `worker/`: target/observation/plan declarations, controlled execution lifecycle, registered worker operators, reconciliation, artifact storage and publication gates. The worker's registered operators are limited (native inspection, approved filtering and narrow type interpretation); they do not provide general aggregation/grain construction.
- `src/data/assess_data_quality.py`, `analyze_relationships.py`, `assess_prediction_feasibility.py`, `specify_preparation_strategy.py`, and associated validators: reuse for their current report-producing analyses. They are substantial, source/repository-aware workflow scripts, not generic APIs for arbitrary data products.
- `tests/` fixture/support modules and framework tests: reuse as the synthetic contract and governance test foundation when extending the relevant component.
- `notebooks/02`–`04`: reuse for analysis walkthroughs and report review; they delegate major computation to `src/data` modules rather than being the sole reusable implementation.

### No reusable ML implementation found

No existing code trains a model, builds lag/calendar features, evaluates chronological model splits, saves a `.joblib` artifact, loads a model for prediction, or exposes a prediction function. `models/` and `evaluation/` are empty; the training-dataset workbook and blueprints under `reports/analysis` are specifications/evidence, not generated training tables. `requirements.txt` includes scikit-learn, XGBoost, statsmodels and joblib, but no inspected training/inference module imports or uses them. This is a capability gap, not a reason to recreate already implemented governance or data discovery.

## Reusability findings

| Concern | Finding |
| --- | --- |
| Data loading and validation | **Partly reusable.** Generic adapters exist in `business_prediction`; NOP analysis workflows also contain purpose-specific file reads, profiling and validation. Reuse adapters for framework flows and existing scripts for current reports; do not fork another CSV/Excel loader without a demonstrated missing capability. |
| Feature engineering | **Absent.** The `src/features/` directory is empty. No reusable feature contract or transformation pipeline is delivered. |
| Training vs evaluation | **Absent.** No training module or split/evaluation pipeline was found. The assessment engine assesses readiness, not model performance. |
| Importable prediction | **Absent.** No `predict()` interface or serving/model-loading module exists. |
| Configuration | **Partial.** `business_prediction/runtime/config.py` defines runtime configuration; `.vscode/settings.json` configures the local editor. Analysis scripts generally derive paths from the repository root and embed workflow/output paths in code. Dependency metadata is a plain unpinned `requirements.txt`. |
| Tests | **Good for implemented scope.** `unittest` fixtures exercise the framework with synthetic inputs. Current tests match the package-oriented backend but cannot validate absent model behavior. |
| Documentation | **Extensive but layered.** Development guides identify implementation boundaries, while README opening sections and its tree need a single current-state pass. Evidence documents are appropriately explicit that proposed semantics are not approvals. |
| Storage consistency | **Mixed.** Report outputs are mostly grouped under `reports/`; several empty root directories suggest parallel destinations. Raw files are in `dataset/`, with a byte-identical zip at root. There is no canonical generated dataset/model/evaluation artifact policy yet. |

## Duplications and inconsistencies

1. **Empty roots overlap with report categories.** Root `analysis/`, `data_inventory/` and `data_quality/` are empty while their actual report content is under `reports/`. `data/`, `processed/`, `model_ready/`, `models/` and `evaluation/` are also empty placeholders. These are candidates for future consolidation, not confirmed dead directories.
2. **Raw-data archive duplicates current source files.** The existing archive review reports that all 17 archive members match source files by hash. This is intentional duplication only if the zip serves a separate archive/distribution purpose.
3. **Workflow code is mixed with evidence output.** The two report-evidence directories contain helper scripts alongside generated evidence. Moving these scripts would improve separation, but validators, notebooks and README links need to be checked/updated together.
4. **Notebook/code boundary differs by workflow.** Notebooks 02–04 call workflow modules. Notebook 01 contains extensive inventory code, while `validate_inventory.py` validates notebook-produced outputs rather than serving as a matching inventory engine. Do not mistake that validator for a duplicate inventory workflow.
5. **Documentation has stale or conflicting summaries.** README’s introductory tree predates the `business_prediction` package, and some broad “not implemented” statements overstate what is absent: target assessment, governed specifications and controlled preparation execution now exist, while model training and prediction remain absent. The later detailed sections describe the current boundary more accurately.
6. **Package installation is environment-dependent.** Framework imports use `business_prediction` from the `src/` layout. The documented test command sets `PYTHONPATH=src`; there is no `pyproject.toml` or setup file for editable installation or package metadata. Notebook scripts similarly insert repository-local paths.
7. **Dependencies are broad and unpinned.** The requirements list covers analyses, Excel, notebooks and possible ML but does not separate runtime, development and optional modeling needs. Avoid deleting libraries based on a source-only scan; notebooks and validation workflows use dependencies too.

No files were classified as safe to delete. No exact duplicated implementation was found that justifies consolidating code immediately; similar low-level parsing or hashing patterns across analysis scripts warrant a narrower code-level review before abstraction.

## Recommended target structure

Preserve the current framework package and keep analysis/workflow code distinct from generated data and evidence. A low-disruption target is:

```text
NOP_Project/
├── README.md
├── pyproject.toml                 # Add when packaging/dependency policy is approved
├── requirements.txt               # Keep during transition or derive from declared groups
├── dataset/                        # Existing immutable/raw NOP sources; preserve current path
├── data/
│   ├── interim/                    # Future, explicitly approved intermediate data
│   ├── processed/                  # Future validated derived datasets
│   └── model_ready/                # Future approved training/inference inputs
├── artifacts/
│   ├── models/                     # Versioned model artifacts
│   └── evaluations/                # Machine-readable evaluation/provenance outputs
├── notebooks/                      # Exploratory and report walkthroughs
├── reports/
│   ├── data_inventory/
│   ├── data_quality/
│   ├── analysis/
│   └── evaluation/                 # Human-readable result summaries
├── src/
│   ├── business_prediction/        # Existing generic governed backend; preserve
│   └── data/                       # Existing NOP workflow entry points; preserve initially
├── tests/                          # Unit/contract tests mirroring source packages
├── docs/
├── logs/                           # Transient, ignored execution logs
└── local_state/                    # Existing documented ignored runtime state
```

This is a target, not a request to create empty folders now. If future reusable ML code is authorized, add a generic package boundary (for example, `business_prediction/modeling/` with separately testable feature construction, training, evaluation and prediction interfaces) only after contracts and consumer needs are defined. Keep NOP-specific source names and interpretations in configuration/evidence bindings, never in generic model code. Do not place experiment-specific code into the existing governance framework merely because its directories are adjacent.

## Proposed moves and renames

| Existing path | Proposed treatment | Preconditions / risk |
| --- | --- | --- |
| `analysis/`, `data_inventory/`, `data_quality/` (empty roots) | Retire or document as aliases for `reports/analysis`, `reports/data_inventory`, `reports/data_quality`. | Search external/IDE links as well as repository references; contents are empty, but names may be user conventions. Do not create duplicate report trees. |
| `processed/`, `model_ready/` | In a future data-layout migration, place under `data/processed/` and `data/model_ready/`. | Update scripts, documentation, access controls and data-retention policy; no current artifacts need movement. |
| `models/`, `evaluation/` | In a future artifact-policy migration, use `artifacts/models/` and `artifacts/evaluations/`; keep readable summaries under `reports/evaluation/`. | Decide naming, versioning, provenance and ignore/commit policy before generated artifacts exist. |
| `reports/analysis/nop_readiness_evidence/assess_sources.py` and `reports/analysis/initial_prediction_clarification_evidence/build_documents.py` | Move maintained helper code to `scripts/` or a reporting package; leave evidence outputs under `reports/`. | Update references/tests and preserve reproducibility/provenance. Their current location is understandable as task evidence but blurs code/output ownership. |
| `dataset.zip` | Keep as a separately documented archive or retire after choosing a single source handoff. | Verify consumer and backup requirements; it duplicates all 17 present source files byte-for-byte according to archive evidence. |
| `src/features/`, `src/training/`, `src/prediction/` | Do not move or populate as a cleanup task. Decide whether to retain these empty placeholders or replace them with a single `business_prediction/modeling/` package when actual functionality is approved. | Avoid multiple competing homes for the same future ML APIs. |

No move or rename is recommended before the reference and compatibility checks above. The existing `dataset/` path is embedded in notebooks and scripts; the report/evidence paths are also referenced by validation code and documentation.

## Missing but genuinely required for an ML product

These are missing capabilities, not cleanup findings:

- A package/build configuration and a documented supported Python/dependency policy if the framework is to be installed/imported by teammate services instead of relying on `PYTHONPATH=src`.
- A reusable, schema-aware feature/data transformation contract and training entry point, separate from exploratory notebooks and the governed preparation worker.
- Chronological split and evaluation orchestration with leakage controls, baseline comparison, metrics, and recorded data/model provenance.
- A serializable model bundle contract, compatibility metadata, independently importable prediction interface, input/output validation, and model lifecycle policy.
- Configuration and artifact storage policy for approved dataset versions, model versions, evaluations, and logs.
- Tests for training, fresh-process model loading, prediction input/output and artifact compatibility once those features exist.

These components must integrate with, not replace, the current approval/evidence framework. The current preparation worker is not a model-training dispatcher and should not be treated as one.

## Risks and compatibility considerations

- Moving `dataset/` or report paths can invalidate notebook references, validators, README commands, manifests and relative output assumptions.
- The present approval/evidence system pins source and schema revisions. Reorganizing data must retain original bytes and provenance; a path change alone does not transfer business approval.
- Raw business sources are not ignored by `.gitignore`; committing them may expose sensitive data. Resolve data-sharing policy before any Git or artifact policy change.
- The zip duplicates raw source data and creates two handoff locations that can drift after later updates.
- Large notebooks and generated workbooks/evidence can make diffs difficult; preserve evidence intentionally and avoid treating notebooks as the only source of business logic.
- Local runtime and worker guides distinguish development-only providers from required production integrations. A cleaner tree cannot make those production services available.
- Unpinned dependencies and absent packaging metadata can make teammate integration environment-sensitive. Pinning or splitting dependencies needs a tested compatibility decision, not an arbitrary cleanup edit.
- Existing ML packages in requirements do not establish that training is supported, authorized, or tested.

## Prioritized cleanup plan

1. **Clarify current-state documentation.** Update the README structure and status wording so implemented backend capabilities and missing ML/inference capabilities are unambiguous. Add a short purpose statement for each root data/output directory.
2. **Set data handling policy.** Decide whether `dataset/` and `dataset.zip` may be versioned/shared; then align `.gitignore` and README. Keep source bytes unchanged.
3. **Choose one generated-data/artifact convention before producing outputs.** Decide `data/{interim,processed,model_ready}` and `artifacts/{models,evaluations}` or another explicit layout; avoid populating both root-level and nested duplicates.
4. **Resolve empty-root intent.** Search code, docs, scripts and editor tooling for references to empty folders. Retain those with a planned role; otherwise remove only after approval and reference updates.
5. **Separate maintained scripts from generated evidence.** Relocate the two report-folder helper scripts only as a coordinated change with updated references and reproducibility checks.
6. **Add packaging/dependency metadata when integration is scheduled.** Keep the current setup working while selecting supported Python, package metadata, optional analysis/model extras and version bounds; validate a clean environment.
7. **Add ML modules only for an approved objective and data path.** Implement and test reusable feature, train/evaluate and prediction interfaces in one selected package boundary; do not duplicate adapter, approval or provenance services.
8. **Avoid deletion/consolidation absent evidence.** The current audit found no safe code deletion. Review any proposed removal against tests, path references and the historical evidence record first.

## Files inspected

The structural review included `README.md`, `requirements.txt`, `.gitignore`, `.vscode/settings.json`, all Python paths under `src/` and `tests/`, notebook metadata/cells/headings, development and architecture documentation, logs, report/evidence inventories, source-data filenames and the archive review manifest. Binary workbook/image contents were not exhaustively re-opened; cited detailed analyses and validation evidence were used for their stated scopes.
