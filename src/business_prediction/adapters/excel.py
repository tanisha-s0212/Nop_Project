"""Modern Excel adapter; formulas remain inert and cached values are not inferred."""

from io import BytesIO
from zipfile import ZipFile

from openpyxl import __version__ as reader_version, load_workbook

from .base import CellError, FileAdapter, Formula, physical_table
from ..errors import SourceError


class ExcelAdapter(FileAdapter):
    adapter_kind = "excel_ooxml"

    def __init__(self, path, config, *, header_rows=None, default_header_row=1,
                 max_uncompressed_bytes=128*1024*1024, **kwargs):
        super().__init__(path, config, **kwargs)
        self.header_rows = dict(header_rows or {})
        self.default_header_row = default_header_row
        if type(max_uncompressed_bytes) is not int or max_uncompressed_bytes < 1:
            raise ValueError("Uncompressed byte budget must be positive.")
        self.max_uncompressed_bytes = max_uncompressed_bytes

    def _settings(self):
        return {**super()._settings(), "header_rows": self.header_rows,
                "default_header_row": self.default_header_row,
                "max_uncompressed_bytes": self.max_uncompressed_bytes,
                "reader": "openpyxl", "reader_version": reader_version,
                "data_only": False, "read_only": True, "keep_links": False,
                "date_policy": "reader_number_format_decoding; no numeric serial inference"}

    def _tables_from_bytes(self, payload):
        if self.path.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise SourceError("unsupported_format", "Only xlsx and xlsm are supported by this adapter.")
        try:
            with ZipFile(BytesIO(payload)) as archive:
                if sum(i.file_size for i in archive.infolist()) > self.max_uncompressed_bytes:
                    raise SourceError("resource_limit", "Workbook exceeds the uncompressed byte budget.")
            workbook = load_workbook(BytesIO(payload), read_only=True, data_only=False, keep_links=False)
            try:
                if set(self.header_rows) - set(workbook.sheetnames):
                    raise SourceError("invalid_layout", "Header configuration names an unknown worksheet.")
                result, count = [], 0
                for i, sheet in enumerate(workbook):
                    sheet.reset_dimensions()  # Do not trust stale worksheet dimension declarations.
                    rows = []
                    for row in sheet.iter_rows():
                        count += max(1, len(row))
                        if count > self.max_cells:
                            raise SourceError("resource_limit", "Workbook exceeds the configured cell budget.")
                        rows.append(tuple(Formula(c.value) if c.data_type == "f" else
                                          CellError(c.value) if c.data_type == "e" else c.value for c in row))
                    result.append(physical_table(f"table-{i+1}", sheet.title, rows,
                                                 self.header_rows.get(sheet.title, self.default_header_row),
                                                 self.max_cells))
                return tuple(result)
            finally:
                workbook.close()
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError("unreadable_source", "Workbook could not be inspected safely.") from exc
