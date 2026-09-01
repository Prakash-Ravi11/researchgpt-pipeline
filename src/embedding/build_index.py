"""
Stage 3 — Embedding & Indexing.

Embeds all chunks from Stage 2 (chunks.json) using bge-m3 on GPU in a single
batched pass, then writes them into a persistent ChromaDB collection.

Design choices for speed:
  - One batched .encode() call for all chunks (not per-chunk) — this is the
    dominant cost, and GPU batching amortizes it almost entirely.
  - One batched collection.add() call per Chroma batch limit, not per-chunk
    upserts — avoids per-call Python/HTTP-free-but-still-overhead cost inside
    the local Chroma client.
  - Model is loaded once and reused; same model your Stage 1 reranker already
    pulled, so no extra download.

Run standalone for testing:
    python -m src.embedding.build_index --config configs/config.yaml
"""
import argparse
import json
from pathlib import Path

import yaml
from tqdm import tqdm

# ChromaDB's client-side add() has an internal max batch size (depends on
# version, ~5000+); 178 chunks is nowhere near it, but we batch anyway so this
# script doesn't silently break once your corpus grows past that limit.
CHROMA_ADD_BATCH_SIZE = 500


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_chunks(processed_dir: str) -> list[dict]:
    path = Path(processed_dir) / "chunks.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_model(model_name: str, device: str):
    """Load bge-m3 once, tuned for short-ish chunks on limited VRAM."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=device)

    # bge-m3 defaults to an 8192-token max sequence length. Our chunks are
    # ~800 words (~1000-1200 tokens), so leaving this uncapped means every
    # batch pays for attention over a much longer sequence than we actually
    # have — this was the real cause of the ~97s/batch slowdown on a 6GB
    # laptop GPU. Capping it to match our actual chunk size fixes that.
    model.max_seq_length = 1024

    if device == "cuda":
        # fp16 roughly halves memory + often ~2x throughput on consumer GPUs,
        # with negligible impact on embedding quality for retrieval use.
        model.half()

    return model


def embed_chunks(model, chunks: list[dict]) -> "list":
    """Single batched GPU pass over all chunk texts. Returns list of embedding vectors."""
    texts = [c["text"] for c in chunks]

    # normalize_embeddings=True -> cosine similarity == dot product at query time,
    # which is what we tell Chroma to use below (hnsw:space = cosine).
    embeddings = model.encode(
        texts,
        batch_size=16,           # smaller batch to stay within 6GB VRAM headroom
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    return embeddings


def build_collection(chunks: list[dict], embeddings, chroma_dir: str, collection_name: str):
    import chromadb

    Path(chroma_dir).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_dir)

    # Fresh build each run — drop and recreate so re-running Stage 3 after
    # re-processing never leaves stale/duplicate vectors behind.
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "paper_id": c["paper_id"],
            "title": c["title"],
            "year": c["year"] if c["year"] is not None else 0,
            "venue": c.get("venue") or "",
            "has_full_text": c["has_full_text"],
            "source": c["source"],
            "chunk_index": c["chunk_index"],
            # provenance carried through when Stage 2 ran provenance-aware
            # (FINAL_REPORT.md §O); empty strings otherwise — Chroma rejects None.
            "section": c.get("section") or "",
            "page_or_node": c.get("page_or_node") or "",
            "block_id": c.get("block_id") or "",
            "representation": c.get("representation") or "",
        }
        for c in chunks
    ]
    vectors = embeddings.tolist()

    total = len(chunks)
    for start in tqdm(range(0, total, CHROMA_ADD_BATCH_SIZE), desc="Writing to ChromaDB"):
        end = min(start + CHROMA_ADD_BATCH_SIZE, total)
        collection.add(
            ids=ids[start:end],
            embeddings=vectors[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    return collection


def sanity_query(collection, query_text: str, model, n: int = 3):
    """Quick end-to-end retrieval check so you're not just trusting silent success."""
    q_vec = model.encode([query_text], normalize_embeddings=True).tolist()

    results = collection.query(query_embeddings=q_vec, n_results=n)
    print(f"\nSanity check — top {n} results for: '{query_text}'")
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    )):
        print(f"  {i+1}. [{dist:.4f}] {meta['title'][:70]}  ({meta['source']})")
        print(f"     {doc[:120].strip()}...")


def run_embedding(config: dict) -> None:
    paths_cfg = config["paths"]
    emb_cfg = config["embedding"]

    chunks = load_chunks(paths_cfg["processed_dir"])
    print(f"Loaded {len(chunks)} chunks from {paths_cfg['processed_dir']}/chunks.json")

    print(f"Embedding with {emb_cfg['model']} on {emb_cfg['device']} (single batched pass)...")
    model = load_model(emb_cfg["model"], emb_cfg["device"])
    embeddings = embed_chunks(model, chunks)
    print(f"Produced {embeddings.shape[0]} vectors of dim {embeddings.shape[1]}")

    chroma_dir = paths_cfg.get("chroma_dir", "data/chroma_db")
    collection_name = config.get("system", {}).get("collection_name", "researchgpt_papers")

    print(f"Writing to ChromaDB at {chroma_dir} (collection: {collection_name})...")
    collection = build_collection(chunks, embeddings, chroma_dir, collection_name)
    print(f"Indexed {collection.count()} chunks into ChromaDB")

    sanity_query(collection, config["collection"]["domain_query"], model)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_embedding(cfg)