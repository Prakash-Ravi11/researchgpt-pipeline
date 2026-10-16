"""Synthetic positive/negative contracts; real PDF execution is separate."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from src.evidence import verifier as V
from src.evidence import gate as G
from src.evidence.monitor import ExtractionTrace
from src.evaluation.extraction_repair import evaluate_acceptance

FIXTURE=json.loads((Path(__file__).parent/'fixtures/target_extraction_acceptance.json').read_text(encoding='utf-8'))


def supported_case():
    required=deepcopy(FIXTURE['required_rows'])
    for metric,left,right in [('EM',34.1,38.8),('F1',40.2,46.9)]:
        for method,retriever,value in [('SIM-RAGfull','BM25',left),('Auto-RAG','E5',right)]:
            required.append({'method':method,'configuration':{'llm':'Llama3','retriever':retriever},
                'dataset':'2WikiMultiHopQA','metric':metric,'value':value})
    cells=[]
    for i,row in enumerate(required,1):
        cells.append({'cell_id':f'synthetic:table1:r{i}:c1','row':i,'col':1,'method':row['method'],
            'configuration':row['configuration']['llm']+'/'+row['configuration']['retriever'],
            'dataset':row['dataset'],'metric':row['metric'],'value':str(row['value']),
            'page':'p7','bbox':[10.,float(i*20),20.,float(i*20+10)]})
    def chunk(cid,text,page,section,start):
        return {'chunk_id':cid,'paper_id':'synthetic','text':text,'page_or_node':page,'section':section,
                'char_start':start,'char_end':start+len(text),'block_id':cid,'block_type':'paragraph',
                'source':'synthetic','representation':'pdf'}
    chunks=[chunk('intro','We propose SIM-RAG, a new retrieval framework.','p1','method',0),
            chunk('table','A synthetic unit-test table, not production PDF parsing.','p7','results',100)]
    chunks[-1]['association_tables']=[{'table_id':'synthetic:table1','page':'p7','cells':cells}]
    for i,review in enumerate(FIXTURE['limitation_reviews']):
        chunks.append(chunk('limit'+str(i),review['text'],'p9','discussion',1000+i*1000))
    repaired,validation=V.grounded_field_repair({'limitations':'An unverified model inference.'},chunks)
    assert not validation['rejections']
    return repaired['_association_evidence'],chunks


def evaluate(payload,chunks):
    return evaluate_acceptance(payload,chunks,FIXTURE,source_sha256=FIXTURE['source_sha256'])


def codes(report):return {r['code'] for r in report['rejections']}


def test_supported_positive_fixture_passes_before_negative_tests():
    payload,chunks=supported_case()
    report=evaluate(payload,chunks)
    assert report['complete'],report
    assert report['matched_required_tuples']==6
    assert len(report['supported_limitations'])==3
    assert V.validate_comparisons(payload['comparisons'],V.source_rows(chunks))==[]


@pytest.mark.parametrize('metric',['EM','F1'])
def test_missing_required_metric_has_specific_reason(metric):
    payload,chunks=supported_case()
    payload['metrics']['values'].remove(metric)
    assert 'missing_required_metrics' in codes(evaluate(payload,chunks))


@pytest.mark.parametrize('label',['TEMPERATURE','F10'])
def test_bogus_substring_metric_aliases_do_not_pass(label):
    payload,chunks=supported_case();payload['metrics']['values']=[label]
    assert 'metric_alias_invalid' in codes(evaluate(payload,chunks))


@pytest.mark.parametrize('change,reason',[
    (lambda r:r.update(value=70.5),'value_or_unit_mismatch'),
    (lambda r:r['configuration'].update(llm='Llama3'),'method_configuration_dataset_metric_mismatch'),
    (lambda r:r['configuration'].update(retriever='E5'),'method_configuration_dataset_metric_mismatch'),
    (lambda r:r.update(method='SIM-RAGlite'),'method_configuration_dataset_metric_mismatch'),
    (lambda r:r['source'].update(page=99),'source_page_mismatch'),
    (lambda r:r['source'].update(table_id='invented'),'source_table_mismatch'),
    (lambda r:r['source'].update(cell_id='missing'),'unknown_source_cell'),
    (lambda r:r['source'].update(row=True),'source_cell_coordinate_mismatch'),
    (lambda r:r['source'].update(bbox=[0,0,0,0]),'source_bbox_mismatch')])
def test_bad_associations_reject_for_intended_reason(change,reason):
    payload,chunks=supported_case();change(payload['results']['rows'][0])
    assert reason in codes(evaluate(payload,chunks))


def test_duplicate_and_conflicting_rows_reject_without_confusing_baseline():
    for value,reason in [(77.5,'duplicate_row'),(70.5,'conflicting_row')]:
        payload,chunks=supported_case();extra=deepcopy(payload['results']['rows'][0]);extra['value']=value
        payload['results']['rows'].append(extra)
        assert reason in codes(evaluate(payload,chunks))


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-float('inf')])
def test_nonfinite_or_boolean_numeric_values_have_structured_rejections(value):
    payload,chunks=supported_case();payload['results']['rows'][0]['value']=value
    assert 'numeric_value_type' in codes(evaluate(payload,chunks))


@pytest.mark.parametrize('claim',[
    'Our synthetic data may not reflect the full complexity of real-world scenarios.',
    'Our critic has no context length constraint and we do not limit search rounds.'])
def test_unsupported_or_contradictory_limitations_sharing_keywords_reject(claim):
    payload,chunks=supported_case();item=payload['limitations']['values'][0]
    item.update(text=claim,verified=True,semantic_approved=True)
    assert 'limitation_not_source_quote' in codes(evaluate(payload,chunks))


def test_wrong_limitation_offsets_reject():
    payload,chunks=supported_case();payload['limitations']['values'][0]['source']['char_start']+=1
    assert 'limitation_span_mismatch' in codes(evaluate(payload,chunks))


def test_reversed_comparison_with_correct_values_rejects():
    payload,chunks=supported_case();payload['comparisons'][0]['winner']='SIM-RAGfull'
    assert 'comparison_direction_reversed' in codes(evaluate(payload,chunks))


def test_missing_comparative_evidence_is_incomplete():
    payload,chunks=supported_case();payload['comparisons']=[]
    assert 'required_comparative_evidence_missing' in codes(evaluate(payload,chunks))


@pytest.mark.parametrize('mutate,reason',[
    (lambda p:p['results'].update(rows=None),'collection_type'),
    (lambda p:p['datasets'].update(values=None),'collection_type'),
    (lambda p:p['datasets'].update(status={'bad':True}),'invalid_status'),
    (lambda p:p['metrics'].update(values=[True]),'label_type'),
    (lambda p:p['results']['rows'].__setitem__(0,None),'row_type')])
def test_malformed_nested_types_return_reasons_not_crashes(mutate,reason):
    payload,chunks=supported_case();mutate(payload)
    assert reason in codes(evaluate(payload,chunks))


@pytest.mark.parametrize('page',[7,'7','p7','07','P07'])
def test_integer_and_string_page_ids_resolve_consistently(page):
    payload,chunks=supported_case()
    for row in payload['results']['rows']:row['source']['page']=page
    verdict=V.validate_associated_evidence(payload,chunks)
    assert not verdict['rejections']
    assert V.normalize_page_id(page)=='p7'


def test_absence_is_not_inferred_from_limited_evidence():
    payload,chunks=supported_case();payload['datasets']['status']='not_reported'
    assert 'absence_requires_source_inspection' in codes(evaluate(payload,chunks))


def test_unresolved_semantic_support_never_counts_as_verified_acceptance():
    payload,chunks=supported_case()
    altered=deepcopy(FIXTURE);altered['limitation_reviews']=[]
    report=evaluate_acceptance(payload,chunks,altered,source_sha256=FIXTURE['source_sha256'])
    assert not report['complete'] and 'limitation_semantic_support_unresolved' in codes(report)


def test_trace_writes_and_finalization_failures_do_not_fake_storage(tmp_path,monkeypatch):
    trace=ExtractionTrace(tmp_path,{'source_sha256':'test'})
    import src.evidence.monitor as M
    monkeypatch.setattr(M,'atomic_json_write',lambda *a:(_ for _ in ()).throw(OSError('storage failed')))
    assert not trace.emit('valid_name',{'evidence':'quoted "text" ?'})
    assert trace.checkpoints[-1]['stored'] is False
    assert not trace.finish('completed') and trace.state=='finalization_failed'
    assert len(trace.errors)==2
    assert not trace.emit('../invalid',{})


def test_source_quoted_strings_survive_atomic_utf8_trace(tmp_path):
    trace=ExtractionTrace(tmp_path,{})
    text='"73%" '+chr(92)+' '+chr(956)+chr(10)+'unchanged'
    assert trace.emit('literal',{'evidence':text})
    saved=json.loads(Path(trace.checkpoints[-1]['path']).read_text(encoding='utf-8'))
    assert saved['data']['evidence']==text


def test_prose_only_numeric_gate_is_preserved_and_model_inferences_separated():
    claim='Our method achieves a Dice score of 0.87.'
    chunk={'chunk_id':'p:1','paper_id':'p','text':claim,'char_start':100,'char_end':100+len(claim),
        'block_id':'p:1','block_type':'paragraph','source':'test','representation':'pdf','section':'results','page_or_node':'p1'}
    original={'results':claim,'metrics':[],'datasets':[],'limitations':'A reviewer inference.'}
    repaired,_=V.grounded_field_repair(original,[chunk])
    before=G.gate_paper(original,[chunk],G.FULL_TEXT,[])
    after=G.gate_paper(repaired,[chunk],G.FULL_TEXT,[])
    assert before['results']==after['results']==claim
    assert after['limitations']=='' and after['reviewer_inferences']==['A reviewer inference.']



def test_pdf_source_checker_keeps_method_before_raised_citation(monkeypatch):
    import pymupdf
    from src.evaluation.extraction_repair import verify_pdf_locations
    words=[(50.,40.,112.,50.,'StandardRAG',0,0,0),
           (120.,39.8,140.,49.8,'[14]',0,0,1),
           (170.,40.,230.,50.,'Llama3/E5',0,1,0),
           (300.,40.,322.,50.,'58.9',0,2,0),
           (300.,10.,340.,20.,'TriviaQA',0,3,0),
           (300.,25.,312.,35.,'EM',0,4,0)]
    cell={'cell_id':'unit:table1:r1:c1','row':1,'col':1,'method':'StandardRAG [14]',
        'configuration':'Llama3/E5','dataset':'TriviaQA','metric':'EM','value':'58.9','page':'p7',
        'bbox':[300.,40.,322.,50.],'method_bbox':[50.,39.8,140.,50.],
        'configuration_bbox':[170.,40.,230.,50.],'dataset_header_bbox':[300.,10.,340.,20.],
        'metric_header_bbox':[300.,25.,312.,35.]}
    chunks=[{'chunk_id':'unit','association_tables':[{'table_id':'unit:table1','page':'p7','cells':[cell]}]}]
    class Page:
        def get_text(self,kind):return words
    class Document:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def __len__(self):return 7
        def __getitem__(self,index):return Page()
    monkeypatch.setattr(pymupdf,'open',lambda *a:Document())
    checked=verify_pdf_locations(V.source_rows(chunks),chunks,'synthetic-unit-source.pdf')
    assert checked['passed']==checked['checked']==1
    assert checked['checks'][0]['actual_source_text']['method_bbox']=='StandardRAG [14]'
