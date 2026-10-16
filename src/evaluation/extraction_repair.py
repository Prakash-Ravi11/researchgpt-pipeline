"""Independent acceptance checks. Never imported by extraction or retrieval."""
from collections import Counter
from src.evidence.verifier import (validate_associated_evidence,validate_comparisons,
    canonical_dataset,canonical_metric,canonical_method,canonical_configuration,
    normalize_page_id,_row_key,association_sources)


def evaluate_acceptance(payload,chunks,fixture,*,source_sha256):
    verdict=validate_associated_evidence(payload,chunks)
    reasons=list(verdict['rejections'])
    if not isinstance(payload,dict):return {'complete':False,'rejections':reasons}
    if source_sha256!=fixture.get('source_sha256'):reasons.append({'code':'source_hash_mismatch'})
    rows=verdict['accepted']
    for field,canonical in [('datasets',canonical_dataset),('metrics',canonical_metric)]:
        obj=payload.get(field)
        values=obj.get('values') if isinstance(obj,dict) else None
        if not isinstance(values,list):continue
        actual={canonical(v) for v in values if isinstance(v,str)}
        for expected in fixture.get(field,[]):
            if canonical(expected) not in actual:reasons.append({'field':field,'code':'missing_required_'+field,'value':expected})
    tuple_counts=Counter(_row_key(r) for r in rows)
    for expected in fixture.get('required_rows',[]):
        matches=[r for r in rows if _row_key(r)==_row_key(expected)]
        if len(matches)!=1:
            reasons.append({'code':'required_tuple_count','tuple':expected,'count':len(matches)});continue
        row=matches[0]
        if row['value']!=expected['value']:reasons.append({'code':'required_tuple_value','tuple':expected})
        if normalize_page_id(row['source']['page'])!=normalize_page_id(expected['page']) or row['source']['table_id'].split('table')[-1]!=expected['table_number']:
            reasons.append({'code':'required_tuple_location','tuple':expected})
    comparisons=payload.get('comparisons',[])
    reasons+=validate_comparisons(comparisons,rows)
    for expected in fixture.get('comparisons',[]):
        matches=[]
        if isinstance(comparisons,list):
            for item in comparisons:
                if not isinstance(item,dict):continue
                if item.get('dataset')!=expected['dataset'] or item.get('metric')!=expected['metric']:continue
                left,right=item.get('left'),item.get('right')
                if not isinstance(left,dict) or not isinstance(right,dict):continue
                if (left.get('method')==expected['left_method'] and right.get('method')==expected['right_method']
                    and canonical_configuration(left.get('configuration'))==expected['left_configuration']
                    and canonical_configuration(right.get('configuration'))==expected['right_configuration']
                    and left.get('value')==expected['left_value'] and right.get('value')==expected['right_value']):matches.append(item)
        if len(matches)!=1:reasons.append({'code':'required_comparative_evidence_missing','expected':expected,'count':len(matches)})
        elif matches[0].get('winner')!=expected['winner']:reasons.append({'code':'required_comparison_winner','expected':expected})
    limitation=payload.get('limitations')
    claims=limitation.get('values') if isinstance(limitation,dict) else None
    supported=[]
    if not isinstance(claims,list) or not claims:reasons.append({'code':'missing_source_supported_limitations'})
    else:
        for claim in claims:
            if not isinstance(claim,dict):continue
            source=claim.get('source')
            try:page=normalize_page_id(source.get('page')) if isinstance(source,dict) else None
            except ValueError:page=None
            reviews=[r for r in fixture.get('limitation_reviews',[]) if r.get('text')==claim.get('text')
                     and normalize_page_id(r['page'])==page
                     and r.get('assessment')=='supported_author_statement']
            if not reviews:reasons.append({'code':'limitation_semantic_support_unresolved','text':claim.get('text')})
            else:supported.append({'text':claim['text'],'review':reviews[0]})
    return {'complete':not reasons,'rejections':reasons,'required_tuple_count':len(fixture.get('required_rows',[])),
        'matched_required_tuples':sum(tuple_counts[_row_key(e)]==1 for e in fixture.get('required_rows',[])),
        'supported_limitations':supported,'semantic_assessment':'automated source review, not independently measured accuracy',
        'independent_human_correctness_labels':None}


def verify_pdf_locations(rows,chunks,pdf_path):
    """Re-open the actual PDF; verify numeric, row, config and hierarchical headers."""
    import pymupdf
    from src.evidence.verifier import canonical_configuration
    tables=association_sources(chunks)
    cells={c['cell_id']:c for t in tables.values() for c in t.get('cells',[])}
    checks=[]
    with pymupdf.open(pdf_path) as document:
        page_words={}
        for row in rows:
            cell=cells.get(row['source']['cell_id'])
            if cell is None:checks.append({'cell_id':row['source']['cell_id'],'passed':False,'reason':'unknown_cell'});continue
            page_no=int(normalize_page_id(row['source']['page'])[1:])
            if not 1<=page_no<=len(document):checks.append({'passed':False,'reason':'page_out_of_bounds'});continue
            if page_no not in page_words:page_words[page_no]=document[page_no-1].get_text('words')
            words=page_words[page_no]
            def text_at(rect):
                found=[w for w in words if rect[0]-.1<=w[0] and w[2]<=rect[2]+.1 and rect[1]-.1<=w[1] and w[3]<=rect[3]+.1]
                # Adapter rectangles describe one row/cell. Citation fonts can sit
                # fractions of a point above the method baseline; x-order is
                # the actual label order within this bounded row rectangle.
                return ' '.join(w[4] for w in sorted(found,key=lambda w:w[0]))
            actual={name:text_at(cell[name]) for name in ('bbox','method_bbox','configuration_bbox','dataset_header_bbox','metric_header_bbox')}
            passed=(actual['bbox']==cell['value'] and canonical_method(actual['method_bbox'])==row['method']
                and actual['configuration_bbox']==cell['configuration']
                and canonical_dataset(actual['dataset_header_bbox'])==row['dataset']
                and (canonical_metric(actual['metric_header_bbox']) or actual['metric_header_bbox'])==row['metric'])
            checks.append({'cell_id':cell['cell_id'],'page':page_no,'passed':passed,'actual_source_text':actual})
    return {'checked':len(checks),'passed':sum(c['passed'] for c in checks),'checks':checks}
