r"""Explicit, deterministic, rule-based claim extraction. No LLM.

The treatment for decision D3 (NO_CLAIMS_REACH_BINDER). The legacy path reads
free-form `datasets` / `metrics` / `results` strings out of the frozen Stage-4
extraction cache; this module instead walks the paper's own body blocks and emits
one claim per sentence that carries a standalone numeric value.

CONTRACT — this is load-bearing, see STOP CONDITION 4.
`gate_paper` (gate.py:601-611) takes a dict whose `results` is ONE string, which
it re-splits with `_SENT = re.compile(r"(?<=[.!?])\s+")` and then filters to
sentences of >= 12 chars containing a digit. So this module:
  * splits body text with that SAME `_SENT` object, imported not copied;
  * emits only sentences of >= 12 chars containing a digit;
  * guarantees every emitted sentence ends in `.`/`!`/`?` so that joining them
    with a single space and re-splitting is exactly the identity;
  * asserts that round-trip itself in `build_record`.
The `sentence` recorded for a claim is therefore byte-identical to the string
`gate_paper` will iterate.

Nothing here decides anything about binding, grounding or attribution. It only
chooses which sentences are offered.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from src.evidence.gate import _SENT          # the gate's own sentence splitter

# ---- reason codes -----------------------------------------------------------
IN_REFERENCES = "IN_REFERENCES"
IN_ACKNOWLEDGMENTS = "IN_ACKNOWLEDGMENTS"
IN_TABLE_BLOCK = "IN_TABLE_BLOCK"
IN_CAPTION = "IN_CAPTION"
NO_NUMBER = "NO_NUMBER"
NUMBER_IS_LABEL = "NUMBER_IS_LABEL"
CITATION_MARKER = "CITATION_MARKER"
YEAR = "YEAR"
NUMBER_IN_NAME = "NUMBER_IN_NAME"

RULE_STANDALONE = "R1_STANDALONE_NUMERIC"

MIN_SENTENCE_CHARS = 12                       # gate.py:609
TERMINATORS = ".!?"

# ---- numeric token ---------------------------------------------------------
# optional sign (ASCII hyphen, plus, or U+2212 MINUS), integer part, optional
# decimal, optional scientific notation (1.2e-4 or 1.2 x 10^-4), optional
# percent/permille. A +/- error term is matched so "92.3 +/- 0.4" reads as one
# value rather than two.
_SIGN = r"[-+−]?"
_SCI = r"(?:\s*(?:[eE]|[×x*]\s*10\s*\^?)\s*[-+−]?\d+)?"
_ERR = r"(?:\s*[±]\s*\d+(?:\.\d+)?)?"
_PCT = r"(?:\s*[%‰])?"
NUMERIC_TOKEN_RE = re.compile(_SIGN + r"\d+(?:\.\d+)?" + _SCI + _ERR + _PCT)

_LABEL_BEFORE_RE = re.compile(
    r"(?:table|tab|fig|figure|eq|equation|section|sect|sec|appendix|appendices|"
    r"algorithm|alg|listing|step|chapter|part)\s*\.?\s*$", re.I)
_CAPTION_OPENER_RE = re.compile(r"^\s*(?:table|tab\.|figure|fig\.)\s*\d+", re.I)
_TABLE_MENTION_RE = re.compile(r"\b(?:tables?|tab\.)\s*([IVXLC]+|\d+)", re.I)
_BRACKET_RE = re.compile(r"\[[^\]\[]{0,40}\]")
_LETTER = re.compile(r"[A-Za-z]")

YEAR_LO, YEAR_HI = 1900, 2099


def _bracket_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _BRACKET_RE.finditer(text)]


def classify_number(text: str, start: int, end: int,
                    brackets: list[tuple[int, int]]) -> str | None:
    """Reason code disqualifying this numeric token, or None if it is standalone.

    Order is fixed so the result is deterministic: bracket citation, then an
    explicit label (Table 2), then digits inside a name (GPT-4), then a year.
    """
    tok = text[start:end]
    for b0, b1 in brackets:
        if start >= b0 and end <= b1:
            return CITATION_MARKER
    if _LABEL_BEFORE_RE.search(text[max(0, start - 24): start]):
        return NUMBER_IS_LABEL
    before = text[start - 1] if start else ""
    before2 = text[start - 2] if start >= 2 else ""
    after = text[end] if end < len(text) else ""
    if _LETTER.match(before or ""):
        return NUMBER_IN_NAME
    if before in "-_/" and _LETTER.match(before2 or ""):
        return NUMBER_IN_NAME
    if _LETTER.match(after or ""):
        return NUMBER_IN_NAME
    core = tok.strip()
    if re.fullmatch(r"\d{4}", core):
        if YEAR_LO <= int(core) <= YEAR_HI:
            return YEAR
    return None


def _section_reason(section: str | None, block_type: str | None,
                    sentence: str) -> str | None:
    sec = (section or "").lower()
    if "reference" in sec or "bibliograph" in sec:
        return IN_REFERENCES
    if "acknowledg" in sec:
        return IN_ACKNOWLEDGMENTS
    if block_type == "table":
        return IN_TABLE_BLOCK
    if block_type in ("figure_caption", "table_caption", "caption"):
        return IN_CAPTION
    if _CAPTION_OPENER_RE.match(sentence):
        return IN_CAPTION
    return None


def _terminated(s: str) -> str:
    """Guarantee the sentence survives a _SENT re-split as one unit."""
    return s if s and s[-1] in TERMINATORS else s + "."


def claim_id(paper_id: str, span: tuple[int, int]) -> str:
    h = hashlib.sha256(f"{paper_id}:{span[0]}:{span[1]}".encode("utf-8"))
    return h.hexdigest()[:16]


def extract(paper_id: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Walk the paper's blocks and split them into kept claims and rejections.

    Blocks, not chunks: the chunker overlaps by 40 words, which would emit the
    same sentence more than once.
    """
    claims: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []

    for b in blocks:
        text = b.get("text") or ""
        if not text.strip():
            continue
        section = b.get("section")
        btype = b.get("block_type")
        base = int(b.get("char_start") or 0)
        cursor = 0
        for raw in _SENT.split(text):
            # offset of this sentence inside the block's text
            idx = text.find(raw, cursor)
            if idx < 0:
                idx = cursor
            cursor = idx + len(raw)
            s = raw.strip()
            if not s:
                continue
            span = (base + idx, base + idx + len(raw))
            rec = {
                "claim_id": claim_id(paper_id, span),
                "paper_id": paper_id,
                "section": section,
                "block_type": btype,
                "page": b.get("page_or_node"),
                "block_id": b.get("block_id"),
                "sentence": _terminated(s),
                "char_span": [span[0], span[1]],
            }

            why = _section_reason(section, btype, s)
            if why is None and (not re.search(r"\d", s)
                                or len(_terminated(s)) < MIN_SENTENCE_CHARS):
                # no digit at all, or too short for gate_paper to iterate
                # (gate.py:609). Both are "there is no number here to claim".
                why = NO_NUMBER

            if why is not None:
                rejections.append({**rec, "reason_code": why})
                continue

            brackets = _bracket_spans(s)
            kept, reasons = [], []
            for m in NUMERIC_TOKEN_RE.finditer(s):
                r = classify_number(s, m.start(), m.end(), brackets)
                if r is None:
                    kept.append({"text": m.group(0).strip(),
                                 "span": [span[0] + m.start(), span[0] + m.end()]})
                else:
                    reasons.append(r)

            if not kept:
                # one reason code per rejected sentence, by fixed priority
                for cand in (NUMBER_IS_LABEL, CITATION_MARKER, YEAR, NUMBER_IN_NAME):
                    if cand in reasons:
                        rejections.append({**rec, "reason_code": cand})
                        break
                else:
                    rejections.append({**rec, "reason_code": NO_NUMBER})
                continue

            claims.append({
                **rec,
                "numeric_spans_raw": kept,
                "table_mentions_raw": [m.group(0) for m in _TABLE_MENTION_RE.finditer(s)],
                "rule_id": RULE_STANDALONE,
            })

    return {"paper_id": paper_id, "claims": claims, "rejections": rejections}


def build_record(paper_id: str, extraction: dict[str, Any]) -> dict[str, Any]:
    """The exact container `gate_paper` expects: a dict whose `results` is one
    string. Asserts the _SENT round-trip so a mismatch cannot reach the gate.
    """
    sentences = [c["sentence"] for c in extraction["claims"]]
    blob = " ".join(sentences)
    if sentences:
        back = [x.strip() for x in _SENT.split(blob.strip()) if x.strip()]
        kept = [x for x in back
                if len(x) >= MIN_SENTENCE_CHARS and re.search(r"\d", x)]
        if len(kept) != len(sentences):
            raise AssertionError(
                "explicit_claims: _SENT round-trip is not the identity — "
                f"emitted {len(sentences)} sentences, gate_paper would iterate "
                f"{len(kept)}. STOP CONDITION 4.")
    return {"paper_id": paper_id, "datasets": None, "metrics": None, "results": blob}


def claims_for_gate(paper_id: str, blocks: list[dict[str, Any]]):
    """(record for gate_paper, extraction detail). The dispatch entry point."""
    ex = extract(paper_id, blocks)
    return build_record(paper_id, ex), ex
