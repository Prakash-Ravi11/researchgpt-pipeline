"""3.2b + 3.2c measurement.  Canonical 34 full-text papers, content_aware@10, seeded,
clean cache, WITH the fixed output reservation (num_predict 768 / num_ctx term) and the
conformance circuit breaker active.  data_test (8) as a regression check.  Medical: only
the now-visible legacy-schema fallback count.

  python -u experiments/document_evidence_pipeline/context_budget_measure.py
"""
from __future__ import annotations
import json, sys, time
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

COV = HERE / "runs" / "selection_policy"
OUT = HERE / "runs" / "context_budget"
OUT.mkdir(parents=True, exist_ok=True)
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)
CORE = ["method", "datasets", "metrics", "results", "limitations"]
LLM = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "timeout_seconds": 300,
       "temperature": 0, "seed": 42, "max_context_words": 2500,
       "extraction_deadline_seconds": 240, "extraction_output_reservation": 768}


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


def cfg_for(processed, chroma, coll, budget):
    return {"paths": {"processed_dir": str(processed), "chroma_dir": str(chroma)},
            "embedding": {"model": "BAAI/bge-m3", "device": "cuda"},
            "system": {"collection_name": coll}, "llm": LLM,
            "selection": {"mode": "content_aware", "max_passages": budget}}


def run(tag, processed, chroma, coll, ids):
    cfg = cfg_for(processed, chroma, coll, 10)
    papers_all = build_retrieval_aware_papers(cfg, 2500)
    papers = {p: papers_all[p] for p in ids if p in papers_all}
    t0 = time.time()
    ext = S.extract_paper_fields(dict(papers), dict(LLM), cache={}, processed_dir=None)
    ext = S._apply_selection_circuit_breaker(cfg, ext, 2500)
    dt = time.time() - t0
    schema_fb = S._legacy_schema_fallback_count(str(processed))
    rows = [{"paper_id": p, "n": len(nef(ext[p])), "fields": nef(ext[p]),
             "conformance": ext[p].get("_conformance"), "variant": ext[p].get("_domain_variant"),
             "selection_fallback": bool(ext[p].get("_selection_fallback")),
             "extraction_failed": bool(ext[p].get("_extraction_failed")),
             "failure_reason": ext[p].get("_failure_reason")} for p in papers]
    (OUT / f"{tag}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    n = len(rows)
    cb_fb = [r["paper_id"] for r in rows if r["selection_fallback"]]
    with_fb_mean = sum(r["n"] for r in rows) / n
    wo = [r for r in rows if not r["selection_fallback"]]
    wo_mean = (sum(r["n"] for r in wo) / len(wo)) if wo else None
    print(f"\n== {tag}  n={n}  runtime {dt:.0f}s ({dt/n:.0f}s/paper) ==")
    print(f"  circuit-breaker fallbacks: {len(cb_fb)} {[p[:10] for p in cb_fb]}")
    print(f"  legacy-schema fallbacks:   {schema_fb}")
    print(f"  mean non-empty fields/paper: {with_fb_mean:.2f}  (excluding fallen-back papers: "
          f"{wo_mean:.2f} over n={len(wo)})" if wo_mean is not None else f"  mean {with_fb_mean:.2f}")
    print(f"  conformance: {dict(Counter(r['conformance'] for r in rows))}")
    print(f"  extraction_failed: {sum(r['extraction_failed'] for r in rows)} "
          f"{[(r['paper_id'][:10], r['failure_reason']) for r in rows if r['extraction_failed']]}")
    for f in CORE:
        g = sum(1 for r in rows if f in r["fields"])
        print(f"    {f:12} {g}/{n} ({g/n:.0%})")
    return rows


def main():
    CANON = HERE / "runs/prodab-20260902T004416Z/canonical"
    ch = json.loads((CANON / "processed/chunks.json").read_text(encoding="utf-8"))
    ft = sorted({c["paper_id"] for c in ch if c.get("has_full_text")})
    rows = run("canonical_ca10_v2", CANON / "processed", CANON / "chroma_db", "researchgpt_papers", ft)

    # vs the pre-3.2b ca@10 numbers + list papers that got worse
    prev = {r["paper_id"]: r for r in json.loads((COV / "cov_canon_ca10.json").read_text(encoding="utf-8"))}
    now = {r["paper_id"]: r for r in rows}
    print("\n-- vs pre-3.2b ca@10 (per paper, only changes) --")
    worse = []
    for pid in ft:
        a, b = prev[pid]["n"], now[pid]["n"]
        if b != a:
            tag = "WORSE" if b < a else "better"
            if b < a:
                worse.append((pid[:12], a, b, now[pid]["conformance"], now[pid]["selection_fallback"]))
            print(f"   {pid[:12]}  {a:2}->{b:2}  {tag:6}  conf={now[pid]['conformance']} "
                  f"fb={now[pid]['selection_fallback']}")
    print(f"\n  0549e2e9 : {prev[[p for p in ft if p.startswith('0549e2e9')][0]]['n']} -> "
          f"{now[[p for p in ft if p.startswith('0549e2e9')][0]]['n']} fields, "
          f"conformance={now[[p for p in ft if p.startswith('0549e2e9')][0]]['conformance']}, "
          f"selection_fallback={now[[p for p in ft if p.startswith('0549e2e9')][0]]['selection_fallback']}")
    print(f"  papers that got WORSE: {worse or 'none'}")

    # data_test regression
    dt_cfg = yaml.safe_load((ROOT / "configs/staging_config.yaml").read_text(encoding="utf-8"))
    dtp = ROOT / dt_cfg["paths"]["processed_dir"]
    dt_ids = sorted({c["paper_id"] for c in json.loads((dtp / "chunks.json").read_text(encoding="utf-8"))})
    dt_before = {r["paper_id"]: len(nef(r)) for r in json.loads((dtp / "paper_summaries.json").read_text(encoding="utf-8"))}
    dt_rows = run("datatest_ca10_v2", dtp, ROOT / dt_cfg["paths"]["chroma_dir"],
                  dt_cfg["system"]["collection_name"], dt_ids)
    dreg = [(r["paper_id"][:10], dt_before.get(r["paper_id"], 0), r["n"])
            for r in dt_rows if r["n"] < dt_before.get(r["paper_id"], 0)]
    print(f"\ndata_test regression vs on-disk: {dreg or 'NONE'}")

    # medical: just the now-visible legacy-schema fallback count (build only, no LLM)
    med_cfg = cfg_for(ROOT / "data/processed", ROOT / "data/chroma_db", "researchgpt_papers", 10)
    build_retrieval_aware_papers(med_cfg, 2500)
    print(f"\nmedical corpus legacy-schema fallback count (now visible): "
          f"{S._legacy_schema_fallback_count(str(ROOT / 'data/processed'))} "
          f"(of {len({c['paper_id'] for c in json.loads((ROOT / 'data/processed/chunks.json').read_text(encoding='utf-8'))})} papers)")


if __name__ == "__main__":
    main()
