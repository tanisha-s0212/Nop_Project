"""Meeting-document builder, not an end-user question catalogue or ML runtime."""
from pathlib import Path
import csv, hashlib, json, math, re
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'reports/analysis'; EV=Path(__file__).resolve().parent
OWN={'initial_prediction_business_clarification.md','initial_prediction_readiness_checklist.xlsx','initial_prediction_clarification_validation.json'}
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return pd.read_csv(p,keep_default_na=False,encoding='utf-8-sig')

def run():
    manifest=EV/'input_manifest.json'
    if manifest.exists():baseline=json.loads(manifest.read_text(encoding='utf-8'))
    else:
        assert not any((OUT/n).exists() for n in OWN),'Existing deliverables need review'
        paths=[p for p in (ROOT/'reports').rglob('*') if p.is_file() and EV not in p.parents and p.name not in OWN]
        paths += [p for p in (ROOT/'dataset').rglob('*') if p.is_file()]
        paths += list((ROOT/'notebooks').glob('*.ipynb'))+list((ROOT/'src/data').glob('*.py'))
        baseline={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
        manifest.write_text(json.dumps(baseline,indent=2),encoding='utf-8')
    assert all(sha(ROOT/p)==h for p,h in baseline.items())
    readme=ROOT/'README.md'; oldlinks=EV/'readme_link_baseline.json'
    if not oldlinks.exists():oldlinks.write_text(json.dumps(re.findall(r'\]\(([^)]+)\)',readme.read_text(encoding='utf-8'))),encoding='utf-8')
    rules=read(OUT/'preparation_evidence/business_rules.csv')
    cols=read(ROOT/'reports/data_inventory/validation/column_validation.csv')
    examples=read(OUT/'feasibility_evidence/assessment_examples.csv')
    assert len(rules)==36
    for file,sheet,expected in [
        ('business_rule_register.xlsx','business_rules',rules),
        ('data_cleaning_specification.xlsx','issue_treatment_specification',read(OUT/'preparation_evidence/issue_treatment_specification.csv')),
        ('training_dataset_blueprint.xlsx','dataset_blueprints',read(OUT/'preparation_evidence/dataset_blueprints.csv')),
        ('prediction_target_mapping.xlsx','assessment_examples',examples)]:
        actual=pd.read_excel(OUT/file,sheet_name=sheet,keep_default_na=False)
        assert actual.shape==expected.shape and list(actual.columns)==list(expected.columns)
        if file=='business_rule_register.xlsx':assert actual.astype(str).equals(expected.astype(str))
    for p in ['data_preparation_strategy.md','business_prediction_feasibility_report.md']:
        assert len((OUT/p).read_text(encoding='utf-8'))>100
    P=('Sales Invoice Details.xlsx','Sheet1');L=('Sales Invoice Details 1.xlsx','Sheet1');G=('GSTR1_Invoice.csv','(CSV table)')
    def binding(source,names):
        for name in names:assert len(cols[(cols.file==source[0])&(cols.worksheet==source[1])&(cols.column_name==name)])==1,(source,name)
        return {'file':source[0],'worksheet':source[1],'actual_fields':names}
    def p(names=None):return binding(P,names or ['Invoice Num','Invoice Date','TransType'])
    # ID, original rule IDs, responsible role, observation, exact question, why,
    # required confirmation/evidence, and consequence if unresolved.
    notes=[
      ('D01',['BR-005','BR-034'],'ERP/source owner; business owner',
       '337 small-export lines versus 100188 larger-export rows; production authority/authenticity unapproved.',
       'Which exact invoice extract/version is authoritative for the intended issuer/company/branch and history, and is it complete production data rather than a filtered, sample or synthetic extract?',
       'Consistency does not establish production provenance or source precedence.',
       'ERP report definition, version, scope, filters, extraction timestamp, completeness controls and production-use confirmation.',
       'Blocks authoritative history; do not choose by file size or suffix.'),
      ('D02',['BR-006'],'NOP sales/process owner',
       'The candidate is invoice-document activity, not units, orders, net sales or recognized revenue.',
       'Does forecasting issued invoice-document volume support the actual business decision, and which event/transaction types qualify? If the need is units, orders or value, what is that outcome instead?',
       'An easier proxy must not replace the requested business meaning.',
       'Written business use and qualifying-event definition; ERP meanings of TransType or equivalent evidence.',
       'Blocks target agreement; a different outcome needs re-scoped dependencies.'),
      ('D03',['BR-010','BR-025'],'ERP/document owner',
       '234 nonblank raw full invoice references appear in 337 lines; global key scope unapproved.',
       'Within what issuer/company, series and financial-year scope does Invoice Num identify one invoice? Can it be reused or reformatted, and must case, spaces, punctuation and leading zeros be preserved?',
       'Distinct documents require an approved namespace.',
       'ERP numbering/series scope, reuse examples and approved equivalence rules; no invented business IDs.',
       'Blocks document identity; no guessed composite keys or silent normalization.'),
      ('D04',['BR-010','BR-023'],'ERP/report owner; data owner',
       '337 detail lines / 234 references; observed party/date/document total consistent within each reference; no blank Invoice Num/Invoice Date.',
       'Are rows invoice detail lines and should the count be once per approved scoped invoice regardless of line count? What verified policy applies if a later record has missing keys/dates or conflicting document dates?',
       'Repeated invoice references are expected line structure, not duplicate-row proof.',
       'Report grain, document determinants and source-backed exception/remediation policy; no arbitrary first-row selection.',
       'Blocks document-grain release with unresolved required-field conflicts.'),
      ('D05',['BR-016','BR-018'],'ERP/process owner',
       'Invoice Date: 107 ambiguous / 230 calendar-resolved full-year values; partial 2025-12-21 to 2026-09-13. SO Date is not required here.',
       'What source/version-specific formats and business meaning does Invoice Date have, and is it the correct count-event date? Please verify ambiguous examples using ERP/export evidence, not a guessed global DD/MM or MM/DD default.',
       'Alternative readings change time buckets and history.',
       'Format/event-role documentation, verified examples and relevant timezone/date-only convention.',
       'Blocks date correction and dependent temporal observations.'),
      ('D06',['BR-007'],'Sales/process owner; finance owner for lifecycle scope',
       'Gross issuance versus valid/net event population and complete invoice lifecycle history are unapproved.',
       'Should we count gross issued invoices, valid/nonvoid invoices or another lifecycle outcome? How do cancellations, returns, credit/debit adjustments and reissues affect it, as of when? If lifecycle evidence is absent, is labelled gross issuance acceptable?',
       'A credit note does not automatically subtract one invoice.',
       'Approved lifecycle/as-of inclusion rule and ERP history if needed; GST/note calculations only when the outcome requires them.',
       'Blocks final event population; not all GST rules become mandatory.'),
      ('D07',['BR-019','BR-032'],'ERP/data operations owner',
       'Small-source resolved dates are not beyond the prior cutoff; larger partial Invoice Date reaches 2027-03-20. Event date does not prove availability.',
       'Are records actual issued events, plans or tests? What extraction watermark, revision/reporting delay and latest complete cutoff apply, and what shows history was available at each forecast decision time?',
       'Future/planned entries and later revisions cannot silently become mature history.',
       'Actual/planned semantics, extraction/availability boundary, closure and revision-delay evidence; missing metadata must be supplied, not invented.',
       'Blocks trustworthy as-of observations and leakage-free evaluation.'),
      ('D08',['BR-018','BR-020'],'Reporting/business owner; data operations owner',
       'Ten observed months of partial timestamps do not establish full periods or zero-activity dates.',
       'Which calendar and reporting boundaries apply, which periods are closed and fully captured, and how is a true no-invoice period distinguished from incomplete, unobserved or out-of-scope data?',
       'Missing capture cannot be filled as business zero.',
       'Calendar, closure/extraction controls and approved complete/partial/zero/unknown policy.',
       'Blocks complete temporal observations and zero interpretation.'),
      ('D09',['BR-005','BR-024'],'ERP/data owner',
       'Small extract has zero exact/payload-excess duplicates; repeated IDs are lines. Larger export has 60 payload-excess candidates; version union is unapproved.',
       'Will one approved source/version supply history? If repeat exports, amendments or recurring records appear, which are the same occurrence and what precedence rule applies? Please distinguish valid detail lines from duplicate extracts.',
       'Avoid both double counting versions and deleting legitimate lines.',
       'Extraction/version/occurrence specification and exception/precedence policy if needed; no blanket deduplication or union.',
       'Blocks combining versions or resolving candidates, not unrelated global duplicate groups.'),
      ('D10',['BR-006','BR-032'],'NOP process/decision owner',
       'No horizon, bucket, lead time, update cadence or entity-level scope supplied.',
       'Who uses the forecast, for which decision, at what issuer-level scope, time bucket, future horizon H and update cadence? What lead time is useful, and are customer/product splits actually required?',
       'Horizon and grain determine observations/validation; monthly is not an assumed default.',
       'Decision-use statement, H, bucket/calendar linkage, as-of/update schedule and scope.',
       'Blocks final observation/evaluation contract, not an otherwise approved bounded parser treatment.'),
      ('D11',['BR-020','BR-033'],'ERP/data owner; business owner',
       '337 lines / 234 references are not 337 time observations; ten partial months do not establish annual seasonality or adequate holdout support.',
       'Can NOP provide complete mature authoritative history for the agreed horizon, bucket and validation periods, with closure and scope-change evidence? If an honest holdout is unsupported, what additional history can be supplied?',
       'Temporal support, not row count, determines suitability.',
       'Closed-period production coverage and scope history; additional mature data where H/folds need it. No universal minimum-month threshold.',
       'Blocks credible training/evaluation where support is inadequate.'),
      ('D12',['BR-033'],'NOP process owner; ML/data owner',
       'Chronological evaluation, mature observations and protected final holdout are proposed. No scores or approved error thresholds exist.',
       'Can we agree chronological evaluation for H with mature training observations, protected holdout periods and suitable simple baselines? Which error costs and acceptance criteria match the decision?',
       'Technical protocol is not business acceptance or measured performance.',
       'Approved evaluation/maturity protocol, baseline/metric rationale and business acceptance criteria; actual scores remain unknown.',
       'Blocks training/evaluation signoff; no model/features are needed during clarification.'),
      ('D13',['BR-002','BR-012','BR-036'],'Project/business owner; ERP/data owner',
       'Only documentation is authorized; no cleaning, dataset, features or training approval exists.',
       'Who owns each applicable decision/exception, and will they approve the exact source/version, treatment and checks before execution? Please authorize cleaning, dataset construction, feature work and training as distinct bounded activities.',
       'Completed documents must not authorize later stages silently.',
       'Recorded answer, accountable owner, evidence/version, scope and approval date; current answer/approver/date placeholders remain blank.',
       'Blocks every unapproved execution stage despite promising technical evidence.'),
      ('D14',['BR-008','BR-009','BR-030'],'Master data owner; requesting business owner',
       'Party/product fields exist, but mappings are unapproved; aggregate count needs no master join.',
       'Only if a customer/product split or filter is requested: which scoped identities and historical crosswalks are authoritative, and how are shared/missing codes and memberships handled at decision time?',
       'Segmentation adds identity and temporal-join dependencies.',
       'Scope-change confirmation and approved entity/crosswalk/history/join contract; otherwise not applicable to this scope.',
       'Blocks segmentation/enrichment only, not a confirmed join-free aggregate count.'),
      ('D15',['BR-013','BR-014','BR-015','BR-021','BR-022','BR-029'],'Finance/product-unit owner; requesting business owner',
       'Value/quantity follow-ons need approved units/additivity; repeated totals are nonadditive; Manual UOM has no approved physical meaning.',
       'Only for a value, quantity or net-financial outcome: what measure, currency/unit and tax/freight/discount/sign/adjustment basis is intended? Is recognized revenue needed rather than an invoiced-value proxy?',
       'Pure count needs no tax recalculation or unit conversion.',
       'Approved dimensional/financial definition and relevant reconciliation/lifecycle evidence; ledger recognition if required.',
       'Blocks the changed measure only; do not impose all financial/unit cleaning on count.'),
      ('D16',['BR-028','BR-029','BR-030'],'ERP/finance source owner',
       'Diagnostic GST reconstruction has 234 scoped references; document join expands 337 to 609. Invoice+description is not an approved stable line key.',
       'Only if GST is primary or an owner requires reconciliation: what issuer/series/prefix/suffix and version rules define the document, and what reconciliation grain/exceptions are approved? Is a business join needed at all?',
       'Raw GST numbers omit scope; alternate exports are not extra sales.',
       'Explicit trigger and approved reference/reconciliation contract; tax/note allocation only if needed by the outcome.',
       'Blocks GST-dependent scope only; no mandatory GST join/signoff for a single-source count.'),
      ('D17',['BR-016','BR-017','BR-019'],'ERP/source owner',
       'Large Invoice Date: 33782 ambiguous cells, 2996 serial candidates, partial range to 2027-03-20. Small Invoice Date has no serial/impossible candidates.',
       'If an alternate mixed-date source is chosen, what formats, century and workbook epoch/domain rules apply to its relevant date field, and which future/planned entries are actual history? Can source-verified examples support each interpretation?',
       'A source switch invalidates an assumed small-source date policy.',
       'Selected-source field/version interpretation and actual/planned evidence; century/epoch only where relevant.',
       'Blocks that alternate source/date field, not all 14949 project-wide serial candidates.')]
    overrides={
        'D01':[p(),binding(L,['Invoice Num',' Invoice Date '])],
        'D04':[p(['Invoice Num','Invoice Date','Customer Billing Name','Invoice Total Include GST'])],
        'D05':[p(['Invoice Date'])], 'D07':[p(),binding(L,['Invoice Num',' Invoice Date '])],
        'D14':[p(['Customer Billing Name','Customer Billing GSTIN','Part Code SAP Code','Item Foreign Code'])],
        'D15':[p(['Taxable Value','Total Value','Invoice Total Include GST','Quantity','UOM','Item Type G or S'])],
        'D16':[binding(G,['Invoice_Date','Invoice_Number','Doc_Series','Doc_Series_Prefix','Doc_Series_Suffix']),p(['Invoice Num','Invoice Date'])],
        'D17':[binding(L,['Invoice Num',' Invoice Date '])]}
    triggers={'D14':'Customer/product filter or segmentation only','D15':'Value/quantity/net-financial outcome only','D16':'GST primary source or required reconciliation only','D17':'Alternate mixed-date source only'}
    decisions=pd.DataFrame([{'decision_id':id,'original_business_rule_ids':'; '.join(ids),'relevance':'Conditional' if id in triggers else 'Core',
        'dependency_trigger':triggers.get(id,'Initial aggregate invoice-count discussion'),
        'decision_status':'Proposed' if id=='D12' else 'Unresolved','responsible_owner_role':owner,
        'affected_file_worksheet_fields':json.dumps(overrides.get(id,[p()]),ensure_ascii=False),
        'existing_technical_evidence':observation,'exact_question_for_owner':question,'why_it_matters':why,
        'confirmation_or_evidence_required':needed,'impact_if_unresolved':impact,'business_definition_approved':False,
        'evidence_reference':'business_rule_register.xlsx; business_prediction_feasibility_report.md; identifier_relationship_matrix.xlsx; initial_prediction_clarification_evidence/technical_observations.csv'}
        for id,ids,owner,observation,question,why,needed,impact in notes])
    observations=pd.DataFrame([
        ('E01',*P,'Invoice Num; Invoice Date','337 detail lines / 234 raw nonblank references; no missing key/date.','Not approved identity/grain','dataset_granularity_report.xlsx; ../data_quality/identifier_quality.csv'),
        ('E02',*P,'Invoice Num; Invoice Date; Customer Billing Name; Invoice Total Include GST','No within-reference observed party/date/document-total variation for 234 references.','Not business approval','document_context.csv; feasibility_evidence/independent_grain_probes.csv'),
        ('E03',*P,'Invoice Date','107 ambiguous / 230 calendar-resolved full-year cells; partial 2025-12-21 to 2026-09-13; ten observed months / 103 resolved distinct dates.','Not complete history or annual support','../data_quality/date_quality.csv; feasibility_evidence/historical_date_coverage.csv'),
        ('E04',*P,'Whole row / payload','Zero exact and zero payload-excess duplicates; repeated invoice references are lines.','No source-union approval','../data_quality/duplicate_analysis.csv'),
        ('E05',*L,' Invoice Date ; Invoice Num','100188 rows including 5 empty; 33782 ambiguous Invoice Date cells / 2996 serial candidates; partial range through 2027-03-20; 60 payload-excess candidates.','Alternate evidence, not preferred authority','../data_quality/source_tables.csv; ../data_quality/date_quality.csv; ../data_quality/duplicate_analysis.csv'),
        ('E06',*G,'Invoice_Number; Doc_Series; Doc_Series_Prefix; Doc_Series_Suffix','337 rows; 178 raw numbers / 234 diagnostic scoped references; same small-invoice representation, not extra sales history.','GST reconstruction/relationship unapproved','identifier_relationship_matrix.xlsx; dataset_relationship_report.md'),
        ('E07','Sales Order Report 1.xlsx','Sheet1','SO No; Customer Code; Posting Date','275/299 raw SO groups vary customer and 278 vary Posting Date; longer partial range depends on century.','Not the first count by span alone','document_context.csv; business_prediction_feasibility_report.md')],
        columns=['evidence_id','file','worksheet','fields_or_scope','existing_observation','approval_boundary','evidence_reference'])
    candidates=pd.DataFrame([
        {'priority':1,'candidate':'Scoped invoice-document volume','classification':'Feasible with Conditions; not ready for training','evidence':'337 lines / 234 references; internally consistent observed document fields.','limitations':'107 ambiguous dates; ten partial months; authority, scope, lifecycle, completeness, H and evaluation support unapproved.','dependencies':'No business joins, unit/financial rules or customer/product/GST enrichment inherently needed.','recommendation':'Discuss first; source is an evidence anchor, not chosen authority.'},
        {'priority':2,'candidate':'Approved invoiced-value proxy','classification':'Feasible with Conditions; not ready for training','evidence':'Reported taxable/line/document amounts and matching small GST/invoice representation.','limitations':'Same source/time limits plus financial additivity, currency, tax/freight/discount/sign/adjustments; recognition needs ledger.','dependencies':'D15; D16 only if explicitly needed.','recommendation':'Follow-on if value is the actual objective; no silent proxy.'},
        {'priority':3,'candidate':'Observed goods/product quantity','classification':'Feasible with Conditions; not ready for training','evidence':'323 G / 14 S small-invoice lines; item, quantity and UOM fields.','limitations':'Same temporal/authority limits plus product identity, compatible units and per-series history; Manual UOM unapproved; service hours/latent demand unsupported.','dependencies':'D14/D15; additional lifecycle evidence for other meanings.','recommendation':'Follow-on if units are needed; count is not physical demand.'}])
    app={}
    def scope(ids,category,linked,note):
        for id in ids:app[id]=(category,linked,note)
    scope(['BR-001','BR-003','BR-004'],'Confirmed project boundary',[],'Immutable evidence, no fixed question routes and backend-only scope are constraints, not business approval.')
    scope(['BR-002','BR-012','BR-036'],'Core execution/release',['D13'],'Exact stage/treatment/lineage needs explicit permission.')
    scope(['BR-005','BR-034'],'Core',['D01','D09'],'Authority and production provenance for selected source, not file-size preference.')
    scope(['BR-006'],'Core',['D02','D10'],'Accepted business outcome, time, H and scope.')
    scope(['BR-007'],'Core',['D06'],'Lifecycle population decision; full GST/note calculations not automatic.')
    scope(['BR-008','BR-009'],'Conditional',['D14'],'Only requested entity split/filter/enrichment; no default master joins.')
    scope(['BR-010'],'Core',['D03','D04'],'Scoped document grain; persistent line IDs not mandatory for count if determinants defensible.')
    scope(['BR-011'],'Technical observation',['D03','D04'],'Observed consistency/key variation is not approval.')
    scope(['BR-013','BR-014','BR-015','BR-021','BR-022'],'Conditional',['D15'],'Relevant measure/filter only. Never sum repeated totals; pure count needs no monetary definition.')
    scope(['BR-016'],'Core; alternate extension',['D05','D17'],'Relevant Invoice Date field only; no global parsing rule.')
    scope(['BR-017'],'Conditional',['D17'],'No small Invoice Date serial/impossible candidates; not a global resolution gate.')
    scope(['BR-018'],'Core',['D05','D08'],'Event/time and reporting calendar/closure.')
    scope(['BR-019'],'Core',['D07','D17'],'Actual/available history; source change needs confirmation.')
    scope(['BR-020'],'Core',['D08','D11'],'Completeness/zero and mature temporal support.')
    scope(['BR-023'],'Core for required fields',['D04','D05'],'Key/date missing/conflict policy; unrelated optional blanks not blockers.')
    scope(['BR-024'],'Core',['D09'],'No deleting expected lines or combining unapproved variants.')
    scope(['BR-025'],'Core for identity only',['D03'],'Namespace equivalence if applied; unrelated spelling/flag/numeric fixes deferred.')
    scope(['BR-026','BR-027','BR-035'],'Deferred',[],'Inventory and PCT_NOPJ meaning unrelated to issuer-level invoice count.')
    scope(['BR-028','BR-029'],'Conditional',['D15','D16'],'Only required source/outcome/reconciliation triggers these rules.')
    scope(['BR-030'],'Conditional join approval',['D14','D16'],'No joins needed by default; exact relation approval if scope changes.')
    scope(['BR-031'],'Technical observation',[],'Fanout/safe-direction evidence does not require approving all relationships.')
    scope(['BR-032'],'Core time/H subset',['D07','D10'],'Cutoff/H/maturity matter; no customer positive-negative cohort needed for aggregate count.')
    scope(['BR-033'],'Core history/evaluation',['D11','D12'],'Chronological validation proposed; no scores/features/models exist.')
    assert set(app)==set(rules.rule_id)
    rule_scope=pd.DataFrame([dict(r,initial_candidate_relevance=app[r['rule_id']][0],decision_ids='; '.join(app[r['rule_id']][1]),scope_note=app[r['rule_id']][2],original_register_modified=False) for r in rules.to_dict('records')])
    ready_notes=[
        ('R01','1. Target/observation grain',['D01','D02'],'Objective and authority','Accepted event/use and production source/version/issuer.','No silent metric substitution.'),
        ('R02','1. Target/observation grain',['D03','D04','D09'],'Document/occurrence grain','Scoped numbering, determinants, lines/version policy and required-field exception route.','No ordinal or guessed business key.'),
        ('R03','1. Target/observation grain',['D05','D06','D07','D08','D10'],'Time/population/bucket/H','Approved date, lifecycle, actual/available cutoff, full periods, zero policy, H/cadence.','No propensity negative panel added to count.'),
        ('R04','2. Before scoped cleaning',['D01','D03','D04','D05'],'Exact field treatment','Approved source/version, required key/date grammar and exception policy.','No unrelated inventory/GST/SO Date or optional-field cleanup prerequisite.'),
        ('R05','2. Before scoped cleaning',['D09','D13'],'Raw/change/occurrence lineage','Immutable raw/hash plus treatment/reason/validation and version/occurrence policy.','No fabricated zero/date/ID, blanket dedup or arbitrary first row.'),
        ('R06','2. Before scoped cleaning',['D13'],'Cleaning authorization','Named owner approval for exact treatment and checks.','H/evaluation need not block an otherwise approved bounded parser; later dependent work remains blocked.'),
        ('R07','3. Before training dataset',['D01','D02','D03','D04','D05','D06','D07','D08','D09','D10','D13'],'Accepted observation/preparation contract','Accepted results from later authorized preparation, full scope/time contract and explicit build approval.','No unapproved joins or fabricated observations.'),
        ('R08','3. Before training dataset',['D07','D08','D10','D11'],'Mature temporal support','Complete closed history for H/folds; more production history if needed.','337 lines are not 337 time observations; ten partial months prove no annual pattern or holdout.'),
        ('R09','3. Before training dataset',['D03','D04','D09','D13'],'Identity/lineage conservation','Approved raw/document/exception/occurrence reconciliation protocol.','No joins by default; triggered relations need scoped/time/cardinality/coverage checks.'),
        ('R10','4. Before prepared-data EDA/features',['D13'],'Prepared-data EDA permission','Accepted derivative and explicitly bounded EDA permission.','Existing audit review is not new source-analysis/feature permission.'),
        ('R11','4. Before prepared-data EDA/features',['D07','D10','D12','D13'],'Feature availability contract','Approved later feature scope, known-at-cutoff inputs and fold-local fitting boundaries.','No future/current-state/target-arithmetic/duplicate leakage; no feature generated now.'),
        ('R12','4. Before prepared-data EDA/features',['D14','D15','D16','D17'],'Triggered dependencies only','Conditional approvals only if split/measure/GST/source switch required.','Non-triggered items not applicable to scope, not globally resolved; not all 36 decisions required.'),
        ('R13','5. Before training/evaluation',['D10','D11','D12'],'Evaluation and acceptance','H/utility, mature chronological development/final holdout, baselines/metrics and error costs approved.','No claimed score, model winner or confidence before measured evaluation.'),
        ('R14','5. Before training/evaluation',['D03','D07','D09','D12','D13'],'Compatible input/model and leakage checks','Versioned target/input/source/transform scope and related-event/chronological separation.','No universal model or fixed question-to-model routes.'),
        ('R15','5. Before training/evaluation',['D13'],'Separate authorization','Named owner approves bounded model work after applicable gates.','No training or prediction release authorized by documents.')]
    readiness=pd.DataFrame([{'checklist_id':id,'stage':stage,'decision_ids':'; '.join(ids),'minimum_requirement':item,'evidence_and_approval_required':evidence,'acceptance_check':accept,'status':'Proposed' if id in ('R11','R13') else 'Unresolved','execution_authorized':False,'readiness_confirmed':False,'evidence_received':'','approved_by':'','approval_date':''} for id,stage,ids,item,evidence,accept in ready_notes])
    fields=[];seen=set()
    for d in decisions.itertuples(index=False):
        for s in json.loads(d.affected_file_worksheet_fields):
            for name in s['actual_fields']:
                key=(s['file'],s['worksheet'],name)
                if key in seen:continue
                seen.add(key);c=cols[(cols.file==key[0])&(cols.worksheet==key[1])&(cols.column_name==key[2])].iloc[0]
                fields.append({'file':key[0],'worksheet':key[1],'actual_column_name':key[2],'column_number':int(c.column_number),'existing_types':c.types_and_counts_json,'nonblank_values_from_prior_evidence':c.nonblank_values,'missing_values_from_prior_evidence':c.missing_values,'meaning_approved':False})
    response=decisions[['decision_id','original_business_rule_ids','relevance','decision_status','responsible_owner_role']].copy()
    for name in ['owner_answer','supporting_evidence_reference','approved_scope_version','confirmed_by','confirmation_date','review_notes']:response[name]=''
    response['business_approval_recorded']=False
    integrity=pd.DataFrame([{'path':p,'sha256_before':h,'sha256_after':sha(ROOT/p),'unchanged':sha(ROOT/p)==h} for p,h in baseline.items()])
    sheets={'prediction_candidates':candidates,'decision_questions':decisions,'readiness_checklist':readiness,'rule_relevance':rule_scope,'source_field_evidence':pd.DataFrame(fields),'technical_observations':observations,'decision_response_log':response,'preserved_input_integrity':integrity}
    bookpath=OUT/'initial_prediction_readiness_checklist.xlsx'
    for name,frame in sheets.items():frame.to_csv(EV/(name+'.csv'),index=False,encoding='utf-8-sig',float_format='%.15g')
    with pd.ExcelWriter(bookpath,engine='openpyxl') as writer:
        for name,frame in sheets.items():frame.to_excel(writer,sheet_name=name,index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
            for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='244665')
            for row in ws:
                for c in row:
                    if isinstance(c.value,str):c.data_type='s'
                    c.alignment=Alignment(vertical='top',wrap_text=True)
            widths={'exact_question_for_owner':78,'existing_technical_evidence':62,
                'confirmation_or_evidence_required':68,'impact_if_unresolved':58,
                'affected_file_worksheet_fields':72,'responsible_owner_role':36,
                'why_it_matters':45,'specification':65,'scope_note':60,
                'evidence_and_approval_required':65,'acceptance_check':62,
                'existing_observation':72,'evidence_reference':70,'path':78,
                'owner_answer':65,'supporting_evidence_reference':65,'review_notes':60}
            for col in ws.columns:
                label=str(col[0].value)
                ws.column_dimensions[col[0].column_letter].width=widths.get(label,min(70,max(20,len(label)+5)))
            heights={'decision_questions':155,'readiness_checklist':100,'rule_relevance':115,
                'technical_observations':100,'prediction_candidates':110,'decision_response_log':70,
                'source_field_evidence':65,'preserved_input_integrity':35}
            ws.row_dimensions[1].height=42
            for row_no in range(2,ws.max_row+1):ws.row_dimensions[row_no].height=heights[ws.title]
            if ws.title in ('decision_questions','decision_response_log'):ws.freeze_panes='D2'
    def question_table(frame):
        lines=['| Decision / original rules | Exact owner question |','| --- | --- |']
        for d in frame.itertuples(index=False):lines.append('| '+d.decision_id+' / '+d.original_business_rule_ids+' | '+d.exact_question_for_owner.replace('|','\\|')+' |')
        return '\n'.join(lines)
    brief=f'''# Initial prediction: business clarification brief

**Purpose:** obtain scoped NOP business, ERP, finance and data-owner decisions before preparation. This is a meeting document, not approval or a catalogue of end-user prediction questions. No source data is cleaned, transformed, joined or aggregated; no labels, features or models are generated.

## Discuss this candidate first

Discuss **future scoped invoice-document volume**: one approved invoice document per approved time bucket and horizon. This is a proposed aggregate event-count capability, not an agreed target or chosen model. Confirm usefulness first; invoice count is not order booking, shipped units, invoiced value or recognized revenue.

Evidence anchor: `Sales Invoice Details.xlsx / Sheet1` has **337 detail lines / 234 nonblank raw invoice references**, with consistent observed party/date/document total within each reference. That does not approve a global business key. `Invoice Date` has **107 ambiguous values**; 230 calendar-resolved full-year values span **2025-12-21–2026-09-13**, ten observed months with completeness unconfirmed. These are not 337 temporal observations and do not establish annual seasonality or enough holdout history. The smaller extract is a discussion anchor, not the chosen authority.

| Priority | Candidate | Missing evidence / limitation |
| --- | --- | --- |
| 1 | Scoped invoice-document volume: consistent observed references; can avoid business joins and monetary/unit rules | Authority/version, actual event, identity/date/lifecycle scope, complete mature periods, H and evaluation support |
| 2 | Approved invoiced-value proxy: reported financial fields exist | Same source/time issues plus additivity, currency/sign/discount/freight/tax/adjustments; recognition needs ledger evidence |
| 3 | Observed goods/product quantity: item/quantity fields and 323 G / 14 S small-invoice lines | Product identity, compatible units and per-series history; Manual UOM unapproved; service hours/latent demand unsupported |

All three are **Feasible with Conditions; none is ready for training**. Propensity/inventory remain deferred under existing feasibility findings. The longer small-order range is not a better first count by default: 275/299 raw SO groups vary customer, 278 vary Posting Date and its dates depend on an unapproved century convention.

## Scope the discussion tightly

Proposed minimum: `Invoice Num`, `Invoice Date`, qualifying type/event semantics (`TransType` where relevant) and confirmed issuer/source metadata. No customer/product master, order or inventory join, financial calculation or GST join is inherently required for issuer-level document count. Request missing metadata; do not invent it.

Lifecycle is a core population decision, but gross issuance does not automatically require net-revenue or GST tax/note-allocation rules. Activate only dependencies triggered by the accepted source/outcome.

The [readiness workbook](initial_prediction_readiness_checklist.xlsx) contains all 17 decisions with exact file/worksheet/fields, owner roles, existing evidence, why/impact and required confirmation. **D01–D13 are core; D14–D17 conditional.** D12 is Proposed; other decisions are Unresolved. No business decision is Confirmed. Answer, approver and date placeholders remain blank; owner roles are not appointed people.

## Core owner questions

{question_table(decisions[decisions.relevance=='Core'])}

## Ask only when triggered

{question_table(decisions[decisions.relevance=='Conditional'])}

All 36 original rules are reviewed, not modified. BR-026/027 (inventory) and BR-035 (PCT_NOPJ) are deferred for this count. BR-008/009 apply to requested entity splits/filters; BR-013–015/021–022 to relevant measures/filters; BR-028/029 and BR-030 to required GST/source/reconciliation/join dependencies. BR-031 is evidence, not a requirement to approve 148 relationships. BR-032 applies to cutoff/H/maturity, not a propensity positive/negative cohort. No rule is generally waived or resolved.

## Readiness by stage

All execution stages remain **not authorized / not ready**. The workbook provides 15 checkable items.

| Before this activity | Minimum evidence and approval |
| --- | --- |
| Establish target/observation grain | Authority and accepted business use; scoped identity/grain; lifecycle, date, calendar/complete periods, zero policy and t/H/cadence |
| Clean relevant fields only | Exact version/projection and approved key/date/exception/occurrence policy; immutable raw/change lineage and explicit treatment authorization. H/evaluation need not block an otherwise approved bounded parser, but still block later dependent work |
| Construct first training dataset | Accepted outputs from later authorized preparation; signed observation contract and mature history for H/folds; record/document/exception conservation and provenance; explicit build permission. No joins by default |
| Prepared-data EDA/features | Accepted derivative and scoped permission; known-at-cutoff inputs/features and fold-local fitting. Reviewing existing audits now does not permit new source analysis or features |
| Train/evaluate | Adequate mature temporal support; approved H/utility/metrics/baselines and chronological development/final holdout; compatible input/target/model scope, related-event leakage checks and explicit authorization |

## Evidence is not approval

- Small source has **zero exact/payload-excess duplicates** in prior checks. Repeated references are detail structure; do not delete them as duplicate invoices.
- GST is an alternate representation: prior document join expands 337 to 609; scoped invoice+description aligns 337, with no approved stable line key/relationship. No reconciliation is performed or imposed here.
- Large Invoice Date has 33,782 ambiguous values, 2,996 serial candidates and future-dated partial coverage. A source switch needs its own relevant decisions, not preference by size.
- Project-wide 424 issues, 203,455 ambiguous dates, 28 impossible dates, 14,949 serial candidates and duplicate findings remain unresolved. Address dependencies affecting this scope, not the entire project by default.

## Meeting outcome and next action

Record owner answer, source/rule version, scope, evidence, approver and date in `decision_response_log`. Move Unresolved/Proposed to Confirmed only on explicit recorded owner confirmation. Non-triggered items are not applicable **to this scope**, not globally approved. Consistent values or completed documents are not business approval or execution permission.

If invoice activity does not meet the objective, re-scope against actual evidence rather than substitute it. This is one proposed contract in the general-purpose schema-aware backend, not fixed prediction questions, question-to-dataset/model routes or a universal model. No UI, LLM or MCP functionality is implemented.

**Next:** hold the scoped owner review, then seek explicit authorization for the next bounded activity once its applicable checklist is satisfied. Stop here; preparation/model development does not start automatically.

## References

[Preparation strategy](data_preparation_strategy.md), [36-rule register](business_rule_register.xlsx), [cleaning specification](data_cleaning_specification.xlsx), [dataset blueprint](training_dataset_blueprint.xlsx), [prediction feasibility](business_prediction_feasibility_report.md), [target mapping](prediction_target_mapping.xlsx), [relationship evidence](identifier_relationship_matrix.xlsx), [document context](document_context.csv), [date evidence](../data_quality/date_quality.csv).

[Readiness/response workbook](initial_prediction_readiness_checklist.xlsx), [validation record](initial_prediction_clarification_validation.json), [preservation ledger](initial_prediction_clarification_evidence/preserved_input_integrity.csv).
'''
    (OUT/'initial_prediction_business_clarification.md').write_text(brief,encoding='utf-8')
    addition='''
## Initial prediction business clarification

- [Initial prediction clarification brief](reports/analysis/initial_prediction_business_clarification.md) separates core owner decisions from conditional dependencies for the first candidate discussion.
- [Initial prediction readiness checklist](reports/analysis/initial_prediction_readiness_checklist.xlsx) links questions to unchanged business rules and records stage evidence, approvals and response placeholders.

These documents support clarification only. No business definition or data/model work is approved by completing them. No UI, LLM or MCP functionality is implemented.
'''
    text=readme.read_text(encoding='utf-8')
    if 'reports/analysis/initial_prediction_business_clarification.md' not in text:readme.write_text(text.rstrip()+'\n'+addition,encoding='utf-8')
    checks=[]
    def check(name,condition):
        assert bool(condition),name
        checks.append({'test':name,'passed':True})
    for path,h in baseline.items():check('Preserved '+path,sha(ROOT/path)==h)
    check('36 original rules retained',len(rule_scope)==36 and rule_scope[list(rules.columns)].astype(str).equals(rules.astype(str)))
    check('17 unique decisions',len(decisions)==17 and decisions.decision_id.is_unique)
    check('No approval fabricated',not decisions.business_definition_approved.any() and not response.business_approval_recorded.any() and set(decisions.decision_status).issubset({'Unresolved','Proposed'}))
    check('No stage authorization',not readiness.execution_authorized.any() and not readiness.readiness_confirmed.any())
    check('Unrelated inventory/PCT deferred',all(app[r][0]=='Deferred' for r in ['BR-026','BR-027','BR-035']))
    for r in readiness.itertuples(index=False):check('Readiness decision links '+r.checklist_id,set(r.decision_ids.split('; ')).issubset(set(decisions.decision_id)))
    for d in decisions.itertuples(index=False):
        check('Original rule links '+d.decision_id,set(d.original_business_rule_ids.split('; ')).issubset(set(rules.rule_id)))
        for s in json.loads(d.affected_file_worksheet_fields):
            for field in s['actual_fields']:check('Actual field '+d.decision_id+'/'+field,len(cols[(cols.file==s['file'])&(cols.worksheet==s['worksheet'])&(cols.column_name==field)])==1)
    wb=load_workbook(bookpath,read_only=True,data_only=False)
    try:
        check('Workbook tabs',wb.sheetnames==list(sheets))
        for name,frame in sheets.items():
            ws=wb[name]
            with (EV/(name+'.csv')).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
            check('Shape '+name,len(rows)==len(frame)+1 and ws.max_row==len(rows) and ws.max_column==len(frame.columns))
            for actual,expected in zip(ws,rows):
                assert len(actual)==len(expected)
                for c,v in zip(actual,expected):
                    assert c.data_type not in ('f','e'),(name,c.coordinate)
                    if c.value is None:good=v==''
                    elif c.data_type=='n':good=math.isclose(float(c.value),float(v),abs_tol=1e-7,rel_tol=1e-12)
                    else:good=str(c.value)==v
                    assert good,(name,c.coordinate,c.value,v)
            check('Every workbook/CSV cell '+name,True)
    finally:wb.close()
    check('Previous README links retained',set(json.loads(oldlinks.read_text(encoding='utf-8'))).issubset(re.findall(r'\]\(([^)]+)\)',readme.read_text(encoding='utf-8'))))
    result={'status':'passed','evidence_baseline':'Existing validated evidence dated 2026-11-02; no new source profiling','core_decisions':13,'conditional_decisions':4,'rules_reviewed':36,'readiness_items':15,'workbook_sheets':len(sheets),'previous_inputs_preserved':len(baseline),'source_files_unchanged':len([p for p in baseline if p.startswith('dataset/')]),'previous_reports_unchanged':len([p for p in baseline if p.startswith('reports/')]),'business_decisions_confirmed':0,'source_cleaning_transformations_joins_aggregations':0,'features_labels_models_generated':0,'ui_llm_mcp_implemented':False,'brief_sha256':sha(OUT/'initial_prediction_business_clarification.md'),'workbook_sha256':sha(bookpath),'builder_sha256':sha(Path(__file__)),'checks':checks}
    dest=OUT/'initial_prediction_clarification_validation.json';dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    for md in [readme,OUT/'initial_prediction_business_clarification.md']:
        for link in re.findall(r'\]\(([^)]+)\)',md.read_text(encoding='utf-8')):
            if not re.match(r'^[a-z]+://|^#',link):check('Reference '+link,(md.parent/link.split('#')[0]).exists())
    result['checks']=checks;dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
    print('Validated checks:',len(checks))

if __name__=='__main__':run()
