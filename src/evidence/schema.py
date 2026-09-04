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
REPR_LATEX = "latex"          # arXiv e-print source — CONTENT/TABLES/STRUCTURE ONLY.
                              # Identity + metadata never come from here (S2ORC: LaTeX
                              # metadata is worse than PDF-derived). See acquire.py
                              # `identity_validate` guard and semantic_scholar.py.
REPR_HTML = "html"
REPR_ABSTRACT = "abstract"
REPR_NONE = "none"

# Ranking of structured full-text representations, most-structured first. The
# acquisition resolver tries candidates in this order: JATS/XML (no table-structure
# collapse at all) > arXiv LaTeX e-print (real tabular/\caption/\multicolumn) >
# PDF (PyMuPDF keeps digits + page provenance but collapses table structure —
# only ~9% of table-resident values stay context-bindable).
STRUCTURED_REPR_RANK = {REPR_JATS: 0, REPR_LATEX: 1, REPR_PDF: 2}

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
        if rec.get("representation_type") not in (REPR_JATS, REPR_PDF, REPR_LATEX, REPR_HTML):
            problems.append("FULL_TEXT without a document representation")
        # content/identity split: a LaTeX representation is only valid if its
        # identity was established from something OTHER than the LaTeX source.
        if rec.get("representation_type") == REPR_LATEX:
            src = rec.get("identity_validation", {}).get("signals", {}).get("identity_source")
            if src not in ("arxiv_pdf", "semantic_scholar"):
                problems.append("REPR_LATEX identity_validation.signals.identity_source "
                                f"must be arxiv_pdf|semantic_scholar, got {src!r}")
    return problems


def structured_table(*, table_id: str, paper_id: str, source: str, representation: str,
                     section: str | None, caption: str, cells: list[dict[str, Any]],
                     parse_status: str, fallback: str | None, notes: list[str] | None = None,
                     raw_text: str = "") -> dict[str, Any]:
    """ONE canonical shape for a parsed table, emitted identically by the LaTeX
    e-print path and the Europe PMC JATS path (Phase 5's gate consumes this — two
    shapes would mean two code paths in the gate).

    `raw_text` is the FULL verbatim cell content of the table — every value,
    including cells whose structural parsing failed. It is the parity guarantee:
    structured `cells` are additional metadata layered on top of `raw_text`, never
    a replacement for it (Phase-4b M1: a value the PDF path keeps must also survive
    here). `cells` carries value + column_header + row_label + caption + section
    for the subset that parsed cleanly.

    parse_status: "parsed" | "partial" | "fallback_pdf" (fallback_pdf now means
    "no structured cells" — the value text still ships via raw_text).
    """
    return {
        "table_id": table_id,
        "paper_id": paper_id,
        "source": source,
        "representation": representation,
        "section": section,
        "caption": caption,
        "n_cells": len(cells),
        "cells": cells,                 # [{value, column_header, row_label, caption, section, ...}]
        "raw_text": raw_text,           # full verbatim cell content — never dropped
        "parse_status": parse_status,
        "fallback": fallback,
        "notes": notes or [],
    }


def table_cell(*, value: str, column_header: str, row_label: str,
               caption: str, section: str | None,
               row: int, col: int, spans: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "value": value.strip(),
        "column_header": column_header.strip(),
        "row_label": row_label.strip(),
        "caption": caption.strip(),
        "section": section,
        "row": row,
        "col": col,
        "spans": spans or {},          # {"colspan": n} / {"rowspan": n} when \multicolumn/\multirow
    }


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
