"""Semantic gating and metric-label contracts; no network/model calls."""
from types import SimpleNamespace

import pytest

from src.evidence import entailment as N
from src.evidence import gate as G


def chunk(text, **extra):
    return dict(block_id='source:block', chunk_id='source:chunk', source='source.pdf',
                representation='pdf', section='results', page_or_node='p2',
                block_type='paragraph', text=text, char_start=100,
                char_end=100 + len(text), **extra)


SOURCE = 'Our method achieves a Dice score of 0.87 on the validation cohort.'
CLAIM = 'Our model records a Dice score of 0.87 on the validation cohort.'


@pytest.fixture(autouse=True)
def offline_scores(monkeypatch):
    monkeypatch.setattr(G, 'entailment_scores', lambda pairs: [None] * len(pairs))


@pytest.mark.parametrize('policy', ['legacy', 'v2'])
def test_owned_paraphrase_is_entailed_with_original_sentence_offsets(monkeypatch, policy):
    monkeypatch.setenv('RGPT_BINDER_POLICY', policy)
    pairs = []
    def score(inputs):
        pairs.extend(inputs)
        return [0.95] * len(inputs)
    monkeypatch.setattr(G, 'entailment_scores', score)
    source = chunk('Trial completed.  ' + SOURCE + ' More work follows.')
    result = G.gate_paper({'results': CLAIM}, [source], G.FULL_TEXT, [])
    item = result['evidence']['results'][0]
    assert result['results'] == CLAIM
    assert item['evidence_status'] == G.ENTAILED and item['attribution'] == G.OWN_PAPER
    assert item['entailment']['confidence'] == 0.95
    assert 0.65 <= item['entailment']['lexical_overlap'] <= 0.85
    assert pairs == [(SOURCE, CLAIM)]
    assert source['text'][item['char_start'] - 100:item['char_end'] - 100] == SOURCE
    assert item['evidence_span'] == SOURCE and item['provenance_valid']


@pytest.mark.parametrize('score,returned', [(0.9, True), (0.89999, False),
                                          (0.1, False), (None, False),
                                          (float('nan'), False), (float('inf'), False)])
def test_entailment_probability_threshold(monkeypatch, score, returned):
    monkeypatch.setattr(G, 'entailment_scores', lambda pairs: [score] * len(pairs))
    item = G._gate_value('results', CLAIM, [chunk(SOURCE)], [])
    assert (item['final'] == G.RETURNED) == returned


@pytest.mark.parametrize('shared,allowed', [(12, False), (13, True), (17, True), (18, False)])
def test_overlap_band_includes_only_requested_boundaries(monkeypatch, shared, allowed):
    words = ('segmentation model improved average validation accuracy reduced latency across multiple '
             'hospital cohorts following careful parameter tuning robust evaluation protocol calibration').split()
    assert len(words) == 20
    claim = ' '.join(words)
    source = chunk('Our approach: ' + ' '.join(words[:shared]) + '.')
    calls = []
    def scores(pairs):
        calls.extend(pairs)
        return [0.95] * len(pairs)
    monkeypatch.setattr(G, 'entailment_scores', scores)
    result = G._semantic_ground(claim, [source], field='results', surnames=[])
    assert bool(result) == allowed
    assert bool(calls) == allowed


@pytest.mark.parametrize('claim,source', [
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.370.'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.72.'),
    ('Our method achieves Dice of 0.37.', 'Our method does not achieve Dice of 0.37.'),
    ('Our method achieves Dice of 0.37.', 'We test whether our method achieves Dice of 0.37.'),
    ('Our method improves Dice by 0.37.', 'Our method achieves Dice of 0.37.'),
    ('Our method increases Dice by 0.37.', 'Our method decreases Dice by 0.37.'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves Accuracy of 0.37 and Dice of 0.72.'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.72 and baseline Dice is 0.37.'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves Dice of 0.72 and UNet reaches Dice of 0.37.'),
    ('UNet achieves Dice of 0.37.', 'ResNet achieves Dice of 0.37.'),
    ('Our method achieves HD95 of 0.37 mm.', 'Our method achieves HD95 of 0.37 cm.'),
    ('Our method achieves Dice of 0.37.', 'Our method achieves an unrelated score of 0.37.'),
    ('Our method achieves Dice above 0.87.', 'Our method achieves Dice below 0.87.'),
    ('Our method achieves Dice of 0.87.', 'Our method achieves Dice around 0.87.'),
    ('Our explanations achieve an expert score of 4.9/5.', 'Our explanations achieve an expert score of 4.9/6.'),
    ('Our method reports Dice of 0.87 with 95% CI (0.85, 0.90).',
     'Our method reports Dice of 0.87 with 90% CI (0.85, 0.90).'),
])
def test_nli_cannot_override_quantitative_conflicts(claim, source):
    assert not G._quantities_supported(claim, source)


def test_dataset_and_split_names_are_not_mistaken_for_model_subjects():
    source = ('Our method improves performance by +4.2% on the Single-Hop subset and +0.4% '
              'on the full dataset, while on InfoSeek it achieves gains of +7.8% on the Unseen-Q subset.')
    claim = ('Single-Hop subset improvement of +4.2%, full dataset gain of +0.4%, '
             'and Unseen-Q subset gain of +7.8% on InfoSeek.')
    assert G._quantities_supported(claim, source)


@pytest.mark.parametrize('source,extra', [
    ('Prior work achieves a Dice score of 0.87 on the validation cohort.', {}),
    ('A Dice score of 0.87 was recorded on the validation cohort.', {}),
    (SOURCE + ' [12]', {}),
    (SOURCE, {'table_cells': [{'value': '0.87'}]}),
])
def test_unowned_or_table_sources_never_reach_nli(monkeypatch, source, extra):
    def forbidden(_):
        raise AssertionError('Unowned or table evidence must not reach NLI')
    monkeypatch.setattr(G, 'entailment_scores', forbidden)
    assert G._semantic_ground(CLAIM, [chunk(source, **extra)], field='results', surnames=[]) is None


def test_missing_offsets_and_separate_sentences_cannot_supply_a_claim(monkeypatch):
    monkeypatch.setattr(G, 'entailment_scores', lambda pairs: [1.0] * len(pairs))
    source = chunk(SOURCE); source.pop('char_start')
    assert G._semantic_ground(CLAIM, [source], field='results', surnames=[]) is None
    claim = 'Our model records Dice of 0.87 and accuracy of 0.92.'
    source = chunk('Our method records Dice of 0.87. Our method records accuracy of 0.92.')
    assert G._semantic_ground(claim, [source], field='results', surnames=[]) is None


def test_inference_is_bounded_and_preserves_input_chunks(monkeypatch):
    chunks = [chunk(SOURCE) for _ in range(8)]
    calls = []
    def scores(pairs):
        calls.extend(pairs)
        return [0.95] * len(pairs)
    monkeypatch.setattr(G, 'entailment_scores', scores)
    assert G._semantic_ground(CLAIM, chunks, field='results', surnames=[])
    assert len(calls) == N.MAX_CANDIDATES
    assert all('_entailment' not in c for c in chunks)


class Tokenizer:
    def __call__(self, premise, hypothesis, *, truncation):
        assert truncation is False
        return {'input_ids': [1] * (600 if premise == 'oversized' else 3)}

    def pad(self, items, **kwargs):
        import torch
        return {'input_ids': torch.zeros((len(items), 3), dtype=torch.long)}


def test_adapter_uses_softmax_entailment_label_and_never_truncates(monkeypatch):
    import torch
    calls = []
    class Model:
        config = SimpleNamespace(max_position_embeddings=512)
        def __call__(self, **features):
            calls.append(features)
            return SimpleNamespace(logits=torch.tensor([[0.0, 0.0, 0.95]]))
    monkeypatch.setattr(N, '_load_model', lambda path: (Tokenizer(), Model(), 2))
    scores = N.entailment_scores([('premise', 'hypothesis'), ('oversized', 'hypothesis')])
    assert scores[0] == pytest.approx(torch.tensor([0.0, 0.0, 0.95]).softmax(-1)[2].item())
    assert scores[0] < 0.90
    assert scores[1] is None and len(calls) == 1


def test_unavailable_model_fails_closed(monkeypatch):
    monkeypatch.setattr(N, '_load_model', lambda path: None)
    assert N.entailment_scores([('premise', 'hypothesis')]) == [None]


def test_model_loader_uses_local_safetensors_and_configured_label_order(monkeypatch):
    import sys
    calls = []
    class Model:
        config = SimpleNamespace(id2label={0: 'neutral', 1: 'contradiction', 2: 'entailment'})
        def to(self, device):
            assert device == 'cpu'
            return self
        def eval(self):
            return self
    def tokenizer(path, **kwargs):
        calls.append(kwargs)
        return Tokenizer()
    def model(path, **kwargs):
        calls.append(kwargs)
        return Model()
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer),
        AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=model)))
    N._load_model.cache_clear()
    try:
        assert N._load_model('test-local-model')[2] == 2
        assert all(c['local_files_only'] and not c['trust_remote_code'] for c in calls)
        assert calls[1]['use_safetensors']
    finally:
        N._load_model.cache_clear()


@pytest.mark.parametrize('label', ['BERTScore', 'bertScore', 'HR', 'Context relevance',
                                  'answer relevance', 'long tail coverage', 'HD95', '95HD'])
def test_named_metrics_are_valid_without_a_numeric_shortcut(label):
    assert G._value_sane('metrics', label)


@pytest.mark.parametrize('label,definition', [
    ('popularity lift', 'We evaluate exposure metrics including popularity lift.'),
    ('mean popularity rank', 'Our evaluation metrics include mean popularity rank.'),
    ('Average number of retrieved tokens (#Token)',
     'We measure efficiency using the Average number of retrieved tokens (#Token).'),
    ('Win and tie ratio (W+T)', 'We evaluate the Win and tie ratio (W+T).'),
    ('Retrieval Contexts', 'We report the total number of fetched contexts (Retrieval Contexts).'),
    ('Repeat Prompts', 'We report the number of prompts producing direct tokens (Repeat Prompts).'),
    ('Targeted Information', 'For targeted attacks, we report extracted information (Targeted Information).'),
])
def test_custom_metrics_require_a_local_measurement_definition(label, definition):
    assert not G._value_sane('metrics', label)
    assert G._value_sane('metrics', label, [chunk(definition)])
    assert not G._value_sane('metrics', label, [chunk('We discuss ' + label + '.')])


@pytest.mark.parametrize('value', ['2026', '73', 'There were 73 papers', 'Version 3.10',
                                  'repeat prompts 20', ['BERTScore', '2026']])
def test_digits_do_not_turn_nonmetric_values_into_metrics(value):
    assert not G._value_sane('metrics', value)


def test_hyphenated_metric_label_flows_through_gate(monkeypatch):
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'legacy')
    result = G.gate_paper({'metrics': ['long tail coverage']},
                          [chunk('We evaluate long-tail coverage.')], G.FULL_TEXT, [])
    assert result['metrics'] == ['long tail coverage']
    assert result['evidence']['metrics'][0]['attribution'] == G.OWN_PAPER


def test_author_defined_judge_rating_requires_a_real_reported_value():
    label = 'GPT-4-based expert evaluation'
    assert not G._value_sane('metrics', label)
    assert not G._value_sane('metrics', label, [chunk('We discuss ' + label + '.')])
    assert G._value_sane('metrics', label, [chunk(
        'Generated explanations reached 0.94 in BERTScore and 4.9/5 in GPT-4-based expert evaluation.')])


def test_dataset_grounding_keeps_its_existing_policy():
    label = 'central hospital imaging validation cohort'
    assert G._ground(label, [chunk('We evaluate central hospital imaging validation studies.')],
                     field='datasets') is not None


@pytest.mark.parametrize('label', ['IoU-based Human Evaluation', 'Dice-based evaluation',
                                  'Jamming success rates', 'attack failure rate', 'error rates'])
def test_named_metric_qualifiers_and_standard_rates_are_sane(label):
    assert G._value_sane('metrics', label)


@pytest.mark.parametrize('label', ['IoU-basedness', 'IoUish-based evaluation',
                                  'successrateModel', 'confidence intervals', 'Logical consistency'])
def test_metric_qualifiers_do_not_admit_lookalikes_or_broad_descriptions(label):
    assert not G._value_sane('metrics', label)
