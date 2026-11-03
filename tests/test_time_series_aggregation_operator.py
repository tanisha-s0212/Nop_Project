import unittest

from src.business_prediction.contracts import reference_key
from src.business_prediction.semantics.common import GovernanceError
from src.business_prediction.specifications.operations import default_operation_registry
from src.business_prediction.worker.operators import ApprovedTimeSeriesAggregation, PreparationOperatorRegistry
from src.business_prediction.worker.storage import validate_batch


def ref(name):
    return {"contract_type": "SemanticBinding", "contract_version": "1.0",
            "object_id": name, "object_revision": 1}


class TimeSeriesAggregationTests(unittest.TestCase):
    def setUp(self):
        self.month = ref("month-date")
        self.issuer = ref("issuer")
        self.invoice = ref("invoice-number")
        self.operation = {
            "operation_type": "time_series_aggregation", "operation_version": "1.0",
            "input_grain": "invoice-line", "output_grain": "issuer-month",
            "input_binding_references": [self.month, self.issuer, self.invoice],
            "parameters": {
                "dimensions": [{"binding_reference": self.month, "output_field_id": "period", "bucket": "month"},
                               {"binding_reference": self.issuer, "output_field_id": "issuer-group", "bucket": "native"}],
                "measures": [{"binding_references": [self.issuer, self.invoice], "output_field_id": "document-count", "method": "count_distinct"}],
                "reconciliation_checks": ["input_rows", "distinct_documents"],
                "missing_period_policy": "observed_only"}}
        self.field_ids = {reference_key(self.month): "f-date", reference_key(self.issuer): "f-issuer",
                          reference_key(self.invoice): "f-invoice"}
        self.batch = {"schema": [{"field_id": "f-date", "types": ["date"]},
                                 {"field_id": "f-issuer", "types": ["text"]},
                                 {"field_id": "f-invoice", "types": ["text"]}],
                      "rows": [[{"type": "date", "value": "2025-01-04"}, {"type": "text", "value": "A"}, {"type": "text", "value": "INV-1"}],
                               [{"type": "date", "value": "2025-01-29"}, {"type": "text", "value": "A"}, {"type": "text", "value": "INV-1"}],
                               [{"type": "date", "value": "2025-02-01"}, {"type": "text", "value": "A"}, {"type": "text", "value": "INV-2"}]],
                      "ordinals": [1, 2, 3]}
        self.operator = ApprovedTimeSeriesAggregation()

    def test_monthly_distinct_document_count_is_deterministic_and_observed_only(self):
        self.operator.validate(self.operation)
        accepted, rejected = self.operator.apply(self.batch, self.operation, self.field_ids)
        validate_batch(accepted); validate_batch(rejected)
        self.assertEqual([r[0]["value"] for r in accepted["rows"]], ["2025-01", "2025-02"])
        self.assertEqual([r[2]["value"] for r in accepted["rows"]], [1, 1])
        self.assertEqual(accepted["ordinals"], [1, 2])
        self.assertEqual(rejected["rows"], [])
        self.assertTrue(self.operator.reconcile(self.batch, accepted, rejected, self.operation, self.field_ids))

    def test_operation_is_registered_in_existing_specification_and_worker_registries(self):
        declaration = dict(self.operation, operation_id="monthly-documents")
        validator = default_operation_registry().get("time_series_aggregation", "1.0")
        self.assertTrue(validator.permits_grain_change)
        self.assertEqual(validator.validate(declaration, {"resolver": lambda value: value}), [])
        self.assertIsInstance(PreparationOperatorRegistry().get(declaration), ApprovedTimeSeriesAggregation)

    def test_text_date_is_not_interpreted_as_a_calendar_date(self):
        batch = {**self.batch, "schema": [{"field_id": "f-date", "types": ["text"]}, *self.batch["schema"][1:]],
                 "rows": [[{"type": "text", "value": "01/02/2025"}, *row[1:]] for row in self.batch["rows"]]}
        with self.assertRaises(GovernanceError) as error:
            self.operator.apply(batch, self.operation, self.field_ids)
        self.assertEqual(error.exception.code, "date_bucket_requires_native_date")

    def test_null_identity_or_date_fails_closed(self):
        batch = {**self.batch, "rows": [list(self.batch["rows"][0])]}
        batch["rows"][0][2] = {"type": "null", "value": None}
        with self.assertRaises(GovernanceError) as error:
            self.operator.apply(batch, self.operation, self.field_ids)
        self.assertEqual(error.exception.code, "aggregation_missing_measure")

    def test_calendar_bucket_requires_canonical_date(self):
        batch = {**self.batch, "rows": [list(self.batch["rows"][0])]}
        batch["rows"][0][0] = {"type": "date", "value": "2025-1-4"}
        with self.assertRaises(GovernanceError) as error:
            self.operator.apply(batch, self.operation, self.field_ids)
        self.assertEqual(error.exception.code, "invalid_native_date")


if __name__ == "__main__":
    unittest.main()
