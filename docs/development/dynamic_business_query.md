# Dynamic business query integration

The callable entry point is `business_prediction.DynamicBusinessQueryService.process(request)`. It discovers prepared datasets and model sidecars, reuses the existing discovery catalogue or registered source adapters, validates target scope and fingerprints, creates a reproducible plan, and executes supported calculations or model inference. Questions and source mappings are runtime inputs. The generic code contains no NOP source-column mappings or question catalogue.

## Environment

From the repository root:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m business_prediction --request evaluation/dynamic_business_intelligence/example_request.json
```

Use an environment matching the selected artifacts' dependency metadata. The existing actual-source models record Python 3.12.10 and scikit-learn 1.8.0. During validation, the system `python` matched these versions; `.venv` had scikit-learn 1.9.1. The service returns model failures for incompatible dependencies before unpickling. No packages were installed or changed.

## Python and MCP invocation

```python
from pathlib import Path
from business_prediction import DynamicBusinessQueryService

service = DynamicBusinessQueryService(Path.cwd())
result = service.process({
    "question": "Forecast the explicitly selected confirmed-date subset",
    "intent": "forecast",
    "objective_id": "nop-confirmed-date-invoice-count-exploratory",
    "periods_ahead": 2,
})
```

A Python MCP tool can call `service.process(arguments)` and return the dictionary as JSON. Configure repository paths, source adapters, catalogue, interpreter, and inference adapters in trusted host code. Input requests cannot supply import paths, arbitrary artifact paths, Python formulas, credentials, or approval records. This repository does not run an MCP or HTTP server.

Actual example results are in [fresh_process_prediction.json](../../evaluation/dynamic_business_intelligence/fresh_process_prediction.json); the broader scenario results are in [actual_request_results.json](../../evaluation/dynamic_business_intelligence/actual_request_results.json).

## Request contract

A request may be a question string or an object with `question` and optional fields:

| Field | Meaning |
| --- | --- |
| `intent` | `historical_analysis`, `forecast`, `diagnostic`, or `profile`; unfamiliar intents receive clarification. |
| `dataset_id` | Exact prepared dataset selected from `service.discover()`. |
| `objective_id` | Exact forecast target selected from discovered model metadata. |
| `analysis` | Explicit measure, operation, dimensions, time field/range, filters and missing policy. |
| `periods_ahead`, `horizon_unit` | Positive forecast length and unit. The selected adapter enforces its supported horizon and frequency. |
| `model_identifier`, `model_version` | Optional compatible model selection. Otherwise models remain separate; a champion is not inferred. |
| `plan_only` | Return a deterministic plan with data/model fingerprints without executing it. |
| `mode` | `exploratory` by default; `approved` delegates to the existing authenticated assessment service. |
| `source_reference` | Exact `source_id`, `table_id`, and optional `field_id` for a physical source profile. |

Example historical request:

```python
result = service.process({
    "question": "Rank the observed monthly counts",
    "intent": "historical_analysis",
    "dataset_id": "nop-confirmed-date-invoice-count-exploratory",
    "analysis": {
        "measure": "target_count",
        "operation": "rank",
        "dimensions": ["period"],
        "time_range": {"start": "2026-01", "end": "2026-08"},
    },
})
```

Supported generic operations are summary, mean, minimum/maximum, distinct stored-value counting, series, change, comparison, ranking, anomaly checks, and sum when additive semantics are explicitly evidenced. Grouped comparisons/rankings compare observation means. Canonical periods are `YYYY-MM` or `YYYY-MM-DD`; date grammar is never guessed. Missing values fail validation unless `missing_policy: "exclude"` is explicit, in which case exclusions are counted. Missing periods are not created. Filters support exact stored-value `eq` and `in` operations.

## Dataset registration and semantics

Prepared CSVs use adjacent `<name>.metadata.json` files with dataset identity/version/hash, target definition, source hashes, data mode, and explicit `business_approved: false` for exploratory access. A sibling `<name>.spec.json` or metadata `query_schema` supplies `target_column` and `period_column`. These field roles replace hardcoded column names.

Summation additionally requires `query_schema.measure_semantics[measure]` (or the sibling specification) to include `additive: true` and an `evidence` reference/description. This prevents repeated document totals or distinct counts across incompatible grains being silently summed. The local specification records an exploratory assumption; it does not create a governed business approval.

`source_adapters=[...]` reuses `discover()` for current sources. A supplied `MetadataCatalogue` can reuse existing pinned discoveries while verifying their source bytes. Prefix profiles remain labeled with their coverage; a sample distinct count is not presented as a full-table count. Source profiles return physical facts and unreviewed semantic status.

## Natural-language interpretation

The built-in interpreter is conservative and limited to common analytical phrasing. It does not guarantee understanding of arbitrary language. Unsupported business concepts, omitted grouping, unresolved periods, and unmatched targets receive clarification. A broad invoice question receives a partial result when only a scoped subset exists.

Connect the teammate's existing LLM through a provider-neutral callback:

```python
from business_prediction import DynamicBusinessQueryService, JSONRequestInterpreter

# complete(messages) is supplied by the host's existing LLM integration.
service = DynamicBusinessQueryService(
    Path.cwd(),
    interpreter=JSONRequestInterpreter(complete),
)
result = service.process("A previously unseen business question")
```

The callback receives role/content messages containing the question and current schemas, prepared targets, and models. It returns a JSON object conforming to the request contract. Interpreter selections remain hypotheses and produce partial exploratory answers until an exact target is explicitly selected. The interpreter cannot grant approvals or execute code. No remote LLM provider or credentials are bundled.

## Existing governance and worker integration

`runtime.business_query_service(root, worker=worker)` shares the existing catalogue and runtime. `process(..., authorization=...)` in approved mode submits a structured `requirement` to the current requirement assessment engine. Host authorization includes `scope`, submission `context`, `command_id`, `expected_head`, and optional separate `assessment_context`. Readiness still has `execution_authorized: false`.

`service.run_preparation(request_reference, context=..., command_id=..., expected_head=...)` advances an already authorized execution through the existing worker and reconciler. It cannot authorize the request itself. Interrupted or already-running work uses the existing recovery API. Publication remains a separate permission and operation through the existing publication service. Local exploratory asset metadata is never accepted as production approval.

## Training and inference extensions

`service.train_dataset(dataset_id, specification, version="new-version", seed=...)` calls the existing monthly regression trainer on one integrity-verified exploratory prepared dataset. The full objective/target/period/eligibility specification is required. It creates a new version directory and refuses overwrite. The existing trainer supports nonnegative regular monthly targets, at least eight eligible observations, calendar-index features, Linear Regression and Random Forest, and the existing small chronological split. It does not prepare new labels from question text or establish business approval. The existing synthetic demonstration pipeline is separate.

Additional model families integrate through trusted `inference_adapters`, each exposing `supports(metadata)` and `predict(path, inputs)`. Returned forecasts must contain matching model identity/version, distinct ordered ISO periods, finite numeric predictions, and exploratory approval status. The built-in adapter wraps the existing monthly regression inference function; its current horizon is 1–24 months. Source/model/data fingerprints and dependency versions are verified before dispatch.

## Output and current limitations

Responses have `status`, `answer_type`, `question`, relevant results/forecasts, a plan, source observations, provenance and limitations. Statuses include `answered`, `partially_answered`, `planned`, `clarification_required`, `validation_failed`, `unsupported`, and `approval_blocked`. Business explanations name the actual target and method. Descriptive changes and anomaly scores do not establish causation.

The actual NOP example represents only 152 confirmed-date invoice references in one workbook, excluding 82 unresolved references. It has 10 observed monthly buckets, unknown extraction completeness, and two models evaluated on a two-month holdout. Neither beat its baseline. Complete revenue/profit/demand/inventory/customer targets and production integrations remain external evidence and implementation requirements.
