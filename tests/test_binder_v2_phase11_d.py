"""Class D: legacy preservation must survive raw rechecking, never semantic vetoes.

The positive reproduction injects a conservative initial candidate-index omission.
Raw evidence is unchanged, and the verifier receives the complete fresh index.
"""
import pytest
from src.evidence import binder_v2 as B, gate as G
from tests.test_binder_v2_phase11_b import paper


def omit_initial_candidate_index(monkeypatch):
    original = B._index
    calls = 0
    def index(chunks, off):
        nonlocal calls
        calls += 1
        result = original(chunks, off)
        return dict(result, by_value={}) if calls == 1 else result
    monkeypatch.setattr(B, '_index', index)


@pytest.mark.parametrize('suffix', ['', ' and Precision of 0.82'])
def test_verified_legacy_cell_survives_conservative_candidate_omission(suffix, monkeypatch):
    chunks = paper([('Ours', 'Dice', '0.68'), ('Ours', 'Precision', '0.79')])
    claim = 'Our method reports Dice of 0.68' + suffix + '.'
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'legacy')
    assert G.structural_bind(claim, chunks)['status'] == 'bound'
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'v2')
    omit_initial_candidate_index(monkeypatch)
    got = G.structural_bind(claim, chunks)
    assert got['status'] == 'bound', got
    assert got['cell']['row'] == 'Ours' and got['cell']['col'] == 'Dice'
    assert len(got['bindings']) == 1 and got['legacy_preserved'] is True
    assert G._binder_policy() == 'v2'


@pytest.mark.parametrize('claim', [
    'Our method sets a confidence threshold of 0.68 before measuring Dice.',
    'Our method reports Dice of 0.68 in Table 2.',
])
@pytest.mark.parametrize('omit', [False, True])
def test_legacy_wrong_stays_rejected(claim, omit, monkeypatch):
    chunks = paper([('Ours', 'Dice', '0.68')])
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'legacy')
    assert G.structural_bind(claim, chunks)['status'] == 'bound'
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'v2')
    if omit:
        omit_initial_candidate_index(monkeypatch)
    assert G.structural_bind(claim, chunks)['status'] != 'bound'


def test_legacy_first_cell_cannot_rescue_partial_coverage(monkeypatch):
    chunks = paper([('Ours', 'Dice', '0.68'), ('OtherNet', 'Precision', '0.82')])
    claim = 'Our method reports Dice of 0.68 and Precision of 0.82.'
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'legacy')
    assert G.structural_bind(claim, chunks)['status'] == 'bound'
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'v2')
    omit_initial_candidate_index(monkeypatch)
    assert G.structural_bind(claim, chunks)['status'] != 'bound'


def test_legacy_order_cannot_resolve_ambiguous_tables(monkeypatch):
    chunks = paper([('Ours', 'Dice', '0.68')])
    other = paper([('Ours', 'Dice', '0.68')])[0]
    other['chunk_id'] = 'synthetic:second'
    other['text'] = other['table_cells'][0]['caption'] = 'Table 2: Study measurements.'
    chunks.append(other)
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'v2')
    omit_initial_candidate_index(monkeypatch)
    assert G.structural_bind('Our method reports Dice of 0.68.', chunks)['status'] != 'bound'
