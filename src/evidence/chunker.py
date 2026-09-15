"""P2 - provenance-aware chunking.

Splits canonical blocks into retrieval-sized chunks WITHOUT crossing a block
boundary, so every chunk keeps exact section + page/node + char-span provenance.

EXP-LATEX-01 adds ONE opt-in behaviour, off by default
(``RQ_TABLE_ATOMIC``): a ``table`` block is emitted as a single chunk however
long it is, instead of being cut at ``CHUNK_WORDS``. With the flag unset this
module behaves exactly as before — same chunk ids, same spans, same keys.
"""
from __future__ import annotations

from typing import Any

from . import flags

CHUNK_WORDS = 220
CHUNK_OVERLAP = 40

#: Block types kept whole under ``RQ_TABLE_ATOMIC``. A table's meaning lives in
#: the row x column relation; cutting it at an arbitrary word boundary splits
#: rows from their headers and strands values with no metric to bind to.
ATOMIC_BLOCK_TYPES = ("table",)

#: Advisory only. A chunk longer than this is *flagged* ``table_oversized``,
#: never split — the whole point of the flag is that rows are not cut. It exists
#: so the experiment can count how many atomic tables would overflow the
#: embedding window (BGE-M3: 8192 tokens) instead of discovering it as silent
#: truncation. Words are not tokens: pipe-separated table tokens run well above
#: 1 token/word, so the real count must be measured with the tokenizer, not
#: inferred from this number.
EMBED_WORD_SOFT_LIMIT = 3000


def _sliding_spans(n_words: int) -> list[tuple[int, int]]:
    """The historical span layout: CHUNK_WORDS window, CHUNK_OVERLAP back-step."""
    if n_words <= CHUNK_WORDS:
        return [(0, n_words)]
    spans, start = [], 0
    while start < n_words:
        end = min(start + CHUNK_WORDS, n_words)
        spans.append((start, end))
        if end == n_words:
            break
        start = end - CHUNK_OVERLAP
    return spans


def chunk_document(doc: dict[str, Any],
                   table_atomic: bool | None = None) -> list[dict[str, Any]]:
    """Blocks -> chunks.

    `table_atomic` overrides the ``RQ_TABLE_ATOMIC`` environment flag; ``None``
    (the default) reads the flag, which itself defaults to False.
    """
    atomic_on = flags.table_atomic() if table_atomic is None else bool(table_atomic)

    chunks: list[dict[str, Any]] = []
    for block in doc["blocks"]:
        words = block["text"].split()
        if not words:
            continue
        is_atomic = atomic_on and block.get("block_type") in ATOMIC_BLOCK_TYPES
        spans = [(0, len(words))] if is_atomic else _sliding_spans(len(words))
        for i, (s, e) in enumerate(spans):
            sub = " ".join(words[s:e])
            # char offset of this sub-chunk within the source block
            prefix_chars = len(" ".join(words[:s])) + (1 if s else 0)
            rec = {
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
            }
            # Structural table cells (Phase 4a) belong to the whole table block —
            # carry them onto EVERY chunk of that block so Stage 5's structural
            # binding can reach them regardless of which sub-chunk grounds a claim.
            if block.get("table_cells"):
                rec["table_cells"] = block["table_cells"]
                rec["table_caption"] = block.get("table_caption") or ""
            if is_atomic:
                # Only written on the atomic path, so a flag-off run produces
                # byte-identical records to every run before EXP-LATEX-01.
                rec["table_atomic"] = True
                rec["table_n_words"] = len(words)
                rec["table_oversized"] = len(words) > CHUNK_WORDS
                rec["table_over_embed_soft_limit"] = len(words) > EMBED_WORD_SOFT_LIMIT
                # Caption travels with the chunk even when the structural parse
                # produced no cells (fallback_pdf tables), so an oversized chunk
                # is never an anonymous wall of numbers.
                if "table_caption" not in rec:
                    rec["table_caption"] = block.get("table_caption") or ""
            chunks.append(rec)
    return chunks
