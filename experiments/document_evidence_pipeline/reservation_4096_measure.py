"""Decision measurement — full canonical 34, LaTeX ingestion ENABLED, Task-2 field
routing, extraction_output_reservation = 4096. Seeded, clean cache. Staging only;
does NOT touch production config.

  python -u experiments/document_evidence_pipeline/reservation_4096_measure.py
"""
from __future__ import annotations
import json, shutil, subprocess, sys, threading, time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from latex_ingestion_measure import (_rechunk_canonical, _cfg, nef, LLM, PROC, CHROMA,  # noqa: E402
                                     COLL, OUT as LI_OUT, CORE, BASE)
from src.embedding.build_index import load_model, embed_chunks, build_collection    # noqa: E402
from src.summarization import summarize as S                                        # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers          # noqa: E402

RESV = 4096
OUT = HERE / "runs" / "reservation_4096"
OUT.mkdir(parents=True, exist_ok=True)
STRUCT = {"latex", "jats_xml"}


def _vram_poller(stop, peak):
    while not stop.is_set():
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=5)
            used = max(int(x) for x in r.stdout.split() if x.strip().isdigit())
            peak[0] = max(peak[0], used)
        except Exception:
            pass
        stop.wait(2.0)


def main() -> int:
    # ---- fresh re-chunk + index (LaTeX ingestion path; parity gate ON) ----
    for p in (LI_OUT / "reps.json", PROC / "chunks.json"):
        p.unlink(missing_ok=True)
    shutil.rmtree(CHROMA, ignore_errors=True)
    ft_ids, reps = _rechunk_canonical()
    (LI_OUT / "reps.json").write_text(json.dumps(reps, indent=2), encoding="utf-8")
    (OUT / "reps.json").write_text(json.dumps(reps, indent=2), encoding="utf-8")
    chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    print(f"  reps: {dict(Counter(reps.values()))}   ({len(chunks)} chunks)")
    model = load_model("BAAI/bge-m3", "cuda")
    build_collection(chunks, embed_chunks(model, chunks), str(CHROMA), COLL)
    del model
    try:
        import gc, torch
        gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass

    # ---- extraction: content_aware@10, seeded, CLEAN cache, reservation 4096 ----
    llm = {**LLM, "extraction_output_reservation": RESV}
    cfg = {**_cfg(), "llm": llm}
    papers_all = build_retrieval_aware_papers(cfg, 2500)
    papers = {p: papers_all[p] for p in ft_ids if p in papers_all}

    stop, peak = threading.Event(), [0]
    t = threading.Thread(target=_vram_poller, args=(stop, peak), daemon=True); t.start()
    t0 = time.time()
    ext = S.extract_paper_fields(dict(papers), dict(llm), cache={}, processed_dir=None)
    ext = S._apply_selection_circuit_breaker(cfg, ext, 2500)
    dt = time.time() - t0
    stop.set(); t.join(timeout=3)

    rows = []
    for pid in papers:
        r = ext[pid]
        rows.append({"paper_id": pid, "rep": reps.get(pid), "n": len(nef(r)), "fields": nef(r),
                     "conformance": r.get("_conformance"),
                     "selection_fallback": bool(r.get("_selection_fallback")),
                     "extraction_failed": bool(r.get("_extraction_failed")),
                     "failure_reason": r.get("_failure_reason"),
                     "done_reason": r.get("_done_reason"),
                     "elapsed_s": r.get("_elapsed_s"),
                     "response_truncated": bool(r.get("_response_truncated"))})
    (OUT / "rows.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    n = len(rows)

    def cov(sub):
        return {f: (sum(1 for r in sub if f in r["fields"]), len(sub)) for f in CORE}

    def show(label, sub):
        if not sub:
            print(f"  {label:22} n=0"); return
        m = sum(r["n"] for r in sub) / len(sub)
        c = cov(sub)
        print(f"  {label:22} n={len(sub):2}  mean {m:5.2f}  " +
              "  ".join(f"{f[:4]} {c[f][0]}/{c[f][1]} ({c[f][0]/c[f][1]:.0%})" for f in CORE))

    lat = [r for r in rows if r["rep"] == "latex"]
    afb = [r for r in rows if r["rep"] == "pdf(fallback)"]
    oth = [r for r in rows if r["rep"] not in ("latex", "pdf(fallback)")]

    print(f"\n== canonical {n}, LaTeX ENABLED, reservation {RESV}, seeded, clean cache ==")
    print(f"  runtime: {dt:.0f}s total  ({dt/n:.0f}s/paper)   "
          f"[frozen post-3.2b PDF run ~32s/paper; Phase-4b LaTeX@768 full-34 ~50s/paper]")
    print(f"  peak GPU memory.used (nvidia-smi, whole device): {peak[0]} MiB")
    print(f"  mean non-empty fields/paper: {sum(r['n'] for r in rows)/n:.2f}   (baseline {BASE['mean']})")
    print(f"  conformance: {dict(Counter(r['conformance'] for r in rows))}   "
          f"(baseline {BASE['conf']})")
    print(f"  circuit-breaker fallbacks: {sum(r['selection_fallback'] for r in rows)} "
          f"{[r['paper_id'][:10] for r in rows if r['selection_fallback']]}")
    print(f"  _extraction_failed: {sum(r['extraction_failed'] for r in rows)} "
          f"{[(r['paper_id'][:10], r['failure_reason']) for r in rows if r['extraction_failed']]}")
    dl = [r for r in rows if r["done_reason"] == "length"]
    print(f"  done_reason=='length': {len(dl)}  {[r['paper_id'][:10] for r in dl]}"
          f"{'   <-- 4096 INSUFFICIENT' if dl else '   (0 — 4096 is enough)'}")
    for f in CORE:
        g = sum(1 for r in rows if f in r["fields"])
        print(f"    {f:12} {g}/{n} ({g/n:.0%})   baseline {BASE[f]:.0%}")

    print("\n  -- per representation subset --")
    show("LaTeX-retained", lat)
    show("arXiv-fallback (->PDF)", afb)
    show("non-arXiv", oth)

    try:
        prev = {r["paper_id"]: r["n"] for r in json.loads(
            (HERE / "runs" / "context_budget" / "canonical_ca10_v2.json").read_text(encoding="utf-8"))}
    except FileNotFoundError:
        prev = {}
    worse = []
    print("\n  -- per-paper vs post-3.2b frozen (changes only) --")
    for r in rows:
        b = prev.get(r["paper_id"])
        if b is not None and r["n"] != b:
            tag = "WORSE" if r["n"] < b else "better"
            if r["n"] < b:
                worse.append((r["paper_id"][:12], b, r["n"], r["rep"], r["conformance"]))
            print(f"    {r['paper_id'][:12]} {b:2}->{r['n']:2} {tag:6} rep={r['rep']:14} conf={r['conformance']}")
    lat_prev = [prev[r["paper_id"]] for r in lat if r["paper_id"] in prev]
    if lat_prev:
        print(f"\n  LaTeX-retained vs frozen: mean {sum(lat_prev)/len(lat_prev):.2f} -> "
              f"{sum(r['n'] for r in lat)/len(lat):.2f}  "
              f"(better {sum(1 for r in lat if prev.get(r['paper_id'],0) < r['n'])}, "
              f"worse {sum(1 for r in lat if prev.get(r['paper_id'],99) > r['n'])})")
    print(f"\n  papers WORSE overall: {worse or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
