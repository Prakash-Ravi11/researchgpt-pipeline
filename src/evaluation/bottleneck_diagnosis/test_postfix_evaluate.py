"""Tests for the post-fix evaluator's gold-assembly and matching rules (evaluation-only code).

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_postfix_evaluate.py -q

Synthetic inputs only: no PDF, corpus, network or LLM.
"""
from postfix_evaluate import assemble, binding_failure, canonical, gate_failure, reconstruction

CLAIM = "Our method achieves 0.91 Dice (Table 2)."


def target(row="Ours", col="Dice", value=0.91):
    return {"value_in_claim": "0.91", "table_label": "Table 2", "table_page": 4, "row_label_levels": [row],
            "row_index_cell": "", "column_header_levels": [col], "cell_text": "0.91 ± 0.01", "numeric_value": value,
            "other_cells_with_same_value": 0}


def label(cid, status, claim, targets):
    return {"candidate_id": cid, "claim_text_exact": claim, "status": status, "claim_subject_kind": "own_method",
            "table_orientation": "rows_are_entities", "targets": targets, "reason": "", "notes": ""}


def test_a_pair_needs_both_blind_readers_an_exact_substring_and_an_agreed_cell():
    cands = [{"candidate_id": c, "paper_id": "PX", "claim_page": 3, "reference": "explicit", "table_refs": ["2"],
              "claim_text": "Table text 1 2 " + CLAIM} for c in ("C1", "C2", "C3", "C4")]
    a = [label("C1", "VERIFIED_POSITIVE", CLAIM, [target()]), label("C2", "VERIFIED_POSITIVE", "paraphrased claim", [target()]),
         label("C3", "VERIFIED_POSITIVE", CLAIM, [target(row="U-Net")]), label("C4", "WRONG_CLAIM", "", [])]
    b = [label("C1", "VERIFIED_POSITIVE", CLAIM, [target(row=" ours ", col="DICE")]), label("C2", "VERIFIED_POSITIVE", CLAIM, [target()]),
         label("C3", "VERIFIED_POSITIVE", CLAIM, [target()]), label("C4", "WRONG_CLAIM", "", [])]
    decided, pairs = assemble(cands, [{"reader": "A_claim_first", "labels": a}, {"reader": "B_cell_first", "labels": b}])
    assert [d["final_status"] for d in decided] == ["VERIFIED_POSITIVE", "AMBIGUOUS", "AMBIGUOUS", "WRONG_CLAIM"]
    assert [p["candidate_id"] for p in pairs] == ["C1"] and pairs[0]["claim_text"] == CLAIM


def test_reconstruction_matches_the_table_label_exactly_and_grades_row_and_column():
    p = {**target(), "row_label_levels": ["Ours"]}
    cell = lambda row, col, value, cap="Table 2: Results.": {"row_label": row, "column_header": col, "value": value,
                                                              "caption": cap, "row": 1, "col": 1, "page": 4}
    assert reconstruction([cell("Ours", "Dice", "0.91", cap="Table 20: Other.")], p)["table_structured"] is False
    r = reconstruction([cell("U-Net", "Dice", "0.91"), cell("Ours", "Dice", "0.91 ± 0.01")], p)
    assert (r["row"], r["col"], r["value"], r["correct"]) == ("exact", "exact", "exact", True)
    r = reconstruction([cell("O urs", "D ice", "0.91")], p)
    assert (r["row"], r["col"], r["correct"]) == ("whitespace_artifact", "whitespace_artifact", False)


def test_failure_is_the_earliest_stage():
    rec_ok = {"table_structured": True, "correct": True, "row": "exact", "col": "exact", "value": "exact"}
    ev = {"bound_correct": False, "binder_status": "not_bindable", "returned": False, "gate_abstain_reasons": ["ownership_unverified"]}
    assert binding_failure([{"table_structured": False, "correct": False}], ev) == "representation:table_not_reconstructed"
    assert binding_failure([{**rec_ok, "correct": False, "row": "index_as_label"}], ev) == "representation:target_cell_row_index_as_label"
    assert binding_failure([rec_ok], ev) == "binder:not_bindable"
    ok = {**ev, "bound_correct": True, "binder_status": "bound"}
    assert binding_failure([rec_ok], ok) is None and gate_failure("own_method", ok) == "gate:ownership_unverified"
    assert gate_failure("baseline_or_cited", {**ok, "returned": True, "gate_abstain_reasons": [None]}) == "gate:returned_a_non_own_claim"


def test_canonical_claim_is_the_stage_b_template():
    assert canonical({**target(row="3D U-Net [45]", col="Dice Score (%)"), "value_in_claim": "89.7"}) == \
        "The 3D U-Net achieves a Dice Score (%) of 89.7."
