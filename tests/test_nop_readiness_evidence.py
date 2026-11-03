"""Synthetic tests of assessment evidence tooling; never real-data preparation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from openpyxl import Workbook
from business_prediction.adapters import SourceConfig

path = Path(__file__).resolve().parents[1]/'reports/analysis/nop_readiness_evidence/assess_sources.py'
spec = importlib.util.spec_from_file_location('nop_readiness_evidence',path)
evidence = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)


class ReadinessEvidenceTests(unittest.TestCase):
    def test_unfamiliar_excel_schemas_types_missingness_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'unfamiliar.xlsx'
            workbook = Workbook(); first = workbook.active; first.title = 'opaque-grid'
            first.append(['ordinal_x','mixed_y','clock_z']); first.append([1,'text','03/04/2026']); first.append([2,8.5,'2026-05-13'])
            other = workbook.create_sheet('different-grid'); other.append(['flag','optional'])
            other.append([True,None]); other.append([False,'present']); workbook.save(path); workbook.close()
            before = evidence.sha256(path)
            result = evidence.inspect_source(path,SourceConfig('synthetic','unverified','test')).discovery_result
            self.assertEqual(len(result['tables']),2)
            self.assertTrue(result['tables'][0]['fields'][1]['observed']['mixed_types'])
            self.assertEqual(result['tables'][0]['fields'][2]['observed']['temporal_token_counts']['ambiguous_day_month_text'],1)
            self.assertEqual(sum(result['tables'][1]['fields'][1]['observed']['missing_counts'].values()),1)
            self.assertEqual(before,evidence.sha256(path))

    def test_csv_blank_duplicate_headers_invalid_dates_and_unapproved_hypotheses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'unknown.csv'
            path.write_text(',,tag,tag\n1,,03/04/2026,2026-02-30\n2,x,2026-06-13,not-a-date\n',encoding='utf-8')
            before = evidence.source_manifest(directory)
            fields = evidence.inspect_source(path,SourceConfig('synthetic','unverified','test')).discovery_result['tables'][0]['fields']
            self.assertTrue(fields[0]['blank_header']); self.assertTrue(fields[2]['duplicate_header'])
            self.assertEqual(fields[3]['observed']['temporal_token_counts']['invalid_calendar_token'],1)
            self.assertTrue(all(h['approval_status'] == 'unreviewed' for f in fields for h in f['hypotheses']))
            self.assertEqual(before,evidence.source_manifest(directory))

    def test_changed_or_unrecorded_sources_cannot_reuse_prior_evidence(self):
        self.assertTrue(evidence.reusable_prior('same','same'))
        self.assertFalse(evidence.reusable_prior('new','old')); self.assertFalse(evidence.reusable_prior('new',None))

    def test_confirmation_flag_and_owner_label_are_insufficient(self):
        row = {'decision_id':'opaque','decision_status':'Confirmed','business_approval_recorded':'True','confirmed_by':'caller-label'}
        self.assertEqual(evidence.unresolved_decisions([row]),[row])
        row.update({k:'recorded' for k in ('owner_answer','supporting_evidence_reference','approved_scope_version','confirmation_date')})
        self.assertEqual(evidence.unresolved_decisions([row]),[])
        self.assertFalse(evidence.technical_assessment()['execution_authorized'])

    def test_no_approved_target_never_becomes_training_readiness(self):
        result = evidence.technical_assessment()
        self.assertFalse(result['governed_assessment_engine_executed'])
        self.assertIsNone(result['target_without_approved_bindings']['selected'])
        self.assertEqual(result['target_without_approved_bindings']['findings'][0]['code'],'target_not_established')
        self.assertTrue(result['partial_intake_findings'])

    def test_technical_family_detection_does_not_establish_history_or_leakage_safety(self):
        probes = evidence.technical_assessment()['technical_probes']
        self.assertEqual([r['problem_type'] for r in probes],['analytics','forecasting','regression','classification',None])
        self.assertTrue(all(not r['data_readiness_established'] for r in probes))
        self.assertEqual(probes[-1]['findings'][0]['category'],'unsupported')

    def test_evidence_write_never_overwrites_previous_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'record.json'; evidence.write_new(path,{'status':'blocked'}); before = evidence.sha256(path)
            with self.assertRaises(FileExistsError): evidence.write_new(path,{'status':'ready'})
            self.assertEqual(before,evidence.sha256(path))


if __name__ == '__main__': unittest.main()
