"""General change-role boundaries, independent of evaluation claims and tables."""
import pytest

from src.evidence import binder_v2 as B


@pytest.mark.parametrize('claim,expected', [
    ('Our method reports a 0.37 mm improvement in Prism.', True),
    ('Our method improved Prism by 0.37 mm.', True),
    ('Our method reports a 0.37 mm reduction in error.', True),
    ('Our method reports a 0.37% increase in Prism.', True),
    ('Our method reports an improvement of 0.37 mm in Prism.', True),
    ('Our method reports a 0.37 +/- 0.02 mm improvement in Prism.', True),
    ('The p-value is 0.37.', False),
    ('The test reports p=0.37.', False),
    ('The Dice score is 0.37.', False),
    ('Our method reports Prism of 0.37 mm.', False),
    ('Prism is 0.37; improvement is assessed separately.', False),
    ('Prism is 0.37. Improvement is assessed separately.', False),
    ('Prism is 0.37 and improvement in Zeta is 0.12.', False),
    ('The effect size is 0.37.', False),
], ids=['post_mm', 'prefix_by', 'reduction_mm', 'post_percent', 'prefix_of',
        'post_uncertainty', 'bare_p_value', 'p_equals', 'bare_dice', 'absolute_unit',
        'semicolon_boundary', 'sentence_boundary', 'other_quantity', 'effect_size'])
def test_change_role_is_local_to_the_quantity(claim, expected):
    mention = next(m for m in B.mentions(claim) if m['tok'] == '0.37')
    assert mention['delta'] is expected, mention


def paper(caption, cells):
    return [dict(chunk_id='synthetic:change-role', block_type='table',
                 text=caption, table_caption=caption,
                 table_cells=[dict(row_label='Ours', column_header=header,
                                   value=value, caption=caption, page=4)
                              for header, value in cells])]


@pytest.mark.parametrize('caption', [
    'Table 4: Prism measurements.',
    'Table 4: Paired p-values for Prism.',
], ids=['metric_cell', 'p_value_cell'])
def test_postposed_change_cannot_bind_a_matching_absolute_cell(caption):
    chunks = paper(caption, [('Prism', '0.37')])
    got = B.structural_bind_v2('Our method reports a 0.37 mm improvement in Prism.', chunks)
    assert got['status'] == 'not_a_table_claim', got


def test_absolute_quantity_survives_a_separate_change_quantity():
    chunks = paper('Table 4: Prism measurements.', [('Prism', '0.72')])
    claim = 'Our method reports Prism of 0.72 and a 0.37 mm improvement in error.'
    got = B.structural_bind_v2(claim, chunks)
    assert got['status'] == 'bound', got
    assert [b['number'] for b in got['bindings']] == ['0.72']
    assert next(m for m in B.mentions(claim) if m['tok'] == '0.37')['delta']


def test_bare_p_value_keeps_its_non_change_role():
    chunks = paper('Table 4: Test statistics.', [('p-value', '0.37')])
    got = B.structural_bind_v2('Our method reports a p-value of 0.37.', chunks)
    assert got['status'] == 'bound', got
    assert got['cell']['col'] == 'p-value'


@pytest.mark.parametrize('claim,token,count', [
    ('The p-value 0.37 changes our conclusion.', '0.37', None),
    ('The Dice score 0.37 increases to 0.42.', '0.37', None),
    ('The Dice scores of 0.37 increase after tuning.', '0.37', None),
    ('Our method reports 25 changes.', '25', 'changes'),
], ids=['p_value_predicate', 'dice_predicate', 'plural_score_predicate', 'event_count'])
def test_predicates_and_event_counts_are_not_change_amounts(claim, token, count):
    mention = next(m for m in B.mentions(claim) if m['tok'] == token)
    assert mention['delta'] is False, mention
    assert mention['count'] == count, mention


@pytest.mark.parametrize('claim,expected', [
    ('Our method increased Prism to 0.37.', False),
    ('Our method increased Prism by 0.37.', True),
    ('Our method reports an increase of 0.37.', True),
    ('Prism improved by 0.12; our method reports Dice of 0.37.', False),
    ('Prism improved by 0.12 and our method reports Dice of 0.37.', False),
    ('The Dice scores of 0.37 increase in later experiments.', False),
])
def test_change_amount_and_endpoint_are_distinct(claim, expected):
    mention = next(m for m in B.mentions(claim) if m['tok'] == '0.37')
    assert mention['delta'] is expected
    assert claim[mention['start']:mention['end']] == '0.37'


def test_local_change_does_not_bind_same_value_in_an_absolute_cell():
    claim = 'Our method increased Prism by 0.37.'
    got = B.structural_bind_v2(claim, paper('Table 4: Prism measurements.', [('Prism', '0.37')]))
    assert got['status'] == 'not_a_table_claim'
    assert not got.get('bindings')


def test_change_amounts_share_a_governor_across_coordinated_metric_names():
    claim = 'Our method improved Dice and Prism by 0.37 and 0.12, respectively.'
    mentions = B.mentions(claim)
    assert [(m['tok'], m['delta']) for m in mentions] == [('0.37', True), ('0.12', True)]
    got = B.structural_bind_v2(claim, paper('Table 4: Dice and Prism measurements.',
                                         [('Dice', '0.37'), ('Prism', '0.12')]))
    assert got['status'] == 'not_a_table_claim'
    assert not got.get('bindings')
