"""
Retrieval-aware chunk selection for extraction.

Problem this fixes: reconstruct_paper_texts() in summarize.py takes each
paper's chunks IN ORDER up to a word budget. For a full-text paper longer
than that budget, the results/limitations/conclusion sections — which are
usually near the END of the paper — get silently cut off, even though
they're exactly what the extraction prompt needs most.

Two selection modes (config['selection']['mode']):
  "legacy"        — the original: 5 fixed generic queries, top-3 each, union
                    <= 15 chunks, word-budget cap. Unchanged, kept reversible.
  "content_aware" — queries derived from the paper itself (results/eval
                    headings, table & figure captions, detected metric names),
                    candidate chunks scored on retrieval rank + numeric-anchor
                    density + table structure, near-duplicate anchor content
                    de-duplicated, assembled up to a small passage / token
                    budget (defaults sized for a 6 GB card; ~10-passage
                    ceiling — beyond that, correctness and citation accuracy
                    degrade for untrained ~7B RAG, per OpenScholar).

Output shape is identical either way:
    {paper_id: {"paper_id", "title", "year", "venue", "text"}}
so extract_paper_fields etc. work unchanged.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from src.evidence.anchors import find_anchors

# Fallback queries for papers where content-derived query extraction finds
# nothing (e.g. legacy chunks with no section/heading structure).
_GENERIC_QUERIES = [
    "problem statement research gap motivation background",
    "method approach study design procedure participants sample",
    "results findings outcomes performance evaluation",
    "dataset survey data collection measures instruments",
    "limitations discussion conclusion implications future work",
]
# Back-compat alias — external code / tests import TARGET_QUERIES.
TARGET_QUERIES = _GENERIC_QUERIES

_SELECTION_DEFAULTS = {
    "mode": "legacy",          # production default unchanged; staging opts into content_aware
    "max_passages": 10,        # OpenScholar ceiling for untrained ~7B RAG (peak ~10; degrades after)
    "token_budget_chars": 9000,  # ~2.2k tokens; sized for Qwen2.5:7b sharing a 6 GB card with BGE-M3
    "per_query_topk": 4,       # candidates pulled per query before scoring
    "same_anchor_cap": 2,      # at most N selected chunks may share one dominant anchor value
    "w_rank": 1.0,             # score weights
    "w_anchor": 0.6,
    "w_table": 0.5,
}

_METRIC_NAME_RE = re.compile(
    r"\b(accuracy|precision|recall|f1(?:[- ]?score)?|dice(?:\s+(?:score|coefficient|index))?|"
    r"iou|jaccard|mIoU|auroc|auprc|auc|sensitivity|specificity|hausdorff|hd95|"
    r"nDCG(?:@\d+)?|MRR|MAP|exact match|EM|hit@\d+|recall@\d+|precision@\d+|p@\d+|"
    r"BLEU(?:-\d)?|ROUGE(?:-[L\d]+)?|METEOR|perplexity|R?MSE|MAE|MAPE|WER|CER|PSNR|SSIM|"
    r"pearson|spearman|kappa|correlation)\b", re.I)
_RESULTS_HINTS = ("result", "experiment", "evaluation", "ablation", "performance",
                  "comparison", "finding", "quantitative")
_VERB_RE = re.compile(
    r"\b(is|are|was|were|show|shows|achiev\w+|improv\w+|reach\w+|obtain\w+|report\w+|"
    r"outperform\w+|propose\w+|present\w+)\b", re.I)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]+")
_COMMON_SHORT = {"the", "and", "for", "with", "our", "we", "of", "in", "on", "to",
                 "a", "an", "is", "are", "by", "as", "vs", "per", "no"}


def _load_chunks_json(processed_dir: str) -> list[dict]:
    path = Path(processed_dir) / "chunks.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _get_collection(client, config: dict):
    """Resolve the ChromaDB collection without assuming a specific config key."""
    configured_name = config.get("system", {}).get("collection_name")
    if configured_name:
        try:
            return client.get_collection(configured_name)
        except Exception:
            pass
    collections = client.list_collections()
    if len(collections) == 1:
        return client.get_collection(collections[0].name)
    if len(collections) == 0:
        raise RuntimeError(
            f"No collections found in ChromaDB at {config['paths']['chroma_dir']} — "
            f"has Stage 3 been run?")
    names = [c.name for c in collections]
    raise RuntimeError(
        f"Multiple ChromaDB collections found ({names}) and none specified in "
        f"config['system']['collection_name'].")


def _selection_cfg(config: dict) -> dict:
    cfg = dict(_SELECTION_DEFAULTS)
    cfg.update({k: v for k, v in (config.get("selection") or {}).items() if v is not None})
    return cfg


def _query_ok(q: str, section: str) -> bool:
    """Degenerate-query guard: reject reference-list text and word-boundary-broken
    fragments (Test 3 traced misses to queries like 'For etrieval findings...')."""
    if "reference" in (section or "").lower():
        return False
    toks = _WORD_RE.findall(q)
    if len(toks) < 2:
        return False
    longish = [t for t in toks if len(t) >= 3]
    if longish:
        real = sum(1 for t in longish if len(t) >= 4 or t.lower() in _COMMON_SHORT)
        if real / len(longish) < 0.5:
            return False
    return True


def _clean_query(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _derive_queries(paper_chunks: list[dict]) -> tuple[list[str], dict]:
    """Queries derived from the paper itself. Returns (queries, provenance)."""
    full_text = " ".join(c["text"] for c in paper_chunks)
    metrics: list[str] = []
    for m in _METRIC_NAME_RE.finditer(full_text):
        t = m.group(0).strip()
        if t.lower() not in {x.lower() for x in metrics}:
            metrics.append(t)
        if len(metrics) >= 6:
            break

    derived: list[str] = []
    prov = {"metrics": metrics, "headings": [], "captions": []}
    if metrics:
        derived.append(" ".join(metrics) + " results score table")

    for c in paper_chunks:
        bt = c.get("block_type")
        sec = (c.get("section") or "").lower()
        txt = _clean_query(c["text"])
        if not txt:
            continue
        if bt == "heading" and any(h in txt.lower() or h in sec for h in _RESULTS_HINTS):
            q = txt[:120]
            if _query_ok(q, sec):
                derived.append(q)
                prov["headings"].append(q)
        elif bt in ("table", "figure_caption"):
            q = txt.split(". ")[0][:120]
            if _query_ok(q, sec):
                derived.append(q)
                prov["captions"].append(q)

    seen, clean = set(), []
    for q in derived:
        k = q.lower()
        if k in seen or not _query_ok(q, ""):
            continue
        seen.add(k)
        clean.append(q)
    return clean, prov


def _table_signal(chunk: dict, n_anchor: int) -> float:
    if chunk.get("block_type") == "table":
        return 1.0
    win = chunk["text"][:600]
    if n_anchor >= 6 and len(_VERB_RE.findall(win)) <= 1:  # legacy heuristic (no block_type)
        return 0.6
    return 0.0


def _dominant_anchor(anchor_vals: list[str]) -> str | None:
    if not anchor_vals:
        return None
    return Counter(anchor_vals).most_common(1)[0][0]


def _select_content_aware(paper_chunks, collection, model, paper_id, cfg, max_words):
    """Content-derived queries -> candidate scoring -> de-dup -> budgeted assembly."""
    by_id = {c["chunk_id"]: c for c in paper_chunks}
    queries, prov = _derive_queries(paper_chunks)
    used_generic = len(queries) < 2
    all_queries = list(queries)
    if used_generic:
        all_queries += _GENERIC_QUERIES

    qvecs = model.encode(all_queries, normalize_embeddings=True)
    best_rank: dict[str, int] = {}
    for qv in qvecs:
        res = collection.query(query_embeddings=[qv.tolist()],
                               n_results=cfg["per_query_topk"],
                               where={"paper_id": paper_id})
        for rank, cid in enumerate(res["ids"][0]):
            if cid not in best_rank or rank < best_rank[cid]:
                best_rank[cid] = rank

    scored = []
    for cid, rank in best_rank.items():
        ch = by_id.get(cid)
        if ch is None:
            continue
        anchors = [v for v, _ in find_anchors(ch["text"])]
        words = max(len(ch["text"].split()), 1)
        density = len(anchors) / words
        score = (cfg["w_rank"] * (1.0 / (1.0 + rank))
                 + cfg["w_anchor"] * min(density * 40.0, 1.0)
                 + cfg["w_table"] * _table_signal(ch, len(anchors)))
        scored.append((cid, score, anchors))
    scored.sort(key=lambda x: (-x[1], by_id[x[0]]["chunk_index"]))

    selected, sel_anchor_sets = [], []
    used_chars, anchor_use = 0, Counter()
    for cid, score, anchors in scored:
        if len(selected) >= cfg["max_passages"]:
            break
        ch = by_id[cid]
        if selected and used_chars + len(ch["text"]) > cfg["token_budget_chars"]:
            continue
        aset = frozenset(anchors)
        if aset and any(len(aset & s) / max(len(aset), 1) > 0.8 for s in sel_anchor_sets):
            continue  # near-duplicate anchor content
        dom = _dominant_anchor(anchors)
        if dom and anchor_use[dom] >= cfg["same_anchor_cap"]:
            continue
        selected.append(cid)
        sel_anchor_sets.append(aset)
        used_chars += len(ch["text"])
        if dom:
            anchor_use[dom] += 1

    if not selected:
        selected = [c["chunk_id"] for c in paper_chunks]  # never send empty text

    sel_chunks = sorted((by_id[cid] for cid in selected), key=lambda c: c["chunk_index"])
    trace = {
        "mode": "content_aware", "queries": queries, "used_generic_fallback": used_generic,
        "query_provenance": prov, "n_candidates": len(best_rank),
        "selected_chunk_ids": [c["chunk_id"] for c in sel_chunks],
        "selected_sections": [c.get("section") for c in sel_chunks],
        "selected_chars": used_chars, "n_passages": len(sel_chunks),
        "max_passages": cfg["max_passages"], "token_budget_chars": cfg["token_budget_chars"],
    }
    return _assemble(sel_chunks, max_words), trace


def _select_legacy(paper_chunks, collection, query_vecs, paper_id, max_words):
    selected_ids = set()
    for qv in query_vecs:
        res = collection.query(query_embeddings=[qv.tolist()], n_results=3,
                               where={"paper_id": paper_id})
        for cid in res["ids"][0]:
            selected_ids.add(cid)
    sel = [c for c in paper_chunks if c["chunk_id"] in selected_ids] or list(paper_chunks)
    sel.sort(key=lambda c: c["chunk_index"])
    return _assemble(sel, max_words), {"mode": "legacy",
                                       "selected_chunk_ids": [c["chunk_id"] for c in sel]}


def _assemble(chunks: list[dict], max_words: int) -> str:
    words_used, parts = 0, []
    for c in chunks:
        if words_used >= max_words:
            break
        w = c["text"].split()
        take = w[: max_words - words_used]
        parts.append(" ".join(take))
        words_used += len(take)
    return " ".join(parts)


def build_retrieval_aware_papers(config: dict, max_words: int = 2500) -> dict[str, dict]:
    """Retrieval-aware replacement for reconstruct_paper_texts. Same output shape."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    paths_cfg = config["paths"]
    emb_cfg = config["embedding"]
    sel_cfg = _selection_cfg(config)

    all_chunks = _load_chunks_json(paths_cfg["processed_dir"])
    by_paper = defaultdict(list)
    for c in all_chunks:
        by_paper[c["paper_id"]].append(c)

    model = SentenceTransformer(emb_cfg["model"], device=emb_cfg["device"])
    model.max_seq_length = 256
    generic_vecs = model.encode(_GENERIC_QUERIES, normalize_embeddings=True)

    client = chromadb.PersistentClient(path=paths_cfg["chroma_dir"])
    collection = _get_collection(client, config)

    # content_aware derives queries from section headings / block types and scores on
    # table structure — it needs the grounded (evidence-grounding) chunk schema. On
    # legacy chunks it has none of that and measurably regresses (medical corpus:
    # 5/19 papers lost fields). Fall back to legacy selection when the schema is legacy.
    grounded_schema = any("block_type" in c for cs in by_paper.values() for c in cs)
    effective_mode = sel_cfg["mode"]
    if effective_mode == "content_aware" and not grounded_schema:
        effective_mode = "legacy"

    papers, traces = {}, {}
    for paper_id, paper_chunks in by_paper.items():
        paper_chunks.sort(key=lambda c: c["chunk_index"])
        title, year, venue = (paper_chunks[0]["title"], paper_chunks[0]["year"],
                              paper_chunks[0]["venue"])
        total_words = sum(len(c["text"].split()) for c in paper_chunks)

        if total_words <= max_words:
            text = _assemble(paper_chunks, max_words)
            traces[paper_id] = {"mode": "passthrough", "reason": "<= max_words"}
        elif effective_mode == "content_aware":
            text, traces[paper_id] = _select_content_aware(
                paper_chunks, collection, model, paper_id, sel_cfg, max_words)
        else:
            text, traces[paper_id] = _select_legacy(
                paper_chunks, collection, generic_vecs, paper_id, max_words)
            if sel_cfg["mode"] == "content_aware":
                traces[paper_id]["fell_back_from"] = "content_aware (legacy chunk schema)"

        papers[paper_id] = {"paper_id": paper_id, "title": title, "year": year,
                            "venue": venue, "text": text}

    try:
        (Path(paths_cfg["processed_dir"]) / "retrieval_selection.json").write_text(
            json.dumps(traces, indent=2), encoding="utf-8")
    except OSError:
        pass  # inspection artifact only; never block a run on it
    return papers
