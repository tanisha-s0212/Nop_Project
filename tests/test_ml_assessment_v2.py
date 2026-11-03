"""ML assessment checks using immutable actual data and isolated estimator state."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

from prediction.tabular_estimators import QuantityMedianRegressor,QuantityNormalizedRidge
from prediction.tabular_regression import predict_tabular_regression
from prediction.monthly_regression import predict_monthly_objective
from prediction.model_adapters import MonthlyRegressionQueryAdapter,TabularRegressionInferenceAdapter
from training.tabular_regression import _weights

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'evaluation/actual_data_ml_assessment/v2'
MODELS=ROOT/'models/business_regression/nop_domestic_invoice_line_value/v2'


class MLAssessmentV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=pd.read_csv(ROOT/'data/nop_domestic_invoice_line_value/v1/observations.csv',keep_default_na=False,dtype={'item_code':str,'document_id':str})
        cls.spec=json.loads((ROOT/'data/nop_domestic_invoice_line_value/v1/training_spec.json').read_text())
        cls.plan=json.loads((EVIDENCE/'evaluation_plan.json').read_text());cls.study=json.loads((MODELS/'evaluation_metrics.json').read_text())
        cls.development=cls.data[~cls.data.source_row.isin(cls.plan['original_test_source_rows'])]
        cls.test=cls.data[cls.data.source_row.isin(cls.plan['original_test_source_rows'])]

    def test_all_original_sources_prepared_data_models_and_source_modules_preserved(self):
        before=json.loads((EVIDENCE/'protected_manifest_before.json').read_text())
        for path,value in before.items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),value,path)

    def test_csv_semantics_are_source_verified_not_inferred_from_column_names(self):
        audit=json.loads((EVIDENCE/'source_lineage_audit.json').read_text())
        self.assertTrue(audit['all_csv_rows_match_source']);self.assertEqual(audit['csv_rows_verified_against_source'],165)
        self.assertTrue(all(item['matches'] for item in audit['source_hash_checks']))

    def test_rolling_validation_never_contains_the_old_test_partition(self):
        predictions=pd.read_csv(MODELS/'rolling_origin_predictions.csv')
        self.assertFalse(set(predictions.source_row)&set(self.plan['original_test_source_rows']))
        source=self.data.set_index('source_row')
        for fold in self.plan['folds']:
            train=self.development[self.development.event_date.between(*fold['training_dates'])]
            valid=self.development[self.development.event_date.between(*fold['validation_dates'])]
            self.assertLess(train.event_date.max(),valid.event_date.min())
            self.assertFalse(set(train.document_id)&set(valid.document_id))
        for _,rows in predictions.groupby('candidate'):
            self.assertFalse(rows.source_row.duplicated().any())
            np.testing.assert_array_equal(rows.actual.to_numpy(),source.loc[rows.source_row,'target_value'].to_numpy())

    def test_fitted_baseline_exactly_reproduces_the_existing_reference_comparator(self):
        request={'rows':self.test[['quantity','item_code']].to_dict('records')}
        answer=predict_tabular_regression(request,model_path=MODELS/'item_quantity_median_baseline.joblib')
        old=pd.read_csv(ROOT/'models/business_regression/nop_domestic_invoice_line_value/v1/holdout_predictions.csv')
        old=old[(old.algorithm=='ridge_regression')&(old['split']=='test')]
        np.testing.assert_allclose([row['prediction'] for row in answer['predictions']],old.quantity_scaled_item_median.to_numpy())

    def test_baseline_unknown_item_fallback_is_training_only(self):
        baseline=QuantityMedianRegressor(self.spec['features'],'quantity','item_code').fit(self.development[['quantity','item_code']],self.development.target_value)
        expected=float(np.median(self.development.target_value/self.development.quantity))*2
        result=baseline.predict(pd.DataFrame([{'quantity':2,'item_code':'UNSEEN-CODE'}]))
        self.assertAlmostEqual(result[0],expected)

    def test_normalization_rejects_zero_quantity_and_missing_features(self):
        estimator=QuantityNormalizedRidge(self.spec['features'],'quantity')
        invalid=self.development[['quantity','item_code']].copy();invalid.iloc[0,0]=0
        with self.assertRaises(ValueError):estimator.fit(invalid,self.development.target_value)
        with self.assertRaises(ValueError):QuantityMedianRegressor(self.spec['features'],'quantity','item_code').fit(self.development[['quantity']],self.development.target_value)

    def test_normalized_estimator_is_reproducible_without_refitting_a_saved_artifact(self):
        fitted=QuantityNormalizedRidge(self.spec['features'],'quantity',alpha=1.0).fit(self.development[['quantity','item_code']],self.development.target_value,sample_weight=_weights(self.development,'document_id'))
        bundle=joblib.load(MODELS/'quantity_normalized_ridge.joblib')
        np.testing.assert_allclose(fitted.predict(self.test[['quantity','item_code']]),bundle['model'].predict(self.test[['quantity','item_code']]),rtol=1e-12,atol=1e-8)

    def test_previously_seen_test_audit_is_never_marked_as_new_independent_validation(self):
        self.assertFalse(self.study['new_independent_test_available']);self.assertFalse(self.study['original_test_used_for_tuning'])
        for result in self.study['models'].values():
            self.assertFalse(result['independent_new_test']);self.assertIn('retrospective',result['test_evaluation_role'])

    def test_monthly_baselines_use_identical_fixed_cutoff_and_test_periods(self):
        folder=ROOT/'models/business_forecasting/nop_confirmed_date_invoice_subset/baselines/v1'
        comparison=pd.read_csv(folder/'historical_baseline_predictions.csv')
        for _,rows in comparison.groupby('baseline'):
            self.assertEqual(rows.period.tolist(),['2026-07','2026-08'])
            self.assertEqual(rows.horizon_step.tolist(),[1,2]);self.assertEqual(rows.prediction.nunique(),1)
        answer=predict_monthly_objective({'periods_ahead':2},model_path=folder/'last_observed_value.joblib')
        self.assertEqual([point['prediction'] for point in answer['predictions']],[8.0,8.0])

    def test_all_catalogued_artifacts_have_one_compatible_adapter_and_fresh_process_evidence(self):
        catalogue=json.loads((ROOT/'models/model_catalogue.json').read_text());records=json.loads((EVIDENCE/'all_model_inference_verification.json').read_text())
        self.assertEqual(len(records),7);self.assertEqual(catalogue['baseline_predictor_count'],2)
        self.assertTrue(all(record['fresh_process_loaded'] for record in records))
        for entry in catalogue['models']:
            metadata=json.loads((ROOT/entry['metadata_path']).read_text());adapters=[MonthlyRegressionQueryAdapter(),TabularRegressionInferenceAdapter()]
            self.assertEqual(sum(adapter.supports(metadata) for adapter in adapters),1)
            self.assertEqual(hashlib.sha256((ROOT/entry['artifact_path']).read_bytes()).hexdigest(),metadata['artifact_sha256'])

    def test_custom_estimator_loads_without_the_training_orchestration_modules(self):
        code="import json,sys; from prediction.tabular_regression import predict_tabular_regression; r=predict_tabular_regression({'rows':[{'quantity':2,'item_code':'FG00100'}]},model_path=sys.argv[1]); assert 'training.improve_tabular_models' not in sys.modules; assert 'training.tabular_regression' not in sys.modules; print(json.dumps(r,allow_nan=False))"
        process=subprocess.run([sys.executable,'-c',code,str(MODELS/'quantity_normalized_ridge.joblib')],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True,check=True)
        answer=json.loads(process.stdout);self.assertEqual(len(answer['predictions']),1);self.assertFalse(answer['business_approved'])

    def test_reproduction_uses_an_unused_version_and_preserves_registered_artifacts(self):
        from training.improve_tabular_models import assess_and_improve
        with tempfile.TemporaryDirectory(dir=EVIDENCE) as directory:
            output=Path(directory)/'reproduction'
            arguments=(ROOT/'data/nop_domestic_invoice_line_value/v1/observations.csv',self.spec,
                ROOT/'models/business_regression/nop_domestic_invoice_line_value/v1/split_assignments.csv',EVIDENCE/'evaluation_plan.json',output)
            result=assess_and_improve(*arguments,project_root=ROOT,version='2.0.0-reproduction')
            self.assertEqual(result['pooled_rolling_origin'],self.study['pooled_rolling_origin'])
            metadata=json.loads((output/'quantity_normalized_ridge.metadata.json').read_text())
            self.assertEqual(metadata['model_version'],'2.0.0-reproduction')
            self.assertIn('rows',metadata['input_schema'])
            self.assertIn('sample_weighting',metadata['training_configuration'])
            self.assertFalse(metadata['output_schema']['business_approved'])
            with self.assertRaises(FileExistsError):assess_and_improve(*arguments,project_root=ROOT)

    def test_monthly_baseline_reproduction_preserves_evaluation_and_input_contract(self):
        from training.evaluate_monthly_baselines import evaluate_monthly_baselines
        spec=json.loads((ROOT/'data/nop_confirmed_date_invoice_count_exploratory.spec.json').read_text())
        with tempfile.TemporaryDirectory(dir=EVIDENCE) as directory:
            output=Path(directory)/'monthly'
            result=evaluate_monthly_baselines(ROOT/'data/nop_confirmed_date_invoice_count_exploratory.csv',spec,
                ROOT/'models/business_forecasting/nop_confirmed_date_invoice_subset/evaluation_metrics.json',output,project_root=ROOT)
            self.assertEqual(result['comparators']['last_observed_value']['mae'],7.0)
            metadata=json.loads((output/'last_observed_value.metadata.json').read_text())
            self.assertEqual(metadata['feature_names'],['month_index'])
            self.assertEqual(metadata['parameters']['constant'],8.0)
            answer=predict_monthly_objective({'periods_ahead':2},model_path=output/'last_observed_value.joblib')
            self.assertEqual([row['prediction'] for row in answer['predictions']],[8.0,8.0])


if __name__=='__main__':unittest.main()
