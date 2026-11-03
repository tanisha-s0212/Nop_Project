"""Database-neutral unit of work and append-only recovery format."""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from ..contracts import reference_key
from ..semantics.common import clone, digest, GovernanceError, instant


class PersistenceError(GovernanceError):
    pass


@dataclass(frozen=True)
class StorageCapabilities:
    durable: bool
    transactions: bool
    immutable_history: bool
    stale_write_protection: bool
    recovery: bool
    production_approved: bool = False
    test_only: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in self.__dict__.values()):
            raise PersistenceError("invalid_storage_capabilities", "Storage capability declarations must be explicit booleans.")


@dataclass
class UnitOfWork:
    state: dict
    revision: int


def initial_state():
    return {"format_version": "1.0", "store_id": "durable-governance:"+str(uuid4()),
            "documents": [], "journal": {"head": 0, "entries": [], "commands": {}, "last_clock": None},
            "audit": [], "runtime_binding": None}


def append_audit(state, event, **details):
    allowed = {"operation", "error_code", "principal_reference", "command_id", "governance_head", "document_count", "mode", "authorization"}
    if not set(details) <= allowed:
        raise PersistenceError("unsafe_audit_field", "Audit event contains an undeclared field.")
    previous = state["audit"][-1]["event_digest"] if state["audit"] else None
    record = {"sequence": len(state["audit"])+1, "event": event,
              "recorded_at": datetime.now(timezone.utc).isoformat(), "details": clone(details), "previous_event_digest": previous}
    record["event_digest"] = digest(record)
    state["audit"].append(record)


def validate_transition(before, after):
    """Immutable history is enforced independently of a database dialect."""
    try:
        if set(after) != set(before) or any(after[k] != before[k] for k in ("format_version", "store_id")):
            raise ValueError
        old = {reference_key(d): d for d in before["documents"]}
        new = {reference_key(d): d for d in after["documents"]}
        if len(new) != len(after["documents"]) or any(new.get(key) != value for key, value in old.items()):
            raise ValueError
        for key in ("entries",):
            if after["journal"][key][:len(before["journal"][key])] != before["journal"][key]:
                raise ValueError
        if after["audit"][:len(before["audit"])] != before["audit"]:
            raise ValueError
        if any(after["journal"]["commands"].get(k) != v for k, v in before["journal"]["commands"].items()):
            raise ValueError
        if after["journal"]["head"] != len(after["journal"]["entries"]) or after["journal"]["head"] < before["journal"]["head"]:
            raise ValueError
        if before["runtime_binding"] is not None and after["runtime_binding"] != before["runtime_binding"]:
            raise ValueError
        clock_before, clock_after = before["journal"]["last_clock"], after["journal"]["last_clock"]
        if clock_before and (not clock_after or instant(clock_after) < instant(clock_before)):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise PersistenceError("immutable_history_violation", "A transaction attempted to replace immutable history or storage identity.") from None


class PersistenceStore(ABC):
    """Adapter implementations must atomically commit/rollback the whole unit.

    Production adapters supply approved transaction isolation, CAS, persistence,
    access controls and recovery. No database connection is invented here.
    """

    capabilities: StorageCapabilities
    adapter_id: str

    @abstractmethod
    def _transaction(self):
        """Context manager yielding UnitOfWork under cross-worker write isolation."""

    @contextmanager
    def transaction(self):
        with self._transaction() as unit:
            before = clone(unit.state)
            yield unit
            validate_transition(before, unit.state)

    def snapshot(self):
        with self.transaction() as unit:
            return {"revision": unit.revision, "state": clone(unit.state)}

    @abstractmethod
    def health_check(self): ...

    def close(self):
        """Release adapter resources, if any."""


class ProductionStorageAdapter(PersistenceStore):
    """Integration boundary only; implement for an owner-approved database.

    An adapter must additionally expose its deployment approval reference.
    Merely subclassing this interface does not provide a connected database.
    """

    @property
    @abstractmethod
    def approval_reference(self): ...
