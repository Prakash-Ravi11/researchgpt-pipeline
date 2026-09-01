"""P3 - structured evidence extraction with deterministic verification.

LLM proposes {value, verbatim evidence_span, is_explicit}; then a deterministic
check confirms the span really occurs in a retrieved chunk and binds it to that
chunk's provenance. An unverifiable span => UNSUPPORTED (never EXPLICIT).
No value => MISSING. The LLM cannot manufacture provenance.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from .schema import (evidence_item, EXPLICIT, MISSING, INFERRED, UNSUPPORTED,
                     FULLTEXT_ONLY_FIELDS)

FIELD_PROMPT = {
    "dataset": "the dataset(s) / benchmark(s) / collected data the paper's own experiments are run on",
    "metrics": "the evaluation metric(s) the paper uses to measure performance",
    "results": "the paper's main quantitative result(s) - concrete numbers/scores the authors report for their own method",
    "method": "the core technical method/approach the paper proposes",
    "limitations": "limitations or weaknesses of the work (author-stated or clearly evident)",
}

SYS = (
    "You extract ONE field from a research-paper excerpt for a literature review. "
    "You must ground every answer in a verbatim quote from the provided CONTEXT. "
    "Never use outside knowledge. If the CONTEXT does not contain the field, say so. "
    'Respond with ONLY a JSON object: '
    '{"value": <string or null>, "evidence_span": <verbatim quote <=300 chars from CONTEXT, or null>, '
    '"is_explicit": <true if the quote states it directly, false if you had to infer>}'
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _span_in_chunks(span: str, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the chunk whose text contains `span` (exact-normalized or >=0.8 token overlap)."""
    ns = _norm(span)
    if len(ns) < 8:
        return None
    for c in chunks:
        if ns in _norm(c["text"]):
            return c
    st = set(ns.split())
    if len(st) < 3:
        return None
    for c in chunks:
        ct = set(_norm(c["text"]).split())
        if len(st & ct) / len(st) >= 0.8:
            return c
    return None


def call_ollama(base_url: str, model: str, sys_prompt: str, user: str,
                temperature: float = 0.1, timeout: int = 180, num_ctx: int = 6144) -> dict | None:
    payload = {
        "model": model, "stream": False, "format": "json",
        "messages": [{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": user}],
        "options": {"temperature": temperature, "num_ctx": num_ctx, "seed": 42},
    }
    for attempt in range(2):
        try:
            r = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout)
            r.raise_for_status()
            content = r.json()["message"]["content"].strip()
            m = re.search(r"\{.*\}", content, re.DOTALL)
            return json.loads(m.group(0) if m else content)
        except Exception:
            if attempt == 1:
                return None
            time.sleep(1)
    return None


def _build_context(chunks: list[dict[str, Any]], max_words: int = 1600) -> str:
    parts, used = [], 0
    for c in chunks:
        w = c["text"].split()
        if used + len(w) > max_words:
            w = w[: max_words - used]
        parts.append(f"[section={c['section']} loc={c['page_or_node']}]\n" + " ".join(w))
        used += len(w)
        if used >= max_words:
            break
    return "\n\n".join(parts)


def extract_field(paper_id: str, field: str, chunks: list[dict[str, Any]],
                  doc_repr: str, llm_cfg: dict[str, Any]) -> dict[str, Any]:
    item = evidence_item(field)
    item["paper_id"] = paper_id

    # abstention-by-construction: full-text-only fields with no body chunks
    if not chunks or (field in FULLTEXT_ONLY_FIELDS and doc_repr == "abstract"):
        item["evidence_status"] = MISSING
        item["abstain_reason"] = "no_full_text_evidence_available"
        return item

    ctx = _build_context(chunks)
    user = (f"FIELD: {FIELD_PROMPT[field]}\n\nCONTEXT:\n{ctx}\n\n"
            f"Extract the field strictly from the CONTEXT above.")
    resp = call_ollama(llm_cfg["base_url"], llm_cfg["model"], SYS, user,
                       temperature=llm_cfg.get("temperature", 0.1))
    if resp is None:
        item["evidence_status"] = UNSUPPORTED
        item["abstain_reason"] = "llm_call_failed"
        return item

    value = resp.get("value")
    span = resp.get("evidence_span")
    is_explicit = bool(resp.get("is_explicit"))
    if isinstance(value, list):
        value = "; ".join(str(v) for v in value if v)
    item["value"] = value.strip() if isinstance(value, str) and value.strip() else None
    item["claim"] = item["value"]

    if not item["value"]:
        item["evidence_status"] = MISSING
        item["abstain_reason"] = "model_reported_not_present"
        return item

    match = _span_in_chunks(span, chunks) if isinstance(span, str) else None
    if match is None:
        item["evidence_status"] = UNSUPPORTED
        item["evidence_span"] = span if isinstance(span, str) else None
        item["abstain_reason"] = "evidence_span_not_found_in_retrieved_context"
        item["confidence"] = 0.2
        return item

    item["evidence_span"] = span.strip()
    item["source"] = match["source"]
    item["representation"] = match["representation"]
    item["section"] = match["section"]
    item["page_or_node"] = match["page_or_node"]
    item["_block_id"] = match["block_id"]  # exact provenance for attribution context lookup
    item["_matched_chunk_text"] = match["text"]
    item["provenance_valid"] = True
    item["evidence_status"] = EXPLICIT if is_explicit else INFERRED
    item["confidence"] = 0.85 if is_explicit else 0.55
    return item
