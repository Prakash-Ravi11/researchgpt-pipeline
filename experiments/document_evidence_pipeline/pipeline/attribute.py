"""P4 - attribution: is a quantitative claim the authors' OWN result or a CITED one?

Deterministic, bounded, hierarchical. Escalates context only while the answer is
UNKNOWN and stops as soon as it is decisive:

  L1  sentence window around the evidence span
  L2  the whole surrounding paragraph/block
  L3  table / caption context (for numbers that live in a results table)
  L4  section-subject cue (a first-person results/method section makes a
      passive-voice number the paper's own) - only when the span's own
      sentence carries NO citation marker
  (author metadata is used throughout to discount self-citations)

Hard precision rule: a proper citation marker (Name et al. / [n] / (Author, year))
in the span's own sentence blocks OWN_PAPER. UNKNOWN is never upgraded to
OWN_PAPER just to raise recall.
"""
from __future__ import annotations

import re

from .schema import OWN_PAPER, CITED_PAPER, UNKNOWN

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

_OWN = [
    re.compile(r"\b(we|our|us|ours)\b", re.I),
    re.compile(r"\bthis (paper|work|study|approach|method|model|system|article)\b", re.I),
    re.compile(r"\bin this (study|paper|work|article)\b", re.I),
    re.compile(r"\bproposed (method|approach|model|system|framework|pipeline|architecture)\b", re.I),
    re.compile(r"\bthe proposed\b", re.I),
]
# strong, unambiguous contribution cues used for the section-subject escalation
_STRONG_OWN = [
    "we propose", "we present", "we introduce", "we develop", "we design",
    "we build", "we evaluate our", "we report", "we conduct", "we perform",
    "our method", "our approach", "our model", "our framework", "our system",
    "our proposed", "our results", "our experiments", "our pipeline",
    "in this paper we", "in this work we", "this paper proposes", "this work proposes",
    "this study proposes", "we achieve", "we obtain",
]
# weak "own table" cue - only counts toward the section-subject escalation
_OWN_WEAK = re.compile(
    r"\b(table|fig\.?|figure)\s*\d+\s*(shows|presents|reports|summari[sz]es|illustrates|demonstrates|lists)\b",
    re.I)

# proper citation markers (real evidence of a CITED claim). Deliberately NOT
# matching a bare "Foo and Bar" - that hits "Precision and Recall",
# "Question and Answering", etc. "Smith and Jones (2020)" is still caught by the
# year-paren alternative.
_CITE_MARKER = re.compile(
    r"[A-Z][A-Za-z\-]+ et al\.?"                                  # Smith et al.
    r"|\[\d{1,3}(?:\s*[,-]\s*\d{1,3})*\]"                          # [12] , [3-5]
    r"|\((?:[A-Z][A-Za-z\-]+(?:\s+(?:et al\.?|and [A-Z][A-Za-z\-]+))?,?\s+)?\d{4}[a-z]?\)"  # (Smith et al., 2021) / (2021)
)
_CITED_CONTEXT = [
    re.compile(r"\b(prior|previous|existing|earlier|related)\s+"
               r"(work|works|method|methods|approach|approaches|study|studies|model|models|system|systems|literature)\b",
               re.I),
    re.compile(r"\b(reported|achieved|obtained|proposed|introduced|developed) by\b", re.I),
    re.compile(r"\bunlike\s+\[", re.I),
    _CITE_MARKER,
]



def _strip_self_cites(text: str, own_surnames: set[str]) -> str:
    """Remove citation spans whose lead author is one of THIS paper's authors,
    so a self-reference in an own-result sentence isn't read as CITED."""
    # "our earlier work/study" is self-referential prior work, not a competitor
    text = re.sub(r"\b(our|we)\b[^.;]{0,30}?\b(prior|previous|earlier|recent|initial|past)\s+"
                  r"(work|works|study|studies|paper|papers|method|approach|model|version)\b",
                  " ", text, flags=re.I)
    if not own_surnames:
        return text
    def drop_etal(m: "re.Match[str]") -> str:
        return "" if m.group(1).lower() in own_surnames else m.group(0)
    text = re.sub(r"\(?([A-Z][A-Za-z\-]+)\s+et al\.?(?:,?\s*\d{4}[a-z]?)?\)?", drop_etal, text)
    text = re.sub(r"\(([A-Z][A-Za-z\-]+),?\s+\d{4}[a-z]?\)",
                  lambda m: "" if m.group(1).lower() in own_surnames else m.group(0), text)
    return text


def _sentences(text: str) -> list[str]:
    return _SENT_SPLIT.split(text or "")


def _locate(text: str, span: str) -> int:
    if not span:
        return -1
    i = text.find(span)
    if i >= 0:
        return i
    return text.find(span[:40]) if len(span) >= 8 else -1


def _window(text: str, span: str, before: int = 1, after: int = 1) -> str:
    idx = _locate(text, span)
    if idx < 0:
        return span or ""
    sents, pos = _sentences(text), 0
    for i, s in enumerate(sents):
        if pos <= idx < pos + len(s) + 1:
            return " ".join(sents[max(0, i - before): i + 1 + after])
        pos += len(s) + 1
    return text[max(0, idx - 220): idx + 220]


def _span_sentence(text: str, span: str) -> str:
    return _window(text, span, before=0, after=0)


def _own_surnames(names) -> set[str]:
    out = set()
    for n in names or []:
        parts = str(n).split()
        if parts:
            out.add(parts[-1].lower())
    return out


def _count(text: str, own_surnames: set[str]) -> tuple[int, int, bool]:
    """(own_hits, cited_hits, has_proper_cite_marker) after discounting self-cites."""
    t = _strip_self_cites(text, own_surnames)
    own = sum(1 for p in _OWN if p.search(t))
    proper = bool(_CITE_MARKER.search(t))
    cited = sum(1 for p in _CITED_CONTEXT if p.search(t))
    return own, cited, proper


def _decide(own: int, cited: int, proper: bool, span: str, window: str,
            base_conf: float) -> dict | None:
    # citation marker hugging the number -> the number is the cited one
    if proper and span:
        mk = _CITE_MARKER.search(window)
        key = span[:20]
        if mk and key in window and abs(window.find(key) - mk.start()) <= 70:
            return _r(CITED_PAPER, min(0.85, base_conf + 0.15), own, cited, window)
    if own and not cited:
        return _r(OWN_PAPER, min(0.9, base_conf + 0.05 * own), own, cited, window)
    if cited and not own:
        return _r(CITED_PAPER, min(0.9, base_conf + 0.05 * cited), own, cited, window)
    if own and cited:
        # both present, no hugging cite -> genuinely ambiguous at this level
        return None
    return None


def _r(attr, conf, own, cited, window, level=None):
    d = {"attribution": attr, "confidence": round(conf, 2),
         "own_hits": own, "cited_hits": cited, "window": (window or "")[:320]}
    if level:
        d["level"] = level
    return d


def attribute_claim(context_text: str, evidence_span: str, *,
                    block_type: str | None = None, section: str | None = None,
                    section_context: str | None = None,
                    own_author_surnames=None) -> dict:
    """Escalating deterministic attribution. `context_text` = the source block
    (paragraph). `section_context` = concatenated text of the whole section."""
    span = evidence_span or ""
    surn = _own_surnames(own_author_surnames)
    ctx = context_text or ""

    # L1 - sentence window
    win1 = _window(ctx, span, before=1, after=1)
    o, c, p = _count(win1, surn)
    d = _decide(o, c, p, span, win1, base_conf=0.6)
    if d:
        d["level"] = "sentence"
        return d

    # L2 - whole paragraph/block
    o, c, p = _count(ctx, surn)
    d = _decide(o, c, p, span, ctx, base_conf=0.5)
    if d and d["attribution"] != UNKNOWN:
        d["level"] = "paragraph"
        return d

    # L3 - table / caption context
    looks_tabular = (block_type in ("table", "figure_caption")
                     or re.match(r"\s*(table|fig\.?|figure)\s*\d", ctx, re.I))
    if looks_tabular:
        head = ctx[:400].lower()
        cap_says_ours = any(k in head for k in ("proposed", "our ", "ours", "full model",
                                                "complete model", "this work"))
        span_sent = _span_sentence(ctx, span).strip().lower()
        row_is_ours = bool(re.match(r"(proposed|ours|our |full model|complete|w/ all|all components)", span_sent))
        row_is_cited = bool(re.match(r"(\[\d|[A-Z][A-Za-z\-]+ et al)", _span_sentence(ctx, span).strip()))
        if row_is_cited and not row_is_ours:
            return _r(CITED_PAPER, 0.6, 0, 1, ctx[:320], level="table_row")
        if cap_says_ours and row_is_ours:
            return _r(OWN_PAPER, 0.6, 1, 0, ctx[:320], level="table_row")

    # L4 - section-subject cue (passive-voice own result in a first-person section)
    sec_ok = (section or "") in ("results", "experimental_setup", "method",
                                 "discussion", "conclusion", "abstract")
    sc = (section_context or ctx).lower()
    strong = sum(1 for k in _STRONG_OWN if k in sc) + (1 if _OWN_WEAK.search(section_context or ctx) else 0)
    span_sent = _span_sentence(ctx, span)
    if sec_ok and strong >= 2 and not _CITE_MARKER.search(span_sent):
        return _r(OWN_PAPER, 0.55, 0, 0, win1, level="section_subject")

    return _r(UNKNOWN, 0.3, o, c, win1, level="exhausted")
