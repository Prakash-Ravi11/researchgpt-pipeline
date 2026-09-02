"""Meaningful numeric anchor rule — single source of truth.

A "meaningful numeric anchor" is a numeric token worth anchoring a quantitative
claim on: a decimal (``0.72``, ``94.9``), or an integer of two or more digits
(``2165``, ``37``).  A lone single digit is excluded — it is usually part of an
identifier (``BLEU-4``, ``GPT-4``, ``T3``).

``find_anchors`` additionally drops tokens that match the shape but are not
quantitative results: 4-digit years, bracketed reference ids (``[12]``), a
number right after ``Section`` / ``Table`` / ``Eq.`` / ``Figure`` / ``v`` /
``step`` / ..., and arXiv-id fragments (``2401.01234``).

This rule was previously duplicated in ``src/evidence/gate.py`` and in the
Test 2 / Test 3 harnesses; they now all import from here.  The behaviour here is
exactly what those copies did — see ``experiments/document_evidence_pipeline``
``anchor_neutrality_check.py``.

Note: there is deliberately NO single-digit-with-unit extension here.  That was
discussed as a possible Phase-5 change to the gate but was never adopted, so it
is not part of the rule.
"""
from __future__ import annotations

import re

# The core token: a decimal, or a >=2-digit integer.
NUMERIC_ANCHOR_RE = re.compile(r"\d+\.\d+|\b\d{2,}\b")

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_EXCLUDE_PREFIX_RE = re.compile(
    r"(section|sec\.?|equation|eq\.?|figure|fig\.?|table|tab\.?|appendix|"
    r"chapter|line|step|version|v)\s*$", re.I)
_ARXIV_FRAGMENT_RE = re.compile(r"\d{4}\.\d{4,5}$")

# preceding-context window inspected by find_anchors, and how much of it the
# section/table/equation prefix check looks at (kept identical to the previous
# in-harness implementation).
_BEFORE_WINDOW = 20
_PREFIX_WINDOW = 14


def is_meaningful_anchor(value: str, before: str = "", inside_brackets: bool = False) -> bool:
    """True if ``value`` (already matched by ``NUMERIC_ANCHOR_RE``) is a real
    quantitative anchor rather than a year, a bracketed reference id, a
    section/table/equation number, or an arXiv-id fragment.

    ``before`` is the text immediately preceding the match (caller supplies as
    much or as little as it wants; only the last ``_PREFIX_WINDOW`` chars are
    used for the prefix check, and ``before + value`` for the arXiv check).
    """
    if _YEAR_RE.match(value):
        return False
    if inside_brackets:
        return False
    if _EXCLUDE_PREFIX_RE.search(before[-_PREFIX_WINDOW:]):
        return False
    if _ARXIV_FRAGMENT_RE.search(before + value):
        return False
    return True


def find_anchors(text: str) -> list[tuple[str, int]]:
    """Every meaningful numeric anchor in ``text`` as ``(value, start_offset)``."""
    out: list[tuple[str, int]] = []
    for m in NUMERIC_ANCHOR_RE.finditer(text):
        s = m.start()
        before = text[max(0, s - _BEFORE_WINDOW):s]
        lb, rb = text.rfind("[", 0, s), text.rfind("]", 0, s)
        if is_meaningful_anchor(m.group(0), before, inside_brackets=(lb > rb)):
            out.append((m.group(0), s))
    return out


def anchor_values(value: str) -> set[str]:
    """The bare set of anchor tokens in a short value string (no year / ref-id
    exclusion — this is what the evidence gate applies to an already-extracted
    field value, where those exclusions are not relevant)."""
    return set(NUMERIC_ANCHOR_RE.findall(value or ""))
