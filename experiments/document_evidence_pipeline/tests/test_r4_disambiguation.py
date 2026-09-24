"""Unit tests for R4 scored cell disambiguation (src/evidence/gate.py).

Legacy must stay byte-identical in behaviour; scored must change only which of the
SAME value-matching candidates is chosen.

Structural note that shapes these tests: in the `col_hits` branch every candidate
is drawn from `metric_columns`, so its column header already matches the claim's
metric and its score is therefore always >= 1. A zero top score is only reachable
through the `elsewhere` branch (case 5b), where candidates are any cell carrying
the value. Both branches are covered.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evidence import gate as G  # noqa: E402
from src.evidence.schema import table_cell  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_policy(monkeypatch):
    monkeypatch.delenv("RGPT_DISAMBIGUATION_POLICY", raising=False)
    yield


def legacy(monkeypatch):
    monkeypatch.setenv("RGPT_DISAMBIGUATION_POLICY", "legacy")


def scored(monkeypatch):
    monkeypatch.setenv("RGPT_DISAMBIGUATION_POLICY", "scored")


def cell(value, col, row, caption="Table 1: Results."):
    return table_cell(value=value, column_header=col, row_label=row,
                      caption=caption, section="results", row=1, col=1)


def chunks(cells):
    return [{"paper_id": "P", "block_type": "table", "section": "results",
             "table_cells": cells}]


# ---- 1. unique scored winner ---------------------------------------------

def test_unique_scored_winner_agrees_with_legacy_when_the_row_is_the_subject(monkeypatch):
    """When the row label IS the claim's grammatical subject, legacy's existing
    `on_row` filter (gate.py:472) already resolves it. Scored must not regress that:
    both modes bind to the same cell."""
    cells = [cell("92.3", "Accuracy (%)", "BaselineNet"),
             cell("92.3", "Accuracy (%)", "TransformerX")]
    claim = "TransformerX reports an accuracy of 92.3 on the benchmark."

    legacy(monkeypatch)
    lo = G.structural_bind(claim, chunks(cells))
    scored(monkeypatch)
    so = G.structural_bind(claim, chunks(cells))

    assert lo["status"] == so["status"] == "bound"
    assert lo["cell"]["row"] == so["cell"]["row"] == "TransformerX"
    assert so["r4"]["top_score"] == 2 and so["r4"]["n_winners"] == 1


def test_unique_scored_winner_diverges_when_the_row_is_not_the_subject(monkeypatch):
    """The row label appears in the claim but NOT as the grammatical subject, so
    legacy's `on_row` filter finds nothing and it reports wrong_cell against the
    first candidate in document order. Scored scores TransformerX higher and binds.
    This is the divergence R4 exists to produce."""
    cells = [cell("92.3", "Accuracy (%)", "BaselineNet"),
             cell("92.3", "Accuracy (%)", "TransformerX")]
    claim = "Accuracy of 92.3 was obtained by TransformerX in our tests."

    legacy(monkeypatch)
    lo = G.structural_bind(claim, chunks(cells))
    assert lo["status"] == "wrong_cell"
    assert lo["candidate"]["row"] == "BaselineNet"      # first in document order

    scored(monkeypatch)
    so = G.structural_bind(claim, chunks(cells))
    assert so["status"] == "bound"
    assert so["cell"]["row"] == "TransformerX"
    assert so["r4"]["top_score"] == 2 and so["r4"]["n_winners"] == 1


def test_unique_winner_scores_two_when_header_and_row_both_hit(monkeypatch):
    scored(monkeypatch)
    cells = [cell("92.3", "Accuracy (%)", "TransformerX"),
             cell("92.3", "Accuracy (%)", "Zeta")]
    out = G.structural_bind(
        "TransformerX reports an accuracy of 92.3 overall.", chunks(cells))
    assert out["status"] == "bound" and out["r4"]["top_score"] == 2


# ---- 2. tie -> ABSTAIN_AMBIGUOUS ----------------------------------------

def test_tie_abstains(monkeypatch):
    """Both candidates score 1 (metric header matches, neither row named)."""
    cells = [cell("92.3", "Accuracy (%)", "Alpha"),
             cell("92.3", "Accuracy (%)", "Beta")]
    claim = "The pipeline reports an accuracy of 92.3 on the held-out split."

    scored(monkeypatch)
    out = G.structural_bind(claim, chunks(cells))
    assert out["status"] == "ABSTAIN_AMBIGUOUS"
    assert out["r4"]["top_score"] == 1 and out["r4"]["n_winners"] == 2
    assert "cell" not in out


def test_tie_when_both_rows_named_in_the_claim(monkeypatch):
    scored(monkeypatch)
    cells = [cell("92.3", "Accuracy (%)", "Alpha"),
             cell("92.3", "Accuracy (%)", "Beta")]
    out = G.structural_bind(
        "Alpha and Beta both reach an accuracy of 92.3 here.", chunks(cells))
    assert out["status"] == "ABSTAIN_AMBIGUOUS"
    assert out["r4"]["top_score"] == 2 and out["r4"]["n_winners"] == 2


# ---- 3. zero score -> ABSTAIN_AMBIGUOUS --------------------------------

def test_zero_score_abstains_via_cross_column_candidates(monkeypatch):
    """The metric IS a column in the paper, but the value lives only in a
    different column whose header does not match and whose row is unnamed. Legacy
    calls that wrong_cell; scored scores it 0 and abstains."""
    cells = [cell("77.7", "Accuracy (%)", "Alpha"),       # makes accuracy a column
             cell("92.3", "Latency (ms)", "Gamma")]       # the value, wrong column
    claim = "The system reports an accuracy of 92.3 in this configuration."

    legacy(monkeypatch)
    lo = G.structural_bind(claim, chunks(cells))
    assert lo["status"] == "wrong_cell"

    scored(monkeypatch)
    so = G.structural_bind(claim, chunks(cells))
    assert so["status"] == "ABSTAIN_AMBIGUOUS"
    assert so["r4"]["top_score"] == 0
    assert "cell" not in so


# ---- 4. table-mention restriction --------------------------------------

def test_table_mention_restricts_to_the_named_table(monkeypatch):
    cells = [cell("92.3", "Accuracy (%)", "Alpha", caption="Table 1: Ablation."),
             cell("92.3", "Accuracy (%)", "Beta", caption="Table 2: Main results.")]
    claim = "Accuracy reaches 92.3 as reported in Table 2."

    scored(monkeypatch)
    out = G.structural_bind(claim, chunks(cells))
    assert out["status"] == "bound"
    assert out["cell"]["caption"] == "Table 2: Main results."
    assert out["r4"]["restricted"] is True
    assert out["r4"]["n_after_restriction"] == 1


def test_no_restriction_when_two_labels_are_mentioned(monkeypatch):
    cells = [cell("92.3", "Accuracy (%)", "Alpha", caption="Table 1: Ablation."),
             cell("92.3", "Accuracy (%)", "Beta", caption="Table 2: Main results.")]
    scored(monkeypatch)
    out = G.structural_bind(
        "Accuracy reaches 92.3 in Table 1 and Table 2 alike.", chunks(cells))
    assert out["r4"]["restricted"] is False
    assert out["status"] == "ABSTAIN_AMBIGUOUS"          # tie survives, as specified


def test_no_restriction_when_the_label_matches_two_tables(monkeypatch):
    """Two distinct captions both parse to Table 2 -> not exactly one table."""
    cells = [cell("92.3", "Accuracy (%)", "Alpha", caption="Table 2: part one."),
             cell("92.3", "Accuracy (%)", "Beta", caption="Table 2: part two.")]
    scored(monkeypatch)
    out = G.structural_bind("Accuracy reaches 92.3 per Table 2.", chunks(cells))
    assert out["r4"]["restricted"] is False


def test_no_restriction_when_the_mentioned_table_holds_no_candidate(monkeypatch):
    """Restriction must not empty the pool: Table 9 has no candidate, so the
    unrestricted pool is kept."""
    cells = [cell("92.3", "Accuracy (%)", "Alpha", caption="Table 1: Ablation.")]
    scored(monkeypatch)
    out = G.structural_bind("Accuracy reaches 92.3 per Table 9.", chunks(cells))
    assert out["status"] == "bound"
    assert out["r4"]["n_after_restriction"] == 1


# ---- 5. single candidate -> unchanged ----------------------------------

def test_single_candidate_identical_in_both_modes(monkeypatch):
    cells = [cell("92.3", "Accuracy (%)", "Ours")]
    claim = "Our model achieves 92.3% accuracy (Table 1)."

    legacy(monkeypatch)
    lo = G.structural_bind(claim, chunks(cells))
    scored(monkeypatch)
    so = G.structural_bind(claim, chunks(cells))

    assert lo["status"] == so["status"] == "bound"
    assert lo["cell"] == so["cell"]


def test_no_candidate_identical_in_both_modes(monkeypatch):
    cells = [cell("88.1", "Accuracy (%)", "Ours")]
    claim = "Our model achieves 92.3% accuracy (Table 1)."
    legacy(monkeypatch)
    lo = G.structural_bind(claim, chunks(cells))
    scored(monkeypatch)
    so = G.structural_bind(claim, chunks(cells))
    assert lo["status"] == so["status"] == "not_a_table_claim"


def test_pdf_only_identical_in_both_modes(monkeypatch):
    for mode in ("legacy", "scored"):
        monkeypatch.setenv("RGPT_DISAMBIGUATION_POLICY", mode)
        out = G.structural_bind("Accuracy of 92.3 here.", [{"paper_id": "P"}])
        assert out == {"structured": False, "status": "pdf_only"}


def test_not_bindable_identical_in_both_modes(monkeypatch):
    cells = [cell("92.3", "Throughput per hour", "Ours")]
    claim = "Our model achieves a widgetscore of 92.3 overall."
    outs = []
    for mode in ("legacy", "scored"):
        monkeypatch.setenv("RGPT_DISAMBIGUATION_POLICY", mode)
        outs.append(G.structural_bind(claim, chunks(cells)))
    assert outs[0]["status"] == outs[1]["status"] == "not_bindable"


# ---- default policy ----------------------------------------------------

def test_default_policy_is_legacy():
    assert G._disambiguation_policy() == "legacy"


def test_default_run_never_emits_r4_or_abstain_ambiguous():
    """With no env override the shipped config must produce legacy behaviour."""
    cells = [cell("92.3", "Accuracy (%)", "Alpha"),
             cell("92.3", "Accuracy (%)", "Beta")]
    out = G.structural_bind(
        "The pipeline reports an accuracy of 92.3 overall.", chunks(cells))
    assert out["status"] != "ABSTAIN_AMBIGUOUS"
    assert "r4" not in out


# ---- scoring helpers ---------------------------------------------------

def test_row_token_hit_needs_three_chars_and_skips_stopwords():
    assert G._r4_row_token_hit("TransformerX", "TransformerX reports 1.0") is True
    assert G._r4_row_token_hit("X", "X reports 1.0") is False            # too short
    assert G._r4_row_token_hit("the model", "the model reports 1.0") is False
    assert G._r4_row_token_hit("Gamma", "delta reports 1.0") is False


def test_score_components():
    m = G._metric_tokens("accuracy of 92.3")
    assert G._r4_score(cell("92.3", "Accuracy (%)", "Zeta"), m, "accuracy 92.3") == 1
    assert G._r4_score(cell("92.3", "Accuracy (%)", "Zeta"), m, "Zeta accuracy 92.3") == 2
    assert G._r4_score(cell("92.3", "Latency (ms)", "Zeta"), m, "accuracy 92.3") == 0


def test_r4_label_parses_roman_and_arabic():
    assert G._r4_label("Table 12: x") == "12"
    assert G._r4_label("Table II: x") == "II"
    assert G._r4_label("no label here") == ""
