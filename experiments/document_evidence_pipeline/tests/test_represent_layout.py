"""Unit tests for src/evidence/represent_layout.py (exp/parser-backend, §8).

Synthetic fixtures only — no corpus, runs in seconds.
    python -m pytest experiments/document_evidence_pipeline/tests/test_represent_layout.py -q
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.evidence.represent import blocks_from_pdf                       # noqa: E402
from src.evidence.chunker import chunk_document                          # noqa: E402
from src.evidence.gate import structural_bind                            # noqa: E402
from src.evidence.represent_layout import (                              # noqa: E402
    TABLE_EXTRA_KEYS, _attach, _gate_grid, _grid_to_xhtml, _layout_table_cells,
    _parse_pipe_tables, _strip, _tier1_grids, _tier2_page_markdown,
    blocks_from_pdf_layout, pymupdf4llm_invoked)

PID, SRC = "testpaper", "unit"

# Every tier-1 (find_tables) test must run BEFORE pymupdf4llm has been invoked in
# this process — see test_12. The pymupdf4llm tests are therefore last in the
# file, and the tier-1 tests assert the process is still clean rather than
# trusting file order.
CLEAN = ("pymupdf4llm has already run in this process; find_tables results are "
         "contaminated. Keep pymupdf4llm tests last (see test_12).")


# ---------------------------------------------------------------- fixtures --

def _page(width=612, height=460):
    doc = pymupdf.open()
    return doc, doc.new_page(width=width, height=height)


def _caption(page, text="Table 1: Results on the benchmark.", y=60):
    page.insert_text((60, y), text, fontsize=11)


def _grid_text(page, rows, x0=60, y0=140, dx=150, dy=34):
    """Lay out `rows` as a text grid. Returns the cell corner geometry."""
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            page.insert_text((x0 + c * dx + 5, y0 + r * dy + 20), str(val), fontsize=11)
    return x0, y0, dx, dy, len(rows), max(len(r) for r in rows)


def _rule(page, x0, y0, dx, dy, nrow, ncol):
    """Draw full ruling lines so find_tables' lines_strict strategy sees a grid."""
    for r in range(nrow + 1):
        page.draw_line(pymupdf.Point(x0, y0 + r * dy),
                       pymupdf.Point(x0 + ncol * dx, y0 + r * dy), width=0.8)
    for c in range(ncol + 1):
        page.draw_line(pymupdf.Point(x0 + c * dx, y0),
                       pymupdf.Point(x0 + c * dx, y0 + nrow * dy), width=0.8)


RULED_ROWS = [["Method", "Accuracy", "F1"],
              ["BERT", "0.811", "0.792"],
              ["Ours", "0.905", "0.887"]]


def _ruled_pdf() -> bytes:
    doc, page = _page()
    _caption(page)
    geo = _grid_text(page, RULED_ROWS)
    _rule(page, *geo)
    return doc.tobytes()


def _borderless_pdf() -> bytes:
    doc, page = _page()
    _caption(page)
    _grid_text(page, RULED_ROWS)          # same content, no ruling lines
    return doc.tobytes()


def _image_only_pdf() -> bytes:
    """A caption line plus a raster block — no text layer for the grid."""
    doc, page = _page()
    _caption(page, "Table 1: scanned, image only.")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 220, 90))
    pix.set_rect(pix.irect, (210, 210, 210))
    page.insert_image(pymupdf.Rect(60, 140, 280, 230), pixmap=pix)
    return doc.tobytes()


def _cells_of(blocks):
    return [c for b in blocks if b["block_type"] == "table" for c in (b.get("table_cells") or [])]


def _triples(cells):
    return {(c["row_label"], c["column_header"], c["value"]) for c in cells}


def _table_block(blocks):
    tb = [b for b in blocks if b["block_type"] == "table"]
    assert tb, "fixture produced no table-typed block"
    return tb[0]


def _mk_table_block(grid, caption="Table 1: Results.", backend="pymupdf_tables"):
    """Drive _attach directly with a known grid — the real gate and the real
    cell builder, without rendering a PDF."""
    b = {"block_id": f"{PID}:0", "paper_id": PID, "source": SRC, "representation": "pdf",
         "section": "results", "subsection": None, "page_or_node": "p1",
         "block_type": "table", "char_start": 0, "char_end": len(caption), "text": caption}
    _attach(b, grid, "find_tables", PID, SRC, backend)
    return b


# ------------------------------------------------------------------- tests --

def test_1_clean_ruled_table_exact_cells():
    assert not pymupdf4llm_invoked(), CLEAN
    blocks = blocks_from_pdf_layout(_ruled_pdf(), PID, SRC, "pymupdf_tables")
    assert _triples(_cells_of(blocks)) == {
        ("BERT", "Accuracy", "0.811"), ("BERT", "F1", "0.792"),
        ("Ours", "Accuracy", "0.905"), ("Ours", "F1", "0.887"),
    }


def test_3_colspan_in_header():
    """The copied _jats_table_cells must expand @colspan exactly as the original."""
    xhtml = ("<table-wrap><caption>Table 2: spans.</caption><table>"
             "<thead><tr><th>Method</th><th colspan='2'>Scores</th><th>F1</th></tr></thead>"
             "<tbody><tr><td>Ours</td><td>0.90</td><td>0.80</td><td>0.87</td></tr>"
             "<tr><td>BERT</td><td>0.70</td><td>0.60</td><td>0.61</td></tr>"
             "</tbody></table></table-wrap>")
    st = _layout_table_cells(ET.fromstring(xhtml), PID, SRC, "results", "c0", _strip,
                             representation="pdf_layout")
    assert st["parse_status"] == "parsed"
    # col 1 is "Scores"; col 2 is the colspan placeholder (no header) and is skipped;
    # col 3 is "F1".
    assert _triples(st["cells"]) == {("Ours", "Scores", "0.90"), ("Ours", "F1", "0.87"),
                                     ("BERT", "Scores", "0.70"), ("BERT", "F1", "0.61")}
    assert all(c["representation"] != "jats_xml" for c in [st])
    assert st["representation"] == "pdf_layout"


def test_3b_copy_is_faithful_to_the_original_jats_parser():
    """The ONLY duplicated logic in the module is _jats_table_cells. Run the same
    grid through the original and the copy and require identical cells — this is
    what licenses reusing represent.py's semantics, including its quirks (e.g.
    the column cursor over-advancing past a colspan placeholder)."""
    from src.evidence.represent import _jats_table_cells as original
    xhtml = ("<table-wrap><caption>Table 4: spans in a data row.</caption><table>"
             "<thead><tr><th>Method</th><th>A</th><th>B</th><th>F1</th></tr></thead>"
             "<tbody>"
             "<tr><td>Ours</td><td colspan='2'>0.90</td><td>0.87</td></tr>"
             "<tr><td>BERT</td><td>0.70</td><td>0.60</td><td>0.61</td></tr>"
             "</tbody></table></table-wrap>")
    ours = _layout_table_cells(ET.fromstring(xhtml), PID, SRC, "results", "c0", _strip,
                               representation="pdf_layout")
    theirs = original(ET.fromstring(xhtml), PID, SRC, "results", "c0", _strip)
    assert ours["cells"] == theirs["cells"]
    assert ours["parse_status"] == theirs["parse_status"]
    assert ours["representation"] == "pdf_layout" and theirs["representation"] == "jats_xml"


def test_3c_single_column_grid_is_rejected():
    b = _mk_table_block([["Method"], ["Ours"], ["BERT"]])
    assert b["table_cells"] == []
    assert b["table_fallback"].startswith("quality_gate:too_few_columns")


def test_4_multiline_row_label_drops_that_row_only():
    grid = [["Method", "Accuracy"],
            ["Ours", "0.905"],
            ["A very long\nwrapped label", "0.811"],
            ["BERT", "0.792"]]
    b = _mk_table_block(grid)
    assert b["table_parse_status"] == "parsed"
    assert b["n_rows_dropped"] == 1
    assert b["drop_reasons"] == {"newline_in_row_label": 1}
    assert _triples(b["table_cells"]) == {("Ours", "Accuracy", "0.905"),
                                          ("BERT", "Accuracy", "0.792")}
    assert "0.811" not in {c["value"] for c in b["table_cells"]}


def test_5_empty_header_cell_rejects_whole_table():
    grid = [["Method", "", "F1"],
            ["Ours", "0.905", "0.887"],
            ["BERT", "0.811", "0.792"]]
    b = _mk_table_block(grid)
    assert b["table_cells"] == []
    assert b["table_parse_status"] == "fallback_pdf"
    assert b["table_fallback"].startswith("quality_gate:empty_header_cell")


def test_5b_empty_FIRST_header_cell_is_allowed():
    """D5: the row-label corner is conventionally blank and binds nothing."""
    grid = [["", "Accuracy", "F1"],
            ["Ours", "0.905", "0.887"],
            ["BERT", "0.811", "0.792"]]
    b = _mk_table_block(grid)
    assert b["table_parse_status"] == "parsed"
    assert _triples(b["table_cells"]) == {("Ours", "Accuracy", "0.905"), ("Ours", "F1", "0.887"),
                                          ("BERT", "Accuracy", "0.811"), ("BERT", "F1", "0.792")}


def test_6_single_row_table_is_fallback():
    b = _mk_table_block([["Method", "Accuracy"], ["Ours", "0.905"]])
    assert b["table_cells"] == []
    assert b["table_parse_status"] == "fallback_pdf"
    assert b["table_fallback"].startswith("quality_gate:too_few_data_rows")


def test_7_image_only_table_falls_back_without_exception():
    assert not pymupdf4llm_invoked(), CLEAN
    blocks = blocks_from_pdf_layout(_image_only_pdf(), PID, SRC, "pymupdf_tables")
    tb = _table_block(blocks)
    assert tb["table_cells"] == []
    assert tb["table_parse_status"] == "fallback_pdf"


def test_8_block_key_sets_match_blocks_from_pdf():
    assert not pymupdf4llm_invoked(), CLEAN
    data = _ruled_pdf()
    base = blocks_from_pdf(data, PID, SRC)
    lay = blocks_from_pdf_layout(data, PID, SRC, "pymupdf_tables")
    assert len(base) == len(lay)
    base_keys = set(base[0])
    for b0, b1 in zip(base, lay):
        assert b0["block_id"] == b1["block_id"]
        if b1["block_type"] == "table":
            # §8 reading: base key set + exactly the documented extras, nothing else
            assert set(b1) == base_keys | TABLE_EXTRA_KEYS
        else:
            assert set(b1) == set(b0)          # prose blocks: exact equality
            assert b0["text"] == b1["text"]    # and byte-identical text


def test_9_chunker_carries_cells_onto_every_chunk_of_a_table_block():
    assert not pymupdf4llm_invoked(), CLEAN
    blocks = blocks_from_pdf_layout(_ruled_pdf(), PID, SRC, "pymupdf_tables")
    tb = _table_block(blocks)
    assert tb["table_cells"], "fixture must produce cells for this test to mean anything"
    chunks = chunk_document({"paper_id": PID, "representation": "pdf", "blocks": blocks})
    tchunks = [c for c in chunks if c["block_id"] == tb["block_id"]]
    assert tchunks
    assert all(c.get("table_cells") == tb["table_cells"] for c in tchunks)


def test_10_zero_cells_gives_structural_bind_pdf_only():
    assert not pymupdf4llm_invoked(), CLEAN
    blocks = blocks_from_pdf_layout(_image_only_pdf(), PID, SRC, "pymupdf_tables")
    chunks = chunk_document({"paper_id": PID, "representation": "pdf", "blocks": blocks})
    assert not any(c.get("table_cells") for c in chunks)
    assert structural_bind("accuracy of 0.905", chunks) == {"structured": False,
                                                            "status": "pdf_only"}


def test_11_row_drops_that_flip_table_type_are_recorded_not_silent():
    """D6(b): 3 data rows before the gate, 1 after. classify_table's default
    branch needs >= 2 DISTINCT row labels, so the survivor count flips
    results -> other, which abstains a bound claim. The transition must be
    visible in the artifact."""
    grid = [["Method", "Accuracy"],
            ["Ours", "0.905"],
            ["wrapped\nlabel one", "0.811"],
            ["wrapped\nlabel two", "0.792"]]
    b = _mk_table_block(grid, caption="Table 3: scores.")
    assert b["rows_before_gate"] == 3
    assert b["rows_after_gate"] == 1
    assert b["n_rows_dropped"] == 2
    assert b["table_type_before"] == "results"
    assert b["table_type_after"] == "other"
    assert b["table_type_before"] != b["table_type_after"]


# ----------------------------------------------------- gate / parser units --

def test_pipe_table_parsing_drops_separator_row():
    md = "| Method | Acc |\n|---|---:|\n| Ours | 0.9 |\n| BERT | 0.8 |\n"
    assert _parse_pipe_tables(md) == [[["Method", "Acc"], ["Ours", "0.9"], ["BERT", "0.8"]]]


def test_gate_rejects_overlong_header_and_row_label():
    long_h = "x" * 41
    assert _gate_grid([["M", long_h], ["a", "1"], ["b", "2"]])["reject"].startswith("header_too_long")
    g = _gate_grid([["M", "Acc"], ["y" * 61, "1"], ["b", "2"], ["c", "3"]])
    assert g["reject"] is None and g["drop_reasons"] == {"row_label_too_long": 1}


def test_xhtml_escapes_backend_text():
    """Backend output is untrusted and goes through an XML parser."""
    xhtml = _grid_to_xhtml(["M", "A<b>"], [["<script>", "1 & 2"]], 'Cap "x" & <y>')
    st = _layout_table_cells(ET.fromstring(xhtml), PID, SRC, "results", "c0", _strip,
                             representation="pdf_layout")
    assert st["caption"] == 'Cap "x" & <y>'
    assert _triples(st["cells"]) == {("<script>", "A<b>", "1 & 2")}


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        blocks_from_pdf_layout(b"", PID, SRC, "unstructured")


# ------------------------------------------------------------------------- #
# pymupdf4llm tests LAST: invoking it mutates global PyMuPDF state for the rest
# of the process (test_12). Everything above asserts a clean process.
# ------------------------------------------------------------------------- #

def test_2_borderless_table_exact_cells():
    """Tier 2. find_tables (tier 1) finds NOTHING on this borderless fixture in
    a clean process, so these cells can only have come from pymupdf4llm."""
    data = _borderless_pdf()
    doc = pymupdf.open(stream=data, filetype="pdf")
    assert _tier1_grids(doc[0]) == [], "tier 1 must not see this table, or the test proves nothing"
    doc.close()
    blocks = blocks_from_pdf_layout(data, PID, SRC, "pymupdf4llm")
    assert _table_block(blocks)["table_fallback"] == "tier:pymupdf4llm"
    assert _triples(_cells_of(blocks)) == {
        ("BERT", "Accuracy", "0.811"), ("BERT", "F1", "0.792"),
        ("Ours", "Accuracy", "0.905"), ("Ours", "F1", "0.887"),
    }


def test_12_pymupdf4llm_leaks_global_state_into_find_tables():
    """Pins a MEASURED third-party hazard, not a design choice.

    After pymupdf4llm.to_markdown runs, page.find_tables() in the same process
    starts returning text-clustered grids it did not return before, with
    corrupted values ('0 811\\n.' for '0.811'). The measurement harness must
    therefore run each arm in its own process.

    If this test ever FAILS, the leak has been fixed upstream: re-check whether
    process isolation is still required before relaxing the harness.
    """
    data = _borderless_pdf()

    def tier1():
        d = pymupdf.open(stream=data, filetype="pdf")
        g = _tier1_grids(d[0], allow_contaminated=True)   # measuring the leak itself
        d.close()
        return g

    assert pymupdf4llm_invoked(), "test ordering broken: test_2 must run before this"
    contaminated = tier1()
    assert contaminated, "expected the leak: find_tables now sees a phantom grid"
    values = [c for row in contaminated[0][1:] for c in row[1:]]
    assert any("\n" in v for v in values), f"expected corrupted values, got {values}"


def test_13_tier1_refuses_to_run_once_contaminated():
    """Amendment A(ii): an unordered tier-1 call must RAISE, not corrupt."""
    data = _borderless_pdf()
    doc = pymupdf.open(stream=data, filetype="pdf")
    assert pymupdf4llm_invoked(), "test ordering broken: test_2 must run before this"
    with pytest.raises(RuntimeError, match="contaminated"):
        _tier1_grids(doc[0])
    doc.close()


def test_14_second_paper_in_a_contaminated_process_raises():
    """The across-paper case amendment A names: paper 2's tier-1 calls would run
    after paper 1's to_markdown. The run must stop rather than report a
    corrupted arm."""
    with pytest.raises(RuntimeError, match="one paper per process"):
        blocks_from_pdf_layout(_ruled_pdf(), PID, SRC, "pymupdf_tables")
