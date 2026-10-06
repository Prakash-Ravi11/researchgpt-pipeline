"""Class C: formatting normalization must preserve semantic distinctions."""
import pytest
from src.evidence import binder_v2 as B
from tests.test_binder_v2_phase11_a import paper


@pytest.mark.parametrize('row,header,value,claim', [
    ('DeltaNet (Proposed)', 'Dice', '0.68', 'Our method reports Dice of 0.68.'),
    ('DeltaNet [Proposed]', 'Dice', '0.68', 'Our method reports Dice of 0.68.'),
    ('DeltaNet (Ours)', 'Dice', '0.68', 'Our method reports Dice of 0.68.'),
    ('Proposed Method', 'Dice', '0.68', 'Our method reports Dice of 0.68.'),
    ('Ours', 'Dice', '0.68', 'Our method reports Dice of 0.68.'),
    ('DeltaNet [57]', 'Dice↑', '0.68', 'DeltaNet reports Dice of 0.68.'),
    ('DeltaNet (Proposed)', 'Dice↑', '0.68±0.02*', 'DeltaNet reports Dice of 0.68 ± 0.02.'),
    ('DeltaNet', 'Dice (%)↑', '68.4% ± 1.6%*', 'DeltaNet reports Dice of 68.4% ± 1.6%.'),
    ('DeltaNet', 'InternalGroup / Dice (%)↑', '68.4±1.6*',
     'DeltaNet reports Dice of 68.4% ± 1.6% on InternalGroup.'),
    ('DeltaNet', 'Mas k', '0.68', 'DeltaNet reports mask of 0.68.'),
])
def test_supported_decorations(row, header, value, claim, monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    got = B.structural_bind_v2(claim, paper(header, value, row))
    assert got['status'] == 'bound', got
    assert got['cell']['row'] == row and got['cell']['value'] == value


@pytest.mark.parametrize('row,header,value,claim', [
    ('DeltaNet (Proposed) without attention', 'Dice', '0.68', 'Our method reports Dice of 0.68.'),
    ('DeltaNet (pretrained)', 'Dice', '0.68', 'DeltaNet (scratch) reports Dice of 0.68.'),
    ('DeltaNet', 'InternalGroup / Dice', '0.68', 'DeltaNet reports Dice of 0.68 on ExternalGroup.'),
    ('DeltaNet', 'Dice (%)', '68.4% ± 1.6%*', 'DeltaNet reports Dice of 68.4% ± 2.1%.'),
    ('DeltaNet', 'Distance (mm)', '68.4', 'DeltaNet reports distance of 68.4 cm.'),
])
def test_semantic_decorations_are_not_erased(row, header, value, claim, monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)
    assert B.structural_bind_v2(claim, paper(header, value, row))['status'] != 'bound'
