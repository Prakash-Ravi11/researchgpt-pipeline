"""PHASE 2 — decompose the delivery gap into budget effect and query effect.

Measurement only. Nothing in src/ is modified; src is imported read-only for the
frozen generic queries and the frozen metric regex. Reads the existing canonical
chroma store and the existing anchors.json. Writes only to runs/phase2_ladder/.

Ladder (2x2 plus the two known anchor points):

  A  5 generic queries (production)   n_results=3    per-paper union
  B  5 generic queries (production)   n_results=50   per-paper union
  C  per-anchor field query           n_results=3    per-anchor top-k
  D  per-anchor field query           n_results=50   per-anchor top-k
  E  anchor-aware oracle query        n_results=10   per-anchor top-k (from anchors.json)

CELL C/D QUERY CONSTRUCTION — frozen, not tuned:

    metric = first match of the frozen _METRIC regex (retrieval_recall.py:41-45,
             reused by import, not copied) in the +/-220-char window around the
             anchor's value inside its target chunk, taken VERBATIM (match.group(0))
    title  = the paper title as stored on its chunks in chunks.json
    query  = f"{metric} {title}"   -- or the title alone when no metric matches

    No synonyms. No expansion. No iteration. No per-cell tuning.

Relevance criterion, unit and corpus are identical to RETRIEVAL_RECALL_REPORT.md:
hit = target chunk OR any alternate chunk carrying the same value, in the delivered set.
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

RUN = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CHUNKS = RUN / "processed" / "chunks.json"
CHROMA = RUN / "chroma_db"
ANCHORS = HERE / "runs" / "retrieval_recall" / "anchors.json"
OUT = HERE / "runs" / "phase2_ladder"

WINDOW = 220          # same window as retrieval_recall.synth_query
MAX_WORDS = 2500      # configs/config.yaml:37 llm.max_context_words
N_SMALL, N_BIG = 3, 50


def assemble_words(chunks: list[dict], max_words: int = MAX_WORDS) -> int:
    """Word count _assemble (src/summarization/retrieval_aware.py:263-273) would emit."""
    used = 0
    for c in chunks:
        if used >= max_words:
            break
        used += len(c["text"].split()[: max_words - used])
    return used


def main() -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer

    from retrieval_recall import _METRIC                      # frozen metric regex
    from src.summarization.retrieval_aware import TARGET_QUERIES  # frozen 5 generic queries

    OUT.mkdir(parents=True, exist_ok=True)
    anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    by_id = {c["chunk_id"]: c for c in chunks}
    title_of = {c["paper_id"]: c.get("title") or "" for c in chunks}
    papers = sorted({a["paper_id"] for a in anchors})
    nchunks_of = {a["paper_id"]: a["n_chunks"] for a in anchors}

    # ---- freeze the C/D query per anchor -----------------------------------
    n_no_metric = 0
    for a in anchors:
        tgt = by_id.get(a["target_chunk"])
        metric = None
        if tgt:
            txt = tgt["text"]
            i = txt.find(a["value"])
            win = txt[max(0, i - WINDOW): i + WINDOW] if i >= 0 else txt[:2 * WINDOW]
            m = _METRIC.search(win)
            metric = m.group(0) if m else None
        if metric is None:
            n_no_metric += 1
        title = title_of.get(a["paper_id"], "")
        a["_field_query"] = f"{metric} {title}".strip() if metric else title
    print(f"anchors={len(anchors)}  no metric name found={n_no_metric} "
          f"({n_no_metric / len(anchors):.3f}) -> title-only query")

    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    model.max_seq_length = 256
    col = chromadb.PersistentClient(path=str(CHROMA)).get_collection("researchgpt_papers")

    def topk(vec, pid, n):
        n = min(n, nchunks_of[pid])
        r = col.query(query_embeddings=[vec.tolist()], n_results=n, where={"paper_id": pid})
        return r["ids"][0]

    # ---- cells A and B: per-paper union of the 5 generic queries ------------
    gvecs = model.encode(list(TARGET_QUERIES), normalize_embeddings=True, convert_to_numpy=True)
    union_a, union_b = {}, {}
    for pid in papers:
        sa, sb = set(), set()
        for v in gvecs:
            ids = topk(v, pid, N_BIG)
            sa.update(ids[:N_SMALL])
            sb.update(ids[:N_BIG])
        union_a[pid], union_b[pid] = sa, sb
    print("cells A/B retrieved")

    # ---- cells C and D: per-anchor field query ------------------------------
    keys = sorted({(a["paper_id"], a["_field_query"]) for a in anchors})
    qtexts = [k[1] for k in keys]
    qvecs = model.encode(qtexts, normalize_embeddings=True, convert_to_numpy=True,
                         batch_size=64, show_progress_bar=False)
    print(f"unique (paper, field-query) pairs = {len(keys)}")
    hits = {}
    for (pid, q), v in zip(keys, qvecs):
        hits[(pid, q)] = topk(v, pid, N_BIG)
    print("cells C/D retrieved")

    # ---- score every cell ---------------------------------------------------
    def delivered(a, ids) -> bool:
        s = set(ids)
        return a["target_chunk"] in s or any(x in s for x in a["alt_chunks"])

    rows = []
    for a in anchors:
        pid = a["paper_id"]
        ids = hits[(pid, a["_field_query"])]
        rows.append({
            "paper_id": pid, "value": a["value"], "section": a["section"],
            "location": a["location"], "paper_is_short": a["paper_is_short"],
            "n_chunks": a["n_chunks"], "field_query": a["_field_query"],
            "A": delivered(a, union_a[pid]),
            "B": delivered(a, union_b[pid]),
            "C": delivered(a, ids[:N_SMALL]),
            "D": delivered(a, ids[:N_BIG]),
            "E": bool((a["rank_r1"] or 10 ** 9) <= 10 or (a["best_alt_rank_r1"] or 10 ** 9) <= 10),
            "prod_recorded": a["in_production_selection"],
        })

    # budget actually spent, per paper, per cell (for the uniform-random null)
    budget = {
        "A": {p: len(union_a[p]) for p in papers},
        "B": {p: len(union_b[p]) for p in papers},
        "C": {p: min(N_SMALL, nchunks_of[p]) for p in papers},
        "D": {p: min(N_BIG, nchunks_of[p]) for p in papers},
        "E": {p: min(10, nchunks_of[p]) for p in papers},
    }

    def summarise(cell, subset):
        n = len(subset)
        rate = sum(r[cell] for r in subset) / n
        null = sum(budget[cell][r["paper_id"]] / r["n_chunks"] for r in subset) / n
        return {"cell": cell, "n": n, "delivery": round(rate, 4),
                "uniform_null": round(null, 4),
                "ratio_to_random": round(rate / null, 3) if null else None,
                "mean_budget_chunks": round(st.mean([budget[cell][r["paper_id"]] for r in subset]), 1)}

    # words assembled
    def words_per_paper(cell):
        out = []
        for pid in papers:
            if cell in ("A", "B"):
                ids = union_a[pid] if cell == "A" else union_b[pid]
                cs = sorted((by_id[i] for i in ids if i in by_id), key=lambda c: c["chunk_index"])
            else:
                k = N_SMALL if cell == "C" else N_BIG
                seen, cs = set(), []
                for a in (x for x in anchors if x["paper_id"] == pid):
                    for i in hits[(pid, a["_field_query"])][:k]:
                        if i not in seen and i in by_id:
                            seen.add(i)
                            cs.append(by_id[i])
                cs.sort(key=lambda c: c["chunk_index"])
            out.append(assemble_words(cs))
        return out

    long_rows = [r for r in rows if not r["paper_is_short"]]
    report = {"all": {}, "long_only": {}, "words": {}, "n_no_metric": n_no_metric}
    for cell in "ABCDE":
        report["all"][cell] = summarise(cell, rows)
        report["long_only"][cell] = summarise(cell, long_rows)
        w = words_per_paper(cell)
        ws = sorted(w)
        report["words"][cell] = {
            "mean": round(st.mean(w), 1), "median": st.median(w),
            "p95": ws[int(0.95 * (len(ws) - 1))], "max": max(w),
            "papers_at_budget_cap": sum(1 for x in w if x >= MAX_WORDS),
        }

    # Phase 5 step 1: persist the per-paper budget (the union size for cells A/B),
    # which Phase 4 needed for ratio-to-random and could not recover. Output only --
    # no measurement logic above this line is altered.
    report["budget_per_paper"] = budget
    (OUT / "ladder.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (OUT / "per_anchor.json").write_text(json.dumps(rows), encoding="utf-8")

    print("\n            delivery   null   ratio  budget   words(mean/p95)")
    for cell in "ABCDE":
        r, w = report["long_only"][cell], report["words"][cell]
        print(f"  {cell}  long:  {r['delivery']:.4f}  {r['uniform_null']:.4f}  "
              f"{r['ratio_to_random']:>5}  {r['mean_budget_chunks']:>6}   {w['mean']:.0f}/{w['p95']}")
    a, b, c, d = (report["long_only"][x]["delivery"] for x in "ABCD")
    print(f"\n  B-A budget={b - a:+.4f}  C-A query={c - a:+.4f}  D-A both={d - a:+.4f}  "
          f"sum={(b - a) + (c - a):+.4f}  interaction={(d - a) - ((b - a) + (c - a)):+.4f}")

    # self-check: cell A must reproduce the recorded production number
    rec = sum(r["prod_recorded"] for r in long_rows) / len(long_rows)
    got = report["long_only"]["A"]["delivery"]
    print(f"\n  self-check  cell A={got:.4f}  recorded in_production_selection={rec:.4f}  "
          f"delta={abs(got - rec):.4f}")
    assert abs(got - rec) < 0.01, "cell A did not reproduce the recorded production delivery"
    print("  OK")


if __name__ == "__main__":
    main()
