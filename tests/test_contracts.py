from copy import deepcopy
import json
import unittest

from business_prediction.contracts import (ContractDefinition, ContractRegistry, FieldSpec,
    ValueState, reference, uncertain, value_state)
from business_prediction.errors import ContractValidationError
from business_prediction.metadata import foundation_registry
from tests.support import bundle


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = foundation_registry()
        self.bundle = bundle()

    def codes(self, doc, resolver=None):
        with self.assertRaises(ContractValidationError) as caught:
            self.registry.validate(doc, resolver)
        result = caught.exception.to_dict()
        json.dumps(result, allow_nan=False)
        return {i["code"] for i in result["issues"]}

    def test_required_type_and_unexpected_errors_are_structured(self):
        document = deepcopy(self.bundle.source_metadata)
        del document["owner_reference"]
        document["object_revision"] = True
        document["imagined_field"] = "secret-must-not-appear-in-error"
        with self.assertRaises(ContractValidationError) as caught:
            self.registry.validate(document)
        errors = caught.exception.to_dict()
        self.assertEqual({i["code"] for i in errors["issues"]}, {"missing_field", "type", "unexpected_field"})
        self.assertNotIn("secret-must-not-appear", json.dumps(errors))

    def test_value_states_remain_distinct(self):
        doc = {"null": None, "unknown": uncertain("unknown", "Not determined."),
               "unavailable": uncertain("unavailable", "Upstream inaccessible."), "zero": 0}
        self.assertEqual([value_state(doc, k) for k in ("absent", "null", "unknown", "unavailable", "zero")],
                         [ValueState.MISSING, ValueState.NULL, ValueState.UNKNOWN, ValueState.UNAVAILABLE, ValueState.PRESENT])

    def test_explicit_null_and_uncertainty_policy(self):
        document = deepcopy(self.bundle.source_metadata)
        document["authority"] = None
        self.assertIn("null_not_allowed", self.codes(document))
        document["authority"] = uncertain("unavailable", "Awaiting source owner.")
        self.registry.validate(document)
        document["owner_reference"] = uncertain("unknown", "Owner required.")
        self.assertIn("uncertainty_not_allowed", self.codes(document))

    def test_uncertainty_tag_requires_reason_and_known_state(self):
        for value in ({"$state": "unknown"}, {"$state": "estimated", "reason": "No evidence"},
                      {"$state": "unknown", "reason": "", "value": 0}):
            document = deepcopy(self.bundle.source_metadata)
            document["authority"] = value
            self.assertIn("invalid_value_state", self.codes(document))

    def test_exact_reference_required(self):
        document = deepcopy(self.bundle.discovery_result)
        self.assertIn("unresolved_reference", self.codes(document))
        document["source_reference"]["object_revision"] = 98
        self.assertIn("unresolved_reference", self.codes(document, lambda ref: self.bundle.source_metadata))

    def test_wrong_reference_type_and_missing_component(self):
        document = deepcopy(self.bundle.discovery_result)
        document["source_reference"]["contract_type"] = "SchemaDiscoveryResult"
        self.assertIn("reference_type", self.codes(document))
        del document["source_reference"]["object_revision"]
        self.assertIn("missing_field", self.codes(document))

    def test_source_version_must_match_reference(self):
        document = deepcopy(self.bundle.discovery_result)
        document["source_version"] = "different-snapshot"
        self.assertIn("inconsistent_metadata", self.codes(document, lambda ref: self.bundle.source_metadata))

    def test_nested_metadata_evidence_and_denominators_are_validated(self):
        for mutate in (lambda d: d["tables"][0]["fields"][0]["observed"].update(nonmissing_count=999),
                       lambda d: d["tables"][0]["fields"][0]["hypotheses"][0].update(evidence_ids=["absent"]),
                       lambda d: d["tables"][0]["fields"][0]["observed"]["type_counts"].update(text=-1)):
            document = deepcopy(self.bundle.discovery_result)
            mutate(document)
            self.assertIn("inconsistent_metadata", self.codes(document, lambda ref: self.bundle.source_metadata))

    def test_hypotheses_cannot_be_promoted_to_approved(self):
        document = deepcopy(self.bundle.discovery_result)
        document["tables"][0]["fields"][0]["hypotheses"][0]["approval_status"] = "approved"
        self.assertIn("choice", self.codes(document))

    def test_version_extension_is_explicit_and_no_coercion(self):
        registry = ContractRegistry()
        for version, kind in (("1.0", "integer"), ("2.0", "string")):
            registry.register(ContractDefinition("TechnicalExtension", version, {
                "contract_type": FieldSpec("string"), "contract_version": FieldSpec("string"),
                "value": FieldSpec(kind)}))
        registry.validate({"contract_type": "TechnicalExtension", "contract_version": "2.0", "value": "001"})
        for version, value in (("1.0", "001"), ("3.0", 1)):
            with self.assertRaises(ContractValidationError):
                registry.validate({"contract_type": "TechnicalExtension", "contract_version": version, "value": value})

    def test_json_extensions_and_timestamp_validation(self):
        doc = deepcopy(self.bundle.source_metadata)
        doc["extensions"] = {"technical.vendor": {"active": True}}
        self.registry.validate(doc)
        doc["created_at"] = "2026-11-02"
        self.assertIn("timestamp", self.codes(doc))
        doc["extensions"] = {"invalid": float("nan")}
        self.assertIn("json_value", self.codes(doc))

    def test_registered_definition_cannot_be_replaced_or_mutated(self):
        fields = {"contract_type": FieldSpec("string"), "contract_version": FieldSpec("string")}
        definition = ContractDefinition("Example", "1.0", fields)
        fields["new"] = FieldSpec("integer")
        self.assertNotIn("new", definition.fields)
        registry = ContractRegistry()
        registry.register(definition)
        with self.assertRaises(ValueError):
            registry.register(definition)

    def test_non_json_and_malformed_resolver_results_are_structured(self):
        for value in ({7: "integer key"}, {"tuple": (1, 2)}, {"object": object()}):
            document = deepcopy(self.bundle.source_metadata)
            document["extensions"] = value
            self.assertIn("json_value", self.codes(document))
        self.assertIn("unresolved_reference", self.codes(self.bundle.discovery_result, lambda ref: {"wrong": "shape"}))

    def test_schema_hash_and_evidence_locations_cannot_be_fabricated(self):
        for mutate in (lambda d: d.update(schema_version="incorrect"),
                       lambda d: d["evidence"][0].update(table_id="unavailable-table"),
                       lambda d: d["evidence"][0].update(denominator=999)):
            document = deepcopy(self.bundle.discovery_result)
            mutate(document)
            self.assertIn("inconsistent_metadata", self.codes(document, lambda ref: self.bundle.source_metadata))


if __name__ == "__main__":
    unittest.main()
