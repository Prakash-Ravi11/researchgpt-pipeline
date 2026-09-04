"""Stage-2 parity gate for the LaTeX representation.

RULE (Phase-4b): structured cells are metadata layered on top of the text, never a
replacement for it. Every numeric value the PDF path preserves must also survive
the LaTeX path. This module turns that from an aspiration into an enforced check:
if per-paper verbatim survival of the ground-truth numeric values is lower under
LaTeX than under the PDF, the paper FALLS BACK to the PDF representation and the
two survival figures are recorded in provenance.

Ground truth = the meaningful-numeric-anchor rule from src.evidence.anchors (the
same rule the gate and Test 2 use), applied to the LaTeX body.
"""
from __future__ import annotations

import re
from typing import Any

from .anchors import NUMERIC_ANCHOR_RE

_COMMENT = re.compile(r"(?<!\\)%.*")
_BEGIN_DOC = re.compile(r"\\begin\s*\{document\}")
_END_DOC = re.compile(r"\\end\s*\{document\}")
# strip preamble noise that is not article content (lengths, version strings, …)
_PREAMBLE_NOISE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|def|setlength|setcounter|"
    r"usepackage|documentclass|geometry|hypersetup|definecolor|DeclareMathOperator)"
    r"\b[^\n]*", re.I)

# tolerance default: strict parity — LaTeX survival must be >= PDF survival.
DEFAULT_PARITY_TOLERANCE = 0.0


def latex_body(latex: str) -> str:
    s = _COMMENT.sub("", latex)
    m = _BEGIN_DOC.search(s)
    if m:
        s = s[m.end():]
    e = _END_DOC.search(s)
    if e:
        s = s[:e.start()]
    return _PREAMBLE_NOISE.sub(" ", s)


_TABLE_ENV = re.compile(
    r"\\begin\{(?:tabular\*?|tabularx|array|longtable|table\*?|threeparttable|"
    r"sidewaystable)\}.*?\\end\{(?:tabular\*?|tabularx|array|longtable|table\*?|"
    r"threeparttable|sidewaystable)\}", re.S)
_CAPTION = re.compile(r"\\caption\*?\s*(?:\[[^\]]*\])?\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


def _numbers_by_location(latex_source: str) -> dict[str, list[str]]:
    """Numeric-anchor occurrences split table / caption / prose — the same three
    buckets Phase-4b M1 reports, computed from the LaTeX source without importing
    the experiment harness."""
    body = latex_body(latex_source)
    table_spans = [m.span() for m in _TABLE_ENV.finditer(body)]
    cap_spans = [m.span() for m in _CAPTION.finditer(body)]

    def loc(pos: int) -> str:
        if any(a <= pos < b for a, b in cap_spans):
            return "caption"
        if any(a <= pos < b for a, b in table_spans):
            return "table"
        return "prose"

    out: dict[str, list[str]] = {"table": [], "caption": [], "prose": [], "all": []}
    for m in NUMERIC_ANCHOR_RE.finditer(body):
        out[loc(m.start())].append(m.group(0))
        out["all"].append(m.group(0))
    return out


def ground_truth_numbers(latex_source: str) -> list[str]:
    """Every numeric-anchor token OCCURRENCE in the LaTeX body, NOT deduped
    (occurrence-weighted, matching the Phase-4b M1 verbatim-lax metric)."""
    return _numbers_by_location(latex_source)["all"]


def verbatim_survival(gt_values: list[str], block_texts: list[str]) -> float:
    """Fraction of ground-truth value occurrences that appear verbatim SOMEWHERE
    in the representation's block text (verbatim-lax — 'is the number present at
    all'). Distinct values are cached so 50 repeats cost one substring scan."""
    if not gt_values:
        return 1.0
    joined = "\n".join(block_texts)
    present: dict[str, bool] = {}
    hit = 0
    for v in gt_values:
        if v not in present:
            present[v] = v in joined
        hit += present[v]
    return hit / len(gt_values)


def check_parity(latex_source: str, latex_blocks: list[dict[str, Any]],
                 pdf_blocks: list[dict[str, Any]],
                 tolerance: float = DEFAULT_PARITY_TOLERANCE) -> dict[str, Any]:
    """Compare verbatim survival LaTeX vs PDF for one paper.

    Returns {passed, latex_survival, pdf_survival, n_ground_truth, tolerance,
    reason}. `passed` is False when latex_survival + tolerance < pdf_survival —
    the caller then falls back to the PDF representation for this paper.

    The gate reads `text` PLUS `table_raw_text` (Phase-4b Task 2 split the verbatim
    cell dump out of the extractor-visible `text`; the gate still needs every
    value, so it reads the raw dump here). What the extractor sees is `text` only.
    """
    by_loc = _numbers_by_location(latex_source)
    lx_txt = [b["text"] + " " + (b.get("table_raw_text") or "") for b in latex_blocks]
    pf_txt = [b["text"] for b in pdf_blocks]
    per = {}
    worst = []
    for loc in ("all", "table", "prose", "caption"):
        gt = by_loc[loc]
        if not gt:
            continue
        lx = verbatim_survival(gt, lx_txt)
        pf = verbatim_survival(gt, pf_txt)
        per[loc] = {"latex": round(lx, 4), "pdf": round(pf, 4), "n": len(gt)}
        if lx + tolerance < pf:
            worst.append(f"{loc}({lx:.3f}<{pf:.3f})")
    passed = not worst
    return {
        "passed": bool(passed),
        "latex_survival": per.get("all", {}).get("latex"),
        "pdf_survival": per.get("all", {}).get("pdf"),
        "per_location": per,
        "n_ground_truth": len(by_loc["all"]),
        "tolerance": tolerance,
        "reason": "ok" if passed else "below parity on: " + ", ".join(worst),
    }
