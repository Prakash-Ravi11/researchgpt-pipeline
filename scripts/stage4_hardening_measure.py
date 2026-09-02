"""
Measure the Stage-4 hardening (R1 schema conformance + R2 domain prompt) on the
19 full-text papers of the medical/clinical corpus (third corpus), plus a
no-regression check on data_test/ (8 CS/NLP papers).  MEASUREMENT ONLY.

BEFORE  = the on-disk paper_summaries.json / extraction_cache.json (produced by
          the pre-this-phase code).
AFTER   = extract_paper_fields re-run with a fresh cache on the Phase-1 seeded
          path (temperature 0, seed 42).

Run:  .venv/Scripts/python.exe scripts/stage4_hardening_measure.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from src.summarization import summarize as S  # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers  # noqa: E402

OUT = ROOT / "experiments/document_evidence_pipeline/runs/stage4_hardening"
OUT.mkdir(parents=True, exist_ok=True)
SCHEMA = set(S._EXTRACTION_SCHEMA_KEYS)
CORE = ["method", "datasets", "metrics", "results", "limitations"]
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)


def nonempty_fields(rec: dict) -> list[str]:
    out = []
    for f in FLAT:
        v = rec.get(f)
        if f in ("datasets", "metrics"):
            if isinstance(v, list) and any(str(x).strip() for x in v):
                out.append(f)
        elif str(v or "").strip():
            out.append(f)
    return out


def before_conformant(cache_entry: dict) -> bool:
    if not isinstance(cache_entry, dict):
        return False
    junk = any(k not in SCHEMA and not str(k).startswith("_") for k in cache_entry)
    return (not junk) and S._has_min_content(cache_entry)


def run_corpus(tag: str, cfg: dict, paper_ids: list[str]):
    proc = ROOT / cfg["paths"]["processed_dir"]
    summaries = {r["paper_id"]: r for r in json.loads((proc / "paper_summaries.json").read_text(encoding="utf-8"))}
    cache_before = json.loads((proc / "extraction_cache.json").read_text(encoding="utf-8"))

    llm_cfg = {**cfg["llm"], "temperature": 0, "seed": 42}
    max_words = llm_cfg.get("max_context_words", 2500)
    papers_all = build_retrieval_aware_papers(cfg, max_words)
    papers = {pid: papers_all[pid] for pid in paper_ids if pid in papers_all}
    missing = [p for p in paper_ids if p not in papers_all]
    if missing:
        print(f"  [{tag}] WARNING {len(missing)} ids not in selection: {[m[:10] for m in missing]}")

    t0 = time.time()
    after = S.extract_paper_fields(dict(papers), llm_cfg, cache={}, processed_dir=None)
    dt = time.time() - t0

    rows = []
    for pid in papers:
        b_rec = summaries.get(pid, {})
        b_cache = cache_before.get(pid, {})
        a_rec = after[pid]
        rows.append({
            "paper_id": pid,
            "before_fields": nonempty_fields(b_rec),
            "before_n": len(nonempty_fields(b_rec)),
            "before_conformant": before_conformant(b_cache),
            "after_fields": nonempty_fields(a_rec),
            "after_n": len(nonempty_fields(a_rec)),
            "after_conformance": a_rec.get("_conformance"),
            "domain_variant": a_rec.get("_domain_variant"),
            "repair_call": bool(a_rec.get("_repair_call_made")),
            "nonconformant_unrepaired": bool(a_rec.get("_extraction_nonconformant")),
            "conformance_issues": a_rec.get("_conformance_issues", []),
        })
    (OUT / f"{tag}_rows.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    n = len(rows)
    b_conf = sum(r["before_conformant"] for r in rows)
    a_conf_direct = sum(1 for r in rows if r["after_conformance"] == "conformant")
    a_conf_final = sum(1 for r in rows if r["after_conformance"] in
                       ("conformant", "salvaged", "repaired", "repaired_salvaged"))
    repaired_ok = sum(1 for r in rows if r["after_conformance"] in ("repaired", "repaired_salvaged"))
    repair_calls = sum(r["repair_call"] for r in rows)
    still_bad = [r["paper_id"] for r in rows if r["nonconformant_unrepaired"]]
    zero_to_nonzero = [r["paper_id"] for r in rows if r["before_n"] == 0 and r["after_n"] > 0]
    regressions = [(r["paper_id"], r["before_n"], r["after_n"]) for r in rows if r["after_n"] < r["before_n"]]

    print(f"\n===== {tag}  (n={n})  runtime {dt:.0f}s ({dt/max(n,1):.1f}s/paper) =====")
    print(f"  fields/paper   before mean {sum(r['before_n'] for r in rows)/n:.1f}  ->  after mean {sum(r['after_n'] for r in rows)/n:.1f}")
    print(f"  schema-conformance   before {b_conf}/{n}   after (model direct) {a_conf_direct}/{n}   after (incl. salvage/repair) {a_conf_final}/{n}")
    print(f"  repair LLM calls made: {repair_calls}   repair produced a conforming result: {repaired_ok}")
    print(f"  still non-conforming after repair: {len(still_bad)}  {[s[:10] for s in still_bad]}")
    print(f"  papers 0 fields -> >0 fields: {len(zero_to_nonzero)}  {[z[:10] for z in zero_to_nonzero]}")
    print(f"  REGRESSIONS (after_n < before_n): {regressions or 'none'}")
    print("  domain variant:", {v: sum(1 for r in rows if r["domain_variant"] == v) for v in ("cs_ml", "biomed")})
    print(f"\n  {'paper':12} {'var':6} bN->aN  conformance            issues")
    for r in sorted(rows, key=lambda x: x["after_n"]):
        print(f"  {r['paper_id'][:12]:12} {str(r['domain_variant'])[:6]:6} {r['before_n']:>2}->{r['after_n']:<2}  "
              f"{str(r['after_conformance']):22} {r['conformance_issues'][:2]}")
    return rows, {"n": n, "runtime_s": round(dt, 1), "before_conf": b_conf, "after_conf_direct": a_conf_direct,
                  "after_conf_final": a_conf_final, "repair_calls": repair_calls, "repaired_ok": repaired_ok,
                  "still_bad": still_bad, "zero_to_nonzero": zero_to_nonzero, "regressions": regressions}


def main():
    med_cfg = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))
    per_doc = json.loads((ROOT / "experiments/document_evidence_pipeline/runs/extraction_triage/per_doc.json").read_text(encoding="utf-8"))
    med_ids = [r["paper_id"] for r in per_doc if r["has_full_text"]]
    print(f"medical corpus full-text ids: {len(med_ids)}")
    med_rows, med_sum = run_corpus("medical_fulltext", med_cfg, med_ids)

    dt_cfg = yaml.safe_load((ROOT / "configs/staging_config.yaml").read_text(encoding="utf-8"))
    dt_chunks = json.loads((ROOT / dt_cfg["paths"]["processed_dir"] / Path("chunks.json")).read_text(encoding="utf-8")) \
        if False else json.loads((ROOT / dt_cfg["paths"]["processed_dir"] / "chunks.json").read_text(encoding="utf-8"))
    dt_ids = sorted({c["paper_id"] for c in dt_chunks})
    print(f"\ndata_test ids: {len(dt_ids)}")
    dt_rows, dt_sum = run_corpus("data_test", dt_cfg, dt_ids)

    (OUT / "summary.json").write_text(json.dumps({"medical": med_sum, "data_test": dt_sum}, indent=2, default=str), encoding="utf-8")
    print(f"\nrows + summary -> {OUT}")
    if dt_sum["regressions"]:
        print("!! data_test REGRESSED — report this, do not absorb it.")


if __name__ == "__main__":
    main()
