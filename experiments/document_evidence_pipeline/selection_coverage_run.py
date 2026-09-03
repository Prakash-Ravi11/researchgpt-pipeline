"""Extraction coverage: legacy selector vs content_aware @ {10,15} on the frozen-60
canonical 34 full-text papers (primary), Phase-1 seeded path.  data_test (8) and the
medical corpus (19) are REGRESSION checks only — reported, never averaged in.

Reports:
  - non-empty extracted fields / paper, and per field (Method/Dataset/Metric/Result/Limitations)
  - acquisition coverage vs extraction coverage
  - field-presence determinability: determinable-present / determinable-absent / undeterminable
    (structured rep only); coverage-when-present computed ONLY over determinable-present

  python experiments/document_evidence_pipeline/selection_coverage_run.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml  # noqa: E402
from src.summarization import summarize as S  # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers  # noqa: E402

OUT = HERE / "runs" / "selection_policy"
OUT.mkdir(parents=True, exist_ok=True)
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)
CORE = ["method", "datasets", "metrics", "results", "limitations"]
LLM = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b",
       "timeout_seconds": 300, "temperature": 0, "seed": 42, "max_context_words": 2500}

_HEAD = {
    "method": re.compile(r"^\s*(\d+\.?\s+)?(materials?\s+and\s+methods?|methods?|methodology|proposed\s+method|approach|experimental\s+setup)\b", re.I | re.M),
    "datasets": re.compile(r"(\bdataset\b|\bbenchmark\b|\bcorpus\b|\bstudy\s+population\b|\bparticipants\b|\bcohort\b|\bdata\s+collection\b)", re.I),
    "metrics": re.compile(r"(\bevaluation\s+metrics?\b|\bnDCG\b|\bBLEU\b|\bROUGE\b|\bF1\b|\baccuracy\b|\bdice\b|\bAUC\b|\brecall@\d\b|\bMRR\b)", re.I),
    "results": re.compile(r"^\s*(\d+\.?\s+)?(results?|experiments?\s+and\s+results?|experimental\s+results?|evaluation|findings)\b", re.I | re.M),
    "limitations": re.compile(r"(\blimitations?\b|\bfuture\s+work\b|\bthreats\s+to\s+validity\b|^\s*(\d+\.?\s+)?discussion\b)", re.I | re.M),
}


def nef(rec):
    out = []
    for f in FLAT:
        v = rec.get(f)
        if f in ("datasets", "metrics"):
            if isinstance(v, list) and any(str(x).strip() for x in v):
                out.append(f)
        elif str(v or "").strip():
            out.append(f)
    return out


def cfg_for(processed_dir, chroma_dir, collection, mode, budget):
    return {
        "paths": {"processed_dir": str(processed_dir), "chroma_dir": str(chroma_dir)},
        "embedding": {"model": "BAAI/bge-m3", "device": "cuda"},
        "system": {"collection_name": collection},
        "selection": {"mode": mode, "max_passages": budget} if mode == "content_aware" else {"mode": "legacy"},
    }


def run_variant(tag, processed_dir, chroma_dir, collection, mode, budget, ids, structured_ids):
    papers_all = build_retrieval_aware_papers(cfg_for(processed_dir, chroma_dir, collection, mode, budget), 2500)
    papers = {p: papers_all[p] for p in ids if p in papers_all}
    t0 = time.time()
    res = S.extract_paper_fields(dict(papers), dict(LLM), cache={}, processed_dir=None)
    dt = time.time() - t0

    rows = []
    for pid in papers:
        r = res[pid]
        rows.append({"paper_id": pid, "fields": nef(r), "n": len(nef(r)),
                     "conformance": r.get("_conformance"), "variant": r.get("_domain_variant"),
                     "structured": pid in structured_ids,
                     "has_field": {f: bool(f in nef(r)) for f in CORE}})
    (OUT / f"cov_{tag}.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    n = len(rows)
    print(f"\n== {tag}  (n={n}, {dt:.0f}s, {dt/max(n,1):.0f}s/paper) ==")
    print(f"  mean non-empty fields/paper: {sum(r['n'] for r in rows)/n:.2f}")
    print(f"  conformance: {dict(Counter(r['conformance'] for r in rows))}")
    print(f"  per-field non-empty (all n={n}):")
    for f in CORE:
        got = sum(r['has_field'][f] for r in rows)
        print(f"    {f:12} {got}/{n}  ({got/n:.0%})")
    # coverage-when-present, ONLY over determinable-present (structured rep)
    det = [r for r in rows if r["structured"]]
    print(f"  determinable (structured rep): {len(det)}/{n}")
    return rows


def main():
    cfg = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))
    # ---- canonical (frozen-60), 34 full-text papers ----
    CANON = HERE / "runs/prodab-20260902T004416Z/canonical"
    chunks = json.loads((CANON / "processed/chunks.json").read_text(encoding="utf-8"))
    canon_meta = json.loads((CANON / "raw_metadata/collected_papers.json").read_text(encoding="utf-8"))
    ft_ids = sorted({c["paper_id"] for c in chunks if c.get("has_full_text")})
    reps = {(m.get("paperId") or m.get("paper_id")): (m.get("representation_type") or "") for m in canon_meta}
    structured = {pid for pid in ft_ids if reps.get(pid) in ("jats_xml", "latex")}
    # also count structured by chunk representation
    chunk_rep = {}
    for c in chunks:
        chunk_rep.setdefault(c["paper_id"], set()).add(c.get("representation"))
    structured |= {pid for pid in ft_ids if "jats_xml" in chunk_rep.get(pid, set())}

    print(f"CANONICAL full-text papers: {len(ft_ids)}   structured (JATS/LaTeX): {len(structured)}")
    print("acquisition coverage = full-text / all = "
          f"{len(ft_ids)}/{len({c['paper_id'] for c in chunks})}")

    all_rows = {}
    all_rows["legacy"] = run_variant("canon_legacy", CANON / "processed", CANON / "chroma_db",
                                     "researchgpt_papers", "legacy", None, ft_ids, structured)
    all_rows["ca10"] = run_variant("canon_ca10", CANON / "processed", CANON / "chroma_db",
                                   "researchgpt_papers", "content_aware", 10, ft_ids, structured)
    all_rows["ca15"] = run_variant("canon_ca15", CANON / "processed", CANON / "chroma_db",
                                   "researchgpt_papers", "content_aware", 15, ft_ids, structured)

    # per-field, per-variant, with structured-only denominator
    print("\n== EXTRACTION COVERAGE per field — canonical ==")
    print(f"{'field':12} {'legacy':>16} {'ca@10':>16} {'ca@15':>16}   (structured-only: present/n)")
    det_ids = structured
    for f in CORE:
        cells = []
        for key in ("legacy", "ca10", "ca15"):
            rows = all_rows[key]
            allc = sum(r['has_field'][f] for r in rows)
            detc = sum(r['has_field'][f] for r in rows if r["paper_id"] in det_ids)
            cells.append(f"{allc}/{len(rows)} | {detc}/{len(det_ids)}")
        print(f"{f:12} {cells[0]:>16} {cells[1]:>16} {cells[2]:>16}")

    # ---- regression checks (reported, not averaged) ----
    dt_cfg = yaml.safe_load((ROOT / "configs/staging_config.yaml").read_text(encoding="utf-8"))
    dt_proc = ROOT / dt_cfg["paths"]["processed_dir"]
    dt_ids = sorted({c["paper_id"] for c in json.loads((dt_proc / "chunks.json").read_text(encoding="utf-8"))})
    dt_before = {r["paper_id"]: len(nef(r)) for r in json.loads((dt_proc / "paper_summaries.json").read_text(encoding="utf-8"))}
    dt_rows = run_variant("datatest_ca10", dt_proc, ROOT / dt_cfg["paths"]["chroma_dir"],
                          dt_cfg["system"]["collection_name"], "content_aware", 10, dt_ids, set())
    dt_reg = [(r["paper_id"][:10], dt_before.get(r["paper_id"], 0), r["n"])
              for r in dt_rows if r["n"] < dt_before.get(r["paper_id"], 0)]
    print(f"\ndata_test regression (ca@10 vs on-disk): {dt_reg or 'NONE'}")

    med_proc = ROOT / "data/processed"
    med_ids = sorted({c["paper_id"] for c in json.loads((med_proc / "chunks.json").read_text(encoding="utf-8"))
                      if c.get("has_full_text")})
    med_before = {r["paper_id"]: len(nef(r)) for r in json.loads((med_proc / "paper_summaries.json").read_text(encoding="utf-8"))}
    med_rows = run_variant("medical_ca10", med_proc, ROOT / "data/chroma_db",
                           "researchgpt_papers", "content_aware", 10, med_ids, set())
    med_reg = [(r["paper_id"][:10], med_before.get(r["paper_id"], 0), r["n"])
               for r in med_rows if r["n"] < med_before.get(r["paper_id"], 0)]
    print(f"medical regression (ca@10 vs on-disk; NOT averaged): "
          f"{len(med_reg)} papers dropped -> {med_reg}")

    (OUT / "coverage_summary.json").write_text(json.dumps(
        {"canonical_mean": {k: round(sum(r['n'] for r in v)/len(v), 2) for k, v in all_rows.items()},
         "data_test_regressions": dt_reg, "medical_regressions": med_reg}, indent=2), encoding="utf-8")
    print(f"\nrows -> {OUT}")


if __name__ == "__main__":
    main()
