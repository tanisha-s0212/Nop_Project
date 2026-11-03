"""ML-only actual-source delivery workflow; no query, LLM, MCP or API changes."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from features.prepare_invoice_line_value import prepare_line_value
from training.ml_inventory import inspect_sources
from training.tabular_regression import train_tabular_regressors, metrics
from prediction.model_adapters import TabularRegressionInferenceAdapter


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')


def fresh_prediction(root,interface,artifact,request):
    code=f"import json,sys; from {interface[0]} import {interface[1]}; print(json.dumps({interface[1]}(json.loads(sys.argv[2]),model_path=sys.argv[1]),allow_nan=False))"
    process=subprocess.run([sys.executable,'-c',code,str(artifact),json.dumps(request)],cwd=root,
        env={**os.environ,'PYTHONPATH':str(root/'src')},capture_output=True,text=True,check=True)
    return json.loads(process.stdout)


def protected_manifest(root):
    paths=[*(root/'dataset').rglob('*'),*(root/'models').rglob('*'),*(root/'src/business_prediction').rglob('*.py')]
    return {str(path.relative_to(root)):digest(path) for path in paths if path.is_file() and '__pycache__' not in path.parts}


def run_delivery(root,evaluation_directory):
    root,evaluation_directory=Path(root).resolve(),Path(evaluation_directory).resolve()
    evaluation_directory.mkdir(parents=True,exist_ok=True)
    before_path=evaluation_directory/'protected_manifest_before.json'
    if before_path.exists():before=json.loads(before_path.read_text())
    else:
        before=protected_manifest(root);write_json(before_path,before)
    if any(not (root/path).is_file() or digest(root/path)!=value for path,value in before.items()):
        raise ValueError('a protected preexisting source, model or framework file changed')
    inventory_path=evaluation_directory/'source_inventory.json'
    prior=root/'reports/analysis/nop_readiness_evidence'
    if inventory_path.exists():inventory=json.loads(inventory_path.read_text())
    else:
        inventory=inspect_sources(root/'dataset',prior/'discovery_bundles.json',prior/'source_manifest_before.json')
        write_json(inventory_path,inventory)
    if not inventory['all_sources_inspected'] or not inventory['all_recorded_hashes_match']:
        raise ValueError('source inventory or source-hash verification failed')
    for source in inventory['files']:
        if digest(root/'dataset'/source['relative_path'])!=source['sha256']:raise ValueError('source changed after inventory')
    data=root/'data/nop_domestic_invoice_line_value/v1'
    if not data.exists():
        prepare_line_value(root,root/'data/preparation_specs/nop_domestic_invoice_line_value_v1.json',data)
    metadata=json.loads((data/'observations.metadata.json').read_text())
    if digest(data/'observations.csv')!=metadata['dataset_sha256']:raise ValueError('prepared dataset integrity failed')
    spec=json.loads((data/'training_spec.json').read_text())
    models=root/'models/business_regression/nop_domestic_invoice_line_value/v1'
    if not models.exists():train_tabular_regressors(data/'observations.csv',spec,models,project_root=root,version='1.0.0',seed=20261103)
    evaluation=json.loads((models/'evaluation_metrics.json').read_text())
    frame=pd.read_csv(data/'observations.csv',keep_default_na=False,dtype={'item_code':str,'document_id':str})
    assignments=pd.read_csv(models/'split_assignments.csv',keep_default_na=False)
    test_rows=set(assignments[assignments['split']=='test'].source_row)
    test=frame[frame.source_row.isin(test_rows)]
    request={'rows':test[spec['features']['numeric_features']+spec['features']['categorical_features']].to_dict('records'),
             'expected_objective_id':spec['objective_id'],'expected_dataset_id':metadata['dataset_id'],'expected_dataset_version':metadata['dataset_version']}
    holdout=pd.read_csv(models/'holdout_predictions.csv',keep_default_na=False)
    new_results={};model_entries=[]
    for algorithm in evaluation['models']:
        artifact=models/(algorithm+'.joblib');sidecar=json.loads(artifact.with_name(algorithm+'.metadata.json').read_text())
        if digest(artifact)!=sidecar['artifact_sha256']:raise ValueError('new artifact does not match metadata')
        if not TabularRegressionInferenceAdapter().supports(sidecar):raise ValueError('model metadata does not match its inference adapter')
        answer=fresh_prediction(root,('prediction.tabular_regression','predict_tabular_regression'),artifact,request)
        prediction=np.asarray([row['prediction'] for row in answer['predictions']])
        expected=holdout[(holdout.algorithm==algorithm)&(holdout['split']=='test')].prediction.to_numpy()
        np.testing.assert_allclose(prediction,expected,rtol=1e-12,atol=1e-8)
        if answer['objective_id']!=spec['objective_id'] or not np.isfinite(prediction).all():raise ValueError('fresh-process output validation failed')
        recalculated=metrics(test.target_value,prediction,test.document_id)
        for key in ('mae','rmse','r2','smape_percent','document_macro_mae'):
            if not math.isclose(recalculated[key],sidecar['evaluation']['test'][key],rel_tol=1e-12,abs_tol=1e-8):raise ValueError('fresh-process metrics differ from stored evaluation')
        new_results[algorithm]={'artifact':str(artifact.relative_to(root)),'artifact_sha256':sidecar['artifact_sha256'],
            'fresh_process_loaded':True,'prediction_count':len(prediction),'matches_saved_holdout_predictions':True,'recalculated_test_metrics':recalculated,'response':answer}
        model_entries.append({'model_id':sidecar['model_identifier'],'model_version':sidecar['model_version'],'origin':'newly_trained_this_task',
            'business_target':sidecar['target_definition'],'dataset':{'dataset_id':metadata['dataset_id'],'version':metadata['dataset_version'],'sha256':metadata['dataset_sha256'],'path':str((data/'observations.csv').relative_to(root))},
            'training_observations':sidecar['training_observations'],'training_independent_groups':sidecar['training_independent_groups'],
            'eligible_observations':len(frame),'algorithm':algorithm,'test_metrics':recalculated,'baseline_comparison':sidecar['evaluation']['baselines']['test'],
            'artifact_path':str(artifact.relative_to(root)),'metadata_path':str(artifact.with_name(algorithm+'.metadata.json').relative_to(root)),
            'prediction_interface':'prediction.tabular_regression.predict_tabular_regression(input_data, model_path=...)',
            'inference_adapter':'tabular_regression_v1','status':'exploratory; not preferred to the predefined item/quantity baseline',
            'business_approved':False,'fresh_process_verified':True,'limitations':sidecar['known_limitations']})
    write_json(evaluation_directory/'new_model_verification.json',new_results)
    write_json(evaluation_directory/'test_features_request.json',request)
    example={**request,'rows':request['rows'][:2]};write_json(evaluation_directory/'example_request.json',example)
    for algorithm in evaluation['models']:
        answer=fresh_prediction(root,('prediction.tabular_regression','predict_tabular_regression'),models/(algorithm+'.joblib'),example)
        write_json(evaluation_directory/(algorithm+'_example_response.json'),answer)

    existing_data=root/'data/nop_confirmed_date_invoice_count_exploratory.csv'
    observed={row['period']:float(row['target_count']) for row in csv.DictReader(existing_data.open(encoding='utf-8-sig'))}
    existing_results,existing_predictions={},[]
    old_dir=root/'models/business_forecasting/nop_confirmed_date_invoice_subset'
    for algorithm in ('linear_regression','random_forest'):
        artifact=old_dir/(algorithm+'.joblib');sidecar=json.loads(artifact.with_name(algorithm+'.metadata.json').read_text())
        if digest(artifact)!=sidecar['artifact_sha256']:raise ValueError('existing artifact integrity failed')
        stored=sidecar['evaluation'];periods=stored['test_periods'];actual=[observed[period] for period in periods]
        score=metrics(actual,stored['test_predictions'],periods);baseline=metrics(actual,stored['baseline']['test_predictions'],periods)
        for key in ('mae','rmse'):
            if not math.isclose(score[key],stored['test'][key],rel_tol=1e-12):raise ValueError('existing evaluation evidence is inconsistent')
        answer=fresh_prediction(root,('prediction.monthly_regression','predict_monthly_objective'),artifact,{'periods_ahead':2})
        if answer['objective_id']!=sidecar['objective_id'] or not all(math.isfinite(point['prediction']) for point in answer['predictions']):raise ValueError('existing-model fresh prediction failed')
        existing_results[algorithm]={'artifact':str(artifact.relative_to(root)),'artifact_sha256':sidecar['artifact_sha256'],
            'retrained':False,'stored_test_metrics_recalculated':score,'baseline':baseline,'fresh_process_loaded':True,'response':answer}
        existing_predictions.extend({'algorithm':algorithm,'split':'test','period':period,'actual':value,'prediction':prediction,'baseline':base}
            for period,value,prediction,base in zip(periods,actual,stored['test_predictions'],stored['baseline']['test_predictions']))
        model_entries.append({'model_id':sidecar['model_identifier'],'model_version':sidecar['model_version'],'origin':'preexisting_preserved',
            'business_target':sidecar['target_definition'],'dataset':{'dataset_id':sidecar['objective_id'],'version':sidecar['source_provenance']['dataset_version'],'sha256':sidecar['dataset_sha256'],'path':str(existing_data.relative_to(root))},
            'training_observations':len(sidecar['training_periods']),'evaluation_training_observations':5,'eligible_observations':8,
            'algorithm':algorithm,'test_metrics':score,'baseline_comparison':baseline,'artifact_path':str(artifact.relative_to(root)),
            'metadata_path':str(artifact.with_name(algorithm+'.metadata.json').relative_to(root)),
            'prediction_interface':'prediction.monthly_regression.predict_monthly_objective(input_data, model_path=...)',
            'inference_adapter':'monthly_regression_v1','status':'exploratory; two-month test and worse than baseline',
            'business_approved':False,'fresh_process_verified':True,'limitations':sidecar['known_limitations']})
    write_json(evaluation_directory/'existing_model_verification.json',existing_results)
    with (evaluation_directory/'existing_monthly_holdout_predictions.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(existing_predictions[0]));writer.writeheader();writer.writerows(existing_predictions)

    blocked=[
        {'objective':'Additional larger-source line-value regression','sources':['Sales Invoice Details 1.xlsx'],
         'reason':'The strictly historical, reference-consistent source probe has only 37 distinct resolved dates. Large detail-row counts do not satisfy the predefined chronological date-diversity gates.',
         'minimum_requirement':'At least 60 valid distinct historical dates for the 60/20/20 date split, plus source/target-quality confirmation (23 more than the current 37). Do not merge alternate exports without verified source-overlap rules.'},
        {'objective':'Complete monthly invoice/document volume','sources':['Sales Invoice Details.xlsx','Sales Invoice Details 1.xlsx','GSTR1_Invoice.csv'],
         'reason':'Only the date-resolved subset is prepared; reference scope, lifecycle, unresolved dates and complete mature months remain unverified.',
         'minimum_requirement':'Resolve the 82 ambiguous-date references in the small source, approve document/event scope and completeness. For a nonseasonal monthly split supply at least 24 complete regular months (12 train, 6 validation, 6 test); longer history is needed for seasonality.'},
        {'objective':'Sales/order volume forecasting','sources':['Sales Order Report 1.xlsx','Sales Order Report 2.xlsx'],
         'reason':'Detail rows are not unique orders; mixed dates, repeated exports, lifecycle and complete historical periods are unresolved.',
         'minimum_requirement':'Validated order identity, event-date grammar, lifecycle and mature complete chronological periods; no row-as-order counting.'},
        {'objective':'Recognized revenue or monthly sales-value forecasting','sources':['Sales Invoice Details.xlsx','Sales Invoice Details 1.xlsx','GSTR1_Invoice.csv','GSTR1_Credit_Debit_Note 1.csv','GSTR1_Credit_Debit_Note 2.csv'],
         'reason':'Repeated document totals, alternate invoice representations, currency/tax bases, recognition and adjustment policies are not reconciled. The raw-field regression is not a revenue target.',
         'minimum_requirement':'Finance-confirmed line/document grain, currency and tax basis, credit/debit signs, recognition dates and a complete reconciled time series.'},
        {'objective':'Profit or margin','sources':['Sales Invoice Details.xlsx','Inventory Audit Report as on 200327.xlsx'],
         'reason':'No aligned validated realized costs and attributable expenses; inventory value-like fields do not establish realized invoice costs.',
         'minimum_requirement':'Recognized revenue, realized costs and attributable expenses aligned by period/entity/currency, with adjustment rules.'},
        {'objective':'Product/service demand','sources':['Sales Invoice Details.xlsx','Sales Invoice Details 1.xlsx','Sales Order Report 1.xlsx','Sales Order Report 2.xlsx','Item Master Lists 1.xlsx','Item Master Lists 2.xlsx'],
         'reason':'Raw Manual labels do not establish physical units; product identity, service quantities, returns/cancellations and complete item histories are unvalidated.',
         'minimum_requirement':'Approved product/service identity and units, complete dated event capture and return/cancellation treatment; no inferred latent demand.'},
        {'objective':'Inventory balance or stockout','sources':['Inventory Audit Report as on 200327.xlsx','Inventory Audit Report as on 200926.xlsx','Inventory Audit Report as on 200926 1.xlsx'],
         'reason':'Mixed movement/cumulative extracts, largely missing item identity on large-audit movement rows, unclear opening balances and sign/date semantics.',
         'minimum_requirement':'Stable item/warehouse identities, opening balances, signed dated movements and repeated verified stock snapshots.'},
        {'objective':'Customer repeat-purchase propensity','sources':['Customer Master Report 1.xlsx','Customer Master Report 2.xlsx','Sales Invoice Details.xlsx'],
         'reason':'No eligible historical cohort, matured positive and negative labels or point-in-time features; current master records are not outcome labels.',
         'minimum_requirement':'Validated customer links, cohort eligibility, observation/decision windows, complete outcomes and matured follow-up.'},
        {'objective':'Cancellation or delivery outcome','sources':['Sales Order Report 1.xlsx','Sales Order Report 2.xlsx'],
         'reason':'Current line status and promised dates do not establish actual lifecycle transitions or completed delivery outcomes.',
         'minimum_requirement':'Stable line/document identity, dated status transitions or actual delivery events, maturity/censoring and pre-outcome feature snapshots.'},
        {'objective':'Currency rate modeling','sources':['Exchange Rate.xlsx','Exchange Rate 1.xlsx'],
         'reason':'Existing source-authenticity evidence identifies explicit synthetic titles; these cannot be actual-NOP training data.',
         'minimum_requirement':'Genuine historical rates with publication timestamps, currency-pair semantics and verified source provenance.'}
    ]
    for row in blocked:row.update(status='blocked',artifact_path=None,business_approved=False)
    write_json(evaluation_directory/'blocked_objectives.json',blocked)
    catalogue={'catalogue_version':'1.0.0','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'models':model_entries,'blocked_objectives':blocked,'actual_model_count':len(model_entries),'newly_trained_models':2,'previously_existing_actual_models':2,
        'excluded_models':[{'artifact_path':'models/nop_invoice_volume_model.joblib','reason':'synthetic demonstration only; preserved and excluded from actual-NOP evaluation'}],
        'business_champion':None,'business_approved_models':0,'source_inventory':str(inventory_path.relative_to(root))}
    write_json(root/'models/model_catalogue.json',catalogue)
    columns=['model_id','business_target','dataset','training_observations','model_algorithm','evaluation_metrics','baseline_comparison','artifact_path','prediction_interface','status','limitations']
    with (root/'models/model_catalogue.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for entry in model_entries:
            writer.writerow({'model_id':entry['model_id'],'business_target':entry['business_target'],'dataset':entry['dataset']['dataset_id'],
                'training_observations':entry['training_observations'],'model_algorithm':entry['algorithm'],'evaluation_metrics':json.dumps(entry['test_metrics']),
                'baseline_comparison':json.dumps(entry['baseline_comparison']),'artifact_path':entry['artifact_path'],'prediction_interface':entry['prediction_interface'],
                'status':entry['status'],'limitations':json.dumps(entry['limitations'])})
        for entry in blocked:
            writer.writerow({'model_id':'blocked:'+entry['objective'],'business_target':entry['objective'],'status':'blocked',
                'limitations':entry['reason']+' Minimum requirement: '+entry['minimum_requirement']})
    changes=[path for path,value in before.items() if not (root/path).is_file() or digest(root/path)!=value]
    if changes:raise AssertionError('protected files changed: '+json.dumps(changes))
    all_models=[{'artifact_path':entry['artifact_path'],'sha256_matches_metadata':digest(root/entry['artifact_path'])==json.loads((root/entry['metadata_path']).read_text())['artifact_sha256']} for entry in model_entries]
    summary={'source_file_count':inventory['source_file_count'],'tables':inventory['table_count'],'fields':inventory['field_count'],
        'all_original_source_hashes_match':inventory['all_recorded_hashes_match'],'all_preexisting_protected_files_unchanged':not changes,
        'protected_files':len(before),'newly_trained_models':2,'existing_actual_models_preserved':2,'business_approved_models':0,
        'new_target_observations':metadata['included_rows'],'new_target_independent_references':metadata['included_references'],
        'fresh_process_models_verified':len(new_results)+len(existing_results),'model_artifact_checks':all_models,
        'catalogue':'models/model_catalogue.json','created_at_utc':datetime.now(timezone.utc).isoformat()}
    write_json(evaluation_directory/'delivery_verification.json',summary)
    print(json.dumps(summary,indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--evaluation',type=Path,default=Path('evaluation/actual_data_ml_training/v1'))
    arguments=parser.parse_args()
    run_delivery(arguments.root,arguments.evaluation)
