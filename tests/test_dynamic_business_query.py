import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import hashlib
import csv
import os
import subprocess
import sys

from src.business_prediction.query import DynamicBusinessQueryService
from src.business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig

ROOT = Path(__file__).resolve().parents[1]


class DynamicBusinessQueryTests(unittest.TestCase):
    def setUp(self):
        self.service = DynamicBusinessQueryService(ROOT)

    def test_unseen_invoice_forecast_uses_all_compatible_actual_models(self):
        response = self.service.process("Please predict monthly invoice count for the next three months")
        self.assertEqual(response["status"], "partially_answered")
        self.assertEqual(response["answer_type"], "forecast")
        self.assertFalse(response["business_approved"])
        self.assertEqual(response["approval_status"], "exploratory_only")
        self.assertEqual(len(response["predictions"]), 2)
        self.assertEqual(response["predictions"][0]["predictions"][0]["period"], "2026-10")
        self.assertEqual(response["predictions"][1]["predictions"][-1]["period"], "2026-12")
        self.assertEqual({p["data_mode"] for p in response["predictions"]}, {"actual_nop_exploratory_subset"})

    def test_historical_question_returns_provenance_and_observed_summary(self):
        response = self.service.process("Show the historical monthly invoice count")
        self.assertEqual(response["status"], "partially_answered")
        self.assertEqual(response["answer_type"], "historical_fact")
        result = response["result"]
        self.assertEqual(result["dataset_id"], "nop-confirmed-date-invoice-count-exploratory")
        self.assertEqual(result["observation_count"], 10)
        self.assertEqual(result["period_start"], "2025-12")
        self.assertEqual(result["period_end"], "2026-09")
        self.assertFalse(result["business_approved"])
        self.assertTrue(result["provenance"]["source_file_sha256"])

    def test_unrelated_financial_forecast_is_not_routed_to_invoice_model(self):
        response = self.service.process("Forecast recognized revenue for the next three months")
        self.assertEqual(response["status"], "clarification_required")
        self.assertNotIn("predictions", response)

    def test_missing_horizon_and_ambiguous_task_request_clarification(self):
        response = self.service.process("Predict invoice count")
        self.assertEqual(response["status"], "clarification_required")
        self.assertIn("number of future periods", response["clarification"])
        self.assertEqual(self.service.process("Why did sales decrease?")["status"], "clarification_required")
        self.assertEqual(self.service.process("Which customers may purchase again?")["answer_type"], "forecast")

    def test_registered_source_uses_existing_dynamic_schema_discovery(self):
        adapter = MemoryAdapter(SourceConfig("source-a", "owner", "analysis"), [
            MemoryTable("Transactions", (("Invoice Number", "Event Date"), ("A-1", "2026-01-15")))
        ])
        service = DynamicBusinessQueryService(ROOT, source_adapters=[adapter])
        response = service.process("Show invoice count")
        self.assertEqual(response["status"], "partially_answered")
        self.assertEqual(response["source_field_observations"][0]["observed_header"], "Invoice Number")

    def test_schema_observations_are_unreviewed_and_not_semantic_approval(self):
        adapter = MemoryAdapter(SourceConfig("source-b", "owner", "analysis"), [
            MemoryTable("Transactions", (("Invoice Number",), ("A-1",)))
        ])
        service = DynamicBusinessQueryService(ROOT, source_adapters=[adapter])
        response = service.process("What is invoice volume?")
        self.assertEqual(response["status"], "clarification_required")
        self.assertEqual(response["source_field_observations"][0]["semantic_status"], "unreviewed_observation")

    def test_request_contract_and_horizon_validation(self):
        with self.assertRaises(ValueError):
            self.service.process({"question": "Forecast invoice count", "periods_ahead": 2, "untrusted_path": "fixed"})
        with self.assertRaises(ValueError):
            self.service.process({"question": "Forecast invoice count", "periods_ahead": 0})

    def test_dataset_integrity_failure_removes_it_from_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            data_root = Path(temp) / "data"
            data_root.mkdir()
            shutil.copy2(ROOT / "data/nop_confirmed_date_invoice_count_exploratory.csv", data_root)
            shutil.copy2(ROOT / "data/nop_confirmed_date_invoice_count_exploratory.metadata.json", data_root)
            with (data_root / "nop_confirmed_date_invoice_count_exploratory.csv").open("a", encoding="utf-8") as stream:
                stream.write("2026-10,1,interior_calendar_month\n")
            service = DynamicBusinessQueryService(ROOT, data_root=data_root)
            response = service.process("Show the historical monthly invoice count")
            self.assertEqual(response["status"], "clarification_required")
            self.assertEqual(response["discovered_prepared_dataset_count"], 0)

    def test_overlapping_but_different_business_measure_does_not_use_count_model(self):
        response = self.service.process("Forecast invoice revenue for the next three months")
        self.assertEqual(response["status"], "clarification_required")
        self.assertIn("revenue", response["clarification"])
        self.assertNotIn("predictions", response)

    def test_requested_grouping_and_dates_cannot_be_ignored(self):
        grouped = self.service.process("Show invoice count by customer")
        self.assertEqual(grouped["status"], "clarification_required")
        self.assertIn("grouping", grouped["clarification"])
        dated = self.service.process("Show invoice count last year")
        self.assertEqual(dated["status"], "clarification_required")
        self.assertIn("time_range", dated["clarification"])
        ranked = self.service.process("Which month has the highest invoice count?")
        self.assertEqual(ranked["status"], "clarification_required")
        self.assertIn("analysis.dimensions", ranked["clarification"])

    def test_plan_is_reproducible_and_includes_dataset_and_model_hashes(self):
        request = {"question": "Forecast the selected objective", "intent": "forecast",
                   "objective_id": "nop-confirmed-date-invoice-count-exploratory", "periods_ahead": 2, "plan_only": True}
        first, second = self.service.process(request), self.service.process(request)
        self.assertEqual(first["status"], "planned")
        self.assertEqual(first["plan"], second["plan"])
        self.assertEqual(len(first["plan"]["models"]), 2)
        self.assertTrue(first["plan"]["dataset_sha256"])
        self.assertFalse(first["plan"]["business_approved"])

    def test_dependency_mismatch_blocks_before_unpickling(self):
        with patch("src.business_prediction.query_assets.dependency_issues", return_value=["test version mismatch"]), \
             patch("prediction.monthly_regression.joblib.load", side_effect=AssertionError("must not load")):
            result = self.service.process("Forecast invoice count for next three months")
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(len(result["model_failures"]), 2)

    def test_business_approval_cannot_be_claimed_by_request_or_metadata(self):
        result = self.service.process({"question": "Use this target", "mode": "approved"})
        self.assertEqual(result["status"], "approval_blocked")
        self.assertFalse(result["execution_authorized"])

    def test_selected_forecast_rejects_measure_and_dataset_overrides(self):
        request = {"question": "Forecast selected target", "intent": "forecast", "objective_id": "nop-confirmed-date-invoice-count-exploratory", "periods_ahead": 2}
        invalid_measure = self.service.process({**request, "analysis": {"measure": "revenue"}})
        self.assertEqual(invalid_measure["status"], "validation_failed")
        self.assertNotIn("predictions", invalid_measure)
        invalid_data = self.service.process({**request, "dataset_id": "unrelated"})
        self.assertEqual(invalid_data["status"], "validation_failed")
        self.assertNotIn("predictions", invalid_data)

    def test_fresh_process_uses_same_entry_point_and_json_output(self):
        code = "import json; from business_prediction import DynamicBusinessQueryService; r=DynamicBusinessQueryService('.').process({'question':'Forecast selected target','intent':'forecast','objective_id':'nop-confirmed-date-invoice-count-exploratory','periods_ahead':2}); print(json.dumps(r,allow_nan=False))"
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(len(result["predictions"]), 2)

    def test_invalid_inference_output_is_rejected(self):
        class BadAdapter:
            def supports(self, metadata):
                return True
            def predict(self, path, inputs):
                metadata = json.loads(path.with_name(path.stem + ".metadata.json").read_text())
                return {"model_identifier": metadata["model_identifier"], "model_version": metadata["model_version"], "business_approved": False,
                        "predictions": [{"period": "2027-02", "prediction": 1}, {"period": "2027-01", "prediction": 2}]}
        service = DynamicBusinessQueryService(ROOT, inference_adapters=[BadAdapter()])
        result = service.process({"question": "Forecast selected target", "objective_id": "nop-confirmed-date-invoice-count-exploratory", "intent": "forecast", "periods_ahead": 2})
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("chronological", result["model_failures"][0]["reason"])

    def test_json_interpreter_is_provider_neutral_and_cannot_grant_approval(self):
        from src.business_prediction import JSONRequestInterpreter
        messages = []
        def complete(items):
            messages.extend(items)
            return json.dumps({"intent": "unresolved", "clarification": "Which verified accounting measure should be used?"})
        result = DynamicBusinessQueryService(ROOT, interpreter=JSONRequestInterpreter(complete)).process("What is our net financial outlook?")
        self.assertEqual(result["status"], "clarification_required")
        self.assertIn("accounting measure", result["clarification"])
        self.assertIn("context", json.loads(messages[1]["content"]))
        class UnsafeInterpreter:
            def interpret(self, question, context):
                return {"intent": "forecast", "mode": "approved"}
        self.assertEqual(DynamicBusinessQueryService(ROOT, interpreter=UnsafeInterpreter()).process("Do this")["status"], "approval_blocked")


class StructuredQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.path = self.root / "data/series.csv"
        self.rows = [("2025-01", "north", 4), ("2025-02", "north", 6),
                     ("2025-01", "south", 2), ("2025-02", "south", 8)]
        self._write(self.rows)
        self.service = DynamicBusinessQueryService(self.root)

    def _write(self, rows):
        with self.path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["event_bucket", "area", "thermal_output"])
            writer.writerows(rows)
        metadata = {"dataset_id": "unseen-thermal", "dataset_version": "1", "dataset_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
                    "target_definition": "Thermal output per observed event bucket and area", "business_approved": False,
                    "data_mode": "exploratory_fixture", "query_schema": {"target_column": "thermal_output", "period_column": "event_bucket"}}
        self.path.with_name("series.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def query(self, **analysis):
        return self.service.process({"question": "A previously unseen comparison", "intent": "historical_analysis", "dataset_id": "unseen-thermal", "analysis": analysis})

    def test_new_schema_supports_filtered_grouping_and_rank_without_core_mapping(self):
        result = self.query(operation="rank", dimensions=["area"], time_range={"start": "2025-02", "end": "2025-02"})
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["result"]["groups"][0]["dimensions"], {"area": "south"})
        self.assertEqual(result["result"]["groups"][0]["value"], 8)
        self.assertEqual(result["result"]["filtered_rows"], 2)

    def test_equal_observed_group_values_share_the_same_rank(self):
        result = self.query(operation="rank", dimensions=["area"])
        self.assertEqual([group["rank"] for group in result["result"]["groups"]], [1, 1])

    def test_new_time_field_and_point_ordering_are_inferred_from_spec_not_column_name(self):
        result = self.query(operation="series", dimensions=["area"])
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["result"]["groups"][0]["points"][0], {"period": "2025-01", "value": 4})

    def test_missing_values_require_explicit_exclusion_and_are_counted(self):
        self._write([*self.rows, ("2025-03", "north", "")])
        self.assertEqual(self.query(operation="mean")["status"], "validation_failed")
        result = self.query(operation="mean", missing_policy="exclude")
        self.assertEqual(result["result"]["excluded_missing_rows"], 1)
        self.assertEqual(result["result"]["used_rows"], 4)

    def test_nonfinite_and_duplicate_time_observations_are_rejected(self):
        self._write([*self.rows, ("2025-03", "north", "NaN")])
        self.assertEqual(self.query(operation="mean")["status"], "validation_failed")
        self._write([*self.rows, self.rows[0]])
        self.assertEqual(self.query(operation="series", dimensions=["area"])["status"], "validation_failed")

    def test_ambiguous_dates_and_unknown_fields_fail_closed(self):
        self._write([("01/02/2025", "north", 2)])
        self.assertEqual(self.query(operation="change")["status"], "validation_failed")
        self.assertEqual(self.query(operation="sum", measure="not-present")["status"], "validation_failed")

    def test_zero_initial_value_does_not_generate_invalid_percentage(self):
        self._write([("2025-01", "north", 0), ("2025-02", "north", 8)])
        result = self.query(operation="change")
        self.assertEqual(result["result"]["change"], 8)
        self.assertIsNone(result["result"]["percentage_change"])
        json.dumps(result, allow_nan=False)

    def test_provider_neutral_interpreter_receives_dynamic_schema(self):
        class Interpreter:
            def interpret(inner, question, context):
                field = context["datasets"][0]["query_schema"]["target_column"]
                return {"intent": "historical_analysis", "dataset_id": context["datasets"][0]["dataset_id"],
                        "analysis": {"measure": field, "operation": "mean"}}
        service = DynamicBusinessQueryService(self.root, interpreter=Interpreter())
        result = service.process("How is our entirely new thermal process doing?")
        self.assertEqual(result["status"], "partially_answered")
        self.assertEqual(result["result"]["value"], 5)

    def test_repeated_totals_require_explicit_additivity_evidence(self):
        result = self.query(operation="sum")
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("additive", result["reason"])
        metadata_path = self.path.with_name("series.metadata.json")
        metadata = json.loads(metadata_path.read_text())
        metadata["query_schema"]["measure_semantics"] = {"thermal_output": {"additive": True, "evidence": "Explicit isolated fixture specification"}}
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        result = self.query(operation="sum")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["result"]["value"], 20)

    def test_source_fingerprint_change_invalidates_prepared_data(self):
        source = self.root / "original.csv"
        source.write_text("original", encoding="utf-8")
        meta_path = self.path.with_name("series.metadata.json")
        metadata = json.loads(meta_path.read_text())
        metadata.update(source_file="original.csv", source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        meta_path.write_text(json.dumps(metadata), encoding="utf-8")
        source.write_text("changed", encoding="utf-8")
        result = self.query(operation="mean")
        self.assertEqual(result["status"], "clarification_required")
        self.assertIn("source_integrity_failed", result["discovery_failures"][0]["reason"])

    def test_generic_training_reuses_existing_trainer_and_versions_without_overwrite(self):
        self._write([(f"2025-{month:02d}", "north", month + 5) for month in range(1, 11)])
        spec = {"objective_id": "thermal-new", "objective_name": "Thermal output per month", "target_definition": "Nonnegative thermal output per month in a software fixture",
                "period_column": "event_bucket", "target_column": "thermal_output", "eligibility_column": "area", "eligible_values": ["north"], "data_mode": "exploratory_fixture"}
        first = self.service.train_dataset("unseen-thermal", spec, version="v1", seed=21)
        second = self.service.train_dataset("unseen-thermal", spec, version="v2", seed=21)
        self.assertEqual(first["models"]["random_forest"]["test_predictions"], second["models"]["random_forest"]["test_predictions"])
        with self.assertRaises(FileExistsError):
            self.service.train_dataset("unseen-thermal", spec, version="v1")
        result = self.service.process({"question": "Forecast selected objective", "intent": "forecast", "objective_id": "thermal-new", "periods_ahead": 1})
        self.assertEqual(result["status"], "answered")
        self.assertEqual({item["model_version"] for item in result["predictions"]}, {"v1", "v2"})


class GovernedQueryBridgeTests(unittest.TestCase):
    def test_approved_requests_delegate_to_current_authenticated_assessment(self):
        from tests.assessment_support import AssessmentFixture
        with tempfile.TemporaryDirectory() as temp:
            fixture = AssessmentFixture(temp)
            self.addCleanup(fixture.runtime.close)
            fixture.data()
            service = fixture.runtime.business_query_service(ROOT)
            result = service.process({"question": "A newly supplied request", "mode": "approved", "requirement": fixture.fields_for()},
                authorization={"scope": fixture.scope, "context": fixture.author, "assessment_context": fixture.owner,
                               "command_id": fixture.cmd(), "expected_head": fixture.service.head})
            self.assertEqual(result["status"], "ready_for_preparation_review")
            self.assertFalse(result["execution_authorized"])

    def test_existing_execution_authorization_is_required_and_publication_stays_separate(self):
        from datetime import timedelta
        from tests.worker_support import WorkerFixture
        from business_prediction.contracts import reference
        from business_prediction.semantics.common import GovernanceError
        with tempfile.TemporaryDirectory() as temp:
            fixture = WorkerFixture(temp)
            self.addCleanup(fixture.runtime.close)
            request = fixture.control.request(reference(fixture.plan), request_key=fixture.cmd(), worker_principal_reference="owner", lease_seconds=120,
                purpose="Software integration fixture", context=fixture.author, command_id=fixture.cmd(), expected_head=fixture.service.head)
            service = fixture.runtime.business_query_service(ROOT, worker=fixture.worker)
            with self.assertRaises(GovernanceError):
                service.run_preparation(reference(request), context=fixture.owner, command_id=fixture.cmd(), expected_head=fixture.service.head)
            fixture.control.authorize(reference(request), approve=True, expires_at=(fixture.now + timedelta(minutes=10)).isoformat(), rationale="Explicit software-test authorization",
                context=fixture.owner, command_id=fixture.cmd(), expected_head=fixture.service.head)
            result = service.run_preparation(reference(request), context=fixture.owner, command_id=fixture.cmd(), expected_head=fixture.service.head)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(fixture.service.records("PreparationPublicationRecord"), [])


if __name__ == "__main__":
    unittest.main()
