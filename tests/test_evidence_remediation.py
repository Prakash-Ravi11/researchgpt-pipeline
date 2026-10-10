import pytest

from src.evidence import gate as G
from src.evidence.schema import atomic_metrics


def chunk(text, block_type='paragraph'):
    return dict(chunk_id='synthetic:prose', block_id='synthetic:block', source='synthetic.pdf',
                representation='pdf', section='results', page_or_node='p3',
                block_type=block_type, text=text, char_start=100, char_end=100 + len(text))


@pytest.mark.parametrize('policy', ['legacy', 'v2'])
def test_prose_fallback_returns_owned_sentence_with_exact_offsets(monkeypatch, policy):
    monkeypatch.setenv('RGPT_BINDER_POLICY', policy)
    claim = 'Our method achieves a Dice score of 0.87.'
    source = chunk('The evaluation is complete.  ' + claim + ' Further work remains.')
    result = G.gate_paper({'results': claim}, [source], G.FULL_TEXT, [])
    item = result['evidence']['results'][0]
    assert result['results'] == claim
    assert item['evidence_status'] == G.PROSE_GROUNDED
    assert item['attribution'] == G.OWN_PAPER and item['final'] == G.RETURNED
    assert item['structural_binding']['structured'] is False
    assert item['source'] == 'synthetic.pdf' and item['page_or_node'] == 'p3'
    left, right = item['char_start'] - 100, item['char_end'] - 100
    assert source['text'][left:right] == item['evidence_span'] == claim


@pytest.mark.parametrize('claim,source,reason', [
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.370.', 'unverifiable_binding'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.72. Baseline achieves Dice of 0.37.', 'unverifiable_binding'),
    ('Our method achieves Dice of 0.37.', 'Our method does not achieve Dice of 0.37.', 'unverifiable_binding'),
    ('Our method achieves Dice of 0.37.', 'It is not true that our method achieves Dice of 0.37.', 'unverifiable_binding'),
    ('Our method achieves Dice of 0.37.', 'We test whether our method achieves Dice of 0.37.', 'unverifiable_binding'),
    ('Prior work achieves Dice of 0.37.', 'Prior work achieves Dice of 0.37.', 'attributed_to_cited_work'),
    ('Dice of 0.37 was measured.', 'Dice of 0.37 was measured.', 'ownership_unverified'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.37 [12].', 'unverifiable_binding'),
])
def test_prose_fallback_does_not_borrow_values_or_ownership(monkeypatch, claim, source, reason):
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'legacy')
    item = G._gate_value('results', claim, [chunk(source)], [])
    assert item['final'] == G.ABSTAINED
    assert item['abstain_reason'] == reason
    assert item['evidence_status'] != G.PROSE_GROUNDED


def test_prose_fallback_rejects_a_citation_in_the_supporting_sentence():
    claim = 'Our method achieves Dice of 0.37'
    item = G._gate_value('results', claim, [chunk(claim + ' [12].')], [])
    assert item['final'] == G.ABSTAINED
    assert item['attribution'] == G.CITED_PAPER


@pytest.mark.parametrize('kind', ['missing_offsets', 'table', 'table_collision'])
def test_prose_fallback_needs_locatable_prose_not_flattened_tables(kind):
    claim = 'Our method achieves Dice of 0.37.'
    source = chunk(claim)
    chunks = [source]
    if kind == 'missing_offsets':
        source.pop('char_start')
    elif kind == 'table':
        source['block_type'] = 'table'
    else:
        chunks.append(chunk('Table 1. Baseline Dice 0.37.', 'table'))
    item = G._gate_value('results', claim, chunks, [])
    assert item['final'] == G.ABSTAINED
    assert item['abstain_reason'] == 'unverifiable_binding'


@pytest.mark.parametrize('value,expected', [
    ('Accuracy, Precision, Recall, F1', True),
    (['Accuracy', 'Precision, Recall', 'F1'], True),
    (['AUC', 'IoU'], True),
    ('Accuracy, unrelated prose', False),
    (['Accuracy', 'unrelated prose'], False),
    (['Accuracy', 42], False),
    (['Accuracy', ''], False),
    ([], False),
])
def test_metric_sanity_checks_every_atom(value, expected):
    assert G._value_sane('metrics', value) is expected


@pytest.mark.parametrize('policy', ['legacy', 'v2'])
def test_atomic_metrics_receive_separate_grounding(monkeypatch, policy):
    monkeypatch.setenv('RGPT_BINDER_POLICY', policy)
    source = chunk('We report Accuracy, Recall, F1, AUC, and IoU.')
    result = G.gate_paper({'metrics': 'Accuracy, Precision, Recall, F1, AUC, IoU'}, [source], G.FULL_TEXT, [])
    assert result['metrics'] == ['Accuracy', 'Recall', 'F1', 'AUC', 'IoU']
    rejected = [it for it in result['evidence']['metrics'] if it['final'] == G.ABSTAINED]
    assert [(it['value'], it['abstain_reason']) for it in rejected] == [
        ('Precision', 'evidence_span_not_found_in_paper_chunks')]
    assert G._ground('F1', [chunk('We report F10.')], field='metrics') is None


def test_atomic_normalization_preserves_qualifiers_and_nonmetric_values():
    assert atomic_metrics('Accuracy (macro, micro), Latency 1,000 ms, F1') == [
        'Accuracy (macro, micro)', 'Latency 1,000 ms', 'F1']
    assert G._as_list('Benchmark, validation split', 'datasets') == ['Benchmark, validation split']
    assert atomic_metrics('F1,95HD,NDCG@10,73Rho') == ['F1', '95HD', 'NDCG@10', '73Rho']
