"""Read-only data quality profiling with explicitly proposed business checks.

Only derived reports and a progress log are written. Run via notebook 02 or CLI.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from difflib import SequenceMatcher
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import unicodedata

from dateutil import parser as date_parser
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

AS_OF = date(2026, 10, 30)
EXCESSIVE_MISSING_PERCENT = 50.0
OUTLIER_IQR_MULTIPLIER = 3.0
MONEY_ABSOLUTE_TOLERANCE = 1.0
MONEY_RELATIVE_TOLERANCE = 0.005


def blank(v):
    return v is None or isinstance(v, str) and not v.strip()


def label(v):
    return re.sub(r'[\W_]+', ' ', str(v).casefold()).strip()


def kind(v):
    if isinstance(v, bool): return 'boolean'
    if isinstance(v, datetime): return 'datetime'
    if isinstance(v, date): return 'date'
    if isinstance(v, time): return 'time'
    if isinstance(v, (int, float)): return 'number'
    return 'text' if isinstance(v, str) else type(v).__name__


def typed(v):
    if v is None: return ('none', None)
    if isinstance(v, bool): return ('boolean', v)
    if isinstance(v, (int, float)): return ('number', v)
    if isinstance(v, (date, time)): return (kind(v), v.isoformat())
    return (kind(v), str(v))


def raw_json(v):
    return json.dumps(v, ensure_ascii=False, default=lambda x: x.isoformat() if isinstance(x, (date, time)) else str(x))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def pct(a, b):
    return round(100 * a / b, 4) if b else None


def canon(v):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(v))).strip().casefold()


def number(v):
    """Diagnostic interpretation only. No source values are replaced."""
    if blank(v): return (np.nan, 'blank')
    if isinstance(v, bool): return (np.nan, 'boolean; units unconfirmed')
    if isinstance(v, (int, float)):
        return (float(v), 'native number') if math.isfinite(v) else (np.nan, 'nonfinite number')
    if not isinstance(v, str): return (np.nan, 'non-numeric type')
    s = v.strip()
    rules = []
    if s != v: rules.append('outer whitespace')
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1].strip(); rules.append('parentheses as negative')
    currency = re.compile(r'^(?:INR|JPY|USD|EUR|Rs\.?|₹|¥|\$)\s*|\s*(?:INR|JPY|USD|EUR)$', re.I)
    changed = currency.sub('', s)
    if changed != s: rules.append('currency wrapper removed for diagnostic')
    s = changed.strip()
    if s.endswith('%'):
        s = s[:-1].strip(); rules.append('percent sign; value kept in percentage points')
    if ',' in s:
        if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?', s):
            return (np.nan, 'unrecognized comma grouping')
        s = s.replace(',', ''); rules.append('validated thousands grouping')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', s):
        return (np.nan, 'unrecognized numeric text')
    try:
        n = float(s)
        if not math.isfinite(n): return (np.nan, 'nonfinite number')
        return (n, '; '.join(rules) or 'numeric text')
    except (ValueError, OverflowError): return (np.nan, 'numeric parsing failure')


def applicability(name, file):
    n = label(name)
    if re.search(r'^original |advance ?receipt|shipping bill|freight detail|freight sac|fax|address [23]|building floor', n):
        return ('conditionally optional candidate', 'May apply only to amendments, advances, export/shipping or additional contact details; owner confirmation required')
    if re.search(r'gstin|sac code|hsn|cess|igst|cgst|sgst|state.*gst', n):
        return ('transaction/party-dependent candidate', 'Applicability depends on item/party/tax context; zero, blank and not applicable must remain distinct')
    if 'inventory audit' in file.lower() and n in ('item no', 'description'):
        return ('grouped-layout candidate', 'Sparse group labels may apply to following lines; no fill-down authorized')
    return ('requiredness unconfirmed', 'A required-field specification is not available; confirm business purpose before imputing or treating blanks as defects')


def is_measure(name):
    n = label(name)
    # Stock-impact flags and pricing-unit encodings are attributes, not amounts.
    if n in ('stock impact','pricing unit'): return False
    if re.search(r'\b(date|month|year|code|no|number|num|id|phone|fax)\b', n): return False
    return bool(re.search(r'quantity|\bqty\b|price|cost|value|amount|amt|total|rate|discount|stock|inventory|lead time|order to|order by|round off|\btaxes\b', n))


def is_category(name):
    n = label(name)
    return bool(re.search(r'\b(status|active|inactive|country|currency|category|segment|group|uom|unit|type|terms|liable|impact|charge|domestic|reason)\b', n)) and not is_measure(name)


class Assessment:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.out = self.root / 'reports/data_quality'
        self.out.mkdir(parents=True, exist_ok=True)
        self.log = self.root / 'logs/data_quality.log'
        self.log.write_text('data quality assessment started\n', encoding='utf-8')
        self.tables = defaultdict(list)
        self.issues = []
        self.id_counts = {}
        self.payloads = []
        inventory = self.root / 'reports/data_inventory/validation'
        # The validated workbook is the starting reference, not re-inferred headers.
        reference = pd.read_excel(inventory / 'inventory_validation_evidence.xlsx', sheet_name=None, keep_default_na=False)
        self.headers = reference['header_validation']
        self.expected = reference['table_counts']
        self.prior_ids = reference['identifier_validation']
        self.prior_dates = reference['date_validation']
        self.prior_matches = reference['identifier_matching_coverage']
        self.prior_sources = reference['source_completeness']
        self.inventory_before = {p.relative_to(self.root).as_posix(): sha(p) for p in (self.root / 'reports/data_inventory').rglob('*') if p.is_file()}
        module_ast = ast.parse((self.root / 'src/data/validate_inventory.py').read_text(encoding='utf-8'))
        functions = [node for node in module_ast.body if isinstance(node, ast.FunctionDef) and node.name in ('date_result', 'label')]
        env = {'datetime': datetime, 'date': date, 'time': time, 're': re, 'date_parser': date_parser}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<validated inventory date rules>', 'exec'), env)
        self.date_result = env['date_result']
        self.config = {'as_of': AS_OF.isoformat(), 'excessive_missing_percent': EXCESSIVE_MISSING_PERCENT,
            'outlier_iqr_multiplier': OUTLIER_IQR_MULTIPLIER, 'money_absolute_tolerance': MONEY_ABSOLUTE_TOLERANCE,
            'money_relative_tolerance': MONEY_RELATIVE_TOLERANCE,
            'normalization': 'Diagnostic copies only; raw values preserved. Case/spacing equivalence requires confirmation.'}

    def progress(self, text):
        with self.log.open('a', encoding='utf-8') as f: f.write(text + '\n')
        print(text, flush=True)

    def issue(self, file, sheet, column, severity, rule, count, impact, resolution,
              confirmation=True, examples=(), denominator=None, unit='rows/cells in this rule'):
        if not count: return
        self.issues.append({'issue_id': f'DQ-{len(self.issues)+1:04d}', 'severity': severity,
            'source_file': file, 'worksheet': sheet, 'affected_column': column, 'rule': rule,
            'affected_records': int(count), 'count_unit': unit, 'denominator': denominator,
            'source_row_examples': raw_json(list(examples)[:10]), 'potential_business_impact': impact,
            'recommended_resolution': resolution, 'business_confirmation_required': confirmation,
            'status': 'Open; no source changes applied'})

    def rows(self, mask, start):
        return (np.flatnonzero(np.asarray(mask))[:10] + start).tolist()

    def profile(self, file, sheet, frame, names, header, epoch):
        n = len(frame); start = header + 1
        values = [frame[c].tolist() for c in frame.columns]
        masks = [np.array([blank(v) for v in col], dtype=bool) for col in values]
        active = ~np.logical_and.reduce(masks) if masks else np.zeros(n, dtype=bool)
        active_n = int(active.sum())
        expected = self.expected[(self.expected.file == file) & (self.expected.worksheet == sheet)].iloc[0]
        assert n == int(expected.data_rows_below_header) and len(names) == int(expected.worksheet_columns_scanned), (file, sheet, 'extent mismatch')
        assert int((~active).sum()) == int(expected.empty_data_rows), (file, sheet, 'empty rows mismatch')
        self.tables['source_tables'].append({'file': file, 'worksheet': sheet, 'header_row': header,
            'rows_below_header': n, 'nonempty_rows': active_n, 'empty_rows': n-active_n,
            'columns': len(names), 'empty_data_columns': sum(m.all() for m in masks),
            'blank_cells': sum(int(m.sum()) for m in masks), 'data_cells': n*len(names),
            'blank_cell_percent': pct(sum(int(m.sum()) for m in masks), n*len(names)), 'status': 'assessed'})
        self.issue(file, sheet, '(whole row)', 'Low', 'Completely empty data rows', n-active_n,
            'Empty source rows can inflate row counts and identifier-null metrics.',
            'Preserve source coordinates and decide treatment in an approved cleaning phase.', False, self.rows(~active, start), n)
        self.duplicate_profile(file, sheet, frame, names, active, start)
        numeric = {}; exact_dates = {}
        old_ids = self.prior_ids[(self.prior_ids.file == file) & (self.prior_ids.worksheet == sheet)]
        id_by_pos = {int(r.column_number)-1: r for r in old_ids.itertuples()}
        date_positions = set(int(c)-1 for c in self.prior_dates[(self.prior_dates.file == file) & (self.prior_dates.worksheet == sheet)].column_number)
        for c, (name, col, missing) in enumerate(zip(names, values, masks)):
            scope, note = applicability(name, file)
            blanks = int(missing.sum()); effective_blanks = int((missing & active).sum())
            types = Counter(kind(v) for v in col if not blank(v))
            placeholders = Counter(str(v) for v in col if isinstance(v, str) and v.strip().casefold() in {'na','n/a','#n/a','null','none','nan','-'})
            missing_row = {'file': file, 'worksheet': sheet, 'column_number': c+1, 'column_name': name,
                'data_rows': n, 'blank_count': blanks, 'blank_percent_all_rows': pct(blanks,n),
                'nonempty_rows': active_n, 'blanks_on_nonempty_rows': effective_blanks,
                'blank_percent_nonempty_rows': pct(effective_blanks,active_n), 'completely_empty_data_column': blanks == n,
                'placeholder_tokens_not_replaced': raw_json(placeholders), 'placeholder_count': sum(placeholders.values()),
                'applicability_assessment': scope, 'requiredness_confirmed': False, 'business_confirmation': note,
                'raw_data_types': raw_json(types)}
            self.tables['missing_values'].append(missing_row)
            if active_n and effective_blanks / active_n * 100 >= EXCESSIVE_MISSING_PERCENT:
                severity = 'Low' if scope.startswith(('conditionally','transaction')) else 'High' if (c in id_by_pos or c in date_positions or is_measure(name)) else 'Moderate'
                self.issue(file,sheet,name,severity,'Excessive blank values (>=50% of nonempty rows)',effective_blanks,
                    'Field may be unsuitable for its intended use; optionality and layout can explain blanks.',
                    note + '; obtain requiredness/applicability rules before choosing a treatment.',True,self.rows(missing & active,start),active_n)
            if placeholders:
                self.issue(file,sheet,name,'Moderate','Placeholder/error-like values retained as raw tokens',sum(placeholders.values()),
                    'Blank, unknown, not applicable and Excel error-like values can be conflated by readers.',
                    'Confirm token meanings and preserve distinctions in a future approved parsing policy.',True,
                    self.rows([isinstance(v,str) and v.strip().casefold() in {'na','n/a','#n/a','null','none','nan','-'} for v in col],start),active_n)
            if c in id_by_pos:
                prior = id_by_pos[c]; counter = Counter(typed(v) for v in col if not blank(v))
                distinct=len(counter); nonblank=n-blanks; excess=nonblank-distinct
                assert distinct == int(prior.distinct_nonblank_values) and blanks == int(prior.null_or_blank_rows) and excess == int(prior.duplicate_excess_rows), (file,sheet,name,'identifier metrics changed')
                self.id_counts[(file,sheet,name)] = counter
                result=prior._asdict(); result.pop('Index',None)
                result.update({'nonblank_uniqueness_percent':pct(distinct,nonblank),
                    'unique_value_percent_of_all_rows':pct(distinct,n),'null_percent':pct(blanks,n),
                    'null_percent_nonempty_rows':pct(effective_blanks,active_n), 'primary_key_confirmed':False,
                    'granularity_note':'Entity/document reference is not necessarily a row key; repeated line references can be legitimate.'})
                self.tables['identifier_quality'].append(result)
                if prior.semantic_role.startswith('entity/document') and effective_blanks:
                    sev='Moderate' if scope.startswith(('conditionally','grouped')) else 'High'
                    self.issue(file,sheet,name,sev,'Blank candidate entity/document reference on nonempty rows',effective_blanks,
                        'Potential loss of identity or linkage; report grouping and conditional fields may explain blanks.',
                        'Confirm record grain, applicability and approved reference/master before any fill or join.',True,self.rows(missing & active,start),active_n)
            # Entity-name comparisons also apply when the initial sampled-ID
            # heuristic never flagged the name as an identifier.
            self.entity_profile(file,sheet,name,c,frame,names,active,start)
            if c in date_positions:
                exact_dates[c] = self.date_profile(file,sheet,name,c,col,active,start,epoch,types)
            if is_measure(name) and c not in date_positions:
                numeric[c] = self.numeric_profile(file,sheet,name,c,col,active,start,types)
            self.category_profile(file,sheet,name,col,active,start,types,c in date_positions,c in numeric)
        self.chronology(file,sheet,names,exact_dates,values,active,start)
        self.numeric_context(file,sheet,names,numeric,values,active)
        self.financial(file,sheet,names,numeric,active,start)
        if sheet == 'PCT_NOPJ':
            for c, name in enumerate(names):
                if name.startswith('<blank column'):
                    counter=Counter(str(v) for v in values[c] if not blank(v))
                    self.tables['dataset_specific'].append({'file':file,'worksheet':sheet,'column':name,
                        'finding':'Header is blank; data exists','affected_records':sum(counter.values()),
                        'raw_values_and_counts':raw_json(counter),'proposed_interpretation':'Agency/source marker is plausible from neighboring PTC_NOPI Sales agency column; unconfirmed',
                        'recommended_resolution':'Ask source owner for the field definition; retain positional label until approved.'})
                    self.issue(file,sheet,name,'Moderate','Unnamed field contains actual data',sum(counter.values()),
                        'A meaningful field can be omitted or mislabeled during preparation.',
                        'Confirm the intended field name from the owner; preserve the unnamed position meanwhile.',True,
                        self.rows(~masks[c],start),n)
        self.progress(f'Assessed {file} / {sheet}: {n:,} rows, {len(names)} columns')

    def duplicate_profile(self,file,sheet,frame,names,active,start):
        ordinals=[i for i,name in enumerate(names) if name.strip()=='#' or label(name) in ('s no','sno','serial no')]
        payload=[i for i in range(len(names)) if i not in ordinals]
        lookup={label(name):i for i,name in enumerate(names)}
        doc=[i for name,i in lookup.items() if name in ('so no','so num','invoice num','invoice number','creditdebitnote number')]
        proxy=list(dict.fromkeys(doc+[i for name,i in lookup.items() if re.search(r'customer code|customer ref|posting date|invoice date|creditdebitnote date|item no|part code|item description|quantity|unit price|taxable value',name)]))
        modes={'all_raw_fields':list(range(len(names))),'all_fields_excluding_row_ordinal':payload}
        if doc and len(proxy)>=3: modes['proposed_transaction_line_signature']=proxy
        groups={mode:defaultdict(list) for mode in modes}
        for row_index, row in enumerate(frame.itertuples(index=False,name=None)):
            if not active[row_index]: continue
            encoded=[typed(v) for v in row]
            for mode,positions in modes.items():
                serialized=raw_json([encoded[i] for i in positions])
                groups[mode][hashlib.sha256(serialized.encode('utf-8')).digest()].append(row_index)
        for mode,buckets in groups.items():
            repeated=[]
            for hashed,indices in buckets.items():
                if len(indices)<2: continue
                # Confirm typed equality for every duplicate hash group.
                exact=defaultdict(list)
                for idx in indices:
                    exact[raw_json([typed(frame.iat[idx,c]) for c in modes[mode]])].append(idx)
                for serialization, actual in exact.items():
                    if len(actual)>1:
                        repeated.append(actual)
                        self.tables['duplicate_groups'].append({'file':file,'worksheet':sheet,'comparison':mode,
                            'group_fingerprint':hashlib.sha256(serialization.encode('utf-8')).hexdigest(),
                            'group_rows':len(actual),'duplicate_excess':len(actual)-1,
                            'source_row_examples':raw_json([i+start for i in actual[:10]]),
                            'interpretation':'Exact compared values; repeated lines can still be legitimate. No deletion decision.'})
            excess=sum(len(g)-1 for g in repeated); involved=sum(len(g) for g in repeated)
            self.tables['duplicate_analysis'].append({'file':file,'worksheet':sheet,'comparison':mode,
                'compared_columns':raw_json([names[i] for i in modes[mode]]),'nonempty_rows':int(active.sum()),
                'duplicate_groups':len(repeated),'duplicate_excess_rows':excess,'rows_in_duplicate_groups':involved,
                'grain_confirmed':False})
            if excess:
                severity='High' if mode!='proposed_transaction_line_signature' else 'Moderate'
                self.issue(file,sheet,'(compared fields)',severity,'Duplicate signature: '+mode,involved,
                    'Possible double counting, or legitimate repeated lines/records at the source grain.',
                    'Confirm document series, fiscal period and line identity; inspect groups before any deletion.',True,
                    [i+start for group in repeated for i in group][:10],int(active.sum()),'rows participating in duplicate groups')
        schema=tuple(sorted(label(names[i]) for i in payload))
        if len(schema)==len(set(schema)):
            positions=sorted(payload,key=lambda i:label(names[i]))
            hashes=Counter()
            for idx,row in enumerate(frame.itertuples(index=False,name=None)):
                if active[idx]: hashes[hashlib.sha256(raw_json([typed(row[i]) for i in positions]).encode('utf-8')).hexdigest()]+=1
            self.payloads.append({'file':file,'worksheet':sheet,'schema':schema,'counts':hashes})

    def entity_profile(self,file,sheet,name,c,frame,names,active,start):
        master=('master' in file.lower() or sheet in ('Country master','PTC_NOPI','PCT_NOPJ','Customer list'))
        n=label(name)
        entity_code=master and n in ('customer code','bp code','item no','product code','code')
        entity_name=master and n in ('customer name','item description','product name','country name')
        if not (entity_code or entity_name): return
        groups=defaultdict(list)
        for idx,v in enumerate(frame[c]):
            if active[idx] and not blank(v): groups[typed(v) if entity_code else canon(v)].append(idx)
        duplicated=[indices for indices in groups.values() if len(indices)>1]
        conflicts=0
        payload=[i for i,nm in enumerate(names) if nm.strip()!='#' and label(nm) not in ('s no','sno')]
        for group in duplicated:
            variants={raw_json([typed(frame.iat[i,k]) for k in payload]) for i in group}
            conflicts+=len(variants)>1
            self.tables['entity_duplicate_groups'].append({'file':file,'worksheet':sheet,'column':name,
                'comparison':'exact code' if entity_code else 'diagnostic name case/whitespace comparison',
                'rows':len(group),'different_payloads':len(variants),'source_row_examples':raw_json([i+start for i in group[:10]])})
        self.tables['entity_duplicate_analysis'].append({'file':file,'worksheet':sheet,'column':name,
            'comparison':'exact code' if entity_code else 'diagnostic name case/whitespace comparison',
            'duplicate_groups':len(duplicated),'rows_in_groups':sum(map(len,duplicated)),
            'groups_with_differing_attributes':conflicts,'identity_confirmed':False})
        if duplicated:
            self.issue(file,sheet,name,'High' if entity_code else 'Moderate','Repeated master/reference entity candidate',sum(map(len,duplicated)),
                'A code can refer to multiple attribute records; similar names can also describe different entities.',
                'Confirm entity identity, version/effective-date rules and master ownership; do not collapse names automatically.',True,
                [i+start for group in duplicated for i in group][:10],int(active.sum()))

    def date_profile(self,file,sheet,name,c,col,active,start,epoch,types):
        tokens={}; accepted=[None]*len(col); dates=[]; periods=set(); statuses=Counter(); count_serial=0
        for idx,v in enumerate(col):
            if blank(v): continue
            k=typed(v)
            if k not in tokens:
                status,options,note=self.date_result(v,name)
                serial=''
                if epoch is not None and isinstance(v,(int,float)) and not isinstance(v,bool) and 20000<=v<=80000:
                    serial=from_excel(v,epoch).isoformat()
                    note='Possible Excel serial date using workbook epoch; no automatic conversion or accepted coverage inclusion.'
                tokens[k]={'raw_value':str(v.isoformat() if isinstance(v,(date,time)) else v),'raw_type':kind(v),
                    'status':status,'options':options,'interpretation_note':note,'candidate_serial_date':serial,'count':0,'rows':[]}
            t=tokens[k]; t['count']+=1
            if len(t['rows'])<10: t['rows'].append(idx+start)
            status=t['status']; statuses[status]+=1
            if t['candidate_serial_date']: count_serial+=1
            if len(t['options'])==1 and not status.startswith('month period'):
                accepted[idx]=t['options'][0];dates.append(t['options'][0].date())
            if status.startswith('month period'): periods.add(t['options'][0].strftime('%Y-%m'))
            if not t['options']:
                self.tables['date_cell_exceptions'].append({'file':file,'worksheet':sheet,'column_number':c+1,'column':name,
                    'source_row':idx+start,'original_value':t['raw_value'],'original_type':kind(v),
                    'status':status,'possible_excel_serial_date_unconfirmed':t['candidate_serial_date'],'proposed_interpretation':t['interpretation_note']})
        prior=self.prior_dates[(self.prior_dates.file==file)&(self.prior_dates.worksheet==sheet)&(self.prior_dates.column_number==c+1)].iloc[0]
        ambiguous=statuses['ambiguous day/month'];invalid=sum(n for st,n in statuses.items() if st.startswith('invalid'))
        unresolved=sum(t['count'] for t in tokens.values() if not t['options'])
        assert ambiguous==int(prior.ambiguous_day_month_values) and unresolved==int(prior.unresolved_or_invalid_values) and count_serial==int(prior.possible_excel_serial_values_unconfirmed),(file,sheet,name,'inventory date totals disagree')
        for t in tokens.values():
            self.tables['date_value_evidence'].append({'file':file,'worksheet':sheet,'column_number':c+1,'column':name,
                **{k:v for k,v in t.items() if k not in ('options','rows')},
                'possible_dates':raw_json([d.isoformat() for d in t['options']]),'source_row_examples':raw_json(t['rows'])})
        unique=sorted(set(dates)); observed_months=sorted(set(d.strftime('%Y-%m') for d in dates)|periods)
        missing_months=[]
        if observed_months:
            expected=pd.period_range(observed_months[0],observed_months[-1],freq='M').astype(str)
            missing_months=[m for m in expected if m not in observed_months]
        for a,b in zip(unique,unique[1:]):
            if (b-a).days>7:
                self.tables['date_coverage_gaps'].append({'file':file,'worksheet':sheet,'column':name,
                    'from_observed_date':a.isoformat(),'to_observed_date':b.isoformat(),'unobserved_calendar_days':(b-a).days-1,
                    'interpretation':'Partial unambiguous-value coverage only; not proof of missing transactions or expected business cadence.'})
        future=sum(d>AS_OF for d in dates)
        record={'file':file,'worksheet':sheet,'column_number':c+1,'column':name,'raw_types':raw_json(types),
            'representative_original_values':raw_json([{'type':t['raw_type'],'value':t['raw_value'],'count':t['count']} for t in list(tokens.values())[:8]]),
            'nonblank_values':sum(statuses.values()),'status_counts':raw_json(statuses),'ambiguous_values':ambiguous,
            'invalid_calendar_values':invalid,'possible_serial_values':count_serial,'unresolved_full_dates':unresolved,
            'month_period_values':sum(t['count'] for t in tokens.values() if t['status'].startswith('month period')),
            'unambiguous_min':unique[0].isoformat() if unique else '', 'unambiguous_max':unique[-1].isoformat() if unique else '',
            'unambiguous_distinct_dates':len(unique),'month_periods_observed':raw_json(sorted(periods)),
            'unobserved_months_within_partial_coverage':raw_json(missing_months),'future_unambiguous_values':future,
            'coverage_caveat':'Excludes ambiguous/serial/invalid values. Two-digit-year candidates retain the inventory century convention; business validity and cadence unconfirmed.'}
        self.tables['date_quality'].append(record)
        for rule,count in [('Ambiguous day/month dates',ambiguous),('Impossible calendar dates',invalid),('Unconfirmed numeric Excel serial dates',count_serial)]:
            if count:
                status_filter=lambda t: t['status']=='ambiguous day/month' if rule.startswith('Ambiguous') else t['status'].startswith('invalid') if rule.startswith('Impossible') else bool(t['candidate_serial_date'])
                self.issue(file,sheet,name,'High',rule,count,'Incorrect dates can shift periods, distort chronology and create misleading coverage.',
                    'Obtain source-format/epoch confirmation; retain raw values and candidate interpretations; correct invalid dates only against approved source evidence.',True,
                    [r for t in tokens.values() if status_filter(t) for r in t['rows']][:10],sum(statuses.values()),'date-field cells')
        if missing_months:
            self.issue(file,sheet,name,'Moderate','Unobserved months in partial calendar coverage',len(missing_months),
                'Incomplete or sparse observations can look like time gaps; excluded ambiguous dates may explain them.',
                'Confirm expected cadence and evaluate again after an approved date policy; do not fill a calendar yet.',True,(),len(observed_months)+len(missing_months),'calendar months, not source records')
        if future:
            self.issue(file,sheet,name,'Moderate','Future unambiguous dates relative to review date',future,
                'Planned delivery dates may be valid; future historical transactions or synthetic data can affect later evaluation.',
                'Confirm planning versus posting semantics and source provenance before selecting any modeling window.',True,
                [i+start for i,d in enumerate(accepted) if d and d.date()>AS_OF][:10],sum(statuses.values()))
        return accepted

    def numeric_profile(self,file,sheet,name,c,col,active,start,types):
        cache={}; parsed=np.full(len(col),np.nan); formats=Counter(); failures=Counter()
        for idx,v in enumerate(col):
            k=typed(v)
            if k not in cache: cache[k]=number(v)
            val,status=cache[k]; parsed[idx]=val
            if not blank(v):
                formats[status]+=1
                if not math.isfinite(val): failures[(str(v),status)]+=1
        valid=np.isfinite(parsed); arr=parsed[valid]
        row={'file':file,'worksheet':sheet,'column_number':c+1,'column':name,'raw_types':raw_json(types),
            'nonblank_values':sum(not blank(v) for v in col),'diagnostic_numeric_values':len(arr),
            'unparsed_nonblank_values':sum(failures.values()),'format_counts':raw_json(formats),
            'negative_values':int((arr<0).sum()),'zero_values':int((arr==0).sum()),
            'fractional_values':int((~np.isclose(arr,np.round(arr),rtol=0,atol=1e-9)).sum())}
        outlier=np.zeros(len(col),dtype=bool)
        if len(arr):
            q01,q25,q50,q75,q99=np.quantile(arr,[.01,.25,.5,.75,.99]);iqr=q75-q25
            low,high=q25-OUTLIER_IQR_MULTIPLIER*iqr,q75+OUTLIER_IQR_MULTIPLIER*iqr
            if iqr>0 and len(arr)>=8: outlier=valid&((parsed<low)|(parsed>high))
            row.update({'min':float(arr.min()),'max':float(arr.max()),'mean':float(arr.mean()),'std':float(arr.std()),
                'p01':q01,'q25':q25,'median':q50,'q75':q75,'p99':q99,'iqr_outer_low':low,'iqr_outer_high':high,
                'iqr_rule_applicable':bool(iqr>0 and len(arr)>=8)})
        row['iqr_outlier_values']=int(outlier.sum())
        row['interpretation']='Diagnostic numeric copies only. Negative/zero/fractional and IQR flags are review candidates, not automatic errors.'
        self.tables['numerical_quality'].append(row)
        for (value,status),count in failures.items():
            self.tables['numerical_token_issues'].append({'file':file,'worksheet':sheet,'column':name,'raw_value':value,'status':status,'occurrences':count})
        for rule,mask,severity,recommendation in [
            ('Unparsed nonblank measure values',np.array([not blank(v) for v in col])&~valid,'Moderate' if label(name)=='lead time' else 'High','Confirm units, locale, currency and placeholder rules; preserve the original value and explicitly approve parsing.'),
            ('Negative measure values',valid&(parsed<0),'Moderate','Check return, adjustment, credit/debit and accounting conventions; do not replace signs.'),
            ('Zero measure values',valid&(parsed==0),'Low','Distinguish genuine zeros, cancellations, free items and not-applicable encodings; do not replace with missing.'),
            ('IQR distribution outlier candidates',outlier,'Moderate','Investigate product/price/unit mix and source context; do not clip or delete statistical outliers.')]:
            self.issue(file,sheet,name,severity,rule,int(mask.sum()),'Aggregation or interpretation may be distorted if numerical conventions are misunderstood.',recommendation,True,self.rows(mask,start),len(arr) if rule!='Unparsed nonblank measure values' else row['nonblank_values'])
        if re.search(r'quantity|\bqty\b',label(name)):
            fractional=valid&~np.isclose(parsed,np.round(parsed),rtol=0,atol=1e-9)
            self.issue(file,sheet,name,'Moderate','Fractional quantity candidates',int(fractional.sum()),
                'Fractional values may be valid for some UOMs but inconsistent with indivisible units.',
                'Confirm the UOM and pack/pricing-unit rules per product before deciding validity.',True,self.rows(fractional,start),len(arr))
        if re.search(r'(?:gst|cess).*rate|discount',label(name)):
            mask=valid&((parsed<0)|(parsed>100))
            self.issue(file,sheet,name,'High','Outside proposed percentage-point range 0-100',int(mask.sum()),
                'Scale or encoding differences may make tax/discount arithmetic misleading.',
                'Confirm rate units and special adjustments before applying a permitted range.',True,self.rows(mask,start),len(arr))
        return parsed

    def category_profile(self,file,sheet,name,col,active,start,types,is_date,is_numeric):
        texts=[(idx,v) for idx,v in enumerate(col) if isinstance(v,str) and not blank(v)]
        category=is_category(name) and not is_date and not is_numeric
        if not texts and not category: return
        outer=[idx for idx,v in texts if v!=v.strip()]
        inner=[idx for idx,v in texts if re.sub(r'\s+',' ',v.strip())!=v.strip()]
        buckets=defaultdict(Counter)
        for idx,v in texts: buckets[canon(v)][v]+=1
        collisions={k:v for k,v in buckets.items() if len(v)>1}
        casegroups=sum(len({s.strip() for s in variants})>1 for variants in collisions.values())
        self.tables['categorical_consistency'].append({'file':file,'worksheet':sheet,'column':name,
            'category_candidate':category,'text_values':len(texts),'raw_types':raw_json(types),
            'outer_space_values':len(outer),'repeated_internal_space_values':len(inner),
            'diagnostic_representation_collision_groups':len(collisions),'case_variant_groups':casegroups,
            'domain_status':'Allowed business values unconfirmed; observed values alone do not define a valid domain'})
        for canonical,variants in collisions.items():
            self.tables['categorical_variants'].append({'file':file,'worksheet':sheet,'column':name,
                'diagnostic_normalized_value':canonical,'raw_variants_and_counts':raw_json(variants),
                'affected_values':sum(variants.values()),'interpretation':'Possible equivalent representations only; no source normalization applied'})
        if outer or inner:
            affected=set(outer)|set(inner)
            self.issue(file,sheet,name,'Moderate','Leading/trailing or repeated internal whitespace',len(affected),
                'Exact matching, grouping and category counts can split values.',
                'Confirm whitespace significance, then approve explicit normalization in a later phase.',True,[i+start for i in sorted(affected)[:10]],len(texts))
        if collisions and not is_date and not is_numeric:
            self.issue(file,sheet,name,'Moderate','Potential duplicate representations from case/spacing/Unicode',sum(sum(v.values()) for v in collisions.values()),
                'Apparently different categories or codes may represent the same concept.',
                'Confirm semantics and case sensitivity before creating a mapping; retain raw-to-proposed evidence.',True,(),len(texts))
        if category:
            observed=Counter((kind(v),str(v)) for v in col if not blank(v))
            for (data_type,value),count in observed.items():
                self.tables['categorical_values'].append({'file':file,'worksheet':sheet,'column':name,'raw_type':data_type,'raw_value':value,'count':count})
            # Fuzzy candidates are restricted to small textual category domains,
            # excluding entity names, descriptions and codes.
            keys=sorted(buckets)
            if len(keys)<=100 and not re.search(r'code|name|description|group|segment|reason|remark|detail|address',label(name)):
                for a,b in itertools.combinations(keys,2):
                    if min(len(a),len(b))>=4 and max(len(a),len(b))<=50 and not re.search(r'\d',a+b) and .84<=SequenceMatcher(None,a,b).ratio()<1:
                        count=sum(buckets[a].values())+sum(buckets[b].values())
                        self.tables['spelling_candidates'].append({'file':file,'worksheet':sheet,'column':name,
                            'value_a':a,'value_b':b,'similarity':SequenceMatcher(None,a,b).ratio(),'affected_values':count,
                            'interpretation':'Possible spelling difference, not a confirmed synonym or error'})
                        self.issue(file,sheet,name,'Moderate','Potential category spelling variation',count,
                            'Similar labels may split categories, or may have intentionally distinct meanings.',
                            'Review the candidate pair with the approved category catalogue; do not merge automatically.',True,(),len(texts))
            if label(name) in ('active','inactive'):
                allowed={'yes','no','y','n','true','false','1','0','1.0','0.0'}
                bad=[i for i,v in enumerate(col) if not blank(v) and str(v).strip().casefold() not in allowed]
                self.issue(file,sheet,name,'Moderate','Outside proposed binary-flag representations',len(bad),
                    'Flags may have extra states or malformed values.',
                    'Confirm permitted encodings and the meaning of extra states before choosing a mapping.',True,[i+start for i in bad[:10]],int(active.sum()))
            if label(name) in ('active','inactive','stock impact','tax only','tax liable','flag reverse charge'):
                families=defaultdict(Counter)
                for v in col:
                    if blank(v): continue
                    t=str(v).strip().casefold()
                    if isinstance(v,bool): family='native boolean'
                    elif isinstance(v,(int,float)) and v in (0,1): family='native numeric flag'
                    elif t in ('yes','no'): family='yes/no text'
                    elif t in ('y','n'): family='Y/N text'
                    elif t in ('true','false'): family='boolean text'
                    elif t in ('1','0','1.0','0.0'): family='numeric text flag'
                    else: family='other/unconfirmed'
                    families[family][str(v)]+=1
                for family,counts in families.items():
                    self.tables['flag_encoding_representations'].append({'file':file,'worksheet':sheet,'column':name,
                        'representation_family':family,'raw_values_and_counts':raw_json(counts),
                        'count':sum(counts.values()),'equivalence_approved':False})
                if len(families)>1:
                    self.issue(file,sheet,name,'Moderate','Mixed representations of a proposed binary flag',sum(sum(v.values()) for v in families.values()),
                        'Equivalent-looking states may be encoded as text, numbers and booleans, splitting categories.',
                        'Confirm state meanings and approve an explicit mapping; preserve raw encodings.',True,(),int(active.sum()))

    def chronology(self,file,sheet,names,dates,values,active,start):
        lookup={label(n):i for i,n in enumerate(names)}
        pairs=[('posting date','delivery date'),('so date','invoice date'),('start date','end date')]
        for a,b in pairs:
            if a not in lookup or b not in lookup: continue
            ca,cb=lookup[a],lookup[b]
            if ca not in dates or cb not in dates: continue
            eligible=[i for i in range(len(active)) if active[i] and dates[ca][i] is not None and dates[cb][i] is not None]
            reversed_rows=[i for i in eligible if dates[ca][i]>dates[cb][i]]
            self.tables['chronology_checks'].append({'file':file,'worksheet':sheet,'proposed_rule':f'{names[ca]} <= {names[cb]}',
                'active_rows':int(active.sum()),'eligible_unambiguous_pairs':len(eligible),'unevaluable_rows':int(active.sum())-len(eligible),
                'reversed_pairs':len(reversed_rows),'source_row_examples':raw_json([i+start for i in reversed_rows[:10]]),
                'business_rule_confirmed':False})
            self.issue(file,sheet,f'{names[ca]} / {names[cb]}','Moderate','Reversed proposed chronology',len(reversed_rows),
                'Scheduling or posting chronology may be inconsistent, or adjustments may explain it.',
                'Confirm event meanings and exception rules; do not compare ambiguous dates or reorder records.',True,[i+start for i in reversed_rows[:10]],len(eligible))

    def numeric_context(self,file,sheet,names,numeric,values,active):
        contexts=[]
        for c,name in enumerate(names):
            if label(name) in ('transtype','trans type','type credit or debit','status','type export domestic','uom','item uomcode','item uomname'):
                contexts.append((name,[str(v) if not blank(v) else '<blank>' for v in values[c]]))
            if 'inventory audit' in file.lower() and label(name)=='document':
                prefixes=[]
                for v in values[c]:
                    m=re.match(r'^\s*([A-Za-z]+)',str(v)) if not blank(v) else None
                    prefixes.append(m.group(1) if m else '<blank/no alphabetic prefix>')
                contexts.append(('Document alphabetic prefix (diagnostic)',prefixes))
        for context,labels in contexts:
            groups=defaultdict(list)
            for idx,value in enumerate(labels):
                if active[idx]: groups[value].append(idx)
            if len(groups)>50: continue
            for c,arr in numeric.items():
                for value,indices in groups.items():
                    observed=arr[indices];finite=observed[np.isfinite(observed)]
                    self.tables['numerical_context'].append({'file':file,'worksheet':sheet,'column':names[c],
                        'context_field':context,'observed_context_value':value,'source_rows':len(indices),
                        'interpretable_numeric_values':len(finite),'negative_values':int((finite<0).sum()),
                        'zero_values':int((finite==0).sum()),
                        'fractional_values':int((~np.isclose(finite,np.round(finite),rtol=0,atol=1e-9)).sum()),
                        'interpretation':'Contextual evidence only; credit/debit magnitudes, return signs, adjustments and UOM conventions remain unconfirmed.'})

    def financial(self,file,sheet,names,numeric,active,start):
        lookup={label(n):i for i,n in enumerate(names)}
        def find(*candidates):
            for name in candidates:
                if name in lookup and lookup[name] in numeric: return lookup[name]
            return None
        def check(title, required, expected, target, assumption):
            if target is None or any(c is None for c in required): return
            eligible=active.copy()
            for c in list(required)+[target]: eligible&=np.isfinite(numeric[c])
            projected=expected()
            eligible&=np.isfinite(projected)
            delta=np.abs(numeric[target]-projected)
            tolerance=np.maximum(MONEY_ABSOLUTE_TOLERANCE,np.abs(projected)*MONEY_RELATIVE_TOLERANCE)
            bad=eligible&(delta>tolerance)
            self.tables['financial_consistency'].append({'file':file,'worksheet':sheet,'check':title,
                'input_columns':raw_json([names[c] for c in required]),'target_column':names[target],
                'active_rows':int(active.sum()),'evaluable_rows':int(eligible.sum()),'unevaluable_rows':int((active&~eligible).sum()),
                'outside_tolerance_rows':int(bad.sum()),'absolute_tolerance':MONEY_ABSOLUTE_TOLERANCE,
                'relative_tolerance':MONEY_RELATIVE_TOLERANCE,'max_abs_difference_evaluable':float(delta[eligible].max()) if eligible.any() else None,
                'source_row_examples':raw_json(self.rows(bad,start)),'assumption':assumption,'business_rule_confirmed':False})
            self.issue(file,sheet,names[target],'Moderate','Provisional financial arithmetic: '+title,int(bad.sum()),
                'Apparent monetary discrepancies may reflect units, discounts, charges, rounding or source errors.',
                assumption+' Confirm the calculation basis and resolve against source documents; retain raw values.',True,self.rows(bad,start),int(eligible.sum()))
        qty=find('quantity','item quantity');price=find('unit price','item unit price');base=find('taxable value','item taxable value')
        if qty is not None and price is not None and base is not None:
            check('quantity × unit price versus taxable value',[qty,price],lambda:numeric[qty]*numeric[price],base,
                'Line-level same-unit values assumed; document discounts, freight and pricing units are not established.')
        total_lc=find('total lc');discount=find('discount')
        if qty is not None and price is not None and total_lc is not None and discount is not None:
            check('quantity × unit price × (1-discount/100) versus Total (LC)',[qty,price,discount],
                lambda:numeric[qty]*numeric[price]*(1-numeric[discount]/100),total_lc,
                'Discount interpreted as line percentage points; tax/freight/currency and pack-unit basis require confirmation.')
        tax_amounts=[]
        for component in ('igst','cgst','sgst','cess'):
            rate=find(component+' rate');amount=find(component+' amt',component+' amount')
            if amount is not None: tax_amounts.append(amount)
            if base is not None and rate is not None and amount is not None:
                check(component.upper()+' taxable value × rate/100 versus amount',[base,rate],
                    lambda b=base,r=rate:numeric[b]*numeric[r]/100,amount,
                    'Rate interpreted in percentage points on the reported taxable base. This is arithmetic screening, not a statutory GST determination.')
        line_total=find('line total include gst');other=find('non gst taxes')
        if base is not None and line_total is not None and len(tax_amounts)==4 and other is not None:
            required=[base]+tax_amounts+[other]
            check('taxable value + GST/CESS components + non-GST taxes versus line total',required,
                lambda:sum(numeric[c] for c in required),line_total,
                'All reported line-level components must be present and numeric; blanks are never substituted with zero. Unreported adjustments may explain differences.')
        reported_total=find('total value');freight=find('freightamt','freight amt')
        if base is not None and reported_total is not None and len(tax_amounts)>=3 and freight is not None:
            required=[base]+tax_amounts+[freight]
            check('taxable value + reported GST components + freight versus Total Value',required,
                lambda:sum(numeric[c] for c in required),reported_total,
                'Proposed line-total basis; freight allocation, discounts, other charges and document rounding require confirmation. All operands must be reported, never imputed.')
        igst=find('igst amt','igst amount');cgst=find('cgst amt','cgst amount');sgst=find('sgst amt','sgst amount')
        if None not in (igst,cgst,sgst):
            eligible=active&np.isfinite(numeric[igst])&np.isfinite(numeric[cgst])&np.isfinite(numeric[sgst])
            mixed=eligible&(numeric[igst]>0)&((numeric[cgst]>0)|(numeric[sgst]>0))
            self.tables['financial_consistency'].append({'file':file,'worksheet':sheet,'check':'Positive IGST together with positive CGST/SGST',
                'evaluable_rows':int(eligible.sum()),'outside_tolerance_rows':int(mixed.sum()),
                'assumption':'Review mixed components with business team; no tax-law validity conclusion.',
                'source_row_examples':raw_json(self.rows(mixed,start)),'business_rule_confirmed':False})
            self.issue(file,sheet,'IGST / CGST / SGST','Moderate','Mixed positive tax components',int(mixed.sum()),
                'Components may reflect adjustments or a tax-basis inconsistency.',
                'Review original document, transaction type and adjustment rules with the business team.',True,self.rows(mixed,start),int(eligible.sum()))
        if any(re.search(r'invoice.*total|invoice value|credit debit note value|credit debit note value',label(n)) for n in names):
            self.tables['dataset_specific'].append({'file':file,'worksheet':sheet,'column':'document totals',
                'finding':'Document totals may repeat on line-level rows; no unvalidated line-to-document total summation applied',
                'affected_records':int(active.sum()),'recommended_resolution':'Confirm document series, fiscal scope and line grain before document reconciliation.'})

    def matching(self):
        assessed={}
        for row in self.tables['identifier_quality']:
            assessed[(row['file'],row['worksheet'],row['column_name'])]=row
        comparison_counts=Counter()
        for prior in self.prior_matches.to_dict('records'):
            ka=(prior['file_a'],prior['worksheet_a'],prior['column_a'])
            kb=(prior['file_b'],prior['worksheet_b'],prior['column_b'])
            a=self.id_counts[ka];b=self.id_counts[kb];overlap=set(a)&set(b)
            actual={'distinct_a':len(a),'distinct_b':len(b),'distinct_overlap':len(overlap),
                'a_nonblank_rows':sum(a.values()),'b_nonblank_rows':sum(b.values()),
                'a_rows_matching_b':sum(a[v] for v in overlap),'b_rows_matching_a':sum(b[v] for v in overlap)}
            for metric,value in actual.items(): assert int(prior[metric])==value,(ka,kb,metric)
            row={**prior,**actual,'a_unmatched_rows':sum(a.values())-actual['a_rows_matching_b'],
                 'b_unmatched_rows':sum(b.values())-actual['b_rows_matching_a'],
                 'assessment':'Candidate value overlap only; no joined records or confirmed referential constraint'}
            self.tables['identifier_matching_coverage'].append(row)
            comparison_counts[ka]+=1;comparison_counts[kb]+=1
            # Only directional transaction-to-master candidates warrant an RI
            # review flag. Unused master codes are not automatically defects.
            if 'master' in ka[0].lower() and ('sales order report' in kb[0].lower() or 'sales invoice details' in kb[0].lower()) and prior['candidate_family'] in ('customer-code candidate','item-number candidate'):
                unmatched=row['b_unmatched_rows']
                self.issue(kb[0],kb[1],kb[2],'High','Unmatched values against candidate master: '+ka[0],unmatched,
                    'Candidate linkage could lose transaction rows; source version, scope and code conventions are unconfirmed.',
                    'Choose the authoritative master and validate scope/case/spacing rules before establishing a referential constraint or joining.',True,(),actual['b_nonblank_rows'])
        for key,row in assessed.items():
            row['candidate_matching_comparisons']=comparison_counts[key]
            row['matching_coverage_status']='See unconfirmed candidate matching comparisons' if comparison_counts[key] else 'No semantically supported comparison defined; not applicable to ordinals/measures, or mapping requires business confirmation'
            row['referential_constraint_confirmed']=False
        for a,b in itertools.combinations(self.payloads,2):
            if a['schema']!=b['schema']: continue
            overlap=set(a['counts'])&set(b['counts'])
            if overlap:
                self.tables['cross_source_duplicate_coverage'].append({'file_a':a['file'],'worksheet_a':a['worksheet'],
                    'file_b':b['file'],'worksheet_b':b['worksheet'],'distinct_payload_overlap':len(overlap),
                    'a_rows_with_payload_also_in_b':sum(a['counts'][v] for v in overlap),
                    'b_rows_with_payload_also_in_a':sum(b['counts'][v] for v in overlap),
                    'interpretation':'Same normalized header labels, raw typed business values, row ordinals excluded. SHA-256 comparison only; sources remain separate and precedence unconfirmed.'})

    def execute(self):
        dataset=self.root/'dataset'
        paths=sorted(p for p in dataset.rglob('*') if p.is_file())
        manifest={r.file:r for r in self.prior_sources.itertuples()}
        assert {str(p.relative_to(dataset)) for p in paths}==set(manifest),'Source file census changed; inventory refresh required'
        before={p:sha(p) for p in paths}
        for p in paths:
            file=str(p.relative_to(dataset));prior=manifest[file]
            assert before[p]==prior.sha256_after_audit,(file,'source hash differs from validated inventory')
            ref=self.headers[self.headers.file==file]
            book=None
            try:
                if p.suffix.lower() in ('.xlsx','.xlsm'):
                    book=load_workbook(p,read_only=True,data_only=True,keep_links=False)
                    assert set(book.sheetnames)==set(ref.worksheet),(file,'worksheet census changed')
                for record in ref.itertuples():
                    sheet=record.worksheet;header=int(record.header_excel_row)
                    raw_labels=json.loads(record.header_labels_json)
                    names=[str(v) if not blank(v) else f'<blank column {i}>' for i,v in enumerate(raw_labels,1)]
                    if book:
                        it=iter(book[sheet].iter_rows(values_only=True));epoch=book.epoch
                        prefix=list(itertools.islice(it,header))
                    else:
                        with p.open('r',encoding=record.csv_encoding,newline='') as f: rows=list(csv.reader(f,strict=True))
                        it=iter(rows);prefix=list(itertools.islice(it,header));epoch=None
                    actual_header=list(prefix[-1]);actual_header.extend([None]*(len(names)-len(actual_header)))
                    assert actual_header==raw_labels,(file,sheet,'header changed')
                    def padded():
                        for row in it:
                            if len(row)>len(names): raise ValueError('Source row extends beyond validated column extent')
                            yield tuple(row)+(None,)*(len(names)-len(row))
                    frame=pd.DataFrame(padded(),columns=range(len(names)),dtype=object)
                    if any('[SYNTHETIC DATA]' in str(v) for row in prefix for v in row):
                        self.tables['dataset_specific'].append({'file':file,'worksheet':sheet,'column':'preamble',
                            'finding':'Explicit synthetic-data marker in source title','affected_records':len(frame),
                            'recommended_resolution':'Confirm the intended use and whether synthetic scope extends to other files.'})
                        self.issue(file,sheet,'(source provenance)','High','Explicit synthetic-data provenance marker',len(frame),
                            'Synthetic examples can be inappropriate evidence for a production forecasting objective.',
                            'Confirm provenance and approved use of each source version with the business team.',True,(),len(frame))
                    self.profile(file,sheet,frame,names,header,epoch)
                    del frame
            finally:
                if book is not None: book.close()
        self.matching()
        assert len(self.tables['source_tables'])==20
        assert len(self.tables['missing_values'])==521
        assert len(self.tables['identifier_quality'])==135
        assert len(self.tables['date_quality'])==37
        totals={k:sum(r[c] for r in self.tables['date_quality']) for k,c in [('ambiguous', 'ambiguous_values'),('invalid','invalid_calendar_values'),('serial','possible_serial_values')]}
        assert totals=={'ambiguous':203455,'invalid':28,'serial':14949},totals
        for p in paths:
            after=sha(p)
            self.tables['source_integrity'].append({'file':str(p.relative_to(dataset)),'sha256_before':before[p],
                'sha256_after':after,'unchanged':before[p]==after,'matches_validated_inventory':before[p]==manifest[str(p.relative_to(dataset))].sha256_after_audit})
        assert all(r['unchanged'] for r in self.tables['source_integrity'])
        assert {str(p.relative_to(dataset)) for p in dataset.rglob('*') if p.is_file()}==set(manifest)
        for rel,old in self.inventory_before.items():
            assert sha(self.root/rel)==old,('inventory artifact changed',rel)
            self.tables['inventory_integrity'].append({'file':rel,'sha256_before':old,'sha256_after':old,'unchanged':True})
        self.tables['issue_register']=self.issues
        frames={name:pd.DataFrame(records) for name,records in self.tables.items()}
        self.export(frames)
        self.visualize(frames)
        self.report(frames,totals)
        self.progress('Assessment completed; sources and inventory evidence unchanged.')
        return frames

    def export(self,frames):
        detail_only={'duplicate_groups','entity_duplicate_groups','date_cell_exceptions','date_value_evidence','categorical_values','categorical_variants','spelling_candidates','numerical_token_issues'}
        # All detail is exported as CSV; Excel contains complete aggregate tables.
        core=[name for name in frames if name not in detail_only]
        for name,frame in frames.items(): frame.to_csv(self.out/f'{name}.csv',index=False,encoding='utf-8-sig')
        checks=[]
        with pd.ExcelWriter(self.out/'data_quality_evidence.xlsx',engine='openpyxl') as writer:
            used=set()
            for name in core:
                sheet=name[:31]
                assert sheet not in used
                used.add(sheet)
                frames[name].to_excel(writer,sheet_name=sheet,index=False)
                ws=writer.sheets[sheet];ws.freeze_panes='A2'
                for row in ws.iter_rows():
                    for cell in row:
                        if cell.data_type in ('e','f'): cell.data_type='s'
        def equivalent(expected,actual):
            if list(expected.columns)!=list(actual.columns) or len(expected)!=len(actual): return False
            for idx in range(len(expected)):
                for col in expected.columns:
                    v=expected.iloc[idx][col];a=actual.iloc[idx][col]
                    if pd.isna(v): v=''
                    if isinstance(v,(int,float,np.number)) and not isinstance(v,(bool,np.bool_)):
                        if not a: return False
                        # Excel stores 15 significant decimal digits. Compare
                        # floating diagnostics at a documented numerical tolerance.
                        if isinstance(v,(float,np.floating)):
                            if not math.isclose(float(v),float(a),rel_tol=1e-12,abs_tol=1e-12): return False
                        elif Decimal(str(v))!=Decimal(a): return False
                    elif str(v)!=str(a): return False
            return True
        for name,frame in frames.items():
            read=pd.read_csv(self.out/f'{name}.csv',dtype=str,keep_default_na=False)
            csv_ok=equivalent(frame,read)
            excel_ok=None
            if name in core:
                read_excel=pd.read_excel(self.out/'data_quality_evidence.xlsx',sheet_name=name[:31],dtype=str,keep_default_na=False)
                excel_ok=equivalent(frame,read_excel)
            checks.append({'report':name,'rows':len(frame),'csv_content_verified':csv_ok,
                'excel_content_verified':excel_ok,'excel_scope':'complete aggregate table' if name in core else 'full detail in CSV only'})
        pd.DataFrame(checks).to_csv(self.out/'export_validation.csv',index=False,encoding='utf-8-sig')
        assert all(r['csv_content_verified'] and r['excel_content_verified'] is not False for r in checks),'Report export content check failed'
        summary={'configuration':self.config,'files':17,'excel_workbooks':14,'excel_worksheets':17,'csv_tables':3,'tables':20,
            'column_profiles':521,'identifier_candidates':135,'date_fields':37,
            'inventory_artifacts_preserved':len(self.inventory_before),'all_source_hashes_unchanged':True,
            'date_counts':{'ambiguous':sum(r['ambiguous_values'] for r in self.tables['date_quality']),
                'impossible':sum(r['invalid_calendar_values'] for r in self.tables['date_quality']),
                'unconfirmed_serial':sum(r['possible_serial_values'] for r in self.tables['date_quality'])},
            'issue_counts_by_severity':dict(Counter(r['severity'] for r in self.issues)),
            'export_checks':checks,'read_failures':0,'business_primary_keys_confirmed':0}
        (self.out/'assessment_validation.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')

    def visualize(self,f):
        source=f['source_tables'];labels=source.file+' / '+source.worksheet
        fig,ax=plt.subplots(figsize=(12,8),constrained_layout=True)
        ax.barh(labels,source.blank_cell_percent,color='#497a9e');ax.invert_yaxis()
        ax.set_xlabel('Blank data cells (%) — includes optional and conditional fields')
        ax.set_title('Observed missingness by source table; no requiredness score')
        fig.savefig(self.out/'missingness_by_table.png',dpi=150,bbox_inches='tight');plt.close(fig)
        severity=Counter(r['severity'] for r in self.issues)
        fig,ax=plt.subplots(figsize=(7,4),constrained_layout=True)
        ax.bar(['Critical','High','Moderate','Low'],[severity[s] for s in ['Critical','High','Moderate','Low']],color=['#7a1824','#b94b4d','#d8a23b','#549b87'])
        ax.set_ylabel('Distinct source/column/rule findings (overlap possible)')
        ax.set_title('Issue severity — review priority, not proven error counts')
        fig.savefig(self.out/'issue_severity.png',dpi=150);plt.close(fig)

    def report(self,f,totals):
        def table(frame,columns,limit=None):
            if limit is not None: frame=frame.head(limit)
            def cell(v):
                if pd.isna(v): return ''
                if isinstance(v,(bool,np.bool_)): return str(bool(v))
                if isinstance(v,(int,np.integer)): return f'{int(v):,}'
                if isinstance(v,(float,np.floating)): return f'{v:,.4f}'.rstrip('0').rstrip('.')
                return str(v).replace('|','/').replace('\n',' ')
            header='| '+' | '.join(columns)+' |\n| '+' | '.join('---' for _ in columns)+' |\n'
            return header+'\n'.join('| '+' | '.join(cell(row[c]) for c in columns)+' |' for row in frame.to_dict('records'))
        missing=f['missing_values'];dups=f['duplicate_analysis'];dates=f['date_quality'];ids=f['identifier_quality'];nums=f['numerical_quality']
        financial=f.get('financial_consistency',pd.DataFrame());categories=f['categorical_consistency'];issues=f['issue_register']
        severities=issues.severity.value_counts().to_dict()
        substantive=missing[(missing.blank_percent_nonempty_rows>=50)&(missing.applicability_assessment=='requiredness unconfirmed')].copy()
        full=dups[dups.comparison=='all_raw_fields'];payload=dups[dups.comparison=='all_fields_excluding_row_ordinal']
        entity=f.get('entity_duplicate_analysis',pd.DataFrame())
        arithmetic=financial[financial['check'].str.contains('versus',na=False)] if not financial.empty else financial
        top=issues.copy();rank={'Critical':0,'High':1,'Moderate':2,'Low':3}
        top['priority']=top.severity.map(rank)
        top=top.sort_values(['priority','affected_records'],ascending=[True,False]).drop(columns='priority')
        body=f'''# Data quality assessment

Review date: {AS_OF.isoformat()}. This assessment covers 14 Excel workbooks, 17 Excel worksheets and 3 GST CSV tables: **20 tables and 521 columns**. All source files match the validated inventory hashes. The executed notebook checks that source files and every inventory report/evidence file remain unchanged.

## Executive assessment

The sources are available for continued investigation, but preparation for forecasting requires approved rules for dates, source versions, record grain and identifiers. The assessment records **{len(issues):,} source/column/rule findings**: {severities.get('Critical',0):,} Critical, {severities.get('High',0):,} High, {severities.get('Moderate',0):,} Moderate and {severities.get('Low',0):,} Low. These are overlapping review findings, not a count of distinct bad business records. No universal quality score is assigned because required fields, valid domains and business tolerances are unconfirmed.

- Date investigation reproduces all **203,455 ambiguous day/month cells, 28 impossible calendar dates and 14,949 unconfirmed numeric Excel serial candidates** from inventory. Ambiguous dates remain raw; both possible readings are retained in the date evidence.
- Duplicate checks find **{int(full.duplicate_excess_rows.sum()):,} excess exact full rows** and **{int(payload.duplicate_excess_rows.sum()):,} excess rows with identical business payload after excluding structural row ordinals**. These totals count within-source signatures. Repeated lines can be legitimate; no records were deleted.
- All **135 identifier candidates** were checked over full columns, and **101 candidate matching comparisons** were recomputed. Their metrics agree with inventory. No identifier or relationship is declared a confirmed business key or referential constraint.
- **{len(substantive):,} columns** have at least 50% blanks on nonempty rows while requiredness is unconfirmed. Optional/conditional candidates are reported separately rather than automatically treated as defects.
- Numerical and financial flags use diagnostic interpretations and explicit tolerances. Their correctness depends on units, document grain, discounts, return/adjustment conventions and the tax calculation basis.
- The unnamed `PCT_NOPJ` column contains 33 `NOPJ` values. Context suggests an agency/source marker, but its name remains unassigned. Explicit synthetic-data titles in both exchange-rate sheets and the reference customer sheet also need provenance confirmation.

## Scope, preservation and methods

The starting reference is `reports/data_inventory/validation/inventory_validation_evidence.xlsx`, including validated headers, table counts, 37 date-related fields, 135 identifier candidates and 101 matching comparisons. Every table was read in full. Examples are limited to ten locations per finding; counts and statistics use complete applicable columns/rows. Completely empty rows remain represented.

Source data was read without rewriting, cleaning, imputation, record deletion, ambiguous-date conversion, source joins or model training. Numeric parsing, whitespace/case comparisons and possible date readings exist only in diagnostic copies and reports. inventory evidence is preserved. [Source integrity](source_integrity.csv) and [inventory artifact integrity](inventory_integrity.csv) record before/after SHA-256 evidence.

{table(f['source_tables'],['file','worksheet','rows_below_header','nonempty_rows','empty_rows','columns'])}

## Severity and issue interpretation

- **Critical:** loss of source integrity, missing assessment scope or unreadable sources preventing a trustworthy assessment. These conditions stop execution; none were detected in the completed run.
- **High:** substantial risk to dates, identity, linkage, representation of measures, source suitability or double counting. Business confirmation may establish that a pattern is legitimate.
- **Moderate:** plausible formatting, chronology, distribution, category or arithmetic concern whose meaning depends on context.
- **Low:** structural empty rows, optional-field candidates or numerical conventions that merit documentation without an automatic error conclusion.

Every finding in [issue_register.csv](issue_register.csv) includes source, worksheet, column, affected count and unit, denominator where applicable, row examples, impact, recommended resolution and whether business confirmation is required. Some coverage findings count calendar months rather than records. Counts from different rules must not be added as distinct affected records.

## Missing values and applicability

There are **{int(f['source_tables'].empty_rows.sum()):,} completely empty rows** below the validated headers. Missing percentages are supplied both over all source rows and over nonempty rows, so empty structural rows do not inflate business-field missingness unnoticed. Blanks mean `None` or empty/whitespace-only text; placeholders such as `NA`, `#N/A`, `null` and `-` are separately counted and preserved.

Original/amendment fields, advance-receipt details, export/shipping fields, supplementary contact fields and transaction-dependent GST/HSN/SAC fields are marked as **conditional/optional candidates**, not confirmed optional fields. Requiredness remains a business decision. Sparse item labels in inventory audits are marked as a grouped-layout possibility; no fill-down is applied. No missing value is silently assigned a zero or substitute.

Examples with >=50% missingness and unconfirmed requiredness:

{table(substantive.sort_values('blank_percent_nonempty_rows',ascending=False),['file','worksheet','column_name','blanks_on_nonempty_rows','blank_percent_nonempty_rows'],12)}

Complete results: [missing_values.csv](missing_values.csv), one row per source column, including empty-column flags, placeholder counts, applicability explanations and original observed types. Requiredness/applicability should be confirmed before prioritizing blank fields for any cleaning.

## Duplicate records and transaction grain

Three comparisons are separated: all raw typed fields; all fields excluding `#`/`S.No` row ordinals; and an explicitly proposed transaction-line signature where document/item/date/quantity/price fields support it. Raw whitespace and source value types remain significant in exact comparisons. Within-source duplicate hash groups are verified by comparing their typed values.

{table(dups[(dups.duplicate_excess_rows>0)],['file','worksheet','comparison','duplicate_groups','duplicate_excess_rows','rows_in_duplicate_groups'],18)}

Repeated customer/product codes in line tables and repeated document numbers can represent valid granularity. Master/reference codes and diagnostic name variants are separately inspected for repeated identities and differing attributes. Similar names do not prove that entities are identical. Cross-source same-schema payload overlap is reported only as evidence of possible overlapping exports; versions are kept separate and precedence is unconfirmed.

See [duplicate summaries](duplicate_analysis.csv), [duplicate groups and source locations](duplicate_groups.csv), [master/reference entity analysis](entity_duplicate_analysis.csv), and [cross-source payload overlap](cross_source_duplicate_coverage.csv). Confirm document series/fiscal scope/line identifiers and source precedence before considering deduplication.

## Date quality, representations and chronology

All 37 fields include original types, representative untouched values, format/status counts, interpretations, partial coverage and gap evidence in [date_quality.csv](date_quality.csv). [date_value_evidence.csv](date_value_evidence.csv) preserves every observed distinct raw token with its count, original type, candidate readings, interpretation notes and example locations. [date_cell_exceptions.csv](date_cell_exceptions.csv) enumerates incomplete/invalid/serial candidate cells with source coordinates.

- Ambiguous DMY/MDY values retain two alternatives. No one alternative becomes the source date or the accepted date for chronology checks.
- Impossible dates are separately distinguished from ambiguity. All 28 impossible calendar cells are represented in the exception report, including `31/02/27` and `31/02/26`.
- Numeric values are investigated using each workbook's actual epoch and supplied as **unconfirmed Excel serial candidates**. They remain excluded from accepted chronology and coverage.
- `Exchange Rate 1.xlsx` retains the corrected `2027-03` period. The seven observed month periods run September 2026 through March 2027. Month periods are tracked at monthly resolution; a candidate first day is a display convention, not an observed transaction day.
- `Revision_Month` numbers without years remain incomplete period attributes. Two-digit-year interpretations retain inventory's explicitly conditional century convention; source confirmation is still required.
- Chronological coverage and gaps use only calendar-unambiguous values (and explicit monthly periods for month coverage). Excluded ambiguous/serial dates can explain apparent gaps. Calendar gaps do not prove missing business activity, because no working calendar or expected transaction cadence is supplied.
- Proposed order/delivery, order/invoice and exchange-period start/end checks evaluate only pairs with unambiguous readings. Unevaluable counts are reported. Future dates are compared with {AS_OF.isoformat()}; planning dates can legitimately be future dates.

{table(dates.sort_values('ambiguous_values',ascending=False),['file','column','ambiguous_values','invalid_calendar_values','possible_serial_values','unambiguous_min','unambiguous_max'],12)}

See [coverage gaps](date_coverage_gaps.csv) and [chronology checks](chronology_checks.csv). Confirm source-specific format, century, epoch and event semantics before approving any chronological dataset.

## Identifier quality and candidate referential coverage

All 135 inventory candidates have full-column null, duplicate and distinct counts, uniqueness percentages, semantic roles, candidate matching coverage status and explicit unconfirmed-key flags in [identifier_quality.csv](identifier_quality.csv). Uniqueness percentage is distinct nonblank values divided by nonblank values; null percentage is reported separately. Both all-row and nonempty-row denominators are provided.

Ordinals, measures, dates and classification/contact attributes are not promoted to entity keys merely because values are unique. Candidate document references may repeat legitimately on lines. All 101 inventory value-overlap comparisons are recomputed from full raw values in [identifier_matching_coverage.csv](identifier_matching_coverage.csv). Case and whitespace remain significant. Each unmatched transaction-to-master count is an **unconfirmed referential risk**, not a proved foreign-key violation. Unused master values are not automatically defects. Candidates without a supported comparison are explicitly marked unmapped/not applicable instead of receiving fabricated coverage.

{table(ids[ids.semantic_role.str.startswith('entity/document')].sort_values('nulls_on_nonempty_rows',ascending=False),['file','worksheet','column_name','null_or_blank_rows','distinct_nonblank_values','duplicate_excess_rows','nonblank_uniqueness_percent'],12)}

Confirm authoritative customer/item/product masters, code systems, document series and source scope before approving any join or business primary key.

## Numerical, quantity and financial investigation

[numerical_quality.csv](numerical_quality.csv) profiles {len(nums):,} measure columns, including observed types, parse statuses, negative/zero/fractional counts, min/max, percentiles, mean/std and outer-IQR candidates. Raw strings remain unchanged. Diagnostic parsing recognizes explicit numeric strings, validated thousands grouping, currency wrappers, percentage signs and accounting parentheses, with the rule recorded. Unknown grouping, boolean measures and malformed text remain unevaluable; they are not replaced by zero. `Stock_Impact` is a flag. `Pricing unit` is profiled as categorical/unit metadata based on its observed encodings; its business meaning requires confirmation. Mixed-unit lead-time strings require unit confirmation and are not automatically called invalid quantities.

Negative values may be returns or adjustments, zeros may be genuine or cancelled lines, and fractional quantities may be valid under some UOMs. [Numerical context](numerical_context.csv) breaks signs, zeros and fractional values down by available transaction type, credit/debit indicator, status, UOM and inventory document prefix. Prefixes are diagnostic groupings, not approved document semantics. Statistical flags use all interpreted finite values and **Q1/Q3 ± 3 × IQR**; the rule is withheld where IQR is zero or there are fewer than eight values. Product/unit/price mix can explain extreme values. [Numerical token exceptions](numerical_token_issues.csv) preserve representation failures.

Provisional financial screening checks quantity × unit price, explicitly named line discounts, GST component amount versus taxable base × rate/100, and supported CSV line-total component arithmetic. A mismatch exceeds **max(1 monetary unit, 0.5% of the projected value)**. These tolerances are diagnostic parameters, not business-approved materiality or statutory rules. Rates are explicitly interpreted in percentage points for these checks. All operands must be present and interpretable; blanks are not substituted with zero. Document-level invoice/note totals are not summed or compared as if every repeated line were an independent document total.

{table(arithmetic.sort_values('outside_tolerance_rows',ascending=False),['file','worksheet','check','evaluable_rows','unevaluable_rows','outside_tolerance_rows'],16)}

Every supported check, its inputs, eligibility, assumptions, tolerance and examples appears in [financial_consistency.csv](financial_consistency.csv). Discounts, freight, pack/pricing units, rounding, document grain, currency and credit/debit sign conventions must be confirmed before interpreting mismatches as accounting errors. This is arithmetic screening, not a determination of GST legal compliance.

## Categories, spelling and representation

[categorical_consistency.csv](categorical_consistency.csv) profiles string-bearing columns for outer/internal spaces, case variants and diagnostic Unicode/spacing/case collisions. Original values remain separate. The raw-to-proposed representation evidence is in [categorical_variants.csv](categorical_variants.csv); it is not an approved mapping.

Potential spelling pairs are restricted to small category domains, exclude codes/entity names/descriptions/free-text reasons and values containing digits, and use a stated text-similarity threshold of 0.84. [spelling_candidates.csv](spelling_candidates.csv) lists review candidates; resemblance does not establish a typo. [categorical_values.csv](categorical_values.csv) records observed category levels and types. [Flag encoding representations](flag_encoding_representations.csv) separates yes/no, Y/N, boolean, numeric and text encodings without assuming equivalence. The proposed Active/Inactive binary encodings are screened separately; an approved business catalogue is still needed to determine which other category values are invalid or unexpected. No observed-value set is silently treated as an approved domain.

## Dataset-specific findings and confirmation requests

- `PCT_NOPJ` has a blank first-column header but actual data in all 33 rows (`NOPJ`). `PTC_NOPI` provides surrounding agency context; the unnamed column remains positional pending owner confirmation.
- Both exchange-rate sheets and the reference customer table carry explicit synthetic-data markers. Their intended role and whether other sources are synthetic require confirmation; file names and example-looking records alone do not establish authenticity or authority.
- Reference `Customer Code` and `BP_CODE` differ in completeness and code systems. They remain separate candidates.
- Sparse inventory item labels may be group-level context. Forward filling or declaring those blank cells erroneous requires report-layout confirmation.
- Repeated document totals and transaction identifiers need verified document/line grain and source precedence before any aggregation or deduplication.

See [dataset_specific.csv](dataset_specific.csv), the full issue register, and the original inventory validation report for context.

## Priority review queue

The following is an excerpt; the complete register is authoritative. Review priority does not certify that every flagged pattern is erroneous.

{table(top,['issue_id','severity','source_file','worksheet','affected_column','rule','affected_records'],20)}

## Recommended next steps, pending approval

1. Obtain source provenance/version precedence and confirm the forecasting use of synthetic/reference data.
2. Approve date format, century, serial-date and monthly-period rules; obtain corrected source evidence for impossible dates.
3. Confirm requiredness, conditional applicability, business grain, stable identifiers and reference/master mappings.
4. Review duplicate groups and financial exceptions with document, UOM, pricing, tax and accounting context.
5. Approve explicit raw-to-canonical category/numeric policies and a documented exception workflow before applying any cleaning.

Data preparation requires review and approval. No source corrections or modeling steps have been applied.

## Execution and validation

The assessment validates all 20 table extents, 135 identifier metrics and 37 date-field metrics against inventory, including the three headline date counts. All 17 source hashes and all {len(self.inventory_before):,} inventory artifact hashes are checked. [assessment_validation.json](assessment_validation.json) records scope, settings and export checks; [export_validation.csv](export_validation.csv) records CSV/Excel read-back verification. Detailed CSVs are complete; the [Excel evidence workbook](data_quality_evidence.xlsx) contains complete aggregate tables, with detailed row/token evidence explicitly kept in CSVs.

Notebook: [02_data_quality_analysis.ipynb](../../notebooks/02_data_quality_analysis.ipynb). Reusable implementation: [assess_data_quality.py](../../src/data/assess_data_quality.py).

```powershell
.\\.venv\\Scripts\\python.exe src\\data\\assess_data_quality.py
```

All reports contain source-derived business information and should follow the dataset's handling rules.
'''
        # Always create empty optional evidence files with a clear schema.
        optional=['cross_source_duplicate_coverage','spelling_candidates','numerical_token_issues','date_coverage_gaps','entity_duplicate_analysis','entity_duplicate_groups','chronology_checks']
        for name in optional:
            if name not in f:
                pd.DataFrame({'status':['No findings or no supported comparison']}).to_csv(self.out/f'{name}.csv',index=False,encoding='utf-8-sig')
        (self.out/'data_quality_report.md').write_text(body,encoding='utf-8')


def run(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    return Assessment(root).execute()


if __name__=='__main__':
    run()
