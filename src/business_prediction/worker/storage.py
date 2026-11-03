"""Local sealed, exclusive-create artifacts behind a production storage interface.

Local file attributes are accidental-write protection, not production WORM/ACLs.
Only the publication service may expose a version after its durable record.
"""

from abc import ABC, abstractmethod
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from ..semantics.common import clone, digest, GovernanceError


def raw_digest(payload): return "sha256:"+hashlib.sha256(payload).hexdigest()


def missing_cell(cell):
    return cell.get("type") == "null" and cell.get("value") is None or cell.get("type") == "text" and isinstance(cell.get("value"),str) and not cell["value"].strip()


def safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise GovernanceError("artifact_path_alias", "Symlinks/reparse points are not permitted in artifact storage paths.")
    return path.resolve()


def validate_batch(batch):
    if set(batch) != {"schema", "rows", "ordinals"}: raise GovernanceError("invalid_row_batch", "A bounded typed row batch is required.")
    ids = [c["field_id"] for c in batch["schema"]]
    if (not ids or len(set(ids)) != len(ids) or len(batch["rows"]) != len(batch["ordinals"]) or len(set(batch["ordinals"])) != len(batch["ordinals"]) or
            any(type(n) is not int or n < 1 for n in batch["ordinals"])):
        raise GovernanceError("invalid_row_batch", "Schema fields and physical row ordinals must be distinct and aligned.")
    for row in batch["rows"]:
        if len(row) != len(ids): raise GovernanceError("invalid_row_batch", "Rows must match the explicit field schema.")
        for cell, column in zip(row, batch["schema"]):
            if set(cell) != {"type", "value"} or cell["type"] not in set(column["types"]) | {"null"} and not missing_cell(cell):
                raise GovernanceError("invalid_row_batch", "Cell types must conform to the explicit logical schema.")
            kind, value = cell["type"], cell["value"]
            if (kind == "null" and value is not None or kind == "integer" and type(value) is not int or
                    kind == "float" and type(value) is not float or kind == "boolean" and type(value) is not bool or
                    kind in ("text", "date", "datetime", "time", "decimal") and not isinstance(value, str)):
                raise GovernanceError("invalid_row_batch", "Typed scalar values do not match their declared representation.")
    clone(batch)  # finite JSON only


class ArtifactStorage(ABC):
    provider_id: str
    version = "1.0"
    development_only = False
    production_capable = False
    deployment_approval_reference = None

    @abstractmethod
    def health_check(self): ...
    @abstractmethod
    def assert_isolated(self, source_metadata): ...
    @abstractmethod
    def put(self, request_id, category, payload, *, token=None): ...
    @abstractmethod
    def read(self, locator): ...
    @abstractmethod
    def describe(self, locator, role, now): ...
    @abstractmethod
    def promote(self, intent_id, request_id, artifacts): ...
    @abstractmethod
    def orphans(self, referenced_locators): ...


class ProductionArtifactStorage(ArtifactStorage):
    """External adapter must supply immutable object versions, ACLs, CAS promotion,
    integrity, isolated staging, retention and idempotent recovery. No connector
    is supplied. Capability/approval labels require real operator review.
    """
    @abstractmethod
    def authorize_access(self,principal,action,scope,artifact_references,fence_token): ...
    @abstractmethod
    def recover_promotion(self,intent_reference): ...
    @abstractmethod
    def apply_retention(self,policy_reference,artifact_references,authorization_evidence): ...


class LocalArtifactStorage(ArtifactStorage):
    provider_id = "local-sealed-artifact-storage"
    development_only = True

    def __init__(self, root, *, protected_paths=(), max_bytes=16*1024*1024, max_rows=10000):
        self.root = safe_path(root)
        self.max_bytes, self.max_rows = max_bytes, max_rows
        if type(max_bytes) is not int or type(max_rows) is not int or min(max_bytes,max_rows) < 1: raise ValueError("Explicit positive storage budgets are required.")
        self._protected = tuple(safe_path(p) for p in protected_paths)
        self._check_overlap(self._protected)
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root/"store.json"
        if not marker.exists():
            if any(self.root.iterdir()): raise GovernanceError("artifact_root_not_empty", "Initialize only an empty isolated artifact directory.")
            self._exclusive(marker, {"format_version": "1.0", "store_id": str(uuid4())})
        body = self._read_file(marker)
        if set(body) != {"format_version", "store_id"} or body["format_version"] != "1.0": raise GovernanceError("invalid_artifact_store", "Unknown artifact-store format.")
        self.store_id = body["store_id"]; self._token(self.store_id)

    def _check_overlap(self, paths):
        for p in paths:
            if p == self.root or p in self.root.parents or self.root in p.parents:
                raise GovernanceError("artifact_source_overlap", "Artifact roots must be separate from protected source resources.")

    def assert_isolated(self, source_metadata):
        paths = list(self._protected)
        for source in source_metadata:
            locator = source["resource_locator"]
            if source["adapter_kind"] != "memory": paths.append(safe_path(locator))
        self._check_overlap(paths); safe_path(self.root)

    def health_check(self):
        safe_path(self.root)
        return {"ready": self.root.is_dir(), "development_only": True}

    @staticmethod
    def _token(value):
        if not isinstance(value,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}",value):
            raise GovernanceError("invalid_artifact_locator", "Only bounded server-generated artifact tokens are allowed.")
        return value

    def _file(self, locator):
        bits = locator.split(":")
        if len(bits) != 5 or bits[0] != "artifact" or bits[1] != self.store_id:
            raise GovernanceError("invalid_artifact_locator", "Artifact locator belongs to another store or format.")
        _, _, run, category, token = bits
        if category not in ("inputs", "intermediate", "final", "claims", "receipts", "published"):
            raise GovernanceError("invalid_artifact_locator", "Unknown artifact namespace.")
        self._token(run); self._token(token)
        path = safe_path(self.root/run/category/(token+".json"))
        if self.root not in path.parents: raise GovernanceError("artifact_path_escape", "Artifact path escaped isolated storage.")
        return path

    def _exclusive(self, path, body):
        safe_path(path)
        payload = json.dumps(clone(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(payload) > self.max_bytes: raise GovernanceError("artifact_budget_exceeded", "Artifact exceeds the configured byte budget.")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.chmod(path, stat.S_IREAD)
        return raw_digest(payload)

    def _read_file(self, path):
        safe_path(path)
        if path.stat().st_nlink != 1: raise GovernanceError("artifact_path_alias", "Hardlinked artifact files are not accepted.")
        if path.stat().st_size > self.max_bytes: raise GovernanceError("artifact_budget_exceeded", "Artifact exceeds the byte budget.")
        try: return json.loads(path.read_bytes())
        except (OSError, ValueError): raise GovernanceError("artifact_unreadable", "Artifact bytes are unavailable or invalid.") from None

    def put(self, request_id, category, payload, *, token=None):
        if "batch" in payload:
            validate_batch(payload["batch"])
            if len(payload["batch"]["rows"]) > self.max_rows: raise GovernanceError("artifact_budget_exceeded", "Artifact exceeds the row budget.")
        locator = ":".join(("artifact", self.store_id, self._token(request_id), category, self._token(token or str(uuid4()))))
        path = self._file(locator)
        content_digest = self._exclusive(path, payload)
        self._exclusive(path.with_suffix(".seal"), {"content_digest": content_digest, "size_bytes": path.stat().st_size})
        return locator

    def read(self, locator):
        path = self._file(locator); body = self._read_file(path)
        seal = self._read_file(path.with_suffix(".seal"))
        if seal != {"content_digest": raw_digest(path.read_bytes()), "size_bytes": path.stat().st_size}:
            raise GovernanceError("artifact_integrity_failed", "Artifact content differs from its immutable seal.")
        if "batch" in body: validate_batch(body["batch"])
        return body

    def content_digest(self, locator):
        self.read(locator)
        return raw_digest(self._file(locator).read_bytes())

    def describe(self, locator, role, now):
        body = self.read(locator); batch = body["batch"]; rows = batch["rows"]
        missing = {c["field_id"]: sum(missing_cell(row[i]) for row in rows) for i,c in enumerate(batch["schema"])}
        return {"locator": locator, "content_digest": self.content_digest(locator), "size_bytes": self._file(locator).stat().st_size,
            "row_count": len(rows), "duplicate_count": len(rows)-len({digest(row) for row in rows}), "missing_counts": missing,
            "schema": batch["schema"], "source_references": body["lineage"]["source_references"], "complete": True,
            "role": role, "measured_at": now.isoformat(), "evidence_reference": "sealed:"+self.content_digest(locator)}

    def promote(self, intent_id, request_id, artifacts):
        # Deterministic per-intent object names make copy recovery idempotent.
        versions = []
        for artifact in artifacts:
            body = self.read(artifact["locator"])
            if self.content_digest(artifact["locator"]) != artifact["content_digest"]: raise GovernanceError("publication_integrity_failed", "Staging bytes changed before promotion.")
            token = digest({"intent": intent_id, "locator": artifact["locator"]})[7:]
            locator = ":".join(("artifact",self.store_id,request_id,"published",token))
            if self._file(locator).exists():
                path = self._file(locator)
                if not path.with_suffix(".seal").exists():
                    expected = json.dumps(clone(body),sort_keys=True,separators=(",", ":"),ensure_ascii=False).encode("utf-8")
                    if path.read_bytes() != expected: raise GovernanceError("publication_partial_corrupt", "Partial promoted bytes do not match the exact immutable source; no overwrite is allowed.")
                    self._exclusive(path.with_suffix(".seal"),{"content_digest":raw_digest(expected),"size_bytes":len(expected)})
                if self.read(locator) != body: raise GovernanceError("publication_conflict", "Existing promoted object has conflicting bytes.")
            else: self.put(request_id,"published",body,token=token)
            versions.append({"original_locator": artifact["locator"], "locator": locator, "content_digest": self.content_digest(locator), "role": artifact["role"]})
        manifest = {"format_version": "1.0", "intent_id": intent_id, "request_id": request_id, "versions": versions}
        token = "manifest-"+self._token(intent_id)
        locator = ":".join(("artifact",self.store_id,request_id,"published",token))
        if self._file(locator).exists():
            path = self._file(locator)
            if not path.with_suffix(".seal").exists():
                expected = json.dumps(clone(manifest),sort_keys=True,separators=(",", ":"),ensure_ascii=False).encode("utf-8")
                if path.read_bytes() != expected: raise GovernanceError("publication_partial_corrupt", "Partial manifest bytes cannot be silently repaired or replaced.")
                self._exclusive(path.with_suffix(".seal"),{"content_digest":raw_digest(expected),"size_bytes":len(expected)})
            if self.read(locator) != manifest: raise GovernanceError("publication_conflict", "An immutable publication manifest cannot be replaced.")
        else: self.put(request_id,"published",manifest,token=token)
        return {"locator": locator, "content_digest": self.content_digest(locator), "store_id": self.store_id, "version_id": intent_id}

    def orphans(self, referenced_locators):
        known = set(referenced_locators); results = []
        for path in self.root.glob("*/*/*.json"):
            run, category, token = path.parent.parent.name, path.parent.name, path.stem
            locator = ":".join(("artifact",self.store_id,run,category,token))
            try:
                self.read(locator)
                status = "sealed_unreferenced" if locator not in known else "referenced"
            except (OSError, FrameworkError): status = "partial_or_corrupt"
            if status != "referenced": results.append({"locator": locator, "status": status})
        return results


# Keep filesystem exceptions structured at integration boundaries; recovery
# never deletes an orphan, original source or prior published version.
from ..errors import FrameworkError
