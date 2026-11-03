# Synthetic invoice-volume forecast: usage and integration

This workflow provides an executable ML example while approved NOP training data is unavailable. It trains only on the explicitly synthetic dataset at `data/synthetic_monthly_invoice_volume.csv`. Results describe that synthetic series; they are not NOP business performance or an approved production forecast.

## Train and evaluate

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m training.train_invoice_volume
```

The command recreates 180 monthly synthetic observations with fixed seed `20261103`, trains a `RandomForestRegressor`, evaluates a chronological recursive holdout, and writes the model and JSON metadata under `models/` and `evaluation/`. The evaluation estimator is fit only through the pre-holdout cutoff; after evaluation is frozen, the serialized estimator is refit on all 180 months for future prediction. Use `--observations 180 --seed 20261103` to state the defaults explicitly. Training requires the exact generated schema, per-row synthetic/provenance markers, generator seed and target values reproducible by the selected seed; arbitrary or actual data is rejected by this synthetic-only workflow.

Run the focused automated tests with:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest tests.test_invoice_volume_model -v
```

## Prediction function

Import and call the function independently of the training script:

```python
from prediction import predict_invoice_volume

response = predict_invoice_volume({"periods_ahead": 3})
```

By default, inference loads `models/nop_invoice_volume_model.joblib` and starts from the final month in the model-fit history. Predictions are recursive: each predicted count becomes lag history for later requested months. The forecast horizon must be an integer from 1 through 36.

### Request schema

```json
{
  "periods_ahead": 3,
  "historical_monthly_counts": [
    {"period": "2024-01", "invoice_count": 123},
    {"period": "2024-02", "invoice_count": 127}
  ]
}
```

`historical_monthly_counts` is optional. When supplied, provide at least 12 consecutive monthly observations in ascending order, ending in the month before the forecast begins. Counts must be finite non-negative numbers. This package validates shape and chronology only; it does not authenticate source, authorize use, or verify the business meaning of caller-supplied counts. Do not pass unresolved NOP dates or unapproved labels.

Unknown fields, invalid periods/counts, gaps, insufficient history, incompatible artifacts and absent model files raise explicit `ValueError` or `FileNotFoundError` exceptions. A Python MCP adapter can validate/map its structured arguments to this dictionary, call `predict_invoice_volume`, and return the JSON-serializable dictionary. This repository does not implement MCP or UI integration.

### Response schema

```json
{
  "model_identifier": "nop-monthly-invoice-volume-rf",
  "model_version": "1.0.0",
  "prediction_target": "Synthetic illustrative monthly invoice-volume count; not an approved NOP target.",
  "prediction_periods": [
    {"period": "2023-01", "predicted_invoice_volume": 154.2}
  ],
  "data_provenance": {
    "training_data_mode": "synthetic",
    "training_data": {"actual_nop_data_used": false},
    "prediction_history_source": "bundled model-fit history"
  },
  "known_limitations": ["..."]
}
```

The actual response has full provenance metadata. The forecast is a non-negative floating-point regression estimate and may be fractional. No prediction interval or calibrated uncertainty is provided.

## Artifacts

- Dataset: `data/synthetic_monthly_invoice_volume.csv`
- Serialized fitted estimator, feature order, training-cutoff history and provenance: `models/nop_invoice_volume_model.joblib`
- Human-readable model metadata: `models/model_metadata.json`
- Holdout metrics: `evaluation/evaluation_metrics.json`
- Naive baseline comparison: `evaluation/baseline_comparison.json`
- Example request/response: `evaluation/example_request.json` and `evaluation/example_response.json`

Only load `.joblib` files from a trusted location: joblib uses Python object serialization. For the default artifact, inference checks the neighboring `model_metadata.json` SHA-256 before deserialization and then checks model identity and feature order. If using a custom model path, keep the matching metadata file beside it or pass `metadata_path=...`. Metadata records the model artifact SHA-256, data SHA-256 and Python/library versions. Retrain with the documented script if the feature definition changes.

## Intended use and limitations

This is an integration prototype trained on reproducible synthetic counts with trend, annual/semiannual seasonality and seeded noise. It contains no actual NOP invoice records. Its MAE/RMSE measure performance only on a synthetic chronological holdout and must not be interpreted as NOP forecast accuracy. The random forest is not designed to extrapolate long-term trends reliably; recursive errors can compound. No business calendar, source completeness, lifecycle policy, exogenous drivers, production approval, monitoring or deployment service is included. Actual NOP use requires approved source/target semantics, sufficient mature history, leakage-safe evaluation and a new authorized training run.
