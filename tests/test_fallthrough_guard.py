"""Phase 09B fall-through guard (fallthrough_policy=table_value_guard) and its default-legacy flag.

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider tests/test_fallthrough_guard.py -q

Synthetic chunks only, no PDF and no table model. The paper below has one table with attached cells
(Table 1) and one pdf_only table whose caption block holds some table text (Table 2), as the PDF
representation stores them. Definitions: src/evaluation/fallthrough_09b/PREREG_09B.md.
"""
import json
import subprocess
import types
from pathlib import Path

import pytest

import src.evidence.gate as G

ROOT = Path(__file__).resolve().parents[1]
CAP1 = "Table 1: Segmentation results on the test set."
CAP2 = "Table 2: Ablation study. Full 0.93 w/o attention 0.89"
CLAIM = {
    "cell": "Our method reaches 0.150 overall on the benchmark.",                  # not_bindable, 0.150 is a cell
    "pdf_only_table_text": "Our method achieves a Dice of 0.93 on the test set.",  # not_a_table_claim, 0.93 in CAP2
    "prose": "Our method achieves a Dice of 0.91 on the validation set.",          # not_a_table_claim, prose only
    "token": "Our model reaches 15 points overall on the benchmark.",              # cells hold 0.15, 150, 15.2
    "plus_minus": "Our model reaches 0.87±0.06 overall on the benchmark.",         # cell "0.87 ± 0.06"
    "bound": "Our method achieves a Dice of 0.87 ± 0.06.",                          # bound to (Ours, Dice)
    "wrong_cell": "U-Net achieves a Dice of 0.150 on the test set.",                # 0.150 is Baseline's cell
}
PROSE = "We propose a segmentation method. " + " ".join(v for k, v in CLAIM.items() if k not in ("bound", "wrong_cell"))


def _chunk(i, text, btype="paragraph", cells=None):
    c = {"chunk_id": f"SYN:{i}#0", "paper_id": "SYN", "source": "t", "representation": "pdf",
         "section": "results", "page_or_node": "p1", "block_id": f"SYN:{i}", "block_type": btype,
         "char_start": 0, "char_end": len(text), "text": text}
    if cells:
        c.update(table_cells=cells, table_caption=text)
    return c


def _cell(row, col, value):
    return {"row_label": row, "column_header": col, "value": value, "caption": CAP1, "section": "results"}


CELLS = [_cell("Ours", "Dice", "0.87 ± 0.06"), _cell("U-Net", "Dice", "−0.12"), _cell("Baseline", "Dice", "0.150"),
         _cell("A", "Score", "0.15"), _cell("B", "Score", "150"), _cell("C", "Score", "15.2")]
CHUNKS = [_chunk(0, PROSE), _chunk(1, CAP1, "table", CELLS), _chunk(2, CAP2, "table")]
NO_CELLS = [_chunk(0, PROSE), _chunk(1, CAP1, "table"), _chunk(2, CAP2, "table")]


def _item(claim, chunks=CHUNKS):
    return G.gate_paper({"results": claim}, chunks, "FULL_TEXT", [])["evidence"]["results"][0]


def _both(monkeypatch, claim, chunks=CHUNKS):
    monkeypatch.setenv("RGPT_FALLTHROUGH_POLICY", "legacy")
    before = _item(claim, chunks)
    monkeypatch.setenv("RGPT_FALLTHROUGH_POLICY", "table_value_guard")
    return before, _item(claim, chunks)


def test_value_in_an_attached_cell_and_not_bindable_is_abstained(monkeypatch):
    before, after = _both(monkeypatch, CLAIM["cell"])
    assert after["structural_binding"]["status"] == "not_bindable" and before["final"] == G.RETURNED
    assert (after["final"], after["abstain_reason"]) == (G.ABSTAINED, "table_value_unbound")


def test_value_only_in_a_pdf_only_table_blocks_text_is_abstained(monkeypatch):
    before, after = _both(monkeypatch, CLAIM["pdf_only_table_text"])
    assert after["structural_binding"]["status"] == "not_a_table_claim" and before["final"] == G.RETURNED
    assert (after["final"], after["abstain_reason"]) == (G.ABSTAINED, "table_value_unbound")


def test_value_only_in_prose_keeps_the_legacy_fall_through(monkeypatch):
    before, after = _both(monkeypatch, CLAIM["prose"])
    assert after == before and after["final"] == G.RETURNED


def test_token_equality_not_substring(monkeypatch):
    claim = G.claim_value_tokens(CLAIM["token"])
    assert claim == {"15"}
    for cell in ("0.15", "150", "15.2"):
        assert not claim & G.numeric_tokens(cell)
    before, after = _both(monkeypatch, CLAIM["token"])
    assert after == before and after["final"] == G.RETURNED


def test_minus_and_plus_minus_normalisation_match(monkeypatch):
    assert G.claim_value_tokens("a change of -0.12") == {"0.12"} <= G.numeric_tokens("−0.12")
    assert G.claim_value_tokens("Dice 0.87±0.06") == {"0.87", "0.06"} <= G.numeric_tokens("0.87 ± 0.06")
    _, after = _both(monkeypatch, CLAIM["plus_minus"])
    assert (after["final"], after["abstain_reason"]) == (G.ABSTAINED, "table_value_unbound")


def test_bound_and_wrong_cell_claims_are_untouched_by_the_guard(monkeypatch):
    for claim, status in ((CLAIM["bound"], "bound"), (CLAIM["wrong_cell"], "wrong_cell")):
        before, after = _both(monkeypatch, claim)
        assert after == before and after["structural_binding"]["status"] == status


def test_token_equality_also_holds_for_table_block_text():
    text_only = [_chunk(9, "Table 3: Full 15.2 w/o attention 0.15 and 150", "table")]
    assert G.table_value_tokens(text_only) >= {"15.2", "0.15", "150"}
    assert not G.claim_value_tokens(CLAIM["token"]) & G.table_value_tokens(text_only)


def test_legacy_output_is_identical_to_864f2e8(monkeypatch):
    monkeypatch.setenv("RGPT_BINDER_POLICY", "legacy")
    src = subprocess.run(["git", "-C", str(ROOT), "show", "864f2e8:src/evidence/gate.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    old = types.ModuleType("src.evidence._gate_864f2e8")
    old.__package__ = "src.evidence"
    exec(compile(src, "864f2e8:src/evidence/gate.py", "exec"), old.__dict__)
    monkeypatch.setenv("RGPT_FALLTHROUGH_POLICY", "legacy")
    for chunks in (CHUNKS, NO_CELLS):
        for claim in CLAIM.values():
            new = G.gate_paper({"results": claim}, chunks, "FULL_TEXT", [])
            assert json.dumps(new, sort_keys=True) == json.dumps(
                old.gate_paper({"results": claim}, chunks, "FULL_TEXT", []), sort_keys=True)


def test_paper_without_cells_stays_on_the_pdf_only_path(monkeypatch):
    for claim in (CLAIM["cell"], CLAIM["pdf_only_table_text"]):
        before, after = _both(monkeypatch, claim, NO_CELLS)
        assert after == before and after["abstain_reason"] == "unverifiable_binding"


def test_flag_resolution(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "__file__", str(tmp_path / "src" / "evidence" / "gate.py"))   # config: tmp_path/configs
    monkeypatch.delenv("RGPT_FALLTHROUGH_POLICY", raising=False)
    assert G._fallthrough_policy() == "legacy"                     # no config line -> legacy
    (tmp_path / "configs").mkdir()
    cfg = tmp_path / "configs" / "staging_config.yaml"
    cfg.write_text("fallthrough_policy: table_value_guard   # on\n", encoding="utf-8")
    assert G._fallthrough_policy() == "table_value_guard"
    monkeypatch.setenv("RGPT_FALLTHROUGH_POLICY", "legacy")
    assert G._fallthrough_policy() == "legacy"                     # the variable wins
    monkeypatch.setenv("RGPT_FALLTHROUGH_POLICY", "bogus")
    assert G._fallthrough_policy() == "table_value_guard"          # an invalid variable falls to the config
    cfg.write_text("fallthrough_policy: bogus\n", encoding="utf-8")
    assert G._fallthrough_policy() == "legacy"
