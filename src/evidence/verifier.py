"""Deterministic evidence verifier for extracted paper metadata.

This module is intentionally lightweight and explicit: it does not pretend to
be a semantic judge. Instead, it validates whether extracted fields are
present, non-empty, and plausibly grounded in paper text using a narrow set of
cheap deterministic checks.

It is designed to satisfy the project's evidence-gating requirement without
requiring a heavy external model or hidden heuristics.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


VERIFIER_VERSION = "1.0"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(_clean_text(v) for v in value if v is not None)
    if isinstance(value, dict):
        return " ".join(f"{k}: {_clean_text(v)}" for k, v in value.items())
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            text = _clean_text(item)
            if text:
                out.append(text)
        return out
    text = _clean_text(value)
    return [text] if text else []


def _paper_text_coverage(title: str, paper_text: str, fields: dict[str, Any]) -> dict[str, Any]:
    text = (paper_text or "").lower()
    title_l = (title or "").lower()

    supported = []
    weak = []
    issues = []

    for field_name in ["summary", "problem_addressed", "method", "results", "key_findings"]:
        value = _clean_text(fields.get(field_name, ""))
        if not value:
            weak.append(field_name)
            issues.append(f"{field_name} is empty")
            continue

        # If the field is not referencing any paper-specific terms and the
        # paper-text is long enough, flag it as suspicious.
        if len(text) > 200 and len(value) > 40:
            # Require at least one token overlap with the paper text or title.
            overlap = False
            for token in re.findall(r"[a-z0-9]+", value.lower()):
                if token and len(token) >= 4 and (token in text or token in title_l):
                    overlap = True
                    break
            if not overlap:
                weak.append(field_name)
                issues.append(f"{field_name} appears unsupported by the paper text")
                supported.append(field_name)
                continue

        supported.append(field_name)

    datasets = _as_list(fields.get("datasets"))
    if datasets:
        supported.append("datasets")
    else:
        weak.append("datasets")
        issues.append("datasets are missing")

    metrics = _as_list(fields.get("metrics"))
    if metrics:
        supported.append("metrics")
    else:
        weak.append("metrics")
        issues.append("metrics are missing")

    verdict = {
        "score": 10 if not weak else max(0, 10 - len(weak) * 2),
        "supported": not weak,
        "issues": issues,
        "missing_or_weak_fields": weak,
        "corrected_summary": _clean_text(fields.get("summary")) or "",
        "corrected_key_findings": _clean_text(fields.get("key_findings")) or "",
        "corrected_datasets": datasets,
    }
    return verdict


def verify_evidence(paper: dict, paper_text: str) -> dict:
    """Return a field-level verification result for one paper.

    Expected input shape is a single paper record from the Stage 4 output.
    Output matches the schema expected by the project's audit harness and CLI
    flow.
    """
    if not isinstance(paper, dict):
        return {
            "score": 0,
            "supported": False,
            "issues": ["paper record is not a dictionary"],
            "missing_or_weak_fields": ["summary", "method", "datasets", "key_findings"],
            "corrected_summary": "",
            "corrected_key_findings": "",
            "corrected_datasets": [],
        }

    title = paper.get("title") or paper.get("paper_id") or ""
    return _paper_text_coverage(title, paper_text, paper)


def verify_papers(records: list[dict], papers_by_id: dict[str, dict]) -> list[dict]:
    """Verify many records and return a list of per-paper verification results."""
    results = []
    for paper in records:
        pid = paper.get("paper_id") or paper.get("title") or "unknown"
        raw = papers_by_id.get(pid, "")
        if isinstance(raw, dict):
            paper_text = raw.get("text") or raw.get("paper_text") or ""
        else:
            paper_text = str(raw or "")
        results.append({"paper_id": pid, **verify_evidence(paper, paper_text)})
    return results


def _load_json(path: str | Path) -> Any:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def verify_directory(path: str | Path) -> dict:
    """Convenience entrypoint for an entire processed output directory."""
    processed_dir = Path(path)
    summaries = _load_json(processed_dir / "paper_summaries.json") or []
    chunks = _load_json(processed_dir / "chunks.json") or []
    paper_texts = {}

    by_paper: dict[str, list[str]] = {}
    for chunk in chunks:
        by_paper.setdefault(chunk.get("paper_id"), []).append(chunk.get("text", ""))

    for pid, texts in by_paper.items():
        paper_texts[pid] = " ".join(texts)

    verified = verify_papers(summaries, paper_texts)
    total = len(verified)
    avg_score = sum(v.get("score", 0) for v in verified) / total if total else 0
    supported = sum(1 for v in verified if v.get("supported"))
    return {
        "total": total,
        "average_score": round(avg_score, 2),
        "supported_count": supported,
        "results": verified,
        "version": VERIFIER_VERSION,
    }



ASSOCIATION_VERSION = '2026-10-13.method-configuration-source-v1'
FIELD_STATES = {'extracted', 'not_found_in_supplied_evidence', 'extraction_failed', 'not_reported'}


def normalize_page_id(value):
    if type(value) is int and value > 0:
        return 'p'+str(value)
    if isinstance(value,str) and re.fullmatch(r'(?:p)?[0-9]+',value.strip().casefold()) and int(value.strip().casefold().removeprefix('p'))>0:
        return 'p'+str(int(value.strip().casefold().removeprefix('p')))
    raise ValueError('invalid_page_id')


def canonical_metric(value):
    aliases={'em':'EM','exact match':'EM','exact match / em':'EM',
             'exact match (em)':'EM','f1':'F1','f1 score':'F1','f1-score':'F1'}
    return aliases.get(value.strip().casefold()) if isinstance(value,str) else None


def canonical_dataset(value):
    from src.synthesis.dataset_resolution import BENCHMARKS,_key
    if not isinstance(value,str):return None
    key=_key(value)
    for canonical,aliases,_ in BENCHMARKS:
        if key in {_key(canonical),*(_key(a) for a in aliases)}:return canonical
    return value.strip() or None


def canonical_method(value):
    if not isinstance(value,str):return None
    return re.sub(r'\s*\[\d+\]\*?\s*$', '',value).strip().rstrip('*')


def canonical_configuration(value):
    if not isinstance(value,dict) or set(value)!= {'llm','retriever'}:return None
    if not isinstance(value['llm'],str) or not (value['retriever'] is None or isinstance(value['retriever'],str)):return None
    aliases={'llama-3':'Llama3','llama3':'Llama3','gpt4':'GPT-4','gpt-4':'GPT-4'}
    llm=aliases.get(value['llm'].strip().casefold(),value['llm'].strip())
    return {'llm':llm,'retriever':value['retriever'].strip() if isinstance(value['retriever'],str) else None}


def association_sources(chunks):
    tables={}
    for chunk in chunks:
        if not isinstance(chunk,dict):continue
        for table in chunk.get('association_tables') or []:
            if isinstance(table,dict) and isinstance(table.get('table_id'),str):tables[table['table_id']]=table
    return tables


def source_rows(chunks):
    rows=[]
    for table in association_sources(chunks).values():
        cells=table.get('cells')
        if not isinstance(cells,list):continue
        for cell in cells:
            if not isinstance(cell,dict) or not all(isinstance(cell.get(k),str) for k in ('configuration','method','dataset','metric','value','cell_id')):continue
            try:
                numeric=float(cell['value'].rstrip('%'))
                normalize_page_id(cell.get('page'))
            except (ValueError,TypeError):continue
            import math
            if not math.isfinite(numeric):continue
            if any(type(cell.get(k)) is not int for k in ('row','col')) or not isinstance(cell.get('bbox'),list):continue
            config=cell['configuration'].split('/',1)
            rows.append({'method':canonical_method(cell['method']),
                'configuration':canonical_configuration({'llm':config[0],'retriever':config[1] if len(config)>1 else None}),
                'dataset':canonical_dataset(cell['dataset']),'metric':canonical_metric(cell['metric']) or cell['metric'],
                'value':float(cell['value'].rstrip('%')),'unit':'%' if cell['value'].endswith('%') else 'as_reported',
                'source':{'page':table['page'],'table_id':table['table_id'],'cell_id':cell['cell_id'],
                          'row':cell['row'],'col':cell['col'],'bbox':cell['bbox']}})
    return rows


def _row_key(row):
    cfg=canonical_configuration(row['configuration'])
    return (canonical_method(row['method']),cfg['llm'],cfg['retriever'],
            canonical_dataset(row['dataset']),canonical_metric(row['metric']) or row['metric'])


def validate_associated_evidence(payload, chunks):
    """Host validation; model booleans/verification flags never approve a claim."""
    import math
    reasons=[];accepted=[]
    if not isinstance(payload,dict):return {'accepted':[],'rejections':[{'code':'payload_type'}]}
    for field in ('datasets','metrics','results','limitations'):
        obj=payload.get(field)
        if not isinstance(obj,dict):reasons.append({'field':field,'code':'field_object_type'});continue
        if not isinstance(obj.get('status'),str) or obj.get('status') not in FIELD_STATES:reasons.append({'field':field,'code':'invalid_status'})
        if obj.get('status')=='not_reported':reasons.append({'field':field,'code':'absence_requires_source_inspection'})
        key='rows' if field=='results' else 'values'
        if not isinstance(obj.get(key),list):reasons.append({'field':field,'code':'collection_type'})
    if reasons:return {'accepted':[],'rejections':reasons}
    source_metric_labels={r['metric'] for r in source_rows(chunks)}
    for field in ('datasets','metrics'):
        for value in payload[field]['values']:
            if not isinstance(value,str):reasons.append({'field':field,'code':'label_type'})
            elif field=='metrics' and canonical_metric(value) is None and value not in source_metric_labels:reasons.append({'field':field,'code':'metric_alias_invalid'})
    trusted={row['source']['cell_id']:row for row in source_rows(chunks)}
    seen={}
    for index,row in enumerate(payload['results']['rows']):
        def reject(code):reasons.append({'field':'results','index':index,'code':code})
        if not isinstance(row,dict):reject('row_type');continue
        if not all(isinstance(row.get(k),str) and row[k].strip() for k in ('method','dataset','metric','unit')):
            reject('row_label_type');continue
        cfg=canonical_configuration(row.get('configuration'))
        if cfg is None:reject('configuration_type');continue
        value=row.get('value')
        if type(value) not in (int,float) or not math.isfinite(value):reject('numeric_value_type');continue
        source=row.get('source')
        if not isinstance(source,dict) or not isinstance(source.get('cell_id'),str):reject('source_reference_type');continue
        ref=trusted.get(source['cell_id'])
        if ref is None:reject('unknown_source_cell');continue
        try:page=normalize_page_id(source.get('page'))
        except ValueError:reject('invalid_page_id');continue
        if page!=normalize_page_id(ref['source']['page']):reject('source_page_mismatch');continue
        if source.get('table_id')!=ref['source']['table_id']:reject('source_table_mismatch');continue
        if any(type(source.get(k)) is not int or source[k]!=ref['source'][k] for k in ('row','col')):
            reject('source_cell_coordinate_mismatch');continue
        if _row_key(row)!=_row_key(ref):reject('method_configuration_dataset_metric_mismatch');continue
        key=_row_key(row)
        if key in seen:
            reject('duplicate_row' if seen[key]==value else 'conflicting_row');continue
        if float(value)!=ref['value'] or row['unit']!=ref['unit']:reject('value_or_unit_mismatch');continue
        if source.get('bbox')!=ref['source']['bbox']:reject('source_bbox_mismatch');continue
        seen[key]=value
        accepted.append({**ref,'structural_provenance':'associated_source_cell',
                         'semantic_assessment':'not_a_semantic_correctness_guarantee'})
    lookup={c['chunk_id']:c for c in chunks if isinstance(c,dict) and isinstance(c.get('chunk_id'),str)}
    for index,item in enumerate(payload['limitations']['values']):
        if not isinstance(item,dict) or not isinstance(item.get('text'),str) or not isinstance(item.get('source'),dict):
            reasons.append({'field':'limitations','index':index,'code':'limitation_type'});continue
        ref=lookup.get(item['source'].get('chunk_id'))
        if ref is None:code='unknown_limitation_source'
        else:
            try:page=normalize_page_id(item['source'].get('page'))
            except ValueError:page=None
            if page!=normalize_page_id(ref['page_or_node']):code='limitation_page_mismatch'
            elif item['text'] not in ref['text']:code='limitation_not_source_quote'
            elif any(type(item['source'].get(k)) is not int for k in ('char_start','char_end')):code='limitation_offset_type'
            elif (item['source']['char_start'],item['source']['char_end']) != (ref['char_start']+ref['text'].find(item['text']),ref['char_start']+ref['text'].find(item['text'])+len(item['text'])):code='limitation_span_mismatch'
            elif not _author_limitation_context(ref['text'], ref.get('section','')):code='limitation_attribution_unresolved'
            else:continue
        reasons.append({'field':'limitations','index':index,'code':code})
    return {'accepted':accepted,'rejections':reasons}


def _author_limitation_context(text, section):
    # Exact quotation plus local author/system context, never keyword overlap
    # with a differently worded model claim. Automated assessment is explicit.
    if 'discussion' not in section.casefold():return False
    modal=re.search(r'\b(?:may|cannot|limited|constraint|struggle|retrain|challenge)\w*\b',text,re.I)
    own=re.search(r'\b(?:our|we|this (?:method|system)|the (?:critic|reasoner))\b',text,re.I)
    prior=re.search(r'\b(?:prior work|previous work|et al\.)\b',text,re.I)
    return bool(modal and own and not prior)


def ownership_sources(method, chunks):
    root=re.sub(r'(?:full|lite)$','',canonical_method(method),flags=re.I)
    root=re.sub(r'[^a-z0-9]','',root.casefold())
    for chunk in chunks:
        if 'reference' in (chunk.get('section') or '').casefold():continue
        text=chunk['text']
        for statement in re.finditer(r'\bwe\s+(?:propose|introduce|present)\b[^.!?]{0,250}',text,re.I):
            phrase=statement.group().casefold().replace('-','')
            if re.search(r'(?<![a-z0-9])'+re.escape(root)+r'(?:full|lite)?(?![a-z0-9])',phrase):
                return {'chunk_id':chunk['chunk_id'],'page':chunk['page_or_node'],'source_span':statement.group()}
    return None


def derived_comparisons(rows, chunks):
    comparisons=[]
    own=[r for r in rows if ownership_sources(r['method'],chunks)]
    other=[r for r in rows if not ownership_sources(r['method'],chunks)]
    for left in own:
        if left['metric'] not in ('EM','F1'):continue
        alternatives=[r for r in other if r['dataset']==left['dataset'] and r['metric']==left['metric']
                      and r['configuration']['llm']==left['configuration']['llm']]
        if not alternatives:continue
        right=max(alternatives,key=lambda r:r['value'])
        winner=left['method'] if left['value']>right['value'] else right['method'] if right['value']>left['value'] else 'tie'
        comparisons.append({'dataset':left['dataset'],'metric':left['metric'],
            'left':left,'right':right,'winner':winner,'direction':'higher_is_better',
            'assessment':'derived_from_associated_source_values'})
    return comparisons


def validate_comparisons(comparisons, accepted_rows):
    if not isinstance(comparisons,list):return [{'code':'comparison_collection_type'}]
    keys={_row_key(r):r for r in accepted_rows};reasons=[]
    for index,item in enumerate(comparisons):
        if not isinstance(item,dict) or not all(isinstance(item.get(k),dict) for k in ('left','right')):
            reasons.append({'index':index,'code':'comparison_type'});continue
        try:
            left=keys[_row_key(item['left'])];right=keys[_row_key(item['right'])]
            same_values=all(type(item[side].get('value')) in (int,float) and item[side].get('value')==row['value'] and item[side].get('source')==row['source']
                            for side,row in (('left',left),('right',right)))
        except (KeyError,TypeError):reasons.append({'index':index,'code':'comparison_source_missing'});continue
        if not same_values:reasons.append({'index':index,'code':'comparison_source_mismatch'});continue
        if left['dataset']!=right['dataset'] or left['metric']!=right['metric'] or left['configuration']['llm']!=right['configuration']['llm']:
            reasons.append({'index':index,'code':'comparison_configuration_mismatch'});continue
        winner=left['method'] if left['value']>right['value'] else right['method'] if right['value']>left['value'] else 'tie'
        if item.get('winner')!=winner or item.get('direction')!='higher_is_better':
            reasons.append({'index':index,'code':'comparison_direction_reversed'})
    return reasons


def grounded_field_repair(extraction, chunks):
    """Recover source-parsed values, not evaluation expectations or model flags."""
    rows=source_rows(chunks)
    own=[r for r in rows if ownership_sources(r['method'],chunks)]
    quotations=[]
    for chunk in chunks:
        for match in re.finditer(r'[^.!?]+[.!?](?:\s|$)',chunk['text']):
            sentence=match.group().strip()
            if _author_limitation_context(sentence,chunk.get('section','')):
                offset=chunk['text'].find(sentence)
                quotations.append({'text':sentence,'source':{'chunk_id':chunk['chunk_id'],'page':chunk['page_or_node'],
                    'char_start':chunk['char_start']+offset,'char_end':chunk['char_start']+offset+len(sentence)},
                    'semantic_assessment':'unverified_automated_author_context',
                    'independent_review':'not_available'})
    # Keep quote selection bounded; all inspected source stays available to audit.
    quotations=quotations[:3]
    payload={'datasets':{'status':'extracted' if own else 'not_found_in_supplied_evidence',
                         'values':list(dict.fromkeys(r['dataset'] for r in own))},
        'metrics':{'status':'extracted' if own else 'not_found_in_supplied_evidence',
                   'values':list(dict.fromkeys(r['metric'] for r in own))},
        'results':{'status':'extracted' if own else 'not_found_in_supplied_evidence','rows':rows},
        'limitations':{'status':'extracted' if quotations else 'not_found_in_supplied_evidence','values':quotations}}
    verdict=validate_associated_evidence(payload,chunks)
    if verdict['rejections']:return extraction,verdict
    result=dict(extraction)
    result['_limitation_evidence']=quotations
    result['_field_states']={field:('extracted' if result.get(field) else 'not_found_in_supplied_evidence')
                             for field in ('datasets','metrics','results','limitations')}
    if own:
        result['_association_evidence']=payload
        result['_association_evidence']['comparisons']=derived_comparisons(verdict['accepted'],chunks)
    result['_association_version']=ASSOCIATION_VERSION
    result['_reviewer_inferences']=[extraction['limitations']] if extraction.get('limitations') and not any(extraction['limitations']==q['text'] for q in quotations) else []
    result['limitations']=' '.join(q['text'] for q in quotations)
    if own:
        result['datasets']=payload['datasets']['values'];result['metrics']=payload['metrics']['values']
        sentences=[f"{r['method']} ({r['configuration']['llm']}/{r['configuration']['retriever']}) on {r['dataset']}: {r['metric']} {r['value']:g} ({r['unit']}); {r['source']['page']}, table {r['source']['table_id'].split('table')[-1]}, row {r['source']['row']}, column {r['source']['col']}." for r in own]
        exceptions=[c for c in payload['comparisons'] if c['winner'] not in (c['left']['method'],'tie')]
        sentences += [f"For {c['dataset']} {c['metric']}, {c['right']['method']} ({c['right']['configuration']['llm']}/{c['right']['configuration']['retriever']}) scores {c['right']['value']:g}, above {c['left']['method']} ({c['left']['configuration']['llm']}/{c['left']['configuration']['retriever']}) at {c['left']['value']:g}." for c in exceptions]
        result['results']=' '.join(sentences)
        if exceptions:result['key_findings']=' '.join(sentences[-len(exceptions):])
    result['_field_states']={field:('extracted' if result.get(field) else 'extraction_failed' if result.get('_extraction_failed') else 'not_found_in_supplied_evidence') for field in ('datasets','metrics','results','limitations')}
    result.pop('_no_dataset_stated',None)
    return result,verdict
