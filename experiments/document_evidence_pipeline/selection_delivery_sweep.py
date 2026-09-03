"""Anchor-chunk DELIVERY rate: does the chunk holding a numeric anchor reach the
extractor?  legacy selector vs content_aware, swept over the passage budget.
34-paper frozen-60 canonical corpus, Phase-1 seeded path.  No LLM (selection only).

Uses the exact 3981-anchor set from the last retrieval_recall.py run
(runs/retrieval_recall/anchors.json), so the delivery % is on the same denominator
as Test 3's R@k / in_prod_sel numbers.

STEP 0 baseline = the `legacy` row here (seeded).  Do not compare it to the older
unseeded 7%.

  python -u experiments/document_evidence_pipeline/selection_delivery_sweep.py
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

from src.summarization import retrieval_aware as RA  # noqa: E402

CANON = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
ANCHORS = HERE / "runs" / "retrieval_recall" / "anchors.json"
OUT = HERE / "runs" / "selection_policy"
OUT.mkdir(parents=True, exist_ok=True)
BUDGETS = [5, 10, 15, 20]


def delivery(anchors, sel_by_paper, f=None):
    sub = [a for a in anchors if f is None or f(a)]
    if not sub:
        return None, 0
    hit = sum(1 for a in sub if a["target_chunk"] in sel_by_paper.get(a["paper_id"], ())
              or any(x in sel_by_paper.get(a["paper_id"], ()) for x in a["alt_chunks"]))
    return round(hit / len(sub), 4), len(sub)


def main():
    import chromadb
    from sentence_transformers import SentenceTransformer

    anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))
    print(f"anchors: {len(anchors)} (from retrieval_recall run)")
    chunks = json.loads((CANON / "processed" / "chunks.json").read_text(encoding="utf-8"))
    by_paper: dict[str, list[dict]] = {}
    for c in chunks:
        if c.get("has_full_text"):
            by_paper.setdefault(c["paper_id"], []).append(c)
    for pid in by_paper:
        by_paper[pid].sort(key=lambda c: c["chunk_index"])
    long_pids = {p for p in by_paper if sum(len(c["text"].split()) for c in by_paper[p]) > 2500}
    short_pids = set(by_paper) - long_pids
    short_sel = {p: {c["chunk_id"] for c in by_paper[p]} for p in short_pids}
    print(f"papers: {len(by_paper)}  long(>2500w): {len(long_pids)}  short: {len(short_pids)}")

    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    model.max_seq_length = 256
    generic_vecs = model.encode(RA._GENERIC_QUERIES, normalize_embeddings=True)
    col = chromadb.PersistentClient(path=str(CANON / "chroma_db")).get_collection("researchgpt_papers")

    def variant(mode, budget):
        t0 = time.time()
        sel = dict(short_sel)
        passes, chars = [], []
        for pid in long_pids:
            pcs = by_paper[pid]
            if mode == "legacy":
                _, tr = RA._select_legacy(pcs, col, generic_vecs, pid, 2500)
            else:
                c = {**RA._SELECTION_DEFAULTS, "mode": "content_aware", "max_passages": budget}
                _, tr = RA._select_content_aware(pcs, col, model, pid, c, 2500)
            ids = set(tr["selected_chunk_ids"])
            sel[pid] = ids
            passes.append(len(ids))
            chars.append(sum(len(x["text"]) for x in pcs if x["chunk_id"] in ids))
        row = {"mode": mode, "budget": budget, "runtime_s": round(time.time() - t0, 1),
               "mean_passages": round(sum(passes) / len(passes), 1),
               "mean_chars": round(sum(chars) / len(chars)), "max_chars": max(chars)}
        for lbl, f in [("ALL", None),
                       ("g0", lambda a: not a["gate_returns_some"]),
                       ("gS", lambda a: a["gate_returns_some"]),
                       ("longALL", lambda a: a["paper_id"] in long_pids),
                       ("long_g0", lambda a: a["paper_id"] in long_pids and not a["gate_returns_some"]),
                       ("long_gS", lambda a: a["paper_id"] in long_pids and a["gate_returns_some"]),
                       ("table", lambda a: a["location"] == "table"),
                       ("prose", lambda a: a["location"] == "prose")]:
            row[lbl], row[lbl + "_n"] = delivery(anchors, sel, f)
        return row

    rows = [variant("legacy", None)] + [variant("content_aware", b) for b in BUDGETS]
    (OUT / "delivery_sweep.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print("\n== ANCHOR-CHUNK DELIVERY RATE ==")
    print(f"{'variant':16} {'pass':>5} {'chars':>6} {'ALL':>7} {'g0':>7} {'gS':>7} |"
          f" {'longALL':>8} {'long_g0':>8} {'long_gS':>8} | {'table':>7} {'prose':>7}  {'s':>4}")
    for r in rows:
        nm = r["mode"] + (f"@{r['budget']}" if r["budget"] else "")
        print(f"{nm:16} {r['mean_passages']:>5} {r['mean_chars']:>6} "
              f"{r['ALL']:>7} {r['g0']:>7} {r['gS']:>7} | "
              f"{r['longALL']:>8} {r['long_g0']:>8} {r['long_gS']:>8} | "
              f"{r['table']:>7} {r['prose']:>7}  {r['runtime_s']:>4}")
    b = rows[0]
    print(f"\nn: ALL={b['ALL_n']} g0={b['g0_n']} gS={b['gS_n']}  longALL={b['longALL_n']} "
          f"table={b['table_n']} prose={b['prose_n']}")


if __name__ == "__main__":
    main()
