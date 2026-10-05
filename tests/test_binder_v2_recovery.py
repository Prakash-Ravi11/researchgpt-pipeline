"""Confirmed recovery defects, entirely synthetic and model-free."""
import json
from pathlib import Path
import pytest
from src.evidence import binder_v2 as B

CASES = json.loads((Path(__file__).parent / "fixtures/binder_v2_recovery.json").read_text(encoding="utf-8"))

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_confirmed_review_case(case, monkeypatch):
    monkeypatch.setenv("RGPT_BINDER_POLICY", "v2")
    monkeypatch.delenv("RGPT_BINDER_V2_DISABLE", raising=False)
    B._CACHE.clear()
    got = B.structural_bind_v2(case["claim"], case["chunks"])
    assert (got["status"] == "bound") == (case["expected"] == "bound"), got
    if case["cell"] and case["expected"] == "bound":
        assert all(got["cell"][k] == v for k, v in case["cell"].items()), got

def table(value='0.73', header='Dice', row='DeltaNet'):
    cap = 'Table 1: Segmentation results.'
    return {'chunk_id': 'S:1', 'block_type': 'table', 'text': cap,
            'table_cells': [{'row_label': row, 'column_header': header,
                             'value': value, 'caption': cap, 'row': 1, 'col': 1, 'page': 1}]}


def test_verifier_and_mocked_judge_contract(monkeypatch):
    monkeypatch.setenv("RGPT_BINDER_POLICY", "v2")
    monkeypatch.delenv("RGPT_BINDER_V2_DISABLE", raising=False)
    monkeypatch.setattr(B, "_llm_call", B._llm_call)
    results = []
    def record(name, observed, safe, **extra):
        results.append({'name': name, 'observed': observed, 'safe': bool(safe), **extra})

    claim = 'DeltaNet obtains a Dice of 0.73.'
    chunks = [table('0.73 ± 0.02')]
    idx = B._index(chunks, frozenset())
    fr = B._frame(claim, idx, frozenset())
    m = fr['mentions'][0]
    p = idx['cells'][0]
    lk = B.links(m, p, fr, idx, frozenset())
    record('verifier_positive', B.verify(claim, m, p, chunks, frozenset(), lk=lk),
           B.verify(claim, m, p, chunks, frozenset(), lk=lk) is None)
    bad_m = dict(m, pm='0.09')
    v = B.verify('DeltaNet obtains a Dice of 0.73 ± 0.09.', bad_m, p, chunks, frozenset(), lk=lk)
    record('verifier_rechecks_uncertainty', v, v is not None)
    bad_chunks = [table('0.73', 'CohortA / Dice')]
    idx = B._index(bad_chunks, frozenset())
    fr = B._frame('DeltaNet obtains a Dice of 0.73 on CohortA.', idx, frozenset())
    m = fr['mentions'][0]
    p = idx['cells'][0]
    lk = B.links(m, p, fr, idx, frozenset())
    v = B.verify('DeltaNet obtains a Dice of 0.73 on CohortB.', m, p, bad_chunks, frozenset(), lk=lk)
    record('verifier_rechecks_qualifier', v, v is not None)

    paper = [table(), {'chunk_id': 'S:0', 'block_type': 'paragraph', 'text':
             ' '.join(['DeltaNet has an auxiliary component.'] * 9) +
             ' The reference network DeltaNet is the comparator.'}]
    calls = []
    span = 'The reference network DeltaNet is the comparator.'
    def judge(request):
        calls.append(request)
        return {'choice': 'k1', 'span': span}
    B._llm_call = judge
    try:
        got = B.structural_bind_v2('The reference network achieves Dice of 0.73.', paper, llm=True)
        record('judge_unprovided_paper_span', got['status'], False,
               span_was_in_input=any(span in s for r in calls for s in r['paper_sentences']))
    except B.LLMViolation as exc:
        record('judge_unprovided_paper_span', str(exc), True)

    for name, chunks, answer in [
        ('judge_claim_only_span', [table()], 'The reference network achieves Dice of 0.73.'),
        ('judge_nonverbatim_paper_span', [table(), {'text': 'The reference network\nDeltaNet is the comparator.'}],
         'The reference network DeltaNet is the comparator.'),
    ]:
        B._llm_call = lambda request, answer=answer: {'choice': 'k1', 'span': answer}
        try:
            got = B.structural_bind_v2('The reference network achieves Dice of 0.73.', chunks, llm=True)
            record(name, got['status'], False)
        except B.LLMViolation as exc:
            record(name, str(exc), True)
    assert all(c["safe"] for c in results), results


@pytest.mark.parametrize("label,expected", [("17", "bound"), ("18", "not_bound")])
def test_explicit_numeric_row_label(label, expected, monkeypatch):
    monkeypatch.delenv("RGPT_BINDER_V2_DISABLE", raising=False)
    chunks = [table('0.73', 'Dice', '17')]
    got = B.structural_bind_v2(f'Row {label} achieves a Dice of 0.73.', chunks)
    assert (got['status'] == 'bound') == (expected == 'bound'), got


@pytest.mark.parametrize("cohort,expected", [("internal", "bound"), ("external", "not_bound")])
def test_completed_caption_context(cohort, expected, monkeypatch):
    monkeypatch.delenv("RGPT_BINDER_V2_DISABLE", raising=False)
    chunks = [table('0.73', 'Dice', 'Ours')]
    cell = chunks[0]['table_cells'][0]
    cell['caption'] = 'Table 1: Comparison on'
    chunks[0]['table_caption'] = 'Table 1: Comparison on the internal cohort.'
    other = table('0.65', 'Dice', 'Ours')
    other['table_cells'][0]['caption'] = 'Table 2: Segmentation results on the external cohort.'
    other['chunk_id'] = 'S:2'
    chunks.append(other)
    claim = f'On the {cohort} cohort for organ segmentation, our method achieves Dice of 0.73.'
    got = B.structural_bind_v2(claim, chunks)
    assert (got['status'] == 'bound') == (expected == 'bound'), got


@pytest.mark.parametrize('page,start,expected', [('p1', 42, 'bound'), ('p2', 42, 'not_bound'), ('p1', 99, 'not_bound')])
def test_caption_continuation_requires_adjacent_source_span(page, start, expected, monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    chunks = [table('0.73', 'Dice', 'Ours')]
    chunks[0].update(text='Table 1: Results on', page_or_node='p1', char_start=20, char_end=42)
    chunks[0]['table_cells'][0]['caption'] = chunks[0]['text']
    chunks.append({'chunk_id': 'S:2', 'block_type': 'paragraph', 'page_or_node': page,
                   'char_start': start, 'char_end': start + 30, 'text': 'the DeltaSet cohort. Other text.'})
    got = B.structural_bind_v2('Our method achieves Dice of 0.73 on DeltaSet.', chunks)
    assert (got['status'] == 'bound') == (expected == 'bound'), got


def test_direct_quantity_header_precedes_generic_caption_term(monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    chunks = [table('0.73', 'Dice', 'Ours')]
    chunks[0]['table_cells'][0]['caption'] = 'Table 1: Results on'
    chunks[0]['table_caption'] = 'Table 1: Results on the DeltaSet dataset.'
    other = table('DeltaSet', 'Dataset', 'Study')
    other['table_cells'][0]['caption'] = 'Table 2: Study information.'
    chunks.append(other)
    got = B.structural_bind_v2('On the DeltaSet dataset, our method achieves Dice of 0.73.', chunks)
    assert got['status'] == 'bound', got
    assert got['bindings'][0]['quantity'] == 'header'
