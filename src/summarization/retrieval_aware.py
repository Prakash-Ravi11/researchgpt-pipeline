"""
Retrieval-aware chunk selection for extraction.

Problem this fixes: reconstruct_paper_texts() in summarize.py takes each
paper's chunks IN ORDER up to a word budget. For a full-text paper longer
than that budget, the results/limitations/conclusion sections — which are
usually near the END of the paper — get silently cut off, even though
they're exactly what the extraction prompt needs most. This was a named,
known limitation, not a hidden one: "Stage 4 extraction doesn't actually use
retrieval — it front-loads the first ~2500 words rather than retrieving the
specific chunks relevant to what dataset/metric they used."

Fix: for each paper, instead of front-loading, RETRIEVE that paper's own
chunks (already embedded in ChromaDB from Stage 3) ranked by relevance to a
set of target queries covering what the extraction prompt actually asks for
— problem/method, results, datasets/metrics, limitations/conclusion. Union
the top chunks per query (deduped), preserve their original page order for
readability, and cap at the same word budget as before.

This costs nothing extra in LLM calls or GPU time — it's smarter chunk
SELECTION using an index you already built, not more compute.

Usage (drop-in alternative to summarize.reconstruct_paper_texts):
    from src.summarization.summarize import load_chunks
    from src.reporting... no — this lives in src/summarization/retrieval_aware.py

    papers = build_retrieval_aware_papers(config, max_words=2500)
    # same {paper_id: {"paper_id", "title", "year", "venue", "text"}} shape
    # as reconstruct_paper_texts — everything downstream (extract_paper_fields
    # etc.) works unchanged.
"""
from collections import defaultdict
from pathlib import Path

# Each query targets a specific slice of what the extraction prompt asks for.
# Kept short and content-focused (not meta-phrased like "find the results
# section") since these are matched against chunk TEXT embeddings, not asked
# as questions to an LLM.
TARGET_QUERIES = [
    "problem statement research gap motivation background",
    "method approach study design procedure participants sample",
    "results findings outcomes performance evaluation",
    "dataset survey data collection measures instruments",
    "limitations discussion conclusion implications future work",
]


def _load_chunks_json(processed_dir: str) -> list[dict]:
    import json
    path = Path(processed_dir) / "chunks.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _get_collection(client, config: dict):
    """Resolve the ChromaDB collection without assuming a specific config key —
    different sessions/builds of this project have stored the collection name
    in different places (or hardcoded it), so auto-detect instead of guessing."""
    configured_name = config.get("system", {}).get("collection_name")
    if configured_name:
        try:
            return client.get_collection(configured_name)
        except Exception:
            pass  # fall through to auto-detection below

    collections = client.list_collections()
    if len(collections) == 1:
        return client.get_collection(collections[0].name)
    if len(collections) == 0:
        raise RuntimeError(
            f"No collections found in ChromaDB at {config['paths']['chroma_dir']} — "
            f"has Stage 3 been run?"
        )
    names = [c.name for c in collections]
    raise RuntimeError(
        f"Multiple ChromaDB collections found ({names}) and none specified in "
        f"config['system']['collection_name'] — add that key to config.yaml with "
        f"the correct name to disambiguate."
    )


def build_retrieval_aware_papers(config: dict, max_words: int = 2500) -> dict[str, dict]:
    """Retrieval-aware replacement for reconstruct_paper_texts. Same output shape,
    smarter chunk selection for papers that exceed the word budget."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    paths_cfg = config["paths"]
    emb_cfg = config["embedding"]

    all_chunks = _load_chunks_json(paths_cfg["processed_dir"])
    by_paper = defaultdict(list)
    for c in all_chunks:
        by_paper[c["paper_id"]].append(c)

    model = SentenceTransformer(emb_cfg["model"], device=emb_cfg["device"])
    model.max_seq_length = 256
    query_vecs = model.encode(TARGET_QUERIES, normalize_embeddings=True)

    client = chromadb.PersistentClient(path=paths_cfg["chroma_dir"])
    collection = _get_collection(client, config)

    papers = {}
    for paper_id, paper_chunks in by_paper.items():
        paper_chunks.sort(key=lambda c: c["chunk_index"])
        title = paper_chunks[0]["title"]
        year = paper_chunks[0]["year"]
        venue = paper_chunks[0]["venue"]

        total_words = sum(len(c["text"].split()) for c in paper_chunks)
        if total_words <= max_words:
            # Short enough already — no truncation happening, retrieval adds
            # nothing here, just use everything in original order.
            selected_chunks = paper_chunks
        else:
            # Retrieve this paper's OWN chunks (metadata-filtered), ranked by
            # relevance to each target query, then union the top hits.
            selected_ids = set()
            for query_vec in query_vecs:
                results = collection.query(
                    query_embeddings=[query_vec.tolist()],
                    n_results=3,
                    where={"paper_id": paper_id},
                )
                for chunk_id in results["ids"][0]:
                    selected_ids.add(chunk_id)

            selected_chunks = [c for c in paper_chunks if c["chunk_id"] in selected_ids]
            if not selected_chunks:
                # Retrieval found nothing (shouldn't normally happen) — fall
                # back to front-loading rather than sending empty text.
                selected_chunks = paper_chunks
            selected_chunks.sort(key=lambda c: c["chunk_index"])  # keep reading order

        words_used = 0
        text_parts = []
        for c in selected_chunks:
            chunk_words = c["text"].split()
            if words_used >= max_words:
                break
            take = chunk_words[: max_words - words_used]
            text_parts.append(" ".join(take))
            words_used += len(take)

        papers[paper_id] = {
            "paper_id": paper_id, "title": title, "year": year, "venue": venue,
            "text": " ".join(text_parts),
        }

    return papers