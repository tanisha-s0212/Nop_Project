from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
from business_prediction.discovery import discover


def bundle(rows=None, *, revision=1):
    rows = rows if rows is not None else (("opaque", "measure"), ("A", 1), ("B", 2))
    adapter = MemoryAdapter(SourceConfig("synthetic-source", "test-owner", "unit-test"),
                            [MemoryTable("arbitrary", rows)])
    return discover(adapter, source_revision=revision, discovery_revision=revision)
