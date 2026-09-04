"""Stage 1 integration measure — re-acquire the 50-paper medical corpus through
the canonical five-source resolver (S2 + arXiv + OpenAlex + Europe PMC + Crossref).

Isolated: copies the medical metadata into runs/medical_reacquire/ and points the
resolver there; data/raw_metadata/ and data/pdfs/ are NOT touched. Acquisition
only — no extraction. arXiv LaTeX e-print ingestion stays disabled.

  python -u experiments/document_evidence_pipeline/medical_reacquire_measure.py
"""
from __future__ import annotations
import json, shutil, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.collection.semantic_scholar import re_acquire_corpus  # noqa: E402

SRC_META = ROOT / "data" / "raw_metadata" / "collected_papers.json"
OUT = HERE / "runs" / "medical_reacquire"
META_DIR = OUT / "raw_metadata"
PDF_DIR = OUT / "pdfs"


def main() -> int:
    META_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC_META, META_DIR / "collected_papers.json")
    papers_before = json.loads((META_DIR / "collected_papers.json").read_text(encoding="utf-8"))
    n = len(papers_before)
    ft_before = sum(1 for p in papers_before if p.get("has_full_text"))
    ext_before = Counter()
    for p in papers_before:
        eids = p.get("externalIds") or {}
        ext_before["PMC"] += bool(eids.get("PubMedCentral"))
        ext_before["ArXiv"] += bool(eids.get("ArXiv"))
        ext_before["DOI"] += bool(eids.get("DOI"))

    cfg = {
        "paths": {"raw_metadata_dir": str(META_DIR), "pdf_dir": str(PDF_DIR)},
        "collection": {"contact_email": None},
        "evidence_grounding": {"latex_ingestion_enabled": False},
    }
    papers = re_acquire_corpus(cfg)

    # ---- report ----
    ft_after = sum(1 for p in papers if p.get("has_full_text"))
    reps = Counter(p.get("representation_type") for p in papers if p.get("has_full_text"))
    src = Counter(p.get("pdf_source") for p in papers if p.get("has_full_text"))
    status = Counter(p.get("acquisition_status") for p in papers)
    jats = [p for p in papers if p.get("representation_type") == "jats_xml"]

    print("\n" + "=" * 68)
    print("MEDICAL CORPUS RE-ACQUISITION — canonical five-source resolver")
    print("=" * 68)
    print(f"\nidentifiers present: {dict(ext_before)}  (of {n})")
    print(f"\nfull-text coverage:  {ft_before}/{n} ({ft_before/n:.0%})  ->  "
          f"{ft_after}/{n} ({ft_after/n:.0%})     (baseline 19/50 = 38%)")
    print(f"acquisition_status:  {dict(status)}")
    print(f"\nrepresentation distribution (full-text only):")
    print(f"  JATS (jats_xml) : {reps.get('jats_xml', 0)}")
    print(f"  PDF (pdf)       : {reps.get('pdf', 0)}")
    print(f"  abstract-only   : {n - ft_after}")
    print(f"\nper-source contribution (accepted full text):")
    for s in ("semantic_scholar", "arxiv", "openalex", "europepmc", "crossref", "unpaywall"):
        print(f"  {s:16} {src.get(s, 0)}")
    other = {k: v for k, v in src.items() if k not in
             ("semantic_scholar", "arxiv", "openalex", "europepmc", "crossref", "unpaywall")}
    if other:
        print(f"  other            {other}")

    # identity validation — wrong-paper accepted MUST be 0
    accepted = [p for p in papers if p.get("has_full_text")]
    bad_identity = [p for p in accepted if not (p.get("identity_validation") or {}).get("passed")]
    sims = sorted((p.get("identity_validation") or {}).get("signals", {}).get("title_similarity", 0.0)
                  for p in accepted)
    print(f"\nidentity validation:")
    print(f"  full-text papers with identity_validation.passed == False (wrong-paper accepted): {len(bad_identity)}")
    print(f"  title_similarity of accepted papers: min {sims[0]:.2f} / median "
          f"{sims[len(sims)//2]:.2f} / max {sims[-1]:.2f}" if sims else "  (none accepted)")

    # content rejections
    rej = Counter()
    rej_examples = []
    for p in papers:
        for c in (p.get("acquisition_candidates") or []):
            if c.get("content_passed") is False:
                r = str(c.get("content_reason") or "?").split(":")[0]
                rej[r] += 1
                if len(rej_examples) < 12:
                    rej_examples.append((p["paperId"][:10], c.get("source"), c.get("content_reason")))
    print(f"\ncontent rejections ({sum(rej.values())} candidate fetches rejected on content):")
    for r, k in rej.most_common():
        print(f"  {r:36} {k}")
    for pid, s, reason in rej_examples:
        print(f"    [{pid}] {s:14} {reason}")

    print("\n" + "=" * 68)
    print(f"THE NUMBER THAT MATTERS: medical papers now with JATS = {len(jats)}")
    print(f"  (Phase-5 structural binding can be validated on {len(jats)} medical JATS "
          f"papers, vs 2 in the canonical corpus.)")
    print("=" * 68)
    for p in jats:
        eids = p.get("externalIds") or {}
        print(f"  {p['paperId'][:12]}  PMC{eids.get('PubMedCentral')}  "
              f"identity={((p.get('identity_validation') or {}).get('signals') or {}).get('title_similarity')}  "
              f"{(p.get('title') or '')[:70]}")

    (OUT / "reacquire_summary.json").write_text(json.dumps({
        "n": n, "ft_before": ft_before, "ft_after": ft_after,
        "representation": dict(reps), "by_source": dict(src), "status": dict(status),
        "jats_count": len(jats), "wrong_paper_accepted": len(bad_identity),
        "content_rejections": dict(rej),
    }, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
