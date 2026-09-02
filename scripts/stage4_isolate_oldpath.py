"""Isolation: run the SAME seeded path but emulate the OLD Stage-4 (single cs_ml
prompt, no conformance detection/salvage/repair) so before/after reflects only
the R1/R2 change, not the Phase-1 determinism change.  MEASUREMENT ONLY."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yaml
from src.summarization import summarize as S
from src.summarization.retrieval_aware import build_retrieval_aware_papers

OUT = ROOT / "experiments/document_evidence_pipeline/runs/stage4_hardening"
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)

# monkeypatch to emulate pre-phase behaviour on the seeded path
S.select_extraction_prompt = lambda text: ("cs_ml_forced", S.EXTRACTION_SYSTEM_PROMPT)
S.check_schema_conformance = lambda parsed: (True, [])  # never treat as non-conforming

def nef(rec):
    n = 0
    for f in FLAT:
        v = rec.get(f)
        if f in ("datasets", "metrics"):
            n += bool(isinstance(v, list) and any(str(x).strip() for x in v))
        else:
            n += bool(str(v or "").strip())
    return n

def run(tag, cfg, ids):
    llm = {**cfg["llm"], "temperature": 0, "seed": 42}
    papers_all = build_retrieval_aware_papers(cfg, llm.get("max_context_words", 2500))
    papers = {p: papers_all[p] for p in ids if p in papers_all}
    t0 = time.time()
    res = S.extract_paper_fields(dict(papers), llm, cache={}, processed_dir=None)
    dt = time.time() - t0
    rows = [{"paper_id": p, "oldpath_n": nef(res[p])} for p in papers]
    (OUT / f"{tag}_oldpath.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"{tag}: {dt:.0f}s  " + "  ".join(f"{r['paper_id'][:10]}={r['oldpath_n']}" for r in rows))
    return rows

med_cfg = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))
after_med = {r["paper_id"]: r for r in json.loads((OUT / "medical_fulltext_rows.json").read_text(encoding="utf-8"))}
cs_med = [pid for pid, r in after_med.items() if r["domain_variant"] == "cs_ml"]
print("cs_ml-routed medical papers:", [c[:10] for c in cs_med])
r1 = run("medical_csml", med_cfg, cs_med)

dt_cfg = yaml.safe_load((ROOT / "configs/staging_config.yaml").read_text(encoding="utf-8"))
dt_ids = sorted({c["paper_id"] for c in json.loads((ROOT / dt_cfg["paths"]["processed_dir"] / "chunks.json").read_text(encoding="utf-8"))})
r2 = run("data_test", dt_cfg, dt_ids)

after_dt = {r["paper_id"]: r for r in json.loads((OUT / "data_test_rows.json").read_text(encoding="utf-8"))}
print("\n== R1/R2 delta vs OLD-path-on-seeded (negative = R1/R2 cost) ==")
for tag, oldrows, aftermap in [("medical_csml", r1, after_med), ("data_test", r2, after_dt)]:
    print(f" {tag}:")
    for r in oldrows:
        a = aftermap[r["paper_id"]]["after_n"]
        d = a - r["oldpath_n"]
        mark = "  <-- cost" if d < 0 else ""
        print(f"   {r['paper_id'][:12]}  old-path={r['oldpath_n']}  R1R2={a}  delta={d:+d}{mark}")
