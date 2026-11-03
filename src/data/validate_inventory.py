"""Read-only dataset inventory audit. Run with .venv/Scripts/python.exe from the project.

Writes validation evidence only under reports/data_inventory/validation/.
Original source files and the initial inventory reports are never rewritten.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import date, datetime, time
from pathlib import Path
import csv
import hashlib
import itertools
import json
import numbers
import re
import sys
from decimal import Decimal
import xml.etree.ElementTree as ET
import zipfile

import nbformat
import pandas as pd
from dateutil import parser as date_parser
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries
from openpyxl.utils.datetime import from_excel

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / 'dataset'
REPORTS = ROOT / 'reports' / 'data_inventory'
OUT = REPORTS / 'validation'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
sys.stdout.reconfigure(encoding='utf-8')


def blank(v):
    return v is None or isinstance(v, str) and not v.strip()


def key(v):
    if isinstance(v, bool): return ('boolean', v)
    if isinstance(v, (int, float)): return ('number', v)
    if isinstance(v, (date, time)): return (type(v).__name__, v.isoformat())
    return (type(v).__name__, str(v))


def dtype(v):
    if isinstance(v, bool): return 'boolean'
    if isinstance(v, datetime): return 'datetime'
    if isinstance(v, date): return 'date'
    if isinstance(v, time): return 'time'
    if isinstance(v, (int, float)): return 'number'
    if isinstance(v, str): return 'text'
    return type(v).__name__


def json_value(v):
    return v.isoformat() if isinstance(v, (date, time)) else v


def label(v):
    return re.sub(r'[^a-z0-9]+', ' ', str(v).lower()).strip()


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    s = p.stat()
    return h.hexdigest(), s.st_size, s.st_mtime_ns


def role(name):
    n = label(name)
    if str(name).strip() == '#' or n in ('s no', 'sno', 'serial no'):
        return 'row ordinal; not a business primary key'
    if re.search(r'hsn|sac|segment|category|gstcode|gst code|state code|port code', n):
        return 'classification code; not a row identifier'
    if re.search(r'phone|fax|contact number|zip|postal|street|bank|account|swift|ifs', n):
        return 'contact/location/bank attribute; uniqueness does not establish a primary key'
    if re.search(r'gstin|\bpan\b', n):
        return 'party/tax identifier; business semantics need confirmation'
    if re.search(r'\b(code|id|key|number|num|no|ref|reference|sku|document)\b', n):
        return 'entity/document reference; candidate only'
    if re.search(r'date|month|year|period', n):
        return 'date/period attribute; not established as a primary key'
    return 'measure/descriptive attribute; sampled uniqueness is insufficient'


def match_family(name):
    n = label(name)
    if n in ('customer code', 'bp code'): return 'customer-code candidate'
    if n in ('item no', 'part code sap code'): return 'item-number candidate'
    if n in ('product code', 'foreign code', 'item foreign code', 'bp catalog no'):
        return 'product/foreign-code candidate'
    if n in ('invoice num', 'invoice number'): return 'invoice-number candidate'
    if n in ('so no', 'so num'): return 'sales-order-number candidate'
    if n in ('customer ref no', 'customer ref number'): return 'customer-reference candidate'
    return None


def date_result(v, column_name=''):
    """Return alternatives without choosing an ambiguous day/month order."""
    if isinstance(v, datetime): return ('native Excel datetime', [v.replace(tzinfo=None)], '')
    if isinstance(v, date): return ('native Excel date', [datetime.combine(v, time.min)], '')
    if not isinstance(v, str): return ('non-date numeric/other value', [], 'No Excel serial-date assumption')
    t = v.strip()
    year_note = ''
    try:
        if label(column_name) == 'revision month' and re.fullmatch(r'\d{1,2}', t) and 1 <= int(t) <= 12:
            return ('month number without year', [], 'Month-like attribute, not a complete date; confirm year and meaning')
        m = re.fullmatch(r'(\d{4})-(\d{2})', t)
        if m:
            return ('month period, represented by first day', [datetime(int(m.group(1)), int(m.group(2)), 1)], 'Year-month period; first day is a display convention, not an observed day')
        m = re.fullmatch(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})(?:[ T]00:00(?::00)?)?', t)
        if m:
            a, b, y = map(int, m.groups())
            if len(m.group(3)) == 2:
                y += 2000 if y <= 68 else 1900
                year_note = 'Two-digit year: conventional 00-68=>2000-2068, 69-99=>1969-1999; confirm century'
            choices = []
            for month, day in ((b, a), (a, b)):
                try: choices.append(datetime(y, month, day))
                except ValueError: choices.append(None)
            if choices[0] and choices[1] and choices[0] != choices[1]:
                return ('ambiguous day/month', choices, year_note)
            if choices[0] and choices[1]: return ('same under DMY and MDY', [choices[0]], year_note)
            if choices[0]: return ('unambiguous DMY by calendar', [choices[0]], year_note)
            if choices[1]: return ('unambiguous MDY by calendar', [choices[1]], year_note)
            return ('invalid calendar date', [], year_note)
        m = re.fullmatch(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?:[ T].*)?', t)
        if m: return ('explicit year-month-day', [datetime(*map(int, m.groups()))], '')
        m = re.fullmatch(r'([A-Za-z]+)[\s/.-]+(\d{2}|\d{4})', t)
        if m:
            month = datetime.strptime(m.group(1)[:3].title(), '%b').month
            y = int(m.group(2))
            if len(m.group(2)) == 2:
                y += 2000 if y <= 68 else 1900
                year_note = 'Two-digit year; century requires confirmation'
            return ('month period, represented by first day', [datetime(y, month, 1)], year_note)
        # Restrict textual parsing to strings with an explicit alphabetic month
        # and a four-digit year. No arbitrary default year or fuzzy parsing.
        if re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[A-Za-z]*\b', t, re.I) and re.search(r'\b\d{4}\b', t):
            parsed = date_parser.parse(t, fuzzy=False, default=datetime(1900, 1, 1))
            return ('textual month with explicit year', [parsed.replace(tzinfo=None)], '')
        return ('unrecognized date text', [], 'No implicit date format selected')
    except (ValueError, OverflowError, TypeError):
        return ('invalid calendar date or malformed month', [], '')


def xml_audit(z, path):
    result = {'physical_xml_rows': 0, 'max_xml_row': 0, 'max_xml_column': 0,
              'declared_dimension': '', 'formula_cells': 0, 'missing_or_empty_formula_cache': 0,
              'formula_error_cache': 0, 'formula_zero_cache': 0}
    merged, formula_details = [], []
    with z.open(path) as source:
        for event, elem in ET.iterparse(source, events=('end',)):
            if elem.tag == NS + 'dimension': result['declared_dimension'] = elem.get('ref', '')
            elif elem.tag == NS + 'c':
                address = elem.get('r', '')
                if address:
                    r, c = coordinate_to_tuple(address)
                    result['max_xml_row'] = max(result['max_xml_row'], r)
                    result['max_xml_column'] = max(result['max_xml_column'], c)
                formula = elem.find(NS + 'f')
                if formula is not None:
                    result['formula_cells'] += 1
                    cached = elem.find(NS + 'v')
                    cache_value = cached.text if cached is not None else None
                    unavailable = cache_value is None
                    result['missing_or_empty_formula_cache'] += unavailable
                    result['formula_error_cache'] += elem.get('t') == 'e'
                    result['formula_zero_cache'] += cache_value == '0'
                    formula_details.append({'cell': address, 'formula': formula.text or '',
                                            'formula_type': formula.get('t', ''), 'cache': cache_value,
                                            'missing_or_empty_cache': unavailable, 'cell_type': elem.get('t', '')})
                elem.clear()
            elif elem.tag == NS + 'row':
                result['physical_xml_rows'] += 1
                result['max_xml_row'] = max(result['max_xml_row'], int(elem.get('r', 0)))
                elem.clear()
            elif elem.tag == NS + 'mergeCell':
                merged.append(elem.get('ref'))
                elem.clear()
    result['merged_ranges_json'] = json.dumps(merged)
    return result, merged, formula_details


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    old_files = pd.read_excel(REPORTS / 'excel_file_inventory.xlsx', sheet_name='Files')
    old_sheets = pd.read_excel(REPORTS / 'worksheet_inventory.xlsx', sheet_name='Worksheets')
    old_cols = pd.read_excel(REPORTS / 'column_metadata.xlsx')
    old_dates = pd.read_excel(REPORTS / 'date_coverage.xlsx')
    old_samples = pd.read_excel(REPORTS / 'sample_data.xlsx')
    old_hashes = dict(zip(old_files.file, old_files.sha256_before))
    old_sheet_map = {(r.file, r.worksheet): r._asdict() for r in old_sheets.itertuples(index=False)}
    old_col_map = {(r.file, r.worksheet, int(r.column_number)): r._asdict() for r in old_cols.itertuples(index=False)}
    old_date_map = {(r.file, r.worksheet, int(r.column_number)): r._asdict() for r in old_dates.itertuples(index=False)}
    nb = nbformat.read(ROOT / 'notebooks/01_data_inventory.ipynb', as_version=4)
    # Use the documented previous parser solely to compare its published results.
    env = {'Counter': Counter, 'deque': deque, 'datetime': datetime, 'date': date,
           'time': time, 're': re, 'date_parser': date_parser}
    exec(next(c.source for c in nb.cells if c.cell_type == 'code' and 'def parse_date(value):' in c.source), env)
    legacy_parse = env['parse_date']

    discovered = sorted(p for p in DATASET.rglob('*') if p.is_file())
    before = {p: digest(p) for p in discovered}
    sources, headers, counts, columns, dates, tokens, ids = [], [], [], [], [], [], []
    formulas, formula_cells, comparisons, failures = [], [], [], []
    matching_columns = []

    def compare(file, sheet, metric, prior, actual):
        if isinstance(prior, float) and pd.isna(prior): prior = None
        comparisons.append({'file': file, 'worksheet': sheet, 'metric': metric,
                            'initial_report_value': str(prior), 'audited_source_value': str(actual),
                            'match': prior == actual})

    def inspect(name, sheet, iterator, header_row, kind, xml=None, merged=(), state='', encoding='', epoch=None):
        baseline = old_sheet_map.get((name, sheet))
        prefix = list(itertools.islice(iterator, max(10, header_row)))
        raw_header = list(prefix[header_row - 1]) if len(prefix) >= header_row else []
        ncols = len(raw_header)
        types, nonempty, all_nonempty = [], [], []
        counters, d_tokens = {}, {}
        first, last = [], deque(maxlen=5)
        data_rows = total_rows = empty_rows = empty_data_rows = 0
        candidate_positions = set()
        date_positions = set()

        def add_columns(width):
            nonlocal ncols
            while len(types) < width:
                pos = len(types) + 1
                raw = raw_header[pos - 1] if pos <= len(raw_header) else None
                name_label = str(raw) if not blank(raw) else f'<blank column {pos}>'
                orig = old_col_map.get((name, sheet, pos), {})
                if orig.get('potential_identifier', False) or re.search(r'\b(code|id|key|number|num|no|ref|reference|sku|document|gstin|pan)\b', label(name_label)) or name_label == '#':
                    candidate_positions.add(pos)
                    counters[pos] = Counter()
                if orig.get('potential_date_column', False) or re.search(r'\b(date|month|year|period|day)\b', label(name_label)):
                    date_positions.add(pos)
                    d_tokens[pos] = {}
                types.append(Counter()); nonempty.append(0); all_nonempty.append(0)
            ncols = max(ncols, width)

        add_columns(ncols)
        for r, values in enumerate(itertools.chain(prefix, iterator), 1):
            total_rows += 1
            add_columns(len(values))
            is_empty = all(blank(v) for v in values)
            empty_rows += is_empty
            for c, value in enumerate(values, 1):
                if not blank(value): all_nonempty[c - 1] += 1
            if r <= header_row: continue
            data_rows += 1
            empty_data_rows += is_empty
            if not is_empty:
                sample = (r, [json_value(v) for v in values])
                if len(first) < 5: first.append(sample)
                last.append(sample)
            for c, v in enumerate(values, 1):
                if blank(v): continue
                nonempty[c - 1] += 1
                types[c - 1][dtype(v)] += 1
                if isinstance(v, (date, datetime)) and c not in date_positions:
                    date_positions.add(c); d_tokens[c] = {}
                if c in candidate_positions: counters[c][key(v)] += 1
                if c in date_positions:
                    k = key(v)
                    if k not in d_tokens[c]:
                        column_name = raw_header[c - 1] if c <= len(raw_header) else ''
                        result, alternatives, note = date_result(v, column_name)
                        serial_candidate = ''
                        if epoch is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 <= v <= 80000:
                            serial_candidate = from_excel(v, epoch=epoch).isoformat()
                            note = f'Possible Excel serial date using workbook epoch {epoch.date()}; business confirmation required; excluded from accepted date coverage'
                        try: old = legacy_parse(v)
                        except Exception: old = None
                        d_tokens[c][k] = {'value': str(json_value(v)), 'kind': dtype(v),
                            'count': 0, 'first_rows': [], 'status': result,
                            'alternatives': alternatives, 'note': note, 'legacy': old,
                            'serial_candidate': serial_candidate}
                    t = d_tokens[c][k]
                    t['count'] += 1
                    if len(t['first_rows']) < 5: t['first_rows'].append(r)

        padded_header = raw_header + [None] * (ncols - len(raw_header))
        col_names = [str(v) if not blank(v) else f'<blank column {c}>' for c, v in enumerate(padded_header, 1)]
        blank_headers = [c for c, v in enumerate(padded_header, 1) if blank(v)]
        # Unicode-aware comparison keeps Japanese labels distinct rather than
        # collapsing all non-ASCII headers to an empty string.
        normalized_names = [re.sub(r'[\W_]+', ' ', str(v).casefold()).strip()
                            for v in padded_header if not blank(v)]
        duplicate_headers = [n for n, num in Counter(normalized_names).items() if num > 1]
        header_merges = []
        for ref in merged:
            _, minr, _, maxr = range_boundaries(ref)
            if minr <= header_row <= maxr: header_merges.append(ref)
        headers.append({'file': name, 'worksheet': sheet, 'header_excel_row': header_row,
            'first_row_is_table_header': header_row == 1, 'blank_header_columns': json.dumps(blank_headers),
            'duplicate_labels_after_label_comparison': json.dumps(duplicate_headers),
            'merged_ranges': json.dumps(list(merged)), 'merged_ranges_intersecting_header': json.dumps(header_merges),
            'header_labels_json': json.dumps([json_value(v) for v in padded_header], ensure_ascii=False),
            'top_10_rows_json': json.dumps([[json_value(v) for v in row] for row in prefix], ensure_ascii=False),
            'layout': 'table starts at row 1' if header_row == 1 else 'title/metadata preamble above a single table header row',
            'manual_confirmation': 'Blank header needs business label' if blank_headers else ('Merged header needs review' if header_merges else ''),
            'sheet_state': state, 'csv_encoding': encoding})
        metrics = {'worksheet_rows_scanned': total_rows, 'worksheet_columns_scanned': ncols,
            'data_rows_below_header': data_rows, 'empty_rows_entire_worksheet': empty_rows,
            'empty_data_rows': empty_data_rows, 'empty_columns_entire_worksheet': sum(x == 0 for x in all_nonempty),
            'empty_data_columns': sum(x == 0 for x in nonempty), 'missing_data_values': sum(data_rows - x for x in nonempty)}
        counts.append({'file': name, 'worksheet': sheet, 'format': kind, **metrics})
        if baseline:
            for metric, value in metrics.items(): compare(name, sheet, metric, baseline[metric], value)
            compare(name, sheet, 'column_names_json_in_order', json.loads(baseline['column_names_json_in_order']), [json_value(v) for v in padded_header])
            if xml:
                maxr, maxc = xml['max_xml_row'], xml['max_xml_column']
                if xml['declared_dimension']:
                    _, _, declared_c, declared_r = range_boundaries(xml['declared_dimension'])
                    maxr, maxc = max(maxr, declared_r), max(maxc, declared_c)
                compare(name, sheet, 'rows_vs_independent_XML_extent', total_rows, maxr)
                compare(name, sheet, 'columns_vs_independent_XML_extent', ncols, maxc)
            source_samples = {'first': first, 'last': list(last)}
            for which, records in source_samples.items():
                reported = old_samples[(old_samples.file == name) & (old_samples.worksheet == sheet) & (old_samples['sample'] == which)]
                actual = [(int(r.excel_row_number), json.loads(r.record_values_json_in_column_order)) for r in reported.itertuples()]
                compare(name, sheet, f'{which}_five_records', actual, records)

        for c in range(1, ncols + 1):
            nm = col_names[c - 1]
            col = {'file': name, 'worksheet': sheet, 'column_number': c, 'column_name': nm,
                'data_rows': data_rows, 'missing_values': data_rows - nonempty[c - 1],
                'nonblank_values': nonempty[c - 1], 'types_and_counts_json': json.dumps(dict(types[c - 1])),
                'entire_sheet_column_empty': all_nonempty[c - 1] == 0}
            columns.append(col)
            orig = old_col_map.get((name, sheet, c))
            if orig:
                compare(name, sheet, f'column_{c}_missing', orig['missing_data_values'], col['missing_values'])
                compare(name, sheet, f'column_{c}_nonblank', orig['nonblank_data_values'], col['nonblank_values'])
                compare(name, sheet, f'column_{c}_label', orig['column_name'], nm)
                reported_types = {} if orig['observed_data_types_and_counts'] == 'no nonblank values' else {a: int(b) for a, b in (part.rsplit(': ', 1) for part in orig['observed_data_types_and_counts'].split(', '))}
                compare(name, sheet, f'column_{c}_type_counts', reported_types, dict(types[c - 1]))
                compare(name, sheet, f'column_{c}_empty', bool(orig['completely_empty_entire_worksheet']), col['entire_sheet_column_empty'])
            if c in candidate_positions:
                counter = counters[c]
                repeated = sum(1 for count in counter.values() if count > 1)
                dup_excess = sum(count - 1 for count in counter.values())
                semantic_role = role(nm)
                unique = len(counter) == nonempty[c - 1] and nonempty[c - 1] > 0
                ids.append({'file': name, 'worksheet': sheet, 'column_number': c, 'column_name': nm,
                    'initially_flagged': bool(orig and orig.get('potential_identifier')),
                    'semantic_role': semantic_role, 'data_rows': data_rows,
                    'null_or_blank_rows': data_rows - nonempty[c - 1],
                    'nulls_on_nonempty_rows': data_rows - nonempty[c - 1] - empty_data_rows,
                    'entirely_empty_data_rows': empty_data_rows, 'nonblank_rows': nonempty[c - 1],
                    'distinct_nonblank_values': len(counter), 'duplicate_value_groups': repeated,
                    'duplicate_excess_rows': dup_excess,
                    'rows_with_duplicated_values': sum(n for n in counter.values() if n > 1),
                    'full_nonblank_column_unique': unique,
                    'unique_and_no_nulls': unique and nonempty[c - 1] == data_rows,
                    'empirical_primary_key_candidate': unique and nonempty[c - 1] == data_rows and semantic_role.startswith('entity/document'),
                    'primary_key_confirmed': False})
                family = match_family(nm)
                if family:
                    matching_columns.append({'file': name, 'worksheet': sheet, 'column_name': nm,
                        'family': family, 'counter': counter})

        for c in sorted(date_positions):
            entries = list(d_tokens[c].values())
            status_counts = Counter()
            unambiguous, all_options, legacy_dates = [], [], []
            legacy_parsed = ambiguous = unresolved = period_values = two_digit = different = 0
            for t in entries:
                n = t['count']; status = t['status']; alternatives = t['alternatives']
                status_counts[status] += n
                if t['legacy'] is not None: legacy_dates.append(t['legacy']); legacy_parsed += n
                if status == 'ambiguous day/month': ambiguous += n
                elif not alternatives: unresolved += n
                elif status.startswith('month period'): period_values += n
                else: unambiguous.extend(alternatives)
                all_options.extend(alternatives)
                if 'Two-digit' in t['note']: two_digit += n
                if len(alternatives) == 1 and t['legacy'] is not None and t['legacy'].date() != alternatives[0].date(): different += n
                if status == 'ambiguous day/month' or not alternatives or t['note']:
                    tokens.append({'file': name, 'worksheet': sheet, 'column_number': c,
                        'column_name': col_names[c - 1], 'raw_value': t['value'], 'source_type': t['kind'],
                        'occurrences': n, 'first_source_rows': json.dumps(t['first_rows']), 'status': status,
                        'possible_dates': json.dumps([v.isoformat() for v in alternatives]),
                        'possible_excel_serial_date_unconfirmed': t['serial_candidate'],
                        'previous_assumed_date': t['legacy'].isoformat() if t['legacy'] else '', 'note': t['note']})
            def low(v): return min(v).isoformat() if v else ''
            def high(v): return max(v).isoformat() if v else ''
            dates.append({'file': name, 'worksheet': sheet, 'column_number': c, 'column_name': col_names[c - 1],
                'nonblank_values': nonempty[c - 1], 'missing_values': data_rows - nonempty[c - 1],
                'legacy_parsed_values': legacy_parsed, 'ambiguous_day_month_values': ambiguous,
                'unresolved_or_invalid_values': unresolved, 'month_period_values': period_values,
                'possible_excel_serial_values_unconfirmed': sum(t['count'] for t in entries if t['serial_candidate']),
                'month_number_without_year_values': status_counts['month number without year'],
                'two_digit_year_values': two_digit, 'unambiguous_values': nonempty[c - 1] - ambiguous - unresolved - period_values,
                'unambiguous_min_date': low(unambiguous), 'unambiguous_max_date': high(unambiguous),
                'possible_coverage_min_including_alternatives_and_periods': low(all_options),
                'possible_coverage_max_including_alternatives_and_periods': high(all_options),
                'previous_assumed_min_date': low(legacy_dates), 'previous_assumed_max_date': high(legacy_dates),
                'unambiguous_values_disagreeing_with_previous_parser': different,
                'status_counts_json': json.dumps(dict(status_counts)),
                'business_format_confirmed': False})
            prev = old_date_map.get((name, sheet, c))
            if prev:
                compare(name, sheet, f'date_column_{c}_legacy_parsed_count', prev['parsed_date_values'], legacy_parsed)
                compare(name, sheet, f'date_column_{c}_legacy_min', pd.Timestamp(prev['min_date']).isoformat() if pd.notna(prev['min_date']) else '', low(legacy_dates))
                compare(name, sheet, f'date_column_{c}_legacy_max', pd.Timestamp(prev['max_date']).isoformat() if pd.notna(prev['max_date']) else '', high(legacy_dates))

    for p in discovered:
        name = str(p.relative_to(DATASET))
        source = {'file': name, 'extension': p.suffix.lower(), 'size_bytes': before[p][1],
                  'sha256_before_audit': before[p][0], 'status': 'pending', 'tables': 0}
        try:
            if p.suffix.lower() in ('.xlsx', '.xlsm'):
                book = load_workbook(p, read_only=True, data_only=True, keep_links=False)
                try:
                    with zipfile.ZipFile(p) as z:
                        workbook_xml = ET.fromstring(z.read('xl/workbook.xml'))
                        calc = workbook_xml.find(NS + 'calcPr')
                        calc_info = dict(calc.attrib) if calc is not None else {}
                        for sheet in book.worksheets:
                            try:
                                xml, merged, details = xml_audit(z, sheet._worksheet_path.lstrip('/'))
                                formulas.append({'file': name, 'worksheet': sheet.title, **xml,
                                    'calculation_properties_json': json.dumps(calc_info),
                                    'cache_freshness_proven': False if xml['formula_cells'] else 'not applicable'})
                                formula_cells.extend({'file': name, 'worksheet': sheet.title, **d} for d in details)
                                original = old_sheet_map.get((name, sheet.title))
                                if original is None:
                                    raise RuntimeError('Worksheet not in original inventory; header needs review')
                                inspect(name, sheet.title, iter(sheet.iter_rows(values_only=True)),
                                    int(original['inferred_header_excel_row']), 'Excel', xml, merged, sheet.sheet_state, epoch=book.epoch)
                                source['tables'] += 1
                            except Exception as exc:
                                failures.append({'file': name, 'worksheet': sheet.title, 'error': f'{type(exc).__name__}: {exc}'})
                    source['status'] = 'reviewed' if source['tables'] == len(book.worksheets) else 'partial failure'
                    source['business_information'] = 'Excel business source; see headers and table evidence'
                finally: book.close()
            elif p.suffix.lower() == '.csv':
                encoding = 'utf-8-sig'
                try: p.read_text(encoding=encoding)
                except UnicodeDecodeError:
                    encoding = 'cp1252'
                    p.read_text(encoding=encoding)
                with p.open('r', encoding=encoding, newline='') as f:
                    rows = list(csv.reader(f, delimiter=',', strict=True))
                width = len(rows[0]) if rows else 0
                source['csv_encoding'] = encoding
                source['csv_nonempty_rows_with_wrong_field_count'] = sum(bool(row) and len(row) != width for row in rows[1:])
                source['business_information'] = 'GST invoice lines, tax amounts and document references' if 'invoice' in p.stem.lower() else 'GST credit/debit note lines, tax amounts and original invoice references'
                inspect(name, '(CSV table)', iter(rows), 1, 'CSV', encoding=encoding)
                source['status'] = 'reviewed'; source['tables'] = 1
                source['initial_exclusion_reason'] = 'Initial inventory discovery intentionally accepted Excel extensions only; CSV is relevant and included in this audit.'
            else:
                source['status'] = 'unreviewed format'
                source['business_information'] = 'Unknown; requires review before exclusion'
        except Exception as exc:
            source['status'] = 'failed'
            failures.append({'file': name, 'worksheet': '', 'error': f'{type(exc).__name__}: {exc}'})
        sources.append(source)
        print(f"Reviewed {name}: {source['status']} ({source['tables']} tables)", flush=True)

    matching = []
    for a, b in itertools.combinations(matching_columns, 2):
        if a['family'] != b['family']: continue
        aset, bset = set(a['counter']), set(b['counter'])
        overlap = aset & bset
        matching.append({'candidate_family': a['family'], 'file_a': a['file'], 'worksheet_a': a['worksheet'],
            'column_a': a['column_name'], 'file_b': b['file'], 'worksheet_b': b['worksheet'], 'column_b': b['column_name'],
            'distinct_a': len(aset), 'distinct_b': len(bset), 'distinct_overlap': len(overlap),
            'a_distinct_match_percent': round(100 * len(overlap) / len(aset), 3) if aset else None,
            'b_distinct_match_percent': round(100 * len(overlap) / len(bset), 3) if bset else None,
            'a_nonblank_rows': sum(a['counter'].values()),
            'a_rows_matching_b': sum(a['counter'][v] for v in overlap),
            'b_nonblank_rows': sum(b['counter'].values()),
            'b_rows_matching_a': sum(b['counter'][v] for v in overlap),
            'confirmed_relationship': False,
            'method': 'Full observed values; text case/whitespace preserved; no source joins or cleaning'})

    after_paths = sorted(p for p in DATASET.rglob('*') if p.is_file())
    for p, row in zip(discovered, sources):
        try:
            after = digest(p)
            row['sha256_after_audit'] = after[0]
            row['unchanged_during_audit'] = before[p] == after
            prior = old_hashes.get(row['file'])
            row['matches_initial_inventory_hash'] = before[p][0] == prior if prior else 'not in initial Excel inventory'
        except Exception as exc:
            row['unchanged_during_audit'] = False
            failures.append({'file': row['file'], 'worksheet': '', 'error': f'Fingerprint failed: {exc}'})

    compare('(all)', '', 'Excel workbooks', len(old_files), sum(p.suffix.lower() in ('.xlsx', '.xlsm', '.xls') for p in discovered))
    compare('(all)', '', 'Excel worksheets', len(old_sheets), sum(s['tables'] for s in sources if s['extension'] in ('.xlsx', '.xlsm', '.xls')))
    compare('(all)', '', 'Excel column records', len(old_cols), sum(c['format'] == 'Excel' and c['worksheet_columns_scanned'] for c in counts))
    compare('(all)', '', 'Excel date column records', len(old_dates), sum(d['file'].lower().endswith(('.xlsx', '.xlsm', '.xls')) for d in dates))
    compare('(all)', '', 'sample data records', len(old_samples), 10 * len(old_sheets))

    tables = {'source_completeness': sources, 'header_validation': headers, 'table_counts': counts,
        'column_validation': columns, 'date_validation': dates, 'date_token_issues': tokens,
        'identifier_validation': ids, 'identifier_matching_coverage': matching,
        'formula_validation': formulas, 'formula_cells': formula_cells,
        'report_consistency': comparisons, 'validation_failures': failures}
    for filename, records in tables.items():
        frame = pd.DataFrame(records)
        if frame.empty: frame = pd.DataFrame(columns=['status'], data=[['No findings']])
        # UTF-8 BOM allows Excel to display Japanese column labels correctly.
        frame.to_csv(OUT / f'{filename}.csv', index=False, encoding='utf-8-sig')
    with pd.ExcelWriter(OUT / 'inventory_validation_evidence.xlsx', engine='openpyxl') as writer:
        for filename, records in tables.items():
            frame = pd.DataFrame(records)
            if frame.empty: frame = pd.DataFrame({'status': ['No findings']})
            frame.to_excel(writer, sheet_name=filename[:31], index=False)
            writer.sheets[filename[:31]].freeze_panes = 'A2'
            # Preserve audit literals such as '#N/A' as text. Otherwise Excel
            # error typing makes pandas read them back as missing values.
            for row in writer.sheets[filename[:31]].iter_rows():
                for cell in row:
                    if cell.data_type in ('e', 'f'):
                        cell.data_type = 's'
    # Check CSV and Excel exports against the records, preserving text such as NA,
    # whitespace and leading zeros. Only actual numeric scalars allow numeric equivalence.
    export_checks = []
    for filename, records in tables.items():
        expected = pd.DataFrame(records)
        if expected.empty: expected = pd.DataFrame({'status': ['No findings']})
        csv_read = pd.read_csv(OUT / f'{filename}.csv', dtype=str, keep_default_na=False)
        xlsx_read = pd.read_excel(OUT / 'inventory_validation_evidence.xlsx', sheet_name=filename[:31], dtype=str, keep_default_na=False)
        def export_matches(actual):
            if list(actual.columns) != list(expected.columns) or len(actual) != len(expected): return False
            for row_index in range(len(expected)):
                for col in expected.columns:
                    value = expected.iloc[row_index][col]
                    observed = actual.iloc[row_index][col]
                    if pd.isna(value): value = ''
                    if isinstance(value, numbers.Number) and not isinstance(value, bool):
                        if not observed or Decimal(str(value)) != Decimal(observed): return False
                    elif str(value) != str(observed): return False
            return True
        export_checks.append({'table': filename, 'expected_rows': len(expected),
            'csv_rows': len(csv_read), 'excel_rows': len(xlsx_read),
            'csv_content_matches_records': export_matches(csv_read),
            'excel_content_matches_records': export_matches(xlsx_read)})
    pd.DataFrame(export_checks).to_csv(OUT / 'export_verification.csv', index=False, encoding='utf-8-sig')
    summary = {'source_files': len(discovered), 'file_set_unchanged': discovered == after_paths,
        'extension_counts': dict(Counter(p.suffix.lower() for p in discovered)),
        'excel_worksheets': sum(c['format'] == 'Excel' for c in counts),
        'csv_tables': sum(c['format'] == 'CSV' for c in counts), 'validation_failures': failures,
        'all_sources_unchanged': all(s['unchanged_during_audit'] for s in sources),
        'initial_excel_hashes_match': all(s['matches_initial_inventory_hash'] is True for s in sources if s['extension'] == '.xlsx'),
        'consistency_checks': len(comparisons), 'consistency_mismatches': [c for c in comparisons if not c['match']],
        'export_verification': export_checks,
        'formula_cells': sum(f['formula_cells'] for f in formulas),
        'ambiguous_date_values': sum(d['ambiguous_day_month_values'] for d in dates),
        'unresolved_date_values': sum(d['unresolved_or_invalid_values'] for d in dates)}
    (OUT / 'audit_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    if not all(c['csv_content_matches_records'] and c['excel_content_matches_records'] for c in export_checks):
        raise RuntimeError('An audit export failed content verification; inspect export_verification.csv')


if __name__ == '__main__':
    run()
