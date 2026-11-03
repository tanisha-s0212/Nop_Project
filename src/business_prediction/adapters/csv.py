"""CSV bytes remain text: no NA token inference or numeric/date coercion."""

import csv
import io

from .base import FileAdapter, physical_table
from ..errors import SourceError


class CSVAdapter(FileAdapter):
    adapter_kind = "csv"

    def __init__(self, path, config, *, encoding="utf-8-sig", delimiter=",", header_row=1, **kwargs):
        super().__init__(path, config, **kwargs)
        if not isinstance(delimiter, str) or len(delimiter) != 1:
            raise ValueError("CSV delimiter must be one character.")
        self.encoding, self.delimiter, self.header_row = encoding, delimiter, header_row

    def _settings(self):
        return {**super()._settings(), "encoding": self.encoding, "delimiter": self.delimiter,
                "header_row": self.header_row, "csv_strict": True, "value_policy": "raw_text"}

    def _tables_from_bytes(self, payload):
        try:
            rows, cells = [], 0
            for row in csv.reader(io.StringIO(payload.decode(self.encoding), newline=""),
                                  delimiter=self.delimiter, strict=True):
                cells += max(1, len(row))
                if cells > self.max_cells:
                    raise SourceError("resource_limit", "CSV exceeds the configured cell budget.")
                rows.append(tuple(row))
            return (physical_table("table-1", self.path.name, rows, self.header_row, self.max_cells),)
        except csv.Error as exc:
            raise SourceError("unreadable_source", "CSV cannot be parsed with the configured dialect.") from exc
