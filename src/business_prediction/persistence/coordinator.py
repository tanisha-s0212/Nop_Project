"""Durable catalogue/journal adapters reusing the existing validation/lifecycle.

One storage transaction covers metadata, decisions, replay outcomes and audit.
The SQLite adapter serializes this boundary across independent processes.
"""

import json
import sys
from threading import RLock

from ..catalogue import MetadataCatalogue
from ..contracts import reference, reference_key
from ..semantics.common import clone, digest, instant
from ..semantics.contracts import CONTRACT_TYPES
from ..assessment.contracts import ASSESSMENT_TYPES
from ..specifications.contracts import SPECIFICATION_CONTRACT_TYPES
from ..execution.contracts import EXECUTION_TYPES
from ..worker.contracts import WORKER_TYPES
from ..semantics.journal import GovernanceJournal
from .base import PersistenceError, append_audit

JOURNALED_TYPES = CONTRACT_TYPES + ASSESSMENT_TYPES + SPECIFICATION_CONTRACT_TYPES + EXECUTION_TYPES + WORKER_TYPES


class _TransactionLock:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        owner = self.owner
        owner._mutex.acquire()
        try:
            if owner._depth == 0:
                owner._context = owner.store.transaction()
                owner._unit = owner._context.__enter__()
                owner._before = clone(owner._unit.state)
                try:
                    owner._load(owner._unit.state)
                except BaseException:
                    owner._context.__exit__(*sys.exc_info())
                    raise
            owner._depth += 1
            return self
        except BaseException:
            owner._mutex.release()
            raise

    def __exit__(self, kind, value, traceback):
        owner = self.owner
        owner._depth -= 1
        try:
            if owner._depth == 0:
                exited = False
                try:
                    if kind is None:
                        owner._capture()
                    exited = True
                    owner._context.__exit__(kind, value, traceback)
                except BaseException:
                    if not exited:
                        owner._context.__exit__(*sys.exc_info())
                    owner._load(owner._before)
                    raise
                if kind is not None:
                    owner._load(owner._before)
        finally:
            owner._mutex.release()
        return False


class DurableCatalogue(MetadataCatalogue):
    """Same catalogue API, persisted atomically; no public governance import."""

    def __init__(self, registry, owner):
        super().__init__(registry)
        self._owner = owner

    def add_many(self, documents):
        documents = list(documents)
        with self._owner.lock:
            if any(d.get("contract_type") in JOURNALED_TYPES for d in documents) and not self._owner._issuing:
                raise PersistenceError("untrusted_governance_import", "Governance records must be issued through the shared service transaction.")
            super().add_many(documents)
            if documents:
                append_audit(self._owner._unit.state, "metadata.bundle_added", document_count=len(documents))

    def resolve(self, ref):
        with self._owner.lock:
            return super().resolve(ref)

    def export_documents(self):
        with self._owner.lock:
            return super().export_documents()


class DurableJournal:
    """Journal interface consumed by SemanticApprovalService, with durable replay."""

    def __init__(self, owner):
        self._owner = owner
        self.catalogue = owner.catalogue
        self.lock = owner.lock

    @property
    def head(self):
        with self.lock:
            return self._owner._memory.head

    @property
    def instance_id(self):
        with self.lock:
            return self._owner._unit.state["store_id"]

    @property
    def last_clock(self):
        with self.lock:
            return self._owner._unit.state["journal"]["last_clock"]

    def record_clock(self, now):
        self._owner._unit.state["journal"]["last_clock"] = now.isoformat()

    def replay(self, *args):
        return self._owner._memory.replay(*args)

    def check_head(self, *args):
        return self._owner._memory.check_head(*args)

    def commit(self, documents, *, expected_head, command_id, command_digest, outcome):
        self._owner._issuing = True
        try:
            result = self._owner._memory.commit(documents, expected_head=expected_head, command_id=command_id,
                command_digest=command_digest, outcome=outcome)
            entry = self._owner._memory._entries[-1]
            entry["command_digest"], entry["outcome_digest"] = command_digest, digest(outcome)
            entry.pop("entry_digest")
            entry["entry_digest"] = digest(entry)
            append_audit(self._owner._unit.state, "governance.command_committed", command_id=command_id,
                         governance_head=self._owner._memory.head, error_code=outcome.get("error_code"),
                         principal_reference=documents[0]["owner_reference"] if documents else None)
            return result
        finally:
            self._owner._issuing = False

    def get(self, ref):
        return self._owner._memory.get(ref)

    def documents(self, kind=None):
        return self._owner._memory.documents(kind)

    def history(self):
        return self._owner._memory.history()

    def record_failure(self, operation, error_code, *, authorization=None):
        with self.lock:
            append_audit(self._owner._unit.state, "governance.operation_blocked", operation=operation,
                         error_code=error_code, authorization=authorization)


class DurableCoordinator:
    def __init__(self, registry, store):
        self.store = store
        self._mutex, self._depth, self._issuing = RLock(), 0, False
        self.lock = _TransactionLock(self)
        self.catalogue = DurableCatalogue(registry, self)
        self._memory = GovernanceJournal(self.catalogue)
        self.journal = DurableJournal(self)
        if self.store.health_check().get("ready") is not True:
            raise PersistenceError("storage_unavailable", "Storage did not pass startup readiness.")
        with self.lock:
            pass  # Full startup reference/journal consistency validation.

    def _load(self, state):
        try:
            if state["format_version"] != "1.0":
                raise ValueError
            validated = MetadataCatalogue(self.catalogue.registry)
            validated.add_many(state["documents"])
            journal = state["journal"]
            entries, commands = journal["entries"], journal["commands"]
            if journal["head"] != len(entries) or len(commands) != len(entries):
                raise ValueError
            trusted, previous, command_ids = {}, None, set()
            for sequence, entry in enumerate(entries, 1):
                raw = {k: v for k, v in entry.items() if k != "entry_digest"}
                if (entry["sequence"] != sequence or entry["previous_entry_digest"] != previous
                        or digest(raw) != entry["entry_digest"] or entry["command_id"] in command_ids
                        or len(entry["references"]) != len(entry["document_digests"])):
                    raise ValueError
                command_ids.add(entry["command_id"])
                command = commands[entry["command_id"]]
                if command["digest"] != entry["command_digest"] or digest(command["outcome"]) != entry["outcome_digest"]:
                    raise ValueError
                for ref, expected in zip(entry["references"], entry["document_digests"]):
                    document = validated.get(ref)
                    if digest(document) != expected or reference_key(ref) in trusted:
                        raise ValueError
                    trusted[reference_key(ref)] = expected
                previous = entry["entry_digest"]
            governance = {reference_key(d) for d in state["documents"] if d["contract_type"] in JOURNALED_TYPES}
            if governance != set(trusted):
                raise ValueError
            previous = None
            for i, event in enumerate(state["audit"], 1):
                raw = {k: v for k, v in event.items() if k != "event_digest"}
                if event["sequence"] != i or event["previous_event_digest"] != previous or digest(raw) != event["event_digest"]:
                    raise ValueError
                previous = event["event_digest"]
            if journal["last_clock"]:
                floor = instant(journal["last_clock"])
                if any(instant(d["created_at"]) > floor for d in state["documents"] if d["contract_type"] in JOURNALED_TYPES):
                    raise ValueError
            elif trusted:
                raise ValueError
            self.catalogue._documents = dict(validated._documents)
            self._memory.instance_id = state["store_id"]
            self._memory.head = journal["head"]
            self._memory._entries = clone(entries)
            self._memory._commands = clone(commands)
            self._memory._trusted = trusted
        except Exception as exc:
            if isinstance(exc, PersistenceError):
                raise
            raise PersistenceError("recovery_consistency_failed", "Catalogue, journal, command or audit recovery checks failed; runtime was blocked.") from None

    def _capture(self):
        state = self._unit.state
        state["documents"] = [json.loads(p) for p in self.catalogue._documents.values()]
        state["journal"].update(head=self._memory.head, entries=clone(self._memory._entries), commands=clone(self._memory._commands))
        self._load(state)  # Validate complete state before allowing commit.

    def bind_runtime(self, binding):
        with self.lock:
            old = self._unit.state["runtime_binding"]
            if old is not None and old != binding:
                raise PersistenceError("runtime_binding_changed", "Persisted policy/provider/mode bindings differ; explicit migration/review is required.")
            self._unit.state["runtime_binding"] = clone(binding)

    def audit_event(self, event, **details):
        with self.lock:
            append_audit(self._unit.state, event, **details)

    def audit_history(self):
        with self.lock:
            return clone(self._unit.state["audit"])

    def health_check(self):
        health = self.store.health_check()
        with self.lock:
            return {**health, "catalogue_consistent": True, "governance_head": self._memory.head}
