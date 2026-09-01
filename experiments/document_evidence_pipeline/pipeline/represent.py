"""P1/P2 - canonical document representation + provenance-bearing blocks.

One code path, two front-ends:
  * JATS XML -> section/paragraph hierarchy with XML node paths
  * PDF      -> PyMuPDF text blocks with page numbers + heuristic section labels

Output block schema (every downstream evidence item traces to one of these):
  {block_id, paper_id, source, representation, section, subsection,
   page_or_node, block_type, char_start, char_end, text}
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from .schema import REPR_JATS, REPR_PDF

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


def build_document(acq_record: dict[str, Any], data: bytes | None,
                   fallback_abstract: str | None = None) -> dict[str, Any]:
    """Canonical document = ordered provenance-bearing blocks + summary stats."""
    pid = acq_record["paper_id"]
    source = acq_record.get("source") or "none"
    rep = acq_record.get("representation_type")
    blocks: list[dict[str, Any]] = []
    if data is not None and rep == REPR_JATS:
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
    return {
        "paper_id": pid,
        "representation": rep if blocks and rep in (REPR_JATS, REPR_PDF) else "abstract",
        "source": source,
        "n_blocks": len(blocks),
        "sections_present": sections,
        "has_results_section": "results" in sections,
        "has_method_section": "method" in sections,
        "total_words": sum(len(b["text"].split()) for b in blocks),
        "blocks": blocks,
    }
