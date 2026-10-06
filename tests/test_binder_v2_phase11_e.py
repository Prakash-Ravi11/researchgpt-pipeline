"""Class E: invented reproductions of A4 metric recognition and status mechanisms."""
import pytest

from src.evidence import binder_v2 as B, gate as G


def paper(cells):
    caption = 'Table 7: Results of the lantern study.'
    text = 'We present our method. Our method reports measured results. ' + ' '.join(
        ' '.join(cell) for cell in cells)
    return [dict(chunk_id='synthetic:e', block_id='synthetic:e', block_type='table',
                 representation='latex', section='results', source='synthetic',
                 page_or_node='p7', char_start=0, char_end=len(text), text=text,
                 table_caption=caption,
                 table_cells=[dict(row_label=row, column_header=col, value=value,
                                   caption=caption, section='results', page=7)
                              for row, col, value in cells])]


@pytest.fixture(autouse=True)
def deterministic_v2(monkeypatch):
    monkeypatch.setenv('RGPT_BINDER_POLICY', 'v2')
    monkeypatch.setenv('RGPT_FALLTHROUGH_POLICY', 'table_value_guard')
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)


@pytest.mark.parametrize('metric', ['LumaGain@7', 'ZetaYield@9'])
def test_compound_metric_own_cell_is_returned(metric):
    chunks = paper([('Ours', metric, '0.7328'), ('BirchNet', metric, '0.5186')])
    claim = f'Our method reports a {metric} of 0.7328.'
    chunks[0]['text'] = claim
    got = G._gate_value('results', claim, chunks, [])
    assert got['structural_binding']['status'] == 'bound', got
    assert got['final'] == 'RETURNED', got


def test_compound_metric_cross_row_is_wrong_cell():
    chunks = paper([('Ours', 'LumaGain@7', '0.7328'), ('BirchNet', 'LumaGain@7', '0.5186')])
    got = G._gate_value('results', 'Our method reports LumaGain@7 of 0.5186.', chunks, [])
    assert got['abstain_reason'] == 'binding_wrong_cell', got


def test_compound_metric_cutoff_is_not_interchangeable():
    chunks = paper([('Ours', 'LumaGain@7', '0.7328')])
    assert B.structural_bind_v2('Our method reports LumaGain@9 of 0.7328.', chunks)['status'] != 'bound'


@pytest.mark.parametrize('claim,expected', [
    ('Our method reports NovaGain of 0.8467.', 'not_bindable'),
    ('Cedar reports specimen readings of 28.', 'not_bindable'),
    ('Our method reports LumaGain of 0.8467.', 'not_a_table_claim'),
])
def test_absent_value_requires_quantity_scope(claim, expected):
    got = B.structural_bind_v2(claim, paper([('Ours', 'LumaGain', '0.7328')]))
    assert got['status'] == expected, got


@pytest.mark.parametrize('heading', ['Model scores', 'System results'])
@pytest.mark.parametrize('value', ['64.37', '71.26'])
def test_generic_group_heading_is_not_a_quantity(heading, value):
    chunks = paper([('BirchNet', heading, '64.37'), ('CedarNet', heading, '71.26'),
                    ('AspenNet', heading, '58.49'), ('BirchNet', 'Accuracy', '65.48')])
    claim = f'AspenNet reports {heading} of {value}.'
    got = B.structural_bind_v2(claim, chunks)
    assert got['status'] == 'not_bindable', got
    gated = G._gate_value('results', claim, chunks, [])
    assert gated['final'] == 'ABSTAINED' and gated['abstain_reason'] == 'table_value_unbound', gated


def test_explicit_quantity_cross_row_remains_wrong_cell():
    chunks = paper([('BirchNet', 'LumaGain', '64.37'), ('AspenNet', 'LumaGain', '58.49')])
    got = B.structural_bind_v2('AspenNet reports LumaGain of 64.37.', chunks)
    assert got['status'] == 'wrong_cell', got


def test_explicit_count_header_remains_bindable():
    chunks = paper([('Birch', 'Specimens', '28')])
    got = B.structural_bind_v2('Birch has 28 specimens.', chunks)
    assert got['status'] == 'bound', got
