import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from openpyxl import Workbook

from src.features.prepare_invoice_volume_exploratory import prepare
from src.training.monthly_regression import train_monthly_regressors
from src.prediction.monthly_regression import predict_monthly_objective


ROOT = Path(__file__).resolve().parents[1]
SPEC = {
    "objective_id": "test-monthly-exploratory", "objective_name": "Test objective",
    "target_definition": "Explicit test fixture target", "period_column": "period",
    "target_column": "target_count", "eligibility_column": "calendar_boundary_status",
    "eligible_values": ["interior_calendar_month"], "data_mode": "actual_nop_exploratory_subset"}


class ActualDataExploratoryTests(unittest.TestCase):
    def _workbook(self, path):
        book = Workbook(); sheet = book.active
        sheet.append(["Invoice Num", "Invoice Date", "TransType"])
        sheet.append(["INV-DEC", "21/12/2025", "GST Tax Invoice"])
        for month, count in enumerate((22, 12, 20, 19, 22, 19, 16, 8), start=1):
            for number in range(count):
                day = 13 + (number % 15)
                sheet.append([f"INV-{month}-{number}", f"{day:02d}/{month:02d}/2026", "GST Tax Invoice"])
        sheet.append(["INV-SEP", "13/09/2026", "GST Tax Invoice"])
        sheet.append(["INV-AMBIG", "05/01/2026", "GST Tax Invoice"])
        sheet.append(["INV-AMBIG", "05/01/2026", "GST Tax Invoice"])
        book.save(path)

    def test_preparation_keeps_distinct_documents_and_rejects_ambiguous_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); source = temp / "fixture.xlsx"
            output = temp / "prepared.csv"; metadata = temp / "prepared.metadata.json"
            self._workbook(source)
            result = prepare(source, output, metadata)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[1]["period"], "2026-01")
            self.assertEqual(int(rows[1]["target_count"]), 22)
            self.assertEqual(result["distinct_references_included"], 140)
            self.assertEqual(result["distinct_references_without_fully_resolved_date_excluded"], 1)
            self.assertEqual(result["ambiguous_date_rows_excluded"], 2)
            self.assertFalse(result["business_approved"])
            self.assertFalse(result["controlled_worker_execution"])

    def test_training_is_chronological_and_persists_independent_models(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); dataset = temp / "series.csv"
            rows = [{"period": f"2025-{m:02d}", "target_count": value,
                     "calendar_boundary_status": "interior_calendar_month"}
                    for m, value in enumerate([10, 12, 9, 13, 11, 14, 8, 7, 9, 6], 1)]
            with dataset.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
            result = train_monthly_regressors(dataset, SPEC, temp / "models", seed=21)
            self.assertEqual(result["split"]["training_count"], 7)
            self.assertEqual(result["split"]["validation_count"], 1)
            self.assertEqual(result["split"]["test_count"], 2)
            self.assertEqual(set(result["models"]), {"linear_regression", "random_forest"})
            for name in result["models"]:
                artifact = temp / "models" / f"{name}.joblib"
                self.assertTrue(artifact.is_file())
                response = predict_monthly_objective({"periods_ahead": 2}, model_path=artifact)
                self.assertEqual([x["period"] for x in response["predictions"]], ["2025-11", "2025-12"])
                self.assertTrue(all(isinstance(x["prediction"], float) and x["prediction"] >= 0 for x in response["predictions"]))
                artifact.write_bytes(artifact.read_bytes() + b"tamper")
                with self.assertRaisesRegex(ValueError, "integrity"):
                    predict_monthly_objective({"periods_ahead": 1}, model_path=artifact)

    def test_independent_process_loads_artifact_and_returns_json(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); dataset = temp / "series.csv"
            rows = [{"period": f"2025-{m:02d}", "target_count": value,
                     "calendar_boundary_status": "interior_calendar_month"}
                    for m, value in enumerate([10, 12, 9, 13, 11, 14, 8, 7, 9, 6], 1)]
            with dataset.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
            train_monthly_regressors(dataset, SPEC, temp / "models", seed=21)
            artifact = temp / "models" / "linear_regression.joblib"
            code = ("import json,sys; sys.path.insert(0,'src'); "
                    "from prediction.monthly_regression import predict_monthly_objective; "
                    "print(json.dumps(predict_monthly_objective({'periods_ahead':1},model_path=sys.argv[1])))")
            env = dict(os.environ); env["PYTHONPATH"] = "src"
            proc = subprocess.run([sys.executable, "-c", code, str(artifact)], cwd=ROOT, env=env,
                                  check=True, capture_output=True, text=True)
            response = json.loads(proc.stdout)
            self.assertEqual(response["model_identifier"], "test-monthly-exploratory-linear_regression")
            self.assertEqual(len(response["predictions"]), 1)

    def test_invalid_request_and_tampered_artifact_are_rejected(self):
        with self.assertRaises(ValueError): predict_monthly_objective({"periods_ahead": True}, model_path="missing.joblib")


if __name__ == "__main__":
    unittest.main()
