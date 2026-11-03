"""Fixed-cutoff baseline evaluation and persistence for an existing monthly target."""

import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor

from training.monthly_regression import _atomic_json,_atomic_joblib,_period_index
from training.tabular_regression import metrics,digest,_source_matches


def evaluate_monthly_baselines(dataset_path,specification,existing_evaluation_path,output_dir,*,project_root):
    dataset_path,output=Path(dataset_path),Path(output_dir)
    if output.exists():raise FileExistsError('use an unused baseline version directory')
    metadata=json.loads(dataset_path.with_name(dataset_path.stem+'.metadata.json').read_text());fingerprint=digest(dataset_path)
    if metadata['dataset_sha256']!=fingerprint or metadata['business_approved'] is not False:raise ValueError('invalid exploratory dataset provenance')
    _source_matches(metadata,project_root)
    frame=pd.read_csv(dataset_path,keep_default_na=False)
    frame=frame[frame[specification['eligibility_column']].isin(specification['eligible_values'])]
    periods=frame[specification['period_column']].astype(str).tolist();values=frame[specification['target_column']].to_numpy(dtype=float)
    parsed=[pd.Period(value,freq='M') for value in periods]
    if [str(value) for value in parsed]!=periods or periods!=sorted(set(periods)) or any(b.ordinal-a.ordinal!=1 for a,b in zip(parsed,parsed[1:])):raise ValueError('monthly observations must be canonical, unique, chronological and consecutive')
    if not np.isfinite(values).all() or (values<0).any():raise ValueError('invalid count target')
    original=json.loads(Path(existing_evaluation_path).read_text());test_periods=original['split']['test_periods']
    first=periods.index(test_periods[0]);history=values[:first];actual=values[first:]
    if periods[first:]!=test_periods or len(history)<3:raise ValueError('original fixed holdout cannot be reproduced')
    comparators={'last_observed_value':float(history[-1]),'moving_mean_2':float(history[-2:].mean()),'moving_mean_3':float(history[-3:].mean())}
    evaluated={};rows=[]
    for name,value in comparators.items():
        prediction=np.full(len(actual),value);evaluated[name]=metrics(actual,prediction,test_periods)
        rows.extend({'baseline':name,'period':period,'actual':float(target),'prediction':float(value),'horizon_step':step} for step,(period,target) in enumerate(zip(test_periods,actual),1))
    dependencies={'python':platform.python_version(),'scikit_learn':sklearn.__version__,'numpy':np.__version__,'pandas':pd.__version__,'joblib':joblib.__version__}
    estimator=DummyRegressor(strategy='constant',constant=float(values[-1])).fit((_period_index(periods)-parsed[0].ordinal).reshape(-1,1),values)
    identifier=specification['objective_id']+'-last_observed_value_baseline-v1.0.0'
    limitations=[*metadata['limitations'],'The two-period historical comparator is not a reliable forecast-performance estimate.']
    bundle={'artifact_format_version':1,'model':estimator,'model_identifier':identifier,'model_version':'1.0.0','objective_id':specification['objective_id'],
        'objective_name':specification['objective_name'],'target_definition':specification['target_definition'],'data_mode':metadata['data_mode'],'business_approved':False,
        'feature_names':['month_index'],'feature_origin_period':periods[0],'latest_source_period':metadata['observation_period']['end'],
        'training_end_period':periods[-1],'training_periods':periods,'dataset_sha256':fingerprint,'training_data_provenance':metadata,'known_limitations':limitations}
    output.mkdir(parents=True,exist_ok=False);artifact=output/'last_observed_value.joblib';_atomic_joblib(artifact,bundle)
    sidecar={'inference_adapter':'monthly_regression_v1','model_family':'baseline','model_identifier':identifier,'model_version':'1.0.0','algorithm':'last_observed_value_baseline',
        'objective_id':bundle['objective_id'],'target_definition':bundle['target_definition'],'data_mode':bundle['data_mode'],'business_approved':False,
        'artifact_path':artifact.relative_to(Path(project_root)).as_posix(),'artifact_sha256':digest(artifact),'dataset_sha256':fingerprint,'training_periods':periods,
        'source_provenance':metadata,'dependency_versions':dependencies,'known_limitations':limitations,'training_timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'evaluation':{'test':evaluated['last_observed_value'],'test_periods':test_periods,'test_evaluation_role':'historical fixed-cutoff baseline already inspected before this task','comparators':evaluated},
        'training_observations':len(values),'deployment_last_value':float(values[-1]),'evaluation_last_value':float(history[-1]),
        'feature_names':['month_index'],'feature_definition':'known calendar-month offset; ignored by the constant last-value estimator',
        'parameters':{'strategy':'constant','constant':float(values[-1])},'random_seed_not_applicable':True,
        'prediction_frequency':'month','supported_horizon':{'minimum':1,'maximum':24,'business_horizon_validated':False},'recommended_for_business_use':False,
        'input_schema':{'periods_ahead':'integer from 1 through 24'},'output_schema':'monthly regression forecast response with period and prediction',
        'refit_policy':'baseline state after evaluation uses all eight eligible source months; test comparator used only the earlier cutoff'}
    _atomic_json(output/'last_observed_value.metadata.json',sidecar)
    result={'test_periods':test_periods,'fixed_cutoff':periods[first-1],'comparators':evaluated,'seasonal_naive_status':'insufficient history for a 12-month lag',
        'business_champion':None,'artifact_path':sidecar['artifact_path'],'deployment_training_periods':periods,'deployment_value':float(values[-1]),
        'test_is_previously_seen':True,'horizon_protocol':'fixed two-step forecast; no actual test target is fed back as history'}
    _atomic_json(output/'evaluation_metrics.json',result)
    with (output/'historical_baseline_predictions.csv').open('x',encoding='utf-8',newline='') as stream:writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return result
