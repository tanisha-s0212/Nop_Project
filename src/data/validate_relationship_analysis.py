"""Independent output and notebook checks for the relationship assessment."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import nbformat
import pandas as pd
from openpyxl import load_workbook


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def excel_rows(path):
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        it=wb.active.iter_rows(values_only=True)
        header=next(it)
        return [dict(zip(header,row)) for row in it]
    finally:
        wb.close()


def validate(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    out=root/'reports/analysis'
    checks=[]
    def check(name,condition,detail=''):
        checks.append({'test':name,'passed':bool(condition),'detail':str(detail)})
        if not condition:raise AssertionError((name,detail))
    validation=json.loads((out/'analysis_validation.json').read_text(encoding='utf-8'))
    check('Engine checks passed',all(c['passed'] for c in validation['checks']))
    check('Scope complete',validation['tables']==20 and validation['identifier_candidates']==135 and validation['prior_comparisons_reconciled']==101)
    notebook=root/'notebooks/03_dataset_relationship_analysis.ipynb'
    n=nbformat.read(notebook,as_version=4);nbformat.validate(n)
    code=[c for c in n.cells if c.cell_type=='code']
    errors=[o for c in code for o in c.get('outputs',[]) if o.output_type=='error']
    check('Every notebook code cell executed',all(c.execution_count is not None for c in code))
    check('Notebook has no cell errors',not errors)
    counts=[c.execution_count for c in code]
    check('Fresh sequential notebook execution',counts==list(range(1,len(code)+1)),counts)
    check('Notebook ran full assessment',any('analysis.run()' in c.source for c in code))
    integrity=pd.read_csv(out/'protected_file_integrity.csv',keep_default_na=False)
    for r in integrity.itertuples(index=False):
        check('Protected hash '+r.path,digest(root/r.path)==r.sha256_before)
    rel=pd.read_csv(out/'relationship_candidates.csv',keep_default_na=False)
    joins=pd.read_csv(out/'controlled_join_validation.csv',keep_default_na=False)
    check('Controlled joins match candidate manifest',set(joins.relationship_id)==set(rel.loc[rel.controlled_join_tested==True,'relationship_id']))
    for r in joins.itertuples(index=False):
        expected=rel[rel.relationship_id==r.relationship_id].iloc[0]
        check('Stored row calculation '+r.relationship_id,r.actual_left_join_rows==expected.predicted_left_join_rows and r.actual_inner_join_rows==expected.predicted_inner_join_rows)
        check('Source rows retained '+r.relationship_id,r.actual_left_join_rows>=r.original_source_rows)
    # Independent direct source reads and Python frequency arithmetic for key examples.
    orders=excel_rows(root/'dataset/Sales Order Report 1.xlsx')
    customers=excel_rows(root/'dataset/Customer Master Report 1.xlsx')
    invoices=excel_rows(root/'dataset/Sales Invoice Details.xlsx')
    with (root/'dataset/GSTR1_Invoice.csv').open(encoding='utf-8-sig',newline='') as f:
        gst=list(csv.DictReader(f))
    def relation(source,target,source_cols,target_cols):
        rows=rel[(rel.source_table.str.startswith(source+' :: ')) & (rel.target_table.str.startswith(target+' :: ')) & (rel.key_mode=='raw')]
        rows=rows[rows.source_column.apply(json.loads).apply(lambda x:x==source_cols) & rows.target_column.apply(json.loads).apply(lambda x:x==target_cols)]
        check('Unique expected experiment '+source+' / '+str(source_cols),len(rows)==1)
        return rows.iloc[0]
    customer_counts=Counter(r['CUSTOMER CODE'] for r in customers)
    customer_experiment=relation('Sales Order Report 1.xlsx','Customer Master Report 1.xlsx',['Customer Code'],['CUSTOMER CODE'])
    expected_rows=sum(max(customer_counts[r['Customer Code']],1) for r in orders)
    check('Independent small customer lookup',expected_rows==len(orders)==customer_experiment.predicted_left_join_rows and all(customer_counts[r['Customer Code']]==1 for r in orders))
    scoped=[r['Doc_Series_Prefix']+r['Doc_Series']+r['Invoice_Number']+r['Doc_Series_Suffix'] for r in gst]
    invoice_counts=Counter(r['Invoice Num'] for r in invoices)
    gst_experiment=relation('GSTR1_Invoice.csv','Sales Invoice Details.xlsx',['@scoped_invoice'],['Invoice Num'])
    check('Independent GST scoped document coverage',sum(k in invoice_counts for k in scoped)==gst_experiment.matching_source_records)
    check('Independent GST detail fanout',sum(max(invoice_counts[k],1) for k in scoped)==gst_experiment.predicted_left_join_rows)
    check('Raw invoice number loses series scope',len(set(r['Invoice_Number'] for r in gst)) < len(set(scoped)))
    so_counts=Counter(r['SO No'] for r in orders)
    so_experiment=relation('Sales Invoice Details.xlsx','Sales Order Report 1.xlsx',['SO Num'],['SO No'])
    check('Independent invoice-order fanout',sum(max(so_counts[r['SO Num']],1) for r in invoices)==so_experiment.predicted_left_join_rows)
    # Read every generated workbook, verify sheet manifests and dimensions against CSVs.
    for filename in ('identifier_relationship_matrix.xlsx','dataset_granularity_report.xlsx'):
        expected=[v for v in validation['export_checks'] if v['workbook']==filename]
        wb=load_workbook(out/filename,read_only=True,data_only=False)
        try:
            check('Workbook tabs '+filename,wb.sheetnames==[v['sheet'] for v in expected])
            for entry in expected:
                ws=wb[entry['sheet']]
                check('Workbook dimensions '+entry['sheet'],ws.max_row==entry['rows']+1 and ws.max_column==entry['columns'])
                check('No exported formula/error cells '+entry['sheet'],not any(c.data_type in ('f','e') for row in ws for c in row))
        finally:wb.close()
    check('SVG valid',ET.parse(out/'data_model_diagram/logical_business_model.svg').getroot().tag.endswith('svg'))
    import matplotlib.pyplot as plt
    for name in ('data_model_diagram/logical_business_model.png','controlled_join_expansion.png'):
        check('PNG valid '+name,plt.imread(out/name).size>0)
    for md in (root/'README.md',out/'dataset_relationship_report.md',out/'data_model_diagram/README.md'):
        for link in re.findall(r'\]\(([^)]+)\)',md.read_text(encoding='utf-8')):
            if not re.match(r'^[a-z]+://|^#',link):
                check('Documentation link '+link,(md.parent/link.split('#')[0]).exists())
    result={'status':'passed','notebook':str(notebook.relative_to(root)),
        'executed_code_cells':len(code),'cell_errors':len(errors),'execution_counts':counts,
        'notebook_sha256':digest(notebook),'implementation_sha256':digest(root/'src/data/analyze_relationships.py'),
        'independent_validation_sha256':digest(Path(__file__)),
        'source_and_prior_evidence_hashes_unchanged':True,'checks':checks,
        'client_analysis_date':'2026-11-02','interpreter':sys.executable}
    (out/'notebook_execution_validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
    return result


if __name__=='__main__':validate()
