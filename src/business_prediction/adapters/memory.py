"""Synthetic/in-process source adapter with immutable scalar snapshots."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json

from .base import DataSourceAdapter, FrozenSnapshot, SourceConfig, encode_cell, physical_table


@dataclass(frozen=True)
class MemoryTable:
    name: str
    rows: tuple
    header_row: int | None = 1


class MemoryAdapter(DataSourceAdapter):
    def __init__(self, config: SourceConfig, tables, *, max_cells=1_000_000):
        if type(max_cells) is not int or max_cells < 1:
            raise ValueError("Cell budget must be a positive integer.")
        self.config = config
        captured = tuple(MemoryTable(t.name, tuple(tuple(r) for r in t.rows), t.header_row) for t in tables)
        self._tables = tuple(physical_table(f"table-{i+1}", t.name, t.rows, t.header_row, max_cells)
                             for i, t in enumerate(captured))
        # Encode every cell now: unsupported mutable objects cannot enter snapshots.
        payload = [{"name": t.name, "header_row": t.header_row,
                    "rows": [[encode_cell(v) for v in r] for r in t.rows]} for t in captured]
        self._version = "sha256:"+hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.max_cells = max_cells

    @property
    def source_id(self):
        return self.config.source_id

    @contextmanager
    def open_snapshot(self):
        yield FrozenSnapshot({"source_id": self.source_id, "source_version": self._version,
                              "owner_reference": self.config.owner_reference,
                              "purpose_scope": self.config.purpose_scope,
                              "adapter_settings": {"max_cells": self.max_cells, "value_policy": "typed_scalars"},
                              "adapter_kind": "memory", "resource_locator": "memory:"+self.source_id,
                              "consistency": "immutable_captured_values"}, self._tables)
