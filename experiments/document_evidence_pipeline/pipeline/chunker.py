"""P2 - provenance-aware chunking.

Splits canonical blocks into retrieval-sized chunks WITHOUT crossing a block
boundary, so every chunk keeps exact section + page/node + char-span provenance.
"""
from __future__ import annotations

from typing import Any

CHUNK_WORDS = 220
CHUNK_OVERLAP = 40


def chunk_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for block in doc["blocks"]:
        words = block["text"].split()
        if not words:
            continue
        if len(words) <= CHUNK_WORDS:
            spans = [(0, len(words))]
        else:
            spans, start = [], 0
            while start < len(words):
                end = min(start + CHUNK_WORDS, len(words))
                spans.append((start, end))
                if end == len(words):
                    break
                start = end - CHUNK_OVERLAP
        for i, (s, e) in enumerate(spans):
            sub = " ".join(words[s:e])
            # char offset of this sub-chunk within the source block
            prefix_chars = len(" ".join(words[:s])) + (1 if s else 0)
            chunks.append({
                "chunk_id": f"{block['block_id']}#{i}",
                "paper_id": block["paper_id"],
                "source": block["source"],
                "representation": block["representation"],
                "section": block["section"],
                "page_or_node": block["page_or_node"],
                "block_id": block["block_id"],
                "block_type": block["block_type"],
                "char_start": block["char_start"] + prefix_chars,
                "char_end": block["char_start"] + prefix_chars + len(sub),
                "text": sub,
            })
    return chunks
