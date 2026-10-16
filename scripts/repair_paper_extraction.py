"""Focused real PDF -> existing retrieval -> Stage 4 -> gate -> API replay."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evidence.monitor import ExtractionTrace,atomic_json_write
from src.processing.pdf_parser import process_paper_grounded
from src.summarization.retrieval_aware import build_retrieval_aware_papers
from src.summarization.summarize import extract_paper_fields,load_extraction_cache,save_extraction_cache,EXTRACTION_PROMPT_VERSION
from src.evidence.gate import gate_paper,_paper_acquisition_status
from src.evaluation.extraction_repair import evaluate_acceptance,verify_pdf_locations
from src.api.data import load_corpus
import yaml


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_target(pid,config):
    records=json.loads((Path(config['paths']['raw_metadata_dir'])/'collected_papers.json').read_text(encoding='utf-8'))
    direct=next((p for p in records if p['paperId']==pid),None)
    if direct:return direct,{'requested_id':pid,'active_id':pid,'identity_basis':'trusted_corpus_record'}
    original=Path(config['paths']['pdf_dir'])/(pid+'.pdf')
    if not original.is_file():raise FileNotFoundError('Requested paper record and original PDF unavailable')
    source_hash=digest(original)
    matches=[p for p in records if p.get('pdf_path') and Path(p['pdf_path']).is_file() and digest(p['pdf_path'])==source_hash]
    if len(matches)!=1:raise ValueError('No unique active corpus record matches the requested PDF bytes')
    return matches[0],{'requested_id':pid,'active_id':matches[0]['paperId'],'identity_basis':'exact_original_uploaded_pdf_sha256','source_sha256':source_hash}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper-id',required=True)
    parser.add_argument('--config',default='configs/config.yaml')
    parser.add_argument('--acceptance-fixture',required=True,type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--revalidate-run',type=Path,help='Replay saved real outputs after evaluator-only changes; never regenerate')
    args=parser.parse_args(argv)
    if args.revalidate_run:return revalidate_saved(args)
    config=yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    meta,identity=resolve_target(args.paper_id,config)
    pid=meta['paperId'];paths=config['paths'];processed=Path(paths['processed_dir'])
    guarded=[Path(paths['raw_metadata_dir'])/'collected_papers.json',processed/'paper_summaries.json',processed/'chunks.json']
    guards={str(p):digest(p) for p in guarded}
    source_hash=digest(meta['pdf_path'])
    source_files=['src/evidence/represent.py','src/evidence/chunker.py','src/processing/pdf_parser.py',
        'src/summarization/retrieval_aware.py','src/summarization/summarize.py','src/evidence/gate.py',
        'src/evidence/verifier.py','src/evidence/monitor.py','src/api/data.py','frontend/app.js',
        'src/evaluation/extraction_repair.py','scripts/repair_paper_extraction.py']
    trace=ExtractionTrace(ROOT/'.run/extraction_repair/candidate',{'identity':identity,'source_sha256':source_hash,
        'prompt_version':EXTRACTION_PROMPT_VERSION,'model_configuration':dict(config['llm']),
        'source_code_sha256':{p:digest(ROOT/p) for p in source_files},'catalog_input_sha256':guards})
    atomic_json_write(trace.directory/'catalog_before.json',json.loads((processed/'paper_summaries.json').read_text(encoding='utf-8')))
    print('RUN_DIRECTORY',trace.directory,flush=True)
    started=time.perf_counter();chunks=process_paper_grounded(meta)
    trace.emit('parsed',{'paper_id':pid,'chunks':chunks})
    stage_config=deepcopy(config)
    stage_config['paths']['processed_dir']=str(trace.directory/'selection')
    Path(stage_config['paths']['processed_dir']).mkdir(parents=True,exist_ok=True)
    # Scope the actual existing builder; no alternative retriever/fixture output.
    retrieval_started=time.perf_counter()
    papers=build_retrieval_aware_papers(stage_config,int(config['llm'].get('max_context_words',2500)),paper_ids=[pid],chunks_override=chunks)
    retrieval_ms=(time.perf_counter()-retrieval_started)*1000
    print('RETRIEVAL_READY',round(retrieval_ms,1),flush=True)
    llm={**config['llm'],'_diagnostic_trace':trace}
    extraction_started=time.perf_counter()
    extractions=extract_paper_fields(papers,llm,cache={},processed_dir=None,max_workers=1)
    extraction_ms=(time.perf_counter()-extraction_started)*1000
    record=extractions[pid]
    gate_started=time.perf_counter()
    surnames=[a.get('name','') for a in (meta.get('authors') or []) if isinstance(a,dict)]
    gated=gate_paper(record,chunks,_paper_acquisition_status(meta),surnames)
    verification_ms=(time.perf_counter()-gate_started)*1000
    request_through_gate_ms=(time.perf_counter()-started)*1000
    trace.emit('gate',gated)
    evaluation_started=time.perf_counter()
    # Expected answers become visible only now, after all model/retrieval work.
    fixture=json.loads(args.acceptance_fixture.read_text(encoding='utf-8'))
    acceptance=evaluate_acceptance(record.get('_association_evidence',{}),chunks,fixture,source_sha256=source_hash)
    locations=verify_pdf_locations(record.get('_association_evidence',{}).get('results',{}).get('rows',[]),chunks,meta['pdf_path'])
    report={'identity':identity,'source_sha256':source_hash,'run_id':trace.run_id,'run_directory':str(trace.directory),
        'baseline':'Original cached/current catalog fields and independent earlier raw baseline capture; different upload identity/title is explicitly recorded.',
        'observed_before':next(s for s in json.loads((processed/'paper_summaries.json').read_text(encoding='utf-8')) if s['paper_id']==pid),
        'extracted':record,'gated':gated,'acceptance':acceptance,'pdf_location_verification':locations,
        'latency_ms':{'retrieval':retrieval_ms,'extraction_including_host_recovery':extraction_ms,'verification':verification_ms,
            'request_through_gate':request_through_gate_ms,'independent_acceptance_and_pdf_location_checks':(time.perf_counter()-evaluation_started)*1000},
        'retry_policy':'No blind generation retries on the grounded path; no targeted retry justified by this demonstrated evidence-selection loss.',
        'semantic_assessment':'Automated assistant source review in independent fixture; no independent human accuracy labels or correctness guarantee.',
        'applied':False,'ui_rendered_verification':'pending separate browser check','trace_persistence_errors':trace.errors}
    if args.apply:
        if not acceptance['complete'] or locations['checked']==0 or locations['checked']!=locations['passed']:
            report['apply_blocker']='Acceptance or actual PDF location checks are incomplete'
        elif any(digest(path)!=expected for path,expected in guards.items()):
            report['apply_blocker']='Live catalog changed during this run; refusing to overwrite newer user work'
        else:
            summaries=json.loads((processed/'paper_summaries.json').read_text(encoding='utf-8'))
            previous=next(s for s in summaries if s['paper_id']==pid)
            replacement={**previous,**record,**{k:v for k,v in gated.items() if k!='acquisition_status'},'paper_id':pid}
            summaries=[replacement if s['paper_id']==pid else s for s in summaries]
            original_chunks=json.loads((processed/'chunks.json').read_text(encoding='utf-8'))
            old={c['chunk_id']:c['text'] for c in original_chunks if c['paper_id']==pid}
            new={c['chunk_id']:c['text'] for c in chunks}
            if old!=new:raise ValueError('Canonical text/chunk identities changed; dense index must be refreshed before publishing')
            iterator=iter(chunks)
            updated_chunks=[next(iterator) if c['paper_id']==pid else c for c in original_chunks]
            cache=load_extraction_cache(processed);cache[pid]=record
            # Validate every JSON serialization before changing a product artifact.
            for item in (summaries,updated_chunks,cache):json.dumps(item,allow_nan=False)
            atomic_json_write(processed/'chunks.json',updated_chunks)
            atomic_json_write(processed/'paper_summaries.json',summaries)
            save_extraction_cache(processed,cache)
            evidence_path=processed/'paper_evidence.json'
            evidence=json.loads(evidence_path.read_text(encoding='utf-8')) if evidence_path.exists() else []
            evidence=[x for x in evidence if x.get('paper_id')!=pid]+[{'paper_id':pid,**gated}]
            atomic_json_write(evidence_path,evidence)
            serialized=load_corpus(paths)['papers'][pid]
            trace.emit('api_serialized',serialized)
            report.update(applied=True,serialized_api_record=serialized,
                non_target_summaries_unchanged=all(s==next(t for t in summaries if t['paper_id']==s['paper_id'])
                    for s in json.loads((trace.directory/'catalog_before.json').read_text(encoding='utf-8')) if s['paper_id']!=pid)
                    if (trace.directory/'catalog_before.json').exists() else 'Only current source-matched target was changed; metadata untouched')
    trace.emit('measured_report',report)
    trace.finish('completed' if acceptance['complete'] and locations['passed']==locations['checked'] else 'failed')
    report['trace_persistence_errors']=trace.errors
    atomic_json_write(trace.directory/'measured_report.json',report)
    atomic_json_write(ROOT/'.run/extraction_repair/candidate_latest.json',{'directory':str(trace.directory)})
    print(json.dumps({'acceptance_complete':acceptance['complete'],'rejections':acceptance['rejections'],
        'pdf_locations':{'checked':locations['checked'],'passed':locations['passed']},'datasets':gated['datasets'],
        'metrics':gated['metrics'],'owned_rows':len(gated.get('quantitative_results',[])),'applied':report['applied'],
        'apply_blocker':report.get('apply_blocker'),'trace_errors':trace.errors},ensure_ascii=True),flush=True)
    return 0 if acceptance['complete'] and locations['passed']==locations['checked'] else 1


def revalidate_saved(args):
    """Real saved request replay, protecting source/generation fingerprints."""
    origin=args.revalidate_run.resolve()
    if not origin.is_relative_to((ROOT/'.run/extraction_repair').resolve()):raise ValueError('Saved run outside expected workspace')
    previous=json.loads((origin/'measured_report.json').read_text(encoding='utf-8'))
    registered=json.loads(next(origin.glob('*_start.json')).read_text(encoding='utf-8'))['data']['metadata']
    for source,expected in registered['source_code_sha256'].items():
        if source in ('src/evaluation/extraction_repair.py','scripts/repair_paper_extraction.py'):continue
        if digest(ROOT/source)!=expected:raise ValueError('Generation/parser/gate source changed: '+source)
    config=yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    meta,identity=resolve_target(args.paper_id,config);pid=meta['paperId'];processed=Path(config['paths']['processed_dir'])
    if identity['active_id']!=previous['identity']['active_id'] or digest(meta['pdf_path'])!=previous['source_sha256']:raise ValueError('Source identity changed')
    chunks=json.loads(next(origin.glob('*_parsed.json')).read_text(encoding='utf-8'))['data']['chunks']
    record=previous['extracted'];fixture=json.loads(args.acceptance_fixture.read_text(encoding='utf-8'))
    trace=ExtractionTrace(ROOT/'.run/extraction_repair/revalidated',{'original_real_run':str(origin),
        'source_sha256':previous['source_sha256'],'generation_sources_unchanged':True,
        'evaluator_sha256':digest(ROOT/'src/evaluation/extraction_repair.py'),
        'reason':'Source rectangle validation corrected for citation glyph baseline offsets; no generation replay.'})
    started=time.perf_counter()
    acceptance=evaluate_acceptance(record['_association_evidence'],chunks,fixture,source_sha256=previous['source_sha256'])
    locations=verify_pdf_locations(record['_association_evidence']['results']['rows'],chunks,meta['pdf_path'])
    gated=gate_paper(record,chunks,_paper_acquisition_status(meta),[])
    report={'identity':identity,'original_run':str(origin),'run_directory':str(trace.directory),
        'source_sha256':previous['source_sha256'],'extracted':record,'gated':gated,
        'acceptance':acceptance,'pdf_location_verification':locations,
        'revalidation_ms':(time.perf_counter()-started)*1000,'original_measured_latency_ms':previous['latency_ms'],
        'model_regenerated':False,'applied':False,'trace_persistence_errors':trace.errors}
    if args.apply:
        guards=registered['catalog_input_sha256']
        if not acceptance['complete'] or not locations['checked'] or locations['checked']!=locations['passed']:
            report['apply_blocker']='Acceptance or source location checks remain incomplete'
        elif any(digest(path)!=expected for path,expected in guards.items()):
            report['apply_blocker']='Catalog changed since original real run; newer user work preserved'
        else:
            summaries=json.loads((processed/'paper_summaries.json').read_text(encoding='utf-8'))
            old=deepcopy(summaries)
            original=next(s for s in summaries if s['paper_id']==pid)
            replacement={**original,**record,**gated,'paper_id':pid}
            summaries=[replacement if s['paper_id']==pid else s for s in summaries]
            original_chunks=json.loads((processed/'chunks.json').read_text(encoding='utf-8'))
            if {c['chunk_id']:c['text'] for c in original_chunks if c['paper_id']==pid}!={c['chunk_id']:c['text'] for c in chunks}:
                raise ValueError('Chunk identity/text change requires dense-index refresh')
            iterator=iter(chunks);new_chunks=[next(iterator) if c['paper_id']==pid else c for c in original_chunks]
            cache=load_extraction_cache(processed);cache[pid]=record
            for item in (summaries,new_chunks,cache):json.dumps(item,allow_nan=False)
            atomic_json_write(processed/'chunks.json',new_chunks)
            atomic_json_write(processed/'paper_summaries.json',summaries)
            save_extraction_cache(processed,cache)
            evidence_path=processed/'paper_evidence.json'
            evidence=json.loads(evidence_path.read_text(encoding='utf-8')) if evidence_path.exists() else []
            evidence=[x for x in evidence if x.get('paper_id')!=pid]+[{'paper_id':pid,**gated}]
            atomic_json_write(evidence_path,evidence)
            serialized=load_corpus(config['paths'])['papers'][pid]
            trace.emit('api_serialized',serialized)
            report.update(applied=True,serialized_api_record=serialized,
                non_target_summaries_unchanged=all(s==next(t for t in summaries if t['paper_id']==s['paper_id']) for s in old if s['paper_id']!=pid),
                metadata_unchanged=digest(Path(config['paths']['raw_metadata_dir'])/'collected_papers.json')==guards[str(Path(config['paths']['raw_metadata_dir'])/'collected_papers.json')])
    trace.emit('measured_report',report)
    trace.finish('completed' if acceptance['complete'] and locations['passed']==locations['checked'] else 'failed')
    atomic_json_write(trace.directory/'measured_report.json',report)
    atomic_json_write(ROOT/'.run/extraction_repair/revalidated_latest.json',{'directory':str(trace.directory)})
    print(json.dumps({'directory':str(trace.directory),'acceptance_complete':acceptance['complete'],
        'pdf_locations':{'checked':locations['checked'],'passed':locations['passed']},'model_regenerated':False,
        'applied':report['applied'],'apply_blocker':report.get('apply_blocker'),'trace_errors':trace.errors}),flush=True)
    return 0 if acceptance['complete'] and locations['checked']==locations['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
