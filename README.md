# NOP Business Prediction and ML

A Python repository for schema-aware business data preparation, governed prediction workflows and independently callable ML inference using NOP source data.

The current delivery contains **seven actual-source predictors: five ML estimators and two baselines**. All remain exploratory. No business-approved champion or production forecasting performance has been established.

[Integration guide](docs/development/nop_ml_model_integration_guide.md) | [Model catalogue](reports/nop_ml_model_catalogue.md) | [Handoff verification](reports/nop_ml_final_handoff_verification.md) | [Contributing](CONTRIBUTING.md)

## Current delivery

| Target | Available predictors | Evidence and limits |
| --- | --- | --- |
| Confirmed-date monthly invoice-reference subset count | Linear Regression, Random Forest, last-value baseline | Eight eligible months; two historical test months. Neither ML estimator beat the baseline. |
| Offline stored line-value estimation from supplied quantity/item code | Ridge v1, Random Forest v1, normalized Ridge v2, item/quantity median baseline | Restricted actual-source rows; raw field meaning is not approved revenue or profit. The v2 candidate lost to its baseline on all three development folds. |

The existing synthetic invoice-volume demonstration is separate and excluded from actual-source model counts. Training and evaluation evidence is in the [ML report](reports/nop_actual_data_ml_training_report.md). Exact artifact identities, versions and SHA-256 values are in the [delivery manifest](evaluation/actual_data_ml_assessment/v2/delivery_manifest.json).

## Quick start

Use **Python 3.12.10**. The delivered artifacts require the pinned versions in [requirements-ml.txt](requirements-ml.txt); the existing local `.venv` was found to have an incompatible scikit-learn version. Create a separate environment for this delivery.

Windows PowerShell:

```powershell
python -m venv .venv-ml
.\.venv-ml\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e .
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
```

Linux or macOS:

```bash
python3.12 -m venv .venv-ml
source .venv-ml/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e .
export PYTHONPATH="$PWD/src"
```

`requirements-ml.txt` pins the verified inference dependencies. `requirements-dev.txt` adds the existing Excel adapters and packaging tools used by local verification and CI. The original `requirements.txt` remains available for broader analysis/notebook dependencies; it is not a reproducible model environment by itself. If those additional packages are needed, constrain their installation with `-c requirements-ml.txt`.

The Python package installs reusable source modules. Models, data and evidence remain separate repository assets and must accompany an integration delivery. No model is automatically trained during installation.

## Inference

Run from the repository root with the delivered artifacts present.

Monthly count-subset prediction:

```python
from prediction.monthly_regression import predict_monthly_objective

result = predict_monthly_objective(
    {"periods_ahead": 2},
    model_path=(
        "models/business_forecasting/nop_confirmed_date_invoice_subset/"
        "baselines/v1/last_observed_value.joblib"
    ),
)
```

Supplied-row line-value estimation:

```python
from prediction.tabular_regression import predict_tabular_regression

result = predict_tabular_regression(
    {
        "rows": [{"quantity": 4, "item_code": "FG00100"}],
        "expected_objective_id": "nop-domestic-confirmed-date-line-value",
        "expected_dataset_version": "1.0.0",
    },
    model_path=(
        "models/business_regression/nop_domestic_invoice_line_value/"
        "v2/item_quantity_median_baseline.joblib"
    ),
)
```

Both interfaces return JSON-compatible structured results with model identity, provenance and limitations. Monthly periods start after the stored September 2026 source cutoff, rather than today's date. The package-level `prediction.predict_invoice_volume` function belongs to the separate synthetic demonstration.

For schemas, dependency preflight, source/dataset integrity, feature-row routing and integration ownership, follow the [ML integration guide](docs/development/nop_ml_model_integration_guide.md) and [final handoff report](reports/nop_ml_final_handoff_verification.md).

## Validation and CI

The automatic [GitHub Actions workflow](.github/workflows/ci.yml) runs source-independent contract, schema-discovery and aggregation checks on Windows and Linux:

```bash
python -m unittest -v tests.test_contracts tests.test_discovery tests.test_time_series_aggregation_operator
```

A manually dispatched workflow can additionally run eight read-only delivery checks when the original data and model artifacts are available. Those checks verify preservation, lineage, baseline reproduction, temporal partitions and inference without retraining registered models. The workflow does not upload source data or model artifacts as job outputs.

**Known integration gap:** four existing dynamic-query tests assume exactly two monthly artifacts; discovery now legitimately identifies three. Their recorded failures and correct identity-based expectations are documented in the handoff report. These tests remain unchanged. A passing scoped CI job does not mean the full repository suite passes, and GitHub-hosted execution must be confirmed after the repository is published.

## Repository layout

```text
NOP_Project/
|-- .github/          # CI and issue/pull-request templates
|-- dataset/          # Original source files; preserve exact bytes
|-- data/             # Prepared datasets, specifications and provenance
|-- src/
|   |-- business_prediction/  # Existing governed framework
|   |-- data/                 # Source inventory and analysis scripts
|   |-- features/             # Shared feature validation/preparation
|   |-- training/             # Training and evaluation workflows
|   `-- prediction/           # Independent inference and adapters
|-- models/           # Versioned artifacts, sidecars and model indexes
|-- evaluation/       # Metrics, predictions and verification evidence
|-- reports/          # Assessment, catalogue and handoff reports
|-- docs/             # Architecture and integration guides
|-- notebooks/        # Existing analysis walkthroughs
|-- tests/            # Framework and ML tests
|-- pyproject.toml    # Python package metadata
|-- requirements-ml.txt
|-- requirements-dev.txt
`-- requirements.txt  # Existing broader analysis dependencies
```

The existing structure and model versions are preserved. `.gitattributes` prevents implicit line-ending conversion of hash-referenced files across operating systems. Do not bulk-format governed assets or run `git add --renormalize` against the existing delivery.

## Development and ownership

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing data, models or shared contracts. Original source files are read-only, and new model deliveries require unused version directories, reproducible preparation, baseline evaluation and fresh-process inference.

ML ownership covers preparation, features, training, evaluation, artifacts and documented inference. Integration owners maintain LLM interpretation, MCP, APIs, UI and routing. Existing framework documentation is under [docs/architecture](docs/architecture/), and the current dynamic entry point is described in [its guide](docs/development/dynamic_business_query.md).

## Access, security and licensing

The repository includes business data and derived evidence. Repository visibility and distribution require the project owner's decision; see [SECURITY.md](SECURITY.md). Load only trusted serialized models with verified hashes. No license is currently declared; licensing remains a repository-owner decision.
