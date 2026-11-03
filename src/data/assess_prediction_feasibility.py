"""Evidence-based feasibility documentation; no prediction engine is implemented.

This module audits existing metadata, profiles date evidence, and renders a human
assessment. The named use cases are report examples, not a runtime catalogue,
question router, model registry, automatic target builder or algorithm selector.
No source joins, target values, features, predictions or model metrics are made.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from openpyxl import load_workbook


AS_OF = date(2026, 11, 2)
VALID_DATE_STATUSES = {'native Excel datetime', 'explicit year-month-day',
                       'same under DMY and MDY', 'unambiguous DMY by calendar'}
OUTPUT_NAMES = {'business_prediction_feasibility_report.md', 'prediction_target_mapping.xlsx',
                'prediction_data_requirements.xlsx', 'feasibility_validation.json',
                'feasibility_notebook_validation.json'}


def read_csv(path):
    return pd.read_csv(path, keep_default_na=False, encoding='utf-8-sig')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()


def blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def norm(value):
    return re.sub(r'[\W_]+', ' ', str(value).casefold()).strip()


def markdown_table(frame, columns):
    def cell(v): return str(v).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---']*len(columns)) + ' |'] +
                     ['| ' + ' | '.join(cell(v) for v in row) + ' |'
                      for row in frame[columns].itertuples(index=False, name=None)])


class FeasibilityAssessment:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.out = self.root/'reports/analysis'
        self.evidence = self.out/'feasibility_evidence'
        self.evidence.mkdir(parents=True, exist_ok=True)
        manifest = self.evidence/'input_manifest.json'
        if manifest.exists():
            self.baseline = json.loads(manifest.read_text(encoding='utf-8'))
        else:
            files = [p for p in (self.root/'reports').rglob('*') if p.is_file()
                     and self.evidence not in p.parents and p.name not in OUTPUT_NAMES]
            files += [p for p in (self.root/'dataset').rglob('*') if p.is_file()]
            files += [p for p in (self.root/'notebooks').glob('*.ipynb') if not p.name.startswith('04_')]
            files += [self.root/'src/data'/name for name in (
                'validate_inventory.py', 'assess_data_quality.py', 'analyze_relationships.py', 'validate_relationship_analysis.py')]
            self.baseline = {p.relative_to(self.root).as_posix(): sha(p) for p in files}
            manifest.write_text(json.dumps(self.baseline, indent=2), encoding='utf-8')
        self.checks, self.results, self.export_checks = [], {}, []
        self.check('All prior artifacts match assessment baseline',
                   all((self.root/p).exists() and sha(self.root/p)==h for p,h in self.baseline.items()))

    def check(self, test, passed, detail=''):
        self.checks.append({'test': test, 'passed': bool(passed), 'detail': str(detail)})
        if not passed: raise AssertionError((test, detail))

    def load_evidence(self):
        q = self.root/'reports/data_quality'
        i = self.root/'reports/data_inventory/validation'
        self.columns = read_csv(i/'column_validation.csv')
        self.headers = read_csv(i/'header_validation.csv')
        self.sources = read_csv(q/'source_tables.csv')
        self.dates = read_csv(q/'date_quality.csv')
        self.date_tokens = read_csv(q/'date_value_evidence.csv')
        self.possible_dates = read_csv(i/'date_validation.csv')
        self.issues = read_csv(q/'issue_register.csv')
        self.numeric = read_csv(q/'numerical_quality.csv')
        self.missing = read_csv(q/'missing_values.csv')
        self.categories = read_csv(q/'categorical_values.csv')
        self.relationships = read_csv(self.out/'relationship_candidates.csv')
        self.granularity = read_csv(self.out/'dataset_granularity.csv')
        self.context = read_csv(self.out/'document_context.csv')
        self.ids = read_csv(self.out/'identifier_profiles.csv')
        self.financial = read_csv(q/'financial_consistency.csv')
        self.authority = read_csv(self.out/'authority_assessment.csv')
        self.authenticity = read_csv(self.out/'source_authenticity.csv')
        self.duplicates = read_csv(q/'duplicate_analysis.csv')
        self.schema_ids = {tuple(v): n for n,v in enumerate(self.sources[['file','worksheet']].itertuples(index=False,name=None))}
        self.check('Validated evidence scope', len(self.sources)==20 and len(self.columns)==521 and len(self.ids)==135
                   and len(self.dates)==37 and len(self.issues)==424 and len(self.relationships)==148)
        source_hashes = read_csv(q/'source_integrity.csv')
        files = {p.relative_to(self.root/'dataset').as_posix():p for p in (self.root/'dataset').rglob('*') if p.is_file()}
        self.check('Source file census unchanged', set(files)==set(source_hashes.file) and len(files)==17)
        for r in source_hashes.itertuples(index=False):
            self.check('Source matches validated source hash: '+r.file, sha(files[r.file])==r.sha256_after)
        # Read actual workbooks as starting references; CSV companions must agree.
        for file,sheets in [
            (i/'inventory_validation_evidence.xlsx', {'header_validation':self.headers, 'column_validation':self.columns}),
            (self.out/'identifier_relationship_matrix.xlsx', {'identifier_profiles':self.ids, 'relationship_candidates':self.relationships}),
            (self.out/'dataset_granularity_report.xlsx', {'dataset_granularity':self.granularity, 'document_context':self.context})]:
            with pd.ExcelFile(file) as book:
                for sheet, expected in sheets.items():
                    actual = book.parse(sheet, keep_default_na=False)
                    self.compare(expected, actual, f'Prior workbook/CSV {file.name}/{sheet}')
        for p in [self.root/'reports/data_inventory/inventory_validation_report.md',q/'data_quality_report.md',
                  self.out/'dataset_relationship_report.md', self.out/'data_model_diagram/logical_business_model.mmd']:
            self.check('Reviewed reference nonempty: '+p.name, len(p.read_text(encoding='utf-8'))>100)
        self.check('Logical diagram readable',ET.parse(self.out/'data_model_diagram/logical_business_model.svg').getroot().tag.endswith('svg'))
        self.results['source_grain_evidence'] = self.granularity.copy()
        self.results['schema_evidence'] = self.columns.copy()
        self.results['measure_evidence'] = self.numeric.copy()
        self.results['identifier_evidence'] = self.ids.copy()
        self.results['financial_rule_evidence'] = self.financial.copy()
        self.results['categorical_evidence'] = self.categories.copy()
        self.results['document_context_evidence'] = self.context.copy()
        self.results['source_authority'] = self.authority.copy()
        self.results['source_authenticity'] = self.authenticity.copy()

    def date_coverage(self):
        rows, buckets = [], []
        for r in self.dates.itertuples(index=False):
            tokens = self.date_tokens[(self.date_tokens.file==r.file) &
                (self.date_tokens.worksheet==r.worksheet) & (self.date_tokens.column_number==r.column_number)]
            self.check(f'Date token counts reconcile {r.file}/{r.column}',int(tokens['count'].sum())==int(r.nonblank_values))
            calendar, strict = Counter(), Counter()
            century_rows = 0
            for tok in tokens.itertuples(index=False):
                century = 'century' in str(tok.interpretation_note).casefold()
                if century: century_rows += int(tok.count)
                values = json.loads(tok.possible_dates)
                if tok.status in VALID_DATE_STATUSES and len(values)==1:
                    d = date.fromisoformat(values[0][:10])  # Already explicit ISO evidence; never parse a raw source token.
                    calendar[d] += int(tok.count)
                    if not century: strict[d] += int(tok.count)
            before = {d:n for d,n in strict.items() if d<=AS_OF}
            calendar_before = {d:n for d,n in calendar.items() if d<=AS_OF}
            days = sorted(before)
            months = sorted({d.strftime('%Y-%m') for d in days})
            weeks = {d.isocalendar()[:2] for d in days}
            month_span = ((days[-1].year-days[0].year)*12+days[-1].month-days[0].month+1) if days else 0
            prior = self.possible_dates[(self.possible_dates.file==r.file) &
                (self.possible_dates.worksheet==r.worksheet) & (self.possible_dates.column_number==r.column_number)].iloc[0]
            rows.append({'file':r.file,'worksheet':r.worksheet,'column':r.column,'column_number':int(r.column_number),
                'original_types':r.raw_types,'representative_original_values':r.representative_original_values,
                'nonblank_date_cells':int(r.nonblank_values),'ambiguous_day_month_cells':int(r.ambiguous_values),
                'invalid_calendar_cells':int(r.invalid_calendar_values),'possible_serial_cells':int(r.possible_serial_values),
                'century_dependent_cells_including_ambiguous':century_rows,
                'calendar_resolved_cells_under_prior_century_convention':sum(calendar.values()),
                'calendar_resolved_min_under_prior_convention':min(calendar).isoformat() if calendar else '',
                'calendar_resolved_max_under_prior_convention':max(calendar).isoformat() if calendar else '',
                'calendar_resolved_at_or_before_asof':sum(calendar_before.values()),
                'calendar_resolved_beyond_asof':sum(n for d,n in calendar.items() if d>AS_OF),
                'explicit_full_year_or_native_cells':sum(strict.values()),
                'explicit_full_year_or_native_at_or_before_asof':sum(before.values()),
                'explicit_full_year_or_native_beyond_asof':sum(n for d,n in strict.items() if d>AS_OF),
                'strict_partial_history_min':days[0].isoformat() if days else '',
                'strict_partial_history_max':days[-1].isoformat() if days else '',
                'distinct_observed_days_asof':len(days),'distinct_iso_weeks_asof':len(weeks),
                'distinct_observed_months_asof':len(months),'partial_month_span_asof':month_span,
                'unobserved_months_in_partial_span':month_span-len(months),
                'explicit_month_period_cells':int(r.month_period_values),
                'possible_min_including_alternatives_NOT_accepted':prior.possible_coverage_min_including_alternatives_and_periods,
                'possible_max_including_alternatives_NOT_accepted':prior.possible_coverage_max_including_alternatives_and_periods,
                'production_history_sufficiency':'Not established: formats/century, actual-versus-planned meaning, extract completeness and availability time unapproved',
                'evidence_reference':'../data_quality/date_value_evidence.csv; ../data_inventory/validation/date_validation.csv'})
            by_month = Counter()
            for d,n in before.items(): by_month[d.strftime('%Y-%m')]+=n
            for month,n in sorted(by_month.items()):
                buckets.append({'file':r.file,'worksheet':r.worksheet,'column':r.column,'month':month,
                    'date_cell_occurrences':n,'interpretation':'Diagnostic timestamp coverage only; not a target series, transaction count, complete period or imputed zero'})
        self.results['historical_date_coverage'] = pd.DataFrame(rows)
        self.results['date_coverage_diagnostics'] = pd.DataFrame(buckets)
        c = self.results['historical_date_coverage']
        self.check('Unresolved dates preserved',int(c.ambiguous_day_month_cells.sum())==203455 and
            int(c.invalid_calendar_cells.sum())==28 and int(c.possible_serial_cells.sum())==14949)
        self.check('As-of partitions conserve explicit dates',bool((c.explicit_full_year_or_native_cells==
            c.explicit_full_year_or_native_at_or_before_asof+c.explicit_full_year_or_native_beyond_asof).all()))

    def column(self, file, sheet, name):
        candidates=self.columns[(self.columns.file==file)&(self.columns.worksheet==sheet)]
        matches=candidates[candidates.column_name.apply(norm)==norm(name)]
        if len(matches)!=1: raise ValueError(('Evidence binding not uniquely supported',file,sheet,name))
        return matches.iloc[0]

    def source_probe(self):
        # Small representative source probes independently check the problematic grain.
        # Selection is for auditing cost only and does not assign source authority.
        rows=[]
        for entity in ('Sales order detail','Sales invoice detail'):
            source=self.granularity[self.granularity.candidate_business_entity==entity].sort_values('row_count').iloc[0]
            context=self.context[self.context.table==source.table]
            key=context.document_key.iloc[0]
            ref=self.headers[(self.headers.file==source.file)&(self.headers.worksheet==source.worksheet)].iloc[0]
            wb=load_workbook(self.root/'dataset'/source.file,read_only=True,data_only=True)
            try:
                it=wb[source.worksheet].iter_rows(values_only=True)
                for _ in range(int(ref.header_excel_row)): header=next(it)
                names=list(header)
                def pos(n):
                    found=[i for i,v in enumerate(names) if norm(v)==norm(n)]
                    if len(found)!=1:raise ValueError((source.file,n,found))
                    return found[0]
                kp=pos(key)
                attrs={a:pos(a) for a in context.attribute}
                groups={a:defaultdict(set) for a in attrs}
                n=0
                for raw in it:
                    n+=1
                    k=raw[kp] if kp<len(raw) else None
                    if blank(k):continue
                    for a,p in attrs.items():
                        v=raw[p] if p<len(raw) else None
                        if not blank(v):groups[a][(type(k).__name__,str(k))].add((type(v).__name__,str(v)))
                self.check('Independent source row count '+source.file,n==int(source.row_count))
                for old in context.itertuples(index=False):
                    actual=sum(len(v)>1 for v in groups[old.attribute].values())
                    self.check('Independent document context '+source.file+'/'+old.attribute,
                        actual==int(old.groups_with_multiple_nonblank_raw_values))
                    rows.append({'file':source.file,'worksheet':source.worksheet,'raw_document_key':key,
                        'attribute':old.attribute,'source_rows':n,'document_groups':int(old.document_groups),
                        'groups_with_multiple_raw_attribute_values':actual,
                        'interpretation':'Confirmed raw variation; reused scope, formatting or genuine conflict not resolved; source not corrected'})
            finally:wb.close()
        self.results['independent_grain_probes']=pd.DataFrame(rows)

    def assessment_examples(self):
        # Human-reviewed examples for this report only; not a question/model mapping.
        base={'horizon_requirement':'Not supplied by NOP. Confirm decision lead time H, bucket and update cadence; any horizon examples are discussion options, not approved requirements.',
              'today_model_ready':False,'business_definition_approved':False,'target_values_generated':False}
        examples=[
            ('T01','Sales forecasting','Primary requested example','Feasible with Conditions',
             'Forecast recorded invoice activity; distinguish document count, booked orders, shipped units and financial sales.',
             'Future count of distinct scoped invoice references per approved complete time bucket',
             'Proposed only: COUNT DISTINCT(Invoice Num at owner-confirmed issuer/series/year scope) by approved Invoice Date bucket; count documents, not lines. No count series generated. Issuer/scope is a required semantic rule, not an invented source column.',
             'Time-series count forecasting after source/time gates; compare simple count/seasonal baselines only when supported. Historical COUNT is analytics.',
             'Aggregate issuer-level first; customer/product breakdown requires separate stable entities and adequate observations.',
             'Small invoice: 337 lines / 234 document references, internally constant billing party/date/total; partial full-year dates span ten months. No annual-seasonality evidence and no approved extraction boundary.',
             'Priority 1 candidate after gates: least dependence on monetary/unit rules and joins; never substitute invoice activity for another meaning of sales.',
             'Source authenticity, invoice scope/date rules, complete periods and cancellation/void policy; additional mature history if folds/horizon cannot be supported.'),
            ('T02','Revenue forecasting','Primary requested example','Feasible with Conditions',
             'Forecast an approved invoiced tax-exclusive value proxy; recognized revenue is a different business outcome.',
             'Future additive invoiced taxable value per approved period, currency and entity scope',
             'Proposed only: SUM(reported Taxable Value) on approved invoice lines in a period; discount/freight/tax/sign and currency policies unresolved. Net adjustments require separate approved allocation and note sign rules. Invoice Total Include GST repeats per line.',
             'Time-series value forecasting conditional on a reconciled additive measure; historical SUM/SQL is analytics, not a prediction.',
             'Issuer/currency/period; no product/customer split until keys, units and series support pass.',
             '337 small invoice lines correspond to GST representation, not additional revenue. Only ten months of partial dated coverage; quantity/base and tax arithmetic exceptions remain.',
             'Conditional follow-on after count capability and finance-owned measure contract.',
             'Actual revenue recognition, collections and profit cannot be inferred from invoice values. Obtain ledger recognition/settlement history for those outcomes.'),
            ('T03','Customer purchase propensity','Primary requested example','Not Currently Feasible',
             'Estimate probability of a defined purchase in a future window for a known eligible customer at a decision cutoff.',
             'P(purchase in (t,t+H] | information available at t) for an eligible customer',
             'Proposed definition only: positive if approved purchase event occurs in the complete outcome window; negative only if eligible and fully observed with no qualifying purchase. Censored/unknown is not negative. No labels made.',
             'Supervised classification or event-time approach only after cohort, historical positive/negative outcomes and label maturity are defensible.',
             'Eligible customer at cutoff t; customer identity, H and repeat-scoring interval require approval.',
             'Customer/order references and purchases-like events exist, but all 40 small-order customer codes occur in the 40-row master. No verified historical nonpurchaser/cohort/exposure panel or eligibility start/end/observation boundary. Invoice customer mapping is unapproved.',
             'Defer model development; obtain cohort and observation history before creating either class.',
             'Approved customer crosswalk; onboarding/eligibility/activity history, complete event capture, extraction closure, outcome maturity and decision-time availability.'),
            ('T04','Product/service demand forecasting','Primary requested example','Feasible with Conditions',
             'Forecast observable product sales/order demand proxies; distinguish these from unconstrained physical demand and service capacity.',
             'Future product-period reported quantity, or service-period activity/value under a separately approved unit',
             'Proposed only: SUM(Quantity) for approved product/UOM and event scope. Goods/service flags identify separate line classes; do not add incompatible units or infer latent unmet demand. Service hours/jobs are not provided.',
             'Per-series or pooled time-series strategy depends on each entity history, intermittency, cold starts and hierarchy validity; not one algorithm for every product.',
             'Product + approved unit + period; service category/metric requires an owner-approved definition.',
             'Small invoice has 323 G and 14 S lines; large has 99,242 G and 941 S. Small order has 36 blank product rows; repeated SO scope and service-like zero quantities prevent a universal quantity target. UOM Manual is not a confirmed physical unit.',
             'Conditional for sufficiently supported goods series; service duration/capacity and unconstrained demand are not currently supported.',
             'Approved item/foreign-code crosswalks, returns/cancellations, pricing units, complete entity history, stockout/lost-sales data for latent demand and actual service units/history.'),
            ('T05','Inventory forecasting','Primary requested example','Not Currently Feasible',
             'Forecast future on-hand stock or stockout risk by product and warehouse.',
             'Future stock balance or probability of stockout over an approved horizon',
             'Desired balance identity only: approved opening stock + signed receipts - signed issues +/- approved adjustments. Movement signs/types, grouping and opening/cumulative semantics are unvalidated; no stock series calculated.',
             'Inventory balance planning/rules may be sufficient when future movements are known; uncertain inputs may later require forecasts. Stockout classification needs availability/outcome history.',
             'Product/warehouse/availability time; forecast horizon should reflect replenishment decisions, not an arbitrary fixed period.',
             'Large audit has 98,104 movement rows without raw item code; three grouped audits are not a confirmed regular snapshot panel. Item master stock/update date is not repeated historical stock observation.',
             'Defer stock and stockout models; approve movement reconstruction and obtain authoritative snapshots/movement lifecycle first.',
             'Opening balances, stable movement/product/warehouse IDs, receipt/issue/adjustment semantics, as-of snapshots, reservations, purchase orders and actual receipt/stockout history.'),
            ('T06','Unknown numerical outcomes','Broader capability example','Not Currently Feasible',
             'Predict an unknown future/decision-time numerical outcome rather than retrieve an already observed amount.',
             'Owner-selected realized numerical outcome at an explicit event/decision horizon',
             'No approved realized-outcome/decision-time pair supplied. Existing invoice amounts and quantities are observed fields, not automatically regression labels for an unseen transaction.',
             'Supervised regression is conditional on historical feature availability, comparable decisions and outcome capture; deterministic quantity/price arithmetic remains analytics.',
             'Decision/event row with stable identity and outcome linkage, not arbitrary missing-cell imputation.',
             'Numerical fields exist, but no approved quote/decision snapshot, actual realization linkage or availability timestamps establish a leakage-free supervised dataset.',
             'Obtain the decision process and realized outcome history before selecting predictors or algorithms.',
             'Decision records, effective/available timestamps, realized outcome definition, scope, training eligibility and outcome delay.'),
            ('T07','Cancellation or adjustment risk','Broader capability example','Not Currently Feasible',
             'Predict future cancellation/credit adjustment for an eligible order or invoice.',
             'Future event indicator within a defensible observation window',
             'Current Status and existing notes are observed states/events, not future labels. Need order/invoice-at-t cohort plus event timestamps and complete non-event windows.',
             'Classification or event-time analysis only with matured outcomes and approved temporal document linkage.',
             'Eligible document at cutoff with unambiguous company/year/series/line scope.',
             'Small order has current 44 Canceled lines, 50 Open and 1,004 Closed; these are line states, not 44 uniquely scoped historical cancellation outcomes. No transition history or verified negatives.',
             'Defer; existing states support descriptive audit only under known scope.',
             'Status event log, decision-time state/features, cancellation/credit dates, original document keys and full follow-up.'),
            ('T08','Delivery time or delay prediction','Broader capability example','Not Currently Feasible',
             'Predict actual completion time or lateness against a promised date.',
             'Actual completion duration, or actual-versus-promised lateness',
             'No verified actual delivery/completion timestamp. Delivery Date role is unconfirmed; subtracting it from Posting Date yields a reported interval, not necessarily realized delivery performance.',
             'Regression/survival only with actual events, censoring and decision-time evidence; a planned-date difference is analytics.',
             'Scoped order/line/service event and promised-versus-actual event history.',
             'Posting Date and Delivery Date exist; large delivery field contains 15 impossible dates and values extending to 2028-04-30 under partial interpretations.',
             'Request actual fulfilment/service milestones; do not relabel planned dates as outcomes.',
             'Promise revisions, actual shipment/delivery/completion events, partial quantities, censoring and stable line references.'),
            ('T09','Collections, cash flow, recognized revenue or margin','Broader capability example','Not Currently Feasible',
             'Predict collection/default timing, recognized revenue or realized profitability.',
             'Future settled cash, ledger-recognized amount or realized margin under an approved finance definition',
             'No actual settlement/recognition/COGS allocation outcome established. Payment Terms, invoice totals and inventory costs are not substitute labels.',
             'Forecasting, regression or classification depends on the outcome; no approach is admissible without labels/financial semantics.',
             'Customer/invoice/ledger period with actual settlement and cost allocation scope.',
             'Schema lacks identified actual-payment/settlement and recognition lifecycle fields. Inventory Cost/Trans. Value are not validated invoice-line COGS.',
             'Additional financial lifecycle sources required, not a different algorithm.',
             'Receivables/payments, allocations, general ledger recognition, realized COGS, currency and adjustment policies.'),
            ('T10','Tax/adjustment activity forecasting','Broader capability example','Feasible with Conditions',
             'Forecast reported adjustment counts or an approved tax reporting measure, without interpreting tax liability automatically.',
             'Future scoped note/event count or approved additive reported tax component per period',
             'Proposed only: distinct scoped note counts or separately approved line tax sums; respect CN/DN series, sign and filing/revision scope. Do not add overlapping invoice/GST representations.',
             'Time-series aggregate strategy if mature history and stable filing scope exist; current tax arithmetic is diagnostic analytics.',
             'Issuer/reporting-period/note type; H and tax-accounting meaning require owner approval.',
             '6-row notes have 6 scoped references; 276 nonempty larger-note rows have 243 scoped references, 33 repeats and 3 exact excess duplicates. Much larger-note coverage extends beyond assessment date.',
             'Lower priority; likely needs more mature production reporting history before forecasting.',
             'Filing versions, dates, note scope/sign, completeness, authority and enough mature reporting periods.'),
            ('T11','Hierarchical or segmented forecasting','Broader capability example','Feasible with Conditions',
             'Extend an approved aggregate forecasting target across stable business entities and hierarchies.',
             'Same approved additive/count outcome per validated hierarchy level',
             'No new target invented: inherit an approved outcome contract; aggregate only along approved many-to-one dimensions and compatible units.',
             'Pooled/per-series/hierarchical strategy requires individual-series coverage, cold-start and reconciliation evaluation; not guaranteed by global row count.',
             'Approved customer/product/territory/category hierarchy and time bucket.',
             'Customer/item and PTC/PCT classification candidates exist; 27 row-preserving raw-key directions remain conditional. Larger master duplicates and partial matching can expand or lose records.',
             'After aggregate target approval and entity-specific support assessment; not every segment can be forecast.',
             'Validated hierarchy, time-varying memberships, entity identity, unit consistency, enough history per series and treatment of new/discontinued entities.'),
            ('T12','Historical retrieval, aggregations and diagnostics','Analytics boundary example','Feasible with Conditions',
             'Answer questions about recorded historical data without claiming a future prediction.',
             'No prediction target; approved recorded counts/sums/rates or audit findings',
             'Read-only retrieval, grouping or rules at verified grain. Source structure/missingness/duplicate counts already reproducible; business SUM/COUNT semantics still need approval.',
             'SQL/dataframe aggregation or documented rules; ML is unnecessary for observed facts. Anomaly flags are diagnostic, not fraud probabilities or predictive accuracy.',
             'Requested historical scope; preserve raw-versus-diagnostic interpretations and unresolved dates.',
             '20 validated tables / 521 columns and existing quality/relationship calculations support descriptive evidence. Business measures remain conditional on authority, grain and date rules.',
             'Use now for evidence review; do not present a historical calculation as a forecast.',
             'Clarify metric, scope, time basis and join safety. Fraud/causal claims would need independent labels or intervention evidence.'),
            ('T13','Currency rate forecasting','Broader capability example','Not Currently Feasible',
             'Forecast a real exchange-rate process for a business currency/time basis.',
             'Future observed market/contract FX rate under an approved basis',
             'No production target from marked synthetic examples. Rate Month is a period; start/end applicability and rate fixing basis remain unapproved.',
             'Time-series methods cannot establish production validity from synthetic examples; no FX forecast or financial advice produced.',
             'Currency pair, fixing basis, timezone and requested horizon.',
             'Only 7 and 22 explicitly synthetic monthly rate records, overlapping two pairs/periods; some future periods and serial-date candidates.',
             'Obtain authorized real rate history if this capability is required.',
             'Production market/contract rates, fixing calendar, publication timestamps, currency convention and approved conversion policy.')]
        self.results['assessment_examples']=pd.DataFrame([dict(base,assessment_id=r[0],use_case=r[1],scope=r[2],
            feasibility=r[3],business_objective=r[4],proposed_target=r[5],target_definition_proposal=r[6],
            method_suitability=r[7],prediction_granularity=r[8],evidence_and_history=r[9],priority_recommendation=r[10],
            limitations_and_dependencies=r[11]) for r in examples])
        required_scope={
            'T01':('Owner-confirmed issuer/series/year scope for Invoice Num; persistent line IDs needed for line-based alternatives, not fabricated document identities.',
                   'Invoice Date as actual approved issuance event; Posting Date is an alternative order event and is not interchangeable.'),
            'T02':('Scoped Invoice Num plus stable line identity and scoped adjustment references; currency/entity scope must be confirmed.',
                   'Approved invoice/adjustment accounting event dates; ledger recognition timestamps are not established.'),
            'T03':('Historical stable customer identity, eligibility history, qualifying purchase event/document identity and approved invoice-party mapping.',
                   'Decision t, purchase time, eligibility intervals, availability/capture cutoff and full mature window t+H; these clocks are not supplied as a verified panel.'),
            'T04':('Approved product/service identity, unit, issuer/agency scope and stable source event/line identity; classification joins require separate approval.',
                   'Approved order/invoice event according to the chosen observed-demand proxy; actual demand/stockout and service completion histories are absent/unverified.'),
            'T05':('Product + warehouse + company and stable typed movement/snapshot identity; raw item group labels cannot be inherited without approval.',
                   'Actual posting/effective movement time, availability clock and authoritative stock as-of time; master update date is not a stock panel.'),
            'T06':('Stable historical decision and realized-outcome identity; no validated decision/realization pair has been supplied.',
                   'Actual decision time, each input availability time and realized outcome/maturity date; observed invoice date alone does not establish this contract.'),
            'T07':('Scoped order/invoice and lifecycle event identity, with original document links and full non-event follow-up.',
                   'Decision cutoff, actual status-transition or adjustment time, availability and complete outcome-window closure; current Status has no validated transition timestamp.'),
            'T08':('Scoped order/line or service, shipment/completion identity and partial-fulfilment references.',
                   'Actual versus promised dispatch/delivery/completion timestamps and censoring; Delivery Date role remains unconfirmed.'),
            'T09':('Party/invoice, payment allocation, recognition ledger and realized cost allocation identities; relevant finance lifecycle records not supplied.',
                   'Actual settlement/due/recognition/COGS effective and available times, depending on the requested outcome; no verified outcome clocks in supplied schema.'),
            'T10':('Issuer/year/series/type-scoped note reference and original invoice identity; stable line key required for line measures.',
                   'CreditDebitNote_Date, approved reporting period/revision and publication/maturity cutoff; month-without-year does not establish time scope.'),
            'T11':('Approved base-target identity plus historical entity/hierarchy version and membership scope.',
                   'Base target event/availability clocks plus hierarchy effective/available intervals; current master membership cannot be applied retrospectively without approval.'),
            'T12':('Depends on requested historical grain; use approved event/document identity for business counts, or source row position only for structural audit counts.',
                   'Requested historical event/as-of basis, or no time dimension for a source-structure audit; actual field roles must be distinguished.'),
            'T13':('Currency pair + fixing basis + period/instant as an approved scope; supplied synthetic period keys are not production identifiers.',
                   'Rate Month, Start Date and End Date are synthetic period evidence; production fixing/publication time and calendar required.')}
        frame=self.results['assessment_examples']
        frame['required_identifier_scope']=frame.assessment_id.map(lambda x:required_scope[x][0])
        frame['required_date_and_availability_roles']=frame.assessment_id.map(lambda x:required_scope[x][1])
        frame['supporting_evidence_references']='feasibility_evidence/target_source_bindings.csv; feasibility_evidence/historical_date_coverage.csv; feasibility_evidence/document_context_evidence.csv; feasibility_evidence/categorical_evidence.csv; dataset_relationship_report.md; ../data_quality/data_quality_report.md'

    def bindings(self):
        # Explicit review citations, not runtime column assumptions or question mappings.
        examples = {
            'invoice': ('Sales Invoice Details.xlsx','Sheet1'),
            'large_invoice': ('Sales Invoice Details 1.xlsx','Sheet1'),
            'order': ('Sales Order Report 1.xlsx','Sheet1'),
            'large_order': ('Sales Order Report 2.xlsx','Sheet1'),
            'gst': ('GSTR1_Invoice.csv','(CSV table)'),
            'credit': ('GSTR1_Credit_Debit_Note 2.csv','(CSV table)'),
            'customer': ('Customer Master Report 1.xlsx','Sheet1'),
            'item': ('Item Master Lists 1.xlsx','Item Lists'),
            'inventory': ('Inventory Audit Report as on 200327.xlsx','Sheet1'),
            'rate': ('Exchange Rate.xlsx','INR to JPY')}
        citations=[
            ('T01','invoice','event / document / scope',['Invoice Date','Invoice Num','TransType']),
            ('T01','order','Alternative order activity, not interchangeable with invoices',['Posting Date','SO No','Customer Code','Status']),
            ('T02','invoice','Proposed proxy measure; document total is not line-additive',['Taxable Value','Invoice Date','Invoice Num','Total Value','Invoice Total Include GST','Invoice Discount %','FreightAmt']),
            ('T02','gst','Reconciliation representation; never stack with invoice source',['Invoice_Date','Invoice_Number','Doc_Series','Doc_Series_Prefix','Doc_Series_Suffix','Item_Taxable_Value','Invoice_Value']),
            ('T02','credit','Adjustment scope/sign unresolved',['CreditDebitNote_Date','CreditDebitNote_Number','Type_Credit_or_Debit','Invoice_Number','Item_Taxable_Value','Credit_Debit_Note_Value']),
            ('T03','customer','Snapshot party attributes; no eligibility history',['CUSTOMER CODE','ACTIVE','INACTIVE','GSTIN']),
            ('T03','order','Possible positive event evidence; keys/time/purchase meaning unapproved',['Customer Code','Posting Date','SO No','Status']),
            ('T03','invoice','Party mapping cannot be assumed',['Customer Billing Name','Customer Billing GSTIN','Invoice Date','Invoice Num']),
            ('T04','invoice','Observed goods/service class and quantity/unit fields',['Invoice Date','Part Code SAP Code','Item Foreign Code','Item Type G or S','Quantity','UOM','Taxable Value']),
            ('T04','order','Booked detail proxy; status-at-time and blank items unresolved',['Posting Date','Item No','Quantity','Unit Price','Status']),
            ('T04','item','Candidate reference; current master is not historical dimension',['Item No.','foreign Code','Pricing unit','Item Group','Product Segment','Lead Time']),
            ('T05','inventory','Grouped movement and cumulative fields; not a validated stock panel',['Item No.','System Date','Posting Date','Document','Doc. Row','Whse','Quantity','Trans. Value','Cumulative Qty','Cumulative Value']),
            ('T05','item','Current extract quantities do not create past snapshots',['In Stock','Order to Supllier','Order by Customer','Minimum Inventory','Date of Udate']),
            ('T06','invoice','Observed amounts, no approved decision-time labels',['Quantity','Unit Price','Taxable Value','Invoice Date']),
            ('T07','order','Current state only',['Status','Posting Date','SO No']),
            ('T07','credit','Observed adjustments, not a cohort of negative outcomes',['CreditDebitNote_Date','Invoice_Number','Type_Credit_or_Debit']),
            ('T08','order','Actual versus planned event role unconfirmed',['Posting Date','Delivery Date','SO No','Item No']),
            ('T08','large_order','Invalid/future dates constrain duration labels',['Posting Date','Delivery Date']),
            ('T09','order','Payment terms do not prove settlement',['Payment Terms','Total (LC)']),
            ('T09','inventory','Movement valuation is not validated realized sales margin',['Cost','Trans. Value']),
            ('T10','credit','Scoped counts/measure proposal only',['CreditDebitNote_Date','CreditDebitNote_Number','Doc_Series','Doc_Series_Prefix','Doc_Series_Suffix','Type_Credit_or_Debit','IGST_Amount','CGST_Amount','SGST_Amount']),
            ('T11','item','Hierarchy candidates require approved scope/history',['Item No.','Item Group','Segment','Product Segment']),
            ('T11','invoice','Segment fields observed but memberships/time semantics unknown',['Territory','Sales Employee','Country','Part Code SAP Code']),
            ('T12','invoice','Historical quantities/values are analytics',['Invoice Date','Quantity','Taxable Value']),
            ('T13','rate','Explicit synthetic source',['Rate Month','Start Date','End Date','From Currency','To Currency','Exchange Rate (1 INR = ? JPY)'])]
        rows=[]
        for aid,key,role,names in citations:
            file,sheet=examples[key]
            source=self.sources[(self.sources.file==file)&(self.sources.worksheet==sheet)].iloc[0]
            for name in names:
                col=self.column(file,sheet,name)
                dates=self.dates[(self.dates.file==file)&(self.dates.worksheet==sheet)&(self.dates.column_number==col.column_number)]
                identifiers=self.ids[(self.ids.file==file)&(self.ids.worksheet==sheet)&(self.ids.column_number==col.column_number)]
                rows.append({'assessment_id':aid,'file':file,'worksheet':sheet,'actual_column_name':col.column_name,
                    'column_number':int(col.column_number),'review_role':role,'source_rows':int(source.rows_below_header),
                    'source_nonempty_rows':int(source.nonempty_rows),'source_columns':int(source.columns),
                    'nonblank_values':int(col.nonblank_values),'missing_values':int(col.missing_values),
                    'source_types':col.types_and_counts_json,
                    'date_evidence_reference':f'historical_date_coverage: {file} / {sheet} / column {col.column_number}' if len(dates) else 'Not a profiled date field',
                    'identifier_distinct':identifiers.distinct_values.iloc[0] if len(identifiers) else '',
                    'identifier_null_rows':identifiers.null_rows.iloc[0] if len(identifiers) else '',
                    'identifier_duplicate_excess':identifiers.duplicate_excess_rows.iloc[0] if len(identifiers) else '',
                    'identifier_prior_semantic_role':identifiers.role.iloc[0] if len(identifiers) else 'Not among prior identifier candidates',
                    'business_mapping_approved':False,'reference':'../data_inventory/validation/column_validation.csv; ../data_quality/source_tables.csv; identifier_relationship_matrix.xlsx'})
        self.results['target_source_bindings']=pd.DataFrame(rows)
        self.check('Every example has traceable actual columns',set(self.results['assessment_examples'].assessment_id)==set(self.results['target_source_bindings'].assessment_id))
        reviews=self.results['assessment_examples']
        dates=self.results['historical_date_coverage']
        for ix, review in reviews.iterrows():
            bindings=self.results['target_source_bindings']
            relevant=bindings[bindings.assessment_id==review.assessment_id]
            date_details=[]; identifiers=[]
            for binding in relevant.itertuples(index=False):
                found=dates[(dates.file==binding.file)&(dates.worksheet==binding.worksheet)&(dates.column_number==binding.column_number)]
                for d in found.itertuples(index=False):
                    date_details.append({'file':d.file,'worksheet':d.worksheet,'column':d.column,
                        'prior_calendar_min_NOT_approved':d.calendar_resolved_min_under_prior_convention,
                        'prior_calendar_max_NOT_approved':d.calendar_resolved_max_under_prior_convention,
                        'strict_partial_min_asof':d.strict_partial_history_min,'strict_partial_max_asof':d.strict_partial_history_max,
                        'distinct_days_asof':d.distinct_observed_days_asof,'distinct_weeks_asof':d.distinct_iso_weeks_asof,
                        'distinct_months_asof':d.distinct_observed_months_asof})
                if binding.identifier_distinct!='':
                    identifiers.append({'file':binding.file,'worksheet':binding.worksheet,'column':binding.actual_column_name,
                        'role':binding.identifier_prior_semantic_role,'business_key_approved':False})
            reviews.at[ix,'required_date_fields_and_coverage']=json.dumps(date_details,ensure_ascii=False)
            reviews.at[ix,'identifier_candidate_evidence']=json.dumps(identifiers,ensure_ascii=False)
            reviews.at[ix,'available_observation_frequency']='Event/detail or snapshot extracts, not an approved regular panel; daily/ISO-week/month timestamp support is diagnostic only. Inspect coverage per actual date field; complete business cadence is unconfirmed.'
            reviews.at[ix,'required_source_tables']=json.dumps(relevant[['file','worksheet','source_rows','source_columns']].drop_duplicates().to_dict('records'),ensure_ascii=False)

    def requirements(self):
        rows=[
            ('Business metric contract','All predictive requests','NOP process owner','Decide the intended outcome, unit, scope, event, population and cost of error; sales may mean orders, invoices, shipped units or value.','Open','Column names alone do not establish the outcome.'),
            ('Decision horizon and cadence','All predictive requests','NOP process owner','Specify H, lookback, decision frequency and usable lead time; no requested horizon has been supplied.','Open','Choose validation only after H and decision clock are defined.'),
            ('Source production authority','All source-dependent tasks','Source system owners','Verify real versus synthetic/sample data, extraction filters, company/issuer and approved authoritative version.','Open','Two rate sheets and reference customer list explicitly synthetic; additional example-domain indicators.'),
            ('Date and century rules','All temporal tasks','Source owners','Approve source/field-specific DMY/MDY, century, epoch and invalid-date handling; keep original values and lineage.','Open','203455 ambiguous / 28 impossible / 14949 serial candidates; small order dates depend on century convention.'),
            ('Observation cutoff and availability','All predictive tasks','Data operations','Supply extraction completion, ingestion/available time and actual-versus-planned event semantics.','Open','Future-dated records cannot be assumed realized history at 2026-11-02.'),
            ('Complete periods and missingness','All time series','Data operations / business owner','Distinguish no activity, out-of-scope, unobserved, closed/partial periods and ingestion gaps.','Open','Unobserved dates/months in partial coverage are not business zeros.'),
            ('Stable invoice/document scope','Count/value forecasting','ERP owner','Confirm issuer/year/series and persistent line IDs; require consistent document date and party within scope.','Open','Small invoice has 234 internally consistent references; still no approved business PK.'),
            ('Sales-order scope','Order-driven tasks','ERP owner','Explain reused SO numbers and validate composite scope/line identity upstream.','Open','275 of 299 raw small SO groups span multiple customer codes; 278 vary Posting Date.'),
            ('Duplicate/extract precedence','All quantitative targets','Data owner','Confirm repeated line legitimacy, 3 exact duplicates, 972 payload candidates and overlap precedence before any removal/union.','Open','No deduplication authorized; source payload agreement is not a document key.'),
            ('Additive monetary measure','Value forecasting','Finance owner','Approve taxable/gross/net basis, currency, freight, discount, rounding, adjustment signs and posting/recognition event.','Open','Repeated Invoice Total Include GST is not additive; arithmetic exceptions remain.'),
            ('Units and demand semantics','Product/service forecasts','Sales / inventory owners','Approve UOM/pricing units, goods/service metric and cancellations/returns; observed sales is not unconstrained demand.','Open','Manual UOM; 14 small service invoice lines; missing product codes may be service-like.'),
            ('Historical customer crosswalk','Customer-level tasks','Master data owner','Stable account/party mapping over time including shared GSTINs and changed codes.','Open','Invoice billing name/GSTIN does not establish customer-master FK.'),
            ('Historical eligible customer cohort','Propensity / churn','CRM owner','Eligibility/activation/deactivation and observation start/end per customer at decision time.','Additional source required','Current ACTIVE/INACTIVE values cannot establish past eligibility.'),
            ('Positive and negative purchase outcomes','Propensity','CRM / transactions owners','Complete approved purchase events plus full no-purchase observation windows; preserve censored labels as unknown.','Additional evidence/source required','40 small-order customer codes all occur in small master; no defensible negative panel supplied.'),
            ('Label maturity and censoring','Supervised/event-time tasks','Business / data operations','Define outcome window, reporting delay, maturity rule and censoring; purge overlaps between train and validation.','Open','No approved decision cutoff, H or observation closure.'),
            ('Time-varying dimension history','Segmented prediction','Master data owner','Effective/available times for customer/product attributes and hierarchy changes.','Additional source required','Current master Date of Udate is not an attribute-history panel.'),
            ('Inventory group context','Stock forecasting','Inventory owner','Approve item-block reconstruction and document/warehouse/item movement scope.','Open','98104 large movement rows lack raw item code; no fill-down authorized.'),
            ('Inventory snapshots and movement ledger','Stock/stockout forecasts','Inventory owner','Authoritative product/warehouse as-of balances; typed signed movement events with lifecycle.','Additional source required','Grouped audits are not a confirmed regular stock snapshot panel.'),
            ('Replenishment and availability events','Stockout / latent demand','Supply chain owner','Purchase orders, actual receipts, reservations, availability/stockout/lost-sales and lead-time history.','Additional source required','Current master Lead Time and In Stock are not realized temporal outcomes.'),
            ('Actual fulfilment/service events','Delivery / duration','Operations owner','Promise revisions and actual dispatch/delivery/completion events, partial quantities and cancellations.','Additional source required','Delivery Date meaning unconfirmed; no verified actual completion field.'),
            ('Decision-time numerical examples','Unknown numeric regression','Business owner','Comparable decisions/quotes with as-of inputs and independently observed realized outcomes.','Additional source required','An observed amount is not automatically an admissible label for an earlier decision.'),
            ('Status transition history','Cancellation / adjustment risk','ERP owner','Event-time state transitions and mature non-event windows linked to scoped documents.','Additional source required','Current Status variations alone are insufficient future outcome labels.'),
            ('Settlement and recognition lifecycle','Cash flow / recognized revenue','Finance owner','Payments/allocations, due/settlement events, recognition ledger and realized COGS allocations.','Additional source required','Payment Terms, tax amounts and inventory costs do not identify these outcomes.'),
            ('Sufficient mature history','All forecasting','Data operations','Assess complete observations per series relative to H, seasonality, dynamics, folds and error-cost tolerance.','Open; may need more history','337 invoice lines are not 337 monthly observations; partial span is ten months.'),
            ('Approved joins and referential policies','Enriched tasks','Data / business owners','Use temporal many-to-one contracts with coverage and row/financial conservation; reject arbitrary detail-to-detail joins.','Open','Invoice/order SO-only 100188 to 402400 rows; GST/invoice document join 337 to 609.'),
            ('Production FX history','FX or cross-currency values','Finance / data owner','Approved currency convention, real rate history, fixing basis, publication timestamps and calendar.','Additional source required','Available 7/22 monthly rate examples explicitly synthetic.'),
            ('Error costs and evaluation acceptance','All prediction','Business owner','Specify appropriate metrics, decision utility, acceptable error and baseline comparison before any training.','Open','No forecast, accuracy, calibration or confidence metrics have been generated.'),
            ('Permissions and provenance scope','Future dynamic platform','Data governance','Enforce dataset/column authorization, approved lineage and immutable versioned target contracts.','Design requirement','Natural-language flexibility cannot bypass data access or business approval.'),
            ('Unseen request acceptance','Future dynamic platform','Product / data governance','Judge new requests by evidence and target contract, not a question allowlist or keyword/model mapping.','Design requirement','These report examples are not the permitted request universe.')]
        self.results['data_requirements']=pd.DataFrame([{'requirement_id':f'REQ-{i+1:03d}','requirement':r[0],
            'applies_to':r[1],'owner_to_confirm':r[2],'required_resolution':r[3],'status':r[4],
            'observed_evidence':r[5]} for i,r in enumerate(rows)])
        missing=[
            ('Eligibility/cohort history','Customer onboarding, eligibility start/end, historical inactive periods','Current customer master status is a snapshot; no verified historical cohort', 'Propensity/churn'),
            ('Event availability history','Ingestion/available timestamp and extraction closure','Event dates exist; transaction timestamps do not prove known-at-decision information','All prospective validation'),
            ('Actual fulfilment outcomes','Actual delivery/service completion and censoring','Delivery Date is unconfirmed planned/actual; no verified actual completion lifecycle','Duration/delay'),
            ('Financial lifecycle','Actual settlement, recognition and realized COGS','Payment Terms and inventory Cost are not those outcomes','Collections/recognized revenue/profit'),
            ('Stock availability history','Regular product/warehouse snapshots, typed movements and stockout/lost sales','Grouped inventory and current item stock cannot establish a balance/outcome panel','Inventory/unconstrained demand'),
            ('Decision/realization pairs','Historical decisions or quotes with realized outcomes','Invoice amounts are observed outcomes with no approved earlier decision snapshot','Supervised numerical prediction'),
            ('State transitions','Timestamped status/credit/cancellation lifecycle','Current Status and observed notes do not establish timed positive/negative outcome windows','Cancellation/adjustment classification'),
            ('Real production FX','Authorized observed currency fixing history','Only explicitly marked synthetic rate tables supplied','Production FX forecasts')]
        self.results['outcome_availability_audit']=pd.DataFrame([{'missing_requirement':r[0],'needed_evidence':r[1],
            'observed_schema_finding':r[2],'affected_capability':r[3],
            'absence_claim_scope':'Not identified or validated in all 521 inventoried columns/evidence; external business systems may contain it'} for r in missing])

    def architecture(self):
        capabilities=[
            ('Historical retrieval / aggregation','Observed facts within approved scope','SQL/dataframe grouping or documented arithmetic','Feasible with Conditions','No model needed; dates/units/authority/grain still govern business aggregates'),
            ('Descriptive quality diagnostics','Existing source/metadata counts','Reproducible read-only profiling','Feasible','Already verified source extents, missingness, raw duplicates and relationship fanout; this is analytics, not prediction'),
            ('Future aggregate count process','Mature scoped events over complete buckets','Time-series candidates and non-ML count baselines','Feasible with Conditions','Invoice activity is the least measure-dependent first candidate; no annual evidence from ten months'),
            ('Future additive numerical process','Approved additive amount/quantity and coherent time series','Time-series family chosen after diagnostics/validation','Feasible with Conditions','Entity/unit/currency and fiscal/sign semantics; no universal algorithm'),
            ('Unknown numerical outcome at decision time','Comparable historical input/outcome pairs and as-of availability','Supervised regression when labels are defensible','Not Currently Feasible','Observed amount columns do not establish retrospective decision examples'),
            ('Future categorical/propensity outcome','Eligible population, matured positive/negative windows','Classification or event-time family','Not Currently Feasible','No defensible negative purchase cohort or historical availability panel'),
            ('Duration / time-to-event','Actual timed events, origins and censoring','Event-time or numerical duration family','Not Currently Feasible','Actual completion/payment lifecycle unverified'),
            ('Hierarchical / multi-series forecasts','Approved shared target plus per-entity history and hierarchy','Per-series/pooled/hierarchical options, assessed empirically','Feasible with Conditions','Current crosswalks and memberships unapproved; global row counts do not establish series support'),
            ('Operational stock trajectories','Validated opening state and typed flows/as-of snapshots','Balance rules for known movements; predictive inputs only where uncertain','Not Currently Feasible','Grouped movement context, replenishment and stockout outcomes missing/unconfirmed'),
            ('Anomaly diagnostics','Approved rules or stable reference distribution','Rule-based or exploratory unsupervised diagnostics','Feasible with Conditions','A flag is not a fraud label, causal finding, probability or forecast confidence')]
        self.results['reusable_capability_assessment']=pd.DataFrame([{'capability_family':a,'data_contract_requirement':b,
            'method_family_not_fixed_algorithm':c,'feasibility':d,'limitation':e} for a,b,c,d,e in capabilities])
        architecture=[
            ('Request interpretation','Extract outcome intent, entities, metric/unit, time basis, horizon, grain, scope, filters and requested action from unseen language.','Versioned intent draft; preserve original request, ambiguity and unfilled fields','No anticipated-question list; resolve only material missing details.'),
            ('Authorized evidence discovery','Discover current schemas, types, grains, time/identifier/measure profiles, lineage, rights and approved relationships.','Versioned evidence catalogue with actual source/column bindings and validity times','Column-name resemblance is insufficient; new data triggers re-profiling and review.'),
            ('Semantic grounding / clarification','Bind requested meaning to supported fields and business definitions with traceable alternatives.','Proposed semantic bindings, evidence and minimal clarification request','No invented columns/outcomes or silent metric substitution.'),
            ('Target and observation contract','Specify outcome equation, entity/record grain, eligible population, event/availability clocks, H, label window/maturity, units/sign/currency, authority and permitted joins.','Human-reviewable versioned target contract independent of wording','Business-rule configurations are reusable semantic metadata, not question-to-model mappings.'),
            ('Evidence readiness / abstention gate','Check source authenticity, complete periods, temporal integrity, support, labels/cohorts, identifiers, leakage and join conservation.','Admissible / conditional / unsupported decision with blockers and required evidence','Unsupported or ambiguous requests yield limitations or necessary questions, never fabricated values/confidence.'),
            ('Task and strategy planning','Separate retrieval/SQL/rules, numerical forecasting, unknown-outcome regression, classification and other supported tasks.','Admissible strategy families and resource/business constraints','No single algorithm and no fixed question/model table; candidate suitability must follow the approved contract.'),
            ('Reusable preparation interface — future only','Honor the target contract with versioned, reusable preparation and point-in-time transformation components.','Lineage-preserving execution plan and fitted-transform boundaries','Not implemented or executed in this assessment; raw evidence stays immutable.'),
            ('Evaluation and candidate comparison — future only','Select time-respecting folds, baselines, appropriate error metrics/decision utility, calibration and interval diagnostics when relevant.','Auditable evaluation protocol and measured evidence before selection','No made-up performance; fit transforms only within training folds; protect final holdout.'),
            ('Inference and explanation — future only','Apply approved fitted artifacts to an authorized request and supported horizon/entity scope.','Prediction versus observed fact, units, as-of time, empirical uncertainty, lineage and limitations','Block extrapolation beyond evaluated scope and unknown entities without an approved policy.'),
            ('Monitoring, versioning and extension','Track freshness, schema/identity/semantic drift, target/availability changes, evaluation decay and access policy.','Registries of evidence/semantic contracts/components and monitored versions','New domains extend metadata/adapters/contracts; no rewrite of core or exhaustive question catalogue required.')]
        self.results['architecture_requirements']=pd.DataFrame([{'component':a,'required_capability':b,
            'contract_or_output':c,'guardrail':d,'implementation_status':'Assessment design only; not implemented'} for a,b,c,d in architecture])
        fields=[
            ('Outcome intent','Observed retrieval versus future/unknown outcome; do not relabel analytics'),
            ('Business measure','Approved equation, source fields, dimensional units and aggregation'),
            ('Entity and record grain','Observation entity, scoped IDs and stable event/line identity'),
            ('Population','Eligibility, exposure, entry/exit and censoring'),
            ('Event clock','Business date/time role, timezone/calendar and effective scope'),
            ('Availability clock','When each input/outcome was actually knowable; extraction watermark'),
            ('Decision cutoff','Explicit t and data snapshot/version available at t'),
            ('Prediction horizon','Business-supplied H and usable decision lead time'),
            ('Observation / label window','Outcome interval, reporting delay and maturity'),
            ('Lookback and granularity','Allowed past interval, bucket, frequency and hierarchy'),
            ('Outcome positivity/negativity','Event, non-event, missing and censored definitions'),
            ('Additivity and unit policy','Quantity/unit, currency, signs, tax/freight/discount/returns'),
            ('Coverage / zero policy','Missing, out of scope, no activity, partial and complete periods distinguished'),
            ('Authority and provenance','Source version, production status and extraction filters'),
            ('Join contract','Approved semantic/temporal cardinality, coverage, null and expansion rules'),
            ('Validation protocol','Chronological folds, label maturity, baseline, leakage checks and final holdout'),
            ('Decision utility','Appropriate evaluation metrics, business error costs and acceptance rules'),
            ('Permissions / limitations','Authorized bindings, unsupported scope, new entity and extrapolation policy')]
        self.results['target_contract_requirements']=pd.DataFrame([{'contract_field':a,'required_definition':b,
            'status':'Required design field; no production target contract approved'} for a,b in fields])

    def quality_and_risk(self):
        carry=read_csv(self.out/'quality_carry_forward.csv')
        carry['feasibility_status']='Still unresolved; feasibility does not approve treatment or upgrade source validity'
        self.results['unresolved_issue_summary']=carry
        issues=self.issues.copy()
        def impact(r):
            text=' '.join(str(r[c]) for c in ['affected_column','rule','potential_business_impact']).casefold()
            if 'date' in text or 'chronolog' in text: return 'May invalidate event clock, horizon or history/label maturity; source-specific approved interpretation required.'
            if any(x in text for x in ['duplicat','identifier','match','link','referential']): return 'May duplicate target mass, lose entity observations or conflate scopes; approved identity/grain/join contract required.'
            if any(x in text for x in ['financial','tax','quantity','numeric','amount','unit','price']): return 'Target additivity, unit or accounting meaning may be unvalidated; do not treat field presence as valid outcome.'
            if 'synthetic' in text:return 'Production representativeness and authority are unconfirmed; sample results cannot establish production feasibility.'
            return 'Requiredness, applicability or semantic consistency must be confirmed for each target contract; no automatic imputation, correction or exclusion.'
        issues['prediction_feasibility_impact']=issues.apply(impact,axis=1)
        self.results['unresolved_issue_dependencies']=issues
        self.check('Prior issue register preserved in full',len(issues)==424 and list(issues.columns[:len(self.issues.columns)])==list(self.issues.columns))
        relations=self.relationships.copy()
        relations['prediction_dependency_note']=np.where(relations.predicted_excess_left_rows>0,
            'Direct enrichment can repeat target/financial quantities; do not use without new grain/line allocation approval.',
            'No current fanout does not approve source identity, point-in-time availability, coverage or future uniqueness.')
        self.results['relationship_dependency_evidence']=relations
        leakage=[
            ('Current state as historical feature','Status / ACTIVE / INACTIVE / current master stock','Post-outcome or future updates can encode label information.','Require historical state effective/available at t; current status cannot be retrospectively treated as known.'),
            ('Future or planned events','Future Invoice Date, Posting Date, Delivery Date and synthetic rates','Future/planned entries can be mistaken for realized history.','Use source-supported actual/known-at-time roles; separate business event, planning and availability clocks; do not delete source rows.'),
            ('Outcome arithmetic in predictors','Price, quantity, taxable/base and tax totals','Target components can trivially reconstruct an amount instead of predicting an unknown outcome.','Confirm which values are available at the decision; deterministic arithmetic belongs in analytics.'),
            ('Cross-export and duplicate leakage','Overlapping invoice/GST and duplicate signatures','Same event can enter training and test or be counted twice.','Approved lineage/event identity across splits; group related records while preserving temporal order; no blind random line split.'),
            ('Label-window overlap','Customer/doc outcomes over (t,t+H]','Training labels may use events after validation decision time.','At fold cutoff c, require training outcome windows and reporting lag matured by c; purge/embargo as necessary.'),
            ('Retrospective customer eligibility','Current master and missing transactions','Missing events are wrongly assigned negative labels.','Eligibility and complete capture for entire window required; unknown/censored windows stay unknown.'),
            ('Future dimension joins','Master classifications and synthetic reference lists','Latest attributes can reveal future entity state.','Approved many-to-one effective/available-time join; do not fill historical dimensions from latest state automatically.'),
            ('Global preprocessing / selection','Transforms, imputation, features, hierarchy or algorithm tuning','Future distributions or holdout outcomes contaminate fitting.','Fit on each training fold only; compare candidates within development folds; keep final chronological holdout untouched.'),
            ('Artificial continuity / zeros','Gaps and unobserved bucket/entity periods','Zero-filled missing capture creates fabricated negative outcomes and demand troughs.','Approve business calendar and coverage first; missing is not zero.'),
            ('Current financial totals','Document total repeated on lines, credit notes and final adjustments','Post-decision settlements/adjustments or repeated totals distort outcomes.','Approved line/document measure, revision cutoff, sign and target maturity before aggregation.'),
            ('Short history / unsupported seasonality','Ten-month partial small invoice span and sparse segments','Many lines create misleading confidence about temporal observations.','Compare fold/H/season support at target grain; request more mature history where validation cannot be honest.')]
        self.results['leakage_and_validation_controls']=pd.DataFrame([{'risk':a,'affected_evidence':b,'potential_leakage':c,
            'required_chronological_control':d,'status':'Required; not implemented or validated through model training'} for a,b,c,d in leakage])
        self.results['propensity_outcome_audit']=pd.DataFrame([
            {'element':'Positive purchase evidence','status':'Candidate events only','evidence':'Order and invoice references exist; order placement versus qualifying purchase must be approved.',
             'required_action':'Confirm purchase event and customer mapping, not just repeated customer IDs.'},
            {'element':'Historical negative outcomes','status':'Not established','evidence':'No verified eligible-and-fully-observed no-purchase panel; blank/zero quantities and absent transactions are not negatives.',
             'required_action':'Obtain eligibility, complete event capture and mature outcome windows before label construction.'},
            {'element':'Defensible prediction window','status':'Not supplied','evidence':'No approved t/H, extraction closure or label-reporting delay.',
             'required_action':'NOP must define decision cadence, future window, horizon and maturity rule.'},
            {'element':'Customer risk set','status':'Not historical','evidence':'Small master has 40 codes, and all 40 appear among 1098 small-order rows; current master status supplies no past eligibility.',
             'required_action':'Obtain historical entry/exit/activity and complete follow-up; do not label other-master unmatched accounts as nonpurchasers.'},
            {'element':'Entity identity','status':'Unapproved','evidence':'135 ID candidates remain unconfirmed; invoice party mapping and SO scope unstable.',
             'required_action':'Approve scoped customer and event identity before partitioning windows.'},
            {'element':'Features at decision','status':'Availability history absent','evidence':'No approved availability timestamps or prior-state snapshots.',
             'required_action':'Specify point-in-time admissible inputs; no feature engineering in this assessment.'}])

    def integrity(self):
        rows=[{'path':p,'sha256_before':h,'sha256_after':sha(self.root/p),'unchanged':sha(self.root/p)==h}
              for p,h in self.baseline.items()]
        self.results['preserved_input_integrity']=pd.DataFrame(rows)
        self.check('All sources, previous reports, notebooks and implementations unchanged',
            bool(self.results['preserved_input_integrity'].unchanged.all()),len(rows))

    def compare(self,expected,actual,name):
        expected=expected.fillna('');actual=actual.fillna('')
        self.check('Shape/columns '+name,expected.shape==actual.shape and list(expected.columns)==list(actual.columns))
        for col in expected.columns:
            for a,b in zip(expected[col],actual[col]):
                if isinstance(a,(int,float,np.integer,np.floating)) and not isinstance(a,(bool,np.bool_)):
                    try: good=not isinstance(b,(bool,np.bool_)) and math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-7)
                    except (ValueError,TypeError):good=False
                else:good=str(a)==str(b)
                if not good:raise AssertionError((name,col,repr(a),repr(b)))

    def export(self):
        books={
            'prediction_target_mapping.xlsx':['assessment_examples','target_source_bindings','historical_date_coverage',
                'reusable_capability_assessment','source_grain_evidence','independent_grain_probes','measure_evidence',
                'identifier_evidence','relationship_dependency_evidence','financial_rule_evidence','categorical_evidence','document_context_evidence'],
            'prediction_data_requirements.xlsx':['data_requirements','outcome_availability_audit','architecture_requirements',
                'target_contract_requirements','propensity_outcome_audit','leakage_and_validation_controls',
                'unresolved_issue_dependencies','unresolved_issue_summary','source_authority','source_authenticity',
                'preserved_input_integrity','schema_evidence','date_coverage_diagnostics']}
        for name,frame in self.results.items():
            frame.to_csv(self.evidence/f'{name}.csv',index=False,encoding='utf-8-sig',float_format='%.15g')
            self.compare(frame,read_csv(self.evidence/f'{name}.csv'),'New CSV '+name)
        for filename,names in books.items():
            with pd.ExcelWriter(self.out/filename,engine='openpyxl') as writer:
                for name in names:self.results[name].to_excel(writer,sheet_name=name[:31],index=False)
                for ws in writer.book.worksheets:
                    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
                    for row in ws:
                        for cell in row:
                            if isinstance(cell.value,str):cell.data_type='s'
                    for column in ws.columns:
                        ws.column_dimensions[column[0].column_letter].width=min(65,max(18,len(str(column[0].value))+2))
            with pd.ExcelFile(self.out/filename) as book:
                self.check('New workbook sheet manifest '+filename,book.sheet_names==[n[:31] for n in names])
                for name in names:
                    frame=book.parse(name[:31],keep_default_na=False)
                    self.compare(self.results[name],frame,'New Excel '+name)
                    self.export_checks.append({'workbook':filename,'sheet':name[:31],
                        'evidence_csv':f'feasibility_evidence/{name}.csv','rows':len(frame),'columns':len(frame.columns),
                        'complete_cell_content_verified':True})

    def report(self):
        example=self.results['assessment_examples']
        coverage=self.results['historical_date_coverage']
        dateview=coverage[['file','worksheet','column','calendar_resolved_min_under_prior_convention',
            'calendar_resolved_max_under_prior_convention','century_dependent_cells_including_ambiguous',
            'strict_partial_history_min','strict_partial_history_max','distinct_observed_months_asof',
            'calendar_resolved_beyond_asof','explicit_full_year_or_native_beyond_asof']]
        report=f'''# Business prediction requirements and target feasibility

Assessment date and diagnostic cutoff: **{AS_OF.isoformat()}** (Asia/Calcutta date; no source event timezone is assumed). Scope: 17 original files, 20 tables, 521 columns, 37 date-related fields and 135 identifier candidates. This is an assessment, not a prediction platform implementation. No source joins, cleaning, duplicate removal, label/target values, features, training, forecasts or forecasting metrics were produced.

## Executive decision

There is **no unconditionally production-ready prediction target**. Sales activity, an approved invoiced-value proxy, selected product demand proxies, reporting activity and hierarchical extensions are **Feasible with Conditions**. Customer propensity, stock/stockout forecasts, actual delivery outcomes, decision-time numerical regression, cancellation risk, settlement/recognized revenue/margin and production FX forecasts are **Not Currently Feasible** under the supplied evidence. A descriptive evidence audit is already feasible and is not ML prediction.

**First prediction capability to develop, after business/data gates:** a reusable aggregate event-count forecasting capability, initially evaluated against scoped invoice-document activity in an authoritative single invoice source. The small invoice export has 337 detail rows / 234 full invoice references, with constant observed billing party/date/document total within each reference and matching GST representation. This candidate avoids monetary-unit arithmetic and order/invoice joins, but the 10-month partial date span, 107 ambiguous dates, extraction closure, scope and production provenance must be resolved. It cannot establish annual seasonality, performance, an approved horizon or complete observation periods. More mature history is needed if honest horizon/fold evaluation cannot be supported. Invoice activity must not be silently substituted for booked orders, shipped units or recognized revenue.

The longer small-order date span does **not** justify choosing order-count forecasting first: 275 of 299 raw SO-number groups span multiple customer codes, 278 vary Posting Date and its dates use an unapproved two-digit-year convention. These are scope/representation conflicts, not a confirmed count of erroneous business documents. No winner is selected by newest/largest filename.

## Classification meaning and task boundary

- **Feasible:** the exact bounded task has directly verified evidence and no unresolved prerequisite for that stated scope; here this applies to existing structural/descriptive diagnostics, not production prediction.
- **Feasible with Conditions:** observable ingredients support a precise candidate after listed gates; this is not model readiness, sufficient history certification or permission to resolve data issues.
- **Not Currently Feasible:** a defensible outcome, population, temporal availability, required state/history or production evidence is missing/unverified. A more complex algorithm cannot supply missing labels or semantics.

The five requested use cases below are assessment examples. Additional examples and capability families explore the evidence boundary; they are not a fixed supported-question catalogue, question-to-model table or manually programmed application responses. The future system must judge previously unseen requests against evidence and an approved target contract.

## Requested business use cases and broader examples

{markdown_table(example,['assessment_id','use_case','feasibility','proposed_target','evidence_and_history','priority_recommendation'])}

Complete business objectives, proposed equations, source columns, date/key needs, scope, observation frequency, horizon requirements, limitations and method suitability are in [prediction_target_mapping.xlsx](prediction_target_mapping.xlsx), its `assessment_examples`, `target_source_bindings` and `historical_date_coverage` sheets. Formulas are proposed definitions, not generated target columns. All 13 examples have verified actual-column citations. Horizons have not been supplied by NOP; H, lead time, bucket and update cadence remain requirements rather than defaults.

### What can be generalized

{markdown_table(self.results['reusable_capability_assessment'],['capability_family','data_contract_requirement','method_family_not_fixed_algorithm','feasibility','limitation'])}

Schema/quality/lineage discovery, grain/identity evidence, point-in-time contracts, readiness checks, validation protocols and component interfaces can generalize. Business meanings, eligibility, time roles, units, signs, source authority, event identities and outcome windows require target-specific approved semantic configurations. Those configurations describe data and business meaning, not anticipated questions or a model chosen by keyword.

## Actual source evidence and historical suitability

All 20 tables retain the meanings and uncertainties in [granularity evidence](dataset_granularity_report.xlsx). Customer/item masters are current reference candidates, not historical eligibility or attribute panels. Sales orders and invoices contain detail rows, tax exports are reporting representations, inventory is a grouped mixed-grain report, and rate examples are explicitly synthetic. Country/product classifications are references, not predictive outcome histories. Source rows are not independent time observations, invoice totals are repeated at line grain and similar schemas do not establish identical grain.

### Dates and observation counts

The following coverage is **timestamp evidence only**, not a cleaned time series or a count of supervised examples. Calendar-resolved ranges from prior validation can depend on a two-digit-year convention. A separate conservative view includes only native/full-year, one-interpretation dates at or before {AS_OF.isoformat()}, excluding century-dependent tokens from that view without changing or discarding any source records. ISO strings already present in date evidence are read; raw source dates are not reinterpreted. Neither view proves actual-versus-planned meaning, completeness, decision-time availability or production legitimacy.

{markdown_table(dateview,list(dateview.columns))}

- Small invoice and GST invoice `Invoice Date` / `Invoice_Date`: 337 cells each; 107 ambiguous, 230 full-year calendar-resolved, with partial 2025-12-21 to 2026-09-13 coverage over 10 observed months. These are corresponding source representations, not 674 new line observations or 20 months of history.
- Small order `Posting Date`: 1,098 cells; 417 ambiguous. Prior calendar resolution gives a partial 2024-04-13 to 2026-09-19 range, but every date depends on the century convention. Zero rows in the conservative full-year view does not mean no source dates exist. Raw SO grouping is also unstable.
- Large invoice ` Invoice Date `: 100,183 nonblank cells, 33,782 ambiguous and 2,996 possible serial candidates; its partial calendar range reaches 2027-03-20. Large order posting/delivery fields also extend beyond the assessment cutoff; a future delivery date may be a plan, not an observed outcome.
- Period labels such as rate `2027-03` remain monthly periods. Item `Date of Udate` is an update attribute, not a purchase/stock observation date. Revision month without a year cannot establish event history.
- Daily, ISO-weekly and monthly distinct timestamp support is recorded per field in the workbook, with both partial spans and unobserved months. This does not authorize daily/weekly/monthly target aggregation. Approved calendars and capture completeness are required before interpreting an empty bucket as zero. No zero filling or aggregation of business targets occurred.
- Sufficiency depends on complete mature observations at the requested entity/frequency relative to H, validation folds, seasonality and decision utility. There is no universal minimum-row threshold. Ten partial months do not establish annual seasonality; hundreds of thousands of lines over a short or future-dated interval do not establish long production history.

## Identifiers, grain and join dependencies

Existing evidence: [relationship report](dataset_relationship_report.md), [identifier and relationship matrix](identifier_relationship_matrix.xlsx), [logical business model](data_model_diagram/README.md). All 148 candidate comparisons and 69 controlled joins retain their original conditional status; no business keys/relationships are approved by this assessment.

- Invoice/order SO-only join: **100,188 -> 402,400 rows**, quantity **363,277 -> 1,472,651**. This is row replication, not growth or extra demand. Do not enrich targets through that direct detail join.
- Small GST/invoice scoped document join: **337 -> 609 rows**. Scoped invoice + raw item description aligns **337 -> 337**, with matching six numerical line fields in these specific extracts. Description is not an upstream stable line key. Use GST as reconciliation evidence, not extra sales rows; no permanent merge is performed.
- Large-order to large-customer-master raw lookup: **100,286 -> 100,898 rows**; even a master lookup can distort targets. The 27 current raw row-preserving directions still need scope, authority, completeness and temporal approvals.
- Independently rereading the small order and small invoice sources reproduces the reported within-key attribute variations. Small invoice 234 references have no observed party/date/document-total variation. Small order raw SO number cannot be treated as a globally scoped order key; adding customer/product without approval is not sufficient identity evidence.
- Inventory has **98,104 movement rows without populated raw item code** in the large audit; no forward fill is authorized. Stock movements, opening balances and cumulative fields must not be mixed into an additive demand/stock target.

For the first count candidate, no cross-source business join is necessary. Value, goods demand, customer features, adjustments and hierarchical extensions require progressively more semantic/identity/measure evidence. Targets that can be supported in a single approved source should not acquire avoidable join dependencies.

## Customer propensity: explicit outcome audit

{markdown_table(self.results['propensity_outcome_audit'],['element','status','evidence','required_action'])}

The proposed label contract is only a specification: at a decision time t, an eligible customer has a positive label only after an approved purchase in (t,t+H]; a negative label requires verified full-window capture and continued eligibility with no qualifying purchase. Customers with immature follow-up, censored eligibility, missing capture or unresolved identity remain unknown. No label values or fabricated nonpurchasing records were created. Zero/negative quantities, current inactive flags, cancellation lines and unmatched master accounts are not purchase-negative examples.

## Analytics, prediction and leakage

Historical SELECT/COUNT/SUM and observed price/tax arithmetic are analytics or rules. They can be sufficient for a historical question but cannot answer a request for an unknown future value. Forecasting uses an approved ordered process; regression predicts an unknown numerical outcome with comparable historical examples; classification needs defensible outcomes/cohorts. Anomaly flags are diagnostics without validated labels and cannot be called fraud probabilities. Inventory balance rules can plan known flows, but forecast uncertainty requires supported uncertain inputs.

{markdown_table(self.results['leakage_and_validation_controls'],['risk','potential_leakage','required_chronological_control'])}

For a future chronological evaluation, first approve the target contract and snapshot/availability history. At each cutoff c, only inputs available by c and training labels fully matured by c may be used. Evaluate future blocks of the requested H, allow reporting delay, purge overlapping label windows and preserve a final untouched chronological holdout. Fit all transforms and candidate selection within training/development folds. Cross-export duplicates and related lines must not leak between splits; related-event grouping must preserve temporal order. Compare appropriate naive/rule/seasonal baselines only if supported. Metrics, calibration and intervals must be measured on a real approved evaluation, never invented. No folds, features, training or accuracy values were generated now.

## Unresolved findings and new clarification needs

All **424 prior issue entries** are copied into the requirements evidence with their original identifiers, sources, columns, severity, counts and unresolved status, plus their feasibility impact. The 203,455 ambiguous dates, 28 impossible dates, 14,949 serial candidates, 3 excess exact duplicates and 972 payload-duplicate candidates remain intact. Financial exceptions, synthetic indicators, unnamed PCT_NOPJ field and 135 unconfirmed ID candidates are not resolved. Counts overlap and are not a unique count of defective records. Century dependence, future-versus-realized dates, extraction completeness and raw SO scope make these issues directly relevant to target feasibility.

The NOP team needs to confirm metric meanings; company/issuer/time scope; production provenance and authoritative versions; dates/century/epoch; current versus historical status; stable document/line/customer/product IDs; complete periods/zeros; units/currency/financial rules; observation windows/H; service units; inventory movement layout and snapshot meaning. No business horizon, valid target, key approval or relationship approval is inferred from this report.

Missing lifecycle evidence is documented in [prediction_data_requirements.xlsx](prediction_data_requirements.xlsx). Propensity requires eligibility and complete outcomes; actual delivery needs fulfilment events; stock/latent demand needs availability/receipts/stockout history; cash/recognized revenue/profit need settlement/ledger/cost allocation history. More mature real transaction history may also be required for the first invoice-count candidate. Whether these fields exist in NOP systems outside the supplied 521 columns must be established with owners; absence here is not a claim that they do not exist in the business.

## Technology-independent future architecture

```mermaid
flowchart TD
    R[Unseen authorized natural-language request] --> I[Outcome / entity / metric / time / H / grain intent draft]
    I --> E[Current authorized schema, profile and provenance evidence]
    E --> C[Grounded versioned business target and observation contract]
    C --> G[Semantic, quality, history, label, leakage and join readiness gates]
    G -->|unsupported or material ambiguity| Q[Explain missing evidence / request only necessary clarification]
    G -->|historical task supported| A[Read-only retrieval / aggregation / approved rules]
    G -->|predictive task admissible| S[Evidence-dependent strategy families and validation plan]
    S --> P[Future approved reusable preparation and candidate evaluation components]
    P --> V[Measured comparison, baseline checks and protected chronological holdout]
    V --> O[Future versioned inference with lineage, limits and empirical uncertainty]
    O --> M[Freshness, drift, scope and outcome monitoring]
    M --> E
```

{markdown_table(self.results['architecture_requirements'],['component','required_capability','contract_or_output','guardrail'])}

The contract must include the fields in `target_contract_requirements`; all predictive bindings remain unapproved. A future new dataset must be profiled and grounded without changing a question list; a new request uses the same contract/gates, with admissible method families determined by outcome/observation structure and evaluated evidence. Additional algorithms/adapters can extend components without rewriting the system. Semantic metadata and owner-approved target-specific settings are necessary; fixed column names, anticipated scenarios, manually scripted answers and single-model routing are not an acceptable platform design. An automated schema profile does not automatically approve a business relationship.

No interpreter, selector, training pipeline, prediction API or implementation of this architecture is created. The analysis code only reads evidence, performs source grain checks and renders assessment documents. The illustrative assessment rows are not executable prediction instructions.

## Recommended next activity

Conduct an evidence-led NOP requirements and source-owner review. Agree on one target/observation contract and the minimal blockers before requesting approval for preparation. Prefer aggregate invoice-event count as the first *conditional technical candidate*, because it avoids monetary-unit rules and optional joins; confirm whether it meets the actual business objective before selecting it. If the desired outcome is instead units, recognized revenue or propensity, retain that meaning and request its missing evidence rather than substitute a supported proxy silently. Establish production authenticity, source/date/key scope, complete mature history, H and acceptance criteria; acquire additional lifecycle/history sources where identified. Stop for approval before cleaning, consolidation, features or models.

## Deliverables and validation

- [Executed feasibility notebook](../../notebooks/04_business_prediction_feasibility.ipynb)
- [Prediction target mapping](prediction_target_mapping.xlsx)
- [Prediction data requirements](prediction_data_requirements.xlsx)
- [Assessment validation](feasibility_validation.json) and [notebook execution validation](feasibility_notebook_validation.json)
- Complete supporting tables are in `feasibility_evidence/`; [input preservation ledger](feasibility_evidence/preserved_input_integrity.csv) hashes original sources and all previous reports/notebooks/implementations.

Validation checks input CSV/workbook agreements, actual source/column references, all 37 date-field token totals and as-of partitions, all 13 illustrative assessments, complete 424-issue carry-forward, independently reread source grain, every cell of new CSV/Excel outputs and documentation links. Existing reports remain unchanged. Final execution results are recorded by the notebook validator after execution. Limitations are semantic/observation evidence and production readiness, not undisclosed generated forecasting metrics.
'''
        (self.out/'business_prediction_feasibility_report.md').write_text(report,encoding='utf-8')

    def run(self):
        self.load_evidence();self.date_coverage();self.source_probe();self.assessment_examples()
        self.bindings();self.requirements();self.architecture();self.quality_and_risk()
        self.integrity();self.export();self.report();self.integrity()
        validation={'assessment_date':AS_OF.isoformat(),'source_files':17,'source_tables':20,'schema_columns':521,
            'date_fields':37,'identifier_candidates':135,'illustrative_assessments':len(self.results['assessment_examples']),
            'capability_families':len(self.results['reusable_capability_assessment']),
            'issue_entries_carried_forward':424,'preserved_inputs':len(self.baseline),
            'all_inputs_unchanged':bool(self.results['preserved_input_integrity'].unchanged.all()),
            'prediction_targets_generated':0,'models_trained':0,'source_joins_performed':0,
            'prediction_engine_implemented':False,'read_or_validation_failures':0,
            'classification_counts':self.results['assessment_examples'].feasibility.value_counts().to_dict(),
            'checks':self.checks,'export_checks':self.export_checks,
            'limitation':'Conditional classifications are not approval or model readiness; histories/cohorts/horizons require business evidence.'}
        (self.out/'feasibility_validation.json').write_text(json.dumps(validation,indent=2,ensure_ascii=False),encoding='utf-8')
        print(f'Assessment complete: 20 tables; {len(self.results["assessment_examples"])} examples; {len(self.export_checks)} verified workbook sheets; prior inputs preserved.',flush=True)
        return self.results


def run(root=None):
    return FeasibilityAssessment(Path(root) if root else Path(__file__).resolve().parents[2]).run()


if __name__=='__main__':run()
