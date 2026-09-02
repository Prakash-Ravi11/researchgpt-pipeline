"""Tests for src.evidence.anchors — the single source of truth for the
meaningful-numeric-anchor rule (shared by the evidence gate and the Test 2 /
Test 3 harnesses).

Includes a neutrality check: an inline verbatim copy of the pre-centralization
`anchors_in_text` / `is_anchor` from retrieval_recall.py, asserted equal to the
new `find_anchors` on strings that exercise every branch.
"""
import re

from src.evidence.anchors import (
    NUMERIC_ANCHOR_RE,
    anchor_values,
    find_anchors,
    is_meaningful_anchor,
)


# --- the core token rule ------------------------------------------------------
def test_matches_decimal_and_2plus_digit_int():
    assert NUMERIC_ANCHOR_RE.findall("dice 0.72 and 94 points, 2165 total") == ["0.72", "94", "2165"]


def test_rejects_lone_single_digit():
    # single digits are identifier fragments (BLEU-4, GPT-4, T3)
    assert NUMERIC_ANCHOR_RE.findall("BLEU-4 and GPT-4 on T3") == []
    assert NUMERIC_ANCHOR_RE.findall("improved by 3 points") == []


def test_anchor_values_no_exclusions():
    assert anchor_values("nDCG@5 = 0.4502 in 2021") == {"0.4502", "2021", "5"} - {"5"}  # 5 is single-digit, dropped
    assert anchor_values("nDCG@5 = 0.4502 in 2021") == {"0.4502", "2021"}


# --- is_meaningful_anchor branch coverage -----------------------------------
def test_year_excluded():
    assert is_meaningful_anchor("2021") is False
    assert is_meaningful_anchor("1998") is False
    assert is_meaningful_anchor("94.9") is True


def test_bracketed_reference_id_excluded():
    assert is_meaningful_anchor("12", before="as shown in [", inside_brackets=True) is False


def test_section_table_equation_prefix_excluded():
    assert is_meaningful_anchor("31", before="see Section ") is False
    assert is_meaningful_anchor("41", before="in Table ") is False
    assert is_meaningful_anchor("22", before="Eq. ") is False
    assert is_meaningful_anchor("35", before="the Dice was ") is True


def test_arxiv_fragment_excluded():
    assert is_meaningful_anchor("01234", before="arXiv:2401.") is False


# --- find_anchors end to end -----------------------------------------------
def test_find_anchors_offsets_and_filtering():
    text = "In 2021 the model reached 94.9 Dice (see Table 3) per [12], up 45 points."
    got = find_anchors(text)
    vals = [v for v, _ in got]
    assert "2021" not in vals          # year
    assert "94.9" in vals              # real result
    assert "3" not in vals            # single digit anyway
    assert "12" not in vals           # bracketed ref id
    assert "45" in vals               # real result
    # offsets point at the token
    for v, pos in got:
        assert text[pos:pos + len(v)] == v


# --- NEUTRALITY: inline copy of the pre-centralization logic ----------------
_OLD_NUMVAL = re.compile(r"\d+\.\d+|\b\d{2,}\b")
_OLD_YEAR = re.compile(r"^(19|20)\d{2}$")
_OLD_EXCLUDE_PREFIX = re.compile(
    r"(section|sec\.?|equation|eq\.?|figure|fig\.?|table|tab\.?|appendix|"
    r"chapter|line|step|version|v)\s*$", re.I)


def _old_is_anchor(value, before, inside_brackets):
    if _OLD_YEAR.match(value):
        return False
    if inside_brackets:
        return False
    if _OLD_EXCLUDE_PREFIX.search(before[-14:]):
        return False
    if re.search(r"\d{4}\.\d{4,5}$", before + value):
        return False
    return True


def _old_anchors_in_text(text):
    out = []
    for m in _OLD_NUMVAL.finditer(text):
        s = m.start()
        before = text[max(0, s - 20):s]
        lb, rb = text.rfind("[", 0, s), text.rfind("]", 0, s)
        if _old_is_anchor(m.group(0), before, lb > rb):
            out.append((m.group(0), s))
    return out


_NEUTRALITY_SAMPLES = [
    "The proposed method reaches 94.9 Dice and 0.4502 nDCG@5 on TREC 2024.",
    "As reported in [12] and [3-5], accuracy rose 45 points (Section 3.1, Eq. 2).",
    "arXiv:2401.01234 — see Table 4, Figure 12, appendix 7, step 3, version 2.",
    "no numbers here at all",
    "1998 1999 2020 2026 are years; 100 200 0.5 12.34 are not",
    "]12[ weird brackets 34 ] 56 [ 78",
    "line 40 of the file; v 21 of the api; chapter 15; 3.14159 pi; 42",
]


def test_neutrality_against_pre_centralization_implementation():
    for s in _NEUTRALITY_SAMPLES:
        assert find_anchors(s) == _old_anchors_in_text(s), s
