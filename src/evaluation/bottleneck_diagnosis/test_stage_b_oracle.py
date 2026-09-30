"""Tests for the Stage B GOLD->BINDER oracle adapters (evaluation-only code; production code untouched).

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_stage_b_oracle.py -q

Synthetic inputs only (no PDF, corpus, network or LLM). The table mirrors the shape of the verified
P003 Table 3 so the tests pin down exactly the behaviours the oracle report interprets.
"""
import json

import pytest

import src.evidence.gate as G
from stage_b_gold_binder_oracle import (canonical_claim, canonical_rowlabel_claim, column_orders, entity_text,
                                        gold_chunks, load_verified, target_in_representation)

VT = {"label": "Table 3", "page": 6, "caption": "Table 3: Comparison with state-of-the-art methods on the ISLES dataset.",
      "header": ["S.no", "Method", "Dice Score (%)"],
      "rows": [["01", "3D U-Net [45]", "89.7"], ["02", "Attention U-Net [46]", "90.5"],
               ["03", "DualSeg [47]", "91.2"], ["04", "Proposed Method", "92.3"]],
      "entity_column": 1, "target_cells": [{"cell_id": "T004_R6_C3", "row": 3, "col": 2}]}
ORD = column_orders(VT)


def cell(chunks, value):
    return next(c for c in G.paper_table_cells(chunks) if c["value"] == value)


def test_production_converter_takes_the_first_column_as_row_label():
    c = cell(gold_chunks(VT, ORD["R1_gold_production_convention"], "X"), "92.3")
    assert (c["row_label"], c["column_header"]) == ("04", "Dice Score (%)")


def test_entity_first_order_makes_the_entity_the_row_label():
    c = cell(gold_chunks(VT, ORD["R2_gold_entity_first"], "X"), "92.3")
    assert (c["row_label"], c["column_header"]) == ("Proposed Method", "Dice Score (%)")
    assert target_in_representation(VT, ORD["R2_gold_entity_first"], 3, 2) == {
        "row_label": "Proposed Method", "column_header": "Dice Score (%)", "value": "92.3"}


def test_canonical_claims_use_only_table_content():
    assert canonical_claim(VT, 3, 2) == "The Proposed Method achieves a Dice Score (%) of 92.3."
    assert canonical_rowlabel_claim(VT, 3, 2) == "Row 04 achieves a Dice Score (%) of 92.3."
    assert entity_text("3D U-Net [45]") == "3D U-Net"


def test_binder_on_gold_cells_under_both_conventions():
    prod, ent = (gold_chunks(VT, ORD[k], "X") for k in ("R1_gold_production_convention", "R2_gold_entity_first"))
    b = G.structural_bind(canonical_claim(VT, 3, 2), ent)
    assert (b["status"], b["cell"]["row"], b["cell"]["col"], b["cell"]["value"]) == ("bound", "Proposed Method", "Dice Score (%)", "92.3")
    assert G.structural_bind(canonical_claim(VT, 3, 2), prod)["status"] == "wrong_cell"      # row label is '04'
    assert G.structural_bind(canonical_rowlabel_claim(VT, 3, 2), prod)["status"] == "bound"   # naming the row as R1 labels it


def test_no_table_cells_is_pdf_only():
    chunks = [{"text": "our method achieves a Dice score of 92.3%", "section": "results", "block_type": "paragraph"}]
    assert G.structural_bind("Our method achieves a Dice score of 92.3%.", chunks)["status"] == "pdf_only"


def test_oracle_refuses_anything_but_verified_positive(tmp_path):
    p = tmp_path / "gold.json"
    p.write_text(json.dumps({"verified_gold_pairs": [{"key": "PX/G1", "verification_status": "WRONG_CELL"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_verified(p)
