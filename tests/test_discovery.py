from copy import deepcopy
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook, load_workbook

from business_prediction.adapters import CSVAdapter, MemoryAdapter, MemoryTable, SourceConfig
from business_prediction.adapters.base import CellError, Formula
from business_prediction.adapters.excel import ExcelAdapter
from business_prediction.discovery import DiscoveryOptions, compare_schemas, discover
from business_prediction.errors import SourceError
from tests.support import bundle


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.config = SourceConfig("arbitrary-source", "test-owner", "synthetic-discovery")

    def test_mixed_types_missingness_and_headers_preserve_positions(self):
        rows = (("token", "value", "clock", "", "repeat", "repeat", "spare"),
                ("a", 1, date(2026, 11, 1), None, "u", "m", None),
                ("b", "2", "03/04/2026", "", "v", "n", None),
                ("c", 3.5, "31/02/2026", " ", "w", "o", None), ())
        saved = deepcopy(rows)
        result = discover(MemoryAdapter(self.config, [MemoryTable("unrelated", rows)])).discovery_result
        table = result["tables"][0]
        self.assertEqual(rows, saved)
        self.assertEqual((table["observed_row_count"], table["schema_field_count"], table["completely_empty_rows"]), (4, 7, 1))
        self.assertEqual(table["fields"][3]["observed"]["missing_counts"],
                         {"null": 1, "empty_text": 1, "whitespace_text": 1, "structurally_absent": 1})
        self.assertEqual(table["fields"][1]["observed"]["type_counts"], {"integer": 1, "text": 1, "float": 1})
        self.assertTrue(table["fields"][1]["observed"]["mixed_types"])
        self.assertEqual([f["position"] for f in table["fields"] if f["duplicate_header"]], [5, 6])
        self.assertTrue(table["fields"][3]["blank_header"])
        self.assertEqual(table["fields"][3]["raw_header"]["value"], "")
        self.assertEqual(table["fields"][6]["observed"]["nonmissing_count"], 0)
        clock = table["fields"][2]["observed"]
        self.assertEqual(clock["temporal_token_counts"], {"native_date": 1, "ambiguous_day_month_text": 1, "invalid_calendar_token": 1})
        self.assertEqual(clock["unambiguous_date_min"], "2026-11-01")

    def test_new_tables_names_and_fields_need_no_core_modification(self):
        first = discover(MemoryAdapter(self.config, [MemoryTable("sensor_grid", (("x",), ("a",), ("b",)))]))
        second = discover(MemoryAdapter(self.config, [
            MemoryTable("another_department", (("q", "r"), ("a", True), ("b", False))),
            MemoryTable("third_table", (("additional",), (7,), (8,)))]))
        self.assertEqual([t["name"] for t in second.discovery_result["tables"]], ["another_department", "third_table"])
        kinds = {c["kind"] for c in compare_schemas(first.discovery_result, second.discovery_result)}
        self.assertTrue({"table_added", "field_added", "table_identity_or_layout_changed"} <= kinds)

    def test_identifier_candidates_are_explicitly_unapproved_and_value_based(self):
        result = bundle().discovery_result
        for field in result["tables"][0]["fields"]:
            self.assertEqual(field["hypotheses"][0]["kind"], "unique_value_candidate")
            self.assertEqual(field["hypotheses"][0]["status"], "hypothesized")
            self.assertEqual(field["hypotheses"][0]["approval_status"], "unreviewed")
            self.assertIn("ordinary measure", field["hypotheses"][0]["explanation"])

    def test_temporal_detection_ignores_names_and_preserves_ambiguity(self):
        rows = (("opaque", "event_date"), ("03/04/2026", 45000), ("15/04/2026", 45001),
                ("04/03/26", 45002), ("2026-12-31", 45003))
        result = bundle(rows).discovery_result["tables"][0]["fields"]
        self.assertEqual(result[0]["observed"]["temporal_token_counts"],
                         {"ambiguous_day_month_text": 1, "single_calendar_reading_text": 1,
                          "century_unresolved_text": 1, "iso_date_text": 1})
        self.assertEqual(result[0]["observed"]["unambiguous_date_min"], "2026-04-15")
        self.assertEqual(result[1]["observed"]["temporal_token_counts"], {})
        self.assertFalse(any(h["kind"] == "temporal_candidate" for h in result[1]["hypotheses"]))

    def test_formula_error_and_nonfinite_cells_are_not_missing_or_keys(self):
        rows = (("expression", "fault", "nonfinite", "bool", "other"),
                (Formula("=1+2"), CellError("#N/A"), float("nan"), True, Decimal("1.10")),
                (Formula("=1+3"), CellError("#REF!"), float("inf"), False, Decimal("2.20")))
        fields = bundle(rows).discovery_result["tables"][0]["fields"]
        self.assertEqual(fields[0]["observed"]["type_counts"], {"formula": 2})
        self.assertEqual(fields[1]["observed"]["nonmissing_count"], 2)
        self.assertEqual(fields[2]["observed"]["nonfinite_numeric_count"], 2)
        for field in fields[:4]:
            self.assertFalse(any(h["kind"] == "unique_value_candidate" for h in field["hypotheses"]))

    def test_row_limits_report_sampling_and_empty_samples(self):
        adapter = MemoryAdapter(self.config, [MemoryTable("series", (("opaque",), ("a",), ("b",), ("a",)))])
        partial = discover(adapter, options=DiscoveryOptions(max_rows=2)).discovery_result
        table = partial["tables"][0]
        self.assertFalse(table["profile_complete"])
        self.assertEqual((table["scanned_row_count"], table["observed_row_count"]), (2, 3))
        self.assertEqual(partial["evidence"][0]["coverage"], "prefix_sample")
        self.assertIn("prefix sample", table["fields"][0]["hypotheses"][0]["explanation"])
        full = discover(adapter).discovery_result
        self.assertFalse(full["tables"][0]["fields"][0]["hypotheses"])
        empty = discover(adapter, options=DiscoveryOptions(max_rows=0)).discovery_result
        self.assertEqual(empty["tables"][0]["scanned_row_count"], 0)

    def test_schema_shape_ignores_count_changes_but_detects_types_and_reordering(self):
        old = bundle().discovery_result
        more = bundle((("opaque", "measure"), ("C", 3), ("D", 4), ("E", 5)), revision=2).discovery_result
        self.assertNotEqual(old["source_version"], more["source_version"])
        self.assertEqual(old["schema_version"], more["schema_version"])
        self.assertEqual(compare_schemas(old, more), [])
        changed = bundle((("measure", "opaque"), (1, "a"), (2, "b")), revision=3).discovery_result
        kinds = {c["kind"] for c in compare_schemas(old, changed)}
        self.assertEqual(kinds, {"field_identity_or_position_changed", "observed_types_changed"})

    def test_csv_preserves_raw_tokens_blank_rows_ragged_and_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"unfamiliar.csv"
            path.write_bytes(b',echo,echo\r\n001,NA,2026-11-01\r\n,,\r\n\r\n002,#N/A,03/04/2026,extra\r\n')
            before = path.read_bytes()
            adapter = CSVAdapter(path, self.config)
            result = discover(adapter).discovery_result["tables"][0]
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(result["schema_field_count"], 4)
            self.assertTrue(result["fields"][0]["blank_header"])
            self.assertFalse(result["fields"][3]["header_present"])
            self.assertEqual(result["fields"][1]["observed"]["nonmissing_count"], 2)
            with adapter.open_snapshot() as snap:
                self.assertEqual(next(snap.iter_rows("table-1")).cells[:2], ("001", "NA"))

    def test_excel_all_sheets_custom_layout_formulas_and_file_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"schema.xlsx"
            book = Workbook()
            a = book.active; a.title = "lab_alpha"
            a.append(["title only"]); a.append([]); a.append([None, "same", "same", "opaque"])
            a.append(["a", 1, "001", datetime(2026, 11, 1, 9)])
            a.append(["b", "=1+2", "NA", "03/04/2026"])
            b = book.create_sheet("lab_beta"); b.append(["other"]); b.append([True])
            book.save(path); book.close()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = discover(ExcelAdapter(path, self.config, header_rows={"lab_alpha": 3})).discovery_result
            self.assertEqual([t["name"] for t in result["tables"]], ["lab_alpha", "lab_beta"])
            self.assertEqual(result["tables"][0]["fields"][1]["observed"]["type_counts"], {"integer": 1, "formula": 1})
            self.assertEqual(result["tables"][0]["fields"][3]["observed"]["temporal_token_counts"],
                             {"native_datetime": 1, "ambiguous_day_month_text": 1})
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            original = load_workbook(path, data_only=False)
            self.assertEqual(original["lab_alpha"]["B5"].value, "=1+2")
            original.close()

    def test_source_changes_during_snapshot_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"changing.csv"; path.write_text('a\n1\n', encoding="utf-8")
            adapter = CSVAdapter(path, self.config)
            with self.assertRaises(SourceError) as caught:
                with adapter.open_snapshot():
                    path.write_text('a\n2\n', encoding="utf-8")  # Synthetic writer, never adapter mutation.
            self.assertEqual(caught.exception.code, "source_changed")

    def test_corrupt_missing_and_resource_limited_sources_are_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"broken.xlsx"; path.write_bytes(b'not a workbook')
            cases = [(ExcelAdapter(path, self.config), "unreadable_source"),
                     (CSVAdapter(Path(tmp)/"missing.csv", self.config), "unreadable_source"),
                     (CSVAdapter(path, self.config, max_bytes=1), "resource_limit")]
            for adapter, code in cases:
                with self.subTest(code=code), self.assertRaises(SourceError) as caught:
                    discover(adapter)
                self.assertEqual(caught.exception.code, code)

    def test_headerless_empty_and_invalid_configurations(self):
        table = MemoryTable("without_header", ((1, "a"), (2, "b")), header_row=None)
        result = discover(MemoryAdapter(self.config, [table, MemoryTable("empty", ())])).discovery_result
        self.assertEqual(result["tables"][0]["observed_row_count"], 2)
        self.assertTrue(all(not f["header_present"] for f in result["tables"][0]["fields"]))
        self.assertEqual(result["tables"][1]["schema_field_count"], 0)
        for limit in (-1, True):
            with self.assertRaises(ValueError):
                DiscoveryOptions(max_rows=limit)

    def test_logs_contain_event_metadata_not_source_values(self):
        with self.assertLogs("business_prediction", level="INFO") as logs:
            discover(MemoryAdapter(self.config, [MemoryTable("safe", (("field",), ("private-sample",)))]))
        self.assertNotIn("private-sample", str(logs.output))
        self.assertTrue(any(record.msg == "discovery.completed" for record in logs.records))

    def test_reader_settings_and_preamble_changes_are_reproducible(self):
        a = MemoryAdapter(self.config, [MemoryTable("view", (("preamble-a",), ("x",), (1,)), header_row=2)])
        b = MemoryAdapter(self.config, [MemoryTable("view", (("preamble-b",), ("x",), (1,)), header_row=2)])
        old, new = discover(a), discover(b)
        self.assertNotEqual(old.source_metadata["source_version"], new.source_metadata["source_version"])
        self.assertEqual(old.discovery_result["schema_version"], new.discovery_result["schema_version"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"dialect.csv"; path.write_bytes(b'x;y\n001;2\n')
            result = discover(CSVAdapter(path, self.config, delimiter=";")).source_metadata
            self.assertEqual(result["adapter_settings"]["delimiter"], ";")
            self.assertEqual(result["adapter_settings"]["value_policy"], "raw_text")

    def test_unknown_encoding_and_legacy_excel_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"legacy.xls"; path.write_bytes(b'a\n1\n')
            for adapter, code in [(CSVAdapter(path, self.config, encoding="unavailable-codec"), "unreadable_source"),
                                  (ExcelAdapter(path, self.config), "unsupported_format")]:
                with self.assertRaises(SourceError) as caught:
                    discover(adapter)
                self.assertEqual(caught.exception.code, code)

    def test_periods_times_and_impossible_short_years_do_not_invent_dates(self):
        rows = (("opaque",), ("2026-11",), ("2026-13",), ("09:30",), ("31/02/26",), ("29/02/00",))
        observed = bundle(rows).discovery_result["tables"][0]["fields"][0]["observed"]
        self.assertEqual(observed["temporal_token_counts"], {
            "year_month_period_text": 1, "invalid_period_token": 1, "iso_time_text": 1,
            "invalid_calendar_token": 1, "century_unresolved_text": 1})
        self.assertIsNone(observed["unambiguous_date_min"])

    def test_removed_tables_fields_and_type_changes_are_reported(self):
        first = MemoryAdapter(self.config, [MemoryTable("one", (("x", "y"), (1, "a"))),
                                            MemoryTable("two", (("z",), (True,)))])
        second = MemoryAdapter(self.config, [MemoryTable("one", (("x",), ("text",)))])
        changes = compare_schemas(discover(first).discovery_result, discover(second).discovery_result)
        self.assertTrue({"field_removed", "table_removed", "observed_types_changed"} <= {c["kind"] for c in changes})


if __name__ == "__main__":
    unittest.main()
