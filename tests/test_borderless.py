"""Phase 09A borderless backend: gates G1-G3, consensus, and the default-off flag.

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider tests/test_borderless.py -q

No table model runs here. The gates and the consensus are pure functions over synthetic words and grids,
and the flag tests replace the backend entry point. So these tests pass in the production venv too, which
has no docling or torch. Definitions: src/evaluation/borderless_09a/PREREG_09A.md.
"""
import sys

import pytest

import src.evidence.represent as R
from src.evidence import borderless as BL
from tests.test_pdf_table_cells import _grid, _pdf


def W(x0, y0, text, line, word=0, w=40, h=8):
    return (x0, y0, x0 + w, y0 + h, text, 0, line, word)


WORDS = [W(10, 10, "Model", 0, 0), W(60, 10, "Dice", 0, 1),
         W(10, 30, "A", 1, 0), W(60, 30, "0.87±0.06", 1, 1),
         W(10, 50, "B", 2, 0), W(60, 50, "0.90", 2, 1),
         W(10, 70, "C", 3, 0), W(60, 70, "−0.12", 3, 1)]
BODY = [["A", "0.87 ± 0.06"], ["B", "0.90"], ["C", "-0.12"]]
TEXTS = [{"text": "0.87 ± 0.06", "center": (80, 34)}, {"text": "0.90", "center": (80, 54)},
         {"text": "-0.12", "center": (80, 74)}]


def test_normalisation():
    assert BL.norm("0.87±0.06") == BL.norm("0.87 ± 0.06") == BL.norm("0.87 ± 0.06")
    assert BL.norm("−0.12") == BL.norm("-0.12")
    assert BL.norm("**89.76±5.09**") == BL.norm("89.76±5.09*") == BL.norm("89.76±5.09†")


def test_g1_accepts_minus_and_plus_minus_spacing_and_rejects_a_hallucinated_digit():
    assert BL.gate_g1(BODY, 0, WORDS)["pass"]
    bad = BL.gate_g1([["A", "0.87 ± 0.06"], ["B", "0.91"], ["C", "-0.12"]], 0, WORDS)
    assert not bad["pass"] and bad["failures"] == ["0.91"]


def test_g2_rejects_a_dropped_row_and_a_duplicated_row():
    assert BL.gate_g2(TEXTS, WORDS, None)["pass"]
    dropped = BL.gate_g2(TEXTS[:1] + TEXTS[2:], WORDS, None)
    assert not dropped["pass"] and dropped["missing"] == ["0.90"]
    duplicated = BL.gate_g2(TEXTS + [{"text": "0.90", "center": (80, 94)}], WORDS, None)
    assert not duplicated["pass"] and duplicated["duplicated"] == ["0.90"]


def test_g2_ignores_caption_and_footnote_lines():
    assert BL.gate_g2(TEXTS, WORDS + [W(10, 90, "Note:", 4, 0), W(60, 90, "p<0.05", 4, 1)], None)["pass"]
    caption = [W(10, -10, "Table", 9, 0), W(60, -10, "3.", 9, 1)]
    assert BL.gate_g2(TEXTS, caption + WORDS, [0, -12, 120, 0])["pass"]


def test_g3_structure():
    assert BL.gate_g3(["Model", "Dice"], BODY, 0)["pass"]
    assert BL.gate_g3(["Model", "Dice"], BODY[:1], 0)["problem"] == "too_few_data_rows:1"
    assert BL.gate_g3(["Model"], BODY, 0)["problem"] == "too_few_columns:1"
    assert BL.gate_g3(["Model", "D" * 41], BODY, 0)["problem"] == "header_too_long"
    assert BL.gate_g3(["Model", "Dice"], [["x" * 61, "0.9"], ["B", "0.8"]], 0)["problem"] == "row_label_too_long"


def parser(triples, **gates):
    base = {"candidate": True, "G1": {"pass": True}, "G2": {"pass": True}, "G3": {"pass": True}, "triples": triples}
    return {**base, **{g: {"pass": v} for g, v in gates.items()}}


T = [["a", "dice", "0.87±0.06"], ["b", "dice", "0.90"]]


def test_consensus_rejects_a_single_disagreeing_cell():
    assert BL.decide(parser(T), parser(T))[0] is None
    code, only_a, only_b = BL.decide(parser(T), parser([T[0], ["b", "dice", "0.91"]]))
    assert (code, only_a, only_b) == ("disagree", [["b", "dice", "0.90"]], [["b", "dice", "0.91"]])


def test_reason_codes_follow_the_preregistered_order():
    assert BL.decide({"candidate": False}, parser(T))[0] == "no_candidate"
    assert BL.decide(parser(T, G1=False, G2=False), parser(T))[0] == "G1"
    assert BL.decide(parser(T), parser(T, G2=False, G3=False))[0] == "G2"
    assert BL.decide(parser(T, G3=False), parser(T))[0] == "G3"


def test_grid_folds_header_rows_and_keeps_spans_as_none():
    c = lambda r0, r1, c0, c1, text, header: {"r0": r0, "r1": r1, "c0": c0, "c1": c1, "text": text, "header": header,
                                              "center": None}
    t = {"rows": 4, "cols": 3, "cells": [
        c(0, 2, 0, 1, "Model", True), c(0, 1, 1, 3, "Dice", True), c(1, 2, 1, 2, "WT", True), c(1, 2, 2, 3, "TC", True),
        c(2, 4, 0, 1, "Ours", False), c(2, 3, 1, 2, "0.91", False), c(2, 3, 2, 3, "0.85", False),
        c(3, 4, 1, 2, "0.90", False), c(3, 4, 2, 3, "0.84", False)]}
    header, body, texts = BL.grid_of(t)
    assert header == ["Model", "Dice / WT", "Dice / TC"]
    assert body == [["Ours", "0.91", "0.85"], [None, "0.90", "0.84"]]
    assert len(texts) == 4


def test_tatr_grid_assigns_words_by_overlap_and_merges_spanning_cells():
    rows, cols = [[0, 0, 200, 20], [0, 20, 200, 40], [0, 40, 200, 60]], [[0, 0, 100, 60], [100, 0, 200, 60]]
    words = [(10, 5, 40, 15, "Model", 0, 0, 0), (110, 5, 140, 15, "Dice", 0, 0, 1),
             (10, 35, 40, 45, "Ours", 0, 1, 0), (110, 25, 140, 35, "0.91", 0, 2, 0), (110, 45, 140, 55, "0.90", 0, 3, 0)]
    g = BL._tatr_cells(rows, cols, [[0, 0, 200, 20]], [[0, 20, 100, 60]], words)
    header, body, _ = BL.grid_of(g)
    assert header == ["Model", "Dice"] and body == [["Ours", "0.91"], [None, "0.90"]]


def test_caption_matching_uses_the_ruled_gap_rule():
    cap = [72, 100, 400, 112]
    below, far, beside = ({"bbox": b} for b in ([72, 120, 400, 300], [72, 200, 400, 300], [450, 120, 550, 300]))
    assert BL.match_caption([far, below, beside], cap)[0] is below
    assert BL.match_caption([far, beside], cap) is None


# --- the flag -----------------------------------------------------------------------------------------------------
def _ruled_page(page):
    page.insert_text((72, 200), "Table 1: Results with ruling lines.", fontsize=10)
    _grid(page, 72, 225, [140, 90], [["Model", "Dice"], ["A", "0.81"], ["B", "0.84"]])


def _borderless_page(page):
    page.insert_text((72, 200), "Table 2: Results without ruling lines.", fontsize=10)
    for i, row in enumerate([["Model", "Dice"], ["A", "0.87"], ["B", "0.90"]]):
        for k, text in enumerate(row):
            page.insert_text((72 + 140 * k, 230 + 16 * i), text, fontsize=9)


@pytest.fixture
def pdf_bytes():
    return _pdf(_ruled_page, _borderless_page)


def test_flag_resolution(monkeypatch):
    monkeypatch.delenv("RGPT_BORDERLESS_POLICY", raising=False)
    assert R._borderless_policy() == "consensus"        # the default since phase 09B (configs/staging_config.yaml)
    monkeypatch.setenv("RGPT_BORDERLESS_POLICY", "off")
    assert R._borderless_policy() == "off"              # the variable wins over the config
    monkeypatch.setenv("RGPT_BORDERLESS_POLICY", "bogus")
    assert R._borderless_policy() == "consensus"


def test_flag_off_output_is_identical_and_the_backend_is_never_called(monkeypatch, pdf_bytes):
    def boom(*a, **k):
        raise AssertionError("borderless backend called with the flag off")
    monkeypatch.setattr(BL, "attach_borderless", boom)
    monkeypatch.setenv("RGPT_BORDERLESS_POLICY", "off")
    flagged = R.blocks_from_pdf(pdf_bytes, "SYN", "t")
    monkeypatch.setattr(R, "_attach_borderless_cells", lambda data, doc, captions: None)    # the pre-09A path
    assert flagged == R.blocks_from_pdf(pdf_bytes, "SYN", "t")
    assert not any(m in sys.modules for m in ("docling", "transformers"))


def test_consensus_routes_only_ruled_path_rejects(monkeypatch, pdf_bytes):
    seen = []
    monkeypatch.setattr(BL, "attach_borderless", lambda data, doc, todo: seen.extend(b["text"] for b, _, _ in todo))
    monkeypatch.setenv("RGPT_BORDERLESS_POLICY", "consensus")
    blocks = R.blocks_from_pdf(pdf_bytes, "SYN", "t")
    assert seen == ["Table 2: Results without ruling lines."]
    ruled = next(b for b in blocks if b["text"].startswith("Table 1:"))
    assert ruled["table_parse_status"] == "parsed" and ruled["table_cells"]
