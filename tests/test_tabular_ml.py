"""Isolated software fixtures plus read-only preservation checks; no business metrics."""

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
from openpyxl import Workbook

from features.prepare_invoice_line_value import prepare_line_value
from features.tabular_regression import feature_frame
from training.tabular_regression import train_tabular_regressors, split_chronologically, metrics, _baseline
from prediction.tabular_regression import predict_tabular_regression
from prediction.model_adapters import TabularRegressionInferenceAdapter

ROOT=Path(__file__).resolve().parents[1]


class TabularMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        spec=json.loads((ROOT/'data/preparation_specs/nop_domestic_invoice_line_value_v1.json').read_text())
        spec.update(source_file='fixture.xlsx',dataset_id='fixture-line-value',objective_id='fixture-line-value',data_mode='exploratory_fixture')
        spec['columns']={alias:'unseen_'+alias for alias in spec['columns']}
        book=Workbook();sheet=book.active;sheet.title=spec['source_sheet'];aliases=list(spec['columns'])
        sheet.append([spec['columns'][alias] for alias in aliases])
        days=[date(2025,1,13)+timedelta(days=i) for i in range(19)]+[date(2025,2,13)]
        for index,day in enumerate(days):
            q=1+index%3; price=100*(1+index%4)
            values={'document_id':f'R-{index}','event_date':day.strftime('%d/%m/%Y'),'quantity':q,'item_code':f'P-{index%4}',
                    'target_value':q*price,'unit_price_diagnostic':price,**spec['population']}
            sheet.append([values[alias] for alias in aliases]);sheet.append([values[alias] for alias in aliases])
        bad={'document_id':'AMBIG','event_date':'01/02/2025','quantity':1,'item_code':'P-X','target_value':100,'unit_price_diagnostic':100,**spec['population']}
        sheet.append([bad[alias] for alias in aliases])
        bad['event_date']='13/02/2025';sheet.append([bad[alias] for alias in aliases])
        book.save(cls.root/'fixture.xlsx');book.close()
        spec_path=cls.root/'prep.json';spec_path.write_text(json.dumps(spec))
        cls.metadata=prepare_line_value(cls.root,spec_path,cls.root/'data')
        cls.spec=json.loads((cls.root/'data/training_spec.json').read_text())
        cls.spec['minimum_groups']={'train':10,'validation':3,'test':3}
        cls.spec['minimum_days']={'train':10,'validation':3,'test':3}
        cls.dataset=cls.root/'data/observations.csv';cls.output=cls.root/'models/v1'
        cls.evaluation=train_tabular_regressors(cls.dataset,cls.spec,cls.output,project_root=cls.root,seed=19)
        cls.frame=pd.read_csv(cls.dataset,keep_default_na=False)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_preparation_preserves_duplicate_lines_and_excludes_whole_ambiguous_reference(self):
        self.assertEqual(self.metadata['included_rows'],40)
        self.assertEqual(self.metadata['included_references'],20)
        self.assertEqual(self.metadata['excluded_rows'],2)
        self.assertEqual(self.metadata['duplicate_source_rows_preserved'],20)
        self.assertFalse(self.metadata['arithmetic_diagnostic']['used_for_filtering'])
        self.assertTrue(self.metadata['row_reconciliation_passed'])

    def test_feature_schema_rejects_missing_invalid_and_post_outcome_fields(self):
        schema=self.spec['features']
        for row in ({'quantity':float('nan'),'item_code':'P-1'}, {'quantity':'1','item_code':'P-1'},
                    {'quantity':-1,'item_code':'P-1'}, {'quantity':1,'item_code':''}, {'quantity':1,'item_code':'P-1','target_value':100}):
            with self.assertRaises(ValueError):feature_frame([row],schema)
        self.assertEqual(list(feature_frame([{'item_code':'P-1','quantity':1}],schema).columns),['quantity','item_code'])

    def test_splits_are_chronological_and_document_disjoint(self):
        splits,description=split_chronologically(self.frame,self.spec)
        self.assertLess(description['train']['end'],description['validation']['start'])
        self.assertLess(description['validation']['end'],description['test']['start'])
        self.assertFalse(set(splits['train']['document_id']) & set(splits['test']['document_id']))
        self.assertEqual(self.evaluation['saved_fit']['rows'],32)

    def test_insufficient_independent_history_never_creates_artifact(self):
        spec=deepcopy(self.spec);spec['minimum_groups']['test']=1000
        path=self.root/'models/blocked'
        with self.assertRaisesRegex(ValueError,'insufficient independent'):
            train_tabular_regressors(self.dataset,spec,path,project_root=self.root)
        self.assertFalse(path.exists())

    def test_target_and_reference_features_are_rejected(self):
        spec=deepcopy(self.spec);spec['features']['numeric_features'].append('target_value')
        with self.assertRaisesRegex(ValueError,'cannot be input features'):
            train_tabular_regressors(self.dataset,spec,self.root/'models/leakage',project_root=self.root)

    def test_baseline_does_not_use_requested_targets(self):
        splits,_=split_chronologically(self.frame,self.spec)
        first=_baseline(splits['train'],splits['test'],self.spec)
        changed=splits['test'].copy();changed['target_value']=999999
        second=_baseline(splits['train'],changed,self.spec)
        for name in first:np.testing.assert_array_equal(first[name],second[name])

    def test_zero_safe_metrics(self):
        values=metrics([0,2],[0,1],['a','b'])
        self.assertTrue(np.isfinite(values['smape_percent']))
        self.assertEqual(values['mae'],0.5)
        self.assertIsNone(metrics([0],[0],['a'])['r2'])

    def test_adapter_and_independent_fresh_process_match_saved_test_predictions(self):
        heldout=pd.read_csv(self.output/'holdout_predictions.csv')
        splits,_=split_chronologically(self.frame,self.spec)
        rows=splits['test'][['quantity','item_code']].to_dict('records')
        for name in self.evaluation['models']:
            artifact=self.output/(name+'.joblib')
            meta=json.loads(artifact.with_name(name+'.metadata.json').read_text())
            adapter=TabularRegressionInferenceAdapter();self.assertTrue(adapter.supports(meta))
            expected=heldout[(heldout.algorithm==name)&(heldout.split=='test')].prediction.to_numpy()
            request={'rows':rows,'expected_dataset_id':'fixture-line-value','expected_dataset_version':'1.0.0'}
            result=adapter.predict(artifact,request)
            np.testing.assert_allclose([point['prediction'] for point in result['predictions']],expected)
            code="import json,sys; from prediction.tabular_regression import predict_tabular_regression; print(json.dumps(predict_tabular_regression(json.loads(sys.argv[2]),model_path=sys.argv[1]),allow_nan=False))"
            completed=subprocess.run([sys.executable,'-c',code,str(artifact),json.dumps(request)],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True,check=True)
            fresh=json.loads(completed.stdout)
            np.testing.assert_allclose([point['prediction'] for point in fresh['predictions']],expected)

    def test_inference_rejects_wrong_target_and_reports_unknown_categories(self):
        artifact=self.output/'ridge_regression.joblib'
        with self.assertRaisesRegex(ValueError,'does not match'):
            predict_tabular_regression({'rows':[{'quantity':1,'item_code':'P-1'}],'expected_objective_id':'revenue'},model_path=artifact)
        result=predict_tabular_regression({'rows':[{'quantity':1,'item_code':'NEVER-SEEN'}]},model_path=artifact)
        self.assertEqual(result['unseen_categorical_rows'],1)
        self.assertFalse(result['business_approved'])

    def test_tampering_and_semantic_relabeling_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'ridge_regression.joblib';sidecar=artifact.with_name('ridge_regression.metadata.json')
            shutil.copy2(self.output/artifact.name,artifact);shutil.copy2(self.output/sidecar.name,sidecar)
            metadata=json.loads(sidecar.read_text());metadata['target_definition']='Recognized revenue';sidecar.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'contract mismatch'):
                predict_tabular_regression({'rows':[{'quantity':1,'item_code':'P-1'}]},model_path=artifact)
            shutil.copy2(self.output/sidecar.name,sidecar);artifact.write_bytes(artifact.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'integrity'):
                predict_tabular_regression({'rows':[{'quantity':1,'item_code':'P-1'}]},model_path=artifact)

    def test_fixed_seed_is_reproducible_and_registered_version_is_preserved(self):
        second=train_tabular_regressors(self.dataset,self.spec,self.root/'models/v2',project_root=self.root,version='2',seed=19)
        for name in second['models']:
            self.assertEqual(second['models'][name]['test'],self.evaluation['models'][name]['test'])
        with self.assertRaises(FileExistsError):
            train_tabular_regressors(self.dataset,self.spec,self.output,project_root=self.root)

    def test_original_sources_existing_models_and_framework_are_unchanged(self):
        path=ROOT/'evaluation/actual_data_ml_training/v1/protected_manifest_before.json'
        manifest=json.loads(path.read_text())
        for relative,expected in manifest.items():
            self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),expected,relative)


if __name__=='__main__':unittest.main()
