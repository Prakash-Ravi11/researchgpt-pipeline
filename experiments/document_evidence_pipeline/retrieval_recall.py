"""Self-supervised recall of the Stage-3 retrieval path for result-bearing chunks.

For every meaningful numeric anchor in the 34 canonical full-text papers we know
which chunk it lives in (that is the target). We synthesise a query from the
anchor's context WITHOUT the number, run it through the real retrieval primitive
(BGE-M3 encode -> per-paper ChromaDB dense query, exactly as
src/summarization/retrieval_aware.py does), and record whether the target is in
the top-k. Measurement only; nothing in retrieval/chunking/reranking is changed.

  python experiments/document_evidence_pipeline/retrieval_recall.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.evidence.anchors import (  # noqa: E402  (single source of truth for the anchor rule)
    NUMERIC_ANCHOR_RE as _NUMVAL,
    find_anchors as anchors_in_text,
)

RUN = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CHUNKS = RUN / "processed" / "chunks.json"
CHROMA = RUN / "chroma_db"
META = RUN / "raw_metadata" / "collected_papers.json"
EVID = HERE / "runs" / "prodab-20260902T004416Z" / "canonical_paper_evidence.json"
CACHE = RUN / "processed" / "extraction_cache.json"
OUT = HERE / "runs" / "retrieval_recall"

# the meaningful-numeric-anchor rule (_NUMVAL, anchors_in_text) is imported
# from src.evidence.anchors above — shared with the gate and Test 2.
_METRIC = re.compile(
    r"\b(exact match|nDCG@\d+|recall@\d+|precision@\d+|hit@\d+|p@\d+|r@\d+|f1[- ]?score|f1|"
    r"accuracy|precision|recall|dice(?:\s+index)?|iou|auroc|auprc|auc|bleu(?:-\d)?|rouge(?:-[l\d])?|"
    r"meteor|mae|rmse|mse|mape|mrr|map|perplexity|pearson(?:\s+correlation)?|spearman|kappa|"
    r"sensitivity|specificity|faithfulness|relevance|em\b|correlation)\b", re.I)
_DATASET = re.compile(
    r"\b([A-Z][A-Za-z0-9][A-Za-z0-9\-\.]{1,22}(?:Bench|QA|Eval|Bank|Set|k|1k|Nuggets|RAG|Wiki)?)\b"
    r"(?=(?:[^.]{0,40}\b(?:dataset|benchmark|corpus|test set|test split|questions?)\b)|"
    r"|(?:\s+(?:dataset|benchmark|corpus)))")
_STOP = {"the", "and", "for", "with", "from", "this", "that", "using", "based", "our", "we",
         "of", "in", "on", "to", "a", "an", "is", "are", "was", "were", "by", "as", "which",
         "were", "where", "when", "than", "then", "also", "such", "these", "those", "their",
         "results", "result", "table", "figure", "shows", "show", "reported", "report"}


def synth_query(window: str, value: str, paper_datasets: list[str]) -> str:
    """Deterministic. metric name + dataset (if identifiable) + nearest noun-ish
    tokens. NEVER contains the numeric value."""
    w = re.sub(r"\s+", " ", window).strip()
    parts: list[str] = []
    mm = _METRIC.search(w)
    if mm:
        parts.append(mm.group(0))
    dm = _DATASET.search(w)
    ds = dm.group(1) if dm else None
    if not ds:
        for d in paper_datasets:
            toks = [t for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", d)][:2]
            if toks and any(t.lower() in w.lower() for t in toks):
                ds = " ".join(toks)
                break
    if ds:
        parts.append(ds)
    # nearest noun-ish tokens: capitalised words or >=5-char words, not the metric/dataset, not stop
    used = {t.lower() for p in parts for t in p.split()}
    cand = []
    for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", w):
        tl = t.lower()
        if tl in _STOP or tl in used or len(t) < 4:
            continue
        if t[0].isupper() or len(t) >= 6:
            cand.append(t)
    # keep order of appearance, cap
    seen = set()
    nn = [c for c in cand if not (c.lower() in seen or seen.add(c.lower()))][:6]
    parts.extend(nn)
    q = " ".join(parts[:12]).strip()
    # hard guarantee: no numeric value at all in the query (real user queries
    # never contain the answer). strip this anchor's value, then every _NUMVAL.
    q = q.replace(value, " ")
    q = _NUMVAL.sub(" ", q)
    return re.sub(r"\s+", " ", q).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    import chromadb
    from sentence_transformers import SentenceTransformer

    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    meta = {m.get("paperId") or m.get("paper_id"): m for m in json.loads(META.read_text(encoding="utf-8"))}
    evid = json.loads(EVID.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    ret_some = set()
    for r in evid:
        if any(it["final"] == "RETURNED" for f in ("metrics", "results")
               for it in r.get("evidence", {}).get(f, [])):
            ret_some.add(r["paper_id"])

    by_paper: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        if c.get("has_full_text"):
            by_paper[c["paper_id"]].append(c)
    for pid in by_paper:
        by_paper[pid].sort(key=lambda c: c["chunk_index"])

    # ---- STEP 1+2: anchors + synthesized queries ----
    RESULT_SECTIONS = {"results", "experimental_setup", "discussion", "conclusion", "method"}
    anchors = []
    for pid, pcs in by_paper.items():
        pds = cache.get(pid, {}).get("datasets") or []
        chunks_with_val: dict[str, list[str]] = defaultdict(list)
        for c in pcs:
            for val, _ in anchors_in_text(c["text"]):
                chunks_with_val[val].append(c["chunk_id"])
        seen_val_sec = set()
        for c in pcs:
            t = c["text"]
            for val, pos in anchors_in_text(t):
                sec = c.get("section") or "?"
                key = (val, sec)
                if key in seen_val_sec:
                    continue
                seen_val_sec.add(key)
                # prefer a target chunk in a result-y section
                target = c["chunk_id"]
                if sec not in RESULT_SECTIONS:
                    alt = next((cc for cc in pcs if cc["chunk_id"] in chunks_with_val[val]
                                and (cc.get("section") in RESULT_SECTIONS)), None)
                    if alt:
                        target = alt["chunk_id"]
                        c = alt
                        t = alt["text"]
                        pos = t.find(val)
                        sec = alt.get("section") or "?"
                win = t[max(0, pos - 220): pos + 220]
                q = synth_query(win, val, pds)
                if len(q.split()) < 2:
                    continue
                # table-ness of the anchor: block_type or a numbers-dense, verb-sparse window
                bt = c.get("block_type")
                nums_near = len(_NUMVAL.findall(win))
                verbs_near = len(re.findall(r"\b(is|are|was|were|show|shows|achiev\w+|improv\w+|"
                                            r"reach\w+|obtain\w+|report\w+|outperform\w+)\b", win, re.I))
                location = "table" if (bt == "table" or (nums_near >= 6 and verbs_near <= 1)) else "prose"
                anchors.append({
                    "paper_id": pid, "value": val, "section": sec, "location": location,
                    "target_chunk": target, "alt_chunks": sorted(set(chunks_with_val[val])),
                    "query": q, "source": meta.get(pid, {}).get("pdf_source"),
                    "representation": meta.get(pid, {}).get("representation_type"),
                    "gate_returns_some": pid in ret_some,
                })
    before = len(anchors)
    anchors = [a for a in anchors if a["value"] not in a["query"] and not _NUMVAL.search(a["query"])]
    dropped_num = before - len(anchors)
    # keep ALL prose anchors; cap table anchors at 60/paper (deterministic: first by position)
    per_paper_tbl = Counter()
    kept = []
    for a in anchors:
        if a["location"] == "prose":
            kept.append(a)
        else:
            per_paper_tbl[a["paper_id"]] += 1
            if per_paper_tbl[a["paper_id"]] <= 60:
                kept.append(a)
    capped = len(anchors) - len(kept)
    anchors = kept
    print(f"papers: {len(by_paper)}   anchors: {len(anchors)} "
          f"(dropped {dropped_num} non-de-numberable; capped {capped} surplus table cells at 60/paper)")

    # ---- STEP 3: real retrieval primitive ----
    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    model.max_seq_length = 256
    client = chromadb.PersistentClient(path=str(CHROMA))
    col = client.get_collection("researchgpt_papers")

    def run_once(tag: str):
        qs = [a["query"] for a in anchors]
        vecs = model.encode(qs, normalize_embeddings=True, convert_to_numpy=True,
                            batch_size=64, show_progress_bar=False)
        for a, v in zip(anchors, vecs):
            n_chunks = len(by_paper[a["paper_id"]])
            res = col.query(query_embeddings=[v.tolist()],
                            n_results=min(n_chunks, 100), where={"paper_id": a["paper_id"]})
            ids = res["ids"][0]
            rank = ids.index(a["target_chunk"]) + 1 if a["target_chunk"] in ids else None
            alt_ranks = [ids.index(x) + 1 for x in a["alt_chunks"] if x in ids]
            best_alt = min(alt_ranks) if alt_ranks else None
            a[f"rank_{tag}"] = rank
            a[f"best_alt_rank_{tag}"] = best_alt
            a[f"retrieved_ids_{tag}"] = ids[:20]
            a[f"n_chunks"] = n_chunks

    run_once("r1")
    run_once("r2")
    det = all(a["rank_r1"] == a["rank_r2"] for a in anchors)
    print(f"retrieval deterministic across 2 runs: {det}")

    # ---- STEP 3b: production selection (5 fixed queries x top-3 union) ----
    from src.summarization.retrieval_aware import TARGET_QUERIES
    tqv = model.encode(TARGET_QUERIES, normalize_embeddings=True, convert_to_numpy=True)
    prod_sel: dict[str, set] = {}
    short_papers = set()
    for pid, pcs in by_paper.items():
        total_words = sum(len(c["text"].split()) for c in pcs)
        if total_words <= 2500:
            short_papers.add(pid)
            prod_sel[pid] = {c["chunk_id"] for c in pcs}
            continue
        sel = set()
        for v in tqv:
            r = col.query(query_embeddings=[v.tolist()], n_results=3, where={"paper_id": pid})
            sel.update(r["ids"][0])
        prod_sel[pid] = sel
    for a in anchors:
        seen_ids = prod_sel.get(a["paper_id"], set())
        a["in_production_selection"] = (a["target_chunk"] in seen_ids
                                        or any(x in seen_ids for x in a["alt_chunks"]))
        a["paper_is_short"] = a["paper_id"] in short_papers

    (OUT / "anchors.json").write_text(json.dumps(anchors, indent=2), encoding="utf-8")

    # ---- STEP 4: report tables ----
    def rate(sub, k):
        n = len(sub)
        if not n:
            return None
        # lenient: target OR any alt chunk within k
        h = sum(1 for a in sub if (a["rank_r1"] and a["rank_r1"] <= k)
                or (a["best_alt_rank_r1"] and a["best_alt_rank_r1"] <= k))
        return round(h / n, 3)

    def block(name, sub):
        return (f"  {name:34} n={len(sub):5}  R@5={rate(sub,5)}  R@10={rate(sub,10)}  "
                f"R@20={rate(sub,20)}  in_prod_sel={round(sum(a['in_production_selection'] for a in sub)/max(1,len(sub)),3)}")

    print("\n== RECALL (target chunk or an alt chunk with the same value, per-paper dense query) ==")
    print(block("ALL anchors", anchors))
    print(block("  location=table", [a for a in anchors if a["location"] == "table"]))
    print(block("  location=prose", [a for a in anchors if a["location"] == "prose"]))
    for rep in ("jats_xml", "pdf"):
        print(block(f"  representation={rep}", [a for a in anchors if a["representation"] == rep]))
    for src in sorted({a["source"] for a in anchors if a["source"]}):
        print(block(f"  source={src}", [a for a in anchors if a["source"] == src]))
    print(block("  gate returns SOME quant", [a for a in anchors if a["gate_returns_some"]]))
    print(block("  gate returns ZERO quant", [a for a in anchors if not a["gate_returns_some"]]))

    # ---- STEP 5: loss decomposition ----
    misses = [a for a in anchors if not ((a["rank_r1"] and a["rank_r1"] <= 20)
                                         or (a["best_alt_rank_r1"] and a["best_alt_rank_r1"] <= 20))]
    absent = [a for a in misses if not a["rank_r1"] and not a["best_alt_rank_r1"]]
    ranked_out = [a for a in misses if (a["rank_r1"] or a["best_alt_rank_r1"])]
    print(f"\n== LOSS DECOMPOSITION (misses at k=20: {len(misses)}/{len(anchors)}) ==")
    print(f"  absent from embedder candidate set (not in top-{{min(nchunks,200)}}): {len(absent)}")
    print(f"  surfaced by embedder but ranked below 20:                          {len(ranked_out)}")
    print("  (there is NO reranker in the live path — see report; config retrieval.mode is dead)")

    worst = sorted(ranked_out, key=lambda a: -(a["rank_r1"] or a["best_alt_rank_r1"] or 999))[:10]
    worst = (worst + sorted(absent, key=lambda a: a["n_chunks"], reverse=True))[:10]
    wrows = []
    for a in worst:
        tgt = next(c for c in by_paper[a["paper_id"]] if c["chunk_id"] == a["target_chunk"])
        got = []
        for cid in a["retrieved_ids_r1"][:3]:
            cc = next((c for c in by_paper[a["paper_id"]] if c["chunk_id"] == cid), None)
            got.append({"chunk_id": cid, "section": cc.get("section") if cc else "?",
                        "excerpt": re.sub(r"\s+", " ", (cc.get("text") if cc else ""))[:180]})
        wrows.append({
            "paper_id": a["paper_id"], "value": a["value"], "location": a["location"],
            "gate_returns_some": a["gate_returns_some"], "query": a["query"],
            "target_rank": a["rank_r1"], "best_alt_rank": a["best_alt_rank_r1"], "n_chunks": a["n_chunks"],
            "target_chunk": {"chunk_id": a["target_chunk"], "section": tgt.get("section"),
                             "excerpt": re.sub(r"\s+", " ", tgt["text"])[:240]},
            "retrieved_instead": got,
        })
    (OUT / "worst_misses.json").write_text(json.dumps(wrows, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps({
        "papers": len(by_paper), "anchors": len(anchors),
        "retrieval_deterministic": det,
        "recall": {k: rate(anchors, k) for k in (5, 10, 20)},
        "by_location": {loc: {k: rate([a for a in anchors if a["location"] == loc], k) for k in (5, 10, 20)}
                        for loc in ("table", "prose")},
        "by_gate_return": {
            "some": {k: rate([a for a in anchors if a["gate_returns_some"]], k) for k in (5, 10, 20)},
            "zero": {k: rate([a for a in anchors if not a["gate_returns_some"]], k) for k in (5, 10, 20)},
        },
        "misses_k20": len(misses), "absent_from_embedder": len(absent), "ranked_out": len(ranked_out),
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
