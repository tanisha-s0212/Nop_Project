"""Render and validate preparation specifications from immutable audit evidence.

Documentation tooling only: no cleaner, source join, feature builder, request
interpreter, training pipeline, model selector, inference backend or UI is built.
Actual file/field names are evidence citations; reusable component requirements
use semantic contracts and are not executable dataset-specific assumptions.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import nbformat
import numpy as np
import pandas as pd
from openpyxl import load_workbook


OUTPUT_NAMES = {'data_preparation_strategy.md','business_rule_register.xlsx',
                'data_cleaning_specification.xlsx','training_dataset_blueprint.xlsx',
                'preparation_specification_validation.json'}


def read_csv(path):
    return pd.read_csv(path,keep_default_na=False,encoding='utf-8-sig')


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def dump(value):
    return json.dumps(value,ensure_ascii=False,default=str)


def table_md(frame,columns):
    def clean(v):return str(v).replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']+
        ['| '+' | '.join(clean(v) for v in row)+' |' for row in frame[columns].itertuples(index=False,name=None)])


class PreparationSpecification:
    def __init__(self,root):
        self.root=Path(root).resolve();self.out=self.root/'reports/analysis'
        self.evidence=self.out/'preparation_evidence';self.evidence.mkdir(parents=True,exist_ok=True)
        self.results={};self.checks=[];self.export_checks=[]
        path=self.evidence/'input_manifest.json'
        if path.exists():self.baseline=json.loads(path.read_text(encoding='utf-8'))
        else:
            collision=[p.name for p in self.out.iterdir() if p.name in OUTPUT_NAMES]
            if collision:raise FileExistsError(f'Existing deliverables require review before replacement: {collision}')
            files=[p for p in (self.root/'reports').rglob('*') if p.is_file() and self.evidence not in p.parents and p.name not in OUTPUT_NAMES]
            files+=list((self.root/'notebooks').glob('*.ipynb'))
            files+=[p for p in (self.root/'dataset').rglob('*') if p.is_file()]
            files+=[p for p in (self.root/'src/data').glob('*.py') if p.name!=Path(__file__).name]
            self.baseline={p.relative_to(self.root).as_posix():sha(p) for p in files}
            path.write_text(json.dumps(self.baseline,indent=2),encoding='utf-8')
        self.check('Previous deliverables and sources match baseline',all((self.root/p).exists() and sha(self.root/p)==h for p,h in self.baseline.items()))
        readme=self.root/'README.md'
        before=self.evidence/'readme_link_baseline.json'
        if not before.exists():before.write_text(dump(re.findall(r'\]\(([^)]+)\)',readme.read_text(encoding='utf-8'))),encoding='utf-8')
        self.readme_links=json.loads(before.read_text(encoding='utf-8'))

    def check(self,name,condition,detail=''):
        self.checks.append({'test':name,'passed':bool(condition),'detail':str(detail)})
        if not condition:raise AssertionError((name,detail))

    def compare(self,a,b,name):
        a=a.fillna('');b=b.fillna('')
        self.check('Table shape '+name,a.shape==b.shape and list(a.columns)==list(b.columns))
        for col in a:
            for x,y in zip(a[col],b[col]):
                if isinstance(x,(int,float,np.integer,np.floating)) and not isinstance(x,(bool,np.bool_)):
                    try:good=not isinstance(y,(bool,np.bool_)) and math.isclose(float(x),float(y),abs_tol=1e-7,rel_tol=1e-12)
                    except (ValueError,TypeError):good=False
                else:good=str(x)==str(y)
                if not good:raise AssertionError((name,col,repr(x),repr(y)))

    def review_inputs(self):
        q=self.root/'reports/data_quality';i=self.root/'reports/data_inventory/validation'
        self.sources=read_csv(q/'source_tables.csv');self.columns=read_csv(i/'column_validation.csv')
        self.headers=read_csv(i/'header_validation.csv');self.issues=read_csv(q/'issue_register.csv')
        self.ids=read_csv(self.out/'identifier_profiles.csv');self.dates=read_csv(self.out/'feasibility_evidence/historical_date_coverage.csv')
        self.grain=read_csv(self.out/'dataset_granularity.csv');self.rels=read_csv(self.out/'relationship_candidates.csv')
        self.context=read_csv(self.out/'document_context.csv')
        self.numerical=read_csv(q/'numerical_quality.csv');self.duplicates=read_csv(q/'duplicate_analysis.csv')
        self.financial=read_csv(q/'financial_consistency.csv');self.missing=read_csv(q/'missing_values.csv')
        self.requirements=read_csv(self.out/'feasibility_evidence/data_requirements.csv')
        self.bindings=read_csv(self.out/'feasibility_evidence/target_source_bindings.csv')
        self.check('Evidence scope complete',len(self.sources)==20 and len(self.columns)==521 and len(self.issues)==424 and len(self.ids)==135 and len(self.dates)==37 and len(self.rels)==148)
        current={p.relative_to(self.root/'dataset').as_posix():p for p in (self.root/'dataset').rglob('*') if p.is_file()}
        reference=read_csv(q/'source_integrity.csv')
        self.check('17 source-file census matches validated source manifest',set(current)==set(reference.file) and len(current)==17)
        for r in reference.itertuples(index=False):self.check('Validated source unchanged '+r.file,sha(current[r.file])==r.sha256_after)
        reviewed=[]
        for rel in self.baseline:
            p=self.root/rel
            if rel.startswith('dataset/') or rel.startswith('src/'):continue
            kind=p.suffix.lower();detail=''
            if kind=='.csv':
                f=read_csv(p);detail=f'{len(f)} rows; {len(f.columns)} columns; parsed all rows'
            elif kind=='.xlsx':
                wb=load_workbook(p,read_only=True,data_only=False)
                try:
                    sizes={s:sum(1 for _ in wb[s].iter_rows(values_only=True)) for s in wb.sheetnames}
                    detail=dump(sizes)
                finally:wb.close()
            elif kind=='.ipynb':
                n=nbformat.read(p,as_version=4);nbformat.validate(n)
                code=[c for c in n.cells if c.cell_type=='code']
                errors=[o for c in code for o in c.get('outputs',[]) if o.output_type=='error']
                detail=dump({'code_cells':len(code),'executed_cells':sum(c.execution_count is not None for c in code),'stored_errors':len(errors),'rerun':False})
            elif kind=='.json':
                value=json.loads(p.read_text(encoding='utf-8-sig'));detail=f'Parsed {type(value).__name__}'
            elif kind=='.svg':ET.parse(p);detail='XML logical diagram parsed'
            elif kind=='.png':
                from PIL import Image
                with Image.open(p) as image:image.verify()
                detail='Image integrity verified'
            else:detail=f'{len(p.read_text(encoding="utf-8-sig"))} characters reviewed'
            reviewed.append({'path':rel,'format':kind,'review_method_and_scope':detail,'sha256':self.baseline[rel],'read_only':True})
        self.results['reviewed_artifacts']=pd.DataFrame(reviewed)
        # Cross-check primary workbooks, rather than trusting CSV labels alone.
        for file,sheets in [(i/'inventory_validation_evidence.xlsx',{'column_validation':self.columns}),
            (q/'data_quality_evidence.xlsx',{'issue_register':self.issues}),
            (self.out/'identifier_relationship_matrix.xlsx',{'identifier_profiles':self.ids,'relationship_candidates':self.rels}),
            (self.out/'dataset_granularity_report.xlsx',{'dataset_granularity':self.grain}),
            (self.out/'prediction_target_mapping.xlsx',{'historical_date_coverage':self.dates}),
            (self.out/'prediction_data_requirements.xlsx',{'data_requirements':self.requirements})]:
            with pd.ExcelFile(file) as b:
                for sheet,expected in sheets.items():self.compare(expected,pd.read_excel(b,sheet_name=sheet,keep_default_na=False),'Previous '+file.name+'/'+sheet)
        self.results['prior_requirements']=self.requirements.copy()
        self.results['date_evidence']=self.dates.copy();self.results['identifier_evidence']=self.ids.copy()
        self.results['duplicate_count_evidence']=self.duplicates.copy();self.results['financial_evidence']=self.financial.copy()

    def business_rules(self):
        # This register is a reviewed specification, never a business-question list.
        rules=[
            ('Governance','Immutable original sources and prior validated evidence','Confirmed project constraint','Never overwrite, recalculate or mutate sources; preserve lineage and hashes.','Current user instruction; preserved_input_integrity','Project/data owner','Raw input hashes and previous artifact hashes remain identical; source changes stop processing.'),
            ('Authorization','Specification only; no preparation execution','Confirmed project constraint','Document proposed rules now. Cleaning, data joins, features, training and inference require separately authorized work.','Current user instruction','Project owner','No prepared business data, labels, features or model artifacts are written.'),
            ('Architecture','No predefined business-question or scenario catalogue','Confirmed project constraint','Reusable operations bind authorized semantic/schema contracts; no fixed questions, question-dataset/model routes or universal dataset/model.','Mandatory architectural principle','Backend owner','Plans depend on approved outcome/input/model contracts; unknown requests are not denied merely for unseen wording.'),
            ('Interface','Backend-only; external LLM/MCP integration boundary','Confirmed project constraint','Other developer owns language interpretation/MCP integration. Specify structured objective/clarification/result contracts; create no UI/chatbot/interpreter here.','Current user instruction','Backend and integration owners','Backend validates grounded contracts and returns structured evidence/status; no UI or manually scripted business answers.'),
            ('Authority','Production source and version precedence','Unresolved business decision','Approve issuer/company, extraction scope, authenticity, history and authoritative version. File size, suffix and apparent recency cannot select it.','source_authority / source_authenticity; prior feasibility report','ERP/source owners','Authority decision versioned for the particular target/source scope; no automatic union or latest-file winner.'),
            ('Sales','Meaning of sales and qualifying event','Unresolved business decision','Choose order booking, invoice issuance, shipped/fulfilled units or an approved financial metric explicitly; do not substitute another meaning.','prior_requirements; source_grain_evidence','NOP sales/process owner','Metric definition cites actual event, identifiers, status policy, date, unit, scope and denominator where relevant.'),
            ('Sales','Cancellation, return and adjustment treatment','Unresolved business decision','Approve lifecycle/sign/void policy and information available at decision time; current status cannot retrospectively define past known state.','Status categories / missing lifecycle evidence','NOP sales and finance owners','Cohort and target mass reconcile with approved lifecycle; no hindsight filtering or automatic removal.'),
            ('Identity','Customer and party namespace','Unresolved business decision','Approve customer/account/GST-registration scope and historical crosswalk; names or GSTIN alone are not guaranteed account identifiers.','135 identifier profiles; customer/party candidate relationships','Master data owner','Nulls, collisions, duplicate groups, scope and effective/available dates meet an approved identity contract.'),
            ('Identity','Product, service and foreign-code namespace','Unresolved business decision','Approve item/manufacturer/agency/service codes and versioned mappings; category/HSN/description are not unique product identities.','identifier_evidence; classification tables; unnamed field issue','Master data / product owners','Crosswalk is functional where required, scoped and effective-dated; no fuzzy/name-only auto joins.'),
            ('Identity','Document scope and stable line identity','Unresolved business decision','Confirm issuer/year/series and persistent line IDs upstream; SO number alone and row ordinals cannot establish business identity.','document_context.csv; composite_keys.csv; small SO raw scope variation','ERP owner','Approved determinants have unique scoped meaning; repeated product lines and partial fulfilment preserved.'),
            ('Evidence','Current invoice/order key evidence is not approval','Verified evidence only','Small invoice has 234 internally consistent references; small order 275/299 raw SO groups vary customer and 278 vary posting date. These support review, not new keys.','document_context.csv; independent_grain_probes.csv','ERP/process owners','No constraint silently promoted from candidate to approved; business key approvals remain zero.'),
            ('Lineage','Technical record locators versus business identifiers','Proposed technical safeguard','Reference raw source version/hash, relative file, sheet/record and column position as technical lineage only; never invent customer, product or transaction IDs from sequence numbers.','Validated source manifests and row positions','Data engineering owner','Every derivative can trace to raw positions; locators cannot masquerade as business PK/FK.'),
            ('Financial','Additive monetary target and recognition basis','Unresolved business decision','Approve reported taxable/gross/net proxy, currency, scope, signs, freight, discounts, tax inclusion, rounding and adjustments; recognized revenue requires ledger evidence.','financial_evidence; outcome_availability_audit.csv','Finance owner','Line/document totals and additive versus nonadditive measures are explicit; no implicit accounting formula.'),
            ('Financial','Repeated document and cumulative totals','Proposed technical safeguard','Do not sum a repeated header amount or cumulative balance as independent lines. Form document/state views only after determinants and consistency are approved.','Invoice Total Include GST / Invoice_Value / cumulative inventory evidence','Finance / inventory owners','Approved header measure appears once per scoped document, or state once per approved snapshot; no arbitrary first-row selection.'),
            ('Financial','Arithmetic screening is not correction authority','Verified evidence only','Existing absolute 1 and relative 0.005 tolerances are provisional diagnostics, not approved accounting rules. Do not recalculate original amounts to force equality.','financial_evidence assumption and business_rule_confirmed fields','Finance owner','Approved finance rule, unit, tax context and tolerance precede correction; all exceptions retained for reconciliation.'),
            ('Dates','Field-specific formats and two-digit centuries','Unresolved business decision','Approve exact formats per source/field/version; retain alternative DMY/MDY readings and raw tokens. No global dayfirst/default century or flexible silent parsing.','203455 ambiguous cells; date_evidence','Source/process owners','Approved parser round-trips declared format; rejected/ambiguous/century-dependent values remain explicitly unresolved.'),
            ('Dates','Excel serial interpretation and impossible dates','Unresolved business decision','Approve numeric date role, workbook epoch, day conventions and plausible domain before serial interpretation; impossible dates require evidence-based owner resolution, not rollover.','14949 serial candidates / 28 impossible dates','Source owners','Approved epoch/domain and raw-to-derived trace; invalid values never silently shifted or treated as zero.'),
            ('Dates','Time basis, fiscal periods and monthly attributes','Unresolved business decision','Approve event versus posting/reporting/update/availability time, timezone/calendar, period closure and fiscal boundaries. Month-only values need proven year; 2027-03 is a period, not an observed day.','date_evidence; synthetic rate applicability / revision month metadata','Business process / finance owners','No update date becomes an event/snapshot date; complete bucket and time-role contracts are documented.'),
            ('Dates','Future/planned records and information availability','Unresolved business decision','Separate actual, planned and known-in-advance values. Keep raw future records; eligibility of future plans as covariates requires proof of availability at the cutoff.','date_evidence; prior future-date review has its own as-of date','Process / data operations owners','Target observations are realized/mature in approved scope; cutoff-specific views retain exclusion reasons without deleting raw records.'),
            ('Coverage','Missing activity versus zero and partial periods','Unresolved business decision','Approve observation calendar, capture completeness, eligibility and zero policy before dense panels or no-event labels. Unobserved dates are not zeros.','date_evidence / prior requirements','Business / data operations owners','Each missing, zero, unknown, partial and out-of-scope state is distinguishable and reconciled.'),
            ('Quantity','Units, pricing quantities and goods/service semantics','Unresolved business decision','Approve product/UOM/pricing-unit conversions and goods/service measure separately. Manual UOM and zero service-like quantities do not define physical demand or service hours.','numerical/category evidence; small invoice 323 G / 14 S','Product / sales owners','Only compatible dimensional units aggregate; rate/unit conversions are approved and versioned.'),
            ('Numerical','Negative, zero and unusual values','Unresolved business decision','Retain negatives, zeros, fractions and outliers unless business context establishes an error; no automatic abs, clipping, deletion or zero-as-missing.','numerical_quality.csv / financial_evidence','Finance / operations owners','Document applicable signed/zero/unit rules and reconcile distributions and amounts after any approved treatment.'),
            ('Missingness','Requiredness, optional fields and placeholders','Unresolved business decision','Define requiredness by record role and lifecycle. Preserve blank versus placeholder/error token versus not-applicable; never blanket fill with zero or forward/backward fill.','missing_values.csv; all 424 issue records','Source/process owners','Missingness reason and permitted use are explicit; no optional-field blank is automatically a defect.'),
            ('Duplicates','Exact, payload and transaction-signature duplicate handling','Unresolved business decision','Keep all candidates until stable grain, provenance and occurrence policy decide legitimacy. Group membership count differs from excess-row count.','3 exact excess / 972 payload excess; duplicate_count_evidence','ERP / business owners','Any approved derivative occurrence selection reconciles group counts, survivor/reason/lineage and financial/quantity totals; sources never deleted.'),
            ('Representations','Case, Unicode, spelling, flags and numerical text','Unresolved business decision','Only after namespace/domain/unit approval may a derived normalization or strict parser be applied. Preserve leading zeros, raw tokens and collisions; fuzzy suggestions never auto merge.','categorical_consistency.csv / numerical_token_issues.csv','Master data / source owners','Collision/crosswalk report, round-trip type/unit validation and explicit unresolved tokens precede use.'),
            ('Inventory','Group-label propagation and row classes','Unresolved business decision','Approve block boundaries, item scope, opening/movement/subtotal/summary roles and warehouse/document semantics before group reconstruction. No blanket fill-down.','inventory_row_shapes.csv; 98104 large movements lack raw item','Inventory/ERP owner','Every proposed item assignment cites block provenance; reset boundaries, orphan movements and cross-item leakage checked.'),
            ('Inventory','Stock state and snapshot semantics','Unresolved business decision','Approve as-of balance, signed movement types, opening state, snapshot cadence, reservations and completeness. Current master stock/update attributes are not historical snapshots.','Grouped inventory / missing stock availability lifecycle','Inventory owner','Approved balance equation, independent as-of control and nonadditive cumulative-field policy; acquire missing ledger/snapshot evidence if needed.'),
            ('GST','Scoped document reconstruction and invoice reconciliation','Proposed technical safeguard','Keep scoped prefix/series/number/suffix reconstruction diagnostic until approved; use GST/invoice as alternate representations, not extra sales. Description is not a persistent line ID.','337->609 document join; 337->337 scoped invoice+description alignment','Finance / ERP owners','Approved issuer/series/type scope, line correspondence, quantity/tax/base consistency and unmatched handling; do not double count.'),
            ('GST','Tax, credit/debit signs and filing versions','Unresolved business decision','Approve tax applicability, note sign/stock impact, original-invoice allocation, filing/amendment version and reporting period; do not infer them from arithmetic alone.','Financial exceptions / 6 and 276 nonempty note exports','Finance/tax process owner','Separate reported components from approved adjustments/liability; no silent sign reversal or tax imputation.'),
            ('Joins','Semantic and point-in-time join approval','Unresolved business decision','No candidate relationship is currently approved. Declare scoped keys, temporal predicates, allowed cardinality, null/unmatched and expansion policy per join contract.','148 candidates / 69 controlled joins; zero business relationships confirmed','Business and data owners','Target grain and signed/absolute financial mass conserved under approved expectation; no null-to-null matching or arbitrary master dedup.'),
            ('Joins','Row-preserving candidates still require scope approval','Verified evidence only','27 raw-key directions currently have matched keys and unique nonblank targets; 20 raw-key tested directions expand. Counts are observations, not approval.','relationship_candidates.csv / controlled_join_validation.csv','Business/data owners','Uniqueness rechecked at each version and temporal scope; full matching/unmatched coverage and expansion diagnostics required.'),
            ('History','Decision windows, population and label maturity','Unresolved business decision','Specify t, H, eligibility/exposure, qualifying outcome, observation closure, availability and reporting lag. Unknown/censored windows are not negatives.','Propensity outcome audit / no approved horizons','Business / data operations owners','Positive/negative/unknown definitions and label-maturity checks precede any label generation.'),
            ('Leakage','Chronological fitting and event separation','Proposed technical safeguard','Plan train/development/final chronological boundaries, matured training labels, point-in-time joins and related-event separation; fit transforms inside training folds only.','leakage_and_validation_controls.csv','ML/data owner','No future/state/duplicate leakage; fold definitions and baseline/evaluation rules approved before features or fitting.'),
            ('Provenance','Synthetic and sample material','Unresolved business decision','Production-use status must be explicit; marked synthetic rate/reference data cannot become production observations by cleaning.','source_authenticity.csv / source_authority.csv','Source/business owners','Approved use scope and lineage; synthetic data remains separately tagged and cannot certify real performance.'),
            ('Schema','Unnamed PCT_NOPJ field','Unresolved business decision','Retain original blank header and 33 NOPJ values, tracked by position. Agency/source meaning is only a hypothesis; do not invent a column name.','Unnamed field issue / inventory headers','Product/reference owner','Raw header/values retained; only an explicit owner-approved semantic binding may assign meaning.'),
            ('Release','Preparation approval and derivative release','Proposed technical safeguard','Require rule decisions, source/semantic versions, tests, lineage, counts and quantity/financial conservation before releasing a derivative for an approved contract.','All unresolved requirements and current task boundary','Business / data owners','All dependencies approved or explicitly accepted for a bounded use; unresolved records and reasons remain auditable. No universal readiness score.')]
        frame=pd.DataFrame([{'rule_id':f'BR-{i+1:03d}','domain':a,'decision_or_rule':b,'status':c,
            'specification':d,'supporting_evidence':e,'owner_role_to_confirm':f,'acceptance_check':g,
            'business_definition_approved':False,'correction_authorized_now':False,
            'business_confirmation_required':c not in ('Confirmed project constraint',)} for i,(a,b,c,d,e,f,g) in enumerate(rules)])
        self.results['business_rules']=frame

    def cleaning_strategies(self):
        strategies=[
            ('CL-01','Missing/optional information','Assess requiredness by entity, lifecycle and source coverage; retain blanks and missing-reason categories. No blanket imputation or removal.','No automatic value correction; metadata-only flagging can be automated after implementation approval.','Source/process owner','Compare required/optional denominators, blank/placeholder counts and complete-row retention; fit any later model-only imputer within training folds.','Outcome absence, panel zeros and propensity negatives cannot be inferred from missing cells.'),
            ('CL-02','Structural empty rows','Preserve raw row positions. A future analytical view may exclude proven layout-only rows only under an approved structural rule and with a complete retained/excluded ledger.','Conditionally automatable in a derivative after explicit structure rule; no deletion from sources.','Data/source owner','Raw = included + excluded + unresolved, disjoint at the declared source-record scope; no nonblank business row lost.','Prevents empty layout rows from becoming observations without changing business target mass.'),
            ('CL-03','Placeholder/error-like tokens','Keep literal NA/#N/A/null/- and errors separate from blanks; approve token meaning for each field/domain before a derived parse or missing classification.','No semantic replacement automatically safe; classify/flag raw token only.','Source/process owner','Token frequencies and raw-to-derived reason mapping conserved; no legitimate code/token converted to missing.','Avoids fabricated zeros, broken identity and silently altered outcome denominators.'),
            ('CL-04','Ambiguous dates and century','Record raw token, source format candidates and interpretation status; use only owner-approved per-field formats/century rules later. No global dayfirst or inference from neighbouring rows.','No automatic date resolution before approval.','Source/process owner','Format-specific parse/round-trip; ambiguity and century counts reconcile; original tokens and alternative readings stay available.','Event ordering, temporal buckets, horizon and leakage checks depend on this approval.'),
            ('CL-05','Impossible dates','Flag unresolved; request traceable source correction or approved exception policy. Do not roll dates, clamp month ends or shift years.','No automatic correction safe.','Source/process owner','Calendar validity plus source correction reference; before/after exception counts and impact on period coverage reconciled.','Invalid event times cannot create valid-looking history or outcome windows.'),
            ('CL-06','Potential Excel serial dates','Confirm numeric field role, workbook epoch and date range; retain numeric token and proposed interpretation separately until approved.','No automatic numeric-to-date conversion before role/epoch approval.','Source/ERP owner','Explicit epoch/unit tests and raw-to-derived provenance; non-date identifiers/measures never converted.','Prevents false history and accidental transformation of ordinary numbers into timestamps.'),
            ('CL-07','Future/planned timestamps','Keep raw values; establish actual/planned/available roles. Define cutoff-specific eligibility views and reasons, not destructive deletion.','No automatic correction or historical inclusion based on date alone.','Business/data operations owner','Check availability<=decision cutoff for allowed inputs and outcome maturity; compare old review date with current contract cutoff explicitly.','Avoids training on future/planned outcomes and accidental hindsight features.'),
            ('CL-08','Calendar gaps / incomplete history','Identify whether periods are complete, partial, unobserved, ineligible or no-activity using extraction and business calendar evidence. No automatic reindex/zero fill.','No automatic missing-period fabrication.','Business/data operations owner','Bucket completeness and boundaries proven; observed/zero/unknown/partial states remain distinct; temporal-support requirements assessed by contract.','Affects forecast support, seasonality and defensible negative purchase windows.'),
            ('CL-09','Duplicate row/signature candidates','Retain exact, payload and proposed transaction-signature groups; approve occurrence identity, source precedence and legitimate split-line policy before any derivative selection.','No automatic deduplication safe under current key/grain evidence.','ERP/business owner','Group membership versus excess counts reconciled; retained/excluded occurrence lineage, reasons and signed/absolute quantities/amounts conserved under approved policy.','Avoids double counting and removal of valid repeated movements, opening balances or split transactions.'),
            ('CL-10','Repeated reference/entity candidates','Separate exact repetitions from conflicting attributes and legitimate history; require scoped identity and effective/available-time crosswalk, not first/last-row selection.','No automatic merge, latest-row winner or master dedup safe.','Master data owner','Unique eligible target per approved scope/time; conflicts explicit; before/after join cardinality and coverage rechecked.','Prevents fanout or future master attributes entering earlier predictions.'),
            ('CL-11','Blank/unmatched identifiers','Retain orphan/unresolved references with source locator; request approved crosswalk/scope or additional master coverage. No generated business IDs or name-only fuzzy repairs.','No automatic identity correction; unmatched/blank flagging only.','Master data/ERP owner','Null and orphan counts, distinct-key coverage both ways, collisions and point-in-time referential rules; no silent inner-join loss.','Defines eligible entity series/population; unmatched does not mean inactive or nonpurchasing.'),
            ('CL-12','Spacing/case/Unicode/flag representations','Keep raw values. Propose derived normalization by approved namespace/domain; detect collisions and preserve equivalence mapping. Flags require explicit true/false/unknown domain.','Conditionally automatable only after approved semantics and collision checks; fuzzy spelling merges never automatic.','Master data/source owner','Raw and derived distinct counts, collision groups, leading-zero preservation, changed-record ledger and encoding round-trip.','Prevents collapsing distinct customers/products or converting unknown flags into negative outcomes.'),
            ('CL-13','Unparsed numerical text','Keep raw token and parse status; approve field role, units/currency/locale and strict grammar before derived numeric parsing. Pricing-unit/stock-impact flags are not financial amounts.','Conditionally automatable after unit/locale/role approval; unsupported strings remain unresolved.','Finance/source owner','Valid grammar and unit/locale tests; parse failures counted separately from blank/zero; round-trip/provenance and financial controls.','Prevents silent zero imputation and mixing identifiers, units and measures.'),
            ('CL-14','Negative/zero/fractional measures','Review returns, cancellations, adjustments, rates and unit conventions. Preserve values until a documented business rule identifies an error.','No automatic abs, sign flip, zero replacement or row deletion safe.','Finance/operations owner','Context-specific sign/zero/fraction rules; signed and absolute sums and counts reconciled; no blanket positivity assumption.','Legitimate returns/adjustments must remain in the approved target definition.'),
            ('CL-15','Distribution outlier candidates','Treat IQR flags as review evidence, not errors; assess context and source evidence. Later model-only robust transforms, if approved, must be fitted within training folds.','No automatic clipping/winsorization/removal safe.','Business/ML owner','Raw tails and exceptions retained; approved change policy and fold-contained transform provenance; before/after target mass reviewed.','Protects rare legitimate demand/transactions and avoids holdout leakage.'),
            ('CL-16','Provisional financial exceptions','Review additive grain, unit, discount, freight, tax, rounding, sign and filing rules with finance; retain source amounts. Do not overwrite reported values to match a formula.','No automatic monetary/tax recalculation safe.','Finance owner','Owner-approved formula/tolerance/context; line/document/adjustment reconciliation and exception ledger; no duplicated totals.','Affects value/tax targets and evaluation labels; recognized revenue remains unsupported without ledger evidence.'),
            ('CL-17','Synthetic source provenance','Tag approved source-use scope in metadata; do not treat cleaning as validation of production authenticity or combine with real data by default.','No automatic promotion to production safe.','Source/business owner','Source marker, lineage and allowed-use decision visible in every derivative; no production-performance claim from examples.','Synthetic histories cannot certify actual demand, customer behavior or FX outcomes.'),
            ('CL-18','Unnamed populated field','Keep blank original header plus position and raw values. Request semantic confirmation; a display locator is not a new business column name.','No automatic renaming/meaning assignment safe.','Reference/product owner','Original blank-header metadata and 33 populated values preserved; approved binding, if any, explicitly versioned.','Unconfirmed agency/source interpretation cannot drive product grouping or joins.'),
            ('CL-19','Unclassified issue or new schema condition','Retain evidence, stop dependent use and request scoped review. New quality rules must have explicit lineage, proposed treatment and approval status.','No automatic correction; fail closed for dependent semantic use.','Data/business owner','Issue has an owner, valid scope/counts, evidence, treatment proposal and post-treatment acceptance criteria before release.','New sources/tasks are assessed through metadata contracts rather than a hardcoded scenario exception.')]
        self.results['cleaning_methods']=pd.DataFrame([{'strategy_id':a,'issue_family':b,'proposed_handling':c,
            'automatic_correction_safety':d,'owner_role_to_confirm':e,'post_correction_validation':f,
            'prediction_impact':g,'business_approval_required':True,'execution_status':'Specification only; no correction executed'} for a,b,c,d,e,f,g in strategies])
        def classify(rule):
            r=rule.casefold()
            if 'completely empty data rows' in r:return 'CL-02'
            if 'placeholder' in r:return 'CL-03'
            if 'ambiguous day/month' in r:return 'CL-04'
            if 'impossible calendar' in r:return 'CL-05'
            if 'excel serial' in r:return 'CL-06'
            if 'future unambiguous' in r:return 'CL-07'
            if 'unobserved months' in r:return 'CL-08'
            if 'duplicate signature' in r:return 'CL-09'
            if 'repeated master' in r:return 'CL-10'
            if 'blank candidate' in r or 'unmatched values' in r:return 'CL-11'
            if any(s in r for s in ('whitespace','case/spacing','spelling','binary flag')):return 'CL-12'
            if 'unparsed nonblank' in r:return 'CL-13'
            if 'negative measure' in r or 'zero measure' in r:return 'CL-14'
            if 'iqr distribution' in r:return 'CL-15'
            if 'financial arithmetic' in r:return 'CL-16'
            if 'synthetic' in r:return 'CL-17'
            if 'unnamed field' in r:return 'CL-18'
            if 'blank values' in r:return 'CL-01'
            return 'CL-19'
        strategies=self.results['cleaning_methods'].set_index('strategy_id')
        records=[]
        scopes={'(whole row)','(compared fields)','(source provenance)'}
        for old in self.issues.to_dict('records'):
            sid=classify(old['rule']);st=strategies.loc[sid]
            file,sheet=old['source_file'],old['worksheet']
            cols=self.columns[(self.columns.file==file)&(self.columns.worksheet==sheet)]
            self.check('Issue source table exists '+old['issue_id'],len(cols)>0)
            col=old['affected_column']
            self.check('Issue column/scope maps '+old['issue_id'],col in set(cols.column_name) or col in scopes,col)
            records.append(dict(old,strategy_id=sid,scope_mapping='Table/provenance-level scope' if col in scopes else 'Exact validated column label',
                proposed_handling=st.proposed_handling,automatic_correction_safety=st.automatic_correction_safety,
                business_approval_required=True,owner_role_to_confirm=st.owner_role_to_confirm,
                post_correction_validation=st.post_correction_validation,prediction_target_impact=st.prediction_impact,
                current_authorization='Document only; no treatment approved or executed'))
        self.results['issue_treatment_specification']=pd.DataFrame(records)
        self.check('Every quality issue mapped without fallback',len(records)==424 and all(r['strategy_id']!='CL-19' for r in records))
        summary=self.results['issue_treatment_specification'].groupby(['strategy_id','severity'],as_index=False).agg(issue_entries=('issue_id','size'))
        summary['count_interpretation']='Issue entries; affected-record counts overlap and must not be summed as unique defects'
        self.results['treatment_coverage_summary']=summary
        self.check('Exact and payload EXCESS duplicate counts preserved',
            self.duplicates.loc[self.duplicates.comparison=='all_raw_fields','duplicate_excess_rows'].sum()==3 and
            self.duplicates.loc[self.duplicates.comparison=='all_fields_excluding_row_ordinal','duplicate_excess_rows'].sum()==972)

    def table_and_column_requirements(self):
        table_rows=[];column_rows=[]
        for t in self.grain.itertuples(index=False):
            columns=self.columns[(self.columns.file==t.file)&(self.columns.worksheet==t.worksheet)]
            issues=self.issues[(self.issues.source_file==t.file)&(self.issues.worksheet==t.worksheet)]
            ids=self.ids[(self.ids.file==t.file)&(self.ids.worksheet==t.worksheet)]
            dates=self.dates[(self.dates.file==t.file)&(self.dates.worksheet==t.worksheet)]
            numeric=self.numerical[(self.numerical.file==t.file)&(self.numerical.worksheet==t.worksheet)]
            used=self.bindings[(self.bindings.file==t.file)&(self.bindings.worksheet==t.worksheet)]
            header=self.headers[(self.headers.file==t.file)&(self.headers.worksheet==t.worksheet)].iloc[0]
            raw_headers=json.loads(header.header_labels_json)
            key_positions=set(ids.column_number);date_positions=set(dates.column_number)
            num_positions=set(numeric.column_number);used_positions=set(used.column_number)
            issue_columns=set(issues.affected_column)
            important=[]
            for col in columns.itertuples(index=False):
                roles=[]
                if col.column_number in key_positions:roles.append('Prior identifier candidate/attribute; not approved business key')
                if col.column_number in date_positions:roles.append('Date/period candidate; source-specific role/format unapproved')
                if col.column_number in num_positions:roles.append('Numerical diagnostic profile; units/additivity not approved')
                if col.column_number in used_positions:roles.append('Cited in feasibility evidence; not a question-to-field mapping')
                if col.column_name in issue_columns:roles.append('Has quality issue requiring treatment decision')
                if roles:important.append(col.column_name)
                column_rows.append({'file':t.file,'worksheet':t.worksheet,'column_number':int(col.column_number),
                    'validated_display_label':col.column_name,'raw_header_json':dump(raw_headers[int(col.column_number)-1]),
                    'source_types':col.types_and_counts_json,'nonblank_values':int(col.nonblank_values),'missing_values':int(col.missing_values),
                    'review_roles':dump(roles or ['Retain raw; target-specific relevance and projection undecided']),
                    'target_specific_binding_approved':False,'proposed_handling':'Keep raw field and source position; bind meaning/type only through approved versioned semantic contract',
                    'business_confirmation_required':True})
            entity=t.candidate_business_entity.casefold()
            if 'inventory' in entity:use='Potential typed movement/state views only after approved group reconstruction and balance/snapshot semantics; no current stock panel.'
            elif 'currency' in entity:use='Separate period reference evidence; explicitly synthetic examples not production rates without authority approval.'
            elif 'reference' in entity or 'country' in entity or 'classification' in entity:use='Optional semantic reference view; scope, historical membership and allowed production use must be approved; not an outcome history.'
            elif 'customer' in entity or 'product' in entity:use='Candidate entity/reference view; current extracts cannot supply historical eligibility or time-varying attributes without additional evidence.'
            elif 'adjustment' in entity or 'gst' in entity:use='Separate reporting/adjustment event views with scoped identity and sign/filing contract; reconciliation without counting alternate representation as extra activity.'
            else:use='Separate document/detail event views; approved target contract may create bucket or decision observations only after identity/time/measure gates.'
            table_rows.append({'table':t.table,'file':t.file,'worksheet':t.worksheet,'rows_below_header':int(t.row_count),
                'nonempty_rows':int(t.nonempty_rows),'columns':int(t.column_count),'business_purpose_candidate':t.candidate_business_entity,
                'record_grain_candidate':t.candidate_record_grain,'grain_evidence':t.evidence,
                'important_columns':dump(important),'relevant_date_fields':dump(dates.column.tolist()),
                'identifier_candidates':dump(ids[['column_name','role','null_rows','distinct_values','duplicate_excess_rows']].to_dict('records')),
                'quality_issue_ids':dump(issues.issue_id.tolist()),'quality_issue_entries':len(issues),'intended_future_use':use,
                'business_confirmation_required':True,'unresolved_scope':t.business_confirmation,
                'currently_approved_business_joins':0,'preparation_execution_authorized':False})
        self.results['table_preparation_requirements']=pd.DataFrame(table_rows)
        self.results['column_preparation_requirements']=pd.DataFrame(column_rows)
        self.check('All source tables and columns specified',len(table_rows)==20 and len(column_rows)==521)
        self.check('Table issue mapping conserves issue entries',sum(r['quality_issue_entries'] for r in table_rows)==424)

    def joins(self):
        frame=self.rels.copy()
        frame['business_join_approved']=False
        frame['preparation_execution_authorized']=False
        frame['future_join_contract_requirements']='Approved semantic scope, exact composite keys, effective/available-time predicates, expected cardinality, null/unmatched policy, grain and conservation tolerances'
        frame['proposed_dependency_decision']=np.where(frame.predicted_excess_left_rows>0,
            'Blocked as direct enrichment: observed expansion; require upstream scope/line allocation or separately approved grain change',
            np.where(frame.matching_distinct_keys==0,'Unsupported on tested keys; no relationship approval inferred',
                'Conditional evidence only: verify authority, temporal scope, coverage and eligible target uniqueness before any approved use'))
        frame['post_join_checks']='Per-key source/target multiplicity, expected versus actual rows, retained/unmatched/null counts, distinct entities, signed/absolute measures, related-event lineage, no null equality'
        self.results['join_dependency_register']=frame
        self.results['join_safeguards']=pd.DataFrame([
            {'safeguard':a,'required_check':b,'approval_state':'Proposed technical control; no business join approved'} for a,b in [
                ('Identity','Keys must identify the same business entity/event and scope; column names or matching values alone insufficient.'),
                ('Nulls','Missing key components do not match missing target values; preserve source rows in diagnostics and record unresolved references.'),
                ('Time','Reference rows effective at event/decision time and actually available at decision cutoff; intervals must not overlap where uniqueness is expected.'),
                ('Cardinality','Many-to-one lookup requires unique eligible target key at the relevant time; reject arbitrary first/last record deduplication.'),
                ('Coverage','Report row and distinct-key coverage both ways; approved unmatched policy, no silent inner join loss.'),
                ('Fanout','Frequency-based expected rows independently checked against actual joins in later approved work; no sampled-only assurance.'),
                ('Mass conservation','At declared grain/unit/currency, reconcile counts, signed and absolute quantities/amounts; repeated header and cumulative totals handled separately.'),
                ('Grain changes','One-to-many/many-to-many relationships need an approved allocation/aggregation/event model, never an accidental expanded training row.'),
                ('Representations','GST/invoice alternate exports must not be stacked as separate events; approved reconciliation links retain each source lineage.'),
                ('Evolution','Revalidate uniqueness, temporal scope and conservation on every source/schema/version; current row preservation is not a future guarantee.')]])

    def blueprints(self):
        rows=[
            ('BP-01','Immutable source/evidence layer','Any authorized source files plus inventories','Source file/version and original record/cell position; no business grain assumed','None','No cross-source business join; source structure captured in metadata','Hashes, source census, headers/extents and raw record/cell counts unchanged','No predictive outcome or transformed values; all periods and unresolved tokens preserved','Preserved raw records, schema and provenance evidence only'),
            ('BP-02','Schema-bound typed observation view','One approved source/record role plus semantic/type contract','One original record at its declared role; raw/parsed/status lineage separate','Only after approved per-field interpretation; preserve period and timestamp roles','None required; do not add entity lookups as a default','Input = eligible + ineligible/unresolved by exclusive reason at declared grain; parsing round-trip and collision checks','Parsed dates/amounts are not automatically valid outcomes or features; no future cutoff inferred','Typed view and explicit unresolved-record ledger, not an automatically clean universal table'),
            ('BP-03','Scoped entity/reference view','Approved master/reference sources and identity/version contract','One approved entity/version/effective interval, not arbitrary first/last row','History/effective and availability intervals required for retrospective enrichment','Only approved crosswalks; unique eligible lookup per scoped key/time','Conflicting versions and collisions explicit; cardinality and target mass preserved','Current/synthetic master attributes cannot be backfilled into earlier decisions without history','Separate customer/product/other reference views as supported by schemas'),
            ('BP-04','Canonical event-detail view','An approved event source with stable event/line identity, time role and measure semantics','One approved event detail/occurrence at declared domain grain','Mature realized events for outcomes; planned/available roles explicit','Optional approved many-to-one references only; no generic detail-to-detail linkage','Occurrence/duplicate policy, line identity and measure conservation; no invented business IDs','Order, invoice, adjustment, service and movement roles remain distinct; target-specific scope is not a source union','Separate event-detail views by approved event semantics, reusable across domains'),
            ('BP-05','Document/header observation view','Approved detail view plus verified document determinants','One scoped document only when approved header attributes/amounts are functionally consistent','Approved document event/date and closure/version basis','Detail-to-header grouping only through approved determinants, not arbitrary first row','Rows/lines and distinct docs reconcile; repeated header totals counted once only under approved rule','No automatic aggregation of mixed-unit lines or assumed order scope','Optional document-level view; does not assert that a repeated ID already defines a business document'),
            ('BP-06','Parallel reporting/reconciliation view','Two approved representations and explicit correspondence contract','Source occurrence plus approved cross-reference, not merged extra transactions','Comparable event/reporting/revision basis and availability','Approved scoped document/line reference; ambiguous matches remain exceptions','Matched/unmatched scope, fanout and quantities/tax/base comparisons; no double counting','Cross-representation duplicates grouped across future validation splits; reconcile before using either version as target authority','Separate evidence views and reconciliation outcomes, not an extra sales fact'),
            ('BP-07','State/flow or as-of panel','Approved baseline state, typed signed movements or authoritative snapshots','Entity/location/as-of state and separately scoped movement events','Complete baseline/flow period, calendar and snapshot semantics required','Only approved group-context reconstruction and identity/temporal joins','Opening + typed flows matches independent balance; no mixing cumulative values as additive flows','Missing state is not zero; current master quantity/update date cannot fabricate history; require lifecycle data when absent','Conditional inventory or other state/flow view; currently blocked for NOP stock history'),
            ('BP-08','Contract-defined temporal metric panel','Approved event/state view with target-specific metric, unit, entity and calendar contract','Chosen entity/unit/currency/time bucket, not raw line count by default','Complete mature observations sufficient for H, folds and relevant seasonality; no universal row minimum','Optional approved dimension/hierarchy memberships at correct time','Aggregation conserves approved target mass; zero/missing/partial/exposure states explicit','No unknown periods filled as zero; observed fields/SQL aggregates are analytics until a valid future outcome contract is defined','Request-derived time-series observations; no single fixed training dataset or target generated now'),
            ('BP-09','Decision/population/outcome observation panel','Approved eligibility/exposure, decision snapshots, event outcomes and observation closure','Eligible entity/event at decision cutoff with defined outcome window','t, H, reporting lag, label maturity and censoring explicitly supplied','Only approved scoped entity/event and point-in-time feature-source joins','Positive/negative/unknown labels distinguish complete follow-up; identity and population counts conserved','Current status and absent capture are not historical negatives; actual outcome/availability history required','Conditional supervised/event-time observation panel; propensity/duration outcomes currently lack sufficient evidence'),
            ('BP-10','Training/validation and inference input contract','Approved temporal/decision observations, feature definitions and deployment capability metadata','Target-defined observation with stable lineage and frozen input schema','Chronological train/development/final holdout; matured labels and fit cutoffs','Only approved request/target-specific joins; model input schema must match preprocessing artifact','No related-event/duplicate leakage; fold-local fitting, feature availability checks, appropriate evaluation/baseline plan','Document proposed feature interfaces only now; no features, labels, splits, fitted statistics or models created','Versioned input/output contracts for future model families; actual preparation/training needs separate approval')]
        self.results['dataset_blueprints']=pd.DataFrame([{'blueprint_id':a,'structural_view_family':b,
            'required_source_capabilities':c,'expected_record_grain':d,'historical_coverage_requirement':e,
            'join_dependency_policy':f,'expansion_and_conservation_checks':g,'leakage_or_semantic_risk':h,
            'intended_output':i,'approved_business_join_dependencies':'None currently approved; exact bindings only after a contract-specific decision',
            'execution_status':'Specification only; no dataset constructed'} for a,b,c,d,e,f,g,h,i in rows])
        self.results['source_view_evidence']=self.results['table_preparation_requirements'][[
            'table','file','worksheet','business_purpose_candidate','record_grain_candidate','intended_future_use','business_confirmation_required']].copy()
        self.results['source_view_evidence']['binding_type']='Current source evidence only; no question-to-dataset route or runtime selection rule'
        # Evidence annotations for structural view types, not executable routes.
        # Exact source names are drawn from the reviewed metadata, never operator constants.
        document_tables=set(self.context.table)
        source_bindings=[]
        blueprints=self.results['dataset_blueprints']
        blueprints['current_source_candidates_NOT_approved']=''
        blueprints['required_upstream_view']=''
        for b in blueprints.itertuples(index=False):
            candidates=[]
            for t in self.grain.itertuples(index=False):
                entity=t.candidate_business_entity.casefold()
                reference=any(s in entity for s in ('customer','product','country','currency','reference','classification')) and 'detail' not in entity
                event=any(s in entity for s in ('detail','adjustment','movement','inventory'))
                relevant=(b.blueprint_id in ('BP-01','BP-02') or
                    b.blueprint_id=='BP-03' and reference or
                    b.blueprint_id in ('BP-04','BP-08') and event or
                    b.blueprint_id=='BP-05' and t.table in document_tables or
                    b.blueprint_id=='BP-06' and any(s in entity for s in ('gst','invoice')) or
                    b.blueprint_id=='BP-07' and 'inventory' in entity or
                    b.blueprint_id=='BP-09' and ('customer' in entity or t.table in document_tables))
                if not relevant:continue
                candidates.append({'file':t.file,'worksheet':t.worksheet})
                source_bindings.append({'blueprint_id':b.blueprint_id,'structural_view_family':b.structural_view_family,
                    'file':t.file,'worksheet':t.worksheet,'source_table':t.table,'rows_below_header':int(t.row_count),
                    'candidate_source_grain':t.candidate_record_grain,
                    'binding_status':'Evidence of potential ingredients only; not an approved source, prepared dataset or runtime routing rule',
                    'required_source_columns':'See exact positional/role requirements for this table in column_preparation_requirements; final projection is contract-dependent',
                    'business_approval_required':True,'business_join_approved':False,
                    'dependency_limitation':('Current party/event extracts do not establish historical eligibility, decision-time snapshots or complete negative windows' if b.blueprint_id=='BP-09' else
                        'No approved state/flow reconstruction or authoritative time panel' if b.blueprint_id=='BP-07' else
                        'Underlying authority, scope, time, identity and measure approvals remain open')})
            ix=blueprints.index[blueprints.blueprint_id==b.blueprint_id][0]
            blueprints.at[ix,'current_source_candidates_NOT_approved']=dump(candidates)
            blueprints.at[ix,'required_upstream_view']=('Approved BP-08/BP-09 observations and compatible feature/input/model contracts; no direct raw training-table assignment' if b.blueprint_id=='BP-10' else
                'Contract-specific approved upstream source/view; candidates are not evidence of readiness')
        self.results['blueprint_source_evidence']=pd.DataFrame(source_bindings)
        self.check('Blueprint source evidence covers all 20 sources',set(self.results['blueprint_source_evidence'].source_table)==set(self.grain.table))
        self.check('Blueprint source annotations reference real views',set(self.results['blueprint_source_evidence'].blueprint_id).issubset(set(blueprints.blueprint_id)))
        self.results['document_context_evidence']=self.context.copy()
        self.results['release_gates']=pd.DataFrame([{'gate_id':f'G-{i+1:02d}','gate':a,'required_evidence':b,
            'current_status':c,'execution_authorized':False} for i,(a,b,c) in enumerate([
                ('Source/evidence preservation','Stable source/report hashes and schema/extent baseline','Verified for this specification only'),
                ('Authority and semantics','Owner-approved source/version/use, outcome, grain, units and scope','Open'),
                ('Identity and relationships','Stable scoped business IDs, line identity, crosswalks and point-in-time cardinality','Open; zero business joins approved'),
                ('Time and coverage','Per-field date/century/epoch rules, calendars, availability and capture closure','Open'),
                ('Quality treatments','Signed-off issue treatments and duplicate/optional/collision policies','Open; no corrections authorized'),
                ('Target/population contract','Target definition, t/H, requiredness, observations, maturity and relevant lifecycle evidence','Open'),
                ('Derivative verification','Row partitions, raw lineage, orphan/fanout, quantity/financial controls and rule-version checks','Design only; requires later approved execution'),
                ('Leakage/validation plan','Chronological boundaries, related events, fold-contained transforms and untouched holdout','Design only; no split/feature/model generated'),
                ('Business acceptance and release','Owner acceptance of bounded unresolved exceptions, limitations and intended use','Open; no derivative release or training authorized')])])

    def architecture(self):
        components=[
            ('Metadata/source adapters','Discover schemas/types/positions, source versions and raw record roles; normalize metadata without renaming source fields.','Authorized source/version and adapter schema','Evidence catalogue plus raw lineage','No filenames or business column assumptions inside reusable operators.'),
            ('Semantic bindings and rule registry','Bind actual field references to owner-approved roles, unit/time/identity rules and validity scope.','Versioned field references, rule decisions, ownership and approval','Typed semantic contract and unresolved alternatives','Actual source names live in data/metadata bindings; no predefined business questions.'),
            ('External LLM/MCP boundary','Accept grounded or partially grounded structured objective from the other developer; validate required objective/entity/metric/time/H/grain/constraints.','Structured intent draft and authorized caller context','Accepted contract draft or minimal structured clarification/blocker','No UI, chatbot, NLP interpreter or manually scripted business-answer implementation in this project task.'),
            ('Plan/readiness validator','Check evidence, authority, feasibility, missing labels/state, approvals and required history; compile admissible operations from contracts.','Current schema/evidence and target/observation contract','Auditable proposed dependency plan or unsupported/needs-approval result','Unseen requests judged by data/method capabilities, not an allowlist of scenarios.'),
            ('Typed parsing and representation interface','Execute approved per-field grammar, locale, epoch/domain normalization with raw values/status retained, only in future approved work.','Approved semantic rule and source field binding','Raw-linked parsed/normalized view plus exception ledger','No global date parser, fixed column constants, auto fuzzy merge or blanket imputation.'),
            ('Identity/context reconstruction interface','Apply approved key scopes, crosswalks and grouped-layout boundaries; expose conflicts and orphans.','Approved identity/group contracts with position/time scope','Scoped entity/event/context view with provenance','No invented business IDs, unapproved forward fill or latest-master assumption.'),
            ('Point-in-time relational interface','Enforce approved scoped/temporal key matching, eligible target uniqueness and explicit unmatched/fanout policies.','Approved relation contract, time predicate and conservation budget','Join diagnostics and authorized derivative only after later approval','No name-only join, null equality, silent inner loss or default detail-to-detail expansion.'),
            ('Metric/calendar observation interface','Build approved entity/bucket/state/count/additive observations with exposure/zero/partial semantics.','Metric, grain, unit, calendar and coverage contract','Target-defined observation interface','No universal aggregated dataset, arbitrary zero filling or automatic fiscal-calendar assumption.'),
            ('Decision/outcome interface','Require eligible population, t/H, availability, full follow-up and positive/negative/unknown definitions.','Approved decision/outcome and maturity/censoring contract','Leakage-auditable decision observations in later approved work','No labels from missing rows/current status; unsupported outcome is explicit.'),
            ('Feature/preprocessing contract — future only','Declare required input roles, temporal lookbacks and transform fit boundaries; bind reusable transformations by schema.','Approved feature/availability definitions and training-fold scope','Versioned feature/input schema and fitted artifacts in later work','Do not implement or compute features now; no target/component leakage or global preprocessing fits.'),
            ('Training/evaluation contracts — future only','Support different target/task types, model families, baseline protocols and chronological validation domains.','Approved target/data contract, candidates and business evaluation utility','Measured evidence, compatible models and packaging metadata in later work','No universal algorithm, no fabricated scores or automatic training on arbitrary requests.'),
            ('Model/input compatibility registry — future only','Describe trained artifact task/target semantics, schema/units, preprocessing version, entity coverage, horizon and validation domain.','Compatible task/outcome/input and trained model capability metadata','Eligible artifact selection or no-compatible-model status','Metadata contracts are permitted; never map anticipated question strings to models or silently substitute a different target.'),
            ('Inference/MCP result contract — future only','Return structured outputs with target definition, units, as-of/H, grain, provenance, model/transform versions and measured uncertainty scope.','Approved request/input contract and compatible trained artifact','Prediction result or explicit needs_clarification/unsupported/insufficient_history/unapproved_rule/no_compatible_model status','No fabricated prediction/confidence; no UI or manual answers. Actual inference not implemented.'),
            ('Audit, lifecycle and extension','Version data/rules/plans/results and monitor schema, identity, freshness, unit, history and model-domain drift.','Source/contract/artifact versions and monitored evidence','Reproducibility, rollback of derivatives and schema-driven extension','New sources/domains/tasks extend adapters/contracts/components rather than a business-question catalogue.')]
        self.results['backend_component_contracts']=pd.DataFrame([{'component':a,'responsibility':b,'inputs':c,'outputs':d,
            'guardrail':e,'implementation_status':'Specification only; future components not built'} for a,b,c,d,e in components])
        self.results['generic_contract_fields']=pd.DataFrame([{'contract_field':a,'specification_requirement':b,
            'status':'Required design definition; no runtime pipeline implemented'} for a,b in [
                ('Objective/task semantics','Observed analytics versus future/unknown target, entity, metric, dimensional unit and decision utility.'),
                ('Authorized source bindings','Source version/hash and actual field/position references from discovered schema; allowed projections and use scope.'),
                ('Semantic/target version','Owner-approved outcome equation, identity/record grain, reporting unit/currency/sign and effective approval version.'),
                ('Time/population contract','Event/available/as-of roles, cutoff t, H, lookback, calendar, eligibility, exposure, completeness and maturity/censoring.'),
                ('Representation/quality contract','Approved parsing/normalization/optional/duplicate/treatment policy plus unresolved-record and collision semantics.'),
                ('Relation/grain contract','Exact scoped/temporal keys, cardinality, null/unmatched behavior, allowed grain change and measure-conservation expectation.'),
                ('Feature/input contract','Required roles, cutoff availability, fit scope, transform artifact and final model schema; no feature computations here.'),
                ('Model capability metadata','Task/target compatibility, trained domain/history/entities/H, units, preprocessing and schema versions, evaluation and uncertainty limits.'),
                ('Structured external request/result','Integration-neutral contract for the other developer: objective/entity/metric/time/H/grain/constraints and result status/evidence/lineage; no question catalogue.'),
                ('Release and audit contract','Approved owner/rule references, counts/lineage/exception reports, immutable inputs, reproducible derivative versions and explicit execution permission.')]])

    def integrity(self):
        frame=pd.DataFrame([{'path':p,'sha256_before':h,'sha256_after':sha(self.root/p),'unchanged':sha(self.root/p)==h}
            for p,h in self.baseline.items()])
        self.check('All prior reports, notebooks, source code and datasets byte-identical',bool(frame.unchanged.all()),len(frame))
        self.results['preserved_input_integrity']=frame

    def export(self):
        mapping={
            'business_rule_register.xlsx':['business_rules','table_preparation_requirements','column_preparation_requirements','prior_requirements','date_evidence','identifier_evidence'],
            'data_cleaning_specification.xlsx':['issue_treatment_specification','cleaning_methods','treatment_coverage_summary','duplicate_count_evidence','financial_evidence'],
            'training_dataset_blueprint.xlsx':['dataset_blueprints','source_view_evidence','blueprint_source_evidence','document_context_evidence','join_dependency_register','join_safeguards','release_gates','backend_component_contracts','generic_contract_fields','reviewed_artifacts','preserved_input_integrity']}
        for name,frame in self.results.items():
            self.check('Untruncated Excel text budget '+name,
                all(not isinstance(value,str) or len(value)<=32767 for row in frame.itertuples(index=False,name=None) for value in row))
            frame.to_csv(self.evidence/f'{name}.csv',index=False,encoding='utf-8-sig',float_format='%.15g')
            self.compare(frame,read_csv(self.evidence/f'{name}.csv'),'New CSV '+name)
        for filename,names in mapping.items():
            self.check('Unique worksheet labels '+filename,len(set(n[:31] for n in names))==len(names))
            with pd.ExcelWriter(self.out/filename,engine='openpyxl') as writer:
                for name in names:self.results[name].to_excel(writer,sheet_name=name[:31],index=False)
                for ws in writer.book.worksheets:
                    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
                    for row in ws:
                        for cell in row:
                            if isinstance(cell.value,str):
                                cell.data_type='s'
                    for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=min(64,max(16,len(str(col[0].value))+2))
            with pd.ExcelFile(self.out/filename) as book:
                self.check('Workbook manifest '+filename,book.sheet_names==[n[:31] for n in names])
                for name in names:
                    loaded=pd.read_excel(book,sheet_name=name[:31],keep_default_na=False)
                    self.compare(self.results[name],loaded,'New Excel '+name)
                    self.export_checks.append({'workbook':filename,'sheet':name[:31],'csv':f'preparation_evidence/{name}.csv',
                        'rows':len(loaded),'columns':len(loaded.columns),'all_cells_verified':True})

    def report(self):
        rules=self.results['business_rules'];tables=self.results['table_preparation_requirements']
        summary=tables[['table','rows_below_header','columns','record_grain_candidate','quality_issue_entries','intended_future_use']]
        text=f'''# Data preparation strategy and business rule specification

Specification baseline: **2026-11-02**; current inventory, quality, relationship and feasibility evidence. Scope: **17 source files, 14 Excel workbooks / 17 worksheets plus 3 GST CSV tables, 20 tables, 521 columns, 37 date-related fields, 135 identifier candidates and 424 existing quality issue entries**.

## Decision and authorization boundary

This is a backend/data specification only. **No cleaning, source transformation, dataset join, aggregation of targets, feature engineering, label generation, training, packaging, inference engine, LLM/MCP integration or UI has been executed or implemented.** Source datasets and every earlier validated report/notebook remain unchanged. Specification-rendering code reads existing evidence; it is not a reusable preparation runtime.

There are **zero currently approved business joins** and **zero newly approved business definitions**. Confirmed project constraints are immutability, documentation-only scope, backend-only development and no predefined questions/scenarios. Verified observations are evidence, not business rules. Proposed safeguards still need implementation approval; semantic/financial/identity/time decisions require the accountable NOP owner. The specification does not authorize itself to execute any treatment.

## Evidence and review coverage

All earlier reports and four existing notebooks were reviewed without reexecution; CSV evidence was parsed, all existing workbook sheets were streamed, narrative/diagram content was read or decoded, and core inventory/quality/relationship/feasibility workbook tables were cross-checked against their CSV companions. Review scope is recorded in `reviewed_artifacts` in the blueprint workbook and [review ledger](preparation_evidence/reviewed_artifacts.csv). Source hashes were checked against the validated source manifest; full source profiles were reused instead of rerunning earlier workflows and overwriting their reports.

References: [inventory validation](../data_inventory/inventory_validation_report.md), [quality assessment](../data_quality/data_quality_report.md), [quality issue register](../data_quality/issue_register.csv), [relationship report](dataset_relationship_report.md), [identifier/relationship matrix](identifier_relationship_matrix.xlsx), [granularity evidence](dataset_granularity_report.xlsx), [logical model](data_model_diagram/README.md), [prediction feasibility](business_prediction_feasibility_report.md), [target evidence](prediction_target_mapping.xlsx), [prediction data requirements](prediction_data_requirements.xlsx).

## Preparation requirements for every source table

{table_md(summary,list(summary.columns))}

[Business rule register](business_rule_register.xlsx) contains the complete `table_preparation_requirements` and `column_preparation_requirements` sheets: exact file/sheet, all 521 column positions, original header JSON/display labels, observed types, missingness, all relevant date fields, all 135 identifier candidates with their roles and counts, important evidence-cited fields, 424 linked issue IDs, intended use, grain evidence and confirmation needs. All 20 tables require business confirmation before predictive semantic use. No column projection, renaming or source selection is approved by a diagnostic importance flag.

Actual source names are citations/bindings in the evidence register, **not constants to embed in reusable preparation operators**. The original PCT_NOPJ blank header is retained as JSON null and a positional display locator; its 33 NOPJ values do not authorize inventing a business name. Every unused field remains in raw evidence; target-specific projection is a later approved contract decision.

## Rule status and required business decisions

{table_md(rules,['rule_id','domain','decision_or_rule','status','specification','owner_role_to_confirm'])}

Each register entry includes acceptance criteria, evidence and current authorization flags. No definition becomes approved merely because the column is populated, unique, apparently similar to another source or arithmetically plausible. The business owner must provide decision, scope, source/field/rule version, rationale, effective/available dates and acceptance criteria before status changes. No owner/person identity or business approval is fabricated; roles identify who should decide.

Specific dependencies include:

- **Sales:** distinguish booked order, issued invoice, shipped/fulfilled quantity and value. Current cancellation states cannot define what was known at a historical cutoff. Small SO number groups vary customer in 275/299 groups and Posting Date in 278/299; source/company/year and line scope must be resolved upstream.
- **Invoice grain:** the small invoice has 337 detail rows / 234 full references with consistent observed party/date/document total per reference, but no approved primary key or stable line ID. Do not declare a description, row ordinal or document+product tuple an upstream line key simply because it is unique here.
- **Finance:** distinguish reported taxable/gross/invoice proxies from recognized revenue, cash receipts and realized margin. Repeated `Invoice Total Include GST`, GST `Invoice_Value`, credit/debit header amounts and cumulative stock measures are nonadditive at detail grain. Discount/freight/tax/sign/unit/currency and revision rules remain open; earlier arithmetic tolerances are screening parameters, not correction or statutory rules.
- **Dates and periods:** 203,455 ambiguous date cells, 28 impossible dates and 14,949 serial candidates remain raw. Approve per-field format, century, epoch, timezone/calendar, event/posting/reporting/availability roles and closed periods. Explicit 2027-03 is a monthly period; yearless revision months and master update timestamps cannot fabricate event history. Earlier future-date findings retain their original review cutoff; a new target contract must state its own as-of date.
- **Units and signs:** reported quantity, pricing unit, UOM, goods/service role and adjustment conventions must be approved before aggregation. Manual UOM and service-like zero quantities do not establish physical demand, service hours or negative outcomes. Negative/zero/outlier values are not automatically errors.
- **Inventory:** 98,104 large-audit movement rows lack raw item labels. Define block boundaries, reset rules, opening/movement/subtotal roles and typed flow signs before any context propagation; no global fill-down. Three grouped audits and current item stock/update attributes do not establish a historical stock snapshot panel. Existing ledger evidence may help only after approved reconstruction; acquire missing baseline/snapshot/flow/availability/lifecycle evidence as needed.
- **GST:** keep invoice/reporting representations separate. Prefix/series/number/suffix reconstruction and scoped invoice+description correspondence are diagnostic candidates, not approved line identity. CN/DN sign, original-invoice allocation, tax applicability, stock impact and filing/amendment versions require finance confirmation.

## Cleaning proposal for every recorded issue

[Data cleaning specification](data_cleaning_specification.xlsx) retains **all 424 original issue entries**, their exact IDs, source/sheet/column or table-level scope, severity, counts, units, original recommended resolution and open status. Each is linked to a proposed method, automatic-correction safety statement, responsible owner role, required approval, post-correction validation and potential target impact. No issue is omitted or treated. All existing rule families map explicitly; the fallback method documents how future unclassified conditions must be blocked/reviewed.

{table_md(self.results['cleaning_methods'],['strategy_id','issue_family','proposed_handling','automatic_correction_safety','post_correction_validation','prediction_impact'])}

### Counting and treatment safeguards

- The **3 exact excess duplicate rows** belong to groups containing 6 records. **972 payload-excess candidates** belong to groups containing 1,542 records; transaction-signature issue groups contain 246 records / 123 excess occurrences. These are different count definitions, not inconsistent reports. Counts overlap across rules and must not be added as distinct defective business records. Inventory opening/group rows may legitimately repeat. No row is selected as a duplicate survivor now.
- A future canonical field may retain raw value, parsed value, parse status, rule version and technical source locator as separate metadata roles; these are design roles, not new business columns generated here. Numeric parse failure, missing, literal placeholder, not-applicable and business zero stay distinct.
- Nonmutating validation/flagging is technically automatable, but there is no current authorization to execute preparation. Even deterministic parsing/normalization can be automated in a derivative only after its grammar/domain/unit/epoch/namespace rule is approved and collision/round-trip checks pass. Semantic date fixes, identity repairs, fuzzy merges, sign changes, duplicate removal and financial recalculation are not automatically safe under current evidence.
- Any later approved treatment preserves immutable raw evidence and a ledger of record/field/rule/reason. At an explicitly declared source-record grain, included, excluded and unresolved partitions must account for every original occurrence without overlap. For group/header/bucket views, use the declared aggregation/lineage reconciliation rather than incorrectly demanding unchanged row counts across an intentional approved grain change.
- No values or outcomes are fabricated from absent records: no default zero, invented date/ID, synthetic eligibility, forward/backward fill, automatic outlier deletion or latest-master winner. Corrections require source or owner evidence; model-only transforms, if later approved, are fitted within training folds and never overwrite business outcomes.

## Separate dataset preparation blueprints

The [training dataset blueprint](training_dataset_blueprint.xlsx) specifies **structural view families**, not a business-question catalogue or a universal training table. No dataset is constructed. Exact source bindings are resolved through authorized metadata and an approved target/observation contract at future planning time.

{table_md(self.results['dataset_blueprints'],['blueprint_id','structural_view_family','required_source_capabilities','expected_record_grain','join_dependency_policy','historical_coverage_requirement','expansion_and_conservation_checks'])}

`source_view_evidence` lists how each of the 20 current tables could contribute in its documented grain. `blueprint_source_evidence` supplies exact candidate file/sheet bindings for each structural family, with limitations, source columns referenced through the positional requirements and approval flags. These are explanatory source citations, not a question-to-dataset routing table or proof of sufficient inputs. The training/input blueprint consumes future approved observation views, not a universal raw-file union. Customer/product/reference views, order events, invoice events, tax reporting/adjustments and inventory state/flow must remain separate until specific semantic contracts justify a bounded relation. A temporal metric panel and a decision/population panel serve different observation structures; neither must be forced on every future task.

### Join dependencies and safeguards

All **148 candidate directions** remain in `join_dependency_register`, including negative coverage results, expected/observed cardinality, source/target rows and key counts, current expansion risks and explicit **business_join_approved=False**. Of the tested raw directions, 27 currently preserve source rows with unique eligible target keys and 20 expand; neither category constitutes business approval.

- SO-only large invoice/order linkage expands **100,188 to 402,400** rows and quantity **363,277 to 1,472,651**. Block direct detail enrichment; require approved scope/line allocation or separate document/aggregate design.
- Small GST/invoice document linkage expands **337 to 609** rows. Scoped invoice+description aligns **337 to 337** with six matching numerical fields in these extracts, but description is not a stable upstream line identifier and sources cannot be stacked as extra sales.
- Large order to large customer master lookup expands **100,286 to 100,898** rows because eligible target codes repeat. Never make it many-to-one by silently selecting the first/latest master row.
- Raw inventory item lookup reaches group labels, not most movements. Reject implicit group propagation and item assignment without an approved layout contract.

{table_md(self.results['join_safeguards'],['safeguard','required_check'])}

No initial target requires adding every available source. Prefer a single authoritative event source when the approved metric can be defined there; enrichment and reconciliation add only approved dependencies. Preserve unmatched/null records in audit evidence; any target-specific eligibility selection must be explicit and explain its loss/coverage impact. No validated join is inferred solely from common column names or empirical equality.

## History, observation contracts and leakage

The feasibility [date evidence](preparation_evidence/date_evidence.csv) preserves all 37 date fields, source types, partial ranges, ambiguous/serial/century counts, timestamp support and beyond-cutoff values. The small invoice/GST partial range covers ten observed months with 107 ambiguous dates per representation; those are the same underlying representation evidence, not doubled history. The longer small-order range depends on unapproved centuries and reused key scope. Large future-dated exports do not establish mature realized history. These limitations cannot be fixed by a large raw row count or by selecting the largest/newest file.

Before later temporal preparation, approve the actual target meaning and unit, population/entity/record grain, t/H, lookback, event/available clocks, calendar, cutoff and reporting lag. Require complete mature observations per requested series for the intended horizon/folds/seasonality, not a universal row threshold. A gap/absent transaction is not a zero. Propensity requires historical eligibility plus defensible positive, negative and unknown/censored windows; current master flags and unmatched accounts cannot supply them. Actual completion, settlement, stockout or recognized revenue requires the missing lifecycle evidence described in [prediction requirements](prediction_data_requirements.xlsx).

Prescribe chronological train/development/final holdout boundaries, matured training labels at each cutoff, point-in-time dimensions and related-event separation across duplicate/alternate exports. Any approved preprocessing/feature fitting occurs within training folds; current/future states, target arithmetic components and later adjustments cannot leak into historical decision inputs. No features, labels, splits, fitted parameters or evaluation metrics are produced in this specification.

## General-purpose backend architecture and integration boundary

The backend must support previously unseen requests through reusable evidence and technical contracts, **not predefined business questions, scenarios, manually programmed answers, question-to-dataset/model mappings or one universal dataset/model**. The other developer owns the LLM and MCP integration. This project task defines the data/backend boundaries only and builds no UI, chatbot, interpreter, pipeline or inference service.

```mermaid
flowchart TD
    MCP[External developer: LLM/MCP structured objective draft] --> C[Backend authorized objective / semantic / observation contract]
    META[Discovered schemas / profile / source / relation evidence] --> C
    RULES[Versioned approved rules and unresolved decisions] --> C
    C --> G[Readiness, permissions, history, identity, leakage and quality gates]
    G -->|missing evidence or ambiguous meaning| B[Structured clarification / unsupported / unapproved-rule status]
    G -->|future approved execution only| P[Reusable schema-bound parsing / context / temporal joins / observations]
    P --> F[Future target-specific feature and input contracts]
    F --> V[Future chronological training/evaluation and compatible artifact metadata]
    V --> M[Model compatibility: task, target, schema, units, H, entities, transform and validation domain]
    M -->|compatible trained artifact| O[Future structured evidence-based inference result to MCP]
    M -->|none compatible| N[No-compatible-model status; never substitute or fabricate]
    O --> A[Versioned lineage / monitoring / drift / scope audit]
    A --> META
```

{table_md(self.results['backend_component_contracts'],['component','responsibility','inputs','outputs','guardrail'])}

The `generic_contract_fields` sheet specifies objective semantics, authorized discovered source bindings, semantic/target versions, time/population, representations/quality, relationships/grain, features/input schemas, model capability metadata and release/audit requirements. Model/target metadata describes compatibility, not an anticipated-question route. New datasets extend adapters/semantic bindings; new targets extend approved observation contracts; new methods extend compatible components. All requested meanings must be grounded or returned with precise missing evidence. Natural-language flexibility cannot invent labels, fields, history, confidence or business approvals.

A future successful result envelope should identify outcome definition/version, entity/metric/unit, as-of/H/grain/scope, prediction values and empirically validated uncertainty where available, source/rule/model/transform versions, evaluation limits and lineage. Non-success envelopes carry a structured status and required evidence/clarification, not fabricated predictions. No engine, trained model, API or MCP integration is implemented now.

## Approval and release sequence

{table_md(self.results['release_gates'],['gate_id','gate','required_evidence','current_status'])}

Next activity is a NOP source-owner/business review of the rule register and contract-specific blockers. Resolve authority, definitions, dates/century/epoch, identity/line grain, units/signs, duplicates, inventory grouping, GST treatment, complete history and horizons where relevant. Obtain missing lifecycle/history sources as required. Record signed-off decisions in a new version without rewriting earlier evidence, then seek explicit authorization for bounded preparation. Do not treat this specification as approval to clean all sources or to launch training.

## Deliverables and validation evidence

- [Business rule register](business_rule_register.xlsx): rules plus every table/column, prior requirements, dates and identifier evidence.
- [Data cleaning specification](data_cleaning_specification.xlsx): all 424 issue treatments, method safety/approval/validation, duplicate count units and financial evidence.
- [Training dataset blueprint](training_dataset_blueprint.xlsx): structural dataset families, current source evidence, 148 conditional join dependencies, safeguards, release gates and backend contracts.
- [Specification validation](preparation_specification_validation.json) and [preservation ledger](preparation_evidence/preserved_input_integrity.csv).

All worksheet manifests, all new CSV/Excel cells, 20 source mappings, 521 column positions/raw headers, 135 identifier profiles, 37 date fields, all 424 unchanged prior issue records and 148 join directions are validated. Report/README references and prior README links are checked. Hashes verify original datasets and all earlier reports/notebooks/implementations remain byte-identical; README is updated only for requested new documentation links. No actual cleaning, joins, features, training, deployment or UI has occurred. Stop for explicit preparation approval.
'''
        (self.out/'data_preparation_strategy.md').write_text(text,encoding='utf-8')

    def update_readme(self):
        p=self.root/'README.md';text=p.read_text(encoding='utf-8')
        additions='''
## Data preparation specification

- [Data preparation strategy](reports/analysis/data_preparation_strategy.md) defines source-specific evidence, proposed treatments, separate dataset view families and a schema-aware backend architecture.
- [Business rule register](reports/analysis/business_rule_register.xlsx) distinguishes project constraints, verified evidence, proposals and unresolved business decisions for every table and column.
- [Data cleaning specification](reports/analysis/data_cleaning_specification.xlsx) maps every recorded issue to proposed handling, approval needs and post-treatment checks.
- [Training dataset blueprint](reports/analysis/training_dataset_blueprint.xlsx) documents structural observation/view contracts, conditional joins, leakage safeguards and future backend/MCP boundaries.

These are specifications only. No cleaning, dataset consolidation, feature engineering, model training or UI is implemented. Actual source names are evidence bindings, not hardcoded rules in future reusable components. Preparation requires explicit approval and scoped business-rule decisions; no business-question catalogue or universal training dataset/model is defined.
'''
        if 'reports/analysis/data_preparation_strategy.md' not in text:p.write_text(text.rstrip()+'\n'+additions,encoding='utf-8')

    def validate(self):
        self.integrity()
        treatment=self.results['issue_treatment_specification']
        self.compare(self.issues,treatment[list(self.issues.columns)],'Original issue fields retained')
        self.check('No business definition/correction authorized',not self.results['business_rules'].business_definition_approved.any() and not self.results['business_rules'].correction_authorized_now.any())
        self.check('No candidate join promoted to approved',not self.results['join_dependency_register'].business_join_approved.any())
        # Independent Excel transport verification through openpyxl/csv, no pandas comparison shortcut.
        for e in self.export_checks:
            wb=load_workbook(self.out/e['workbook'],read_only=True,data_only=False)
            try:
                ws=wb[e['sheet']]
                with (self.out/e['csv']).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
                self.check('Independent export dimensions '+e['sheet'],len(rows)==e['rows']+1 and ws.max_row==len(rows) and ws.max_column==e['columns'])
                for cells,values in zip(ws,rows):
                    if len(cells)!=len(values):raise AssertionError(('Column count',e['sheet']))
                    for c,v in zip(cells,values):
                        if c.data_type in ('f','e'):raise AssertionError(('Unintended formula/error',e['sheet'],c.coordinate))
                        if c.value is None:good=v==''
                        elif c.data_type=='n':
                            try:good=math.isclose(float(c.value),float(v),rel_tol=1e-12,abs_tol=1e-7)
                            except ValueError:good=False
                        else:good=str(c.value)==v
                        if not good:raise AssertionError(('Independent cell content',e['sheet'],c.coordinate,c.value,v))
                self.check('Independent workbook content '+e['sheet'],True)
            finally:wb.close()
        links=re.findall(r'\]\(([^)]+)\)',(self.root/'README.md').read_text(encoding='utf-8'))
        self.check('Previous README links preserved',set(self.readme_links).issubset(links))
        for p in [self.root/'README.md',self.out/'data_preparation_strategy.md']:
            for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
                if re.match(r'^[a-z]+://|^#',link):continue
                target=p.parent/link.split('#')[0]
                # Validation file is the result of these checks; verify it after writing.
                if target.name=='preparation_specification_validation.json':continue
                self.check('Documentation reference '+link,target.exists())

    def run(self):
        self.review_inputs();self.business_rules();self.cleaning_strategies()
        self.table_and_column_requirements();self.joins();self.blueprints();self.architecture()
        self.integrity();self.export();self.report();self.update_readme();self.validate()
        result={'specification_baseline':'2026-11-02','source_files':17,'source_tables':20,'source_columns':521,
            'date_fields':37,'identifier_candidates':135,'quality_issues_specified':424,'relationship_candidates':148,
            'business_rule_entries':len(self.results['business_rules']),'cleaning_method_families':len(self.results['cleaning_methods']),
            'structural_dataset_blueprints':len(self.results['dataset_blueprints']),
            'backend_component_contracts':len(self.results['backend_component_contracts']),
            'approved_business_joins':0,'business_definitions_newly_approved':0,'cleaning_operations_executed':0,
            'source_joins_executed':0,'features_created':0,'models_trained':0,'ui_created':False,
            'preserved_inputs':len(self.baseline),'all_previous_inputs_unchanged':True,
            'reviewed_artifacts':len(self.results['reviewed_artifacts']),'all_checks_passed':all(c['passed'] for c in self.checks),
            'execution_authorization':'Specification only; actual preparation awaits explicit approval',
            'implementation_sha256':sha(Path(__file__)),'export_checks':self.export_checks,'checks':self.checks}
        p=self.out/'preparation_specification_validation.json';p.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        assert json.loads(p.read_text(encoding='utf-8'))['all_checks_passed']
        print(json.dumps({k:v for k,v in result.items() if k not in ('checks','export_checks')},indent=2))
        return result


if __name__=='__main__':PreparationSpecification(Path(__file__).resolve().parents[2]).run()
