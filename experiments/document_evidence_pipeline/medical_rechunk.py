"""3.3a/3.3b STEP 1 — re-chunk the medical corpus with the grounded, provenance-aware
chunker (same one used for the canonical corpus + data_test) and VERIFY the re-chunk
actually produced structure before any measurement.

Isolated: reads data/raw_metadata/collected_papers.json (the 50 medical papers), writes
ONLY under experiments/document_evidence_pipeline/runs/medical_rechunk/. data/processed/
is not touched.

  python -u experiments/document_evidence_pipeline/medical_rechunk.py
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.processing.pdf_parser import process_paper_grounded  # noqa: E402

OUT = Path(__file__).resolve().parent / "runs" / "medical_rechunk" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
META = ROOT / "data" / "raw_metadata" / "collected_papers.json"
OLD_CHUNKS = ROOT / "data" / "processed" / "chunks.json"

RESULTS_SECTIONS = {"results", "experimental_setup", "discussion"}


def main() -> int:
    papers = json.loads(META.read_text(encoding="utf-8"))
    ft = [p for p in papers if p.get("has_full_text")]
    print(f"medical corpus: {len(papers)} papers, {len(ft)} full-text\n")

    all_chunks: list[dict] = []
    per_paper: list[dict] = []
    for p in papers:
        recs = process_paper_grounded(p)
        all_chunks.extend(recs)
        if p.get("has_full_text"):
            bt = Counter(c["block_type"] for c in recs)
            secs = Counter(c["section"] for c in recs)
            per_paper.append({
                "paper_id": p["paperId"][:12],
                "title": (p.get("title") or "")[:60],
                "n_chunks": len(recs),
                "representation": recs[0]["representation"] if recs else "EMPTY",
                "block_types": dict(bt),
                "sections": dict(secs),
                "has_table_block": bt.get("table", 0) > 0,
                "n_table_blocks": bt.get("table", 0),
                "has_results_heading": any(s in RESULTS_SECTIONS for s in secs),
                "results_sections_present": sorted(s for s in secs if s in RESULTS_SECTIONS),
            })

    (OUT / "chunks.json").write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")

    # ---- STEP 1 report ----
    ft_chunks = [c for c in all_chunks if c["has_full_text"]]
    print("=" * 72)
    print("STEP 1 — structure verification (19 full-text papers)")
    print("=" * 72)
    print(f"\nblock_type counts (full-text chunks, n={len(ft_chunks)}):")
    for k, v in Counter(c["block_type"] for c in ft_chunks).most_common():
        print(f"  {k:16} {v}")

    sec_counts = Counter(c["section"] for c in ft_chunks)
    print(f"\nsection value counts (full-text chunks), {len(sec_counts)} distinct:")
    for k, v in sec_counts.most_common():
        print(f"  {str(k):28} {v}")
    JUNK = {"body", "", None}
    junk = sum(v for k, v in sec_counts.items() if k in JUNK)
    print(f"  -> junk/unparsed ('body'/empty): {junk} / {len(ft_chunks)} "
          f"({junk/len(ft_chunks):.0%})")

    print(f"\nper-paper (19 full-text):")
    print(f"  {'paper':14}{'chunks':>7}{'repr':>7}{'tbl':>5}  {'results-heading':<22} title")
    n_with_table = n_with_results = 0
    for r in per_paper:
        n_with_table += r["has_table_block"]
        n_with_results += r["has_results_heading"]
        print(f"  {r['paper_id']:14}{r['n_chunks']:>7}{r['representation']:>7}"
              f"{r['n_table_blocks']:>5}  {str(r['results_sections_present']):<22} {r['title']}")

    print(f"\n  papers with >=1 `table` block:            {n_with_table} / 19")
    print(f"  papers with a recognised results heading: {n_with_results} / 19")

    total_table = sum(r["n_table_blocks"] for r in per_paper)
    print(f"\n  total `table` blocks across corpus: {total_table}")
    if total_table <= 3:
        print("\n  *** STOP CONDITION MET: `table` blocks are near zero across the corpus. ***")
        print("  The PyMuPDF caption-prefix heuristic ('Table ' at block start) cannot")
        print("  identify tables in these publisher-typeset clinical PDFs. content_aware")
        print("  would run WITHOUT falling back yet perform no better than legacy.")
        print("  This is a Stage-2 parsing finding — report it before 3.3c.")
    else:
        print(f"\n  table blocks present on {n_with_table} papers — re-chunk produced table structure.")

    # ---- chunk count old vs new ----
    old = json.loads(OLD_CHUNKS.read_text(encoding="utf-8"))
    old_papers = len({c["paper_id"] for c in old})
    print("\n" + "=" * 72)
    print("chunk count: old (legacy schema) vs new (grounded)")
    print("=" * 72)
    print(f"  old: {len(old)} chunks / {old_papers} papers")
    print(f"  new: {len(all_chunks)} chunks / {len({c['paper_id'] for c in all_chunks})} papers "
          f"({len(ft_chunks)} full-text chunks, {len(all_chunks)-len(ft_chunks)} abstract)")
    print(f"\n  wrote {OUT / 'chunks.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
