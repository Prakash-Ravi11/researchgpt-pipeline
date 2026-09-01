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
        "authors": [a.get("name", "") for a in (paper.get("authors") or []) if isinstance(a, dict)],
        "baseline_has_full_text": bool(paper.get("has_full_text")),
        "acquisition": acq,
        "document": {k: v for k, v in doc.items() if k != "blocks"},
        "blocks": doc["blocks"],
        "chunks": chunks,
        "prepare_seconds": round(time.perf_counter() - t0, 1),
    }


def _block_for(prepared: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    for b in prepared["blocks"]:
        if b["block_id"] == block_id:
            return b
    return None


def _section_context(prepared: dict[str, Any], section: str, limit: int = 6000) -> str:
    parts, used = [], 0
    for b in prepared["blocks"]:
        if b["section"] == section:
            parts.append(b["text"])
            used += len(b["text"])
            if used >= limit:
                break
    return " ".join(parts)


def extract_paper(prepared: dict[str, Any], index: RetrievalIndex,
                  llm_cfg: dict[str, Any]) -> dict[str, Any]:
    pid = prepared["paper_id"]
    doc_repr = prepared["document"]["representation"]
    items = []
    for field in EVIDENCE_FIELDS:
        chunks = index.retrieve(pid, field, k=5) if prepared["chunks"] else []
        item = extract_field(pid, field, chunks, doc_repr, llm_cfg)

        if item["evidence_status"] in ("EXPLICIT", "INFERRED") and item.get("provenance_valid"):
            # attribution runs against the FULL source block (exact block_id from
            # the span match), escalating to section context if the block alone
            # is inconclusive. A PDF page holds several blocks, so section+page
            # is not a unique key - the block_id from the verified span match is.
            src_block = _block_for(prepared, item.get("_block_id", ""))
            block_text = (src_block or {}).get("text") \
                or item.get("_matched_chunk_text", "") or item.get("evidence_span") or ""
            attr = attribute_claim(
                block_text, item.get("evidence_span") or "",
                block_type=(src_block or {}).get("block_type"),
                section=item.get("section"),
                section_context=_section_context(prepared, item.get("section") or ""),
                own_author_surnames=prepared.get("authors"),
            )
            item["attribution"] = attr["attribution"]
            item["attribution_confidence"] = attr["confidence"]
            item["_attr_window"] = attr["window"]
            item["_attr_level"] = attr.get("level")
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
