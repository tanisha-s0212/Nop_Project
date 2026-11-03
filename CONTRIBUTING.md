# Contributing

Use Python 3.12.10 and the pinned ML environment described in [README.md](README.md). Install `requirements-dev.txt` in a project-local environment. Use `PYTHONPATH=src` when running tests from the repository root.

## Scope and ownership

ML contributions belong in the existing feature, training and prediction packages. Reuse established preparation, discovery, inference and artifact contracts. Integration owners maintain language interpretation, MCP, APIs, UI and framework routing. Keep changes focused and coordinate changes to those components with their owners.

## Data and artifact changes

- Preserve original files in `dataset/` and previously delivered model versions.
- Put derived datasets in `data/`, models in `models/` and evaluation evidence in `evaluation/`, with provenance and SHA-256 records.
- Use unused version directories. Include target definitions, dependency versions, feature schemas, evaluation periods and limitations.
- Keep exploratory and synthetic status explicit. Training success does not establish business approval.
- Verify inference in a fresh process and compare against a suitable baseline before proposing model promotion.
- Preserve line endings and bytes of hash-referenced files. Do not run repository-wide formatters or `git add --renormalize` across existing evidence.

## Validation

Run tests relevant to the change and record the exact commands and outcomes in the pull request. The automatic GitHub Actions job runs contract, schema-discovery and monthly-aggregation tests without NOP source data. A manually requested job verifies the delivered actual-source artifacts using read-only checks when the required files are present.

The complete suite has not been established as passing. Four existing dynamic-query assertions still expect two monthly artifacts; the current compatible set contains three. See the [handoff report](reports/nop_ml_final_handoff_verification.md) for the test names and intended identity-based behavior. Do not suppress a compatible baseline or weaken guards to satisfy an old fixed count.

## Pull requests

Explain the concrete behavior changed, the evidence supporting it, tests executed and any compatibility or data implications. Link the relevant report or dataset/model version. Include no credentials, private business rows or generated environment files in issue or pull-request text.
