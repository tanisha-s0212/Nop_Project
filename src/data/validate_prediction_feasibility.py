"""Independent artifact, temporal-evidence and preservation checks; no ML work."""
from collections import defaultdict
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import nbformat
import pandas as pd
from openpyxl import load_workbook


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def validate(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    out=root/'reports/analysis'; evidence=out/'feasibility_evidence'
    checks=[]
    def check(test,condition,detail=''):
        checks.append({'test':test,'passed':bool(condition),'detail':str(detail)})
        if not condition:raise AssertionError((test,detail))
    record=json.loads((out/'feasibility_validation.json').read_text(encoding='utf-8'))
    check('Assessment checks passed',all(c['passed'] for c in record['checks']))
    check('Complete source/schema scope',record['source_tables']==20 and record['schema_columns']==521 and record['identifier_candidates']==135 and record['date_fields']==37)
    check('Assessment boundary',record['models_trained']==0 and record['source_joins_performed']==0 and record['prediction_targets_generated']==0 and record['prediction_engine_implemented'] is False)
    baseline=json.loads((evidence/'input_manifest.json').read_text(encoding='utf-8'))
    for path,h in baseline.items():check('Preserved '+path,(root/path).exists() and sha(root/path)==h)
    notebook=root/'notebooks/04_business_prediction_feasibility.ipynb'
    n=nbformat.read(notebook,as_version=4);nbformat.validate(n)
    cells=[c for c in n.cells if c.cell_type=='code']
    counts=[c.execution_count for c in cells]
    check('Notebook freshly executed in order',counts==list(range(1,len(cells)+1)),counts)
    errors=[o for c in cells for o in c.get('outputs',[]) if o.output_type=='error']
    check('Notebook has no execution errors',not errors)
    check('Notebook runs the complete assessment',any('assessment.run()' in c.source for c in cells))
    examples=pd.read_csv(evidence/'assessment_examples.csv',keep_default_na=False)
    expected={'Sales forecasting','Revenue forecasting','Customer purchase propensity','Product/service demand forecasting','Inventory forecasting'}
    check('Five requested examples plus broader evidence',set(examples.loc[examples.scope=='Primary requested example','use_case'])==expected and len(examples)>5)
    check('Allowed classifications',set(examples.feasibility).issubset({'Feasible','Feasible with Conditions','Not Currently Feasible'}))
    check('No example claims model readiness or approved definitions',not examples.today_model_ready.any() and not examples.business_definition_approved.any() and not examples.target_values_generated.any())
    check('Horizons explicitly unresolved',examples.horizon_requirement.str.contains('Not supplied').all())
    check('Frequency, actual evidence and missing clock/key requirements explicit',
        examples.available_observation_frequency.str.len().gt(0).all() and
        examples.required_identifier_scope.str.len().gt(0).all() and
        examples.required_date_and_availability_roles.str.len().gt(0).all() and
        examples.required_date_fields_and_coverage.apply(lambda x:isinstance(json.loads(x),list)).all() and
        examples.identifier_candidate_evidence.apply(lambda x:isinstance(json.loads(x),list)).all())
    columns=pd.read_csv(root/'reports/data_inventory/validation/column_validation.csv',keep_default_na=False)
    bindings=pd.read_csv(evidence/'target_source_bindings.csv',keep_default_na=False)
    for r in bindings.itertuples(index=False):
        found=columns[(columns.file==r.file)&(columns.worksheet==r.worksheet)&(columns.column_number==r.column_number)]
        check('Actual-column binding '+r.assessment_id+'/'+r.file+'/'+r.actual_column_name,
            len(found)==1 and found.iloc[0].column_name==r.actual_column_name)
    # Recompute conservative date-evidence support independently, without interpreting raw source dates.
    tokens=pd.read_csv(root/'reports/data_quality/date_value_evidence.csv',keep_default_na=False)
    coverage=pd.read_csv(evidence/'historical_date_coverage.csv',keep_default_na=False)
    cutoff=record['assessment_date']
    accepted={'native Excel datetime','explicit year-month-day','same under DMY and MDY','unambiguous DMY by calendar'}
    totals=defaultdict(lambda:{'calendar':0,'strict':0,'past':0,'future':0,'days':set(),'months':set(),'weeks':set()})
    for r in tokens.itertuples(index=False):
        d=json.loads(r.possible_dates)
        if r.status not in accepted or len(d)!=1:continue
        key=(r.file,r.worksheet,int(r.column_number)); b=totals[key]
        b['calendar']+=int(r.count)
        if 'century' in str(r.interpretation_note).casefold():continue
        b['strict']+=int(r.count)
        iso=d[0][:10]
        if iso>cutoff:b['future']+=int(r.count)
        else:
            b['past']+=int(r.count);b['days'].add(iso);b['months'].add(iso[:7]);b['weeks'].add(date.fromisoformat(iso).isocalendar()[:2])
    for r in coverage.itertuples(index=False):
        b=totals[(r.file,r.worksheet,int(r.column_number))]
        check('Independent date support '+r.file+'/'+r.column,
            (r.calendar_resolved_cells_under_prior_century_convention,r.explicit_full_year_or_native_cells,
             r.explicit_full_year_or_native_at_or_before_asof,r.explicit_full_year_or_native_beyond_asof,
             r.distinct_observed_days_asof,r.distinct_observed_months_asof,r.distinct_iso_weeks_asof)==
            (b['calendar'],b['strict'],b['past'],b['future'],len(b['days']),len(b['months']),len(b['weeks'])))
    check('Known unresolved date totals',coverage.ambiguous_day_month_cells.sum()==203455 and coverage.invalid_calendar_cells.sum()==28 and coverage.possible_serial_cells.sum()==14949)
    prior=pd.read_csv(root/'reports/data_quality/issue_register.csv',keep_default_na=False)
    carry=pd.read_csv(evidence/'unresolved_issue_dependencies.csv',keep_default_na=False)
    check('Every prior issue retained with original fields',len(carry)==424 and carry[list(prior.columns)].astype(str).equals(prior.astype(str)))
    # Cell-level independent Excel-versus-CSV transport checks; text IDs remain text.
    for entry in record['export_checks']:
        wb=load_workbook(out/entry['workbook'],read_only=True,data_only=False)
        try:
            ws=wb[entry['sheet']]
            with (out/entry['evidence_csv']).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
            check('Export dimensions '+entry['sheet'],len(rows)==entry['rows']+1 and ws.max_row==len(rows) and ws.max_column==entry['columns'])
            for cells_, expected_ in zip(ws,rows):
                if len(cells_)!=len(expected_):raise AssertionError(('Column count',entry['sheet']))
                for cell,expected_value in zip(cells_,expected_):
                    actual=cell.value
                    if cell.data_type in ('f','e'):raise AssertionError(('Formula/error',entry['sheet'],cell.coordinate))
                    if actual is None:good=expected_value==''
                    elif cell.data_type=='n':
                        try:good=math.isclose(float(actual),float(expected_value),rel_tol=1e-12,abs_tol=1e-7)
                        except ValueError:good=False
                    else:good=str(actual)==expected_value
                    if not good:raise AssertionError(('Workbook content',entry['sheet'],cell.coordinate,actual,expected_value))
            check('All export cells verified '+entry['sheet'],True)
        finally:wb.close()
    import matplotlib.pyplot as plt
    check('Coverage figure decodes',plt.imread(evidence/'date_interpretation_coverage.png').size>0)
    # Write execution record before checking its own report link, then finalize it.
    result={'status':'passed','assessment_date':cutoff,'executed_code_cells':len(cells),'cell_errors':len(errors),
        'execution_counts':counts,'all_original_sources_unchanged':True,'all_prior_artifacts_unchanged':True,
        'preserved_inputs':len(baseline),'notebook_sha256':sha(notebook),
        'assessment_implementation_sha256':sha(root/'src/data/assess_prediction_feasibility.py'),
        'validator_sha256':sha(Path(__file__)),'checks':checks,'interpreter':sys.executable}
    dest=out/'feasibility_notebook_validation.json'
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    for md in [root/'README.md',out/'business_prediction_feasibility_report.md']:
        for link in re.findall(r'\]\(([^)]+)\)',md.read_text(encoding='utf-8')):
            if not re.match(r'^[a-z]+://|^#',link):check('Reference link '+link,(md.parent/link.split('#')[0]).exists())
    result['checks']=checks
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
    return result


if __name__=='__main__':validate()
