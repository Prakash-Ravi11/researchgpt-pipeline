"""3.3b/3.3c — re-measure Phase 3 on the RE-CHUNKED medical corpus (grounded schema).
Both selectors on the NEW chunks. Isolated: reads runs/medical_rechunk/processed/,
builds its own Chroma at runs/medical_rechunk/chroma_db (collection `medical_rechunk`).
data/processed/, the canonical corpus, and data_test are untouched.

  python -u experiments/document_evidence_pipeline/medical_rechunk_measure.py

Prereq: run medical_rechunk.py first (writes runs/medical_rechunk/processed/chunks.json).
"""
from __future__ import annotations
import json, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.evidence.anchors import NUMERIC_ANCHOR_RE as _NUMVAL, find_anchors  # noqa: E402
from src.embedding.build_index import load_model, embed_chunks, build_collection  # noqa: E402
from src.summarization import retrieval_aware as RA  # noqa: E402
from src.summarization import summarize as S  # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers  # noqa: E402

RUN = HERE / "runs" / "medical_rechunk"
PROC = RUN / "processed"
CHROMA = RUN / "chroma_db"
COLL = "medical_rechunk"
OUT = RUN / "measure"
OUT.mkdir(parents=True, exist_ok=True)

LLM = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "timeout_seconds": 300,
       "temperature": 0, "seed": 42, "max_context_words": 2500,
       "extraction_deadline_seconds": 240, "extraction_output_reservation": 768}
CORE = ["method", "datasets", "metrics", "results", "limitations"]
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)
_VERB = re.compile(r"\b(is|are|was|were|show|shows|achiev\w+|improv\w+|reach\w+|obtain\w+|"
                   r"report\w+|outperform\w+)\b", re.I)


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


def cfg_for(mode, budget):
    return {"paths": {"processed_dir": str(PROC), "chroma_dir": str(CHROMA)},
            "embedding": {"model": "BAAI/bge-m3", "device": "cuda"},
            "system": {"collection_name": COLL},
            "selection": ({"mode": "content_aware", "max_passages": budget}
                          if mode == "content_aware" else {"mode": "legacy"})}


def build_anchor_set(by_paper):
    """Same rule as retrieval_recall.py: src.evidence.anchors.find_anchors, table/prose
    via block_type=='table' OR (>=6 numbers & <=1 verb) in a +/-220-char window."""
    anchors = []
    for pid, pcs in by_paper.items():
        chunks_with_val = defaultdict(list)
        for c in pcs:
            for val, _ in find_anchors(c["text"]):
                chunks_with_val[val].append(c["chunk_id"])
        seen = set()
        for c in pcs:
            for val, pos in find_anchors(c["text"]):
                sec = c.get("section") or "?"
                if (val, sec) in seen:
                    continue
                seen.add((val, sec))
                win = c["text"][max(0, pos - 220): pos + 220]
                nums_near = len(_NUMVAL.findall(win))
                verbs_near = len(_VERB.findall(win))
                loc = "table" if (c.get("block_type") == "table"
                                  or (nums_near >= 6 and verbs_near <= 1)) else "prose"
                anchors.append({"paper_id": pid, "value": val, "section": sec, "location": loc,
                                "target_chunk": c["chunk_id"],
                                "alt_chunks": sorted(set(chunks_with_val[val]))})
    # cap surplus table cells at 60/paper (deterministic, by encounter order)
    per = Counter()
    kept = []
    for a in anchors:
        if a["location"] == "prose":
            kept.append(a)
        else:
            per[a["paper_id"]] += 1
            if per[a["paper_id"]] <= 60:
                kept.append(a)
    return kept


def delivery(anchors, sel_by_paper, f=None):
    sub = [a for a in anchors if f is None or f(a)]
    if not sub:
        return None, 0
    hit = sum(1 for a in sub
              if a["target_chunk"] in sel_by_paper.get(a["paper_id"], ())
              or any(x in sel_by_paper.get(a["paper_id"], ()) for x in a["alt_chunks"]))
    return round(hit / len(sub), 4), len(sub)


def main() -> int:
    chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    by_paper = defaultdict(list)
    for c in chunks:
        if c.get("has_full_text"):
            by_paper[c["paper_id"]].append(c)
    for pid in by_paper:
        by_paper[pid].sort(key=lambda c: c["chunk_index"])
    ft_ids = sorted(by_paper)
    print(f"re-chunked medical: {len(ft_ids)} full-text papers, "
          f"{sum(len(v) for v in by_paper.values())} full-text chunks\n")

    # ---- build isolated Chroma index ----
    print("building isolated Chroma index...")
    model = load_model("BAAI/bge-m3", "cuda")
    embs = embed_chunks(model, chunks)
    col = build_collection(chunks, embs, str(CHROMA), COLL)
    print(f"indexed {col.count()} chunks into {COLL}\n")

    # ---- anchor set ----
    anchors = build_anchor_set(by_paper)
    (OUT / "anchors.json").write_text(json.dumps(anchors, indent=2), encoding="utf-8")
    nt = sum(1 for a in anchors if a["location"] == "table")
    print(f"medical anchor set: {len(anchors)}  (table={nt}, prose={len(anchors)-nt})\n")

    # ---- DELIVERY: legacy + ca@10 on new chunks (selection only, no LLM) ----
    gvecs = model.encode(RA._GENERIC_QUERIES, normalize_embeddings=True)
    deliv_rows = []
    for mode, budget in [("legacy", None), ("content_aware", 10)]:
        t0 = time.time()
        sel = {}
        passes = []
        for pid in ft_ids:
            pcs = by_paper[pid]
            words = sum(len(c["text"].split()) for c in pcs)
            if words <= 2500:
                sel[pid] = {c["chunk_id"] for c in pcs}
            elif mode == "legacy":
                _, tr = RA._select_legacy(pcs, col, gvecs, pid, 2500)
                sel[pid] = set(tr["selected_chunk_ids"])
            else:
                c = {**RA._SELECTION_DEFAULTS, "mode": "content_aware", "max_passages": budget}
                _, tr = RA._select_content_aware(pcs, col, model, pid, c, 2500)
                sel[pid] = set(tr["selected_chunk_ids"])
            passes.append(len(sel[pid]))
        row = {"variant": mode + (f"@{budget}" if budget else ""),
               "mean_passages": round(sum(passes) / len(passes), 1),
               "runtime_s": round(time.time() - t0, 1)}
        for lbl, f in [("all", None), ("table", lambda a: a["location"] == "table"),
                       ("prose", lambda a: a["location"] == "prose")]:
            row[lbl], row[lbl + "_n"] = delivery(anchors, sel, f)
        deliv_rows.append(row)
    (OUT / "delivery.json").write_text(json.dumps(deliv_rows, indent=2), encoding="utf-8")
    del model, embs, gvecs
    try:
        import gc, torch
        gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass
    print("== ANCHOR-CHUNK DELIVERY (new chunks, both selectors) ==")
    print(f"  {'variant':16}{'pass':>6}{'all':>9}{'table':>9}{'prose':>9}{'s':>7}")
    for r in deliv_rows:
        print(f"  {r['variant']:16}{r['mean_passages']:>6}{str(r['all']):>9}"
              f"{str(r['table']):>9}{str(r['prose']):>9}{r['runtime_s']:>7}")
    print(f"  n: table={deliv_rows[0]['table_n']} prose={deliv_rows[0]['prose_n']}\n")

    # ---- COVERAGE: both selectors, seeded, clean cache ----
    cov = {}
    for mode, budget in [("legacy", None), ("content_aware", 10)]:
        tag = mode + (f"{budget}" if budget else "")
        papers_all = build_retrieval_aware_papers(cfg_for(mode, budget), 2500)
        papers = {p: papers_all[p] for p in ft_ids if p in papers_all}
        # domain routing on the assembled text actually handed to the extractor
        routing = Counter(S.select_extraction_prompt(papers[p]["text"])[0] for p in papers)
        t0 = time.time()
        res = S.extract_paper_fields(dict(papers), dict(LLM), cache={}, processed_dir=None)
        res = S._apply_selection_circuit_breaker(cfg_for(mode, budget), res, 2500)
        dt = time.time() - t0
        fb = S._legacy_schema_fallback_count(str(PROC))
        rows = []
        for pid in papers:
            r = res[pid]
            rows.append({"paper_id": pid, "n": len(nef(r)), "fields": nef(r),
                         "conformance": r.get("_conformance"),
                         "variant": r.get("_domain_variant"),
                         "selection_fallback": bool(r.get("_selection_fallback")),
                         "extraction_failed": bool(r.get("_extraction_failed")),
                         "failure_reason": r.get("_failure_reason"),
                         "done_reason": r.get("_done_reason"),
                         "elapsed_s": r.get("_elapsed_s")})
        (OUT / f"cov_{tag}.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        cov[tag] = rows
        n = len(rows)
        print(f"== coverage {tag}  n={n}  {dt:.0f}s ({dt/n:.0f}s/paper) ==")
        print(f"  routing (assembled text): {dict(routing)}")
        print(f"  legacy-schema fallback count: {fb}   (MUST be 0)")
        print(f"  circuit-breaker fallbacks: {sum(r['selection_fallback'] for r in rows)} "
              f"{[r['paper_id'][:10] for r in rows if r['selection_fallback']]}")
        print(f"  mean non-empty fields/paper: {sum(r['n'] for r in rows)/n:.2f}")
        print(f"  conformance: {dict(Counter(r['conformance'] for r in rows))}")
        print(f"  _extraction_failed: {sum(r['extraction_failed'] for r in rows)} "
              f"{[(r['paper_id'][:10], r['failure_reason']) for r in rows if r['extraction_failed']]}")
        for f in CORE:
            g = sum(1 for r in rows if f in r["fields"])
            print(f"    {f:12} {g}/{n} ({g/n:.0%})")
        deg = next((r for r in rows if r["paper_id"].startswith("9879e1cce9")), None)
        if deg:
            print(f"  WATCH 9879e1cce9: elapsed={deg['elapsed_s']}s conformance={deg['conformance']} "
                  f"done_reason={deg['done_reason']} failed={deg['extraction_failed']} n={deg['n']}")
        print()

    # ---- worse per paper: ca@10 vs legacy, both on new chunks ----
    lg = {r["paper_id"]: r for r in cov["legacy"]}
    ca = {r["paper_id"]: r for r in cov["content_aware10"]}
    print("== per-paper ca@10 vs legacy (new chunks) — changes only ==")
    worse = []
    for pid in ft_ids:
        a, b = lg[pid]["n"], ca[pid]["n"]
        if a != b:
            tag = "WORSE" if b < a else "better"
            if b < a:
                worse.append((pid[:12], a, b, ca[pid]["conformance"]))
            print(f"  {pid[:12]}  legacy {a:2} -> ca@10 {b:2}  {tag}  conf={ca[pid]['conformance']}")
    print(f"\n  papers WORSE under ca@10: {worse or 'none'}")

    # ---- determinability 3-way (heuristic headings are a LOWER BOUND, not a denominator) ----
    reps = Counter(by_paper[p][0].get("representation") for p in ft_ids)
    print(f"\n== field-presence determinability ==")
    print(f"  representation of the 19: {dict(reps)}")
    print(f"  determinable (structured rep, e.g. JATS): 0 / 19 — triage found no JATS/LaTeX here.")
    print(f"  PyMuPDF gives heuristic section headings only; these are a LOWER BOUND on")
    print(f"  presence, not a denominator. 'undeterminable' is NOT upgraded on a regex.")
    print(f"  => three-way split: determinable-present 0 / determinable-absent 0 / undeterminable 19")
    print(f"  per-field coverage above is the usable number, over all 19 (no presence denominator).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
