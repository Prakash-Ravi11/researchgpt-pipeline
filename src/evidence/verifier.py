"""Deterministic evidence verifier for extracted paper metadata.

This module is intentionally lightweight and explicit: it does not pretend to
be a semantic judge. Instead, it validates whether extracted fields are
present, non-empty, and plausibly grounded in paper text using a narrow set of
cheap deterministic checks.

It is designed to satisfy the project's evidence-gating requirement without
requiring a heavy external model or hidden heuristics.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


VERIFIER_VERSION = "1.0"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(_clean_text(v) for v in value if v is not None)
    if isinstance(value, dict):
        return " ".join(f"{k}: {_clean_text(v)}" for k, v in value.items())
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            text = _clean_text(item)
            if text:
                out.append(text)
        return out
    text = _clean_text(value)
    return [text] if text else []


def _paper_text_coverage(title: str, paper_text: str, fields: dict[str, Any]) -> dict[str, Any]:
    text = (paper_text or "").lower()
    title_l = (title or "").lower()

    supported = []
    weak = []
    issues = []

    for field_name in ["summary", "problem_addressed", "method", "results", "key_findings"]:
        value = _clean_text(fields.get(field_name, ""))
        if not value:
            weak.append(field_name)
            issues.append(f"{field_name} is empty")
            continue

        # If the field is not referencing any paper-specific terms and the
        # paper-text is long enough, flag it as suspicious.
        if len(text) > 200 and len(value) > 40:
            # Require at least one token overlap with the paper text or title.
            overlap = False
            for token in re.findall(r"[a-z0-9]+", value.lower()):
                if token and len(token) >= 4 and (token in text or token in title_l):
                    overlap = True
                    break
            if not overlap:
                weak.append(field_name)
                issues.append(f"{field_name} appears unsupported by the paper text")
                supported.append(field_name)
                continue

        supported.append(field_name)

    datasets = _as_list(fields.get("datasets"))
    if datasets:
        supported.append("datasets")
    else:
        weak.append("datasets")
        issues.append("datasets are missing")

    metrics = _as_list(fields.get("metrics"))
    if metrics:
        supported.append("metrics")
    else:
        weak.append("metrics")
        issues.append("metrics are missing")

    verdict = {
        "score": 10 if not weak else max(0, 10 - len(weak) * 2),
        "supported": not weak,
        "issues": issues,
        "missing_or_weak_fields": weak,
        "corrected_summary": _clean_text(fields.get("summary")) or "",
        "corrected_key_findings": _clean_text(fields.get("key_findings")) or "",
        "corrected_datasets": datasets,
    }
    return verdict


def verify_evidence(paper: dict, paper_text: str) -> dict:
    """Return a field-level verification result for one paper.

    Expected input shape is a single paper record from the Stage 4 output.
    Output matches the schema expected by the project's audit harness and CLI
    flow.
    """
    if not isinstance(paper, dict):
        return {
            "score": 0,
            "supported": False,
            "issues": ["paper record is not a dictionary"],
            "missing_or_weak_fields": ["summary", "method", "datasets", "key_findings"],
            "corrected_summary": "",
            "corrected_key_findings": "",
            "corrected_datasets": [],
        }

    title = paper.get("title") or paper.get("paper_id") or ""
    return _paper_text_coverage(title, paper_text, paper)


def verify_papers(records: list[dict], papers_by_id: dict[str, dict]) -> list[dict]:
    """Verify many records and return a list of per-paper verification results."""
    results = []
    for paper in records:
        pid = paper.get("paper_id") or paper.get("title") or "unknown"
        raw = papers_by_id.get(pid, "")
        if isinstance(raw, dict):
            paper_text = raw.get("text") or raw.get("paper_text") or ""
        else:
            paper_text = str(raw or "")
        results.append({"paper_id": pid, **verify_evidence(paper, paper_text)})
    return results


def _load_json(path: str | Path) -> Any:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def verify_directory(path: str | Path) -> dict:
    """Convenience entrypoint for an entire processed output directory."""
    processed_dir = Path(path)
    summaries = _load_json(processed_dir / "paper_summaries.json") or []
    chunks = _load_json(processed_dir / "chunks.json") or []
    paper_texts = {}

    by_paper: dict[str, list[str]] = {}
    for chunk in chunks:
        by_paper.setdefault(chunk.get("paper_id"), []).append(chunk.get("text", ""))

    for pid, texts in by_paper.items():
        paper_texts[pid] = " ".join(texts)

    verified = verify_papers(summaries, paper_texts)
    total = len(verified)
    avg_score = sum(v.get("score", 0) for v in verified) / total if total else 0
    supported = sum(1 for v in verified if v.get("supported"))
    return {
        "total": total,
        "average_score": round(avg_score, 2),
        "supported_count": supported,
        "results": verified,
        "version": VERIFIER_VERSION,
    }
