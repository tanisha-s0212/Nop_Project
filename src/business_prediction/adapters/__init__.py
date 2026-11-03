"""Read-only adapter API. Excel is optional at import time; no database connections."""

from .base import DataSourceAdapter, SourceConfig, SourceSnapshot
from .csv import CSVAdapter
from .memory import MemoryAdapter, MemoryTable

__all__ = ["DataSourceAdapter", "SourceConfig", "SourceSnapshot", "CSVAdapter", "MemoryAdapter", "MemoryTable"]
