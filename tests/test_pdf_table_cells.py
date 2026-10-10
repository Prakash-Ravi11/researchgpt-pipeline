"""PDF structured table cells (src/evidence/represent.py, "PDF structured table cells").

    .venv\\Scripts\\python.exe -B -m pytest -p no:cacheprovider tests/test_pdf_table_cells.py -q

Every PDF here is a real PDF built with PyMuPDF (ruling lines drawn as vector graphics, text as text)
and pushed through the production code: blocks_from_pdf / build_document -> chunk_document /
process_paper_grounded -> structural_bind / gate_paper. No test writes table_cells by hand.
Generic synthetic values only; the P003 acceptance checks live in
src/evaluation/bottleneck_diagnosis/test_postfix_physical_pdfs.py.
"""
import pymupdf
import pytest

import src.evidence.represent as R
from src.evidence.chunker import chunk_document
from src.evidence.gate import gate_paper, structural_bind
from src.evidence.schema import ABSTAINED, FULL_TEXT, OWN_PAPER, PROSE_GROUNDED, RETURNED
from src.processing.pdf_parser import process_paper_grounded

CAPTION = "Table 1: Comparison with baseline methods on the test set."
CLAIM = "Our method achieves a Dice score of 91.4% on the test set."
RESULTS = [["Model", "Dice (%)", "HD95 (mm)"], ["U-Net", "85.1", "7.2"],
           ["Attention U-Net", "88.6", "5.9"], ["Ours", "91.4", "4.3"]]


def _grid(page, x0, y0, widths, rows):
    """Draw `rows` (first = header) as a fully ruled grid; a cell may hold several lines."""
    hs = [8 + 11 * max(len(str(c).split("\n")) for c in r) for r in rows]
    xs = [x0 + sum(widths[:i]) for i in range(len(widths) + 1)]
    ys = [y0 + sum(hs[:i]) for i in range(len(hs) + 1)]
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            page.insert_text((xs[c] + 3, ys[r] + 12), str(text), fontsize=9)


def _results_page(page, rows=RESULTS, caption=CAPTION, widths=(140, 90, 90)):
    page.insert_text((72, 80), "4 Results", fontsize=12)
    page.insert_textbox(pymupdf.Rect(72, 100, 523, 160),
                        CLAIM + " The comparison with two baselines is given below.", fontsize=10)
    page.insert_text((72, 200), caption, fontsize=10)
    _grid(page, 72, 225, list(widths), rows)


def _pdf(*draws) -> bytes:
    doc = pymupdf.open()
    for draw in draws:
        draw(doc.new_page(width=595, height=842))
    return doc.tobytes()


def _blocks(data: bytes) -> list[dict]:
    return R.blocks_from_pdf(data, "SYN", "test")


def _table_block(blocks: list[dict], head: str) -> dict:
    return next(b for b in blocks if b["block_type"] == "table" and b["text"].startswith(head))


def _cells(block: dict) -> set[tuple]:
    return {(c["row_label"], c["column_header"], c["value"], c["row"], c["col"]) for c in block["table_cells"]}


# --- 1, 2, 8: detection, cell extraction, a genuine first-column row label --------------------------
def test_ruled_table_is_detected_and_every_cell_reconstructed():
    b = _table_block(_blocks(_pdf(_results_page)), "Table 1:")
    assert (b["table_parse_status"], b["table_backend"], b["table_shape"]) == ("parsed", "pymupdf.find_tables", [3, 3])
    assert b["table_row_label_rule"] == "first_column"
    assert _cells(b) == {("U-Net", "Dice (%)", "85.1", 1, 1), ("U-Net", "HD95 (mm)", "7.2", 1, 2),
                         ("Attention U-Net", "Dice (%)", "88.6", 2, 1), ("Attention U-Net", "HD95 (mm)", "5.9", 2, 2),
                         ("Ours", "Dice (%)", "91.4", 3, 1), ("Ours", "HD95 (mm)", "4.3", 3, 2)}


def test_first_column_that_is_a_genuine_label_is_kept():
    # consecutive integers, but headed 'Fold' and not zero-padded: the folds ARE the rows' names
    b = _table_block(_blocks(_pdf(lambda p: _results_page(
        p, rows=[["Fold", "Dice (%)"], ["1", "81.0"], ["2", "84.2"], ["3", "83.5"]], widths=(90, 90)))), "Table 1:")
    assert b["table_row_label_rule"] == "first_column"
    assert _cells(b) == {("1", "Dice (%)", "81.0", 1, 1), ("2", "Dice (%)", "84.2", 2, 1), ("3", "Dice (%)", "83.5", 3, 1)}


# --- 4, 5: caption, section and page preservation ----------------------------------------------------
def test_caption_and_section_are_preserved_on_block_and_cells():
    b = _table_block(_blocks(_pdf(_results_page)), "Table 1:")
    assert b["text"] == CAPTION and b["table_caption"] == CAPTION and b["section"] == "results"
    assert {c["caption"] for c in b["table_cells"]} == {CAPTION}
    assert {c["section"] for c in b["table_cells"]} == {"results"}


def test_page_is_preserved():
    blocks = _blocks(_pdf(lambda p: p.insert_text((72, 80), "1 Introduction", fontsize=12), _results_page))
    b = _table_block(blocks, "Table 1:")
    assert b["page_or_node"] == "p2" and {c["page"] for c in b["table_cells"]} == {2}


# --- 3: propagation into chunks (build_document -> chunk_document, and the Stage 2 grounded path) -----
def test_cells_propagate_to_chunks(tmp_path):
    data = _pdf(_results_page)
    b = _table_block(_blocks(data), "Table 1:")
    doc = R.build_document({"paper_id": "SYN", "source": "test", "representation_type": "pdf"}, data)
    assert doc["n_tables_structured"] == 1
    carrying = [c for c in chunk_document(doc) if c.get("table_cells")]
    assert len(carrying) == 1 and carrying[0]["table_cells"] == b["table_cells"]
    assert carrying[0]["table_caption"] == CAPTION
    pdf = tmp_path / "syn.pdf"
    pdf.write_bytes(data)
    recs = process_paper_grounded({"paperId": "SYN", "has_full_text": True, "representation_type": "pdf",
                                   "pdf_path": str(pdf)})
    carrying = [r for r in recs if r.get("table_cells")]
    assert len(carrying) == 1 and carrying[0]["table_cells"] == b["table_cells"]
    assert carrying[0]["table_caption"] == CAPTION and carrying[0]["page_or_node"] == "p1"


# --- 6, 7: index-column detection and entity row-label selection --------------------------------------
@pytest.mark.parametrize("header,values,expected", [
    ("S.no", ["01", "02", "03"], True),      # zero-padded ordinal
    ("#", ["1", "2", "3"], True),            # index header
    ("", ["1", "2", "3"], True),             # unheaded running number
    ("No.", ["0", "1", "2"], True),          # counts from 0
    ("Fold", ["1", "2", "3"], False),        # a genuine label that happens to be 1..n
    ("No.", ["1", "3", "4"], False),         # not consecutive
    ("No.", ["2", "3", "4"], False),         # does not start at 0 or 1
    ("ID", ["1", "2", ""], False),           # a blank cell
    ("Epochs", ["10", "20", "30"], False),
    ("No.", ["1"], False),                   # a single row decides nothing
])
def test_index_column_detection(header, values, expected):
    assert R._is_index_column(header, values) is expected


def test_entity_row_label_is_used_when_the_first_column_is_an_index():
    rows = [["No.", "Model", "F1"], ["1", "Baseline A", "0.71"], ["2", "Baseline B", "0.74"], ["3", "Our model", "0.79"]]
    b = _table_block(_blocks(_pdf(lambda p: _results_page(p, rows=rows, widths=(50, 120, 70)))), "Table 1:")
    assert b["table_row_label_rule"].startswith("entity_column:1 ")
    assert ("Our model", "F1", "0.79", 3, 2) in _cells(b)
    assert ("Our model", "No.", "3", 3, 0) in _cells(b)          # the index stays, as an ordinary cell
    assert not any(c["row_label"] in {"1", "2", "3"} for c in b["table_cells"])


@pytest.mark.parametrize("header,body,expected", [
    (["#", "Score", "Model"], [["1", "0.5", "A net"], ["2", "0.6", "B net"]], 2),   # first entity column after the index
    (["#", "Dice", "HD95"], [["1", "0.5", "7.1"], ["2", "0.6", "6.2"]], 0),        # index, but no entity column
    (["#", "Model", "Dice"], [["1", "Net", "0.5"], ["2", "Net", "0.6"]], 0),       # duplicated entities: ambiguous
    (["Dataset", "Dice"], [["BraTS", "0.9"], ["ISLES", "0.8"]], 0),
])
def test_row_label_column_rule(header, body, expected):
    col, rule = R._pdf_row_label_column(header, body)
    assert col == expected
    assert (rule == "first_column") is (header[0] == "Dataset")


# --- 9: prose, boxed prose, borderless and malformed grids never become cells --------------------------
def test_prose_never_becomes_a_table():
    def prose(page):
        page.insert_text((72, 80), "4 Results", fontsize=12)
        page.insert_text((72, 120), "Table 1 shows that our model improves the Dice score by 3.2 points.", fontsize=10)

    def boxed(page):
        page.insert_text((72, 200), "Table 2: Qualitative observations.", fontsize=10)
        page.draw_rect(pymupdf.Rect(72, 220, 523, 290))
        page.insert_textbox(pymupdf.Rect(76, 224, 519, 286), "The segmentations were inspected by two raters, "
                            "who found sharper boundaries and more small lesions detected.", fontsize=9)

    def borderless(page):
        page.insert_text((72, 200), "Table 3: Results without ruling lines.", fontsize=10)
        for i, row in enumerate(RESULTS):
            for c, text in enumerate(row):
                page.insert_text((72 + 140 * c, 230 + 16 * i), text, fontsize=9)

    blocks = _blocks(_pdf(prose, boxed, borderless))
    assert not any(b.get("table_cells") for b in blocks)
    assert "table_parse_status" not in _table_block(blocks, "Table 1 shows")    # not caption-like: untouched
    for head in ("Table 2:", "Table 3:"):
        b = _table_block(blocks, head)
        assert b["table_parse_status"] == "fallback_pdf"
        assert b["table_fallback"].startswith("no_ruled_table_beside_caption")


def test_stacked_records_grid_is_rejected():
    rows = [["Model", "Accuracy"], ["Alpha\nBeta\nGamma", "81.2\n84.5\n86.1"], ["Delta", "88.0"]]
    b = _table_block(_blocks(_pdf(lambda p: _results_page(p, rows=rows, widths=(140, 90)))), "Table 1:")
    assert not b.get("table_cells") and "stacked_records" in b["table_fallback"]


@pytest.mark.parametrize("header,body,problem", [
    (["Model", "Dice"], [["A", "0.5"]], "too_few_body_rows:1"),
    (["Model"], [["A"], ["B"]], "too_few_columns:1"),
    (["", "0.45*", "± 0."], [["x", "0.45", "0"], ["y", "0.46", "1"]], "header_has_no_words"),
    (["Model", "Notes"], [["A", "x" * 201], ["B", "ok"]], "prose_like_cell"),
    (["No.", "Description"], [["1", "Automated segmentation based on a CNN that"],
                              [None, "explores small kernels and deeper networks"],
                              [None, "to prevent overfitting with fewer weights"]], "wrapped_text_rows"),
    (["Model", "Dice"], [["A net", "0.5"], [None, "0.6"]], None),                     # a spanning label is fine
])
def test_grid_validation(header, body, problem):
    assert R._pdf_grid_problem(header, body) == problem


# --- text invariance: cells are additive; every other stage reads the same text --------------------------
def test_block_text_stream_is_unchanged(monkeypatch):
    data = _pdf(_results_page, lambda p: _results_page(p, rows=[["No.", "Model", "F1"], ["1", "A net", "0.7"],
                                                                 ["2", "B net", "0.8"]], widths=(50, 120, 70)))
    with_cells = _blocks(data)
    monkeypatch.setattr(R, "_attach_pdf_table_cells", lambda doc, captions: None)
    without = _blocks(data)
    assert len(with_cells) == len(without)
    for a, b in zip(with_cells, without):
        assert {k: a[k] for k in b} == b
        assert set(a) == set(b) or a["block_type"] == "table"


# --- physical PDF -> representation -> cells -> grounded chunks -> binder -> gate --------------------------
def test_end_to_end_claim_binds_and_gate_returns_it(tmp_path, monkeypatch):
    pdf = tmp_path / "syn.pdf"
    pdf.write_bytes(_pdf(_results_page))
    paper = {"paperId": "SYN", "has_full_text": True, "representation_type": "pdf", "pdf_path": str(pdf)}
    chunks = process_paper_grounded(paper)

    sb = structural_bind(CLAIM, chunks)
    assert sb["status"] == "bound" and sb["table_type"] == "results"
    assert sb["cell"] == {"row": "Ours", "col": "Dice (%)", "value": "91.4", "caption": CAPTION}
    item = gate_paper({"results": CLAIM}, chunks, FULL_TEXT, [])["evidence"]["results"][0]
    assert item["final"] == RETURNED and item["attribution"] == OWN_PAPER

    cross_row = "Our method achieves a Dice score of 85.1% on the test set."        # U-Net's value, not ours
    assert structural_bind(cross_row, chunks)["status"] == "wrong_cell"
    item = gate_paper({"results": cross_row}, chunks, FULL_TEXT, [])["evidence"]["results"][0]
    assert (item["final"], item["abstain_reason"]) == (ABSTAINED, "binding_wrong_cell")

    monkeypatch.setattr(R, "_attach_pdf_table_cells", lambda doc, captions: None)   # the pre-fix representation
    before = process_paper_grounded(paper)
    assert structural_bind(CLAIM, before)["status"] == "pdf_only"
    item = gate_paper({"results": CLAIM}, before, FULL_TEXT, [])["evidence"]["results"][0]
    assert (item['final'], item['evidence_status'], item['attribution']) == (RETURNED, PROSE_GROUNDED, OWN_PAPER)
    assert item['structural_binding']['structured'] is False
    hit = next(c for c in before if c['block_id'] == item['block_id']
               and c['char_start'] <= item['char_start'] < c['char_end'])
    span = hit['text'][item['char_start'] - hit['char_start']:item['char_end'] - hit['char_start']]
    assert span == item['evidence_span'] == CLAIM
