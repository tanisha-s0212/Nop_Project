"""Read-only business structure and relationship experiments.

All source cells and prior evidence are preserved. Derived keys and joins exist
only in memory; exported outputs are aggregate diagnostics, never merged data.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from openpyxl import load_workbook

try:
    from .assess_data_quality import blank, label, typed, kind, raw_json, sha, number, pct
except ImportError:
    from assess_data_quality import blank, label, typed, kind, raw_json, sha, number, pct


def read_csv(path):
    return pd.read_csv(path, keep_default_na=False, encoding='utf-8-sig')


def normalized_key(v):
    """Explicit sensitivity experiment: trim/casefold text, preserve other types."""
    return ('text', v.strip().casefold()) if isinstance(v, str) else typed(v)


def tabulate(frame, columns=None):
    cols = list(columns or frame.columns)
    def clean(v):
        return str(v).replace('|', '\\|').replace('\n', ' ') if not blank(v) else ''
    return '\n'.join(['| ' + ' | '.join(cols) + ' |', '| ' + ' | '.join(['---']*len(cols)) + ' |'] +
        ['| ' + ' | '.join(clean(v) for v in row) + ' |' for row in frame[cols].itertuples(index=False, name=None)])


class Table:
    def __init__(self, file, sheet, header, names, rows):
        self.file, self.sheet, self.header = file, sheet, header
        self.id = f'{file} :: {sheet}'
        self.names = names
        self.frame = pd.DataFrame(rows, columns=range(len(names)), dtype=object)
        self.n = len(rows)
        self.active = np.array([any(not blank(v) for v in row) for row in rows], dtype=bool)
        self.derived = {}
        self.cache = {}
        self.numeric_cache = {}

    def position(self, name):
        matches = [i for i, v in enumerate(self.names) if label(v) == label(name)]
        if len(matches) != 1:
            raise ValueError(f'{self.id}: header {name!r} resolves to {matches}')
        return matches[0]

    def values(self, name):
        return self.derived[name] if name.startswith('@') else self.frame[self.position(name)].tolist()

    def keys(self, columns, mode='raw'):
        columns = tuple(columns)
        ck = (columns, mode)
        if ck not in self.cache:
            values = [self.values(c) for c in columns]
            encode = typed if mode == 'raw' else normalized_key
            self.cache[ck] = [None if any(blank(v) for v in row) else tuple(encode(v) for v in row)
                             for row in zip(*values)]
        return self.cache[ck]

    def numeric(self, column):
        if column not in self.numeric_cache:
            values = self.values(column)
            parsed = [number(v) for v in values]
            self.numeric_cache[column] = (np.array([x[0] for x in parsed]),
                int(sum(not blank(v) and not math.isfinite(p[0]) for v, p in zip(values, parsed))))
        return self.numeric_cache[column]


class RelationshipAnalysis:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.out = self.root / 'reports/analysis'
        self.out.mkdir(parents=True, exist_ok=True)
        self.log = self.root / 'logs/relationship_analysis.log'
        self.log.parent.mkdir(exist_ok=True)
        self.log.write_text('Relationship analysis started\n', encoding='utf-8')
        self.reference = self.root / 'reports/data_inventory/validation'
        self.quality = self.root / 'reports/data_quality'
        self.headers = read_csv(self.reference / 'header_validation.csv')
        self.expected = read_csv(self.reference / 'table_counts.csv')
        self.prior_ids = read_csv(self.quality / 'identifier_quality.csv')
        self.prior_matches = read_csv(self.quality / 'identifier_matching_coverage.csv')
        self.quality_validation = json.loads((self.quality / 'assessment_validation.json').read_text())
        self.tables = {}
        self.results = {}
        self.checks = []
        self.relations = []
        self.join_results = []
        self.financial = []
        self.conflicts = []
        self.provenance = []
        self.export_checks = []
        protected = list((self.root / 'dataset').rglob('*'))
        for folder in ('reports/data_inventory', 'reports/data_quality'):
            protected.extend((self.root / folder).rglob('*'))
        self.before = {p.relative_to(self.root).as_posix(): sha(p) for p in protected if p.is_file()}

    def progress(self, message):
        print(message, flush=True)
        with self.log.open('a', encoding='utf-8') as f:
            f.write(message + '\n')

    def check(self, test, condition, detail=''):
        self.checks.append({'test': test, 'passed': bool(condition), 'detail': str(detail)})
        if not condition:
            raise AssertionError(f'{test}: {detail}')

    def table(self, file, sheet=None):
        matches = [t for t in self.tables.values() if t.file == file and (sheet is None or t.sheet == sheet)]
        if len(matches) != 1:
            raise ValueError((file, sheet, len(matches)))
        return matches[0]

    def load(self):
        files = sorted(p for p in (self.root / 'dataset').rglob('*') if p.is_file())
        self.check('Source census exactly matches validated files',
            {p.name for p in files} == set(self.headers.file), f'{len(files)} files')
        evidence_path = self.reference / 'inventory_validation_evidence.xlsx'
        with pd.ExcelFile(evidence_path) as book:
            for sheet, frame in [('header_validation', self.headers), ('table_counts', self.expected)]:
                other = book.parse(sheet, keep_default_na=False)
                self.check(f'Inventory CSV/workbook agreement: {sheet}',
                    frame.astype(str).equals(other.astype(str)))
        old_hashes = read_csv(self.quality / 'source_integrity.csv')
        for p in files:
            self.check(f'Source matches quality baseline: {p.name}',
                sha(p) == old_hashes.loc[old_hashes.file == p.name, 'sha256_after'].iloc[0])
            refs = self.headers[self.headers.file == p.name]
            self.progress(f'Loading {p.name}')
            workbook = None
            try:
                if p.suffix.lower() == '.csv':
                    with p.open('r', encoding='utf-8-sig', newline='') as f:
                        all_rows = list(csv.reader(f, strict=True))
                    iterable = [(refs.iloc[0], all_rows)]
                else:
                    workbook = load_workbook(p, read_only=True, data_only=True)
                    self.check(f'Every worksheet covered: {p.name}', set(workbook.sheetnames) == set(refs.worksheet))
                    iterable = [(r, workbook[r.worksheet]) for r in refs.itertuples(index=False)]
                for ref, content in iterable:
                    sheet = ref['worksheet'] if isinstance(ref, pd.Series) else ref.worksheet
                    h = int(ref['header_excel_row'] if isinstance(ref, pd.Series) else ref.header_excel_row)
                    labels = json.loads(ref['header_labels_json'] if isinstance(ref, pd.Series) else ref.header_labels_json)
                    exp = self.expected[(self.expected.file == p.name) & (self.expected.worksheet == sheet)].iloc[0]
                    width = int(exp.worksheet_columns_scanned)
                    rows = content if isinstance(content, list) else content.iter_rows(values_only=True)
                    data = []
                    for i, row in enumerate(rows, 1):
                        if len(row)>width and any(not blank(v) for v in row[width:]):
                            raise ValueError(f'{p.name}/{sheet}: source data exceeds validated extent at row {i}')
                        padded = list(row[:width]) + [None]*max(0, width-len(row))
                        if i == h:
                            self.check(f'Validated header preserved: {p.name}/{sheet}',
                                padded == labels or [None if v == '' else v for v in padded] == labels)
                        elif i > h:
                            data.append(padded)
                    t = Table(p.name, sheet, h, labels, data)
                    self.check(f'Extent matches inventory: {t.id}',
                        t.n == int(exp.data_rows_below_header) and len(t.names) == width)
                    self.check(f'Empty rows match inventory: {t.id}',
                        int((~t.active).sum()) == int(exp.empty_data_rows))
                    self.tables[t.id] = t
            finally:
                if workbook is not None:
                    workbook.close()
        self.check('20 source tables loaded', len(self.tables) == 20)
        self.progress('All 20 tables loaded without changing source values')

    def derive_keys(self):
        rules, scope_checks = [], []
        for t in self.tables.values():
            if t.file == 'GSTR1_Invoice.csv':
                cols = ['Doc_Series_Prefix', 'Doc_Series', 'Invoice_Number', 'Doc_Series_Suffix']
                t.derived['@scoped_invoice'] = [None if blank(row[2]) or blank(row[1]) or blank(row[0]) else
                    ''.join('' if blank(v) else str(v) for v in row) for row in zip(*(t.values(c) for c in cols))]
                rules.append({'table': t.id, 'diagnostic_key': '@scoped_invoice',
                    'rule': 'Doc_Series_Prefix + Doc_Series + Invoice_Number + Doc_Series_Suffix; blanks allowed only in suffix',
                    'scope_uncertainty': 'Observed prefix/series reconstruction only; issuer and fiscal scope need owner confirmation'})
            elif t.file.startswith('GSTR1_Credit'):
                cols = ['Doc_Series_Prefix', 'Doc_Series_Suffix', 'CreditDebitNote_Number']
                t.derived['@scoped_note'] = [None if any(blank(v) for v in row) else ''.join(str(v) for v in row)
                    for row in zip(*(t.values(c) for c in cols))]
                rules.append({'table': t.id, 'diagnostic_key': '@scoped_note',
                    'rule': 'Doc_Series_Prefix + Doc_Series_Suffix + CreditDebitNote_Number; suffix already contains CN/DN and period',
                    'scope_uncertainty': 'Verify series versus suffix and document type consistency; not a declared business key'})
                conflicts = 0
                type_conflicts = 0
                for series,suffix,typ in zip(t.values('Doc_Series'),t.values('Doc_Series_Suffix'),t.values('Type_Credit_or_Debit')):
                    if blank(series) and blank(suffix): continue
                    if str(series).strip('/') != str(suffix).strip('/'): conflicts += 1
                    expected = 'C' if str(series).startswith('CN/') else 'D' if str(series).startswith('DN/') else None
                    if expected is None or str(typ).strip().upper()!=expected: type_conflicts += 1
                scope_checks.append({'table':t.id,'check':'Note series versus suffix / C-D type',
                    'series_suffix_disagreements':conflicts,'type_series_disagreements_diagnostic':type_conflicts,
                    'interpretation':'Slash wrappers and trim/uppercase used explicitly for comparison only; original tokens retained'})
            elif t.file.startswith('Exchange Rate'):
                periods = []
                for v in t.values('Rate Month'):
                    if isinstance(v, (datetime, date)):
                        periods.append(v.strftime('%Y-%m'))
                    elif isinstance(v, str):
                        out = None
                        for fmt in ('%Y-%m', '%b-%y', '%B %Y', '%b %Y', '%b-%Y', '%B-%Y'):
                            try:
                                out = datetime.strptime(v, fmt).strftime('%Y-%m'); break
                            except ValueError:
                                pass
                        periods.append(out)
                    else:
                        periods.append(None)
                t.derived['@explicit_month_period'] = periods
                rules.append({'table': t.id, 'diagnostic_key': '@explicit_month_period',
                    'rule': 'Native month or explicit YYYY-MM / English named month only; no transaction date parsing',
                    'scope_uncertainty': 'Fiscal period start/end applicability and synthetic rates require confirmation'})
                self.check(f'Every explicit rate period recognized: {t.id}', all(v is not None for v in periods))
        self.results['key_derivation_rules'] = pd.DataFrame(rules)
        self.results['key_scope_checks'] = pd.DataFrame(scope_checks)

    def profile_key(self, t, cols, name=None, note='Candidate only; scope and business meaning unconfirmed'):
        keys = t.keys(cols)
        counts = Counter(k for k in keys if k is not None)
        n = sum(counts.values())
        return {'table': t.id, 'file': t.file, 'worksheet': t.sheet,
            'key': name or ' + '.join(cols), 'columns': raw_json(cols), 'data_rows': t.n,
            'null_rows': t.n-n, 'nonblank_rows': n, 'distinct_values': len(counts),
            'duplicate_excess_rows': n-len(counts), 'duplicate_groups': sum(v > 1 for v in counts.values()),
            'nonblank_uniqueness_percent': pct(len(counts), n),
            'empirically_unique_on_nonblank': bool(n and n == len(counts)),
            'complete_and_unique': bool(n == t.n and n and n == len(counts)),
            'business_primary_key_confirmed': False, 'interpretation': note}

    def identifiers(self):
        rows, formats = [], []
        for old in self.prior_ids.itertuples(index=False):
            t = self.table(old.file, old.worksheet)
            idx = int(old.column_number)-1
            col = t.names[idx]
            self.check(f'Identifier header position: {t.id}/{idx+1}', col == old.column_name)
            r = self.profile_key(t, [col], note=old.semantic_role)
            self.check(f'Full identifier metrics reconcile: {t.id}/{idx+1}',
                (r['null_rows'], r['distinct_values'], r['duplicate_excess_rows']) ==
                (int(old.null_or_blank_rows), int(old.distinct_nonblank_values), int(old.duplicate_excess_rows)))
            values = t.frame[idx].tolist()
            populated = [v for v in values if not blank(v)]
            type_counts = Counter(kind(v) for v in populated)
            format_counts = Counter(self.value_format(v) for v in populated)
            trim = sum(isinstance(v, str) and v != v.strip() for v in populated)
            raw_counts = Counter(typed(v) for v in populated)
            normalized = defaultdict(set)
            for v in populated:
                normalized[normalized_key(v)].add(typed(v))
            r.update({'column_number': idx+1, 'column_name': col,
                'source_types': raw_json(type_counts), 'format_counts': raw_json(format_counts),
                'outer_whitespace_rows': trim, 'case_trim_collision_groups': sum(len(v)>1 for v in normalized.values()),
                'examples_raw': raw_json(list(dict.fromkeys(raw_json(v) for v in populated))[:5]),
                'role': old.semantic_role, 'matching_comparisons': 0,
                'relationship_status': 'No semantic mapping demonstrated; ordinal/attribute uniqueness is not a business key'})
            rows.append(r)
            for fmt, count in format_counts.items():
                formats.append({'table': t.id, 'column': col, 'format': fmt, 'rows': count})
        self.results['identifier_profiles'] = pd.DataFrame(rows)
        self.results['identifier_formats'] = pd.DataFrame(formats)
        self.check('All 135 identifier candidates profiled', len(rows) == 135)
        composites = []
        for t in self.tables.values():
            candidates = []
            if t.file.startswith('Sales Order Report'):
                candidates = [['SO No'], ['SO No','Item No'], ['Customer Code','SO No'], ['SO No','Item No','Customer Ref No']]
            elif t.file.startswith('Sales Invoice Details'):
                candidates = [['Invoice Num'], ['Invoice Num','Part Code SAP Code'], ['Invoice Num','Item Description'],
                              ['SO Num','Part Code SAP Code'], ['Invoice Num','Customer Billing GSTIN']]
            elif t.file == 'GSTR1_Invoice.csv':
                candidates = [['Invoice_Number'], ['Doc_Series_Prefix','Doc_Series','Invoice_Number'],
                              ['@scoped_invoice'], ['@scoped_invoice','Item_Description']]
            elif t.file.startswith('GSTR1_Credit'):
                candidates = [['CreditDebitNote_Number'], ['Doc_Series','CreditDebitNote_Number'],
                              ['@scoped_note'], ['@scoped_note','Item_Description']]
            elif t.file.startswith('Inventory Audit'):
                candidates = [['Document','Doc. Row','Whse'], ['Document','Doc. Row','Whse','Posting Date']]
            elif t.file.startswith('Exchange Rate'):
                candidates = [['@explicit_month_period','From Currency','To Currency']]
            for cols in candidates:
                composites.append(self.profile_key(t, cols, note='Full raw-key diagnostic; missing key components excluded from distinct/duplicate counts. Dates not converted. Uniqueness does not establish line identity.'))
        self.results['composite_keys'] = pd.DataFrame(composites)

    @staticmethod
    def value_format(v):
        if not isinstance(v, str): return kind(v)
        s = v.strip()
        if re.fullmatch(r'\d+', s): fmt = 'digits as text'
        elif re.fullmatch(r'[A-Za-z]+\d+', s): fmt = 'letter prefix + digits'
        elif '/' in s: fmt = 'slash-delimited text'
        elif '-' in s: fmt = 'hyphen-delimited text'
        else: fmt = 'other text'
        return fmt + ('; outer whitespace' if s != v else '')

    def grain(self):
        rows, contexts, services, shapes = [], [], [], []
        for t in self.tables.values():
            f, s = t.file, t.sheet
            uncertainty = 'Business owner must confirm entity scope, extraction filters, history and source authority.'
            evidence = ''
            doc, attrs = None, []
            if f.startswith('Customer Master'):
                entity, grain = 'Customer / business partner', 'Customer-master record candidate; repeated codes in some extracts'
                key = self.profile_key(t, ['CUSTOMER CODE'])
                evidence = f"Customer code: {key['distinct_values']} distinct; {key['duplicate_excess_rows']} excess repeated codes; customer/contact/address/tax attributes."
            elif f.startswith('Item Master'):
                entity, grain = 'Product / item', 'Item-master record candidate with stock and commercial attributes'
                key = self.profile_key(t, ['Item No.'])
                evidence = f"Item number: {key['distinct_values']} distinct; {key['duplicate_excess_rows']} excess repeated codes; descriptions, stock, pricing-unit and classification attributes."
                uncertainty += ' In Stock/Value are extract attributes; snapshot/as-of and valuation basis unconfirmed.'
            elif f.startswith('Sales Order Report'):
                entity, grain = 'Sales order detail', 'Order item/service-like detail record; not one row per order'
                doc, attrs = 'SO No', ['Customer Code', 'Customer Ref No', 'Posting Date', 'Status']
                item = t.values('Item No')
                missing = np.array([blank(v) for v in item]) & t.active
                qty, _ = t.numeric('Quantity'); amount, _ = t.numeric('Total (LC)')
                services.append({'table': t.id, 'indicator': 'Blank item on nonempty order row', 'rows': int(missing.sum()),
                    'zero_quantity_rows': int((missing & (qty == 0)).sum()),
                    'nonzero_line_value_rows': int((missing & np.isfinite(amount) & (amount != 0)).sum()),
                    'interpretation': 'Service/charge-like candidate only; no explicit service flag in this export'})
                uncertainty += ' No stable order-line ID; repeated SO/item can be legitimate split lines or duplicate extracts; blank item is not proof of service.'
            elif f.startswith('Sales Invoice Details'):
                entity, grain = 'Sales invoice detail', 'Invoice goods/service detail candidate with repeated document totals'
                doc, attrs = 'Invoice Num', ['Customer Billing Name','Invoice Date','Invoice Total Include GST','SO Num']
                evidence = 'SAP product, goods/service flag, quantity, line tax/base/total and repeated invoice header fields. '
                flags = Counter(str(v) for v in t.values('Item Type G or S') if not blank(v))
                services.append({'table': t.id, 'indicator': 'Explicit goods/service values', 'rows': int(t.active.sum()),
                    'flag_counts': raw_json(flags), 'interpretation': 'Raw G/S classification observed; confirm meaning and scope; no separate service master supplied'})
                uncertainty += ' No stable invoice-line ID; document total is not additive across detail rows. SO can differ across invoice lines.'
            elif f == 'GSTR1_Invoice.csv':
                entity, grain = 'GST invoice reporting detail', 'Tax reporting line candidate, scoped invoice number repeated across lines'
                doc, attrs = '@scoped_invoice', ['Customer_Billing_Name','Invoice_Date','Invoice_Value']
                evidence = 'Series/prefix/suffix and raw invoice number; item description, GST components, line total versus invoice value. '
                uncertainty += ' Raw invoice number omits series/year; GST description/HSN is not a unique product ID; reconcile with invoice export before treating as independent sales.'
            elif f.startswith('GSTR1_Credit'):
                entity, grain = 'GST credit/debit adjustment', 'Credit/debit reporting detail candidate; observed rows per scoped note assessed separately'
                doc, attrs = '@scoped_note', ['Type_Credit_or_Debit','CreditDebitNote_Date','Credit_Debit_Note_Value','Invoice_Number']
                evidence = 'Credit/debit type, note series and original invoice references with item/tax amounts. '
                uncertainty += ' One observed row per note does not establish document-level grain; issuer, sign conventions, line completeness and linked original invoices need confirmation.'
            elif f.startswith('Inventory Audit'):
                entity, grain = 'Inventory grouped audit / movement', 'Mixed item labels, opening-balance lines and movement details'
                item, docval = t.values('Item No.'), t.values('Document')
                itemmask = np.array([not blank(v) for v in item])
                openmask = np.array([isinstance(v,str) and v.strip().casefold() == 'opening balance' for v in docval])
                move = np.array([not blank(v) for v in docval]) & ~openmask
                for name, mask in [('item-labelled rows', itemmask), ('opening balance rows', openmask),
                                   ('document movement rows', move), ('movement rows without raw item', move & ~itemmask)]:
                    shapes.append({'table': t.id, 'row_class': name, 'rows': int(mask.sum()),
                        'overlapping_classes': True, 'interpretation': 'Raw layout only; no forward fill or reconstruction performed'})
                evidence = f'{int(itemmask.sum())} item-labelled rows; {int(openmask.sum())} opening balance rows; {int(move.sum())} movement rows; {int((move & ~itemmask).sum())} movement rows lack raw item.'
                uncertainty += ' Group context is required before movement-to-product mapping; do not sum cumulative/opening and movement values together. Filename dates are unconfirmed.'
            elif f.startswith('Exchange Rate'):
                entity, grain = 'Currency rate period', 'Monthly currency-pair period record candidate'
                evidence = 'Explicit SYNTHETIC DATA title; monthly period and From/To currency with rate, start/end fields.'
                uncertainty += ' Period applicability, start/end semantics and use of synthetic values require approval; no date-based conversion join attempted.'
            elif s == 'Customer list':
                entity, grain = 'Customer reference / crosswalk candidate', 'Reference customer row with sparse alternate code and BP_CODE'
                evidence = 'Explicit SYNTHETIC DATA title; numeric Customer Code and alphanumeric BP_CODE are separate observed domains.'
                uncertainty += ' Do not equate numeric Customer Code with customer-master C-prefixed code; BP mapping coverage must be assessed.'
            elif s == 'Country master':
                entity, grain = 'Country / geographic reference', 'Country-code row with multilingual names and segment'
                evidence = '11 distinct country codes and country names; multilingual aliases and geographic segment.'
                uncertainty += ' Free-text transaction/master country names need an approved alias mapping; ISO convention is a hypothesis, not an enforced constraint.'
            else:
                entity, grain = 'Product classification reference', 'Product-code row in agency/product classification list'
                evidence = 'Unique observed Product code with category, product and middle segments.'
                if s == 'PCT_NOPJ':
                    v = t.frame[0].tolist()
                    evidence += f' Blank first header has {sum(not blank(x) for x in v)} populated values: {raw_json(list(dict.fromkeys(v)))}.'
                uncertainty += ' Code namespace and link to foreign product codes need confirmation; unnamed PCT_NOPJ field retained without invented name.'
            if doc:
                keys = t.keys([doc]); counts = Counter(k for k in keys if k is not None)
                evidence += f'{len(counts)} raw/scoped document identifiers; {sum(n>1 for n in counts.values())} repeated groups; maximum {max(counts.values(),default=0)} rows/document.'
                for attr in attrs:
                    groups = defaultdict(set)
                    for k, val in zip(keys, t.values(attr)):
                        if k is not None and not blank(val): groups[k].add(typed(val))
                    varying = {k for k,v in groups.items() if len(v)>1}
                    contexts.append({'table': t.id, 'document_key': doc, 'attribute': attr,
                        'document_groups': len(counts), 'groups_with_multiple_nonblank_raw_values': len(varying),
                        'rows_in_varying_groups': sum(counts[k] for k in varying),
                        'interpretation': 'Raw variation only. Formatting, reused key scope, legitimate line attributes or business conflicts require review; no consolidation.'})
            rows.append({'table':t.id,'file': f,'worksheet': s,'row_count':t.n,'nonempty_rows':int(t.active.sum()),
                'empty_rows':int((~t.active).sum()),'column_count':len(t.names),'candidate_business_entity':entity,
                'candidate_record_grain':grain,'evidence':evidence,'business_confirmation':uncertainty})
        self.results['dataset_granularity'] = pd.DataFrame(rows)
        self.results['document_context'] = pd.DataFrame(contexts)
        self.results['inventory_row_shapes'] = pd.DataFrame(shapes)
        self.results['service_indicators'] = pd.DataFrame(services)

    def add_relation(self, a, ac, b, bc, rationale, expected='Unconfirmed; investigate matched key multiplicity',
                     mode='raw', test=False, scope='Candidate value overlap; source authority unconfirmed'):
        # Resolve labels without changing source headers; report their exact spelling/spacing.
        ac = [c if c.startswith('@') else a.names[a.position(c)] for c in ac]
        bc = [c if c.startswith('@') else b.names[b.position(c)] for c in bc]
        signature = (a.id, tuple(ac), b.id, tuple(bc), mode)
        for r in self.relations:
            if r['_signature'] == signature:
                if test: r['_test'] = True
                return r
        ak, bk = a.keys(ac,mode), b.keys(bc,mode)
        ca, cb = Counter(k for k in ak if k is not None), Counter(k for k in bk if k is not None)
        common = ca.keys() & cb.keys()
        amatch = sum(ca[k] for k in common); bmatch = sum(cb[k] for k in common)
        leftrows = sum(max(cb.get(k,0),1) if k is not None else 1 for k in ak)
        cats = Counter(('many' if ca[k]>1 else 'one')+'-to-'+('many' if cb[k]>1 else 'one') for k in common)
        if not common: observed = 'No matches'
        else: observed = ('many' if any(ca[k]>1 for k in common) else 'one')+'-to-'+('many' if any(cb[k]>1 for k in common) else 'one')
        target_unique = bool(cb and max(cb.values()) == 1)
        risk = 'No matched keys; relationship not supported' if not common else (
            'No fanout in current left join; globally unique eligible target keys' if target_unique else
            'Duplicate expansion observed' if leftrows>a.n else 'Target key not unique; future expansion risk')
        r = {'relationship_id':f'REL-{len(self.relations)+1:03d}', 'source_table':a.id,'target_table':b.id,
            'source_column':raw_json(ac),'target_column':raw_json(bc),'key_mode':mode,
            'source_rows':a.n,'target_rows':b.n,'source_nonblank_key_rows':sum(ca.values()),
            'target_nonblank_key_rows':sum(cb.values()),'source_null_key_rows':a.n-sum(ca.values()),
            'target_null_key_rows':b.n-sum(cb.values()),'source_distinct_keys':len(ca),'target_distinct_keys':len(cb),
            'matching_distinct_keys':len(common),'matching_source_records':amatch,'unmatched_source_records':a.n-amatch,
            'unmatched_nonblank_source_records':sum(ca.values())-amatch,
            'matching_target_records':bmatch,'unmatched_target_records':b.n-bmatch,
            'source_nonblank_record_coverage_percent':pct(amatch,sum(ca.values())),
            'source_distinct_coverage_percent':pct(len(common),len(ca)),
            'target_distinct_coverage_percent':pct(len(common),len(cb)),
            'expected_cardinality':expected,'observed_cardinality':observed,'matched_key_cardinality_counts':raw_json(cats),
            'target_key_globally_unique_nonblank':target_unique,'predicted_left_join_rows':leftrows,
            'predicted_inner_join_rows':sum(ca[k]*cb[k] for k in common),
            'predicted_excess_left_rows':leftrows-a.n,'duplicate_expansion_risk':risk,
            'confidence': 'High observed value evidence; business interpretation unconfirmed' if common and pct(amatch,sum(ca.values())) == 100 else
                'Partial observed value evidence; business interpretation unconfirmed' if common else 'Unsupported on tested raw keys',
            'evidence':rationale,'unresolved_questions':scope,
            'join_decision':'Structural lookup candidate only; require source authority/coverage approval' if common and target_unique else 'Do not use as direct enrichment without grain/key resolution',
            'business_relationship_confirmed':False,'controlled_join_tested':False,
            '_signature':signature,'_a':a,'_b':b,'_ac':ac,'_bc':bc,'_test':test}
        self.relations.append(r)
        return r

    def discover_relationships(self):
        # Reassess all legacy comparisons, including weak ones; do not discard negative evidence.
        for old in self.prior_matches.itertuples(index=False):
            a,b = self.table(old.file_a,old.worksheet_a),self.table(old.file_b,old.worksheet_b)
            r = self.add_relation(a,[old.column_a],b,[old.column_b],
                f'Prior {old.candidate_family}: complete typed raw-value overlap, evaluated in its source grains. Classification/contact/customer-reference fields are not assumed unique.')
            self.check(f'Prior overlap reconciled {r["relationship_id"]}',
                r['matching_distinct_keys'] == int(old.distinct_overlap) and
                r['matching_source_records'] == int(old.a_rows_matching_b) and r['matching_target_records'] == int(old.b_rows_matching_a))
        customers = [t for t in self.tables.values() if t.file.startswith('Customer Master')]
        items = [t for t in self.tables.values() if t.file.startswith('Item Master')]
        orders = [t for t in self.tables.values() if t.file.startswith('Sales Order Report')]
        invoices = [t for t in self.tables.values() if t.file.startswith('Sales Invoice Details')]
        inventory = [t for t in self.tables.values() if t.file.startswith('Inventory Audit')]
        refcustomer = self.table('Sales_Order_Data_202609.xlsx','Customer list')
        country = self.table('Sales_Order_Data_202609.xlsx','Country master')
        products = [self.table('Sales_Order_Data_202609.xlsx',s) for s in ('PTC_NOPI','PCT_NOPJ')]
        gst = self.table('GSTR1_Invoice.csv')
        credits = [t for t in self.tables.values() if t.file.startswith('GSTR1_Credit')]
        for order in orders:
            for customer in customers:
                for mode in ('raw','trim_casefold_diagnostic'):
                    self.add_relation(order,['Customer Code'],customer,['CUSTOMER CODE'],
                        'Order customer reference versus customer-master code; test owner/description consistency separately.',
                        'many-to-one lookup desired; not yet approved',mode,True)
            for item in items:
                self.add_relation(order,['Item No'],item,['Item No.'],'Order product reference versus item-master code.',
                    'many-to-one lookup desired',test=True)
        for invoice in invoices:
            for item in items:
                self.add_relation(invoice,['Part Code SAP Code'],item,['Item No.'],
                    'SAP part/item reference; excludes missing product codes rather than matching nulls.',
                    'many-to-one lookup desired',test=True)
            for customer in customers:
                self.add_relation(invoice,['Customer Billing GSTIN'],customer,['GSTIN'],
                    'Billing tax registration versus master tax registration; not necessarily one GSTIN per customer.',
                    'many-to-one only if registration uniquely identifies intended billing entity',test=True)
            for order in orders:
                for ac,bc in [(['SO Num'],['SO No']), (['SO Num','Part Code SAP Code'],['SO No','Item No'])]:
                    self.add_relation(invoice,ac,order,bc,
                        'Invoice order reference and optional product component; many order/invoice lines can share references.',
                        'Document-level 1:M may exist; direct detail-to-detail join can be M:M',test=True,
                        scope='Confirm SO company/year scope, line IDs, partial fulfilment and cancellations; matching product does not establish line identity.')
            self.add_relation(gst,['@scoped_invoice'],invoice,['Invoice Num'],
                'Explicit GST series/prefix reconstruction versus full Excel invoice reference.',
                'Same-document line sets, not unique document rows',test=True)
            self.add_relation(gst,['@scoped_invoice','Item_Description'],invoice,['Invoice Num','Item Description'],
                'Scoped document plus raw description is a diagnostic alignment, not a stable invoice-line key.',
                'Potential line correspondence; repeated description can still fan out',test=True)
            self.add_relation(gst,['@scoped_invoice'],invoice,['Invoice Num'],
                'Explicit trim/case sensitivity test; no source normalization.',mode='trim_casefold_diagnostic',test=True)
            for credit in credits:
                for mode in ('raw','trim_casefold_diagnostic'):
                    self.add_relation(credit,['Invoice_Number'],invoice,['Invoice Num'],
                        'Credit/debit original-invoice reference versus full sales invoice identifier.',
                        'Credit lines to original invoice document; detail join can expand',mode,True,
                        'Confirm whether reference is original document and how adjustments allocate across invoice lines.')
        for inv in inventory:
            for item in items:
                self.add_relation(inv,['Item No.'],item,['Item No.'],
                    'Raw inventory product labels only; movement rows without item cannot inherit group context in this assessment.',
                    'Lookup applies only to populated group-label rows',test=True)
        for t, col in [(i,'foreign Code') for i in items]+[(i,'Item Foreign Code') for i in invoices]:
            for product in products:
                self.add_relation(t,[col],product,['Product code'],
                    'Foreign/manufacturer product reference versus product classification code; compare namespace and description before business approval.',
                    'many-to-one classification lookup desired',test=True)
        for customer in customers:
            self.add_relation(refcustomer,['BP_CODE'],customer,['CUSTOMER CODE'],
                'BP_CODE shares observed customer-master namespace; numeric Customer Code is a different field.',
                'Reference crosswalk to customer entity candidate',test=True)
            self.add_relation(customer,['Bill-to Country'],country,['Country Name'],
                'Country name semantics, with unapproved aliases such as India versus Republic of India.',
                'many-to-one geographic lookup desired',test=True)
            for tax in [gst]+credits:
                self.add_relation(tax,['Customer_Bill_To_GSTIN'],customer,['GSTIN'],
                    'Tax-registration domain overlap; multiple customer accounts can share a registration.',
                    'Unconfirmed billing registration/account relationship',test=True)
        for credit in credits:
            self.add_relation(credit,['Invoice_Number'],gst,['@scoped_invoice'],
                'Original invoice reference versus GST invoice reconstruction; original document can have multiple lines.',
                'Adjustment to invoice document, not invoice line',test=True)
        ratea,rateb = self.table('Exchange Rate 1.xlsx'),self.table('Exchange Rate.xlsx')
        self.add_relation(ratea,['@explicit_month_period','From Currency','To Currency'],
            rateb,['@explicit_month_period','From Currency','To Currency'],
            'Explicit monthly-period/currency-pair overlap in two marked synthetic rate tables; no transaction date interpretation.',
            'one-to-one for observed overlapping period/pair',test=True)
        self.results['prior_matching_coverage'] = self.prior_matches.copy()
        self.progress(f'Computed full key coverage for {len(self.relations)} directed relationship candidates')

    @staticmethod
    def measures(t):
        if t.file.startswith('Sales Order Report'):
            return ['Quantity','Total (LC)','Tax Total']
        if t.file.startswith('Sales Invoice Details'):
            return ['Quantity','Taxable Value','Total Value','IGST Amt','CGST Amt','SGST Amt','Invoice Total Include GST']
        if t.file == 'GSTR1_Invoice.csv':
            return ['Item_Quantity','Item_Taxable_Value','Line_Total_Include_GST','IGST_Amount','CGST_Amount','SGST_Amount','Invoice_Value']
        if t.file.startswith('GSTR1_Credit'):
            return ['Item_Quantity','Item_Taxable_Value','IGST_Amount','CGST_Amount','SGST_Amount','Credit_Debit_Note_Value']
        if t.file.startswith('Inventory Audit'):
            return ['Quantity','Trans. Value','Cumulative Qty','Cumulative Value']
        if t.file.startswith('Item Master'):
            return ['In Stock','Value','Amount']
        return []

    def financial_profile(self, relationship, t, weights, side):
        for col in self.measures(t):
            nums, unparsed = t.numeric(col)
            finite = np.isfinite(nums)
            # Excluding non-numeric cells from a diagnostic sum is explicit, never a business zero.
            baseline = nums[finite]
            affected = finite & (weights != 0)
            before = float(baseline.sum())
            after = float(np.dot(nums[affected], weights[affected]))
            matched_base = float(nums[affected].sum())
            abs_before = float(np.abs(baseline).sum())
            abs_after = float(np.dot(np.abs(nums[affected]), weights[affected]))
            special = label(col) in ('invoice total include gst','invoice value','credit debit note value','cumulative qty','cumulative value')
            if side == 'source' and np.all(weights == 1):
                self.check(f'No-fanout financial conservation {relationship}/{side}/{col}',
                    math.isclose(before,after,rel_tol=1e-12,abs_tol=.01))
            self.financial.append({'relationship_id':relationship,'side':side,'table':t.id,'column':col,
                'parsed_numeric_rows':int(finite.sum()),'unparsed_nonblank_rows':unparsed,
                'blank_or_non_numeric_rows':int((~finite).sum()),'raw_row_sum_before':before,
                'selected_row_sum_before_replication':matched_base,'joined_row_sum_after':after,
                'change_vs_all_original_rows':after-before,
                'replication_change_vs_selected_rows':after-matched_base,
                'absolute_row_sum_before':abs_before,'absolute_row_sum_after':abs_after,
                'joined_numeric_occurrences':int(weights[finite].sum()),
                'sum_is_business_total':False,
                'interpretation':'NON-ADDITIVE document/cumulative field: raw-row sum is only a mechanical fanout diagnostic' if special else
                    'Diagnostic raw-row sum only; currency/unit/sign/financial exceptions unresolved. Source rows retained; target side excludes unmatched target rows.'})

    def test_joins(self):
        for index,r in enumerate([v for v in self.relations if v['_test']],1):
            a,b = r['_a'],r['_b']
            ak,bk = a.keys(r['_ac'],r['key_mode']),b.keys(r['_bc'],r['key_mode'])
            # Tokenizing key tuples makes pandas equality exact and null semantics explicit.
            token = {k:i for i,k in enumerate(dict.fromkeys(k for k in ak+bk if k is not None))}
            acode = np.array([token[k] if k is not None else -1 for k in ak],dtype=np.int64)
            bcode = np.array([token[k] if k is not None else -2 for k in bk],dtype=np.int64)
            eligible = bcode >= 0
            right = pd.DataFrame({'key':bcode[eligible],'right_row':np.flatnonzero(eligible)})
            lweight = np.zeros(a.n,dtype=np.int64); rweight=np.zeros(b.n,dtype=np.int64)
            result_n=matched_n=0
            # Full data, bounded left chunks; never sampled joins. Bound expected fanout per chunk.
            cb = Counter(bcode[eligible].tolist())
            start=0
            while start < a.n:
                stop=start; budget=0
                while stop<a.n and stop-start<10000 and budget<250000:
                    budget+=max(cb.get(int(acode[stop]),0),1); stop+=1
                left=pd.DataFrame({'key':acode[start:stop],'left_row':np.arange(start,stop)})
                merged=left.merge(right,on='key',how='left',sort=False,
                    validate='many_to_one' if r['target_key_globally_unique_nonblank'] else 'many_to_many')
                lw=np.bincount(merged.left_row.to_numpy(dtype=int),minlength=a.n)
                lweight+=lw
                hit=merged.right_row.notna()
                rw=merged.loc[hit,'right_row'].to_numpy(dtype=int)
                rweight+=np.bincount(rw,minlength=b.n)
                result_n+=len(merged); matched_n+=int(hit.sum())
                start=stop
            expected=np.array([max(cb.get(int(k),0),1) for k in acode],dtype=np.int64)
            self.check(f'Actual full left join versus independent count formula {r["relationship_id"]}',
                result_n==r['predicted_left_join_rows'] and matched_n==r['predicted_inner_join_rows'] and np.array_equal(lweight,expected))
            self.check(f'Target replicated row accounting {r["relationship_id"]}',int(rweight.sum())==matched_n)
            self.check(f'No source rows discarded {r["relationship_id"]}',bool(np.all(lweight>=1)))
            r['controlled_join_tested']=True
            self.join_results.append({'relationship_id':r['relationship_id'],'source_table':a.id,'target_table':b.id,
                'key_mode':r['key_mode'],'original_source_rows':a.n,'original_target_rows':b.n,
                'actual_left_join_rows':result_n,'actual_inner_join_rows':matched_n,
                'unmatched_source_rows':r['unmatched_source_records'],
                'unmatched_target_rows':int((rweight==0).sum()),'source_distinct_keys_before':r['source_distinct_keys'],
                'source_distinct_keys_after_left_join':r['source_distinct_keys'],
                'target_distinct_keys_before':r['target_distinct_keys'],'target_distinct_keys_after_join':r['matching_distinct_keys'],
                'extra_source_row_occurrences':result_n-a.n,'source_rows_replicated':int((lweight>1).sum()),
                'left_expansion_factor':result_n/a.n if a.n else None,
                'max_left_row_copies':int(lweight.max()) if a.n else 0,
                'max_target_row_copies':int(rweight.max()) if b.n else 0,
                'method':'Complete typed-key pandas left merge, memory chunks; null targets excluded, null source retained unmatched',
                'permanent_joined_output_written':False,'calculation_validated':True})
            self.financial_profile(r['relationship_id'],a,lweight,'source')
            self.financial_profile(r['relationship_id'],b,rweight,'target')
            if index % 10 == 0: self.progress(f'Validated {index} controlled joins')
        self.results['controlled_join_validation']=pd.DataFrame(self.join_results)
        self.results['join_financial_effects']=pd.DataFrame(self.financial)
        self.results['relationship_candidates']=pd.DataFrame([{k:v for k,v in r.items() if not k.startswith('_')} for r in self.relations])
        ids=self.results['identifier_profiles']
        for ix,row in ids.iterrows():
            rels=[]
            for r in self.relations:
                for side in ('source','target'):
                    if r[f'{side}_table']==row.table and row.column_name in json.loads(r[f'{side}_column']):
                        rels.append(r['relationship_id']); break
            ids.at[ix,'matching_comparisons']=len(rels)
            if rels: ids.at[ix,'relationship_status']='See relationship candidates and identifier match detail; no business constraint confirmed'
        details=[]
        for r in self.relations:
            for side,opposite in [('source','target'),('target','source')]:
                for col in json.loads(r[f'{side}_column']):
                    details.append({'relationship_id':r['relationship_id'],'table':r[f'{side}_table'],'column':col,
                        'other_table':r[f'{opposite}_table'],'other_key':r[f'{opposite}_column'],'mode':r['key_mode'],
                        'matching_records':r[f'matching_{side}_records'],'unmatched_records':r[f'unmatched_{side}_records'],
                        'matching_distinct_keys':r['matching_distinct_keys'],
                        'note':'Composite coverage where multiple columns listed; not a claim of scalar-column equivalence'})
        self.results['identifier_match_detail']=pd.DataFrame(details)

    def compare_attributes(self,a,ac,b,bc,pairs,context,mode='raw'):
        ak,bk=a.keys(ac,mode),b.keys(bc,mode)
        ga,gb=defaultdict(list),defaultdict(list)
        for i,k in enumerate(ak):
            if k is not None:ga[k].append(i)
        for i,k in enumerate(bk):
            if k is not None:gb[k].append(i)
        common=ga.keys() & gb.keys()
        for acol,bcol in pairs:
            av,bv=a.values(acol),b.values(bcol)
            mismatch=normalized_equal=numeric_equal=missing=compared=0
            for k in common:
                aa={typed(av[i]) for i in ga[k] if not blank(av[i])}
                bb={typed(bv[i]) for i in gb[k] if not blank(bv[i])}
                if not aa or not bb:missing+=1;continue
                compared+=1
                if aa != bb:
                    mismatch+=1
                    an={normalized_key(av[i]) for i in ga[k] if not blank(av[i])}
                    bn={normalized_key(bv[i]) for i in gb[k] if not blank(bv[i])}
                    if an==bn:normalized_equal+=1
                    avn=[number(av[i])[0] for i in ga[k] if not blank(av[i])]
                    bvn=[number(bv[i])[0] for i in gb[k] if not blank(bv[i])]
                    if avn and bvn and all(math.isfinite(v) for v in avn+bvn):
                        x,y=sorted(set(avn)),sorted(set(bvn))
                        if len(x)==len(y) and all(math.isclose(u,v,abs_tol=.01,rel_tol=1e-9) for u,v in zip(x,y)):numeric_equal+=1
            self.conflicts.append({'source_table':a.id,'target_table':b.id,'source_key':raw_json(ac),'target_key':raw_json(bc),
                'key_mode':mode,'source_attribute':acol,'target_attribute':bcol,'matched_key_groups':len(common),
                'groups_compared_nonblank':compared,'groups_missing_attribute_one_side':missing,
                'raw_attribute_set_mismatches':mismatch,'mismatches_resolved_by_case_trim_only':normalized_equal,
                'mismatches_numerically_equivalent_diagnostic':numeric_equal,
                'interpretation':context+'; raw set comparison, not row identity or proof of business error; no preferred value selected'})

    def provenance_analysis(self):
        # Compare complete raw typed payloads only when normalized schemas agree.
        payloads=[]
        for t in self.tables.values():
            use=[i for i,n in enumerate(t.names) if label(n) != 's no' and str(n)!='#']
            schema=tuple(label(t.names[i]) for i in use)
            counts=Counter()
            for row in t.frame.itertuples(index=False,name=None):
                if any(not blank(row[i]) for i in use):
                    payload=raw_json([typed(row[i]) for i in use]).encode('utf-8')
                    counts[hashlib.sha256(payload).hexdigest()]+=1
            payloads.append((t,schema,counts))
        for i,(a,sa,ca) in enumerate(payloads):
            for b,sb,cb in payloads[i+1:]:
                if sa!=sb:continue
                common=ca.keys() & cb.keys()
                self.provenance.append({'source_table':a.id,'target_table':b.id,'evidence_type':'Complete raw typed payload comparison',
                    'distinct_payloads_source':len(ca),'distinct_payloads_target':len(cb),'matching_payloads':len(common),
                    'source_rows_with_payload_in_target':sum(ca[k] for k in common),
                    'target_rows_with_payload_in_source':sum(cb[k] for k in common),
                    'multiset_intersection_rows':sum(min(ca[k],cb[k]) for k in common),
                    'row_ordinals_excluded':True,
                    'conclusion':('Observed overlapping extract content; duplicate extract/snapshot/common origin is a hypothesis. No source precedence established.' if common else
                        'No exact raw typed payload overlap. This does not exclude related/generated/history extracts with changed values or encodings; no source authority established.')})
        cm1,cm2=[self.table(f'Customer Master Report {n}.xlsx') for n in (1,2)]
        im1,im2=[self.table(f'Item Master Lists {n}.xlsx') for n in (1,2)]
        self.compare_attributes(cm1,['CUSTOMER CODE'],cm2,['CUSTOMER CODE'],
            [('CUSTOMER NAME','CUSTOMER NAME'),('GSTIN','GSTIN'),('Bill-to Country','Bill-to Country'),('E-MAIL','E-MAIL')],
            'Customer extract overlap; apparent changes can be formatting, mutations, or real changes')
        self.compare_attributes(im1,['Item No.'],im2,['Item No.'],
            [('Item Description','Item Description'),('foreign Code','foreign Code'),('HSN Code','HSN Code'),('In Stock','In Stock')],
            'Product extract overlap; stock comparison lacks an approved as-of scope')
        for order in [t for t in self.tables.values() if t.file.startswith('Sales Order Report')]:
            for cm in (cm1,cm2):
                self.compare_attributes(order,['Customer Code'],cm,['CUSTOMER CODE'],[('Customer Name','CUSTOMER NAME')],
                    'Reference value overlap requires compatible customer identity; normalized names are only supporting evidence')
        invsmall=self.table('Sales Invoice Details.xlsx');gst=self.table('GSTR1_Invoice.csv')
        for inv in [t for t in self.tables.values() if t.file.startswith('Sales Invoice Details')]:
            self.compare_attributes(gst,['@scoped_invoice'],inv,['Invoice Num'],
                [('Customer_Billing_Name','Customer Billing Name'),('Customer_Bill_To_GSTIN','Customer Billing GSTIN'),
                 ('Invoice_Value','Invoice Total Include GST')], 'GST/Excel document overlap; repeated document total compared as value sets, not summed')
            self.compare_attributes(gst,['@scoped_invoice','Item_Description'],inv,['Invoice Num','Item Description'],
                [('Item_Quantity','Quantity'),('Item_Taxable_Value','Taxable Value'),('Line_Total_Include_GST','Total Value'),
                 ('IGST_Amount','IGST Amt'),('CGST_Amount','CGST Amt'),('SGST_Amount','SGST Amt')],
                'Scoped document/description alignment; missing stable line ID means value-set agreement does not prove line identity')
        ra,rb=self.table('Exchange Rate 1.xlsx'),self.table('Exchange Rate.xlsx')
        self.compare_attributes(ra,['@explicit_month_period','From Currency','To Currency'],rb,
            ['@explicit_month_period','From Currency','To Currency'],
            [('Exchange Rate (1 INR = ? JPY)','Exchange Rate (1 INR = ? JPY)'),('Start Date','Start Date'),('End Date','End Date')],
            'Synthetic period overlap; conflicting rates cannot be resolved by filename or size')
        # Explicit markers from validated header evidence, plus sample-domain patterns.
        markers=[]
        for r in self.headers.itertuples(index=False):
            top=json.loads(r.top_10_rows_json)
            synthetic=[str(v) for row in top[:max(int(r.header_excel_row)-1,0)] for v in row if isinstance(v,str) and 'SYNTHETIC DATA' in v.upper()]
            if synthetic:markers.append({'file':r.file,'worksheet':r.worksheet,'indicator':'Explicit title marker',
                'observed_count':len(synthetic),'evidence':raw_json(synthetic),
                'status':'Confirmed marker; business production authenticity not established'})
        for t in (cm1,cm2):
            count=sum(isinstance(v,str) and 'example.com' in v.casefold() for v in t.values('E-MAIL'))
            markers.append({'file':t.file,'worksheet':t.sheet,'indicator':'example.com email domain',
                'observed_count':count,'evidence':'Reserved example-domain pattern in contact values',
                'status':'Sample/synthetic indicator only; not proof all records are synthetic'})
        self.results['source_overlap']=pd.DataFrame(self.provenance)
        self.results['attribute_conflicts']=pd.DataFrame(self.conflicts)
        self.results['source_authenticity']=pd.DataFrame(markers)
        # Authority decisions are deliberately scoped and provisional.
        self.results['authority_assessment']=pd.DataFrame([
            {'domain':'Customers','candidate_source':'Customer Master Reports; Customer list only as candidate BP crosswalk',
             'evidence':'Customer attributes and business codes; complete and partial overlaps measured',
             'decision':'No authoritative source confirmed; versions conflict and reference list is explicitly synthetic'},
            {'domain':'Products','candidate_source':'Item Master Lists; PTC_NOPI/PCT_NOPJ classifications',
             'evidence':'SAP item and foreign product namespaces; classifications are separate reference lists',
             'decision':'No authoritative version/crosswalk confirmed; large master has repeated codes'},
            {'domain':'Orders','candidate_source':'Sales Order Report exports',
             'evidence':'SO references, customer/product, quantities and line values',
             'decision':'Potential order detail fact sources; scope, history, stable line ID and extract precedence required'},
            {'domain':'Sales/invoices','candidate_source':'Sales Invoice Details; GST invoice as reconciliation source',
             'evidence':'Invoice line measures and scoped GST document identifiers with observed overlap',
             'decision':'Keep sources separate; do not stack overlapping invoice/GST rows as additional sales'},
            {'domain':'GST/adjustments','candidate_source':'GSTR1 Invoice and Credit/Debit Note CSVs',
             'evidence':'Reporting fields, series, tax amounts and original invoice references',
             'decision':'Candidate tax/adjustment evidence only; filing version, acceptance status and sign basis unknown'},
            {'domain':'Inventory','candidate_source':'Three inventory audit exports',
             'evidence':'Grouped item labels, opening balances, document movements and cumulative measures',
             'decision':'Require approved grouped-layout reconstruction and snapshot scope before movement fact construction'},
            {'domain':'Currency/country/service','candidate_source':'Synthetic rate periods; country reference; G/S invoice lines',
             'evidence':'Two explicit synthetic rate titles; multilingual country list; goods/service flag',
             'decision':'No production FX authority or independent service master established; approve aliases and service definition'}])

    def carry_quality(self):
        register=read_csv(self.quality/'issue_register.csv')
        self.check('All prior quality issues carried forward',len(register)==424)
        rows=[
            ('Ambiguous dates',203455,'Date equality/order and temporal scope cannot be trusted without approved source-specific formats; no date join executed.'),
            ('Impossible dates',28,'Temporal joins and document chronology may fail; preserve tokens for owner correction.'),
            ('Possible Excel serial dates',14949,'Numeric values are unconfirmed date encodings; not used as dates or inferred periods.'),
            ('Excess exact duplicate rows',3,'Can multiply relationship counts and financial totals; retained in every full-data join.'),
            ('Payload-duplicate candidates',972,'Can expand keys; inventory repeated layout rows may be legitimate. No deduplication performed.'),
            ('Financial exceptions',None,'Unresolved unit, discount, freight and GST rules limit business reconciliation; mechanical fanout sums do not validate accounting.'),
            ('Synthetic indicators',None,'High identifier overlap in sample material does not establish production validity or source authority.'),
            ('Unnamed PCT_NOPJ field',33,'33 populated NOPJ values; likely agency/source context is a hypothesis. Original blank header retained.'),
            ('Unconfirmed business identifiers',135,'Empirical uniqueness and coverage are not approved company/year/entity scope or primary/foreign-key constraints.')]
        self.results['quality_carry_forward']=pd.DataFrame([{'issue':a,'prior_affected_count':b,
            'relationship_impact':c,'status':'Unresolved; preserved; no records corrected or deleted',
            'evidence':'../data_quality/issue_register.csv and data_quality_report.md'} for a,b,c in rows])
        self.results['prior_issue_register']=register
        expected=self.quality_validation['date_counts']
        self.check('Unresolved date totals match validated quality summary',
            expected=={'ambiguous':203455,'impossible':28,'unconfirmed_serial':14949})
        duplicates=read_csv(self.quality/'duplicate_analysis.csv')
        self.check('Exact and payload duplicate totals preserved',
            int(duplicates.loc[duplicates.comparison=='all_raw_fields','duplicate_excess_rows'].sum())==3 and
            int(duplicates.loc[duplicates.comparison=='all_fields_excluding_row_ordinal','duplicate_excess_rows'].sum())==972)
        self.results['prior_duplicate_analysis']=duplicates
        self.results['prior_financial_exceptions']=read_csv(self.quality/'financial_consistency.csv')

    def diagram(self):
        folder=self.out/'data_model_diagram';folder.mkdir(exist_ok=True)
        mermaid='''flowchart LR
    Customer["Customer candidates: master records"]
    Product["Product candidates: item masters"]
    Classification["Product classification: PTC / PCT"]
    Order["Order documents: conceptual grouping"]
    OrderLine["Order detail: no stable line ID"]
    Invoice["Invoice documents: scoped reference"]
    InvoiceLine["Invoice detail: no stable line ID"]
    GST["GST invoice detail: reconciliation source"]
    Adjustment["Credit / debit reporting detail"]
    Inventory["Inventory grouped audit: reconstruction pending"]
    FX["Synthetic FX periods: separate"]
    Country["Country reference: aliases pending"]
    Customer -. "customer code: tested lookup candidates" .-> OrderLine
    Product -. "SAP item: tested lookup candidates" .-> OrderLine
    Product -. "SAP item: tested lookup candidates" .-> InvoiceLine
    Classification -. "foreign product namespace: partial evidence" .-> Product
    Order -. "logical grouping only" .-> OrderLine
    Invoice -. "logical grouping only" .-> InvoiceLine
    OrderLine -. "SO / item: detail fanout risk" .-> InvoiceLine
    InvoiceLine -. "scoped invoice / description: tested" .-> GST
    Adjustment -. "original invoice: document reference" .-> Invoice
    Inventory -. "raw item labels only; group context missing" .-> Product
    Country -. "aliases require approval" .-> Customer
'''
        (folder/'logical_business_model.mmd').write_text(mermaid,encoding='utf-8')
        nodes={
            'customer':(.13,.83,'CUSTOMER\nMaster candidates'),
            'product':(.13,.54,'PRODUCT\nItem-master candidates'),
            'class':(.13,.24,'PRODUCT CLASSIFICATION\nPTC / PCT reference'),
            'order':(.45,.84,'ORDER DOCUMENT / DETAIL\nNo stable detail-line ID'),
            'invoice':(.77,.84,'INVOICE DOCUMENT / DETAIL\nScoped reference; repeated totals'),
            'gst':(.77,.54,'GST INVOICE DETAIL\nReconciliation source'),
            'credit':(.77,.24,'CREDIT / DEBIT DETAIL\nOriginal-invoice reference'),
            'inventory':(.45,.54,'GROUPED INVENTORY AUDIT\nContext reconstruction pending'),
            'reference':(.45,.24,'COUNTRY / SYNTHETIC FX\nSeparate reference evidence')}
        fig,ax=plt.subplots(figsize=(17,9));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
        for key,(x,y,title) in nodes.items():
            box=FancyBboxPatch((x-.115,y-.052),.23,.104,boxstyle='round,pad=0.01',
                facecolor='#edf3fa',edgecolor='#26466b',linewidth=1.3,zorder=3)
            ax.add_patch(box);ax.text(x,y,title,ha='center',va='center',fontsize=9,zorder=4)
        edges=[('customer','order','customer code'),('product','order','item code'),
               ('product','invoice','SAP item'),('class','product','foreign product code'),
               ('order','invoice','SO / item: fanout risk'),('invoice','gst','scoped document / description'),
               ('credit','gst','original invoice'),('inventory','product','raw group labels only')]
        for a,b,text in edges:
            x,y,_=nodes[a];u,v,_=nodes[b]
            dx,dy=u-x,v-y
            border=min(.13/abs(dx) if dx else math.inf,.067/abs(dy) if dy else math.inf)
            start=(x+border*dx,y+border*dy);end=(u-border*dx,v-border*dy)
            ax.annotate('',xy=end,xytext=start,arrowprops=dict(arrowstyle='->',linestyle='--',
                color='#556577',shrinkA=0,shrinkB=0,connectionstyle='arc3,rad=0.06'),zorder=1)
            label_y=(y+v)/2+(.10 if abs(dy)<.03 else .018)
            ax.text((x+u)/2,label_y,text,fontsize=8,ha='center',
                bbox=dict(facecolor='white',edgecolor='none',alpha=.9),zorder=2)
        ax.text(.5,.98,'Logical business structure — candidate relationships',ha='center',fontsize=17,weight='bold')
        ax.text(.5,.08,'Dashed links describe tested reference candidates or conceptual grouping, not approved foreign-key constraints.\n'
            'No physical model or joined dataset is created. Goods/service is a line classification; no independent service master supplied.',
            ha='center',va='center',fontsize=10)
        for extension in ('svg','png'):
            fig.savefig(folder/f'logical_business_model.{extension}',dpi=170,bbox_inches='tight')
        plt.close(fig)
        ET.parse(folder/'logical_business_model.svg')
        img=plt.imread(folder/'logical_business_model.png')
        self.check('Diagram SVG/PNG decode successfully',img.shape[0]>0)
        (folder/'README.md').write_text('# Logical business structure\n\n'
            '[PNG](logical_business_model.png) · [SVG](logical_business_model.svg) · [Mermaid source](logical_business_model.mmd)\n\n'
            'All links remain candidates. Consult the relationship matrix for full coverage, cardinality and financial fanout evidence. '
            'Document/header entities are conceptual; original exports contain detail lines and have not been split or consolidated. '
            'Country alias and rate applicability relationships are unapproved. Service is a source line classification, not an inferred standalone master.\n',encoding='utf-8')

    def integrity(self):
        rows=[]
        for path,digest in self.before.items():
            p=self.root/path
            after=sha(p) if p.exists() else ''
            rows.append({'path':path,'sha256_before':digest,'sha256_after':after,'unchanged':digest==after})
        frame=pd.DataFrame(rows)
        self.check('All sources and prior inventory/quality evidence byte-identical',bool(frame.unchanged.all()),len(frame))
        self.results['protected_file_integrity']=frame

    def exports(self):
        mapping={
            'dataset_granularity_report.xlsx':['dataset_granularity','document_context','inventory_row_shapes','service_indicators'],
            'identifier_relationship_matrix.xlsx':['identifier_profiles','identifier_formats','composite_keys','key_derivation_rules','key_scope_checks',
                'relationship_candidates','identifier_match_detail','controlled_join_validation','join_financial_effects',
                'source_overlap','attribute_conflicts','source_authenticity','authority_assessment','quality_carry_forward',
                'prior_issue_register','prior_matching_coverage','prior_duplicate_analysis','prior_financial_exceptions','protected_file_integrity']}
        for name,frame in self.results.items():
            frame.to_csv(self.out/f'{name}.csv',index=False,encoding='utf-8-sig',lineterminator='\n',float_format='%.15g')
            # Force textual transport to compare all exported cells, including literal NA-like source tokens.
            expected=read_csv(self.out/f'{name}.csv').astype(str)
            self.check(f'CSV dimensions {name}',len(expected)==len(frame) and list(expected.columns)==list(frame.columns))
        for filename,names in mapping.items():
            with pd.ExcelWriter(self.out/filename,engine='openpyxl') as writer:
                for name in names:
                    self.results[name].to_excel(writer,sheet_name=name[:31],index=False)
                for ws in writer.book.worksheets:
                    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
                    for row in ws.iter_rows():
                        for c in row:
                            # Business text such as =... and #N/A must not become formulas/errors.
                            if isinstance(c.value,str):c.data_type='s'
                    for col in ws.columns:
                        ws.column_dimensions[col[0].column_letter].width=min(58,max(15,len(str(col[0].value))+2))
            with pd.ExcelFile(self.out/filename) as book:
                self.check(f'Workbook sheet manifest {filename}',book.sheet_names==[n[:31] for n in names])
                for name in names:
                    loaded=book.parse(name[:31],keep_default_na=False)
                    expected=self.results[name].fillna('')
                    self.compare_exports(expected,loaded,name+' workbook')
                    csvframe=read_csv(self.out/f'{name}.csv')
                    self.compare_exports(expected,csvframe,name+' CSV')
                    self.export_checks.append({'workbook':filename,'sheet':name[:31],'rows':len(expected),
                        'columns':len(expected.columns),'complete_csv_and_excel_content_verified':True})
        self.results['export_validation']=pd.DataFrame(self.export_checks)
        self.results['export_validation'].to_csv(self.out/'export_validation.csv',index=False,encoding='utf-8-sig')

    def compare_exports(self,expected,actual,name):
        self.check(f'Export shape {name}',expected.shape==actual.shape and list(expected.columns)==list(actual.columns))
        for col in expected.columns:
            for a,b in zip(expected[col],actual[col]):
                if isinstance(a,(int,float,np.integer,np.floating)) and not isinstance(a,(bool,np.bool_)):
                    # CSV columns with empty cells may be loaded as text. Coercion is
                    # permitted only because the in-memory report cell is numeric;
                    # textual business identifiers still require exact equality.
                    try:
                        good=not isinstance(b,(bool,np.bool_)) and math.isclose(float(a),float(b),abs_tol=1e-7,rel_tol=1e-12)
                    except (ValueError,TypeError):good=False
                else:good=str(a)==str(b)
                if not good:raise AssertionError((name,col,repr(a),repr(b)))

    def report(self):
        rel=self.results['relationship_candidates'];joins=self.results['controlled_join_validation']
        ids=self.results['identifier_profiles'];comp=self.results['composite_keys']
        safe=rel[(rel.controlled_join_tested) & (rel.target_key_globally_unique_nonblank) & (rel.matching_distinct_keys>0) & (rel.key_mode=='raw')]
        risky=rel[(rel.controlled_join_tested) & (rel.predicted_excess_left_rows>0) & (rel.key_mode=='raw')]
        empirical=ids[(ids.empirically_unique_on_nonblank) & (ids.role.str.contains('entity/document reference',regex=False))]
        def find(source,target,columns):
            selected=rel[(rel.source_table.str.startswith(source+' :: ')) &
                (rel.target_table.str.startswith(target+' :: ')) & (rel.key_mode=='raw') &
                rel.source_column.apply(lambda v:json.loads(v)==columns)]
            if len(selected)!=1:raise AssertionError(('Report experiment is not unique',source,target,columns))
            return selected.iloc[0]
        invoice_order=find('Sales Invoice Details 1.xlsx','Sales Order Report 2.xlsx',['SO Num'])
        gst_document=find('GSTR1_Invoice.csv','Sales Invoice Details.xlsx',['@scoped_invoice'])
        gst_line=find('GSTR1_Invoice.csv','Sales Invoice Details.xlsx',['@scoped_invoice','Item_Description'])
        smallcustomer=find('Sales Order Report 1.xlsx','Customer Master Report 1.xlsx',['Customer Code'])
        largecustomer=find('Sales Order Report 2.xlsx','Customer Master Report 2.xlsx',[' Customer Code '])
        smallproduct=find('Sales Order Report 1.xlsx','Item Master Lists 1.xlsx',['Item No'])
        line_attributes=self.results['attribute_conflicts']
        line_attributes=line_attributes[(line_attributes.target_table=='Sales Invoice Details.xlsx :: Sheet1') &
            (line_attributes.source_key==raw_json(['@scoped_invoice','Item_Description']))]
        self.check('Scoped GST/Excel line numerical correspondence',len(line_attributes)==6 and
            bool((line_attributes.groups_compared_nonblank==337).all()) and
            bool((line_attributes.raw_attribute_set_mismatches==line_attributes.mismatches_numerically_equivalent_diagnostic).all()))
        controls=self.results['join_financial_effects']
        quantity=controls[(controls.relationship_id==invoice_order.relationship_id) &
            (controls.side=='source') & (controls.column=='Quantity')].iloc[0]
        notable=f'''## Main evidence and practical implications

- **Order customer lookup:** the small order export matches {smallcustomer.matching_source_records:,} of {smallcustomer.source_rows:,} rows to 40 distinct codes in the small customer master without fanout. The large order export matches {largecustomer.matching_source_records:,} nonblank-key rows against the large master, leaves {largecustomer.unmatched_source_records:,} total rows unmatched and expands to {largecustomer.predicted_left_join_rows:,} rows because the target codes repeat. Neither master is automatically authoritative for both extracts.
- **Order product lookup:** the small order export matches {smallproduct.matching_source_records:,} rows / {smallproduct.matching_distinct_keys:,} distinct products to the small item master; {smallproduct.unmatched_source_records:,} rows are unmatched, including missing product codes. Missing product values need service/charge-line confirmation.
- **GST/invoice representation overlap:** raw GST invoice numbers yield only 178 distinct values; explicit prefix/series reconstruction yields {gst_document.source_distinct_keys:,} scoped documents. All {gst_document.matching_source_records:,} GST rows match the small invoice export. A document-only detail join produces {gst_document.predicted_left_join_rows:,} rows from 337; adding raw item description produces {gst_line.predicted_left_join_rows:,} rows with {gst_line.matching_distinct_keys:,} unique matching composite values. For each of {len(line_attributes)} quantity/base/line-total/GST fields, every compared line-key group is numerically equivalent under the stated diagnostic tolerance, although CSV text versus Excel number types differ. This is strong evidence of corresponding representations in these specific extracts; it is not a stable upstream line-key guarantee or permission to count them twice.
- **Invoice/order fanout:** SO-number linking the large invoice export to the large order export yields {invoice_order.predicted_left_join_rows:,} rows from {invoice_order.source_rows:,}; raw-row quantity changes from {quantity.raw_row_sum_before:,.2f} to {quantity.joined_row_sum_after:,.2f}. This is join-induced repetition, not new business activity. Invoice-to-order line allocation remains unresolved.
- **Adjustment scope:** the six-row credit/debit file has 3 raw note numbers but 6 scoped note references. The larger file has 243 scoped notes among 276 nonempty rows, with 33 excess repeated scoped keys; 3 additional rows are entirely blank. The two files therefore cannot be assigned identical document/line grain solely from their similar columns. Three excess note-plus-description signatures also remain duplicate candidates.
- **Rate overlap:** two explicit period/currency pairs overlap across the marked synthetic rate files. Their rate values agree on those pairs; one start-date and one end-date comparison differ in raw representation. This is not proof of a different calendar date, and neither synthetic rate source is approved for conversion.
- **Inventory context:** raw item joins reach group labels, while most movement rows have no populated item code. Applying these labels to following rows requires an approved layout rule; the current tests do not reconstruct them.

'''
        text=f'''# Dataset relationship and business structure assessment

Analysis date: 2026-11-02. Scope: 17 files, 14 Excel workbooks / 17 worksheets and 3 GST CSV tables; all 20 tables assessed using the validated inventory headers and complete source columns.

## Executive assessment

The data supports **business target discovery with the NOP team**, but is **not ready for unconditional consolidated preparation or ML**. Technical value overlap is established where reported; no business primary key, foreign-key constraint, source authority or line-level allocation rule has been confirmed. Full raw values were retained, including blank rows and all known duplicate candidates. No permanent join output, cleaning, date correction or model was produced.

{len(ids)} identifier candidates were profiled across complete columns and reconciled with prior quality counts. {len(rel)} directed relationship/key experiments were measured, including all 101 earlier comparisons. {len(joins)} complete controlled left joins were executed in bounded memory chunks and independently checked against key-frequency calculations. {len(safe)} raw-key directions have observed matches and globally unique nonblank target keys; these are **structurally row-preserving lookup candidates**, conditional on approved authority, semantic identity and unmatched-key handling. {len(risky)} raw-key directions demonstrably expand source rows.

{notable}

## Dataset meanings and record grain

Rows below the validated header include completely empty rows. Candidate grain is not inferred from schema similarity alone. Document context variation, key multiplicity, inventory row shape and goods/service indicators are included in the granularity workbook.

{tabulate(self.results['dataset_granularity'],['table','row_count','nonempty_rows','column_count','candidate_record_grain','evidence','business_confirmation'])}

## Identifier validation

All 135 candidates include nulls, distinct counts, excess duplicates (`nonblank rows - distinct values`), uniqueness among nonblank rows, source types, format patterns, whitespace and case/trim collision diagnostics. Nulls include structural blank rows; ordinal and descriptive/contact candidates remain explicitly distinguished from business identifiers. Full matching coverage is in `identifier_match_detail` and `relationship_candidates` sheets, not estimated from samples. Keys with null components do not match each other.

Observed entity/reference candidates unique among their populated values (completeness and business scope still required):

{tabulate(empirical,['table','column_name','null_rows','distinct_values','nonblank_uniqueness_percent','complete_and_unique'])}

Composite keys were tested across the full tables. Document+product or document+description uniqueness is diagnostic only: it cannot establish stable line identity, especially for partial fulfilment, repeated products, service lines, amendments or reused series. See `composite_keys` for all counts. GST invoice scoped keys are reconstructed **only in diagnostic copies** using prefix + series + number + suffix. Credit/debit scoped references use prefix + suffix + note number; raw note numbers can repeat across CN/DN/year series. No ambiguous transaction date participates in a key.

## Supported reference evidence and controlled joins

The complete matrix contains source and target columns, null/eligible counts, distinct and row coverage in both directions, unmatched records, expected versus observed cardinality, predicted fanout, technical confidence and unresolved questions. Relationships are retained even when no matches are found. Old same-family comparisons are exploratory overlaps, not automatically business edges; customer reference numbers, invoice raw numbers and foreign-code namespaces require semantic scope.

### Row-preserving lookup candidates on current raw keys

These preserve all left rows, including unmatched/null keys. They do not certify customer/product identity, correct source values, tax-registration uniqueness in business terms or completeness of coverage. Only eligible target keys are required unique; blank target keys are excluded.

{tabulate(safe,['relationship_id','source_table','source_column','target_table','target_column','matching_source_records','unmatched_source_records','source_distinct_coverage_percent'])}

### Joins with observed duplicate expansion

{tabulate(risky,['relationship_id','source_table','source_column','target_table','target_column','observed_cardinality','source_rows','predicted_left_join_rows','predicted_excess_left_rows'])}

Order and invoice exports contain detail rows, so SO-number equality alone is not a line relationship. Adding product reduces ambiguity but does not establish fulfilment allocation. GST and Excel invoice lines may be alternate representations of the same document; document equality can expand line counts. Credit/debit references point to a document, not an established invoice line. Retain separate order, invoice and tax/adjustment facts until stable keys or approved allocation/reconciliation rules exist.

### Financial and quantity controls

Every executed join records original/source/target row counts, actual left/inner row counts, unmatched records, distinct key counts before/after and per-row copy multiplicities. `join_financial_effects` contains source/target raw-row sums before/after, sums of absolute values to expose offsetting signed amounts, numeric parse failures and selected target totals before replication. All input rows are used; no sampled joins. Target-side totals after a left join exclude unmatched target rows, then repeat matched rows according to source-key multiplicity.

Document totals (`Invoice Total Include GST`, `Invoice_Value`, credit/debit document value), inventory cumulative values and opening balances are **not additive line measures**. Their mechanical row sums illustrate fanout only and are never presented as business revenue, inventory balance or tax liability. Quantity/line amounts also require currency/unit/sign confirmation. Prior financial exceptions remain unresolved; numerical equivalence tolerances in attribute-set comparisons are 0.01 absolute / 1e-9 relative and do not validate accounting. Diagnostics may interpret numeric text via the existing documented quality parser; unparsable values remain excluded and counted, never replaced with business zeros.

## Source overlap, conflicts and authority

`source_overlap` compares full raw typed payloads after excluding export ordinals for identical normalized header schemas. Counts include distinct common payloads, rows on each side and multiset intersection. This proves observed overlap only; historical snapshots, duplicate extracts, generated variants and common origin remain hypotheses. `attribute_conflicts` compares complete sets of nonblank raw attributes within matching keys, reports formatting-only/numeric-equivalent discrepancies separately, and never chooses a winning value. Set agreement does not prove individual line correspondence.

{tabulate(self.results['source_overlap'])}

{tabulate(self.results['authority_assessment'])}

Explicit SYNTHETIC DATA markers are retained for the two exchange-rate sheets and reference Customer list. Example-domain contact values are additional sample indicators, not proof every source is synthetic. No largest/newest-file authority rule is applied. Inventory filename dates and reference update dates do not prove transactional snapshot scope. Overlapping monthly exchange rates are compared by explicit period/currency; neither marked synthetic rate table is approved for production conversion. Transaction-date FX joins were intentionally not attempted while formats and applicability remain unresolved.

## Existing quality findings preserved

{tabulate(self.results['quality_carry_forward'],['issue','prior_affected_count','relationship_impact','status'])}

All 424 prior issue-register entries are carried forward with original source/column/rule counts and severity in the matrix and `prior_issue_register.csv`; issue counts can overlap. No resolution status is upgraded by this analysis. The PCT_NOPJ blank first header remains blank; its 33 `NOPJ` values suggest agency/source context but this interpretation requires manual confirmation. Inventory sparse item labels were not filled down.

## Proposed logical business model

[Logical business model PNG](data_model_diagram/logical_business_model.png) · [SVG](data_model_diagram/logical_business_model.svg) · [Mermaid source](data_model_diagram/logical_business_model.mmd).

Customer and item-master records are potential dimension inputs after source authority, uniqueness and history are approved. Product classifications form separate manufacturer/agency reference candidates. Orders and invoices are separate document/detail concepts; transaction detail facts are possible only after stable line identity and grain are established. GST invoice detail is a reconciliation/reporting representation, and credit/debit detail is an adjustment fact candidate with explicit original-document references and unconfirmed sign conventions. Inventory remains a grouped report requiring approved context reconstruction before movement facts can be defined. Country reference needs an approved alias mapping. Marked synthetic FX periods remain separate. Goods/service flags support a line classification; no independent service entity/master has been demonstrated. A single star schema is not justified at present.

## Decisions and NOP-team questions

1. Which files are production exports, test/synthetic examples or generated variants? What system, company, extraction filters, reporting period and snapshot/version apply to each? Who owns each source of truth?
2. Are customer and product codes globally scoped, or company/branch/version specific? What do alternate numeric Customer Code, BP_CODE, foreign codes and PTC/PCT namespaces mean? Can multiple accounts share GSTIN?
3. What stable order-line and invoice-line IDs exist upstream? Do SO/invoice references include company/year/series scope, and can invoices span orders? How are partial deliveries, repeated products and adjustments allocated?
4. Are GST invoice and Excel invoice rows alternate exports of the same sale? Confirm series reconstruction, filing/revision status, document totals versus line totals, CN/DN signs and original-invoice relationships.
5. Which source-specific date formats and Excel serial epochs are correct? Confirm the monthly 2027-03 period and treatment of impossible tokens; no ambiguous values have been automatically converted.
6. How should inventory group labels, opening balances and cumulative fields be interpreted? Confirm report date labels and whether movement identifiers are unique within warehouse/item scope.
7. Confirm service/charge lines, blank item codes, the unnamed PCT_NOPJ field, country aliases, currency/units, discounts/freight/tax rules and the existing financial exceptions.

**Preparation readiness:** proceed to collaborative business-target analysis using separate source summaries and this evidence. Consolidation and training require explicit approval of source authority, keys/grain, date rules, duplicate treatment, financial reconciliation and join allocation. No next development activity has been started.

## Reproducibility, validation and limitations

- Executable workflow: `notebooks/03_dataset_relationship_analysis.ipynb`; reusable engine: `src/data/analyze_relationships.py`.
- Full outputs: [identifier and relationship matrix](identifier_relationship_matrix.xlsx), [granularity evidence](dataset_granularity_report.xlsx); complete aggregate CSVs accompany workbook sheets.
- All 20 table extents, headers and blank-row counts reconcile with inventory. All 135 identifier null/distinct/duplicate metrics and all 101 prior overlap calculations reconcile with quality evidence.
- Actual pandas join row multiplicities and target row accounting are independently checked against complete key counters. No source rows are discarded, and no null-to-null match is permitted.
- Workbook sheet manifests and every exported aggregate cell are read back and checked against memory and CSV outputs. PNG/SVG diagrams decode successfully. Source and prior-report SHA-256 comparisons are in `protected_file_integrity.csv`; final checks are in `analysis_validation.json` and notebook execution status in `notebook_execution_validation.json`.
- Limitations are business semantics, source authenticity/authority, time interpretation, missing stable line keys, inventory context and unresolved quality exceptions. Name similarity alone does not establish a relationship; matching values alone do not establish a business constraint. Analysis does not validate GST law or accounting treatment.
'''
        (self.out/'dataset_relationship_report.md').write_text(text,encoding='utf-8')

    def run(self):
        self.load();self.derive_keys();self.identifiers();self.grain()
        self.discover_relationships();self.test_joins();self.provenance_analysis();self.carry_quality()
        self.diagram();self.integrity();self.exports();self.report()
        # Final integrity check follows all report generation.
        self.integrity()
        validation={'analysis_date':'2026-11-02','source_files':len(set(t.file for t in self.tables.values())),
            'tables':len(self.tables),'identifier_candidates':len(self.results['identifier_profiles']),
            'relationship_candidates':len(self.relations),'prior_comparisons_reconciled':len(self.prior_matches),
            'controlled_joins':len(self.join_results),'financial_controls':len(self.financial),
            'all_protected_hashes_unchanged':bool(self.results['protected_file_integrity'].unchanged.all()),
            'protected_files':len(self.before),'business_primary_keys_confirmed':0,
            'business_relationships_confirmed':0,'read_failures':0,'join_calculation_failures':0,
            'permanent_consolidation_performed':False,'export_checks':self.export_checks,
            'checks':self.checks,'limitations':['Business definitions and source authority require NOP confirmation',
                'No ambiguous transaction dates resolved','Inventory group context not reconstructed',
                'No stable order/invoice line ID demonstrated']}
        (self.out/'analysis_validation.json').write_text(json.dumps(validation,indent=2,ensure_ascii=False),encoding='utf-8')
        self.progress(f'Completed: {len(self.relations)} relationships, {len(self.join_results)} controlled joins; protected sources/evidence unchanged')
        return self.results


def run(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    return RelationshipAnalysis(root).run()


if __name__=='__main__':
    run()
