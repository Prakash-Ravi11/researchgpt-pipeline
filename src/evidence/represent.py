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
`table_fallback`. PDF table blocks do not (that is the bindability loss).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
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
    doc.close()
    return out


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
