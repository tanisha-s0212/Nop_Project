"""Local durable SQLite storage. Not a production-approved database adapter."""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3

from ..semantics.common import clone, digest
from .base import PersistenceStore, PersistenceError, StorageCapabilities, UnitOfWork, initial_state


class SQLiteStore(PersistenceStore):
    adapter_id = "sqlite-local-v1"
    capabilities = StorageCapabilities(True, True, True, True, True)

    def __init__(self, path, *, timeout_seconds=5.0):
        if (not isinstance(path, (str, Path)) or str(path) in ("", ":memory:") or
                type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise PersistenceError("invalid_storage_configuration", "An on-disk SQLite path and positive timeout are required.")
        self.path = Path(path).resolve()
        self.timeout_seconds = timeout_seconds
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=self.timeout_seconds, isolation_level=None)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self):
        connection = None
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if not tables and version == 0:
                connection.execute("CREATE TABLE framework_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL, payload_digest TEXT NOT NULL)")
                state = initial_state()
                connection.execute("INSERT INTO framework_state VALUES(1,0,?,?)", (json.dumps(state, allow_nan=False), digest(state)))
                connection.execute("PRAGMA user_version=1")
            elif tables != {"framework_state"} or version != 1:
                raise PersistenceError("unsupported_storage_schema", "Existing database is not the supported framework store; no migration was attempted.")
            connection.execute("COMMIT")
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            if connection and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise PersistenceError("storage_unavailable", "SQLite storage could not be opened or initialized safely.") from None
        except BaseException:
            if connection and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            if connection:
                connection.close()

    def _read(self, connection):
        try:
            row = connection.execute("SELECT revision,payload,payload_digest FROM framework_state WHERE id=1").fetchone()
            if row is None:
                raise ValueError
            state = json.loads(row[1])
            if state["format_version"] != "1.0" or digest(state) != row[2] or type(row[0]) is not int or row[0] < 0:
                raise ValueError
            return row[0], state
        except (ValueError, TypeError, KeyError):
            raise PersistenceError("storage_corrupt", "Stored payload/version integrity validation failed.") from None

    @contextmanager
    def _transaction(self):
        connection, committing = None, False
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            revision, state = self._read(connection)
            original = digest(state)
            unit = UnitOfWork(clone(state), revision)
            yield unit
            if digest(unit.state) != original:
                changed = connection.execute("UPDATE framework_state SET revision=?,payload=?,payload_digest=? WHERE id=1 AND revision=?",
                    (revision+1, json.dumps(unit.state, allow_nan=False), digest(unit.state), revision)).rowcount
                if changed != 1:
                    raise PersistenceError("stale_storage_revision", "Storage revision changed before commit.")
            committing = True
            connection.execute("COMMIT")
        except sqlite3.Error:
            if connection and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise PersistenceError("commit_indeterminate" if committing else "storage_transaction_failed",
                "Storage commit outcome requires recovery/replay verification." if committing else "Storage transaction failed and was not accepted.") from None
        except BaseException:
            if connection and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            if connection:
                connection.close()

    def health_check(self):
        connection = None
        try:
            connection = self._connect()
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise PersistenceError("storage_corrupt", "SQLite consistency check failed.")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise PersistenceError("unsupported_storage_schema", "SQLite storage schema is unsupported.")
            revision, state = self._read(connection)
            return {"ready": True, "adapter": self.adapter_id, "durable": True,
                    "production_approved": False, "revision": revision, "store_id": state["store_id"]}
        except sqlite3.Error:
            raise PersistenceError("storage_unavailable", "SQLite health check failed.") from None
        finally:
            if connection:
                connection.close()
