"""Read-only source protocol and immutable physical-table snapshots."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

from ..errors import SourceError


@dataclass(frozen=True)
class Formula:
    expression: str


@dataclass(frozen=True)
class CellError:
    token: str


def cell_type(value):
    if value is None:
        return "null"
    for cls, name in ((Formula, "formula"), (CellError, "cell_error"), (bool, "boolean"),
                      (datetime, "datetime"), (date, "date"), (time, "time"),
                      (int, "integer"), (float, "float"), (Decimal, "decimal"), (str, "text")):
        if isinstance(value, cls):
            return name
    raise SourceError("unsupported_cell_type", "Source contains an unsupported cell type.")


def encode_cell(value):
    """Lossless typed metadata for supported scalar cells; never source mutation."""
    kind = cell_type(value)
    if isinstance(value, (date, time)):
        value = value.isoformat()
    elif isinstance(value, Decimal):
        value = str(value)
    elif isinstance(value, Formula):
        value = value.expression
    elif isinstance(value, CellError):
        value = value.token
    elif isinstance(value, float) and not math.isfinite(value):
        value = repr(value)
    return {"type": kind, "value": value}


@dataclass(frozen=True)
class SourceConfig:
    source_id: str
    owner_reference: str
    purpose_scope: str

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in
               (self.source_id, self.owner_reference, self.purpose_scope)):
            raise ValueError("Source ID, owner reference and purpose are required.")


@dataclass(frozen=True)
class RawField:
    position: int
    header: object
    header_present: bool


@dataclass(frozen=True)
class RawRow:
    position: int
    cells: tuple


@dataclass(frozen=True)
class RawTable:
    table_id: str
    name: str
    header_row: int | None
    fields: tuple[RawField, ...]
    rows: tuple[RawRow, ...]


def physical_table(table_id, name, rows, header_row, max_cells):
    """Preserve ragged/blank rows; source layout is configured, not approved."""
    if header_row is not None and (type(header_row) is not int or header_row < 1):
        raise ValueError("Header row must be a positive integer or None.")
    rows = tuple(tuple(row) for row in rows)
    width = max((len(row) for row in rows), default=0)
    if len(rows) * width > max_cells:
        raise SourceError("resource_limit", "Table exceeds the configured cell budget.")
    if header_row is not None and header_row > len(rows) and rows:
        raise SourceError("invalid_layout", "Configured header row is outside the table.")
    headers = rows[header_row - 1] if header_row and len(rows) >= header_row else ()
    fields = tuple(RawField(i+1, headers[i] if i < len(headers) else None,
                            header_row is not None and i < len(headers)) for i in range(width))
    start = header_row or 0
    return RawTable(table_id, name, header_row, fields,
                    tuple(RawRow(i+1, row) for i, row in enumerate(rows) if i >= start))


class SourceSnapshot(ABC):
    """Future database adapters must provide equally explicit consistency metadata."""

    @abstractmethod
    def metadata(self) -> dict: ...

    @abstractmethod
    def tables(self) -> tuple[RawTable, ...]: ...

    @abstractmethod
    def iter_rows(self, table_id: str): ...

    @abstractmethod
    def verify_unchanged(self): ...


class DataSourceAdapter(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def open_snapshot(self) -> AbstractContextManager[SourceSnapshot]: ...


class FrozenSnapshot(SourceSnapshot):
    def __init__(self, metadata, tables, verify=lambda: None):
        self._metadata_json = json.dumps(metadata, allow_nan=False)
        self._tables = tuple(tables)
        self._verify = verify

    def metadata(self):
        return json.loads(self._metadata_json)

    def tables(self):
        return self._tables

    def iter_rows(self, table_id):
        for table in self._tables:
            if table.table_id == table_id:
                yield from table.rows
                return
        raise SourceError("unknown_table", "Requested table is not in this snapshot.")

    def verify_unchanged(self):
        self._verify()


class FileAdapter(DataSourceAdapter):
    """Capture bytes once; detect on-disk changes before publishing discovery."""

    adapter_kind = "file"

    def __init__(self, path, config: SourceConfig, *, max_bytes=64*1024*1024, max_cells=1_000_000):
        if type(max_bytes) is not int or max_bytes < 1 or type(max_cells) is not int or max_cells < 1:
            raise ValueError("Resource budgets must be positive integers.")
        self.path, self.config = Path(path), config
        self.max_bytes, self.max_cells = max_bytes, max_cells

    @property
    def source_id(self):
        return self.config.source_id

    @abstractmethod
    def _tables_from_bytes(self, payload): ...

    def _settings(self):
        return {"max_bytes": self.max_bytes, "max_cells": self.max_cells}

    @contextmanager
    def open_snapshot(self):
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(self.max_bytes + 1)
            if len(payload) > self.max_bytes:
                raise SourceError("resource_limit", "Source exceeds the configured byte budget.")
            digest = hashlib.sha256(payload).hexdigest()
            tables = self._tables_from_bytes(payload)
        except SourceError:
            raise
        except (OSError, ValueError, LookupError) as exc:
            raise SourceError("unreadable_source", "Cannot read the configured source.") from exc

        def verify():
            try:
                h = hashlib.sha256()
                with self.path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b""):
                        h.update(chunk)
                unchanged = h.hexdigest() == digest
            except OSError:
                unchanged = False
            if not unchanged:
                raise SourceError("source_changed", "Source changed during discovery; result was not accepted.")

        snapshot = FrozenSnapshot({"source_id": self.source_id, "source_version": "sha256:"+digest,
                                   "owner_reference": self.config.owner_reference,
                                   "purpose_scope": self.config.purpose_scope,
                                   "adapter_settings": self._settings(),
                                   "adapter_kind": self.adapter_kind, "resource_locator": str(self.path.resolve()),
                                   "consistency": "captured_bytes_with_exit_hash_check"}, tables, verify)
        try:
            yield snapshot
        finally:
            snapshot.verify_unchanged()
