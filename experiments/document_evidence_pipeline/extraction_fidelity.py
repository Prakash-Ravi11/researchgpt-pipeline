"""Measure numeric-value survival: structured full text (arXiv LaTeX / JATS) vs
our real Stage-2 PDF path. Read-only w.r.t. the pipeline — imports and runs
`src.processing.pdf_parser.process_paper_grounded` (the real grounded Stage 2)
and `process_paper` (the legacy default). Does NOT touch acquisition or the gate.

  python experiments/document_evidence_pipeline/extraction_fidelity.py --step all
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.processing.pdf_parser import process_paper_grounded, process_paper  # noqa: E402

ACQ = HERE / "runs" / "20260901T165648Z-acqverify-3b2b" / "acquisition_records.json"
PDFDIR = HERE / "runs" / "prodab-20260902T004416Z" / "canonical" / "pdfs"
OUT = HERE / "runs" / "extraction_fidelity"
EPRINT = OUT / "eprint"
UA = {"User-Agent": "researchgpt-extraction-fidelity/1.0 (mailto:researchgpt-benchmark@example.org)"}

# the number-anchored gate's rule: a decimal, or a >=2-digit integer
NUMVAL = re.compile(r"\d+\.\d+|\b\d{2,}\b")
YEARISH = re.compile(r"\b(19|20)\d{2}\b")


def _pairs() -> list[dict]:
    recs = json.loads(ACQ.read_text(encoding="utf-8"))
    out = []
    for r in recs:
        if r["status"] != "FULL_TEXT":
            continue
        pid = r["paper_id"]
        oi = r.get("other_identifiers") or {}
        pdf = PDFDIR / f"{pid}.pdf"
        xml = PDFDIR / f"{pid}.xml"
        if oi.get("ArXiv") and pdf.exists():
            out.append({"paper_id": pid, "kind": "arxiv_latex", "arxiv": oi["ArXiv"],
                        "pdf": str(pdf), "pages": r["content_validation"]["metrics"].get("pdf_pages")})
        elif xml.exists():
            out.append({"paper_id": pid, "kind": "jats", "xml": str(xml), "pdf": None})
    return out


# ---------------------------------------------------------------------------
# STEP 1 — fetch arXiv e-print (LaTeX) source
# ---------------------------------------------------------------------------
def step1(pairs: list[dict]) -> list[dict]:
    EPRINT.mkdir(parents=True, exist_ok=True)
    got = []
    for p in pairs:
        if p["kind"] != "arxiv_latex":
            p["latex_status"] = "n/a (jats)"
            got.append(p)
            continue
        aid = p["arxiv"]
        dest = EPRINT / f"{aid}.blob"
        if not dest.exists():
            try:
                r = requests.get(f"https://arxiv.org/e-print/{aid}", headers=UA, timeout=60)
                r.raise_for_status()
                dest.write_bytes(r.content)
                time.sleep(3.1)  # arXiv politeness
            except requests.RequestException as exc:
                p["latex_status"] = f"download_failed: {type(exc).__name__}"
                got.append(p)
                continue
        tex = _extract_tex(dest.read_bytes())
        if not tex:
            p["latex_status"] = "no_tex_in_source (PDF-only upload?)"
        else:
            (EPRINT / f"{aid}.tex").write_text(tex, encoding="utf-8", errors="replace")
            p["latex_status"] = "ok"
            p["tex_chars"] = len(tex)
        got.append(p)
    return got


def _extract_tex(blob: bytes) -> str:
    # arXiv e-print is usually a gzipped tar; sometimes a single gzipped .tex
    body = blob
    try:
        body = gzip.decompress(blob)
    except OSError:
        pass
    try:
        tf = tarfile.open(fileobj=io.BytesIO(body if body is not blob else blob))
        parts = []
        for m in tf.getmembers():
            if m.isfile() and m.name.lower().endswith(".tex"):
                f = tf.extractfile(m)
                if f:
                    parts.append(f"% ==== {m.name} ====\n" + f.read().decode("utf-8", "replace"))
        return "\n\n".join(parts)
    except tarfile.TarError:
        # single-file source
        txt = body.decode("utf-8", "replace")
        return txt if "\\begin{document}" in txt or "\\documentclass" in txt else ""


# ---------------------------------------------------------------------------
# STEP 2 — numeric ground truth from the structured representation
# ---------------------------------------------------------------------------
_SECT_RE = re.compile(r"\\(?:sub)*section\*?\{([^}]{0,80})\}")
_ENVS_TABLE = ("tabular", "tabularx", "table", "table*", "longtable", "threeparttable")


def _latex_sections(tex: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1).strip()) for m in _SECT_RE.finditer(tex)]


def _section_at(sections, pos: str) -> str:
    cur = "preamble/abstract"
    for start, name in sections:
        if start <= pos:
            cur = name
        else:
            break
    return cur


def _strip_comments(tex: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", ln) for ln in tex.splitlines())


def numbers_from_latex(tex: str) -> list[dict]:
    tex = _strip_comments(tex)
    sections = _latex_sections(tex)
    # mark spans that are tables / captions
    table_spans, caption_spans = [], []
    for env in _ENVS_TABLE:
        for m in re.finditer(r"\\begin\{" + re.escape(env) + r"\}(.*?)\\end\{" + re.escape(env) + r"\}", tex, re.DOTALL):
            table_spans.append((m.start(), m.end()))
    for m in re.finditer(r"\\caption\*?\{", tex):
        # balanced-ish: take up to the matching brace within 1500 chars
        s = m.end(); depth = 1; i = s
        while i < len(tex) and i < s + 2000 and depth:
            if tex[i] == "{": depth += 1
            elif tex[i] == "}": depth -= 1
            i += 1
        caption_spans.append((m.start(), i))

    def where(pos: int) -> str:
        for a, b in caption_spans:
            if a <= pos < b:
                return "caption"
        for a, b in table_spans:
            if a <= pos < b:
                return "table"
        return "prose"

    # zones to ignore: \cite \ref \label \eqref \citep \citet \bibitem \includegraphics \url \href \arXiv ids \newcommand
    ignore = []
    for m in re.finditer(r"\\(?:cite[a-z]*|ref|label|eqref|autoref|bibitem|includegraphics|url|href|input|include|newcommand|renewcommand|def|arxiv|doi)\b[^{]*\{[^}]*\}", tex, re.I):
        ignore.append((m.start(), m.end()))
    for m in re.finditer(r"arXiv:\d{4}\.\d{4,5}", tex):
        ignore.append((m.start(), m.end()))

    def ignored(pos: int) -> bool:
        return any(a <= pos < b for a, b in ignore)

    seen = set()
    out = []
    for m in NUMVAL.finditer(tex):
        val = m.group(0)
        pos = m.start()
        if ignored(pos):
            continue
        ctx = tex[max(0, pos - 140): pos + 140]
        ctx = re.sub(r"\s+", " ", ctx).strip()
        # drop obvious citation years: a bare 19xx/20xx sitting next to a name/paren/comma cite
        if YEARISH.fullmatch(val) and re.search(r"(19|20)\d{2}[a-z]?\)|\bet al\.|, (19|20)\d{2}", ctx):
            continue
        w = where(pos)
        key = (val, ctx[:60])
        if key in seen:
            continue
        seen.add(key)
        # nearby metric / dataset hint
        metric = _hint(ctx, _METRIC_WORDS)
        dataset = _hint(ctx, _DATASET_WORDS)
        out.append({"value": val, "location": w, "section": _section_at(sections, pos),
                    "context": ctx, "metric_hint": metric, "dataset_hint": dataset})
    return out


_METRIC_WORDS = re.compile(
    r"\b(accuracy|precision|recall|f1|f-?score|dice|iou|auc|auroc|bleu|rouge|meteor|mae|rmse|mse|"
    r"mrr|ndcg|map|exact match|em|correlation|pearson|spearman|kappa|sensitivity|specificity|"
    r"score|rate|error|loss|latency|throughput|faithfulness|perplexity|hit@|recall@|precision@|p@|r@)\b", re.I)
_DATASET_WORDS = re.compile(
    r"\b(dataset|benchmark|corpus|test set|train(?:ing)? set|validation set|split|"
    r"[A-Z][A-Za-z0-9\-]{2,}(?:Bench|QA|Eval|Set))\b")


def _hint(ctx: str, rx: re.Pattern) -> str | None:
    m = rx.search(ctx)
    return m.group(0) if m else None


def _jats_numbers(xml_path: str) -> list[dict]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(Path(xml_path).read_bytes())

    def strip(t): return t.split("}")[-1]
    out, seen = [], set()

    def walk(el, section, in_table, in_caption):
        tag = strip(el.tag)
        sec = section
        if tag == "sec":
            te = el.find("./{*}title")
            if te is not None:
                sec = "".join(te.itertext()).strip()[:80] or section
        it = in_table or tag in ("table-wrap", "table", "array")
        ic = in_caption or tag in ("caption",)
        text = "".join(el.itertext())
        for m in NUMVAL.finditer(text):
            val = m.group(0); pos = m.start()
            ctx = re.sub(r"\s+", " ", text[max(0, pos - 140):pos + 140]).strip()
            if YEARISH.fullmatch(val) and re.search(r"\bet al\.|, (19|20)\d{2}", ctx):
                continue
            key = (val, ctx[:60])
            if key in seen:
                continue
            seen.add(key)
            loc = "caption" if ic else ("table" if it else "prose")
            out.append({"value": val, "location": loc, "section": sec, "context": ctx,
                        "metric_hint": _hint(ctx, _METRIC_WORDS), "dataset_hint": _hint(ctx, _DATASET_WORDS)})
        # element-level itertext double counts; instead recurse on children only for structure,
        # but we already scanned full text at this node — so only scan LEAF-ish nodes:
        # simpler: clear out and re-walk children for section/table context, dedupe handles repeats
        for ch in list(el):
            walk(ch, sec, it, ic)

    # to avoid the ancestor-includes-descendant text double scan, walk only leaf paragraphs/cells
    out.clear(); seen.clear()

    def walk2(el, section, in_table, in_caption):
        tag = strip(el.tag)
        sec = section
        if tag == "sec":
            te = el.find("./{*}title")
            if te is not None:
                sec = ("".join(te.itertext()).strip()[:80]) or section
        it = in_table or tag in ("table-wrap", "table", "array", "tbody", "thead", "tr", "td", "th")
        ic = in_caption or tag in ("caption", "title") and in_table
        children = list(el)
        if not children:
            text = "".join(el.itertext())
            for m in NUMVAL.finditer(text):
                val = m.group(0); pos = m.start()
                ctx = re.sub(r"\s+", " ", text[max(0, pos - 140):pos + 140]).strip()
                if YEARISH.fullmatch(val) and re.search(r"\bet al\.|, (19|20)\d{2}", ctx):
                    continue
                key = (val, ctx[:60], sec)
                if key in seen:
                    continue
                seen.add(key)
                loc = "caption" if in_caption else ("table" if it else "prose")
                out.append({"value": val, "location": loc, "section": sec, "context": ctx,
                            "metric_hint": _hint(ctx, _METRIC_WORDS), "dataset_hint": _hint(ctx, _DATASET_WORDS)})
        for ch in children:
            walk2(ch, sec, it, in_caption or tag == "caption")

    body = root.find(".//{*}body") or root
    walk2(body, "body", False, False)
    return out


def step2(pairs: list[dict]) -> list[dict]:
    for p in pairs:
        if p["kind"] == "arxiv_latex" and p.get("latex_status") == "ok":
            tex = (EPRINT / f"{p['arxiv']}.tex").read_text(encoding="utf-8", errors="replace")
            p["ground_truth"] = numbers_from_latex(tex)
        elif p["kind"] == "jats":
            p["ground_truth"] = _jats_numbers(p["xml"])
        else:
            p["ground_truth"] = []
        p["gt_count"] = len(p["ground_truth"])
        p["gt_by_loc"] = dict(Counter(g["location"] for g in p["ground_truth"]))
    return pairs


# ---------------------------------------------------------------------------
# STEP 3 — survival through the real Stage-2 PDF path
# ---------------------------------------------------------------------------
def _stage2_chunks(pair: dict, grounded: bool) -> list[dict]:
    paper = {"paperId": pair["paper_id"], "title": "", "year": None, "venue": "",
             "has_full_text": True, "pdf_path": pair["pdf"],
             "representation_type": "pdf", "pdf_source": "arxiv",
             "acquisition_status": "FULL_TEXT", "abstract": ""}
    if grounded:
        return process_paper_grounded(paper)
    return process_paper(paper, chunk_size=800, overlap=100)


def step3(pairs: list[dict]) -> list[dict]:
    for p in pairs:
        if not p["pdf"] or not p["ground_truth"]:
            p["survival"] = None
            continue
        g_chunks = _stage2_chunks(p, grounded=True)
        l_chunks = _stage2_chunks(p, grounded=False)
        g_text = "\n".join(c["text"] for c in g_chunks)
        l_text = "\n".join(c["text"] for c in l_chunks)

        rows = []
        for gt in p["ground_truth"]:
            v = gt["value"]
            gt_words = {w for w in re.findall(r"[a-z]{4,}", gt["context"].lower())}
            # a number is "meaningful" (results-relevant) if it sits in a table/caption
            # OR its prose context names a metric or a dataset
            meaningful = gt["location"] in ("table", "caption") or bool(gt.get("metric_hint")) \
                or bool(gt.get("dataset_hint"))
            in_l = v in l_text
            # strict verbatim: the value AND >=1 significant word from its structured
            # context must appear in the SAME grounded chunk (kills coincidental
            # string matches like a table cell "3.1" hitting section "3.1")
            in_g = False
            hit_chunk = None
            for c in g_chunks:
                if v in c["text"]:
                    if in_g is False:
                        in_g = True  # lax verbatim (string present anywhere)
                    cw = set(re.findall(r"[a-z]{4,}", c["text"].lower()))
                    if not gt_words or (gt_words & cw):
                        hit_chunk = c
                        break
            prov = bool(hit_chunk) and bool(hit_chunk.get("section")) and bool(hit_chunk.get("page_or_node"))
            ctx_ok = False
            if hit_chunk:
                idx = hit_chunk["text"].find(v)
                win = hit_chunk["text"][max(0, idx - 90): idx + 90]
                needles = [x for x in (gt.get("metric_hint"), gt.get("dataset_hint")) if x]
                ctx_ok = (bool(needles) and any(n.lower() in win.lower() for n in needles)) \
                    or bool(_METRIC_WORDS.search(win)) or bool(_DATASET_WORDS.search(win))
            rows.append({**gt, "meaningful": meaningful,
                         "in_grounded_pdf": in_g, "in_grounded_pdf_strict": bool(hit_chunk),
                         "in_legacy_pdf": in_l,
                         "provenance_ok": prov, "context_bindable": bool(in_g and ctx_ok),
                         "hit_section": (hit_chunk or {}).get("section"),
                         "hit_page": (hit_chunk or {}).get("page_or_node"),
                         "hit_block_type": (hit_chunk or {}).get("block_type"),
                         "hit_window": (hit_chunk["text"][max(0, hit_chunk["text"].find(v) - 90):
                                                          hit_chunk["text"].find(v) + 90] if hit_chunk else "")})
        p["survival_rows"] = rows
        p["survival"] = _agg(rows)
        p["grounded_chunk_count"] = len(g_chunks)
        p["grounded_sections"] = sorted({c.get("section") for c in g_chunks})
    return pairs


def _agg(rows: list[dict]) -> dict:
    def rate(sub, key):
        return (round(sum(1 for r in sub if r[key]) / len(sub), 3)) if sub else None
    m = [r for r in rows if r["meaningful"]]  # results-relevant subset

    def block(sub):
        return {"n": len(sub),
                "verbatim_lax": rate(sub, "in_grounded_pdf"),
                "verbatim_strict": rate(sub, "in_grounded_pdf_strict"),
                "with_provenance": rate([r for r in sub if r["in_grounded_pdf_strict"]], "provenance_ok"),
                "context_bindable": rate(sub, "context_bindable"),
                "verbatim_legacy": rate(sub, "in_legacy_pdf")}
    return {
        "n_all": len(rows), "n_meaningful": len(m),
        "ALL": block(rows),
        "MEANINGFUL": block(m),
        "MEANINGFUL_table": block([r for r in m if r["location"] == "table"]),
        "MEANINGFUL_caption": block([r for r in m if r["location"] == "caption"]),
        "MEANINGFUL_prose": block([r for r in m if r["location"] == "prose"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["1", "2", "3", "all"], default="all")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = _pairs()
    print(f"candidate pairs: {len(pairs)}  ({Counter(p['kind'] for p in pairs)})")
    pairs = step1(pairs)
    print("STEP 1 latex_status:", Counter(p.get("latex_status") for p in pairs))
    if args.step in ("2", "3", "all"):
        pairs = step2(pairs)
        usable = [p for p in pairs if p["gt_count"] > 0 and (p["pdf"] or p["kind"] == "jats")]
        print(f"STEP 2 usable pairs (gt>0): {len(usable)}")
        for p in pairs:
            print(f"  {p['paper_id'][:12]} {p['kind']:12} {p.get('latex_status','?'):28} gt={p['gt_count']:4} {p.get('gt_by_loc')}")
    if args.step in ("3", "all"):
        pairs = step3(pairs)
    (OUT / "fidelity.json").write_text(json.dumps(pairs, indent=2), encoding="utf-8")
    done = [p for p in pairs if p.get("survival")]
    print(f"\nSTEP 3 measured pairs: {len(done)}")
    pool = {loc: Counter() for loc in ("all", "table", "caption", "prose")}
    for p in done:
        s = p["survival"]
        M, MT, MP = s["MEANINGFUL"], s["MEANINGFUL_table"], s["MEANINGFUL_prose"]
        print(f"  {p['paper_id'][:12]} meaningful n={M['n']:4} strict-vb={M['verbatim_strict']} "
              f"prov={M['with_provenance']} bindable={M['context_bindable']} | "
              f"TABLE n={MT['n']:3} vb={MT['verbatim_strict']} bind={MT['context_bindable']} | "
              f"PROSE n={MP['n']:3} vb={MP['verbatim_strict']} bind={MP['context_bindable']}")
        for r in p["survival_rows"]:
            if not r["meaningful"]:
                continue
            for key in ("all", r["location"]):
                c = pool[key]
                c["n"] += 1
                c["vb_lax"] += r["in_grounded_pdf"]
                c["vb_strict"] += r["in_grounded_pdf_strict"]
                c["bind"] += r["context_bindable"]
                c["legacy"] += r["in_legacy_pdf"]
    print("\n== POOLED (meaningful numeric values, {} paired papers) ==".format(len(done)))
    for k, c in pool.items():
        if not c["n"]:
            continue
        n = c["n"]
        print(f"  {k:8} n={n:5}  verbatim_lax={c['vb_lax']/n:.3f}  verbatim_strict={c['vb_strict']/n:.3f}  "
              f"context_bindable={c['bind']/n:.3f}  legacy_path_verbatim={c['legacy']/n:.3f}")
    (OUT / "pooled.json").write_text(json.dumps({k: dict(v) for k, v in pool.items()}, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'fidelity.json'}")


if __name__ == "__main__":
    main()
