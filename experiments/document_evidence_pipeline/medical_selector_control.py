"""Controlled 3-arm re-measure of the medical +27pp/+31pp content_aware "gain".

DEFECT the medical coverage figure (metrics 47%->74%, results 37%->68%) attributes
to the SELECTOR a change that also flipped the Stage-4 domain prompt variant on 5
papers (content_aware selection surfaces clinical section text -> routing goes
cs_ml 16 / biomed 3  ->  biomed 8 / cs_ml 11). Phase 2.6 measured the biomed
variant as a real gain on clinical papers, so the number confounds selection with
prompt-variant.

Three arms, SAME 19 re-chunked medical papers, SAME isolated Chroma index, seeded
(temp 0, seed 42), clean cache each arm:

  1. legacy selection      + natural routing
  2. legacy selection      + routing PINNED per paper to arm-3's _domain_variant   <- control
  3. content_aware@10      + natural routing  (+ circuit breaker, as deployed)

Selector's isolated contribution = arm 3 - arm 2.
arm 2 - arm 1 = the prompt-variant / routing component.

Isolated: reads runs/medical_rechunk/processed/ + runs/medical_rechunk/chroma_db;
writes ONLY runs/medical_selector_control/. Six stages unchanged; no src/ edits.

  python -u experiments/document_evidence_pipeline/medical_selector_control.py

Prereq: medical_rechunk.py + medical_rechunk_measure.py already ran (chunks.json,
chroma_db present).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.summarization import summarize as S                                   # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers     # noqa: E402

RUN = HERE / "runs" / "medical_rechunk"
PROC = RUN / "processed"
CHROMA = RUN / "chroma_db"
COLL = "medical_rechunk"
OUT = HERE / "runs" / "medical_selector_control"
OUT.mkdir(parents=True, exist_ok=True)

LLM = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "timeout_seconds": 300,
       "temperature": 0, "seed": 42, "max_context_words": 2500,
       "extraction_deadline_seconds": 240, "extraction_output_reservation": 768}
CORE = ["method", "datasets", "metrics", "results", "limitations"]
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)
_ORIG_SELECT = S.select_extraction_prompt


def nef(rec) -> list[str]:
    out = []
    for f in FLAT:
        v = rec.get(f)
        if f in ("datasets", "metrics"):
            if isinstance(v, list) and any(str(x).strip() for x in v):
                out.append(f)
        elif str(v or "").strip():
            out.append(f)
    return out


def cfg_for(mode: str, budget: int | None) -> dict:
    return {"paths": {"processed_dir": str(PROC), "chroma_dir": str(CHROMA)},
            "embedding": {"model": "BAAI/bge-m3", "device": "cuda"},
            "system": {"collection_name": COLL},
            "llm": LLM,
            "selection": ({"mode": "content_aware", "max_passages": budget}
                          if mode == "content_aware" else {"mode": "legacy"})}


def summarize_rows(rows: list[dict], n: int) -> dict:
    d = {"n": n, "mean_fields": round(sum(r["n"] for r in rows) / n, 2),
         "routing": dict(Counter(r["variant"] for r in rows)),
         "conformance": dict(Counter(r["conformance"] for r in rows)),
         "circuit_breaker": sum(bool(r["selection_fallback"]) for r in rows),
         "extraction_failed": sum(bool(r["extraction_failed"]) for r in rows)}
    for f in CORE:
        g = sum(1 for r in rows if f in r["fields"])
        d[f] = [g, round(g / n, 4)]
    return d


def rows_from(res: dict, ids: list[str]) -> list[dict]:
    out = []
    for pid in ids:
        r = res[pid]
        out.append({"paper_id": pid, "n": len(nef(r)), "fields": nef(r),
                    "conformance": r.get("_conformance"), "variant": r.get("_domain_variant"),
                    "selection_fallback": bool(r.get("_selection_fallback")),
                    "extraction_failed": bool(r.get("_extraction_failed")),
                    "failure_reason": r.get("_failure_reason"),
                    "done_reason": r.get("_done_reason")})
    return out


def run_arm(label: str, mode: str, budget: int | None,
            pin: dict[str, str] | None, ids: list[str]) -> list[dict]:
    """One arm. `pin` maps paper_id -> forced _domain_variant ('biomed'/'cs_ml');
    None = natural routing."""
    papers_all = build_retrieval_aware_papers(cfg_for(mode, budget), 2500)
    papers = {p: papers_all[p] for p in ids if p in papers_all}
    t0 = time.time()
    if pin is None:
        S.select_extraction_prompt = _ORIG_SELECT
        res = S.extract_paper_fields(dict(papers), dict(LLM), cache={}, processed_dir=None)
        res = S._apply_selection_circuit_breaker(cfg_for(mode, budget), res, 2500)
    else:
        # per-paper serial loop with the domain variant PINNED. Mirrors what
        # extract_paper_fields does under a set seed (max_workers=1, prime once).
        S.prime_ollama_cache(LLM)
        res = {}
        for pid in papers:
            v = pin[pid]
            prompt = (S.EXTRACTION_SYSTEM_PROMPT_BIOMED if v == "biomed"
                      else S.EXTRACTION_SYSTEM_PROMPT)
            S.select_extraction_prompt = (lambda _t, _v=v, _p=prompt: (_v, _p))
            _, ex = S._extract_single_paper(pid, papers[pid], dict(LLM), {}, None)
            res[pid] = ex
        S.select_extraction_prompt = _ORIG_SELECT
        # legacy mode -> circuit breaker is a no-op (kept for symmetry / assert)
        res = S._apply_selection_circuit_breaker(cfg_for(mode, budget), res, 2500)
    dt = time.time() - t0
    rows = rows_from(res, ids)
    (OUT / f"arm_{label}.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"  [{label}] {len(rows)} papers, {dt:.0f}s ({dt/len(rows):.0f}s/paper)")
    return rows


def main() -> int:
    chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    ids = sorted({c["paper_id"] for c in chunks if c.get("has_full_text")})
    print(f"medical re-chunk: {len(ids)} full-text papers\n")
    if not (CHROMA / "chroma.sqlite3").exists():
        sys.exit("missing runs/medical_rechunk/chroma_db — run medical_rechunk_measure.py first")

    # arm 3 first — its per-paper _domain_variant is the pin for arm 2
    print("ARM 3 — content_aware@10 + natural routing")
    a3 = run_arm("3_ca_natural", "content_aware", 10, None, ids)
    pin = {r["paper_id"]: r["variant"] for r in a3}
    cb = [r["paper_id"][:10] for r in a3 if r["selection_fallback"]]
    print(f"  pin map (arm-3 _domain_variant): {dict(Counter(pin.values()))}"
          + (f"   [circuit-breaker fallback papers pinned to post-CB variant: {cb}]" if cb else ""))

    print("\nARM 1 — legacy + natural routing")
    a1 = run_arm("1_legacy_natural", "legacy", None, None, ids)

    print("\nARM 2 — legacy + routing PINNED to arm-3 (the control)")
    a2 = run_arm("2_legacy_pinned", "legacy", None, pin, ids)

    S1, S2, S3 = (summarize_rows(a, len(ids)) for a in (a1, a2, a3))
    (OUT / "summary.json").write_text(json.dumps(
        {"arm1_legacy_natural": S1, "arm2_legacy_pinned": S2, "arm3_ca_natural": S3,
         "pin_map": pin}, indent=2), encoding="utf-8")

    n = len(ids)
    print("\n" + "=" * 78)
    print("THREE ARMS — 19 re-chunked medical papers, seeded, clean cache")
    print("=" * 78)
    hdr = f"  {'metric':22}{'1 legacy/natural':>19}{'2 legacy/pinned':>18}{'3 ca@10/natural':>18}"
    print(hdr)
    print(f"  {'mean fields/paper':22}{S1['mean_fields']:>19}{S2['mean_fields']:>18}{S3['mean_fields']:>18}")
    for f in CORE:
        g1, g2, g3 = S1[f][0], S2[f][0], S3[f][0]
        print(f"  {f:22}{f'{g1}/{n} ({g1/n:.0%})':>19}{f'{g2}/{n} ({g2/n:.0%})':>18}{f'{g3}/{n} ({g3/n:.0%})':>18}")
    def rt(s):
        return f"biomed {s['routing'].get('biomed',0)}/cs_ml {s['routing'].get('cs_ml',0)}"
    print(f"  {'routing':22}{rt(S1):>19}{rt(S2):>18}{rt(S3):>18}")
    print(f"  {'conformance':22}{str(S1['conformance']):>19}{str(S2['conformance']):>18}{str(S3['conformance']):>18}")
    print(f"  {'circuit-breaker':22}{S1['circuit_breaker']:>19}{S2['circuit_breaker']:>18}{S3['circuit_breaker']:>18}")
    print(f"  {'extraction_failed':22}{S1['extraction_failed']:>19}{S2['extraction_failed']:>18}{S3['extraction_failed']:>18}")

    print("\n  DECOMPOSITION (percentage points)")
    for f in ("metrics", "results"):
        p1, p2, p3 = S1[f][1] * 100, S2[f][1] * 100, S3[f][1] * 100
        print(f"    {f:9}  confounded (3-1) = {p3-p1:+.0f}pp   "
              f"routing (2-1) = {p2-p1:+.0f}pp   selector isolated (3-2) = {p3-p2:+.0f}pp")

    print("\n  per-paper field count — arm1 -> arm2 -> arm3 (rows that move)")
    m1 = {r["paper_id"]: r for r in a1}
    m2 = {r["paper_id"]: r for r in a2}
    m3 = {r["paper_id"]: r for r in a3}
    for pid in ids:
        r1, r2, r3 = m1[pid], m2[pid], m3[pid]
        if len({r1["n"], r2["n"], r3["n"]}) > 1 or len({r1["variant"], r2["variant"], r3["variant"]}) > 1:
            flip = " FLIP" if r1["variant"] != r3["variant"] else ""
            print(f"    {pid[:12]}  n {r1['n']:2}->{r2['n']:2}->{r3['n']:2}   "
                  f"var {r1['variant']}->{r2['variant']}->{r3['variant']}{flip}   "
                  f"conf {r1['conformance']}/{r2['conformance']}/{r3['conformance']}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
