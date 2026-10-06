"""Class B: per-value support and required comparison coverage."""
import pytest
from src.evidence import binder_v2 as B


def paper(cells):
    cap = 'Table 1: Study measurements.'
    return [{'chunk_id': 'synthetic:b', 'block_type': 'table', 'text': cap,
             'table_cells': [dict(row_label=row, column_header=col, value=value,
                                  caption=cap, row=i + 1, col=1, page=1)
                             for i, (row, col, value) in enumerate(cells)]}]


@pytest.mark.parametrize('claim,cells', [
    ('DeltaNet reports Dice of 0.68 and Precision of 0.82.',
     [('DeltaNet', 'Dice', '0.68'), ('DeltaNet', 'Precision', '0.79')]),
    ('DeltaNet reports Dice of 0.68 while SigmaNet reports Dice of 0.82.',
     [('DeltaNet', 'Dice', '0.68'), ('SigmaNet', 'Dice', '0.79')]),
    ('DeltaNet has an activation coefficient of 0.68 and reports Dice of 0.82.',
     [('DeltaNet', 'Dice', '0.68'), ('DeltaNet', 'Dice', '0.82')]),
])
def test_no_partial_or_borrowed_quantity(claim, cells, monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    got = B.structural_bind_v2(claim, paper(cells))
    assert got['status'] != 'bound', got


@pytest.mark.parametrize('claim,cells', [
    ('DeltaNet reports Dice of 0.68 and Precision of 0.82.',
     [('DeltaNet', 'Dice', '0.68'), ('DeltaNet', 'Precision', '0.82')]),
    ('DeltaNet reports Dice of 0.68 while SigmaNet reports Dice of 0.82.',
     [('DeltaNet', 'Dice', '0.68'), ('SigmaNet', 'Dice', '0.82')]),
    ('DeltaNet reports Dice of 0.68 and Precision of 0.68.',
     [('DeltaNet', 'Dice', '0.68'), ('DeltaNet', 'Precision', '0.68')]),
])
def test_complete_independent_support(claim, cells, monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    got = B.structural_bind_v2(claim, paper(cells))
    assert got['status'] == 'bound', got
    assert {(x['cell']['row'], x['cell']['col'], x['cell']['value']) for x in got['bindings']} == set(cells)
