"""Append-only, in-process catalogue with explicit revision references.

JSON export is a portable development artifact, not a concurrent database or
business-approval store. No approval operation is implemented.
"""

import json
import logging
from pathlib import Path

from .contracts import reference, reference_key
from .errors import CatalogueError

logger = logging.getLogger(__name__)


class MetadataCatalogue:
    def __init__(self, registry):
        self.registry = registry
        self._documents = {}

    def resolve(self, ref):
        try:
            payload = self._documents.get(reference_key(ref))
        except (KeyError, TypeError):
            return None
        return json.loads(payload) if payload is not None else None

    def get(self, ref):
        document = self.resolve(ref)
        if document is None:
            raise CatalogueError("reference_not_found", "Exact catalogue revision was not found.")
        return document

    def add(self, document):
        self.add_many([document])
        return reference(document)

    def add_many(self, documents):
        """Validate references against a staged bundle and commit all or none."""
        documents = list(documents)
        staged = dict(self._documents)
        # First validate shape without following references to unvalidated data.
        # Resolver supplies reference identity only in this first pass; the second
        # pass checks actual cross-document consistency against staged content.
        for document in documents:
            self.registry.validate(document, structural_only=True)
            try:
                key = reference_key(document)
                if (not all(isinstance(v, str) and v.strip() for v in key[:3]) or
                        type(key[3]) is not int or key[3] < 1):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise CatalogueError("invalid_contract_identity", "Catalogue documents require an exact type/version/ID/positive revision identity.") from None
            if key in staged:
                raise CatalogueError("duplicate_revision", "Catalogue revisions cannot be replaced.")
            staged[key] = json.dumps(document, sort_keys=True, allow_nan=False)

        def resolve(ref):
            payload = staged.get(reference_key(ref))
            return json.loads(payload) if payload is not None else None

        for document in documents:
            self.registry.validate(document, resolver=resolve)
        self._documents = staged
        logger.info("catalogue.bundle_added", extra={"document_count": len(documents)})

    def export_documents(self):
        return [json.loads(payload) for payload in self._documents.values()]

    def get_evidence(self, discovery_reference, evidence_id):
        document = self.get(discovery_reference)
        if document["contract_type"] != "SchemaDiscoveryResult":
            raise CatalogueError("reference_type", "Evidence lookup requires a discovery result reference.")
        for evidence in document.get("evidence", []):
            if evidence["evidence_id"] == evidence_id:
                return evidence
        raise CatalogueError("evidence_not_found", "Evidence is absent from the referenced discovery revision.")

    def save(self, path):
        """Exclusive creation: never overwrite previous catalogue evidence."""
        payload = json.dumps({"format_version": "1.0", "documents": self.export_documents()},
                             ensure_ascii=False, indent=2, allow_nan=False)
        try:
            with Path(path).open("x", encoding="utf-8") as stream:
                stream.write(payload)
        except OSError as exc:
            raise CatalogueError("catalogue_write_failed", "Catalogue export could not be created exclusively.") from exc

    @classmethod
    def load(cls, path, registry):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if (not isinstance(payload, dict) or set(payload) != {"format_version", "documents"}
                    or payload["format_version"] != "1.0" or not isinstance(payload["documents"], list)):
                raise ValueError
        except (OSError, ValueError) as exc:
            raise CatalogueError("invalid_catalogue", "Unsupported or unreadable catalogue export.") from exc
        catalogue = cls(registry)
        catalogue.add_many(payload["documents"])
        return catalogue
