"""Focused synthetic-only tests for the invoice-volume modeling workflow."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import joblib
import pandas as pd

from features.invoice_volume import FEATURE_COLUMNS, build_feature_row, build_supervised_features
from prediction import predict_invoice_volume
from training.train_invoice_volume import generate_synthetic_dataset, train_and_evaluate


class InvoiceVolumeModelTests(unittest.TestCase):
    def test_synthetic_generation_is_reproducible_and_labeled(self):
        with tempfile.TemporaryDirectory() as temp:
            first = generate_synthetic_dataset(Path(temp) / "first.csv", observations=132, seed=71)
            second = generate_synthetic_dataset(Path(temp) / "second.csv", observations=132, seed=71)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(len(first), 132)
        self.assertTrue((first["data_mode"] == "synthetic").all())
        self.assertTrue(pd.api.types.is_integer_dtype(first["invoice_count"]))
        self.assertTrue(first["provenance"].str.contains("seed=71").all())
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "observations"):
                generate_synthetic_dataset(Path(temp) / "bad.csv", observations=121.5)

    def test_features_use_prior_values_and_reject_insufficient_history(self):
        periods = pd.period_range("2021-01", periods=15, freq="M").astype(str).tolist()
        counts = list(range(10, 25))
        row = build_feature_row("2022-04", periods, counts)
        self.assertEqual(tuple(row), FEATURE_COLUMNS)
        self.assertEqual(row["lag_1"], 24)
        self.assertEqual(row["lag_3"], 22)
        self.assertEqual(row["lag_6"], 19)
        self.assertEqual(row["lag_12"], 13)
        self.assertEqual(sum(row[f"month_{month:02d}"] for month in range(1, 13)), 1)
        with self.assertRaisesRegex(ValueError, "At least 12"):
            build_feature_row("2022-04", periods[:11], counts[:11])
        with self.assertRaisesRegex(ValueError, "Invalid monthly period"):
            build_feature_row("not-a-month", periods, counts)
        with self.assertRaisesRegex(ValueError, "Invalid monthly period"):
            build_feature_row("2021/01", periods, counts)
        with self.assertRaisesRegex(ValueError, "consecutive"):
            build_feature_row("2022-04", periods[:11] + periods[12:], counts[:11] + counts[12:])

    def test_history_rejects_duplicate_reversed_and_missing_values(self):
        periods = pd.period_range("2020-01", periods=12, freq="M").astype(str).tolist()
        counts = [100 + i for i in range(12)]
        cases = [
            (periods[:5] + [periods[4]] + periods[6:], counts),
            (list(reversed(periods)), list(reversed(counts))),
            (periods, counts[:5] + [None] + counts[6:]),
            (periods, counts[:5] + [float("nan")] + counts[6:]),
            (periods, counts[:5] + [float("inf")] + counts[6:]),
            (periods, counts[:5] + [True] + counts[6:]),
        ]
        for bad_periods, bad_counts in cases:
            with self.subTest(bad_periods=bad_periods, bad_counts=bad_counts):
                with self.assertRaises(ValueError):
                    build_feature_row("2021-01", bad_periods, bad_counts)

    def test_train_artifact_and_recursive_independent_prediction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_path = root / "data.csv"
            generate_synthetic_dataset(data_path, observations=144, seed=19)
            features, targets = build_supervised_features(pd.read_csv(data_path))
            self.assertEqual(len(features), len(targets))
            self.assertEqual(tuple(features.columns), FEATURE_COLUMNS)
            result = train_and_evaluate(
                data_path,
                root / "model.joblib",
                root / "metadata.json",
                root / "metrics.json",
                root / "baseline.json",
                seed=19,
            )
            self.assertGreaterEqual(result["metrics"]["test_observations"], 12)
            self.assertGreaterEqual(result["metrics"]["mae"], 0)
            response = predict_invoice_volume(
                {"periods_ahead": 4}, model_path=root / "model.joblib", metadata_path=root / "metadata.json"
            )
            self.assertEqual(len(response["prediction_periods"]), 4)
            self.assertTrue(all(item["predicted_invoice_volume"] >= 0 for item in response["prediction_periods"]))
            self.assertEqual(
                [item["period"] for item in response["prediction_periods"]],
                ["2023-01", "2023-02", "2023-03", "2023-04"],
            )
            self.assertEqual(response["data_provenance"]["training_data_mode"], "synthetic")
            json.dumps(response)
            repeated = train_and_evaluate(
                data_path,
                root / "model_repeat.joblib",
                root / "metadata_repeat.json",
                root / "metrics_repeat.json",
                root / "baseline_repeat.json",
                seed=19,
            )
            self.assertEqual(result["metrics"], repeated["metrics"])
            self.assertEqual(result["baseline"], repeated["baseline"])
            response_repeat = predict_invoice_volume(
                {"periods_ahead": 4}, model_path=root / "model_repeat.joblib", metadata_path=root / "metadata_repeat.json"
            )
            self.assertEqual(response["prediction_periods"], response_repeat["prediction_periods"])

            incompatible = joblib.load(root / "model.joblib")
            incompatible["artifact_format_version"] = 99
            joblib.dump(incompatible, root / "incompatible.joblib")
            with self.assertRaisesRegex(ValueError, "format version"):
                predict_invoice_volume({"periods_ahead": 1}, model_path=root / "incompatible.joblib")
            tampered = bytearray((root / "model.joblib").read_bytes())
            tampered[-1] ^= 1
            tampered_path = root / "tampered.joblib"
            tampered_path.write_bytes(tampered)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                predict_invoice_volume(
                    {"periods_ahead": 1}, model_path=tampered_path, metadata_path=root / "metadata.json"
                )

            child_env = os.environ.copy()
            child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            child = subprocess.run(
                [sys.executable, "-c", "import json,sys; from prediction import predict_invoice_volume; print(json.dumps(predict_invoice_volume({'periods_ahead':2}, model_path=sys.argv[1])))", str(root / "model.joblib")],
                cwd=Path(__file__).resolve().parents[1],
                env=child_env,
                check=True,
                capture_output=True,
                text=True,
            )
            child_response = json.loads(child.stdout)
            self.assertEqual(len(child_response["prediction_periods"]), 2)
            self.assertEqual(child_response["data_provenance"]["training_data_mode"], "synthetic")
            custom_history = [
                {"period": str(period), "invoice_count": float(value)}
                for period, value in zip(pd.period_range("2020-01", periods=12, freq="M"), range(100, 112))
            ]
            overridden = predict_invoice_volume(
                {"periods_ahead": 2, "historical_monthly_counts": custom_history},
                model_path=root / "model.joblib",
                metadata_path=root / "metadata.json",
            )
            self.assertEqual(overridden["prediction_periods"][0]["period"], "2021-01")
            self.assertIn("unverified", overridden["data_provenance"]["prediction_history_source"])

    def test_invalid_requests_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "periods_ahead"):
            predict_invoice_volume({"periods_ahead": True})
        with self.assertRaisesRegex(ValueError, "unsupported"):
            predict_invoice_volume({"periods_ahead": 1, "target": "real_nop"})
        with self.assertRaisesRegex(ValueError, "at least 12"):
            predict_invoice_volume({"periods_ahead": 1, "historical_monthly_counts": []})
        periods = pd.period_range("2020-01", periods=12, freq="M").astype(str).tolist()
        duplicate_history = [{"period": p, "invoice_count": 10} for p in periods]
        duplicate_history[5]["period"] = duplicate_history[4]["period"]
        with self.assertRaisesRegex(ValueError, "consecutive"):
            predict_invoice_volume({"periods_ahead": 1, "historical_monthly_counts": duplicate_history})
        bad_date_history = [{"period": p, "invoice_count": 10} for p in periods]
        bad_date_history[0]["period"] = "2020/01"
        with self.assertRaisesRegex(ValueError, "YYYY-MM"):
            predict_invoice_volume({"periods_ahead": 1, "historical_monthly_counts": bad_date_history})
        huge_count_history = [{"period": p, "invoice_count": 10} for p in periods]
        huge_count_history[-1]["invoice_count"] = 10**1000
        with self.assertRaisesRegex(ValueError, "finite non-negative"):
            predict_invoice_volume({"periods_ahead": 1, "historical_monthly_counts": huge_count_history})

    def test_training_rejects_tampered_synthetic_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_path = root / "data.csv"
            data = generate_synthetic_dataset(data_path, observations=132, seed=31)
            data.loc[50, "invoice_count"] += 1
            data.to_csv(data_path, index=False)
            with self.assertRaisesRegex(ValueError, "do not match the reproducible"):
                train_and_evaluate(data_path, root / "model.joblib", seed=31)


if __name__ == "__main__":
    unittest.main()
