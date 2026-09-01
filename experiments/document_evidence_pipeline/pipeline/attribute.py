"""P4 - attribution: is a quantitative claim the authors' OWN result or a CITED one?

Deterministic, span-local. Looks at the sentence containing the evidence span
plus one sentence of left context, and weighs first-person / contribution
markers against citation / prior-work markers.
"""
from __future__ import annotations

import re

from .schema import OWN_PAPER, CITED_PAPER, UNKNOWN

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

_OWN = [
    re.compile(r"\b(we|our|us)\b", re.I),
    re.compile(r"\bthis (paper|work|study|approach|method|model|system)\b", re.I),
    re.compile(r"\b(propose|present|introduce|report|achieve|obtain|demonstrate)s?\b", re.I),
    re.compile(r"\bproposed (method|approach|model|system|framework)\b", re.I),
]
_CITED = [
    re.compile(r"\b[A-Z][A-Za-z\-]+ et al\.?", ),
    re.compile(r"\[\d{1,3}(?:,\s*\d{1,3})*\]"),
    re.compile(r"\((?:[A-Z][A-Za-z\-]+,?\s+)?\d{4}[a-z]?\)"),
    re.compile(r"\b(prior|previous|existing|earlier|related|baseline|reference)\s+"
               r"(work|works|method|methods|approach|approaches|study|studies|model|models|system|systems)\b", re.I),
    re.compile(r"\b(reported|achieved|obtained|proposed) by\b", re.I),
    re.compile(r"\b(compared (to|with)|versus|vs\.?)\b", re.I),
]


def _window(text: str, span: str) -> str:
    if not span or span not in text:
        # fall back to fuzzy: locate by first 40 chars
        key = span[:40] if span else ""
        idx = text.find(key) if key else -1
        if idx < 0:
            return span or ""
    else:
        idx = text.find(span)
    sents = _SENT_SPLIT.split(text)
    acc, pos = [], 0
    for i, s in enumerate(sents):
        if pos <= idx < pos + len(s) + 1:
            lo = max(0, i - 1)
            return " ".join(sents[lo:i + 2])
        pos += len(s) + 1
    return text[max(0, idx - 200): idx + 200]


def attribute_claim(context_text: str, evidence_span: str) -> dict:
    """Return {attribution, confidence, own_hits, cited_hits, window}."""
    win = _window(context_text or "", evidence_span or "")
    own = sum(1 for p in _OWN if p.search(win))
    cited = sum(1 for p in _CITED if p.search(win))

    # a comparison sentence that ALSO has first-person framing ("we outperform
    # X et al.'s 88%") - the number right next to "et al." is the cited one
    if cited and own:
        # if an "et al" / bracket cite sits within 60 chars of the span, call it CITED
        near = re.search(r"(et al\.?|\[\d|\(\d{4})", win)
        if near and evidence_span and evidence_span[:20] in win:
            gap = abs(win.find(evidence_span[:20]) - near.start())
            if gap <= 60:
                return {"attribution": CITED_PAPER, "confidence": 0.6,
                        "own_hits": own, "cited_hits": cited, "window": win[:300]}
        return {"attribution": UNKNOWN, "confidence": 0.4,
                "own_hits": own, "cited_hits": cited, "window": win[:300]}
    if own and not cited:
        return {"attribution": OWN_PAPER, "confidence": min(0.95, 0.6 + 0.1 * own),
                "own_hits": own, "cited_hits": cited, "window": win[:300]}
    if cited and not own:
        return {"attribution": CITED_PAPER, "confidence": min(0.95, 0.6 + 0.1 * cited),
                "own_hits": own, "cited_hits": cited, "window": win[:300]}
    return {"attribution": UNKNOWN, "confidence": 0.3,
            "own_hits": own, "cited_hits": cited, "window": win[:300]}
