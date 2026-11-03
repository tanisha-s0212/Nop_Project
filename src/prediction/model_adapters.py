"""Trusted inference adapters for existing artifact families, not business questions."""

from .monthly_regression import predict_monthly_objective, MAX_PERIODS_AHEAD


class MonthlyRegressionQueryAdapter:
    adapter_id = "monthly_regression_v1"

    def supports(self, metadata):
        declared = metadata.get("inference_adapter")
        if declared:
            return declared == self.adapter_id
        # Compatibility with the two existing artifacts; no artifact is rewritten.
        return (metadata.get("algorithm") in {"linear_regression", "random_forest"}
                and metadata.get("business_approved") is False
                and all(key in metadata for key in ("training_periods", "dataset_sha256", "source_provenance")))

    def predict(self, path, inputs):
        if inputs.get("horizon_unit") not in {"month", "period"}:
            raise ValueError("this artifact forecasts monthly observations only")
        steps = inputs["periods_ahead"]
        if type(steps) is not int or not 1 <= steps <= MAX_PERIODS_AHEAD:
            raise ValueError(f"this artifact supports 1 through {MAX_PERIODS_AHEAD} future monthly periods")
        return predict_monthly_objective({"periods_ahead": steps}, model_path=path)


class TabularRegressionInferenceAdapter:
    """ML adapter for feature-row regression; callers supply rows, not horizons."""
    adapter_id = "tabular_regression_v1"

    def supports(self, metadata):
        return metadata.get("inference_adapter") == self.adapter_id and metadata.get("problem_type") == "regression"

    def predict(self, path, inputs):
        from .tabular_regression import predict_tabular_regression
        return predict_tabular_regression(inputs, model_path=path)
