"""Post-fix acceptance on the physical, hash-pinned PDFs -- production code only, no injected cells.

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_postfix_physical_pdfs.py -q

P003 expectations come from the Stage A verified gold (verified_gold_pairs.json, P003/G002), never from
the code under test. The P005 case pins the caption<->table pairing on a page whose caption blocks
overlap their tables. Skipped when a PDF is absent or its SHA-256 differs from the Phase 2.1 manifest.
"""
import csv
import hashlib
import json
from pathlib import Path

import pytest

import src.evidence.represent as R
from src.evidence.gate import gate_paper, structural_bind
from src.evidence.schema import FULL_TEXT, OWN_PAPER, RETURNED
from src.processing.pdf_parser import process_paper_grounded
from stage_b_gold_binder_oracle import canonical_claim

HERE = Path(__file__).resolve().parent
MAN = {r["paper_id"]: r for r in csv.DictReader(open(HERE / "pdf_identity_manifest_v2.csv", encoding="utf-8"))}
GOLD = next(p for p in json.loads((HERE / "verified_gold_pairs.json").read_text(encoding="utf-8"))["verified_gold_pairs"]
            if p["key"] == "P003/G002")
VT = GOLD["verified_table"]
ROW, COL = VT["target_cells"][0]["row"], VT["target_cells"][0]["col"]


def _pdf(pid: str) -> Path | None:
    p = Path(MAN[pid]["canonical_pdf_path"])
    return p if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == MAN[pid]["sha256"] else None


needs_p003 = pytest.mark.skipif(_pdf("P003") is None, reason="hash-pinned P003 PDF not available")
needs_p005 = pytest.mark.skipif(_pdf("P005") is None, reason="hash-pinned P005 PDF not available")


@pytest.fixture(scope="module")
def p003_blocks():
    return R.blocks_from_pdf(_pdf("P003").read_bytes(), "P003", "test")


@pytest.fixture(scope="module")
def table3(p003_blocks):
    return next(b for b in p003_blocks if b["block_type"] == "table"
                and b["page_or_node"] == f"p{GOLD['pdf_table_page']}" and b["text"].startswith(GOLD["pdf_table_label"]))


def _target(table3):
    return next(c for c in table3["table_cells"] if c["value"] == VT["rows"][ROW][COL] and c["col"] == COL)


# --- 10: P003 Table 3 representation -------------------------------------------------------------------
@needs_p003
def test_p003_table3_is_structured_like_the_verified_grid(table3):
    assert (table3["table_parse_status"], table3["table_backend"]) == ("parsed", "pymupdf.find_tables")
    assert table3["table_shape"] == [len(VT["rows"]), len(VT["header"])]
    ent = VT["entity_column"]
    expected = {(r[ent], VT["header"][c], r[c]) for r in VT["rows"] for c in range(len(VT["header"])) if c != ent}
    assert {(c["row_label"], c["column_header"], c["value"]) for c in table3["table_cells"]} == expected


# --- 11: P003 target cell 92.3 ---------------------------------------------------------------------------
@needs_p003
def test_p003_target_cell(table3):
    c = _target(table3)
    assert (c["value"], c["column_header"], c["page"]) == ("92.3", "Dice Score (%)", GOLD["pdf_table_page"])
    assert c["caption"].startswith("Table 3: Comparison with state-of-the-art methods")


# --- 12: P003 entity row label ------------------------------------------------------------------------------
@needs_p003
def test_p003_entity_row_label(table3):
    assert table3["table_row_label_rule"] == f"entity_column:{VT['entity_column']} (column 0 'S.no' is an index)"
    assert _target(table3)["row_label"] == VT["rows"][ROW][VT["entity_column"]] == "Proposed Method"


@needs_p003
def test_p003_split_captions_are_completed(p003_blocks):
    caps = {b["text"].split(":")[0]: b.get("table_caption") for b in p003_blocks if b.get("table_cells")}
    assert caps["Table 2"] == "Table 2: BraTS dataset compared to state-of-the-art methods."
    assert caps["Table 6"] == "Table 6: Segmentation performance on BraTS and ISLES datasets."


# --- physical PDF -> representation -> cells -> grounded chunks -> binder -> gate ------------------------------
@needs_p003
def test_p003_real_and_canonical_claims_bind_and_are_returned():
    pdf = _pdf("P003")
    chunks = process_paper_grounded({"paperId": pdf.stem, "has_full_text": True, "representation_type": "pdf",
                                     "pdf_path": str(pdf)})
    assert any(c.get("table_cells") for c in chunks)
    for claim in (GOLD["claim_text_verified"], canonical_claim(VT, ROW, COL)):
        sb = structural_bind(claim, chunks)
        assert sb["status"] == "bound", claim
        assert (sb["cell"]["row"], sb["cell"]["col"], sb["cell"]["value"]) == ("Proposed Method", "Dice Score (%)", "92.3")
        item = gate_paper({"results": claim}, chunks, FULL_TEXT, [])["evidence"]["results"][0]
        assert (item["final"], item["attribution"]) == (RETURNED, OWN_PAPER), claim


# --- pairing regression: P005 p12 holds three stacked tables whose caption blocks overlap them --------------
@needs_p005
def test_p005_adjacent_tables_pair_with_their_own_captions():
    blocks = R.blocks_from_pdf(_pdf("P005").read_bytes(), "P005", "test")
    t = {b["text"][:8]: b for b in blocks if b["page_or_node"] == "p12" and b.get("table_cells")}
    rows = {k: {c["row_label"] for c in b["table_cells"]} for k, b in t.items()}
    kernels = {k: {c["value"] for c in b["table_cells"] if c["column_header"] == "Filter size"} for k, b in t.items()}
    assert rows["Table 4."] == {"Layer1", "Layer2"} and kernels["Table 4."] == {"7×7"}
    assert "3×3" in kernels["Table 5."] and "7×7" not in kernels["Table 5."]
