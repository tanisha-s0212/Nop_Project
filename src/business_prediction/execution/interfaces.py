"""Trusted evidence boundaries. No transformation/executor is supplied here."""

from abc import ABC, abstractmethod

from ..adapters.base import DataSourceAdapter
from ..discovery import discover
from ..semantics.common import digest, GovernanceError


class SourceVersionVerifier(ABC):
    provider_id: str
    version = "1.0"
    development_only = False
    production_capable = False
    deployment_approval_reference = None

    @abstractmethod
    def verify(self, source_references, catalogue):
        """Verify live/immutable snapshot fingerprints and schemas; raise on doubt."""

    @abstractmethod
    def health_check(self): ...


class AdapterSourceVersionVerifier(SourceVersionVerifier):
    """Explicit read-only adapters; local evidence, not a production snapshot lock.

    Reuses discovery and its integrity checks; never publishes new metadata or
    transforms values. No source directory is searched implicitly.
    """
    provider_id = "local-readonly-adapter-verifier"
    development_only = True

    def __init__(self, adapters):
        self.adapters = dict(adapters)
        if any(not isinstance(a, DataSourceAdapter) or key != a.source_id for key, a in self.adapters.items()):
            raise ValueError("Explicit source IDs must map to read-only adapters.")

    def health_check(self):
        return {"ready": bool(self.adapters), "development_only": True}

    def verify(self, source_references, catalogue):
        checked = []
        seen = set()
        for field in source_references:
            key = digest(field["discovery_reference"])
            if key in seen: continue
            seen.add(key)
            original = catalogue.get(field["source_metadata_reference"])
            adapter = self.adapters.get(original["object_id"])
            if adapter is None:
                raise GovernanceError("source_verifier_unavailable", "No approved verifier is configured for this exact source.")
            current = discover(adapter, source_revision=original["object_revision"], discovery_revision=field["discovery_reference"]["object_revision"])
            if (current.source_metadata["source_version"] != original["source_version"] or
                    current.discovery_result["schema_version"] != field["schema_version"] or
                    any(current.source_metadata[k] != original[k] for k in ("adapter_kind", "adapter_settings", "resource_locator", "consistency"))):
                raise GovernanceError("source_snapshot_changed", "Live source fingerprint, schema or adapter interpretation differs from the approved snapshot.")
            checked.append({"source_reference": field["source_metadata_reference"], "discovery_reference": field["discovery_reference"],
                            "source_version": field["source_version"], "schema_version": field["schema_version"]})
        return {"provider_reference": self.provider_id+"@"+self.version, "verified_snapshots": checked}


class ExecutionEvidenceVerifier(ABC):
    """External, trusted worker/artifact evidence integration, not caller flags.

    Implementations must verify worker receipts, immutable staging ownership and
    fencing, original-source isolation, content hashes and measured statistics.
    Report source references and artifacts only from the pinned execution.
    No local default is provided; automated tests supply a synthetic verifier.
    """
    provider_id: str
    version = "1.0"
    development_only = False
    production_capable = False
    deployment_approval_reference = None

    @abstractmethod
    def health_check(self): ...

    @abstractmethod
    def inspect_operation(self, request, authorization, state, operation, evidence_handle):
        """Return independently verified, measured operation evidence, never predictions.

        Fields: request_reference, authorization_reference, fence_token,
        operation_digest, started_at, completed_at, complete, accepted_count,
        rejected_count, input_artifacts, output_artifacts, evidence_reference.
        Artifact fields conform to execution.contracts.artifact_fields().
        Missing/unperformed counts are null, not invented zero values.
        """

    @abstractmethod
    def inspect_artifact(self, request_reference, artifact):
        """Remeasure an immutable, isolated artifact; reject aliases/outside staging."""
