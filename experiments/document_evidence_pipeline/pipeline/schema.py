"""Canonical schemas + status vocabularies for the document-evidence pipeline.

Deliberately plain dicts (JSON-first), with builder/validator helpers so every
module emits the same shape and the benchmark can assert on it.
"""
from __future__ import annotations

import re
from typing import Any

# --- acquisition status -----------------------------------------------------
FULL_TEXT = "FULL_TEXT"
ABSTRACT_ONLY = "ABSTRACT_ONLY"
METADATA_ONLY = "METADATA_ONLY"
NO_ACCESSIBLE_FULL_TEXT = "NO_ACCESSIBLE_FULL_TEXT"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
ACQ_STATUSES = {FULL_TEXT, ABSTRACT_ONLY, METADATA_ONLY, NO_ACCESSIBLE_FULL_TEXT, FAILED, BLOCKED}

# --- representation type ---------------------------------------------------
REPR_JATS = "jats_xml"
REPR_PDF = "pdf"
REPR_HTML = "html"
REPR_ABSTRACT = "abstract"
REPR_NONE = "none"

# --- evidence status -----------------------------------------------------
EXPLICIT = "EXPLICIT"
MISSING = "MISSING"
INFERRED = "INFERRED"
UNSUPPORTED = "UNSUPPORTED"
EVIDENCE_STATUSES = {EXPLICIT, MISSING, INFERRED, UNSUPPORTED}

# --- attribution -------------------------------------------------------
OWN_PAPER = "OWN_PAPER"
CITED_PAPER = "CITED_PAPER"
UNKNOWN = "UNKNOWN"
ATTRIBUTIONS = {OWN_PAPER, CITED_PAPER, UNKNOWN}

# --- final per-field verdict ------------------------------------------------
RETURNED = "RETURNED"
ABSTAINED = "ABSTAINED"

EVIDENCE_FIELDS = ["dataset", "metrics", "results", "method", "limitations"]
# fields that genuinely require article body text (not answerable from an abstract)
FULLTEXT_ONLY_FIELDS = {"dataset", "metrics", "results"}


def canonical_acquisition_record(paper_id: str) -> dict[str, Any]:
    """Empty canonical acquisition record - section 5 of the brief."""
    return {
        "paper_id": paper_id,
        "doi": None,
        "other_identifiers": {},
        "source": None,                 # which provider supplied the accepted representation
        "candidate_url": None,
        "representation_type": REPR_NONE,
        "status": FAILED,
        "identity_validation": {"checked": False, "passed": False, "signals": {}, "reason": None},
        "content_validation": {"checked": False, "passed": False, "reason": None, "metrics": {}},
        "full_text_confidence": 0.0,
        "latency_ms": None,
        "failure_reason": None,
        "provenance": {},               # source -> representation -> document identity
        "candidates_considered": [],    # audit trail of every source tried
    }


def evidence_item(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "value": None,
        "claim": None,
        "paper_id": None,
        "source": None,
        "representation": None,
        "section": None,
        "page_or_node": None,
        "evidence_span": None,
        "confidence": 0.0,
        "evidence_status": MISSING,
        "attribution": UNKNOWN,
        "attribution_confidence": 0.0,
        "provenance_valid": False,
        "final": ABSTAINED,
        "abstain_reason": None,
    }


def validate_acquisition_record(rec: dict[str, Any]) -> list[str]:
    problems = []
    if rec.get("status") not in ACQ_STATUSES:
        problems.append(f"bad status {rec.get('status')!r}")
    if rec.get("status") == FULL_TEXT:
        if not rec.get("identity_validation", {}).get("passed"):
            problems.append("FULL_TEXT without passed identity_validation")
        if not rec.get("content_validation", {}).get("passed"):
            problems.append("FULL_TEXT without passed content_validation")
        if rec.get("representation_type") not in (REPR_JATS, REPR_PDF, REPR_HTML):
            problems.append("FULL_TEXT without a document representation")
    return problems


_WORD = re.compile(r"[a-z0-9]+")


def norm_tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def title_similarity(a: str, b: str) -> float:
    """Symmetric token containment - robust to subtitle/casing/punctuation noise."""
    ta, tb = set(norm_tokens(a)) - _STOP, set(norm_tokens(b)) - _STOP
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb))


_STOP = {"a", "an", "the", "of", "for", "and", "or", "to", "in", "on", "with", "via",
         "using", "based", "toward", "towards", "from", "by", "at", "as", "is", "are"}
