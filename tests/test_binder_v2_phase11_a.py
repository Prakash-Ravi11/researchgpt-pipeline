"""Class A: general quantity-type and subject near misses; no evaluation data."""
import pytest
from src.evidence import binder_v2 as B


def paper(header='Dice', value='0.68', row='DeltaNet'):
    cap = 'Table 1: Measurements for the study.'
    return [{'chunk_id': 'synthetic:1', 'block_type': 'table', 'text': cap,
             'table_cells': [{'row_label': row, 'column_header': header, 'value': value,
                              'caption': cap, 'row': 1, 'col': 1, 'page': 1}]}]


@pytest.mark.parametrize('claim,header,value,bound', [
    ('DeltaNet sets a confidence threshold of 0.68 before measuring Dice.', 'Dice', '0.68', False),
    ('DeltaNet uses a learning rate of 0.68 for Dice evaluation.', 'Dice', '0.68', False),
    ('DeltaNet uses a dropout probability of 0.68 for Dice evaluation.', 'Dice', '0.68', False),
    ('DeltaNet uses a batch size of 68 for Dice evaluation.', 'Dice', '68', False),
    ('DeltaNet uses 68 samples for Dice evaluation.', 'Dice', '68', False),
    ('DeltaNet uses 68 epochs for Dice evaluation.', 'Dice', '68', False),
    ('DeltaNet reports Dice of 0.68 with a confidence threshold of 0.31.', 'Dice', '0.68', True),
    ('DeltaNet sets a confidence threshold of 0.31 and reports Dice of 0.68.', 'Dice', '0.68', True),
    ('DeltaNet reports a confidence threshold of 0.68.', 'Confidence threshold', '0.68', True),
    ('DeltaNet uses a learning rate of 0.68.', 'Learning rate', '0.68', True),
    ('DeltaNet uses 68 samples.', 'Number of samples', '68', True),
    ('DeltaNet reports Dice of 0.68.', 'Dice', '0.68', True),
    ('OtherNet reports Dice of 0.68.', 'Dice', '0.68', False),
    ('DeltaNet reports Dice of 0.68 on ExternalGroup.', 'InternalGroup / Dice', '0.68', False),
])
def test_quantity_type_and_subject(claim, header, value, bound, monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    got = B.structural_bind_v2(claim, paper(header, value))
    assert (got['status'] == 'bound') == bound, got
    if bound:
        assert got['cell']['row'] == 'DeltaNet'
        assert got['cell']['col'] == header


def test_raw_verifier_rejects_equal_setting_number():
    chunks = paper()
    good = 'DeltaNet reports Dice of 0.68.'
    idx = B._index(chunks, frozenset())
    fr = B._frame(good, idx, frozenset())
    m, p = fr['mentions'][0], idx['cells'][0]
    lk = B.links(m, p, fr, idx, frozenset())
    bad = 'DeltaNet sets a confidence threshold of 0.68 before measuring Dice.'
    bad_m = B._frame(bad, idx, frozenset())['mentions'][0]
    assert B.verify(bad, bad_m, p, chunks, frozenset(), lk=lk) is not None
