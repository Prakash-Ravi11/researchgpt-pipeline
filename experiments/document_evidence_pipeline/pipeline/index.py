"""P5 - isolated retrieval over BGE-M3 + ChromaDB.

Uses an ISOLATED chroma path (experiments/.../pipeline/chroma) - never the
production data/chroma_db. Dense cosine only; a reranker is deliberately NOT
included (see FINAL_REPORT question N - only add if measured recall fails).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CHROMA_DIR = HERE / "chroma"
COLLECTION = "doc_evidence_chunks"

_MODEL = None


def get_model(device: str = "cuda"):
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("BAAI/bge-m3", device=device)
        m.max_seq_length = 512
        if device == "cuda":
            m.half()
        _MODEL = m
    return _MODEL


# field -> retrieval query (matched against chunk-text embeddings)
FIELD_QUERIES = {
    "dataset": "dataset benchmark corpus training data evaluation data samples collected",
    "metrics": "evaluation metric accuracy precision recall F1 dice AUC score measured",
    "results": "results performance achieved outperforms improvement percentage points scores table",
    "method": "proposed method approach architecture model pipeline algorithm procedure design",
    "limitations": "limitations weaknesses failure cases future work threats to validity constraints",
}


class RetrievalIndex:
    def __init__(self, device: str = "cuda", fresh: bool = True):
        import chromadb
        if fresh and CHROMA_DIR.exists():
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            self.client.delete_collection(COLLECTION)
        except Exception:
            pass
        self.col = self.client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        self.device = device

    def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        model = get_model(self.device)
        vecs = model.encode([c["text"] for c in chunks], batch_size=16,
                            normalize_embeddings=True, convert_to_numpy=True,
                            show_progress_bar=False)
        self.col.add(
            ids=[c["chunk_id"] for c in chunks],
            embeddings=vecs.tolist(),
            documents=[c["text"] for c in chunks],
            metadatas=[{k: (v if v is not None else "") for k, v in c.items() if k != "text"}
                       for c in chunks],
        )
        return len(chunks)

    def retrieve(self, paper_id: str, field: str, k: int = 5) -> list[dict[str, Any]]:
        model = get_model(self.device)
        qv = model.encode([FIELD_QUERIES[field]], normalize_embeddings=True).tolist()
        res = self.col.query(query_embeddings=qv, n_results=k, where={"paper_id": paper_id})
        out = []
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            out.append({**meta, "text": doc, "distance": round(float(dist), 4)})
        return out
