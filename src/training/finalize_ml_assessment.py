"""Record ML assessment, inference evidence and versioned model inventories."""

import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from business_prediction.query_assets import model_assets,dataset_assets
from prediction.model_adapters import MonthlyRegressionQueryAdapter,TabularRegressionInferenceAdapter
from training.nop_actual_data_ml import fresh_prediction


def write_new(path,body):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(body,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')


def finalize_assessment(root,out):
    root,out=Path(root).resolve(),Path(out).resolve()
    prior=json.loads((out/'prior_model_catalogue.json').read_text())
    prior_ids={entry['model_id'] for entry in prior['models']}
    prior_by_id={entry['model_id']:entry for entry in prior['models']}
    assets,failures=model_assets(root/'models',root)
    if failures:raise ValueError('model-discovery failures: '+json.dumps(failures))
    datasets,dataset_failures=dataset_assets(root/'data',root)
    if dataset_failures:raise ValueError('dataset-discovery failures: '+json.dumps(dataset_failures))
    dataset_paths={asset['metadata']['dataset_id']:asset['path'].relative_to(root).as_posix() for asset in datasets}
    request=json.loads((root/'evaluation/actual_data_ml_training/v1/test_features_request.json').read_text())
    verification=[];entries=[]
    adapters=[MonthlyRegressionQueryAdapter(),TabularRegressionInferenceAdapter()]
    for asset in assets:
        metadata=asset['metadata'];path=asset['path'];identifier=metadata['model_identifier']
        supported=[adapter.adapter_id for adapter in adapters if adapter.supports(metadata)]
        if len(supported)!=1:raise ValueError('model must match exactly one inference adapter')
        tabular=supported[0]=='tabular_regression_v1'
        interface=('prediction.tabular_regression','predict_tabular_regression') if tabular else ('prediction.monthly_regression','predict_monthly_objective')
        answer=fresh_prediction(root,interface,path,request if tabular else {'periods_ahead':2})
        if answer['model_identifier']!=identifier or answer['business_approved'] is not False:raise ValueError('invalid inference identity/approval output')
        prediction=np.asarray([point['prediction'] for point in answer['predictions']])
        if not np.isfinite(prediction).all():raise ValueError('nonfinite inference output')
        check={'model_id':identifier,'fresh_process_loaded':True,'adapter':supported[0],'prediction_count':len(prediction),'response':answer}
        if tabular:
            report_path=path.parent/'holdout_predictions.csv'
            if report_path.exists():
                values=pd.read_csv(report_path);expected=values[(values.algorithm==metadata['algorithm'])&(values['split']=='test')].prediction.to_numpy()
            else:
                values=pd.read_csv(path.parent/'retrospective_audit_predictions.csv');expected=values[values.algorithm==metadata['algorithm']].prediction.to_numpy()
            np.testing.assert_allclose(prediction,expected,rtol=1e-12,atol=1e-8);check['matches_saved_test_or_audit_predictions']=True
        verification.append(check)
        evaluation=metadata.get('evaluation',{})
        baseline=metadata.get('model_family')=='baseline'
        legacy=identifier in prior_ids
        role=evaluation.get('test_evaluation_role','original historical test evidence')
        if baseline:status='Exploratory reference baseline; business use unapproved'
        elif not legacy:status='Rejected versus baseline on rolling-origin development; research artifact retained'
        else:status='Retained; did not beat its documented baseline'
        source=metadata.get('source_provenance',{})
        entries.append({'model_id':identifier,'model_version':metadata['model_version'],'objective_id':metadata['objective_id'],
            'business_target':metadata['target_definition'],'algorithm':metadata['algorithm'],'model_family':'baseline' if baseline else 'ML',
            'origin':'retained_from_previous_task' if legacy else 'created_in_current_assessment',
            'dataset':{'dataset_id':metadata.get('dataset_id',source.get('dataset_id')),'version':metadata.get('dataset_version',source.get('dataset_version')),
                       'sha256':metadata['dataset_sha256'],'source_file':source.get('source_file'),
                       'path':dataset_paths.get(metadata.get('dataset_id',source.get('dataset_id')))},
            'training_observations':metadata.get('training_observations',len(metadata.get('training_periods',[]))),
            'training_independent_groups':metadata.get('training_independent_groups'),
            'rolling_origin_metrics':evaluation.get('rolling_origin'),'test_or_audit_metrics':evaluation.get('test'),
            'test_metrics':evaluation.get('test'),'baseline_comparison':prior_by_id.get(identifier,{}).get('baseline_comparison'),
            'evaluation_role':role,'independent_new_test':evaluation.get('independent_new_test',False),
            'artifact_path':path.relative_to(root).as_posix(),'metadata_path':asset['sidecar'].relative_to(root).as_posix(),
            'prediction_interface':'.'.join(interface)+'(input_data, model_path=...)','inference_adapter':supported[0],
            'status':status,'business_approved':False,'fresh_process_verified':True,'limitations':metadata['known_limitations']})
    write_new(out/'all_model_inference_verification.json',verification)
    profile=json.loads((out/'csv_profile.json').read_text())
    feasible=[
        {'target':'Monthly document-volume forecasting','status':'Insufficient historical data','definition':'distinct source-scoped references per observed month; rows cannot be counted as unique business documents',
         'source':'original confirmed-date monthly dataset; new CSV has a different narrower population','fields':['document_id','event_date'],
         'aggregation':'distinct scoped references by month, only after identity/lifecycle/completeness review','observations':'10 observed months; 8 eligible interior months in the existing series',
         'required':'Confirmed document identity/event/lifecycle and complete mature periods; at least 24 complete monthly observations for a modest 12/6/6 split; existing eight months are not certified complete.'},
        {'target':'Monthly aggregate quantity forecasting','status':'Blocked pending business clarification','definition':'sum of quantities only within validated compatible product/unit populations',
         'source':'new CSV and invoice source','fields':['quantity','item_code','event_date'],'aggregation':'approved unit-compatible sums by month',
         'observations':'10 observed months; at most 8 interior buckets, not mature complete observations','required':'Physical units, source coverage, lifecycle, compatible aggregation and sufficient complete history. Manual is not a confirmed unit.'},
        {'target':'Item-level quantity forecasting','status':'Insufficient historical data','definition':'quantity per validated item and regular completed period',
         'source':'new CSV','fields':['quantity','item_code','event_date'],'aggregation':'per-item sums after unit/identity approval',
         'observations':f"{profile['items']} item codes; {profile['items_seen_once']} seen once; maximum {profile['max_item_months']} observed months per item",'required':'Validated item identity/units and substantially longer complete per-item series; no zero insertion for unobserved periods.'},
        {'target':'Monthly target-value forecasting','status':'Blocked pending business clarification','definition':'a specifically agreed additive monetary measure, not automatically revenue/profit',
         'source':'new CSV raw Taxable Value lineage','fields':['target_value','document_id','event_date'],'aggregation':'approved line-grain additive sums with currency, adjustment and completeness evidence',
         'observations':'10 partial observed buckets; insufficient complete regular history','required':'Target meaning, currency/tax/recognition basis, additive grain, adjustments, completeness and longer history.'},
        {'target':'Item-level target-value forecasting','status':'Insufficient historical data','definition':'approved item-period value measure with valid item identity and currency basis',
         'source':'new CSV','fields':['target_value','item_code','event_date'],'aggregation':'approved per-item period sums',
         'observations':f"maximum {profile['max_item_months']} observed months per item; median {profile['median_item_months']}",'required':'Long regular per-item history, approved value meaning and period completeness; future quantity is not available as a forecasting feature.'},
        {'target':'Offline stored line-value estimation','status':'Feasible with conditions','definition':'stored native Taxable Value for the explicitly retained source-row population',
         'source':'new CSV with verified original-workbook lineage','fields':['quantity','item_code','target_value'],
         'aggregation':'none; one estimate per supplied source-like feature record','observations':f"{profile['rows']} lines, {profile['references']} reference groups, {profile['observed_dates']} dates",
         'required':'Exploratory use only; currency/units/decision-time availability and prospective performance remain unapproved. Baseline outperforms ML candidates.'}
    ]
    write_new(out/'prediction_target_feasibility.json',feasible)
    catalogue={'catalogue_version':'2.0.0','created_at_utc':datetime.now(timezone.utc).isoformat(),'models':entries,
        'actual_predictor_count':len(entries),'actual_model_count':len(entries),'trained_ml_model_count':sum(entry['model_family']=='ML' for entry in entries),
        'baseline_predictor_count':sum(entry['model_family']=='baseline' for entry in entries),
        'current_task_new_ml_candidates':1,'current_task_new_baselines':2,'retained_actual_models':4,'business_champion':None,'business_approved_models':0,
        'prediction_target_feasibility':feasible,'blocked_objectives':prior['blocked_objectives'],'excluded_models':prior['excluded_models'],
        'previous_catalogue_snapshot':(out/'prior_model_catalogue.json').relative_to(root).as_posix()}
    # The index is mutable; every prior artifact and sidecar remains immutable.
    (root/'models/model_catalogue.json').write_text(json.dumps(catalogue,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with (root/'models/model_catalogue.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['model_id','family','target','version','algorithm','evaluation_role','mae','rmse','artifact_path','status']);writer.writeheader()
        for entry in entries:
            score=entry['test_or_audit_metrics'] or {};writer.writerow({'model_id':entry['model_id'],'family':entry['model_family'],'target':entry['business_target'],'version':entry['model_version'],'algorithm':entry['algorithm'],'evaluation_role':entry['evaluation_role'],'mae':score.get('mae'),'rmse':score.get('rmse'),'artifact_path':entry['artifact_path'],'status':entry['status']})
    lines=['# NOP ML model catalogue','','**Version:** 2.0.0. All entries are exploratory; no business-approved champion exists.','','Seven actual-source predictors comprise five ML models and two fitted baselines. The existing synthetic demonstration is preserved and excluded from these counts.','','| Algorithm / version | Family | Target / dataset | Evaluation | MAE | RMSE | Artifact | Status |','| --- | --- | --- | --- | ---: | ---: | --- | --- |']
    for entry in entries:
        score=entry['test_or_audit_metrics'] or {};label='stored line-value proxy' if entry['inference_adapter']=='tabular_regression_v1' else 'confirmed-date monthly reference count'
        lines.append(f"| {entry['algorithm']} / {entry['model_version']} | {entry['model_family']} | {label}; {entry['dataset']['dataset_id']} | {entry['evaluation_role']} | {score.get('mae',0):,.2f} | {score.get('rmse',0):,.2f} | [{Path(entry['artifact_path']).name}](../{entry['artifact_path']}) | {entry['status']} |")
    lines += ['','## Evaluation interpretation','','The v1 original test results were evaluated before this assessment. New v2 line-value scores on those same 30 rows are retrospective audits, not a new independent test. The v2 primary comparison uses three expanding-origin development folds: 79 predictions across 52 reference groups. The monthly comparison has only two test months and cannot support a reliability claim. Scores across line-value units and monthly counts are not comparable.','','## Requested prediction-target feasibility','','| Candidate | Status | Required evidence |','| --- | --- | --- |']
    lines += [f"| {item['target']} | {item['status']} | {item['required']} |" for item in feasible]
    lines += ['','## Inference and limitations','','Use `prediction.tabular_regression.predict_tabular_regression` for raw line-value predictors and `prediction.monthly_regression.predict_monthly_objective` for monthly predictors. All saved preprocessing/state is in the bundles. Match model/dataset versions and dependency metadata. Tabular requests contain positive numeric quantity and a raw item-code string. Monthly requests contain `periods_ahead` and start after the stored source cutoff.','','Currency, physical units, global document/product identity, complete source capture and business meanings are not approved. Reference groups are split-isolation units; wider statistical dependence can remain. Unseen item codes, sparse history and previously inspected holdouts restrict conclusions. See the [training report](nop_actual_data_ml_training_report.md) and [integration guide](../docs/development/nop_ml_model_integration_guide.md).','','[Machine-readable catalogue](../models/model_catalogue.json) · [Fresh-process evidence](../'+out.relative_to(root).as_posix()+'/all_model_inference_verification.json)']
    (root/'reports/nop_ml_model_catalogue.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    before=json.loads((out/'protected_manifest_before.json').read_text());changed=[path for path,value in before.items() if hashlib.sha256((root/path).read_bytes()).hexdigest()!=value]
    if changed:raise AssertionError('protected files changed: '+json.dumps(changed))
    summary={'actual_predictors':len(entries),'new_ml_candidates':1,'new_baselines':2,'retained_actual_models':4,'fresh_process_predictors_verified':len(verification),
        'protected_file_count':len(before),'protected_file_changes':changed,'original_source_files':len(list((root/'dataset').rglob('*.xlsx')))+len(list((root/'dataset').rglob('*.csv'))),'business_approved_models':0}
    write_new(out/'final_delivery_verification.json',summary)
    print(json.dumps(summary,indent=2));return catalogue


if __name__=='__main__':
    finalize_assessment(Path.cwd(),Path('evaluation/actual_data_ml_assessment/v2'))
