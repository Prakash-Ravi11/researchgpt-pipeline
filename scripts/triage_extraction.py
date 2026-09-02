"""
Extraction triage for the UI-observed corpus (data/).  MEASUREMENT ONLY.

Answers: for full-text papers where the PDF was acquired but text fields came
back empty, where does the information disappear?  Per-document and per-page
signals -> representation class -> bucket (A1/A2/M/B/C/D) -> trace B/M/D only.

Third corpus = whatever is in data/raw_metadata/collected_papers.json now.
Never merged with the frozen-60 or data_test/ numbers.

Run:  .venv/Scripts/python.exe scripts/triage_extraction.py
Full rows -> experiments/document_evidence_pipeline/runs/extraction_triage/
Report is written by hand from the printed aggregates + the on-disk rows.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
import pymupdf  # noqa: E402

OUT = ROOT / "experiments/document_evidence_pipeline/runs/extraction_triage"
OUT.mkdir(parents=True, exist_ok=True)

CFG = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))
PATHS = CFG["paths"]
LLM = {**CFG["llm"], "temperature": 0, "seed": 42}  # Phase-1 seeded path, not production defaults
PROC = ROOT / PATHS["processed_dir"]
PDF_DIR = ROOT / PATHS["pdf_dir"]

TEXT_FIELDS = ["summary", "problem_addressed", "method", "datasets", "metrics",
               "results", "key_findings", "limitations", "inferences", "novelty_claim"]
MISSING_CORE = ["method", "datasets", "metrics", "results", "limitations"]

# ---- thresholds (fixed, not tuned; rationale in the report) -------------------
DENSITY_LOW = 400          # chars/page below this = suspicious (dense 2-col ~2.5-5k, eqn-heavy ~0.8-2k)
IMG_PAGE_FRAC = 0.30       # an image covering >=30% of a page area is a "large image region"
IMG_DOMINATES = 0.55       # >=55% page area in images = image-dominated page
NEAR_MARGIN = 24.0         # pt; text within this of an image bbox counts as "adjacent"
NEAR_TEXT_LOW = 200        # <200 adjacent chars on an image-dominated page = table-as-image suspect

RESULT_HEADING_RE = re.compile(
    r"\b(results?|experiments?|evaluation|ablation|performance|comparison|findings)\b", re.I)
SECTION_HEADS = {
    "method": re.compile(r"\b(method(s|ology)?|approach|proposed method|architecture|model|network|framework)\b", re.I),
    "datasets": re.compile(r"\b(dataset|datasets|data set|benchmark|corpus|training data|materials)\b", re.I),
    "metrics": re.compile(r"\b(metric|metrics|evaluation metric|dice|iou|accuracy|f1|auc|sensitivity|specificity|hausdorff)\b", re.I),
    "results": re.compile(r"\b(results?|experiments?|evaluation|ablation|quantitative)\b", re.I),
    "limitations": re.compile(r"\b(limitation|limitations|discussion|future work|threats to validity)\b", re.I),
}


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def page_signals(page) -> dict:
    """chars, image-region count/area, adjacent-text chars for one page."""
    d = page.get_text("dict")
    pw, ph = page.rect.width, page.rect.height
    page_area = max(pw * ph, 1.0)
    text_spans = []   # (bbox, nchars)
    img_bboxes = []
    for b in d.get("blocks", []):
        if b.get("type") == 1:  # image block
            img_bboxes.append(pymupdf.Rect(b["bbox"]))
        else:
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    t = sp.get("text", "")
                    if t.strip():
                        text_spans.append((pymupdf.Rect(sp["bbox"]), len(t)))
    total_chars = sum(n for _, n in text_spans)
    # union area of image regions (approx: sum, capped at page area)
    img_area = 0.0
    big_regions = 0
    for r in img_bboxes:
        a = max(r.get_area(), 0.0)
        img_area += a
        if a / page_area >= IMG_PAGE_FRAC:
            big_regions += 1
    img_area_frac = min(img_area / page_area, 1.0)
    # chars adjacent to any image region
    near = 0
    if img_bboxes:
        expanded = [pymupdf.Rect(r.x0 - NEAR_MARGIN, r.y0 - NEAR_MARGIN,
                                 r.x1 + NEAR_MARGIN, r.y1 + NEAR_MARGIN) for r in img_bboxes]
        for sbox, n in text_spans:
            if any(not (sbox & ex).is_empty for ex in expanded):
                near += n
    return {
        "chars": total_chars,
        "image_region_count": len(img_bboxes),
        "image_big_region_count": big_regions,
        "image_area_fraction": round(img_area_frac, 3),
        "chars_near_image_regions": near,
        "text_raw": page.get_text().strip(),
    }


def classify_representation(pages: list[dict], rep_type: str | None, arxiv: bool) -> tuple[str, str]:
    if rep_type == "jats_xml":
        return "STRUCTURED", "jats_xml representation"
    if not pages:
        return "UNKNOWN", "no pages read"
    n = len(pages)
    empties = sum(1 for p in pages if not p["text_raw"])
    tot_chars = sum(p["chars"] for p in pages)
    cpp = tot_chars / n
    img_dom_pages = sum(1 for p in pages if p["image_area_fraction"] >= IMG_DOMINATES)
    if empties == n:
        return "IMAGE_ONLY", f"text layer empty on all {n} pages"
    if cpp < DENSITY_LOW and (img_dom_pages / n) >= 0.5:
        return "IMAGE_ONLY", f"cpp {cpp:.0f} < {DENSITY_LOW} AND {img_dom_pages}/{n} pages image-dominated"
    # mixed: healthy text overall but some image-dominated pages with little adjacent text
    tbl_img_pages = [p["page_no"] for p in pages
                     if p["image_area_fraction"] >= IMG_DOMINATES and p["chars_near_image_regions"] < NEAR_TEXT_LOW]
    if cpp >= DENSITY_LOW and tbl_img_pages:
        return "MIXED", f"cpp {cpp:.0f} ok but pages {tbl_img_pages} image-dominated w/ <{NEAR_TEXT_LOW} adjacent chars"
    if cpp >= DENSITY_LOW:
        return "BORN_DIGITAL_TEXT", f"cpp {cpp:.0f}, {n - empties}/{n} pages with text"
    return "UNKNOWN", f"cpp {cpp:.0f} < {DENSITY_LOW}, {img_dom_pages}/{n} img-dominated (need 2nd signal, none)"


def bucket(doc_row: dict, pages: list[dict]) -> tuple[str, str]:
    rep = doc_row["representation"]
    chars = doc_row["extracted_chars"]
    n = doc_row["pages"] or 1
    cpp = doc_row["chars_per_page"]
    chunks = doc_row["chunk_count"]
    embeds = doc_row["embedding_count"]
    empties = sum(1 for p in pages if not p["text_raw"])
    # A1: no text layer anywhere
    if pages and empties == len(pages):
        return "A1", "page.get_text() empty on every page"
    # A2: low density but a text layer exists (>=2 signals: low cpp + image-dominated majority)
    img_dom = sum(1 for p in pages if p["image_area_fraction"] >= IMG_DOMINATES)
    if cpp < DENSITY_LOW and img_dom >= max(1, len(pages) // 2):
        return "A2", f"cpp {cpp:.0f} < {DENSITY_LOW} AND {img_dom}/{len(pages)} pages image-dominated (text layer present)"
    # M: healthy text but table-as-image pages
    tbl_img_pages = [p["page_no"] for p in pages
                     if p["image_area_fraction"] >= IMG_DOMINATES and p["chars_near_image_regions"] < NEAR_TEXT_LOW]
    if cpp >= DENSITY_LOW and tbl_img_pages:
        in_results_zone = [pn for pn in tbl_img_pages
                           if pn >= 0.35 * len(pages)
                           or RESULT_HEADING_RE.search(pages[pn - 1]["text_raw"][:400] if pn - 1 < len(pages) else "")]
        return "M", f"table-as-image pages {tbl_img_pages}; in results zone: {in_results_zone or 'none'}"
    # B: text present but ~no chunks
    if chars > 3000 and chunks <= 1:
        return "B", f"{chars} extracted chars but chunk_count={chunks} (Stage-2 processing/reference-cut)"
    if chunks >= 1 and embeds >= 1 and chars > 500:
        return "C", "text + chunks + embeddings present; loss is downstream"
    return "D", f"chars={chars} chunks={chunks} embeds={embeds} cpp={cpp:.0f}"


def main() -> None:
    papers = load_json(ROOT / PATHS["raw_metadata_dir"] / "collected_papers.json") \
        if (ROOT / PATHS["raw_metadata_dir"]).is_dir() else load_json(Path(PATHS["raw_metadata_dir"]) / "collected_papers.json")
    papers = load_json(ROOT / "data/raw_metadata/collected_papers.json")
    summaries = {r["paper_id"]: r for r in load_json(PROC / "paper_summaries.json")}
    chunks_all = load_json(PROC / "chunks.json")
    chunk_count = Counter(c["paper_id"] for c in chunks_all)
    figman = load_json(PROC / "figures_manifest.json")

    # embedding counts from chroma
    embed_count: dict[str, int] = defaultdict(int)
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(ROOT / PATHS["chroma_dir"]))
        col = None
        want = CFG.get("system", {}).get("collection_name")
        for c in client.list_collections():
            if c.name == want:
                col = client.get_collection(c.name)
        if col is None and client.list_collections():
            col = client.get_collection(client.list_collections()[0].name)
        if col is not None:
            got = col.get(include=["metadatas"])
            for m in got.get("metadatas", []) or []:
                pid = (m or {}).get("paper_id")
                if pid:
                    embed_count[pid] += 1
        print(f"chroma collection: {col.name if col else None}  total vectors: {sum(embed_count.values())}")
    except Exception as e:
        print(f"chroma read failed: {e!r}")

    doc_rows, page_rows = [], []
    for p in papers:
        pid = p["paperId"]
        s = summaries.get(pid, {})
        fields_returned = [f for f in TEXT_FIELDS if s.get(f) not in (None, "", [], {})]
        rep_type = p.get("representation_type")
        arxiv = p.get("pdf_source") == "arxiv"
        pdf_path = PDF_DIR / f"{pid}.pdf"
        pages_sig: list[dict] = []
        pages = 0
        extracted_chars = 0
        read_err = ""
        if p.get("has_full_text") and pdf_path.exists():
            try:
                d = pymupdf.open(pdf_path)
                pages = d.page_count
                for i in range(pages):
                    ps = page_signals(d[i])
                    ps["page_no"] = i + 1
                    pages_sig.append(ps)
                d.close()
                extracted_chars = len("\n".join(x["text_raw"] for x in pages_sig))
            except Exception as e:
                read_err = repr(e)
        cpp = (sum(x["chars"] for x in pages_sig) / pages) if pages else 0.0
        rep, rep_why = classify_representation(pages_sig, rep_type, arxiv)
        if read_err:
            rep, rep_why = "UNKNOWN", f"pdf open failed: {read_err}"
        row = {
            "paper_id": pid,
            "has_full_text": p.get("has_full_text"),
            "pdf_source": p.get("pdf_source"),
            "arxiv_latex_available": arxiv,
            "pages": pages,
            "extracted_chars": extracted_chars,
            "chars_per_page": round(cpp, 1),
            "chunk_count": chunk_count.get(pid, 0),
            "embedding_count": embed_count.get(pid, 0),
            "figure_count": len(figman.get(pid, [])),
            "fields_returned": len(fields_returned),
            "fields_list": "|".join(fields_returned),
            "missing_core": "|".join(f for f in MISSING_CORE if f not in fields_returned),
            "representation": rep,
            "representation_why": rep_why,
        }
        if p.get("has_full_text") and pdf_path.exists() and not read_err:
            row["bucket"], row["bucket_why"] = bucket(row, pages_sig)
        elif not p.get("has_full_text"):
            row["bucket"], row["bucket_why"] = "ABS", "abstract-only, no PDF (not a full-text failure)"
        else:
            row["bucket"], row["bucket_why"] = "D", f"has_full_text but pdf missing/err: {read_err or 'no file'}"
        doc_rows.append(row)
        for ps in pages_sig:
            page_rows.append({"paper_id": pid, **{k: ps[k] for k in
                              ("page_no", "chars", "image_region_count", "image_big_region_count",
                               "image_area_fraction", "chars_near_image_regions")}})

    # ---- write full rows to disk -------------------------------------------------
    with (OUT / "per_doc.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(doc_rows[0].keys()))
        w.writeheader()
        w.writerows(doc_rows)
    with (OUT / "per_page.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(page_rows[0].keys()))
        w.writeheader()
        w.writerows(page_rows)
    (OUT / "per_doc.json").write_text(json.dumps(doc_rows, indent=2), encoding="utf-8")

    # ---- aggregates -----------------------------------------------------------
    ft = [r for r in doc_rows if r["has_full_text"]]
    print(f"\n=== corpus: {len(doc_rows)} papers  |  full-text: {len(ft)}  |  abstract-only: {len(doc_rows) - len(ft)}")
    print("\nrepresentation (full-text only):", dict(Counter(r["representation"] for r in ft)))
    print("bucket (full-text only):        ", dict(Counter(r["bucket"] for r in ft)))
    print("arxiv-latex-available (FT):     ", sum(1 for r in ft if r["arxiv_latex_available"]))
    print(f"\nfull-text papers with fields_returned == 0 : {sum(1 for r in ft if r['fields_returned'] == 0)}")
    print(f"full-text papers with fields_returned <= 2 : {sum(1 for r in ft if r['fields_returned'] <= 2)}")

    print("\n-- full-text papers, sorted by fields_returned --")
    print(f"{'paper_id':12} {'bkt':4} {'rep':17} pg  chars  cpp   ch emb fig  flds  missing_core")
    for r in sorted(ft, key=lambda x: x["fields_returned"]):
        print(f"{r['paper_id'][:12]:12} {r['bucket']:4} {r['representation']:17} "
              f"{r['pages']:>2} {r['extracted_chars']:>6} {r['chars_per_page']:>6.0f} "
              f"{r['chunk_count']:>3} {r['embedding_count']:>3} {r['figure_count']:>3}  "
              f"{r['fields_returned']:>3}   {r['missing_core']}")

    # per-page image-region hotspots for M / A2 candidates
    print("\n-- pages with image_area_fraction >= %.2f (potential table-as-image / scan) --" % IMG_DOMINATES)
    hot = defaultdict(list)
    for pr in page_rows:
        if pr["image_area_fraction"] >= IMG_DOMINATES:
            hot[pr["paper_id"]].append((pr["page_no"], pr["image_area_fraction"], pr["chars_near_image_regions"]))
    for pid, lst in hot.items():
        print(f"  {pid[:12]}: " + ", ".join(f"p{pn}(af={af},near={nr})" for pn, af, nr in lst))

    print(f"\nrows written -> {OUT}")
    # trace list for STEP 4
    trace = [r["paper_id"] for r in ft if r["bucket"] in ("B", "M", "D")]
    (OUT / "trace_ids.json").write_text(json.dumps(trace), encoding="utf-8")
    print("STEP-4 trace ids (buckets B/M/D):", [t[:12] for t in trace])


if __name__ == "__main__":
    main()
