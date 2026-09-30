"""Post-fix evaluation, step 1 -- deterministic harvest of CANDIDATE natural-language claim -> table pairs from the
30 hash-pinned PDFs. The output is the input of the blind labelling pass; it is NOT gold.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/postfix_mine_claims.py <out_dir>

Rules, fixed before any labelling or evaluation:
  text      page.get_text("text") per page. A line break becomes a space, except after a hyphen (hyphen kept, no
            space); whitespace collapsed. Sentences split at [.!?] + whitespace + capital/bracket/quote, never after a
            listed abbreviation (et al., e.g., Fig., Tab., Eq., vs., ...).
  claim     a sentence that references a table ("Table 3", "Tables 2 and 3", "Tab. 2", "TABLE IV"), is not itself a
            caption (sentence starting "Table 3:" / "Table 3." / "TABLE IV" + capital), lies before the References
            heading, and carries a meaningful number (src.evidence.anchors.NUMERIC_ANCHOR_RE) once table / figure /
            equation / section references, bracketed citations and 4-digit years are masked out.
  table     the page(s) holding a text block whose first line is that table's caption (same shape as
            represent._PDF_CAPTION_RE with the table number fixed).
  context   a sentence with no table / figure reference whose immediately preceding sentence on the same page
            references exactly one table is also a candidate for that table (reference = "contextual"; the
            preceding sentence is recorded as context_sentence). Same number rule.
  kept      at least one claim number occurs as a whole token on a table page outside the claim sentence itself.
Nothing here calls find_tables, the binder or the gate. Page renders (170 dpi) and table-page text layers are
written next to candidates.json for the labellers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from src.evidence.anchors import NUMERIC_ANCHOR_RE  # noqa: E402

MANIFEST = HERE / "pdf_identity_manifest_v2.csv"
DPI = 170
_ABBREV = re.compile(r"(?:\bet al|\be\.g|\bi\.e|\bvs|\bFigs?|\bTabs?|\bEqs?|\betc|\bNo|\bRef|\bSec|\bapprox|\bresp|\bcf|"
                     r"\bDr|\bSt|\bFig|\bTab)\.$", re.I)
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(“\"])")
_LABEL = r"(?:\d+|[IVXL]+)"
_TABREF = re.compile(rf"\b(?:Tables?|TABLES?|Tab\.)\s*({_LABEL}(?:\s*(?:,|and|&|or|–|-)\s*{_LABEL})*)\b")
_CAPTION_START = re.compile(rf"^\s*(?:Table|TABLE|Tab\.)\s*{_LABEL}\s*(?:[.:]|$|\s+[A-Z(\[])")
_MASK = re.compile(rf"\b(?:Tables?|TABLES?|Tab\.|Fig(?:ure)?s?\.?|FIG(?:URE)?S?\.?|Eqs?\.?|Equations?|Sec(?:tion)?s?\.?|"
                   rf"Algorithm|Appendix)\s*\(?{_LABEL}(?:\s*(?:,|and|&|–|-)\s*{_LABEL})*\)?|\[[\d,\s–-]+\]|\b(?:19|20)\d\d\b")
_REFS = re.compile(r"^\s*(?:\d+\.?\s*|[IVX]+\.?\s*)?(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*$", re.M)


def norm_text(raw: str) -> str:
    return " ".join(re.sub(r"-\n\s*", "-", raw).split())


def sentences(text: str) -> list[str]:
    out: list[str] = []
    for s in _SPLIT.split(text):
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {s}"
        else:
            out.append(s)
    return [s.strip() for s in out if s.strip()]


def token_count(v: str, text: str) -> int:
    return len(re.findall(r"(?<![\d.])" + re.escape(v) + r"(?![\d])", text))


def caption_pages(doc) -> dict[str, list[int]]:
    pages: dict[str, list[int]] = defaultdict(list)
    for pno, page in enumerate(doc, start=1):
        for b in page.get_text("blocks"):
            first = (b[4] or "").strip().splitlines()[0] if (b[4] or "").strip() else ""
            m = re.match(rf"^\s*(?:Table|TABLE|Tab\.)\s*({_LABEL})\s*(?:[.:]|$|\s+[A-Z(\[])", first)
            if b[6] == 0 and m and pno not in pages[m.group(1)]:
                pages[m.group(1)].append(pno)
    return dict(pages)


def harvest_paper(pid: str, path: Path) -> tuple[list[dict], dict]:
    doc = pymupdf.open(path)
    raw_pages = [p.get_text("text") for p in doc]
    stop_page, stop_at = len(raw_pages) + 1, None
    for i, raw in enumerate(raw_pages, start=1):
        m = _REFS.search(raw)
        if m and i > 1:
            stop_page, stop_at = i, norm_text(raw[:m.start()])
            break
    caps = caption_pages(doc)
    page_text = {i: norm_text(r) for i, r in enumerate(raw_pages, start=1)}
    stats = defaultdict(int)
    out, seen = [], set()
    for pno in range(1, len(raw_pages) + 1):
        if pno > stop_page:
            break
        text = stop_at if pno == stop_page else page_text[pno]
        prev_refs, prev = [], ""
        for s in sentences(text):
            refs = sorted({x for m in _TABREF.finditer(s) for x in re.findall(_LABEL, m.group(1))}, key=lambda x: (len(x), x))
            reference, context = "explicit", None
            if not refs:
                if len(prev_refs) == 1 and not re.search(r"\b(?:Fig(?:ure)?s?|FIG(?:URE)?S?)\.?\s*\d", s):
                    refs, reference, context = prev_refs, "contextual", prev
                prev_refs, prev = [], s
                if not refs:
                    continue
            else:
                prev_refs, prev = refs, s
                stats["table_reference_sentences"] += 1
                if _CAPTION_START.match(s):
                    stats["caption_sentences_skipped"] += 1
                    prev_refs = []
                    continue
            nums = list(dict.fromkeys(NUMERIC_ANCHOR_RE.findall(_MASK.sub(" ", s))))
            if not nums:
                stats[f"{reference}:no_meaningful_number"] += 1
                continue
            tpages = {r: caps.get(r, []) for r in refs}
            found = {v: {str(tp): token_count(v, page_text[tp]) - (token_count(v, s) if tp == pno else 0)
                         for r in refs for tp in tpages[r]} for v in nums}
            found = {v: {tp: n for tp, n in d.items() if n > 0} for v, d in found.items()}
            if not any(found.values()):
                stats[f"{reference}:no_number_on_a_table_page"] += 1
                continue
            if (pid, s) in seen:
                stats["duplicate_sentence"] += 1
                continue
            seen.add((pid, s))
            stats[f"kept_{reference}"] += 1
            out.append({"paper_id": pid, "claim_page": pno, "claim_text": s, "reference": reference,
                        "context_sentence": context, "table_refs": refs, "table_pages": tpages, "numbers": nums,
                        "numbers_on_table_pages": {v: d for v, d in found.items() if d}})
    doc.close()
    stats["kept"] = len(out)
    return out, dict(stats)


def main(out_dir: Path) -> None:
    pymupdf.TOOLS.mupdf_display_errors(False)
    out_dir.mkdir(parents=True, exist_ok=True)
    man = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    cands, stats = [], {}
    for r in man:
        path = Path(r["canonical_pdf_path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != r["sha256"]:
            sys.exit(f"PDF hash mismatch for {r['paper_id']} -- nothing written")
        c, st = harvest_paper(r["paper_id"], path)
        cands += c
        stats[r["paper_id"]] = st
    for i, c in enumerate(cands, start=1):
        c["candidate_id"] = f"C{i:03d}"
    renders = defaultdict(set)
    for c in cands:
        renders[c["paper_id"]].add(c["claim_page"])
        for pages in c["table_pages"].values():
            renders[c["paper_id"]].update(pages)
    paths = {r["paper_id"]: Path(r["canonical_pdf_path"]) for r in man}
    table_pages = {(c["paper_id"], p) for c in cands for ps in c["table_pages"].values() for p in ps}
    for pid, pages in renders.items():
        doc = pymupdf.open(paths[pid])
        for p in sorted(pages):
            doc[p - 1].get_pixmap(dpi=DPI).save(out_dir / f"{pid}_p{p}.png")
            if (pid, p) in table_pages:
                (out_dir / f"{pid}_p{p}.txt").write_text(doc[p - 1].get_text("text"), encoding="utf-8")
        doc.close()
    (out_dir / "candidates.json").write_text(json.dumps({"rules": __doc__, "per_paper_stats": stats, "candidates": cands},
                                                        indent=1, ensure_ascii=False), encoding="utf-8")
    tot = defaultdict(int)
    for st in stats.values():
        for k, v in st.items():
            tot[k] += v
    print(f"candidates: {len(cands)} from {len({c['paper_id'] for c in cands})} papers | totals {dict(tot)}")
    print("per paper kept:", {p: s.get("kept", 0) for p, s in stats.items()})


if __name__ == "__main__":
    main(Path(sys.argv[1]))
