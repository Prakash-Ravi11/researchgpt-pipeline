"""P6 - end-to-end orchestration for one corpus.

corpus -> [acquire -> represent -> chunk] per paper
       -> one shared retrieval index
       -> per paper, per field: retrieve -> extract -> attribute -> decide
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .acquire import acquire_paper
from .represent import build_document
from .chunker import chunk_document
from .index import RetrievalIndex
from .extract import extract_field
from .attribute import attribute_claim
from .decide import decide
from .schema import EVIDENCE_FIELDS, FULL_TEXT, RETURNED

HERE = Path(__file__).resolve().parent


def prepare_paper(paper: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    acq, data = acquire_paper(paper, cache_dir=cache_dir)
    doc = build_document(acq, data, fallback_abstract=paper.get("abstract"))
    chunks = chunk_document(doc)
    return {
        "paper_id": paper.get("paperId", ""),
        "title": paper.get("title", ""),
        "baseline_has_full_text": bool(paper.get("has_full_text")),
        "acquisition": acq,
        "document": {k: v for k, v in doc.items() if k != "blocks"},
        "blocks": doc["blocks"],
        "chunks": chunks,
        "prepare_seconds": round(time.perf_counter() - t0, 1),
    }


def _block_text_for(prepared: dict[str, Any], block_id: str) -> str:
    for b in prepared["blocks"]:
        if b["block_id"] == block_id:
            return b["text"]
    return ""


def extract_paper(prepared: dict[str, Any], index: RetrievalIndex,
                  llm_cfg: dict[str, Any]) -> dict[str, Any]:
    pid = prepared["paper_id"]
    doc_repr = prepared["document"]["representation"]
    items = []
    for field in EVIDENCE_FIELDS:
        chunks = index.retrieve(pid, field, k=5) if prepared["chunks"] else []
        item = extract_field(pid, field, chunks, doc_repr, llm_cfg)

        if item["evidence_status"] in ("EXPLICIT", "INFERRED") and item.get("provenance_valid"):
            # attribution only matters for quantitative/ownership fields; run it
            # against the FULL source block, not just the retrieved slice
            src_block_id = item["page_or_node"]
            # locate the block that produced the matched chunk
            block_text = ""
            for c in chunks:
                if c["section"] == item["section"] and c["page_or_node"] == item["page_or_node"]:
                    block_text = _block_text_for(prepared, c["block_id"])
                    break
            attr = attribute_claim(block_text or (item.get("evidence_span") or ""),
                                   item.get("evidence_span") or "")
            item["attribution"] = attr["attribution"]
            item["attribution_confidence"] = attr["confidence"]
            item["_attr_window"] = attr["window"]
        item = decide(item)
        items.append(item)

    returned = [i for i in items if i["final"] == RETURNED]
    return {
        "paper_id": pid,
        "title": prepared["title"],
        "acquisition_status": prepared["acquisition"]["status"],
        "representation": doc_repr,
        "source": prepared["acquisition"].get("source"),
        "full_text_confidence": prepared["acquisition"].get("full_text_confidence"),
        "n_returned": len(returned),
        "n_abstained": len(items) - len(returned),
        "evidence": items,
    }
