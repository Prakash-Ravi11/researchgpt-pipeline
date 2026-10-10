"""Invented cases for digits in metric names versus asserted numeric values."""
import pytest

from src.evidence import binder_v2 as B


def paper(metric='73Rho', metric_value='1.624'):
    caption = f'Table 9: Prism, {metric} and Zeta measurements.'
    return [dict(chunk_id='synthetic:numeric-metric', block_type='table',
                 text=caption, table_caption=caption,
                 table_cells=[dict(row_label='Ours', column_header=header,
                                   value=value, caption=caption, page=9)
                              for header, value in [('Prism', '0.713'),
                                                    (metric, metric_value),
                                                    ('Zeta', '0.283')]])]


@pytest.fixture(autouse=True)
def deterministic_v2(monkeypatch):
    monkeypatch.delenv('RGPT_BINDER_V2_DISABLE', raising=False)


@pytest.mark.parametrize('metric', ['73Rho', '61Luma'])
def test_numeric_metric_name_preserves_each_local_quantity(metric):
    claim = f'Our method reports Prism of 0.713, {metric} of 1.624, and Zeta of 0.283.'
    got = B.structural_bind_v2(claim, paper(metric))
    assert got['status'] == 'bound', got
    assert {(b['number'], b['cell']['col']) for b in got['bindings']} == {
        ('0.713', 'Prism'), ('1.624', metric), ('0.283', 'Zeta')}


@pytest.mark.parametrize('metric', ['73Rho', '61Luma'])
def test_numeric_metric_name_does_not_allow_cross_quantity_value(metric):
    got = B.structural_bind_v2(f'Our method reports {metric} of 0.713.', paper(metric))
    assert got['status'] == 'wrong_cell', got


@pytest.mark.parametrize('value', ['73', '73 mm'])
def test_real_measurement_equal_to_metric_prefix_is_retained(value):
    got = B.structural_bind_v2(f'Our method reports 73Rho of {value}.', paper(metric_value='73'))
    assert got['status'] == 'bound', got
    assert got['cell']['col'] == '73Rho'
    assert [b['number'] for b in got['bindings']] == ['73']


@pytest.mark.parametrize('claim', [
    'Our method reports 73Rho above 1.624.',
    'Our method improves 73Rho by 1.624.',
])
def test_numeric_metric_name_does_not_turn_non_equality_into_a_measurement(claim):
    got = B.structural_bind_v2(claim, paper())
    assert got['status'] == 'not_a_table_claim', got


def test_different_numeric_metric_prefix_is_not_interchangeable():
    got = B.structural_bind_v2('Our method reports 74Rho of 1.624.', paper())
    assert got['status'] != 'bound', got


def test_postposed_improvement_cannot_bind_a_matching_p_value():
    caption = 'Table 4: Paired p-values for Prism and 83Rho.'
    chunks = [dict(chunk_id='synthetic:delta', block_type='table', text=caption,
                   table_caption=caption,
                   table_cells=[dict(row_label='CedarNet vs. Ours', column_header=header,
                                     value=value, caption=caption, page=4)
                                for header, value in [('Prism', '0.37'), ('83Rho', '0.16')]])]
    claim = ('Our method showed an average of 6% and 0.37 mm improvement in Prism '
             'and 83Rho over BirchNet, respectively.')
    got = B.structural_bind_v2(claim, chunks)
    assert got['status'] != 'bound', got


def test_metric_identifiers_preserve_external_occurrences_and_offsets():
    claim = 'Our method reports 73Rho of 73 and 95HD of 73 mm.'
    got = B.mentions(claim)
    assert [m['tok'] for m in got] == ['73', '73']
    assert [claim[m['start']:m['end']] for m in got] == ['73', '73 mm']
    assert [m['start'] for m in got] == [claim.index('of 73') + 3, claim.rindex('73 mm')]
    assert got[1]['unit'] == 'mm'


def test_attached_unit_is_not_an_identifier():
    claim = 'Our method reports Prism of 73mm.'
    got = B.mentions(claim)
    assert [(m['tok'], m['unit'], claim[m['start']:m['end']]) for m in got] == [('73', 'mm', '73mm')]
