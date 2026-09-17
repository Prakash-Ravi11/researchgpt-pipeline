"""EXPERIMENT (exp/parser-backend) — layout-aware PDF table cells.

Not wired into `build_document()`. `parser_backend_measure.py` calls this
directly. `represent.blocks_from_pdf` is untouched.

The block stream is `blocks_from_pdf`'s, verbatim: this module re-uses it and
only *adds* `table_cells` (+ the recording keys) to blocks already typed
`table`. Prose text, block ids, char spans and section labels are therefore
byte-identical to the `current` arm, which is what makes the arms comparable —
a delta can only come from the cells.

Quality gate thresholds are pre-registered in PARSER_BACKEND_REPORT.md §1.1-1.3
and must not be tuned against a result.
"""
from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from .represent import blocks_from_pdf
from .schema import structured_table, table_cell

# ---- pre-registered quality gate (PARSER_BACKEND_REPORT.md §1.1) -----------
MAX_ROW_LABEL_CHARS = 60
MAX_COL_HEADER_CHARS = 40
MIN_DATA_ROWS = 2
MIN_COLUMNS = 2

# Keys this module adds on top of a `blocks_from_pdf` block. Table blocks carry
# exactly these extras and nothing else (§8 key-set reading).
TABLE_EXTRA_KEYS = frozenset({
    "table_cells", "table_parse_status", "table_fallback", "table_caption",
    "layout_backend", "rows_before_gate", "rows_after_gate", "n_rows_dropped",
    "drop_reasons", "table_type_before", "table_type_after",
    "column_headers", "raw_column_headers", "row_labels",
})

BACKENDS = ("pymupdf_tables", "pymupdf4llm")

# MEASURED HAZARD (see PARSER_BACKEND_REPORT.md): calling pymupdf4llm.to_markdown
# mutates global PyMuPDF state. Afterwards, in the SAME PROCESS,
# page.find_tables() returns text-clustered grids it did not return before, with
# corrupted values ('0 811\n.' for '0.811'). Running the arms in one process
# would therefore silently contaminate the pymupdf_tables and current arms
# depending on execution order. Arms must be process-isolated; this flag lets a
# caller assert it.
_PYMUPDF4LLM_INVOKED = False


def pymupdf4llm_invoked() -> bool:
    """True once pymupdf4llm has run in this process — after which tier-1
    find_tables results are no longer trustworthy."""
    return _PYMUPDF4LLM_INVOKED


# --------------------------------------------------------------------------
# Copy of represent._jats_table_cells with `representation` as a parameter.
# This is the ONLY duplicated logic in this module (§7). Behaviour is otherwise
# unchanged: row[0] is the header, row_label is the first spanning cell of each
# row, >= 2 rows required, cells whose value equals the row_label are skipped.
# --------------------------------------------------------------------------

def _layout_table_cells(node, paper_id: str, source: str, section: str, cpath: str,
                        strip, representation: str):
    cap_el = node.find(".//{*}caption")
    caption = " ".join(x.strip() for x in (cap_el.itertext() if cap_el is not None else []) if x.strip())
    grid = node if strip(node.tag) == "table" else node.find(".//{*}table")
    tid = f"{paper_id}:{cpath}"
    if grid is None:
        return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                representation=representation, section=section, caption=caption,
                                cells=[], parse_status="fallback_pdf",
                                fallback="table-wrap_has_no_xml_grid")
    rows = [tr for tr in grid.iter() if strip(tr.tag) == "tr"]
    if len(rows) < 2:
        return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                representation=representation, section=section, caption=caption,
                                cells=[], parse_status="fallback_pdf", fallback=f"too_few_rows:{len(rows)}")

    def cell_text(c):
        return " ".join(x.strip() for x in c.itertext() if x.strip())

    def expand(tr):
        seq = []
        for c in tr:
            if strip(c.tag) not in ("th", "td"):
                continue
            span = int(c.get("colspan", "1") or "1")
            rspan = int(c.get("rowspan", "1") or "1")
            seq.append((cell_text(c), span, rspan))
            for _ in range(span - 1):
                seq.append(("", 0, 1))
        return seq

    header = [t for (t, _s, _r) in expand(rows[0])]
    cells: list[dict[str, Any]] = []
    for r_i, tr in enumerate(rows[1:], start=1):
        seq = expand(tr)
        try:
            row_label = next(t for (t, s, _r) in seq if s)
        except StopIteration:
            row_label = ""
        col = 0
        for (val, s, r) in seq:
            if s == 0:
                col += 1
                continue
            head = header[col] if col < len(header) else ""
            if val and head and val != row_label:
                cells.append(table_cell(value=val, column_header=head, row_label=row_label,
                                        caption=caption, section=section, row=r_i, col=col,
                                        spans={k: v for k, v in (("colspan", s), ("rowspan", r)) if v > 1}))
            col += s
    status = "parsed" if cells else "fallback_pdf"
    return structured_table(table_id=tid, paper_id=paper_id, source=source,
                            representation=representation, section=section, caption=caption,
                            cells=cells, parse_status=status,
                            fallback=None if cells else "no_data_cells_after_parse")


def _strip(tag: str) -> str:
    return tag.split("}")[-1]


# --------------------------------------------------------------------------
# Pre-registered quality gate
# --------------------------------------------------------------------------

def _collapse_ws(s: str) -> str:
    """Intra-cell whitespace -> single spaces. 'Tempo\\n(sem cache)' becomes
    'Tempo (sem cache)'. Semantic content preserved; only layout wrapping goes."""
    return " ".join((s or "").split())


def _reject_header(header: list[str], collapse_header_ws: bool = False) -> str | None:
    """Whole-table rejection (§1.2). Returns a reason, or None to keep.

    The FIRST header cell may be empty: it is the row-label corner, and
    `_layout_table_cells` never binds anything to it (col 0 holds the row label
    and `val != row_label` skips it). An empty header over a DATA column is the
    dangerous one and still rejects the whole table — see report D5.
    """
    if len(header) < MIN_COLUMNS:
        return f"too_few_columns:{len(header)}"
    for i, h in enumerate(header):
        if i and not (h or "").strip():
            return f"empty_header_cell:col{i}"
        # EXPERIMENT 2, the single variable: with collapse_header_ws the newline
        # no longer rejects the table — the header is normalised instead (done by
        # the caller, before this check). Every other rule is unchanged, and an
        # over-long header still fails below on its NORMALISED length.
        if not collapse_header_ws and "\n" in (h or ""):
            return f"newline_in_header:col{i}"
        if len(h or "") > MAX_COL_HEADER_CHARS:
            return f"header_too_long:col{i}:{len(h)}"
    return None


def _row_drop_reason(row_label: str) -> str | None:
    """Individual row drop (§1.3). A dropped row appears in no cell, so
    structural_bind case 5a falls through to grounding instead of mis-binding."""
    if not (row_label or "").strip():
        return "empty_row_label"
    if "\n" in row_label:
        return "newline_in_row_label"
    if len(row_label) > MAX_ROW_LABEL_CHARS:
        return "row_label_too_long"
    return None


def _gate_grid(grid: list[list[str]], collapse_header_ws: bool = False) -> dict[str, Any]:
    """Apply the pre-registered gate to a raw grid.

    Returns {"header", "rows", "reject", "drop_reasons", "rows_before", "rows_after"}.
    `reject` non-None means the WHOLE table is rejected -> fallback_pdf, no cells.

    MIN_DATA_ROWS is checked on the RAW grid only. It is deliberately NOT
    re-applied after row drops: a table falling below 2 surviving rows is the
    D6(b) `results` -> `other` flip the run is measuring, and re-rejecting here
    would suppress that measurement.
    """
    if not grid or len(grid) < 1 + MIN_DATA_ROWS:
        return {"header": [], "rows": [], "reject": f"too_few_data_rows:{max(0, len(grid) - 1)}",
                "drop_reasons": {}, "rows_before": max(0, len(grid) - 1), "rows_after": 0,
                "raw_header": list(grid[0]) if grid else []}
    raw_header, body = list(grid[0]), grid[1:]
    header = [_collapse_ws(h) for h in raw_header] if collapse_header_ws else raw_header
    rej = _reject_header(header, collapse_header_ws)
    if rej:
        return {"header": header, "rows": [], "reject": rej, "drop_reasons": {},
                "rows_before": len(body), "rows_after": 0, "raw_header": raw_header}
    kept: list[list[str]] = []
    drops: dict[str, int] = {}
    for row in body:
        label = row[0] if row else ""
        why = _row_drop_reason(label)
        if why:
            drops[why] = drops.get(why, 0) + 1
        else:
            kept.append(row)
    return {"header": header, "rows": kept, "reject": None, "drop_reasons": drops,
            "rows_before": len(body), "rows_after": len(kept), "raw_header": raw_header}


def _grid_to_xhtml(header: list[str], rows: list[list[str]], caption: str) -> str:
    """Well-formed XHTML for `_layout_table_cells`. Every value is escaped —
    backend text is untrusted and goes through an XML parser."""
    def tr(cells: list[str], tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{escape(c or '')}</{tag}>" for c in cells) + "</tr>"
    return ("<table-wrap>"
            f"<caption>{escape(caption or '')}</caption>"
            "<table><thead>" + tr(header, "th") + "</thead><tbody>"
            + "".join(tr(r, "td") for r in rows) + "</tbody></table></table-wrap>")


def _classify(caption: str, headers: list[str], rows: list[str]) -> str:
    """gate.classify_table on this table's own inputs. Imported lazily so this
    module stays importable without the gate."""
    from .gate import classify_table
    return classify_table(caption or "", set(headers or []), set(rows or []))


# --------------------------------------------------------------------------
# Backends — imported lazily, never auto-installed
# --------------------------------------------------------------------------

def _norm(grid) -> list[list[str]]:
    return [[("" if c is None else str(c)) for c in row] for row in (grid or [])]


def _tier1_grids(page, *, allow_contaminated: bool = False) -> list[list[list[str]]]:
    """page.find_tables() — ruling-line tables.

    Guarded: once pymupdf4llm has run in this process, find_tables returns
    phantom text-clustered grids with corrupted values, so a tier-1 call after
    that point is not measuring what it claims. Raising here is the amendment-A
    (ii) enforcement — a violation stops the run instead of silently corrupting
    an arm. `allow_contaminated=True` is for the test that pins the leak itself.
    """
    if _PYMUPDF4LLM_INVOKED and not allow_contaminated:
        raise RuntimeError(
            "find_tables() called after pymupdf4llm ran in this process: tier-1 "
            "results would be contaminated (phantom grids, values like '0 811\\n.'). "
            "Run one paper per process, and all tier-1 calls before any tier-2 call."
        )
    out = []
    for t in page.find_tables().tables:
        g = _norm(t.extract())
        if g:
            out.append(g)
    return out


def _parse_pipe_tables(md: str) -> list[list[list[str]]]:
    """Markdown pipe tables -> grids. The separator row (|---|---|) is dropped."""
    grids, cur = [], []
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            cells = [c.strip() for c in s[1:-1].split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):
                continue                       # separator row
            cur.append(cells)
        elif cur:
            grids.append(cur)
            cur = []
    if cur:
        grids.append(cur)
    return [g for g in grids if len(g) >= 2]


def _tier2_page_markdown(data: bytes, doc) -> dict[int, str]:
    """pymupdf4llm markdown, one entry per 1-based page number.

    `table_strategy="text"` is what reaches BORDERLESS tables; the library
    default (`lines_strict`) is the same strategy tier 1 already uses, so at the
    default tier 2 could add nothing. Recorded in the report as an implementation
    choice, not a tuned parameter.
    """
    global _PYMUPDF4LLM_INVOKED
    try:
        import pymupdf4llm
    except ImportError as e:                                  # pragma: no cover
        raise ImportError(
            "backend 'pymupdf4llm' needs: pip install pymupdf4llm"
        ) from e
    _PYMUPDF4LLM_INVOKED = True
    chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, table_strategy="text",
                                     show_progress=False)
    return {i + 1: (c.get("text") or "") for i, c in enumerate(chunks)}


# --------------------------------------------------------------------------

def blocks_from_pdf_layout(data: bytes, paper_id: str, source: str,
                           backend: str, *,
                           collapse_header_ws: bool = False) -> list[dict[str, Any]]:
    """`blocks_from_pdf` blocks + structured `table_cells` on table blocks.

    backend:
      "pymupdf_tables" — tier 1 (page.find_tables) only, else fallback_pdf.
      "pymupdf4llm"    — tier 1, then tier 2 (markdown pipe tables), else
                         fallback_pdf. Tiering is decided PER TABLE.

    collapse_header_ws is EXPERIMENT 2's single variable. False reproduces the
    section-9 behaviour exactly: a newline in a header cell rejects the table.
    True normalises intra-cell header whitespace instead. Nothing else changes.
    """
    if backend not in BACKENDS:
        raise ValueError(f"backend must be one of {BACKENDS}, got {backend!r}")
    try:
        import pymupdf
    except ImportError as e:                                  # pragma: no cover
        raise ImportError("this experiment needs: pip install pymupdf") from e

    blocks = blocks_from_pdf(data, paper_id, source)
    tbl_blocks = [b for b in blocks if b["block_type"] == "table"]
    if not tbl_blocks:
        return blocks

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        # grids per 1-based page, per tier
        # Amendment A(ii): EVERY tier-1 decision for this paper is taken and
        # cached before any tier-2 call, because to_markdown poisons find_tables
        # for the rest of the process. _tier1_grids asserts this itself.
        t1: dict[int, list] = {}
        page_errors: dict[int, str] = {}
        for pno, page in enumerate(doc, start=1):
            try:
                t1[pno] = _tier1_grids(page)
            except RuntimeError:
                raise                   # contamination is a harness bug, not a
                                        # page-level data problem: stop the run
            except Exception as e:      # recorded on that page's table blocks,
                t1[pno] = []            # never swallowed
                page_errors[pno] = f"tier1_page_error:{type(e).__name__}:{e}"
        t2: dict[int, list] = {}
        if backend == "pymupdf4llm":
            md = _tier2_page_markdown(data, doc)
            for pno, text in md.items():
                t2[pno] = _parse_pipe_tables(text)

        # table blocks on a page consume that page's grids in reading order
        used: dict[int, int] = {}
        for b in tbl_blocks:
            pno = int(str(b.get("page_or_node") or "p0").lstrip("p") or 0)
            i = used.get(pno, 0)
            grid, tier = None, None
            if i < len(t1.get(pno, [])):
                grid, tier = t1[pno][i], "find_tables"
            elif backend == "pymupdf4llm" and i < len(t2.get(pno, [])):
                grid, tier = t2[pno][i], "pymupdf4llm"
            used[pno] = i + 1
            _attach(b, grid, tier, paper_id, source, backend, page_errors.get(pno),
                    collapse_header_ws=collapse_header_ws)
    finally:
        doc.close()
    return blocks


def _attach(b: dict[str, Any], grid, tier: str | None, paper_id: str, source: str,
            backend: str, page_error: str | None = None, *,
            collapse_header_ws: bool = False) -> None:
    """Attach cells + every recording key to one table block."""
    caption = (b.get("text") or "").splitlines()[0].strip() if b.get("text") else ""
    section = b.get("section")
    cpath = b.get("block_id", "")

    b["layout_backend"] = backend
    b["table_caption"] = caption
    b["drop_reasons"] = {}
    b["n_rows_dropped"] = 0
    b["rows_before_gate"] = 0
    b["rows_after_gate"] = 0
    b["column_headers"] = []
    b["raw_column_headers"] = []
    b["row_labels"] = []
    b["table_type_before"] = None
    b["table_type_after"] = None

    if grid is None:
        b["table_cells"] = []
        b["table_parse_status"] = "fallback_pdf"
        b["table_fallback"] = page_error or "no_grid_from_backend"
        return

    g = _norm(grid)
    gated = _gate_grid(g, collapse_header_ws)
    b["rows_before_gate"] = gated["rows_before"]
    b["rows_after_gate"] = gated["rows_after"]
    b["drop_reasons"] = gated["drop_reasons"]
    b["n_rows_dropped"] = sum(gated["drop_reasons"].values())

    # D6(b): classify on the PRE-gate grid and on the POST-gate grid, and record
    # both, so a results -> other flip caused by row drops is visible in the
    # artifact rather than silently applied.
    if len(g) >= 2:
        b["table_type_before"] = _classify(caption, g[0], [r[0] for r in g[1:] if r])

    if gated["reject"]:
        b["table_cells"] = []
        b["table_parse_status"] = "fallback_pdf"
        b["table_fallback"] = f"quality_gate:{gated['reject']}"
        b["column_headers"] = gated["header"]
        b["raw_column_headers"] = gated.get("raw_header") or []
        return

    xhtml = _grid_to_xhtml(gated["header"], gated["rows"], caption)
    st = _layout_table_cells(ET.fromstring(xhtml), paper_id, source, section, cpath,
                             _strip, representation="pdf_layout")
    b["table_cells"] = st["cells"]
    b["table_parse_status"] = st["parse_status"]
    b["table_fallback"] = st["fallback"] or (f"tier:{tier}" if st["cells"] else None)
    b["column_headers"] = gated["header"]
    b["raw_column_headers"] = gated.get("raw_header") or []
    b["row_labels"] = sorted({c["row_label"] for c in st["cells"]})
    b["table_type_after"] = _classify(caption, gated["header"], b["row_labels"])
