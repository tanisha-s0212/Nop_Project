"""Read-only evidence runner; never authorizes or executes preparation.

Repository report tooling, not a new framework abstraction or runtime.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from business_prediction.adapters import SourceConfig
from business_prediction.adapters.csv import CSVAdapter
from business_prediction.adapters.excel import ExcelAdapter
from business_prediction.discovery import DiscoveryOptions, discover
from business_prediction.assessment.intake import intake_findings
from business_prediction.assessment.relevance import DataRelevanceAssessor
from business_prediction.assessment.strategies import default_strategies
from business_prediction.assessment.target import TargetAssessor


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def source_manifest(directory):
    root = Path(directory)
    return [{'relative_path':p.relative_to(root).as_posix(), 'extension':p.suffix.lower(),
             'size_bytes':p.stat().st_size, 'sha256':sha256(p)}
            for p in sorted(root.rglob('*')) if p.is_file()]


def reusable_prior(current, recorded):
    return bool(current and recorded and current == recorded)


def unresolved_decisions(rows):
    """Documentary confirmation is not backend execution authorization."""
    keys = ('owner_answer','supporting_evidence_reference','approved_scope_version','confirmed_by','confirmation_date')
    return [dict(r) for r in rows if not (r.get('decision_status','').lower() == 'confirmed'
            and r.get('business_approval_recorded','').lower() == 'true'
            and all(r.get(k,'').strip() for k in keys))]


def write_new(path, value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')


def inspect_source(path, config, *, headers=None, encoding='utf-8-sig', max_rows=32):
    limits = {'max_bytes':64*1024*1024,'max_cells':6_000_000}
    if path.suffix.lower() in {'.xlsx','.xlsm'}:
        adapter = ExcelAdapter(path,config,header_rows=headers or {},max_uncompressed_bytes=256*1024*1024,**limits)
    elif path.suffix.lower() == '.csv': adapter = CSVAdapter(path,config,encoding=encoding,**limits)
    else: raise ValueError('No registered read-only adapter for this format; source not excluded silently.')
    return discover(adapter,options=DiscoveryOptions(max_rows=max_rows))


def technical_assessment():
    """Pure existing components; no governed assessment or owner impersonation."""
    characteristics = [('historical','numeric'),('future','count'),('unknown_outcome','numeric'),
                       ('unknown_outcome','categorical'),('future','unregistered_kind')]
    probes = []
    for intent,kind in characteristics:
        request = {'intent':intent,'desired_output':{'value_kind':kind}}
        strategy,issues = default_strategies().select(request)
        probes.append({'characteristics':request,'problem_type':strategy.problem_type if strategy else None,
                       'findings':issues,'data_readiness_established':False})
    return {'mode':'read_only_component_assessment','partial_intake_findings':intake_findings({}),
            'technical_probes':probes,
            'target_without_approved_bindings':TargetAssessor().assess({},[],DataRelevanceAssessor(),None),
            'governed_assessment_engine_executed':False,'execution_authorized':False,
            'limitation':'No authenticated NOP runtime, approved semantic bindings or attributed target evidence supplied. No credentials, grants, bindings or approvals manufactured.'}


def assess(root, output):
    root,output = Path(root).resolve(),Path(output).resolve()
    if not output.is_dir() or any(output.glob('*.json')):
        raise ValueError('Use a new evidence destination; existing evidence is never overwritten.')
    def rows(rel):
        with (root/rel).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
    before = source_manifest(root/'dataset'); write_new(output/'source_manifest_before.json',before)
    recorded = {r['file']:r['sha256_after'] for r in rows('reports/data_quality/source_integrity.csv')}
    prior = {(r['file'],r['worksheet']):r for r in rows('reports/data_quality/source_tables.csv')}
    layouts = {(r['file'],r['worksheet']):r for r in rows('reports/data_inventory/validation/header_validation.csv')}
    encodings = {r['file']:r['csv_encoding'] or 'utf-8-sig' for r in rows('reports/data_inventory/validation/source_completeness.csv')}
    results,bundles = [],[]
    for item in before:
        path = root/'dataset'/item['relative_path']; same = reusable_prior(item['sha256'],recorded.get(item['relative_path']))
        headers = {sheet:int(r['header_excel_row']) for (name,sheet),r in layouts.items() if name == item['relative_path'] and same}
        result = {**item,'matches_recorded_hash':same,'tables':[]}
        try:
            config = SourceConfig('readiness-'+hashlib.sha256(item['relative_path'].encode()).hexdigest()[:20],
                                  'unverified-source-owner','read_only_readiness_assessment')
            bundle = inspect_source(path,config,headers=headers,encoding=encodings.get(item['relative_path'],'utf-8-sig'))
            bundles.append({'source_metadata':bundle.source_metadata,'discovery_result':bundle.discovery_result})
            for t in bundle.discovery_result['tables']:
                name = '(CSV table)' if path.suffix.lower() == '.csv' else t['name']
                old,layout = prior.get((item['relative_path'],name)),layouts.get((item['relative_path'],name))
                row_match = bool(old and t['observed_row_count'] == int(old['rows_below_header']))
                col_match = bool(old and t['schema_field_count'] == int(old['columns']))
                header_match = bool(layout and [f['raw_header']['value'] for f in t['fields']] == json.loads(layout['header_labels_json']))
                reuse = same and row_match and col_match and header_match
                result['tables'].append({'worksheet':name,'table_id':t['table_id'],'observed_rows':t['observed_row_count'],
                    'columns':t['schema_field_count'],'header_row':t['header_row'],'profile_rows':t['scanned_row_count'],
                    'profile_complete':t['profile_complete'],'row_count_matches_prior':row_match,
                    'column_count_matches_prior':col_match,'headers_match_prior':header_match,
                    'full_prior_quality_evidence_reusable':reuse,'prior_full_profile':old if reuse else None,
                    'schema_version':bundle.discovery_result['schema_version'],
                    'source_version':bundle.source_metadata['source_version'],'approval_status':'unreviewed'})
            result['status'] = 'assessed_read_only'
        except Exception as exc:
            result.update(status='failed',error={'code':getattr(exc,'code',type(exc).__name__),'message':str(exc)})
        results.append(result)
        print(json.dumps({'file':item['relative_path'],'status':result['status'],'tables':len(result['tables'])}),flush=True)
    after = source_manifest(root/'dataset')
    responses = rows('reports/analysis/initial_prediction_clarification_evidence/decision_response_log.csv')
    assessment = {'assessed_at':datetime.now(timezone.utc).isoformat(),'sources':results,'source_count':len(before),
        'excel_workbooks':sum(r['extension'] in {'.xlsx','.xlsm','.xls'} for r in before),
        'csv_files':sum(r['extension'] == '.csv' for r in before),'table_count':sum(len(r['tables']) for r in results),
        'failures':[r['relative_path'] for r in results if r['status'] == 'failed'],'sources_unchanged':before == after,
        'profile_policy':'32-row prefixes; full physical counts/headers reverified. Prior full profiles reused only on exact source hash and matching shape/headers.',
        'historical_coverage_cutoff':'Existing diagnostic cutoff 2026-11-02 retained; not a newly approved cutoff.',
        'training_ready':False,'artifact_published':False,'status':'blocked'}
    databases = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.db','.sqlite','.sqlite3'}
                 and not {'.venv','.git','__pycache__'}.intersection(p.relative_to(root).parts)]
    blockers = {'decision_count':len(responses),'unresolved_decisions':unresolved_decisions(responses),
        'owner_questions':rows('reports/analysis/initial_prediction_clarification_evidence/decision_questions.csv'),
        'repository_runtime_database_candidates':databases,'authenticated_NOP_runtime_supplied':False,
        'external_approval_store_checked':False,'execution_authorized':False,
        'technical_blocker':'Discussion-first document-count target needs approved date interpretation, document-grain construction and time-bucket aggregation. Registered local operators do not support date parsing, aggregation, derived targets or grain changes. No workaround implemented.'}
    write_new(output/'source_manifest_after.json',after); write_new(output/'discovery_bundles.json',bundles)
    write_new(output/'readiness_assessment.json',assessment); write_new(output/'approval_blockers.json',blockers)
    write_new(output/'prediction_candidates.json',{'basis':'Reused feasibility evidence; not new approvals, ready targets or fixed question/model mappings.',
        'candidates':rows('reports/analysis/feasibility_evidence/assessment_examples.csv')})
    write_new(output/'assessment_components.json',technical_assessment())
    print(json.dumps({k:assessment[k] for k in ('source_count','table_count','failures','sources_unchanged','status')}),flush=True)
    return assessment


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); outcome = assess(args.root,args.output)
    if outcome['failures'] or not outcome['sources_unchanged']: raise SystemExit(1)
