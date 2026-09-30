"""P1/P2 - canonical document representation + provenance-bearing blocks.

One code path, several front-ends:
  * JATS XML    -> section/paragraph hierarchy with XML node paths
  * arXiv LaTeX -> section/paragraph structure + STRUCTURED table cells from the
                   e-print source (content only; identity came from the PDF)
  * PDF         -> PyMuPDF text blocks with page numbers + heuristic section labels

Output block schema (every downstream evidence item traces to one of these):
  {block_id, paper_id, source, representation, section, subsection,
   page_or_node, block_type, char_start, char_end, text}
A `block_type == "table"` block from JATS or LaTeX additionally carries
`table_cells` (the canonical structured_table shape - value + column_header +
row_label + caption + section per cell) and `table_parse_status` /
`table_fallback`. A PDF table block carries them only when its caption sits
directly above or below a RULED table that PyMuPDF detects and that passes
validation (see "PDF structured table cells" below); borderless PDF tables are
not reconstructed and keep no cells.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any

from .schema import REPR_JATS, REPR_LATEX, REPR_PDF, structured_table, table_cell

BlockType = str  # "heading" | "paragraph" | "table" | "figure_caption" | "abstract"

_SECTION_WORDS = (
    "abstract", "introduction", "background", "related work", "prior work",
    "materials and methods", "methods", "methodology", "approach", "method",
    "experimental setup", "experiments", "evaluation", "results", "findings",
    "discussion", "analysis", "ablation", "limitations", "threats to validity",
    "conclusion", "conclusions", "future work", "acknowledgements", "references",
)
_HEADING_RE = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*|[IVXivx]{1,5})\.?\s+)?(" +
    "|".join(re.escape(w) for w in _SECTION_WORDS) + r")\b",
    re.IGNORECASE,
)
_NUM_HEADING_RE = re.compile(r"^\s*(?:\d+(?:\.\d+){0,2}|[IVX]{1,5})\.?\s+[A-Z][A-Za-z].{0,60}$")


def _canon_section(label: str, default: str | None = None) -> str:
    low = label.strip().lower()
    for w in ("materials and methods", "methodology", "method", "methods", "approach"):
        if w in low:
            return "method"
    for w in ("experimental setup", "experiments", "evaluation"):
        if w in low:
            return "experimental_setup"
    for w in ("results", "findings"):
        if w in low:
            return "results"
    for w in ("related work", "prior work", "background", "introduction"):
        if w in low:
            return "introduction_related_work"
    for w in ("limitations", "threats to validity"):
        if w in low:
            return "limitations"
    for w in ("discussion", "analysis", "ablation"):
        if w in low:
            return "discussion"
    for w in ("conclusion", "future work"):
        if w in low:
            return "conclusion"
    if "abstract" in low:
        return "abstract"
    if "reference" in low:
        return "references"
    return default if default is not None else (low[:40] or "body")


def _mk(paper_id, source, rep, section, node, btype, text, cursor):
    text = text.strip()
    return {
        "block_id": f"{paper_id}:{len(cursor['blocks'])}",
        "paper_id": paper_id, "source": source, "representation": rep,
        "section": section, "subsection": None, "page_or_node": node,
        "block_type": btype, "char_start": cursor["pos"],
        "char_end": cursor["pos"] + len(text), "text": text,
    }


def blocks_from_jats(data: bytes, paper_id: str, source: str) -> list[dict[str, Any]]:
    root = ET.fromstring(data)
    cursor = {"blocks": [], "pos": 0}
    out: list[dict[str, Any]] = []

    def strip(tag: str) -> str:
        return tag.split("}")[-1]

    abst = root.find(".//{*}abstract")
    if abst is not None:
        txt = " ".join("".join(p.itertext()) for p in abst.iter() if strip(p.tag) == "p") \
              or "".join(abst.itertext())
        if txt.strip():
            b = _mk(paper_id, source, REPR_JATS, "abstract", "front/abstract", "abstract", txt, cursor)
            out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]

    body = root.find(".//{*}body")
    if body is None:
        return out

    def walk(el, sec_label: str, path: str):
        for i, child in enumerate(list(el)):
            t = strip(child.tag)
            cpath = f"{path}/{t}[{i}]"
            if t == "sec":
                title_el = child.find("./{*}title")
                title = "".join(title_el.itertext()).strip() if title_el is not None else ""
                # keep the parent's canonical label when this child's title is not
                # a recognized standard section name (custom method subsections etc.)
                child_label = _canon_section(title, default=sec_label) if title else sec_label
                walk(child, child_label, cpath)
            elif t == "p":
                txt = "".join(child.itertext()).strip()
                if len(txt) > 1:
                    b = _mk(paper_id, source, REPR_JATS, sec_label, cpath, "paragraph", txt, cursor)
                    out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]
            elif t in ("table-wrap", "table"):
                txt = " ".join(x.strip() for x in child.itertext() if x.strip())
                if txt:
                    b = _mk(paper_id, source, REPR_JATS, sec_label, cpath, "table", txt, cursor)
                    # SAME structured cell model as the LaTeX path (one shape
                    # downstream — Phase 5's gate must not need two code paths).
                    st = _jats_table_cells(child, paper_id, source, sec_label, cpath, strip)
                    b["table_cells"] = st["cells"]
                    b["table_parse_status"] = st["parse_status"]
                    b["table_fallback"] = st["fallback"]
                    b["table_caption"] = st["caption"]
                    out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]
            elif t in ("fig",):
                cap = child.find(".//{*}caption")
                txt = "".join(cap.itertext()).strip() if cap is not None else ""
                if txt:
                    b = _mk(paper_id, source, REPR_JATS, sec_label, cpath, "figure_caption", txt, cursor)
                    out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]
            else:
                walk(child, sec_label, cpath)

    walk(body, "body", "body")
    return out


def blocks_from_pdf(data: bytes, paper_id: str, source: str) -> list[dict[str, Any]]:
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    cursor = {"blocks": [], "pos": 0}
    out: list[dict[str, Any]] = []
    current_section = "body"
    captions: list[tuple[dict[str, Any], int, tuple]] = []   # caption-like table blocks: (block, page, bbox)

    for pno, page in enumerate(doc, start=1):
        page_blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text,bno,btype)
        page_blocks.sort(key=lambda b: (round(b[1] / 3), b[0]))  # reading order-ish
        for pb in page_blocks:
            raw = (pb[4] or "").strip()
            if not raw or len(raw) < 3:
                continue
            first_line = raw.splitlines()[0].strip()
            m = _HEADING_RE.match(first_line)
            is_heading = bool(m) or (len(first_line) < 70 and _NUM_HEADING_RE.match(first_line))
            if is_heading:
                current_section = _canon_section(m.group(1) if m else first_line)
                b = _mk(paper_id, source, REPR_PDF, current_section, f"p{pno}", "heading",
                        first_line, cursor)
                out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]
                rest = raw[len(first_line):].strip()
                if len(rest) > 40:
                    b2 = _mk(paper_id, source, REPR_PDF, current_section, f"p{pno}", "paragraph",
                             rest, cursor)
                    out.append(b2); cursor["blocks"].append(b2); cursor["pos"] = b2["char_end"]
                continue
            low = first_line.lower()
            btype = "figure_caption" if low.startswith(("figure ", "fig.", "fig ")) else (
                "table" if low.startswith("table ") else "paragraph")
            b = _mk(paper_id, source, REPR_PDF, current_section, f"p{pno}", btype, raw, cursor)
            out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]
            if btype == "table":
                captions.append((b, pno, tuple(pb[:4])))
    _attach_pdf_table_cells(doc, captions)
    _attach_borderless_cells(data, doc, captions)
    doc.close()
    return out


# --------------------------------------------------------------------------
# PDF structured table cells (ruled tables only)
#
# The PDF front-end above types a block "table" from its first line; that block
# is the table's caption, while the table body stays in ordinary text blocks.
# A caption-LIKE table block ("Table 3: ...", "Table 1.", "TABLE IV",
# "Table 2 Summary ...") gets `table_cells` when PyMuPDF's ruling-line table
# detector (page.find_tables(), default strategy) finds a table directly below,
# under or above it on the same page and the grid passes `_pdf_grid_problem`.
# Only keys are added to that caption block -- block text, ids, char spans and
# types are unchanged, so the text every other stage reads is identical.
# Borderless tables are deliberately not reconstructed: a text-alignment
# strategy splits words across columns and merges rows on real papers, and a
# wrong grid is worse than none (a merged cell binds any row it names). Such
# captions keep no cells, with the reason in `table_fallback`.
#
# Row label (`_pdf_row_label_column`): column 0, unless column 0 is CLEARLY an
# index -- every body cell a small integer, consecutive from 0 or 1, and
# zero-padded, index-headed ('S.no', 'No.', '#', 'ID', 'Rank', ...) or
# unheaded -- AND a later column is entity-bearing (every body cell filled with
# a word, all values distinct). Then the first such column is the row label and
# the index becomes an ordinary cell; otherwise column 0 stays the row label.
# Only the table's own cells decide -- never claims, captions or paper identity.
# --------------------------------------------------------------------------
_PDF_CAPTION_RE = re.compile(r"^\s*(?i:table|tab\.)\s*(?:\d+|[IVXLCivxlc]+)(?:\s*[.:]|\s*$|\s+[A-Z(\[])")
_PDF_CAPTION_GAP = 60.0      # max vertical gap (pt) between a caption and its table
_PDF_MIN_OVERLAP = 0.3       # min horizontal overlap, as a share of the narrower box
_PDF_MIN_COLUMNS = 2
_PDF_MIN_BODY_ROWS = 2
_PDF_MAX_HEADER_CHARS = 60   # a longer "header" cell is a page region or prose, not a table
_PDF_MAX_CELL_CHARS = 200
_INDEX_VALUE_RE = re.compile(r"^\(?(\d{1,3})\)?[.)]?$")
_INDEX_HEADER_RE = re.compile(
    r"^(?:s\.?\s*no\.?|sl\.?\s*no\.?|sr\.?\s*no\.?|no\.?|nr\.?|#|index|idx|id|rank|serial(?:\s*no\.?)?)$", re.I)
_WORD_RE = re.compile(r"[^\W\d_]{2,}")


def _ws(s: Any) -> str:
    return " ".join(str(s or "").split())


def _lines(s: str | None) -> list[str]:
    return [x for x in (s or "").splitlines() if x.strip()]


def _pdf_table_grid(table) -> tuple[list[str], list[list[str | None]]]:
    """(header, body) of a PyMuPDF table. Header cells are whitespace-collapsed; a None
    header cell is covered by a merged header and repeats the header to its left. Body
    cells keep their line breaks (for `_pdf_grid_problem`); None body cells (covered by a
    merged cell) are kept for `_pdf_grid_cells`. An external header that is really the
    caption line above the table is ignored (the first row is the header then). A first
    body row with no digit, above rows that all carry numbers, is a second header row and
    is folded into the header as 'top / sub'."""
    rows = [[None if c is None else c.strip() for c in r] for r in (table.extract() or [])]
    hdr = getattr(table, "header", None)
    names = list(hdr.names or []) if hdr is not None and hdr.external else []
    if not names or _PDF_CAPTION_RE.match(" ".join(h for h in names if h)):
        names, rows = (rows[0] if rows else []), rows[1:]
    header: list[str] = []
    for h in names:
        header.append(header[-1] if h is None and header else _ws(h))
    n = len(header)
    body = [(r + [""] * n)[:n] for r in rows]
    if len(body) > _PDF_MIN_BODY_ROWS and not any(re.search(r"\d", c or "") for c in body[0]) \
            and all(any(re.search(r"\d", c or "") for c in r) for r in body[1:]):
        sub = [_ws(s) for s in body.pop(0)]
        header = [f"{h} / {s}" if h and s and s != h else (h or s or "") for h, s in zip(header, sub)]
    return header, body


def _pdf_grid_problem(header: list[str], body: list[list[str | None]]) -> str | None:
    """Why a detected grid must not become table_cells (None = keep it)."""
    if len(header) < _PDF_MIN_COLUMNS:
        return f"too_few_columns:{len(header)}"
    if len(body) < _PDF_MIN_BODY_ROWS:
        return f"too_few_body_rows:{len(body)}"
    if any(len(h) > _PDF_MAX_HEADER_CHARS for h in header):
        return "header_cell_too_long"
    if not any(_WORD_RE.search(h) for h in header[1:]):
        return "header_has_no_words"         # the "header" row is data or a figure fragment
    if any(len(_ws(c)) > _PDF_MAX_CELL_CHARS for r in body for c in r):
        return "prose_like_cell"
    for r in body:                           # rows merged into one: 'A\nB\nC' beside '1.0\n2.0\n3.0'
        k = len(_lines(r[0]))
        for c in r[1:]:
            ls = _lines(c)
            if k >= 2 and len(ls) == k and all(re.search(r"\d", x) for x in ls) \
                    and len({re.sub(r"\d+", "9", x.strip()) for x in ls}) == 1:
                return "stacked_records"
    if sum(1 for r in body if not r[0] and any(
            (c or "")[:1].islower() and len(_ws(c)) >= 30 for c in r[1:])) >= 2:
        return "wrapped_text_rows"           # the rows are lines of wrapped prose, not records
    return None


def _is_index_column(header: str, values: list[str | None]) -> bool:
    """A CLEAR index/ordinal column: every body cell a small integer, consecutive from
    0 or 1, and zero-padded, index-headed or unheaded."""
    if len(values) < _PDF_MIN_BODY_ROWS or not all(values):
        return False
    found = [_INDEX_VALUE_RE.match(v) for v in values]
    if not all(found):
        return False
    nums = [int(m.group(1)) for m in found]
    if nums[0] not in (0, 1) or any(b - a != 1 for a, b in zip(nums, nums[1:])):
        return False
    padded = any(re.match(r"\(?0\d", v) for v in values)
    return padded or not header or bool(_INDEX_HEADER_RE.match(header))


def _is_entity_column(values: list[str | None]) -> bool:
    """Every body cell filled with a word (2+ letters) and all values distinct."""
    return (len(values) >= _PDF_MIN_BODY_ROWS and all(values)
            and all(_WORD_RE.search(v) for v in values) and len(set(values)) == len(values))


def _pdf_row_label_column(header: list[str], body: list[list[str | None]]) -> tuple[int, str]:
    if not _is_index_column(header[0], [r[0] for r in body]):
        return 0, "first_column"
    for c in range(1, len(header)):
        if _is_entity_column([r[c] for r in body]):
            return c, f"entity_column:{c} (column 0 {header[0]!r} is an index)"
    return 0, "first_column (column 0 is index-like; no entity-bearing column)"


def _pdf_grid_cells(header: list[str], body: list[list[str | None]], caption: str,
                    section: str | None, page_no: int) -> tuple[list[dict[str, Any]], str]:
    lab, rule = _pdf_row_label_column(header, body)
    cells: list[dict[str, Any]] = []
    label = ""
    for r_i, row in enumerate(body, start=1):
        if row[lab] is not None:              # None: covered by a row-spanning label -> carry it down
            label = _ws(row[lab])
        for c, raw in enumerate(row):
            val = _ws(raw)
            if c == lab or not val or not header[c]:
                continue
            cell = table_cell(value=val, column_header=header[c], row_label=label,
                              caption=caption, section=section, row=r_i, col=c)
            cell["page"] = page_no
            cells.append(cell)
    return cells, rule


def _attach_pdf_table_cells(doc, captions: list[tuple[dict[str, Any], int, tuple]]) -> None:
    """Give each caption-like PDF table block the cells of the ruled table beside it."""
    import pymupdf
    by_page: dict[int, list[tuple[dict[str, Any], Any]]] = defaultdict(list)
    for b, pno, bbox in captions:
        if _PDF_CAPTION_RE.match(b["text"].splitlines()[0]):
            by_page[pno].append((b, pymupdf.Rect(bbox)))
    for pno, caps in sorted(by_page.items()):
        try:
            page = doc[pno - 1]
            text_blocks = [(pymupdf.Rect(pb[:4]), pb[4].strip()) for pb in page.get_text("blocks")
                           if pb[6] == 0 and (pb[4] or "").strip()]
            text_blocks.sort(key=lambda x: (x[0].y0, x[0].x0))
            grids, rejected = [], []
            for t in page.find_tables().tables:
                header, body = _pdf_table_grid(t)
                why = _pdf_grid_problem(header, body)
                if why:
                    rejected.append(why)
                else:
                    grids.append((pymupdf.Rect(t.bbox), header, body, bool(t.header is not None and t.header.external)))
            pairs = []
            for ci, (_, cr) in enumerate(caps):
                for gi, (tr, _, _, _) in enumerate(grids):
                    if tr.y0 >= cr.y1 - 3:
                        gap = max(0.0, tr.y0 - cr.y1)           # table below its caption
                    elif cr.y0 <= tr.y0 < cr.y1:
                        gap = 0.0                               # caption block runs into the table top
                    elif tr.y1 <= cr.y0 + 3:
                        gap = max(0.0, cr.y0 - tr.y1) + 0.5     # table above its caption (below wins ties)
                    else:
                        continue
                    if gap <= _PDF_CAPTION_GAP and \
                            min(cr.x1, tr.x1) - max(cr.x0, tr.x0) >= _PDF_MIN_OVERLAP * min(cr.width, tr.width):
                        pairs.append((gap, ci, gi))
            done_c, done_g = set(), set()
            for _gap, ci, gi in sorted(pairs):
                if ci in done_c or gi in done_g:
                    continue
                b, cr = caps[ci]
                tr, header, body, external = grids[gi]
                parts = [b["text"]]
                if not external and tr.y0 >= cr.y1 - 3:   # caption lines split off between caption block and table
                    parts += [t for r, t in text_blocks if r.y0 >= cr.y1 - 1 and r.y1 <= tr.y0 + 1
                              and min(r.x1, cr.x1) - max(r.x0, cr.x0) > 0]
                caption = _ws(" ".join(parts))[:400]
                cells, rule = _pdf_grid_cells(header, body, caption, b["section"], pno)
                if not cells:
                    continue
                done_c.add(ci)
                done_g.add(gi)
                b.update(table_cells=cells, table_caption=caption, table_parse_status="parsed",
                         table_fallback=None, table_backend="pymupdf.find_tables",
                         table_bbox=[round(v, 1) for v in tr], table_row_label_rule=rule,
                         table_shape=[len(body), len(header)])
            for ci, (b, _) in enumerate(caps):
                if ci not in done_c:
                    b.update(table_parse_status="fallback_pdf",
                             table_fallback="no_ruled_table_beside_caption"
                             + (f" (page grids rejected: {', '.join(sorted(set(rejected)))})" if rejected else ""))
        except Exception as e:  # noqa: BLE001 -- cells are additive: never break the text path
            for b, _ in caps:
                if not b.get("table_cells"):
                    b.update(table_parse_status="fallback_pdf",
                             table_fallback=f"table_extraction_error:{type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# Borderless PDF tables (phase 09A), behind `borderless_policy`, default "off".
# Only caption blocks the ruled path above left as `no_ruled_table_beside_caption` are
# routed to src/evidence/borderless.py (Docling + Table Transformer consensus). With "off"
# nothing is routed or imported, so the output is the ruled-only output above.
# The flag is read like gate._disambiguation_policy on exp/r4-disambiguation:
# RGPT_BORDERLESS_POLICY wins, then the `borderless_policy:` line of
# configs/staging_config.yaml, then "off".
# --------------------------------------------------------------------------
_BORDERLESS_POLICIES = ("off", "consensus")


def _borderless_policy() -> str:
    import os
    from pathlib import Path
    env = os.environ.get("RGPT_BORDERLESS_POLICY", "").strip().lower()
    if env in _BORDERLESS_POLICIES:
        return env
    cfg = Path(__file__).resolve().parents[2] / "configs" / "staging_config.yaml"
    try:
        for raw in cfg.read_text(encoding="utf-8").splitlines():
            key, _, val = raw.partition(":")
            if key.strip() == "borderless_policy":
                v = val.split("#")[0].strip().lower()
                if v in _BORDERLESS_POLICIES:
                    return v
    except OSError:
        pass
    return "off"


def _attach_borderless_cells(data: bytes, doc, captions: list[tuple[dict[str, Any], int, tuple]]) -> None:
    """Route ruled-path rejects (`no_ruled_table_beside_caption`) to the borderless backend when enabled."""
    if _borderless_policy() != "consensus":
        return
    todo = [(b, pno, bbox) for b, pno, bbox in captions
            if b.get("table_parse_status") == "fallback_pdf"
            and (b.get("table_fallback") or "").startswith("no_ruled_table_beside_caption")]
    if todo:
        from .borderless import attach_borderless
        attach_borderless(data, doc, todo)


# --------------------------------------------------------------------------
# JATS structured table cells — same canonical shape as the LaTeX path.
# --------------------------------------------------------------------------

def _jats_table_cells(node, paper_id: str, source: str, section: str, cpath: str, strip):
    """Parse a <table-wrap>/<table> into structured_table shape from the XML grid
    (<tr>/<th>/<td> with @colspan/@rowspan). Falls back to PDF for THIS table when
    there is no <table> grid (image-only table-wrap)."""
    cap_el = node.find(".//{*}caption")
    caption = " ".join(x.strip() for x in (cap_el.itertext() if cap_el is not None else []) if x.strip())
    grid = node if strip(node.tag) == "table" else node.find(".//{*}table")
    tid = f"{paper_id}:{cpath}"
    if grid is None:
        return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                representation="jats_xml", section=section, caption=caption,
                                cells=[], parse_status="fallback_pdf",
                                fallback="table-wrap_has_no_xml_grid")
    rows = [tr for tr in grid.iter() if strip(tr.tag) == "tr"]
    if len(rows) < 2:
        return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                representation="jats_xml", section=section, caption=caption,
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
    span_trouble = 0
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
                            representation="jats_xml", section=section, caption=caption,
                            cells=cells, parse_status=status,
                            fallback=None if cells else "no_data_cells_after_parse")


# --------------------------------------------------------------------------
# arXiv LaTeX e-print -> blocks (+ structured table cells).  CONTENT ONLY.
# --------------------------------------------------------------------------

_TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_TEX_SECTION_RE = re.compile(r"\\(sub){0,2}section\*?\s*(?:\[[^\]]*\])?\s*\{")
# Strip only environments whose body is NOT prose: tables (emitted as structured
# blocks), figures (caption emitted separately), and code/verbatim dumps. Keep
# algorithm / equation / align bodies — they carry method + result terms that the
# extractor needs; _tex_prose linearises them.
_TEX_FLOAT_RE = re.compile(
    r"\\begin\{(table\*?|figure\*?|sidewaystable|wrapfigure|"
    r"tabular\*?|tabularx|array|longtable|lstlisting|verbatim|minted|"
    r"tikzpicture|filecontents\*?)\}.*?\\end\{\1\}", re.S)
_TEX_FIGCAP_RE = re.compile(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", re.S)
_TEX_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.S)
# citation/label/ref macros: drop macro AND its {arg} (leaving the key leaks noise)
_TEX_CITEREF_RE = re.compile(
    r"\\(?:cite[a-zA-Z]*|[Cc]ref|[Cc]refrange|ref|eqref|autoref|pageref|label|"
    r"nocite|bibliography|bibliographystyle|url|href|includegraphics|input|include|"
    r"usepackage|documentclass|newcommand|renewcommand|def|newif|setlength)\*?"
    r"\s*(?:\[[^\]]*\])?\s*(?:\{[^{}]*\})?", re.I)
_TEX_CMD_RE = re.compile(r"\\[a-zA-Z@]+\*?(?:\s*\[[^\]]*\])?")


def _tex_prose(s: str) -> str:
    # PARITY: prose numerics ($...$, \num{}, x\pm y, sub/superscripts) must survive
    # too (Phase-4b M1: prose verbatim-lax was 0.688 vs PDF 0.982). Route through
    # the numeric-preserving cleaner, not the lossy cell cleaner.
    from .latex_tables import _numeric_verbatim
    s = _TEX_CITEREF_RE.sub(" ", s)
    return _numeric_verbatim(s)


def _match_brace_local(s: str, i: int) -> int:
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def blocks_from_latex(latex: bytes | str, paper_id: str, source: str,
                      pdf_data: bytes | None = None) -> list[dict[str, Any]]:
    """Section/paragraph blocks + STRUCTURED table blocks from arXiv e-print source.

    Every `table` block carries `table_cells` (canonical structured_table shape).
    A table whose tabular env will not parse is marked
    `table_parse_status="fallback_pdf"` and, when the paired arXiv PDF is
    available, its PyMuPDF table text is attached as the fallback content for
    THAT table (recorded in `table_fallback`). Partial success per paper is fine.
    """
    from .latex_tables import parse_latex_tables

    s = latex.decode("utf-8", "replace") if isinstance(latex, bytes) else latex
    s = _TEX_COMMENT_RE.sub("", s)
    cursor = {"blocks": [], "pos": 0}
    out: list[dict[str, Any]] = []

    def emit(section, node, btype, text, **extra):
        b = _mk(paper_id, source, REPR_LATEX, section, node, btype, text, cursor)
        b.update(extra)
        out.append(b); cursor["blocks"].append(b); cursor["pos"] = b["char_end"]
        return b

    m = _TEX_ABSTRACT_RE.search(s)
    if m:
        ab,txt = "abstract", _tex_prose(m.group(1))
        if txt:
            emit("abstract", "tex/abstract", "abstract", txt)

    doc_m = re.search(r"\\begin\s*\{document\}", s)
    if doc_m:
        body = s[doc_m.end():]
    else:
        # \begin{document} lives in an \input we could not resolve — drop the
        # preamble by starting at the first sectioning command so the walk below
        # does not treat \usepackage/\newcommand lines as prose.
        first_sec = _TEX_SECTION_RE.search(s)
        body = s[first_sec.start():] if first_sec else s
    end_m = re.search(r"\\end\s*\{document\}", body)
    if end_m:
        body = body[:end_m.start()]
    body = _TEX_ABSTRACT_RE.sub("\n\n", body)   # already emitted above; don't re-walk as prose

    # --- tables (structured) ---
    tables = parse_latex_tables(body, paper_id, source)
    for t in tables:
        t["section"] = _canon_section(t["section"] or "body", default=(t["section"] or "body")[:40].lower())
    pdf_tables = None
    if any(t["parse_status"] == "fallback_pdf" for t in tables) and pdf_data:
        try:
            pdf_tables = [b for b in blocks_from_pdf(pdf_data, paper_id, "arxiv")
                          if b["block_type"] == "table"]
        except Exception:  # noqa: BLE001
            pdf_tables = []

    def _pdf_fallback_text(caption: str) -> tuple[str, str]:
        if not pdf_data:
            return "", "pdf_unavailable"
        if not pdf_tables:
            return "", "no_pdf_table_blocks"
        cap_tok = set(re.findall(r"[a-z0-9]+", caption.lower()))
        best, best_ov = None, 0
        for pb in pdf_tables:
            ov = len(cap_tok & set(re.findall(r"[a-z0-9]+", pb["text"][:200].lower())))
            if ov > best_ov:
                best, best_ov = pb, ov
        if best and best_ov >= 2:
            return best["text"], f"pdf_block:{best['block_id']}"
        return (pdf_tables[0]["text"], "pdf_block:unmatched_first") if pdf_tables else ("", "no_pdf_table_match")

    for t in tables:
        # FIELD ROUTING (Phase-4b Task 2): what the EXTRACTOR sees (block `text`)
        # is caption + the linearised "row / col = value" cells — model-legible.
        # The full verbatim cell dump (`raw_text`, pipe-separated tokens) is NOT
        # in `text`; it stays on `table_raw_text`, read by the parity gate and by
        # Phase 5's structural binding. Structured `cells` unchanged.
        raw = t.get("raw_text") or ""
        lin = " ; ".join(f"{c['row_label']} / {c['column_header']} = {c['value']}"
                         for c in t["cells"])
        parts = [p for p in (t["caption"], lin) if p]
        fb_note = t["fallback"]
        if not lin:                                   # structural parse produced no cells
            fb_text, fb_ref = _pdf_fallback_text(t["caption"])
            if fb_text:
                parts.append(fb_text)                 # readable PDF table text as the fallback
            elif raw:
                parts.append(raw)                     # last resort: the verbatim dump
            fb_note = f"{t['fallback']} -> {fb_ref if fb_text else 'raw_text'}"
        txt = "  ||  ".join(parts) or "[table — unparsed, no content recovered]"
        emit(t["section"], t["table_id"], "table", txt,
             table_cells=t["cells"], table_parse_status=t["parse_status"],
             table_caption=t["caption"], table_raw_text=raw,
             table_fallback=fb_note, table_notes=t.get("notes"))

    # --- figure captions ---
    for fm in _TEX_FIGCAP_RE.finditer(body):
        cm = re.search(r"\\caption\*?\s*(?:\[[^\]]*\])?\s*\{", fm.group(2))
        if cm:
            close = _match_brace_local(fm.group(2), cm.end() - 1)
            if close > 0:
                cap = _tex_prose(fm.group(2)[cm.end():close])
                if cap:
                    emit("body", f"{paper_id}:fig{fm.start()}", "figure_caption", cap)

    # --- section headings + prose (floats stripped so table text isn't duplicated) ---
    prose_stream = _TEX_FLOAT_RE.sub("\n\n", body)
    pos, cur_section = 0, "body"
    for sm in _TEX_SECTION_RE.finditer(prose_stream):
        seg = prose_stream[pos:sm.start()]
        for para in re.split(r"\n\s*\n", seg):
            txt = _tex_prose(para)
            if len(txt.split()) >= 8:
                emit(cur_section, f"tex/{cur_section}", "paragraph", txt)
        close = _match_brace_local(prose_stream, sm.end() - 1)
        if close < 0:
            pos = sm.end(); continue
        title = _tex_prose(prose_stream[sm.end():close])
        cur_section = _canon_section(title, default=title[:40].lower() or "body")
        emit(cur_section, f"tex/{cur_section}", "heading", title or cur_section)
        pos = close + 1
    for para in re.split(r"\n\s*\n", prose_stream[pos:]):
        txt = _tex_prose(para)
        if len(txt.split()) >= 8:
            emit(cur_section, f"tex/{cur_section}", "paragraph", txt)

    return out


def build_document(acq_record: dict[str, Any], data: bytes | None,
                   fallback_abstract: str | None = None) -> dict[str, Any]:
    """Canonical document = ordered provenance-bearing blocks + summary stats."""
    pid = acq_record["paper_id"]
    source = acq_record.get("source") or "none"
    rep = acq_record.get("representation_type")
    blocks: list[dict[str, Any]] = []
    if data is not None and rep == REPR_LATEX:
        pdf_fb = acq_record.get("latex_pdf_fallback_bytes")
        blocks = blocks_from_latex(data, pid, source, pdf_data=pdf_fb)
    elif data is not None and rep == REPR_JATS:
        blocks = blocks_from_jats(data, pid, source)
    elif data is not None and rep == REPR_PDF:
        blocks = blocks_from_pdf(data, pid, source)
    elif fallback_abstract:
        blocks = [{
            "block_id": f"{pid}:0", "paper_id": pid, "source": "semantic_scholar",
            "representation": "abstract", "section": "abstract", "subsection": None,
            "page_or_node": "metadata/abstract", "block_type": "abstract",
            "char_start": 0, "char_end": len(fallback_abstract), "text": fallback_abstract.strip(),
        }]
    sections = sorted({b["section"] for b in blocks})
    tbl = [b for b in blocks if b["block_type"] == "table"]
    return {
        "paper_id": pid,
        "representation": rep if blocks and rep in (REPR_JATS, REPR_LATEX, REPR_PDF) else "abstract",
        "source": source,
        "n_blocks": len(blocks),
        "sections_present": sections,
        "has_results_section": "results" in sections,
        "has_method_section": "method" in sections,
        "total_words": sum(len(b["text"].split()) for b in blocks),
        "n_tables": len(tbl),
        "n_tables_structured": sum(1 for b in tbl if b.get("table_cells")),
        "n_tables_fallback_pdf": sum(1 for b in tbl if b.get("table_parse_status") == "fallback_pdf"),
        "blocks": blocks,
    }
