"""Phase 10 Binder v2 (binder_policy = v2 / v2_llm) and its default-legacy router.

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider tests/test_binder_v2.py -q

Synthetic chunks only: no PDF, no table model, and no Ollama call (the LLM judge is a stub). Every case of the
phase 10 brief's STEP 2 list has a test. Definitions: src/evaluation/binder_10/PREREG_10.md.
"""
import json
import subprocess
import types
from pathlib import Path

import pytest

import src.evidence.gate as G
import src.evidence.binder_v2 as B

ROOT = Path(__file__).resolve().parents[1]
START = "afe1488"


def _chunk(i, text, btype="paragraph", cells=None, page=1):
    c = {"chunk_id": f"SYN:{i}#0", "paper_id": "SYN", "source": "t", "representation": "pdf", "section": "results",
         "page_or_node": f"p{page}", "block_id": f"SYN:{i}", "block_type": btype, "char_start": 0,
         "char_end": len(text), "text": text}
    if cells:
        c.update(table_cells=cells, table_caption=text)
    return c


def _table(i, caption, rows, cols, values, page=1):
    """A table chunk; values[r][k] is the cell at (rows[r], cols[k]), None an empty cell."""
    cells = [{"row_label": rows[r], "column_header": cols[k], "value": v, "caption": caption, "section": "results",
              "page": page, "row": r + 1, "col": k + 1}
             for r in range(len(rows)) for k, v in enumerate(values[r]) if v is not None]
    return _chunk(i, caption, "table", cells, page)


T_ROWS = _table(1, "Table 1: Segmentation results on the test set.", ["UNet", "Ours"], ["Dice", "HD95 (mm)", "Acc (%)"],
                [["0.81±0.06", "4.2", "85"], ["0.87±0.06", "3.1", "87"]])
T_COLS = _table(2, "Table 2: Average Dice scores per structure.", ["CSF", "Average"], ["Ours", "nnU-Net"],
                [["0.923 ± 0.006", "0.897 ± 0.011"], ["0.926 ± 0.012", "0.920 ± 0.014"]], page=2)
T_HIER = _table(3, "Table 3: Results per dataset.", ["Ours", "VNet"], ["BraTS / Dice", "ISLES / Dice"],
                [["0.91", "0.88"], ["0.89", "0.86"]], page=3)
T_TEXT = _table(4, "Table 4: Prior work.", ["Smith et al. (2020)"], ["Results"],
                [["DSC: 83.79%, VS: 84.84%, HD95: 35.66 mm"]], page=4)
T_CI = _table(5, "Table 5: Lesion segmentation.", ["FreeHemoSeg", "UNet"], ["DSC"],
              [["0.559 (0.546, 0.571)"], ["0.512 (0.497, 0.526)"]], page=5)
T_DATA = _table(6, "Table 6: Summary of the data used.", ["Training", "Testing"],
                ["Number of subjects", "Age (years)", "Gestational age (weeks)"],
                [["15", "28.7±3.5", "21-38"], ["18", "30.1±2.9", "22-35"]], page=6)
T_DECL = _table(7, "Table 7: Comparison with baselines.", ["OurNet", "VNet"], ["Dice"], [["0.93"], ["0.84"]], page=7)
T_PLUR = _table(8, "Table 8: Lesion results.", ["Ours"], ["DSC", "R²"], [["0.70", "0.91"]], page=8)
T_DUP = _table(9, "Table 9: Detection results.", ["UNet", "VNet"], ["mAP"], [["0.85"], ["0.85"]], page=9)
T_BRATS = _table(10, "Table 10: Results on BraTS.", ["Ours"], ["Dice"], [["0.95"]], page=10)
T_ISLES = _table(11, "Table 11: Results on ISLES.", ["Ours"], ["Dice"], [["0.95"]], page=11)
PROSE = _chunk(0, "We propose OurNet for fetal segmentation. Unexposed controls were scanned twice.")
PAPER = [PROSE, T_ROWS, T_COLS, T_HIER, T_TEXT, T_CI, T_DATA, T_DECL, T_PLUR, T_DUP, T_BRATS, T_ISLES]


@pytest.fixture(autouse=True)
def _v2(monkeypatch):
    monkeypatch.setenv("RGPT_BINDER_POLICY", "v2")
    monkeypatch.setenv("RGPT_FALLTHROUGH_POLICY", "table_value_guard")
    monkeypatch.delenv("RGPT_BINDER_V2_DISABLE", raising=False)
    B._CACHE.clear()


def bind(claim, chunks=PAPER):
    return G.structural_bind(claim, chunks)


def where(sb):
    return (sb["cell"]["row"], sb["cell"]["col"], sb["cell"]["value"]) if sb["status"] == "bound" else sb["status"]


def test_own_method_resolution_with_evidence_span():
    sb = bind("Our method achieves a Dice of 0.87 ± 0.06 on the test set.")
    assert where(sb) == ("Ours", "Dice", "0.87±0.06") and sb["bindings"][0]["subject"] == "own_alias"
    idx = B._index(PAPER, frozenset())
    assert "We propose OurNet" in idx["declared"]["ournet"]               # the alias carries a verbatim span
    assert where(bind("The proposed method reaches a Dice of 0.93.")) == ("OurNet", "Dice", "0.93")


def test_two_declared_own_methods_are_not_merged():
    two = [_chunk(0, "We propose AlphaNet. We also introduce BetaNet for comparison."),
           _table(1, "Table 1: Results.", ["AlphaNet", "BetaNet"], ["Dice"], [["0.90"], ["0.85"]])]
    sb = bind("Our model achieves a Dice of 0.90.", two)
    assert sb["status"] == "ambiguous_subject" and sb["abstain_code"] == "ambiguous_subject"


def test_methods_as_rows_and_as_columns(monkeypatch):
    assert where(bind("UNet obtains a Dice of 0.81.")) == ("UNet", "Dice", "0.81±0.06")
    assert where(bind("Our method achieves an average Dice score of 0.926 ± 0.012.")) == ("Average", "Ours", "0.926 ± 0.012")
    only_column = "nnU-Net obtains a Dice of 0.897."                      # the row (CSF) is not named
    assert where(bind(only_column)) == ("CSF", "nnU-Net", "0.897 ± 0.011")
    monkeypatch.setenv("RGPT_BINDER_V2_DISABLE", "column_subject")
    B._CACHE.clear()
    assert bind(only_column)["status"] != "bound"


def test_hierarchical_headers_dataset_over_metric():
    sb = bind("Ours reaches a Dice of 0.91 on BraTS and 0.88 on ISLES.")
    assert sb["status"] == "bound" and sb["binding_type"] == "MULTI_CELL"
    assert [(b["cell"]["col"], b["number"]) for b in sb["bindings"]] == [("BraTS / Dice", "0.91"), ("ISLES / Dice", "0.88")]


def test_metric_only_in_the_caption():
    assert where(bind("nnU-Net obtains an average Dice score of 0.920 ± 0.014.")) == ("Average", "nnU-Net", "0.920 ± 0.014")


def test_metric_in_cell_text_and_the_wrong_metric_never_binds():
    assert where(bind("Smith et al. (2020) reported a DSC of 83.79%.")) == (
        "Smith et al. (2020)", "Results", "DSC: 83.79%, VS: 84.84%, HD95: 35.66 mm")
    assert bind("Smith et al. (2020) reported a VS of 83.79%.")["status"] != "bound"


def test_plural_metric_and_r_squared(monkeypatch):
    assert where(bind("Ours achieved DSCs of 0.70.")) == ("Ours", "DSC", "0.70")
    assert where(bind("Ours reaches an R2 of 0.91.")) == ("Ours", "R²", "0.91")
    monkeypatch.setenv("RGPT_BINDER_V2_DISABLE", "synonyms")
    B._CACHE.clear()
    assert bind("Ours achieved DSCs of 0.70.")["status"] != "bound"
    assert bind("Ours reaches an R2 of 0.91.")["status"] != "bound"


def test_percent_and_fraction_are_not_merged_and_scales_differ():
    assert bind("Ours has an accuracy of 0.87.")["status"] != "bound"           # 0.87 is Dice; Acc holds 87
    assert where(bind("Ours has an Acc of 87%.")) == ("Ours", "Acc (%)", "87")
    for claim in ("Ours has a Dice of 0.087.", "Ours has a Dice of 87."):
        assert bind(claim)["status"] != "bound"


def test_pm_ci_interval_and_range_parsing():
    assert bind("Ours reaches a Dice of 0.87 ± 0.05.")["status"] != "bound"     # ± disagrees
    ci = "FreeHemoSeg achieved a DSC of 0.559 (95% CI, 0.546–0.571)."
    m = B.mentions(B._prep(ci))
    assert [(x["tok"], x["interval"]) for x in m] == [("0.559", ("0.546", "0.571"))]
    assert where(bind(ci)) == ("FreeHemoSeg", "DSC", "0.559 (0.546, 0.571)")
    rng = "The training set covers gestational ages between 21 and 38 weeks."
    assert [(x["tok"], x["range"], x["unit"]) for x in B.mentions(rng)] == [("21", ("21", "38"), "weeks")]
    assert where(bind(rng)) == ("Training", "Gestational age (weeks)", "21-38")


def test_duplicate_value_across_subjects_and_contexts_abstain():
    sb = bind("UNet and VNet both reach a mAP of 0.85.")
    assert sb["status"] == "ambiguous_subject"
    assert bind("Our method achieves a Dice of 0.95.")["status"] == "duplicate_quantity_context"
    assert where(bind("Our method achieves a Dice of 0.95 on BraTS.")) == ("Ours", "Dice", "0.95") and \
        bind("Our method achieves a Dice of 0.95 on BraTS.")["cell"]["caption"].endswith("BraTS.")


def test_qualifier_mismatch_abstains():
    assert bind("Ours reaches a Dice of 0.91 on ISLES.")["status"] != "bound"


def test_comparison_both_sides_and_partial_comparison():
    sb = bind("Our method achieves an average Dice score of 0.926 ± 0.012 versus 0.920 ± 0.014 for nnU-Net.")
    assert sb["status"] == "bound" and sb["binding_type"] == "COMPARISON"
    assert [(b["cell"]["row"], b["cell"]["col"]) for b in sb["bindings"]] == [("Average", "Ours"), ("Average", "nnU-Net")]
    # D9: 0.897 is nnU-Net's CSF cell, so it is required, but "average" contradicts it: one of two bindings fails
    part = bind("Our method achieves an average Dice score of 0.926 ± 0.012 versus 0.897 ± 0.011 for nnU-Net.")
    assert part["status"] == "partial_binding" and part["abstain_code"] == "partial_binding"
    single = bind("Our method achieves an average Dice score of 0.926 ± 0.012 versus 0.915 for nnU-Net.")
    assert where(single) == ("Average", "Ours", "0.926 ± 0.012")      # 0.915 is in no cell: not a required binding
    ft = bind("Our module improves the Dice from 0.81 by UNet to 0.87 by Ours.")
    assert ft["binding_type"] == "COMPARISON" and [b["cell"]["row"] for b in ft["bindings"]] == ["UNet", "Ours"]


def test_multi_cell_count_and_age_attribute_claims():
    assert where(bind("Our training set contains 15 subjects.")) == ("Training", "Number of subjects", "15")
    assert where(bind("The training cohort had a mean age of 28.7 ± 3.5 years.")) == ("Training", "Age (years)", "28.7±3.5")


def test_table_prose_is_never_a_cell():
    chunks = [_chunk(1, "Table 3 shows that Ours reaches a Dice of 0.95 on the private set.", "table"), T_ROWS]
    assert bind("Ours reaches a Dice of 0.95.", chunks)["status"] == "not_a_table_claim"
    fake = B._parse_cell({"row_label": "Ours", "column_header": "Dice", "value": "0.95", "caption": "Table 3"})
    fake.update(raw={"row_label": "Ours", "column_header": "Dice", "value": "0.95", "caption": "Table 3"})
    m = B.mentions("Ours reaches a Dice of 0.95.")[0]
    assert B.verify("Ours reaches a Dice of 0.95.", m, fake, chunks, frozenset()) == "not_an_attached_cell"


def test_verification_failure_path(monkeypatch):
    monkeypatch.setattr(B, "verify", lambda *a, **k: "subject")
    sb = bind("UNet obtains a Dice of 0.81.")
    assert sb["status"] == "deterministic_verification_failed"
    item = G.gate_paper({"results": "UNet obtains a Dice of 0.81."}, PAPER, "FULL_TEXT", [])["evidence"]["results"][0]
    assert (item["final"], item["abstain_reason"]) == (G.ABSTAINED, "deterministic_verification_failed")


def test_llm_choice_or_span_not_in_its_input_is_rejected(monkeypatch):
    claim = "UNet and VNet both reach a mAP of 0.85."
    monkeypatch.setattr(B, "_llm_call", lambda request: {"choice": "k9", "span": "Table 9: Detection results."})
    with pytest.raises(B.LLMViolation):
        B.structural_bind_v2(claim, PAPER, llm=True)
    monkeypatch.setattr(B, "_llm_call", lambda request: {"choice": "k1", "span": "a sentence the paper never wrote"})
    with pytest.raises(B.LLMViolation):
        B.structural_bind_v2(claim, PAPER, llm=True)
    monkeypatch.setattr(B, "_llm_call", lambda request: {"choice": "none", "span": ""})
    assert B.structural_bind_v2(claim, PAPER, llm=True)["status"] == "ambiguous_subject"
    monkeypatch.setattr(B, "_llm_call", lambda request: {"choice": "k1", "span": "Table 9: Detection results."})
    sb = B.structural_bind_v2(claim, PAPER, llm=True)
    assert sb["status"] == "bound" and sb["bindings"][0]["llm_span"] == "Table 9: Detection results."


def test_the_two_gate_fixes():
    cap, rows = "Table 1: Comparison of explanation methods.", {"Ablation-CAM", "Grad-CAM", "Ours"}
    assert G.classify_table(cap, {"Score"}, rows) == "ablation"
    assert B.classify_table_v2(cap, {"Score"}, rows) == "results"
    text = "Smith et al. reported a Dice of 0.81. UNet obtains a Dice of 0.81."
    v2 = [i["value"] for i in G.gate_paper({"results": text}, PAPER, "FULL_TEXT", [])["evidence"]["results"]]
    assert v2[0] == "Smith et al. reported a Dice of 0.81."


def test_legacy_binding_is_identical_except_rejected_nonmetric_counts(monkeypatch):
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{START}:src/evidence/gate.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    old = types.ModuleType("src.evidence._gate_start")
    old.__package__ = "src.evidence"
    exec(compile(src, f"{START}:src/evidence/gate.py", "exec"), old.__dict__)
    monkeypatch.setenv("RGPT_BINDER_POLICY", "legacy")
    for claim in ("Our method achieves a Dice of 0.87 ± 0.06.", "Smith et al. reported a Dice of 0.81. UNet: 0.81.",
                  "Our method achieves an average Dice score of 0.926 ± 0.012 versus 0.920 ± 0.014 for nnU-Net.",
                  "Ours reaches a Dice of 0.91 on ISLES.", "The training set has 15 subjects aged 21-38 weeks."):
        new = G.gate_paper({"results": claim, "metrics": [claim]}, PAPER, "FULL_TEXT", [])
        previous = old.gate_paper({"results": claim, "metrics": [claim]}, PAPER, "FULL_TEXT", [])
        if claim == "The training set has 15 subjects aged 21-38 weeks.":
            # Subject counts are not metric labels. Tightened sanity rejects
            # this before binding, while preserving the existing result gate.
            metric = previous['evidence']['metrics'][0]
            assert metric['abstain_reason'] == 'table_value_unbound'
            metric.update(abstain_reason='value_failed_sanity_check', structural_binding=None)
        assert json.dumps(new, sort_keys=True) == json.dumps(previous, sort_keys=True)


def test_flag_resolution(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "__file__", str(tmp_path / "src" / "evidence" / "gate.py"))
    monkeypatch.delenv("RGPT_BINDER_POLICY", raising=False)
    assert G._binder_policy() == "legacy"
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "staging_config.yaml").write_text("binder_policy: v2   # on\n", encoding="utf-8")
    assert G._binder_policy() == "v2"
    monkeypatch.setenv("RGPT_BINDER_POLICY", "legacy")
    assert G._binder_policy() == "legacy"
    monkeypatch.setenv("RGPT_BINDER_POLICY", "bogus")
    assert G._binder_policy() == "v2"
