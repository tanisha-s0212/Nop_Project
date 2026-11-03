# NOP ML final handoff verification

**Verification date:** 3 November 2026  
**Executed audit timestamp:** 2026-11-03T16:59:08.462077+00:00  
**Repository:** `D:\Aroha_Files\NOP_Project`

## Handoff outcome

The ML artifacts are available for controlled exploratory integration. All seven actual-source predictors and their sidecars exist; artifact hashes, identities and versions match the delivery manifest. Current discovery returns exactly those seven identity/version pairs: five ML estimators and two baselines, comprising three monthly predictors and four feature-row predictors. No discovery or dependency failures occurred in the matching interpreter.

All seven predictors were independently loaded and used again in fresh Python processes during this handoff. The four previously failing integration tests remain unresolved because they encode the earlier two-monthly-model inventory. Read-only functional probes confirmed the correct behavior with the additional compatible baseline. Neither those tests nor teammate-owned implementation was changed.

No model was trained, refitted, replaced, deleted or promoted. All 123 historically protected files, including all 17 original sources, remain unchanged. This task creates only this report. No business-approved or production-ready champion is declared.

## 1. Inputs reviewed and verification method

Reviewed the current [ML assessment report](nop_actual_data_ml_training_report.md), [model catalogue](nop_ml_model_catalogue.md), [integration guide](../docs/development/nop_ml_model_integration_guide.md), and [delivery manifest](../evaluation/actual_data_ml_assessment/v2/delivery_manifest.json). Their audit-time SHA-256 values are:

| Reviewed input | SHA-256 |
| --- | --- |
| `reports/nop_actual_data_ml_training_report.md` | `1929a0b3864ebbf2fb9a4c21e031cae31c0bffe44a6ceb96abded9d128079f34` |
| `reports/nop_ml_model_catalogue.md` | `1ee663a72148a28fbb8d9c939bd96e49c78c662a103519d3edf7ebaeab606b5f` |
| `docs/development/nop_ml_model_integration_guide.md` | `785119a22282bc9bbe805cdbc69fb75d261e14f23570cf89a99f38a29206a4fa` |
| `evaluation/actual_data_ml_assessment/v2/delivery_manifest.json` | `1e23c478764ecb389ef9a6547f4fc3032cca5e8bcaf48de5564a940c38d530e4` |

The checks read the manifest, invoked existing `business_prediction.query_assets.model_assets` and `dataset_assets`, compared the complete discovered identity/version set with the manifest, verified artifact bytes against both manifest and sidecar SHA-256, checked sidecar identity/version/path, required exactly one compatible adapter, checked recorded dependencies, and matched each model fingerprint to one currently verified prepared dataset. The source-provenance checks in discovery also passed.

The four old test definitions and their prior failure transcript were reviewed. Separate read-only probes exercised their intended contracts using discovered identity/version sets instead of a fixed artifact count. Each artifact was then loaded through its supported adapter in a separate Python process, with JSON serialization, finite-value, count, identity/version and exploratory-status assertions.

**Metadata verification limit:** The existing delivery manifest records sidecar paths, model identities/versions and artifact hashes, but does not pin a separate sidecar-file hash. Sidecar existence, manifest fields and current model/dataset contracts were verified; this cannot prove every sidecar byte is unchanged from the historical manifest. Current sidecar SHA-256 values are recorded below as handoff evidence. No manifest or metadata was rewritten.

## 2. Available predictors and target boundaries

| Ref | Exact model identifier | Version | Kind | Intended target |
| --- | --- | --- | --- | --- |
| A1 | `nop-confirmed-date-invoice-count-exploratory-last_observed_value_baseline-v1.0.0` | 1.0.0 | Baseline | Monthly count subset |
| A2 | `nop-confirmed-date-invoice-count-exploratory-linear_regression` | 0.1.0-exploratory | ML estimator | Monthly count subset |
| A3 | `nop-confirmed-date-invoice-count-exploratory-random_forest` | 0.1.0-exploratory | ML estimator | Monthly count subset |
| A4 | `nop-domestic-confirmed-date-line-value-random_forest-v1.0.0` | 1.0.0 | ML estimator | Supplied-row stored line value |
| A5 | `nop-domestic-confirmed-date-line-value-ridge_regression-v1.0.0` | 1.0.0 | ML estimator | Supplied-row stored line value |
| A6 | `nop-domestic-confirmed-date-line-value-item_quantity_median_baseline-v2.0.0` | 2.0.0 | Baseline | Supplied-row stored line value |
| A7 | `nop-domestic-confirmed-date-line-value-quantity_normalized_ridge-v2.0.0` | 2.0.0 | ML estimator | Supplied-row stored line value |

A1 and A6 are fitted reference baselines, not additional ML improvements. A1 uses a constant last observed count, serialized with `DummyRegressor`. A6 learns per-item median target/quantity and a training-only global fallback. A7 is a research candidate rejected as a baseline replacement: it lost to A6 on every development fold. Preserving an artifact does not recommend it for business decisions.

A2-A5 are the four previously retained actual-source ML models. All seven have `business_approved: false`. The separate synthetic invoice-volume demonstration is unchanged, excluded from these seven and from actual-source comparisons.

### Artifact and sidecar status

| Ref | Exact artifact path | Matching sidecar | Manifest/metadata checks |
| --- | --- | --- | --- |
| A1 | [models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/last_observed_value.joblib](../models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/last_observed_value.joblib) | [last_observed_value.metadata.json](../models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1/last_observed_value.metadata.json) | PASS |
| A2 | [models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib](../models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.joblib) | [linear_regression.metadata.json](../models/business_forecasting/nop_confirmed_date_invoice_subset/linear_regression.metadata.json) | PASS |
| A3 | [models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib](../models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.joblib) | [random_forest.metadata.json](../models/business_forecasting/nop_confirmed_date_invoice_subset/random_forest.metadata.json) | PASS |
| A4 | [models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.joblib](../models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.joblib) | [random_forest.metadata.json](../models/business_regression/nop_domestic_invoice_line_value/v1/random_forest.metadata.json) | PASS |
| A5 | [models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.joblib](../models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.joblib) | [ridge_regression.metadata.json](../models/business_regression/nop_domestic_invoice_line_value/v1/ridge_regression.metadata.json) | PASS |
| A6 | [models/business_regression/nop_domestic_invoice_line_value/v2/item_quantity_median_baseline.joblib](../models/business_regression/nop_domestic_invoice_line_value/v2/item_quantity_median_baseline.joblib) | [item_quantity_median_baseline.metadata.json](../models/business_regression/nop_domestic_invoice_line_value/v2/item_quantity_median_baseline.metadata.json) | PASS |
| A7 | [models/business_regression/nop_domestic_invoice_line_value/v2/quantity_normalized_ridge.joblib](../models/business_regression/nop_domestic_invoice_line_value/v2/quantity_normalized_ridge.joblib) | [quantity_normalized_ridge.metadata.json](../models/business_regression/nop_domestic_invoice_line_value/v2/quantity_normalized_ridge.metadata.json) | PASS |

Both artifact and sidecar must be distributed together. The model catalogue is an index; authoritative inference compatibility also depends on the selected artifact, its sidecar, dataset lineage, adapter and runtime.

| Ref | Artifact SHA-256, matching manifest and sidecar | Current sidecar SHA-256 |
| --- | --- | --- |
| A1 | `5b280e163c546f759a952ee53e891c81da6a6f63bde38747035a16e10871ded7` | `e157cc025064a7c1d87e5d5dc9c09ec9c4d03176bee1a50225d9eea6fddbc0b8` |
| A2 | `e13668b5a9b4dceaf7ff751e9bbe47e9d476687d032c166e315be0ff37068cf4` | `6c85293f65dd9ebeace776d02365a78673ef7e6143f233fed9e723d811352b96` |
| A3 | `e556ed1111c352248f11fa270aee8503ac37633c3fc09adbe13faa2f01dc76e4` | `90f0de4315950b9b8d87e704ff0e4d84bb00cfb01467ae86082ef3fb03571c20` |
| A4 | `095c704de58264e542a0f0dc7b531970e163ff0a0252decae2efa46bdbe072c1` | `eb93a819379c077022d913208d551c1640518e502094eaf74d2cfe49d1f76123` |
| A5 | `b74b69513767218252433e33683fabd718f5964e028ac447f587fc5c851de5ff` | `69fd33d13807d534c4c8219fc5bf6927e99a6179cb25580484e8cbeeca824b78` |
| A6 | `e85a0b8e9e8176e10ff5e802d1f8112072dfb71497d9165841dcd551b739fd0c` | `bac6c800bbb02313581ea7ac9967d515fe349f7c4238b46a88b04fbab52d847a` |
| A7 | `e439637978c97dcdb3a549b085217b44d77a43f98f6593f3167b757b31ddb358` | `676c9d19a4bc5eb83ca55bd384ab95045ab7c7ce016ac2db4ce12d2dc51ec0ed` |

## 3. Verified datasets and compatibility

| Predictor group | Prepared dataset | Dataset identity / version | SHA-256 |
| --- | --- | --- | --- |
| A1-A3 | `data/nop_confirmed_date_invoice_count_exploratory.csv` | `nop-confirmed-date-invoice-count-exploratory` / `1.0.0` | `807bb312577bb595cdb22d28dd227c0fc23e52898ab42dbe73b99f7d4f444b95` |
| A4-A7 | `data/nop_domestic_invoice_line_value/v1/observations.csv` | `nop-domestic-confirmed-date-line-value` / `1.0.0` | `c177d1d76b8695ea41c88995b0782ad2a37545321df419ed30e758341fb8dd8e` |

Model version 2.0.0 for A6/A7 still uses dataset version 1.0.0. Model and dataset versions are separate compatibility fields.

A1-A3 predict only counts of raw invoice references with fully consistent calendar-resolved dates in one source workbook. Ten observed months contain only eight eligible interior months; this is not a complete invoice population or certified complete business history.

A4-A7 estimate the native stored `Taxable Value` cell on a restricted source detail row. The existing dataset has 165 rows, 111 reference groups and 92 item codes, from 22 December 2025 to 13 September 2026. It is not an approved revenue, profit, demand or future-period financial target. The source amount currency and physical quantity units remain unverified. Raw reference identity is scoped to the extract.

A4-A7 accept supplied quantity and item code, with no date, target, unit price or document ID input. Future quantities are not known forecasting features. Monthly target overrides, unrelated measures, groups or datasets must not be routed to the invoice-count artifacts. No current artifact supports profit, inventory or customer propensity.

## 4. Dynamic discovery and supported inference

The existing scanner recursively reads model sidecars and verifies paths, artifact hashes, original-source hashes and recorded dependencies. It does not require new question-to-model mappings. Its current discovered set equals the manifest set exactly, with no missing, extra or duplicate identity/version pair.

Adapter membership is dynamic:

- `MonthlyRegressionQueryAdapter` / `monthly_regression_v1`: A1-A3. A1 declares the adapter explicitly. A2/A3 remain supported by the existing legacy metadata compatibility branch.
- `TabularRegressionInferenceAdapter` / `tabular_regression_v1`: A4-A7, declared as feature-row regression.

Each predictor matched exactly one adapter. Baseline status does not exclude A1 from the monthly adapter; its declared contract is valid.

### Monthly callable

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

The direct function requires exactly `periods_ahead`, an integer from 1 through 24. Its adapter also requires `horizon_unit` equal to `month` or `period`. Response fields include objective/target, model identifier/version, chronological period/prediction pairs, provenance, limitations and `business_approved: false`.

The monthly anchor is the stored September 2026 source cutoff, so the example returns October/November 2026, not automatically the next months after today's date. The baseline deployment state repeats August's eligible count of 8; its historical evaluation used June's value of 19. Do not reuse deployment predictions as the old evaluation or label the October output as a future month on 3 November 2026. Refreshing this state requires a new validated data/model version, not editing the existing bundle.

### Feature-row callable

```python
from prediction.tabular_regression import predict_tabular_regression

result = predict_tabular_regression(
    {
        "rows": [
            {"quantity": 4, "item_code": "FG00100"},
            {"quantity": 10, "item_code": "FG00087"},
        ],
        "expected_objective_id": "nop-domestic-confirmed-date-line-value",
        "expected_dataset_id": "nop-domestic-confirmed-date-line-value",
        "expected_dataset_version": "1.0.0",
    },
    model_path=(
        "models/business_regression/nop_domestic_invoice_line_value/"
        "v2/item_quantity_median_baseline.joblib"
    ),
)
```

These example features come from the delivered actual-derived request. Each row must have exactly the documented quantity/item-code schema. Quantity must be a finite native number meeting the recorded minimum; numeric strings, booleans, missing/extra fields and blank codes are rejected. Positive-quantity normalization applies to A6/A7. Feature order is fixed internally as `quantity`, `item_code`. Unknown codes follow the recorded fallback/encoding policy and are counted explicitly.

Responses include row-index/prediction pairs, model identity/version, objective/target, dataset identity/version/hash, provenance, unknown-category count, limitations and false approval status. Fitted preprocessing is in the bundles; callers must not fit another scaler/encoder.

### Routing and preflight dependencies

**Feature-row routing is a remaining integration responsibility.** The existing dynamic query service's default forecast adapter is monthly, its request schema has no `rows` field, and its forecast execution passes horizon inputs. It therefore does not automatically invoke A4-A7 as row estimators. The supplied tabular callable/adapter works independently; the integration teammate owns connecting supplied feature rows to it. No such framework feature was implemented here.

`model_assets` reports dependency issues; consumers must exclude or block incompatible candidates before loading. Direct monthly inference checks artifact integrity and bundle/metadata contracts but does not itself enforce dependency versions or rehash live prepared/source data. Direct tabular inference enforces recorded dependencies and optional expected dataset identities, but it also does not independently rehash the live dataset/source files. Use existing model/dataset discovery and fingerprint matching as preflight for direct calls; do not infer that a successful unpickle proves current data compatibility or calendar freshness.

## 5. Runtime and packaging requirements

The current passing interpreter is:

`C:\Users\Tanisha\AppData\Local\Programs\Python\Python312\python.exe`

| Runtime component | Verified version | Sidecar compatibility |
| --- | --- | --- |
| Python | 3.12.10 | Recorded and checked |
| scikit-learn | 1.8.0 | Recorded and checked |
| NumPy | 2.4.4 | Recorded and checked |
| pandas | 3.0.2 | Recorded and checked |
| joblib | 1.5.3 | Recorded and checked |
| SciPy | 1.17.1 | Verified transitive runtime dependency; not independently version-pinned in these sidecars |
| threadpoolctl | 3.6.0 | Verified transitive runtime dependency; not independently version-pinned in these sidecars |

The existing project `.venv\Scripts\python.exe` reports Python 3.12.10 but scikit-learn **1.9.1**, so it is not the verified artifact environment. The root `requirements.txt` is unpinned and alone does not reproduce these versions. The integration owner must select or provision a matching isolated runtime using recorded versions and verify compatibility there. No package or environment change was made.

Set `PYTHONPATH=src` from the repository root. Ship the existing prediction/feature modules, including `src/prediction/tabular_estimators.py`, `src/features/tabular_regression.py`, both inference modules and their adapters. New custom classes must remain importable at their serialized module paths. Inference was verified without a training-session state or a new fit.

## 6. Four remaining integration failures

The [previous executed results](../evaluation/actual_data_ml_assessment/v2/framework_inventory_regression_results.json) and [full transcript](../evaluation/actual_data_ml_assessment/v2/framework_inventory_regression_transcript.txt) show **four failures, zero errors, zero skips**. Every failure is the fixed-count assertion `3 != 2`. The four named unit tests were reviewed, not rerun or modified during this handoff.

Their `2` encodes the earlier inventory containing only monthly Linear Regression and Random Forest. The new, explicitly compatible last-value baseline increases the applicable inventory to three. Correct behavior derives expected identity/version sets from the validated selected inventory rather than replacing a permanent constant 2 with a permanent constant 3.

| Existing test / failing line | Fixed assumption | Correct behavior and current probe |
| --- | --- | --- |
| `test_unseen_invoice_forecast_uses_all_compatible_actual_models`, [line 29](../tests/test_dynamic_business_query.py#L29) | Exactly two predictor responses | Return A1-A3 once each, with correct versions, three ordered October-December periods each, no model failures, exploratory approval and `partially_answered` scope. Current read-only probe passed. Validate all outputs rather than only list positions 0 and 1. |
| `test_plan_is_reproducible_and_includes_dataset_and_model_hashes`, [line 118](../tests/test_dynamic_business_query.py#L118) | Exactly two planned models | Both repeated plans must match, with one entry per eligible selected identity/version and matching artifact hash, plus the current dataset fingerprint. A1-A3 were all included; current probe passed. |
| `test_dependency_mismatch_blocks_before_unpickling`, [line 127](../tests/test_dynamic_business_query.py#L127) | Exactly two model failures | Under the mismatch probe, one `incompatible_dependency_versions` failure per selected monthly identity, no predictions and `unsupported` status. All three were blocked; patched `joblib.load` had **zero calls**. Current probe passed. |
| `test_fresh_process_uses_same_entry_point_and_json_output`, [line 149](../tests/test_dynamic_business_query.py#L149) | Exactly two model responses, despite two being the requested horizon | The new process must return A1-A3 with matching versions and two periods per predictor. Current probe returned valid JSON, `answered`, false business approval and zero model failures. `answered` is execution/scope status, not production approval. |

The integration owner should compare expected and actual identity/version sets, check uniqueness and per-predictor horizon/output validity, retain artifact/dataset hash and dependency assertions, and keep approval checks. Merely relaxing the test to `len >= 2` could hide missing, duplicate or misrouted predictors. A baseline should not be suppressed solely to satisfy the old count.

For the exact repeated structured plan in this audit:

- Plan ID: `992618ff6379fe360d686f0dde8e18ba66165b6be09db8789349f91a010b8317`.
- Dataset SHA-256: `807bb312577bb595cdb22d28dd227c0fc23e52898ab42dbe73b99f7d4f444b95`.
- Models: A1-A3 with their identities, versions and artifact hashes listed above.
- Repeated plan equality: true.
- Dependency mismatch status: `unsupported`; failures: three; unpickle calls: zero.

These functional probes do not change the recorded unit-test failures into passes. The earlier ML assessment recorded 52 distinct selected ML/discovery checks passing across its runs. No ML training tests or complete repository suite were rerun during this handoff, and no full-suite success is claimed.

## 7. Fresh-process inference evidence from this handoff

Each of the seven artifacts was loaded in its own new Python process through its existing compatible adapter, with two predictions, matching model identity/version, finite numeric values, JSON serialization and false business approval. Child return codes were zero; stderr was empty.

| Ref | Predicted values, rounded to six decimal places | Output scope | Status |
| --- | ---: | --- | --- |
| A1 | 8.000000 / 8.000000 | October / November 2026 | PASS |
| A2 | 12.142857 / 11.214286 | October / November 2026 | PASS |
| A3 | 14.911875 / 14.911875 | October / November 2026 | PASS |
| A4 | 337475.771951 / 966593.103896 | Actual-derived input rows 0 / 1 | PASS |
| A5 | 197293.066096 / 870266.425492 | Actual-derived input rows 0 / 1 | PASS |
| A6 | 212400.000000 / 900000.000000 | Actual-derived input rows 0 / 1 | PASS |
| A7 | 221103.172724 / 949387.186473 | Actual-derived input rows 0 / 1 | PASS |

The tabular inputs were the two actual-derived rows in [the delivered request](../evaluation/actual_data_ml_assessment/v2/example_tabular_request.json), shown above. These outputs demonstrate operational inference only; they are not new evaluation metrics or business outcomes. Existing full 30-row tabular reproduction and earlier fresh-process evidence remain in [all-model verification](../evaluation/actual_data_ml_assessment/v2/all_model_inference_verification.json).

## 8. Guide accuracy and exploratory limitations

The integration guide was checked in full. It consistently identifies all actual-source predictors as exploratory, states `business_approved: false`, distinguishes the two baselines, rejects the new Ridge as a replacement and does not promise a production champion. Its initial collection statement and target description explicitly exclude recognized revenue/profit meaning. Its monthly section states that the stored cutoff does not follow today's date and that the 1-24 horizon is a software bound, not a validated business horizon. Its evaluation section labels the reused old test as a retrospective audit. **No incorrect approval or production-readiness claim was identified, and no guide edit was needed.**

Limitations remain:

- The monthly test has only two observed months; Linear Regression and Random Forest did not beat last value (MAE/RMSE 7.00/8.06). Seasonal reliability and a useful business forecast horizon are unestablished.
- The line-value target is a restricted stored raw field with unresolved amount/quantity semantics, sparse items, excluded ambiguous dates and unknown extract completeness. It cannot be relabeled as financial performance.
- A6's development reference-macro MAE was 77,135.63 versus A7's 139,302.56; A7 won zero folds. This supports baseline reference use only, not promotion.
- The old 30-row test was already inspected before v2 optimization. V2 audit scores do not establish independent generalization or improvement.
- Model/source fingerprints detect byte changes but do not establish business authenticity, complete capture, semantic approval, calendar freshness or production authorization.

## 9. Responsibilities and outstanding actions

| Owner | Outstanding dependency / exact next action |
| --- | --- |
| Integration owner | Update the four named tests to assert eligible identity/version sets, uniqueness, horizon/schema, hashes and guards; run that suite after changing the tests. No change was made here. |
| Integration owner | Consume the declared callable/adapter family. Connect row inputs to the existing tabular interface where required; the monthly dynamic entry point does not supply them. Preserve target and baseline/ML distinctions. |
| Integration owner | Use a runtime matching artifact dependencies, distribute required Python modules plus sidecars, and preflight original-source/prepared-data hashes. Resolve the current scikit-learn 1.9.1 project-environment mismatch outside this handoff. |
| Integration owner | Preserve exploratory approval/limitations in responses; do not interpret `answered` as approval, choose a business champion from these artifacts or label source-cutoff estimates as current future periods. Apply a defined data-freshness policy. |
| Integration and artifact-release owners | If byte-level metadata immutability is required, include sidecar hashes in a future versioned release manifest. This report records current hashes without modifying the existing manifest. |
| Business/data owners | Confirm document identity scope, lifecycle inclusion/cancellations/returns and event-date interpretation; provide reconciled complete mature monthly extracts and evidence distinguishing genuine zero activity from missing capture. |
| Business/data owners | Confirm item identity, compatible physical quantity units, amount currency/tax/additive grain and recognition basis. Provide aligned recognized revenue, realized costs and expenses before profit modelling. |
| Business/data owners | Supply signed dated inventory movements/opening or snapshot balances for inventory, and stable customer/cohort identities with matured outcomes for propensity. Existing artifacts do not cover those targets. |
| ML owner | After these evidence gaps are resolved, freeze a genuinely unseen prospective evaluation, prepare a new version reproducibly, compare against the saved baselines and issue new artifacts without replacing existing versions. Current assessment requires no additional blind retraining. |

For monthly model improvement, the previous assessment proposes at least 24 complete months for a modest nonseasonal 12/6/6 evaluation; this is a study design rather than a universal guarantee, and seasonal evaluation needs additional depth. Item histories currently span at most four observed months and require substantially longer complete series. No absent periods should be generated or zero-filled to reach a sample target.

## 10. Reproduce the read-only discovery/manifest check

Run with the matching interpreter from the repository root; this code performs no fit or file write:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
```

```python
import json
from pathlib import Path
from business_prediction.query_assets import model_assets, dataset_assets, sha256

root = Path.cwd()
manifest = json.loads(
    (root / "evaluation/actual_data_ml_assessment/v2/delivery_manifest.json")
    .read_text(encoding="utf-8")
)
expected = {
    (m["model_identifier"], m["model_version"]): m
    for m in manifest["actual_artifacts"]
}
assets, failures = model_assets(root / "models", root)
datasets, dataset_failures = dataset_assets(root / "data", root)
assert not failures and not dataset_failures
actual = {
    (a["metadata"]["model_identifier"], a["metadata"]["model_version"]): a
    for a in assets
}
assert len(actual) == len(assets), "Duplicate model identity/version"
assert actual.keys() == expected.keys()
for identity, asset in actual.items():
    delivered = expected[identity]
    meta = asset["metadata"]
    assert not asset["dependency_issues"]
    assert asset["path"].resolve() == (root / delivered["artifact_path"]).resolve()
    assert asset["sidecar"].resolve() == (root / delivered["metadata_path"]).resolve()
    assert sha256(asset["path"]) == delivered["artifact_sha256"] == meta["artifact_sha256"]
    assert meta["business_approved"] is False
    matches = [
        d for d in datasets
        if d["metadata"]["dataset_sha256"] == meta["dataset_sha256"]
    ]
    assert len(matches) == 1
    print(identity, "PASS")
```

## 11. Executed verification summary

```json
{
  "verified_at_utc": "2026-11-03T16:59:08.462077+00:00",
  "manifest_sha256": "1e23c478764ecb389ef9a6547f4fc3032cca5e8bcaf48de5564a940c38d530e4",
  "expected_artifacts": 7,
  "discovered_exact_identity_version_pairs": 7,
  "ml_estimators": 5,
  "baselines": 2,
  "model_discovery_failures": 0,
  "dataset_discovery_failures": 0,
  "dependency_issues": 0,
  "fresh_process_predictors_reverified": 7,
  "protected_files_unchanged": 123,
  "original_source_files_unchanged": 17,
  "historical_integration_test_failures_remaining": 4,
  "dependency_probe_unpickle_calls": 0,
  "teammate_implementation_or_tests_modified": false,
  "retraining_performed": false,
  "full_suite_rerun": false,
  "business_approved_models": 0,
  "business_champion": null
}
```

The existing ML delivery is intact and independently executable for its documented exploratory targets. Closing the integration test assertions, routing, runtime and freshness dependencies belongs to the integration handoff; business-semantic approval and new reliable forecast performance remain external evidence requirements.

