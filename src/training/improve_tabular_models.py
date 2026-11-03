"""Development-only rolling-origin assessment, with a separately labeled old-test audit."""

from datetime import datetime, timezone
from io import BytesIO
import csv
import hashlib
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn

from features.tabular_regression import feature_frame, feature_names
from prediction.tabular_estimators import QuantityMedianRegressor, QuantityNormalizedRidge
from training.tabular_regression import metrics, _weights, _source_matches, digest
from training.monthly_regression import _atomic_json, _atomic_joblib


def assess_and_improve(dataset_path,specification,original_split_path,plan_path,output_dir,*,project_root,version='2.0.0'):
    dataset_path,output=Path(dataset_path),Path(output_dir)
    if not isinstance(version,str) or not version.strip():raise ValueError('an explicit model version is required')
    if output.exists():raise FileExistsError('use an unused model assessment version')
    payload=dataset_path.read_bytes();fingerprint=hashlib.sha256(payload).hexdigest()
    metadata=json.loads(dataset_path.with_name(dataset_path.stem+'.metadata.json').read_text())
    plan=json.loads(Path(plan_path).read_text())
    if metadata['dataset_sha256']!=fingerprint or plan['dataset_sha256']!=fingerprint:raise ValueError('dataset fingerprint mismatch')
    if metadata['business_approved'] is not False or 'synthetic' in metadata['data_mode'].casefold():raise ValueError('invalid actual-source exploratory mode')
    _source_matches(metadata,project_root)
    names=feature_names(specification['features']);target=specification['target_column'];group=specification['group_column'];day=specification['date_column'];lineage=specification['lineage_column']
    if set(names)&set(specification['forbidden_features']):raise ValueError('forbidden input features')
    frame=pd.read_csv(BytesIO(payload),keep_default_na=False,dtype={group:str,day:str,**{name:str for name in specification['features']['categorical_features']}})
    feature_frame(frame[names].to_dict('records'),specification['features'])
    assignment=pd.read_csv(original_split_path,keep_default_na=False)
    if assignment.source_row.duplicated().any() or set(assignment.source_row)!=set(frame[lineage]):raise ValueError('split lineage mismatch')
    old_test=set(assignment[assignment['split']=='test'].source_row)
    if old_test!=set(plan['original_test_source_rows']):raise ValueError('original test partition changed')
    development=frame[~frame[lineage].isin(old_test)].copy();audit=frame[frame[lineage].isin(old_test)].copy()
    if set(development[group])&set(audit[group]) or development[day].max()>=audit[day].min():raise ValueError('old test exclusion failed')
    schema=specification['features'];quantity=specification['baseline']['quantity_field'];category=specification['baseline']['category_field']
    factories={'item_quantity_median_baseline':lambda:QuantityMedianRegressor(schema,quantity,category),
        'quantity_normalized_ridge_alpha_1':lambda:QuantityNormalizedRidge(schema,quantity,alpha=1.0),
        'quantity_normalized_ridge_alpha_10':lambda:QuantityNormalizedRidge(schema,quantity,alpha=10.0)}
    folds=[];predictions=[]
    for fold in plan['folds']:
        training=development[development[day].between(*fold['training_dates'])]
        validation=development[development[day].between(*fold['validation_dates'])]
        if training[group].nunique()<30 or validation[group].nunique()<8:raise ValueError('insufficient fold reference groups')
        if training[day].max()>=validation[day].min() or set(training[group])&set(validation[group]):raise ValueError('fold chronology/group leakage')
        if set(training[lineage])&old_test or set(validation[lineage])&old_test:raise ValueError('test rows entered development')
        scores={}
        for name,factory in factories.items():
            model=factory();model.fit(training[names],training[target],sample_weight=_weights(training,group))
            prediction=model.predict(validation[names]);scores[name]=metrics(validation[target],prediction,validation[group])
            for position,(_,row) in enumerate(validation.iterrows()):
                predictions.append({'candidate':name,'fold':fold['fold'],'source_row':row[lineage],'document_id':row[group],
                    'event_date':row[day],'actual':float(row[target]),'prediction':float(prediction[position])})
        folds.append({**fold,'metrics':scores})
    pooled={}
    for name in factories:
        rows=[row for row in predictions if row['candidate']==name]
        if len({row['source_row'] for row in rows})!=len(rows):raise ValueError('rolling validation rows overlap')
        pooled[name]=metrics([row['actual'] for row in rows],[row['prediction'] for row in rows],[row['document_id'] for row in rows])
    selected=min([name for name in factories if name!='item_quantity_median_baseline'],key=lambda name:pooled[name]['document_macro_mae'])
    versions={'python':platform.python_version(),'scikit_learn':sklearn.__version__,'numpy':np.__version__,'pandas':pd.__version__,'joblib':joblib.__version__}
    results={};models={};audit_records=[]
    for name,key in (('item_quantity_median_baseline','item_quantity_median_baseline'),('quantity_normalized_ridge',selected)):
        estimator=factories[key]();estimator.fit(development[names],development[target],sample_weight=_weights(development,group));models[name]=estimator
        prediction=estimator.predict(audit[names])
        results[name]={'algorithm':name,'selected_candidate':key,'rolling_origin':pooled[key],
            'test':metrics(audit[target],prediction,audit[group]),'test_evaluation_role':'retrospective audit; labels and v1 results were previously inspected',
            'independent_new_test':False,'cv_fold_wins_against_baseline':sum(fold['metrics'][key]['document_macro_mae']<fold['metrics']['item_quantity_median_baseline']['document_macro_mae'] for fold in folds),
            'parameters':{'alpha':estimator.alpha} if hasattr(estimator,'alpha') else {'group_statistic':'median target/quantity','fallback':'global median target/quantity'}}
        for position,(_,row) in enumerate(audit.iterrows()):audit_records.append({'algorithm':name,'source_row':row[lineage],'document_id':row[group],'event_date':row[day],'actual':float(row[target]),'prediction':float(prediction[position])})
    if digest(dataset_path)!=fingerprint:raise ValueError('dataset changed during assessment')
    _source_matches(metadata,project_root)
    output.mkdir(parents=True,exist_ok=False)
    for name,estimator in models.items():
        limitations=[*metadata['limitations'],'Development rolling-origin evidence is exploratory; the reused old test period is not independent validation for this experiment.']
        bundle={'artifact_format_version':1,'model':estimator,'model_identifier':metadata['objective_id']+'-'+name+'-v'+version,'model_version':version,
            'objective_id':metadata['objective_id'],'target_definition':metadata['target_definition'],'feature_schema':schema,'feature_names':names,'prediction_minimum':0.0,
            'dataset_id':metadata['dataset_id'],'dataset_version':metadata['dataset_version'],'dataset_sha256':fingerprint,'data_mode':metadata['data_mode'],
            'business_approved':False,'known_limitations':limitations,'source_provenance':metadata,'dependency_versions':versions,
            'known_categories':{name:sorted(set(development[name])) for name in schema['categorical_features']}}
        artifact=output/(name+'.joblib');_atomic_joblib(artifact,bundle)
        sidecar={key:value for key,value in bundle.items() if key not in {'model','known_categories'}}
        sidecar.update(inference_adapter='tabular_regression_v1',problem_type='regression',algorithm=name,model_family='baseline' if name=='item_quantity_median_baseline' else 'ML',
            artifact_path=artifact.resolve().relative_to(Path(project_root).resolve()).as_posix(),artifact_sha256=digest(artifact),evaluation=results[name],
            parameters=results[name]['parameters'],training_observations=len(development),training_independent_groups=int(development[group].nunique()),
            training_date_range={'start':development[day].min(),'end':development[day].max()},training_configuration={'selection':'rolling-origin development document-macro MAE','test_rows_excluded':True,'seed':20261103,
                'sample_weighting':'unweighted within-item and global medians, matching the original comparator' if name=='item_quantity_median_baseline' else 'inverse detail-row count per reference'},
            input_schema={'rows':'array of exact records following feature_schema','optional_identity_checks':['expected_objective_id','expected_dataset_id','expected_dataset_version']},
            output_schema={'predictions':[{'row_index':'integer','prediction':'finite number'}],'business_approved':False},
            target_transform='median target/quantity lookup, multiplied by supplied quantity' if name=='item_quantity_median_baseline' else 'Ridge target/quantity regression, multiplied by supplied quantity',
            prediction_frequency='one estimate per supplied feature row',supported_horizon=None,recommended_for_business_use=False,
            training_timestamp_utc=datetime.now(timezone.utc).isoformat())
        _atomic_json(output/(name+'.metadata.json'),sidecar);results[name]['artifact_path']=sidecar['artifact_path']
    assessment={'evaluation_plan':plan,'folds':folds,'pooled_rolling_origin':pooled,'selected_normalized_candidate':selected,'models':results,
        'business_champion':None,'new_independent_test_available':False,'original_test_used_for_tuning':False,'dataset_sha256':fingerprint}
    _atomic_json(output/'evaluation_metrics.json',assessment)
    for filename,rows in (('rolling_origin_predictions.csv',predictions),('retrospective_audit_predictions.csv',audit_records)):
        with (output/filename).open('x',encoding='utf-8',newline='') as stream:writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return assessment
