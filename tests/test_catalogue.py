from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from business_prediction.catalogue import MetadataCatalogue
from business_prediction.contracts import ContractDefinition, FieldSpec, reference
from business_prediction.errors import CatalogueError, ContractValidationError
from business_prediction.metadata import foundation_registry
from tests.support import bundle


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = MetadataCatalogue(foundation_registry())
        self.bundle = bundle()

    def test_unordered_atomic_bundle_and_exact_evidence_resolution(self):
        self.catalogue.add_many([self.bundle.discovery_result, self.bundle.source_metadata])
        ref = reference(self.bundle.discovery_result)
        evidence_id = self.bundle.discovery_result["evidence"][0]["evidence_id"]
        self.assertEqual(self.catalogue.get_evidence(ref, evidence_id)["status"], "observed")

    def test_missing_reference_rolls_back_entire_bundle(self):
        with self.assertRaises(ContractValidationError):
            self.catalogue.add_many([self.bundle.discovery_result])
        self.assertEqual(self.catalogue.export_documents(), [])

    def test_existing_revision_cannot_be_replaced(self):
        self.bundle.publish(self.catalogue)
        altered = deepcopy(self.bundle.source_metadata)
        altered["authority"] = "a different unsupported claim"
        with self.assertRaises(CatalogueError) as caught:
            self.catalogue.add(altered)
        self.assertEqual(caught.exception.code, "duplicate_revision")
        self.assertEqual(self.catalogue.get(reference(altered)), self.bundle.source_metadata)

    def test_new_revisions_preserve_history_and_return_defensive_copies(self):
        self.bundle.publish(self.catalogue)
        newer = bundle((("new_label",), ("new-record",)), revision=2)
        newer.publish(self.catalogue)
        old_ref, new_ref = reference(self.bundle.discovery_result), reference(newer.discovery_result)
        fetched = self.catalogue.get(old_ref)
        fetched["tables"].clear()
        self.assertEqual(len(self.catalogue.get(old_ref)["tables"]), 1)
        self.assertNotEqual(self.catalogue.get(old_ref)["schema_version"], self.catalogue.get(new_ref)["schema_version"])
        self.assertIsNone(self.catalogue.resolve({**old_ref, "object_revision": 500}))

    def test_json_roundtrip_preserves_all_contracts_and_no_overwrite(self):
        self.bundle.publish(self.catalogue)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"catalogue.json"
            self.catalogue.save(path)
            before = path.read_bytes()
            restored = MetadataCatalogue.load(path, foundation_registry())
            self.assertEqual(restored.export_documents(), self.catalogue.export_documents())
            with self.assertRaises(CatalogueError):
                self.catalogue.save(path)
            self.assertEqual(path.read_bytes(), before)

    def test_malformed_export_and_unknown_evidence_are_structured(self):
        self.bundle.publish(self.catalogue)
        with self.assertRaises(CatalogueError):
            self.catalogue.get_evidence(reference(self.bundle.discovery_result), "absent")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"broken.json"
            path.write_text('{"format_version":"99","documents":[]}', encoding="utf-8")
            with self.assertRaises(CatalogueError):
                MetadataCatalogue.load(path, foundation_registry())

    def test_registered_extension_still_requires_catalogue_identity(self):
        self.catalogue.registry.register(ContractDefinition("TechnicalExtension", "1.0", {
            "contract_type": FieldSpec("string"), "contract_version": FieldSpec("string")}))
        with self.assertRaises(CatalogueError) as caught:
            self.catalogue.add({"contract_type": "TechnicalExtension", "contract_version": "1.0"})
        self.assertEqual(caught.exception.code, "invalid_contract_identity")
        self.assertEqual(self.catalogue.export_documents(), [])


if __name__ == "__main__":
    unittest.main()
