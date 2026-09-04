"""Stage 5 — evidence gate: attribution + confidence + abstention.

Runs AFTER Stage-4 extraction. For every extracted Dataset / Metric / Result it
finds a verbatim supporting span in that paper's provenance-bearing chunks,
runs hierarchical attribution (metrics/results only), applies a value sanity
check, and decides RETURNED vs ABSTAINED. Papers without validated full text
have Dataset/Metric/Result forced to NOT_FOUND.

Writes `paper_evidence.json` (full detail) and rewrites `paper_summaries.json`
so the gated `datasets` / `metrics` lists and `results` string contain only
RETURNED evidence — Stage 6 synthesis then consumes verified evidence only.

Only active when config['evidence_grounding']['enabled'] is true.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .anchors import NUMERIC_ANCHOR_RE as _NUMVAL
from .attribute import attribute_claim
from .schema import (EXPLICIT, UNSUPPORTED, MISSING, RETURNED, ABSTAINED,
                     OWN_PAPER, CITED_PAPER, UNKNOWN, FULL_TEXT)

_WORD = re.compile(r"[a-z0-9][a-z0-9\-]*")
_STOP = {"the", "and", "for", "with", "from", "this", "that", "using", "based",
         "our", "we", "of", "in", "on", "to", "a", "an", "is", "are", "was",
         "were", "by", "as", "data", "dataset", "datasets", "set", "sets"}
_METRIC_TOKENS = {
    "accuracy", "precision", "recall", "f1", "f-score", "dice", "iou", "auc",
    "auroc", "auprc", "bleu", "rouge", "meteor", "mae", "rmse", "mse", "mape",
    "nll", "perplexity", "mrr", "ndcg", "map", "hit", "em", "exact", "match",
    "correlation", "pearson", "spearman", "kappa", "sensitivity", "specificity",
    "score", "rate", "error", "loss", "latency", "throughput", "faithfulness",
}
_NUM = re.compile(r"\d")
_SENT = re.compile(r"(?<=[.!?])\s+")
# _NUMVAL (the meaningful-numeric-anchor regex) is imported from src.evidence.anchors
# above — single source of truth shared with the Test 2 / Test 3 harnesses.


# --------------------------------------------------------------------------
# METRIC RANGE PLAUSIBILITY
#
# ATTRIBUTION answers "whose result is this"; BINDING answers "which result is
# this". The grounding check ("number + >=2 topical tokens co-occur in one
# chunk") verifies neither binding nor plausibility — a cross-row number, or a
# COUNT misread by Stage 4 as a metric value, co-occurs with the right tokens
# just as well. Test 2's cross-row probes: 4/7 RETURNED. "False OWN = 0" was
# never evidence of binding correctness.
#
# This is a narrow, one-directional plausibility check: when a claim NAMES a
# bounded metric, its asserted value must lie inside that metric's physical
# range, else the claim does not pass the gate. It never *accepts* anything the
# rest of the gate would reject, and it never fires on a value with no named
# metric (silent over-rejection would be worse than the bug it closes).
#
# Metric list derived from the two corpora's RETURNED metrics/results
# (canonical60 + data_test) plus the phase brief's explicit list. Only metrics
# with a FINITE upper bound are in the table. MAE / RMSE / MSE / MAPE /
# perplexity / Hausdorff (HD95) / PSNR / latency / throughput appear in the
# corpora but have no finite ceiling -> deliberately NOT range-checked.
#
# 0-1 vs 0-100 AMBIGUITY — decided rule (not a per-value guess): a
# percentage-family metric is reported in the literature on EITHER a 0-1 or a
# 0-100 scale. The gate accepts both and takes the plausible interval as
# [0, 100]. It does not infer which scale a given number uses; it only rejects
# the physically impossible (< 0, or > 100). Correlation-family (Pearson /
# Spearman / Kendall tau / Cohen kappa) -> [-100, 100] by the same logic.
_PCT_FAMILY = (
    "dice", "dice score", "dice coefficient", "dice index", "dsc",
    "f1", "f1 score", "f1-score", "f-score", "f score", "micro f1", "macro f1",
    "accuracy", "acc", "balanced accuracy", "top-1 accuracy", "top-5 accuracy",
    "precision", "recall", "iou", "miou", "jaccard", "jaccard index",
    "auroc", "auprc", "auc", "auc-roc", "roc-auc", "auc roc", "ap",
    "sensitivity", "specificity", "tpr", "tnr",
    "ndcg", "map", "mrr", "hit rate", "hits", "success rate", "pass rate", "pass@1",
    "bleu", "sacrebleu", "rouge", "rouge-l", "rouge-1", "rouge-2", "rougel",
    "meteor", "chrf", "ter", "exact match", "em", "ssim", "faithfulness",
    "relevance", "win rate", "coverage",
)
_CORR_FAMILY = ("pearson", "spearman", "kendall", "kendall tau", "kappa",
                "cohen kappa", "cohen's kappa", "correlation", "r2", "r^2",
                "r-squared", "matthews correlation", "mcc")
# {canonical metric name -> (lo, hi)}
_METRIC_RANGES: dict[str, tuple[float, float]] = {
    **{m: (0.0, 100.0) for m in _PCT_FAMILY},
    **{m: (-100.0, 100.0) for m in _CORR_FAMILY},
}
# match a metric name, tolerating an @k / -n / -L suffix and a trailing
# "score|coefficient|index|rate" word. Longest names first so "dice coefficient"
# wins over "dice".
_METRIC_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in
                      sorted(_METRIC_RANGES, key=len, reverse=True)) +
    r")\b(?:\s*@\s*\d+|-\d+|-l\b|-1\b|-2\b)?(?:\s+(?:score|coefficient|index|rate|value))?",
    re.I)
# the value ADJACENT to a metric name: "F1 of 0.88", "dice = 94.9", "Dice: 3.1",
# "94.9% Dice", "Dice score 0.9". A number several words away (a sample count, a
# citation year) must NOT bind — silent over-rejection is worse than the bug.
_NUM_AFTER_RE = re.compile(
    r"^\s*(?:(?:of|is|was|reaches?|reached|at|=|:|~|>|<|>=|<=|about|around|nearly|up to)\s*)?"
    r"(-?\d+(?:\.\d+)?)\s*%?", re.I)
_NUM_BEFORE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%?\s*$")
_EPS = 1e-6


def _canon_metric(raw: str) -> str | None:
    """Map a matched metric phrase to a table key (drops @k / -n / trailing word)."""
    s = re.sub(r"\s*@\s*\d+|-\d+|-l\b|-1\b|-2\b", "", raw.lower()).strip()
    s = re.sub(r"\s+(?:score|coefficient|index|rate|value)$", "", s).strip()
    if s in _METRIC_RANGES:
        return s
    # "f1-score" / "rougel" etc. after suffix strip
    return s if s in _METRIC_RANGES else None


def metric_range_check(value: str) -> dict[str, Any] | None:
    """None  -> claim names no bounded metric, or every named-metric value is in
                range (nothing to do).
    dict('metric','value','interval','claim') -> a named metric's asserted value
                is outside its physical range; the claim must NOT pass the gate.
    """
    text = value or ""
    for nm in _METRIC_NAME_RE.finditer(text):
        metric = _canon_metric(nm.group(0))
        if metric is None:
            continue
        lo, hi = _METRIC_RANGES[metric]
        # the ADJACENT number only: "dice of 407" / "F1 = 0.88" (after) or
        # "94.9% Dice" / "0.9 Dice score" (before). A number that needs several
        # intervening words does not bind.
        ma = _NUM_AFTER_RE.match(text[nm.end(): nm.end() + 24])
        mb = _NUM_BEFORE_RE.search(text[max(0, nm.start() - 14): nm.start()])
        cand = ma or mb
        if cand is None:
            continue
        try:
            x = float(cand.group(1))
        except ValueError:
            continue
        if not (lo - _EPS <= x <= hi + _EPS):
            return {"metric": metric, "value": x, "interval": [lo, hi], "claim": text[:200]}
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _sig_tokens(s: str) -> set[str]:
    return {t for t in _WORD.findall((s or "").lower()) if len(t) >= 4 and t not in _STOP}


def _supporting_sentence(value: str, text: str) -> str:
    """The single sentence of `text` that best supports `value` — used as the
    stored evidence_span so the audit trail brackets the claim, not the whole
    chunk. Falls back to a char window, then the value itself."""
    nv = _norm(value)
    sents = _SENT.split(text or "")
    if nv:
        for s in sents:
            if nv in _norm(s):
                return s.strip()
    # a sentence carrying all the value's meaningful numbers is the tightest span
    nums = set(_NUMVAL.findall(value))
    if nums:
        for s in sents:
            if all(n in s for n in nums):
                return s.strip()
    toks = _sig_tokens(value)
    if toks:
        best, best_ov = "", 0.0
        for s in sents:
            stoks = set(_WORD.findall(_norm(s)))
            ov = len(toks & stoks) / len(toks)
            if ov > best_ov:
                best, best_ov = s, ov
        if best_ov >= 0.5:
            return best.strip()
    i = _norm(text).find(nv[:30]) if nv else -1
    if i >= 0:
        return (text[max(0, i - 140): i + 200]).strip()
    return value.strip()


def _ground(value: str, chunks: list[dict[str, Any]], *,
            field: str = "metrics") -> tuple[dict[str, Any], str] | None:
    """Return (chunk, supporting_sentence) for the chunk that verbatim-supports
    `value`, or None. A body chunk is preferred over the paper's own abstract
    when both match, since the abstract merely restates a body result.

    For `results` the value is an LLM *paraphrase* of the paper (Stage-4's
    `results` field is a summary, not a quote), so whole-sentence token overlap
    structurally under-matches. Instead we NUMBER-ANCHOR: every meaningful
    number in the paraphrase must appear verbatim in one chunk, and >=2 of the
    paraphrase's significant tokens must co-occur there. For `metrics` (short,
    near-verbatim values) the substring / >=0.8-token-containment check is kept.
    """
    nv = _norm(value)
    if len(nv) < 4:
        return None
    toks = _sig_tokens(value)
    nums = set(_NUMVAL.findall(value)) if field == "results" else set()

    def matches(c: dict[str, Any]) -> bool:
        ct = _norm(c.get("text", ""))
        if nv in ct:
            return True
        if nums:
            # number-anchored: all meaningful numbers verbatim in this chunk + local lexical support
            if all(n in c.get("text", "") for n in nums):
                return len(toks & set(_WORD.findall(ct))) >= 2
            return False
        if len(toks) < 2:
            return False
        return len(toks & set(_WORD.findall(ct))) / len(toks) >= 0.8

    hits = [c for c in chunks if matches(c)]
    if not hits:
        return None
    hits.sort(key=lambda c: (c.get("section") == "abstract",
                             c.get("section") not in ("results", "experimental_setup", "discussion")))
    chosen = hits[0]
    return chosen, _supporting_sentence(value, chosen.get("text", ""))


def _value_sane(field: str, value: str) -> bool:
    if field == "datasets":
        return bool(value and value.strip())
    v = (value or "").lower()
    return bool(_NUM.search(v)) or bool(_sig_tokens(v) & _METRIC_TOKENS)


def _evidence_item(field: str, value: str) -> dict[str, Any]:
    return {"field": field, "value": value, "evidence_span": None, "source": None,
            "representation": None, "section": None, "page_or_node": None,
            "block_id": None, "char_start": None, "char_end": None,
            "evidence_status": MISSING, "attribution": UNKNOWN,
            "attribution_confidence": 0.0, "confidence": 0.0,
            "provenance_valid": False, "final": ABSTAINED, "abstain_reason": None,
            "range_check": None, "structural_binding": None}


# --------------------------------------------------------------------------
# STRUCTURAL CELL BINDING  (Phase 5a — consumes Phase 4a's table_cells)
#
# ATTRIBUTION = "whose result is this". BINDING = "which result is this" — is the
# claimed number the value at the (row = subject, column = metric) cell it
# implies. Grounding ("number + >=2 topical tokens in one chunk") checks neither.
#
# Where a paper has a STRUCTURED representation (LaTeX e-print / JATS -> parsed
# table_cells on its chunks), a quantitative OWN claim is verified against the
# actual cell. Where only a collapsed PDF representation exists, structural
# binding CANNOT be verified — the claim is marked `unverifiable_binding` and is
# NOT returned as an OWN quantitative result (this reduces returned results on
# PDF-only papers; that reduction is a CORRECTION, like the abstract-vs-body one).
# --------------------------------------------------------------------------

_OWN_ROW = re.compile(
    r"\b(our[s]?|ours|proposed|the proposed|our method|our model|our approach|"
    r"our system|this work|this paper|full model|full|w/o|ablation)\b", re.I)
_SUBJECT_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9\-/\.\+ ]{1,34}?)\s+"
    r"(?:reports?|achiev\w*|obtain\w*|attain\w*|reach\w*|record\w*|get[s]?|"
    r"scor\w*|yield\w*|produc\w*|show\w*|ha[sd]|deliver\w*|report\w+ (?:a|an)|"
    r"=|:|of)\b", re.I)


def paper_table_cells(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distinct structured table cells across a paper's chunks (Phase 4a shape)."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for c in chunks:
        for cell in (c.get("table_cells") or []):
            k = (cell.get("row_label", ""), cell.get("column_header", ""),
                 str(cell.get("value", "")), cell.get("caption", ""))
            if k not in seen:
                seen.add(k)
                out.append(cell)
    return out


def _tok(s: str) -> set[str]:
    return {t for t in _WORD.findall((s or "").lower())}


_ALNUM_SPLIT = re.compile(r"[^a-z0-9]+")


def _metric_tokens(text: str) -> set[str]:
    """Recognised metric tokens in `text` — ONE rule, applied identically to a
    claim string and to a table column header.

    Whether a claim binds to a structured cell must not depend on which side of
    the comparison is being parsed. Previously the two sides disagreed:
      - claim side  = `_sig_tokens(value) & _METRIC_TOKENS` — words of length >=4
        only, so "f1" / "auc" / "iou" in a claim were invisible, and a claim
        naming a genuinely tabulated column came back `not_bindable`;
      - column side = `_col_matches_metric` also did a >=2-char *free substring*
        match, so "Performance metrics" matched "em" (from "exact match") and a
        non-metric column looked bindable from one direction only.
    Both are replaced by this: split on any non-alphanumeric boundary (so
    "F1-score" -> {f1, score}, "Accuracy (%)" -> {accuracy}), intersect whole
    tokens with `_METRIC_TOKENS`, and add any bounded-range metric NAME matched
    by `_METRIC_NAME_RE` ("exact match", "dice coefficient", "r2"). No substring
    matching: "performance metrics" contains no metric word and resolves to the
    empty set on BOTH sides.
    """
    low = (text or "").lower()
    out = {t for t in _ALNUM_SPLIT.split(low) if t} & _METRIC_TOKENS
    for m in _METRIC_NAME_RE.finditer(low):
        canon = _canon_metric(m.group(0))
        if canon:
            out.add(canon)
    return out


def _col_matches_metric(col_header: str, metric_toks: set[str]) -> bool:
    """True iff `col_header` names one of the metrics in `metric_toks`. SYMMETRIC:
    the header is reduced by the SAME `_metric_tokens` rule as the claim side,
    then intersected. `metric_toks` is the claim's `_metric_tokens(value)` (from
    `structural_bind`) or the full `_METRIC_TOKENS` vocab (from `classify_table`)."""
    return bool(_metric_tokens(col_header) & set(metric_toks or ()))


def _row_matches_subject(row_label: str, subject: str | None) -> bool:
    rl = (row_label or "").lower()
    if subject is None:                       # implicit OWN claim
        return bool(_OWN_ROW.search(rl))
    st = _tok(subject)
    return bool(st and (st & _tok(row_label) or
                        re.sub(r"[^a-z0-9]", "", subject.lower())[:12] in
                        re.sub(r"[^a-z0-9]", "", rl)))


# --- table-type classification (deterministic; NO LLM) ----------------------
# AxCell-style, three classes only. An ablation table's numbers are real but must
# not surface as the paper's headline result (cf. the earlier "vs." ablation-table
# attribution bug; 0549e2e9 is ablation-heavy). Classified from caption + header /
# row vocabulary only.
_ABLATION_RE = re.compile(
    r"\bablat\w*|\bw/?o\b|\bwithout\b|\bw/\s|\bvs\.?\b|\bversus\b|leave[- ]one[- ]out|"
    r"contribution of|effect of|impact of|role of|influence of|sensitivity (?:analysis|study|to)|"
    r"component[- ]wise|removing |replacing |varying |different (?:choices|settings|values) of|"
    r"design choice|with and without|w/ and w/o", re.I)
_RESULTS_RE = re.compile(
    r"\b(main |overall |final |test[- ]set |benchmark )?results?\b|comparison (?:with|to|against|of)|"
    r"compared (?:with|to)|state[- ]of[- ]the[- ]art|\bsota\b|leaderboard|performance (?:on|of|comparison)|"
    r"we compare|against (?:prior|existing|baseline)|held[- ]out|official test", re.I)
_OTHER_RE = re.compile(
    r"\bstatistics\b|\bdataset\b .*\b(size|split|counts?|composition)|hyper[- ]?parameters?|"
    r"\bnotation\b|\bsymbols?\b|training (?:details|config|setup)|prompt template|"
    r"\bexamples?\b (?:of|from)|qualitative|case stud|annotation guideline|"
    r"(?:running|inference|training) time|complexity|#\s*params|parameter count|throughput|latency|"
    r"related work|survey of", re.I)


def classify_table(caption: str, headers: set[str] | None = None,
                   rows: set[str] | None = None) -> str:
    """'ablation' | 'results' | 'other'. Ablation cues win over results cues."""
    blob = " ".join(filter(None, [caption or "", " ".join(sorted(headers or [])),
                                  " ".join(sorted(rows or []))]))
    low = blob.lower()
    row_has_ablation = bool(rows) and sum(
        1 for r in rows if _ABLATION_RE.search(r or "") or (r or "").strip().startswith(("-", "−", "w/o"))
    ) >= max(2, len(rows) // 3)
    if _ABLATION_RE.search(low) or row_has_ablation:
        return "ablation"
    if _RESULTS_RE.search(low):
        return "results"
    if _OTHER_RE.search(low):
        return "other"
    # default: a table with >=2 metric-named columns and >=2 method-ish rows reads
    # as a results table; otherwise 'other'.
    metric_cols = sum(1 for h in (headers or []) if _col_matches_metric(h, _METRIC_TOKENS))
    return "results" if (metric_cols >= 1 and len(rows or []) >= 2) else "other"


def _table_type_for(caption: str, all_cells: list[dict[str, Any]]) -> str:
    sib = [c for c in all_cells if (c.get("caption") or "") == (caption or "")]
    return classify_table(caption or "",
                          {c.get("column_header", "") for c in sib},
                          {c.get("row_label", "") for c in sib})


def structural_bind(value: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Verdict on whether `value`'s number(s) bind to the cell its subject+metric
    imply.

    Decision order (5b — binding applies only where a claim is BINDABLE):
      1. no table_cells (PDF-only)              -> status "pdf_only"
      2. claimed metric matches NO column in
         any table in this paper                -> status "not_bindable"
                                                   (fall through to grounding + attribution;
                                                    the 5a range check still applies)
      3. metric IS a column, value at the
         (subject-row x metric-column) cell     -> status "bound"  (proceeds; carries table_type)
      4. metric IS a column, value ELSEWHERE in
         that column at a different row          -> status "wrong_cell"  (cross-row -> REJECT)
      5. metric IS a column, value NOWHERE in that column:
           5a. value is in NO cell of ANY table  -> status "not_a_table_claim"
                                                    (a prose aggregate / mean-across-folds /
                                                     overall figure legitimately has no cell
                                                     -> fall through to grounding)
           5b. value IS in some cell, just not
               the metric's column               -> status "wrong_cell"  (a wrong-column or
                                                     cross-table value -> REJECT). The literal
                                                     "nowhere in that column -> fall through"
                                                     rule let correct-row/wrong-col and
                                                     cross-table probes through; "in no cell at
                                                     all" is what actually makes a claim a
                                                     prose aggregate.

    Case 2 uses `_metric_tokens` on BOTH the claim and every column header (same
    normalisation, whole-token, no substring) so a claim naming a genuinely
    tabulated column can never be `not_bindable` merely because the two sides were
    parsed by different rules. (Earlier asymmetry: claim side dropped tokens < 4
    chars, e.g. "f1"; column side free-substring-matched, e.g. "em" inside
    "Performance metrics". Both removed.)

    RESIDUAL GAP (structural, not an implementation artifact): a claim whose
    metric phrase contains no recognised metric word AT ALL ("performance
    metrics", "blood component used for measurement") still evades binding via
    case 2 and is checked only by grounding + attribution + the 5a range check.
    Structured table-cell binding only reaches claims whose metric is actually a
    named, recognised metric.
    """
    cells = paper_table_cells(chunks)
    if not cells:
        return {"structured": False, "status": "pdf_only"}

    def _bound(n: str, b: dict[str, Any]) -> dict[str, Any]:
        return {"structured": True, "status": "bound", "number": n,
                "table_type": _table_type_for(b.get("caption", ""), cells),
                "cell": {"row": b.get("row_label"), "col": b.get("column_header"),
                         "value": b.get("value"), "caption": b.get("caption")}}

    nums = [n for n in _NUMVAL.findall(value or "")]
    if not nums:
        return {"structured": True, "status": "no_number"}
    metric_toks = _metric_tokens(value)   # SAME rule as the column side (see _metric_tokens)
    sm = _SUBJECT_RE.match(value or "")
    subject = sm.group(1).strip() if sm else None
    if subject and _OWN_ROW.search(subject):
        subject = None                        # "Our method reports ..." -> implicit OWN
    subj_lbl = repr(subject) if subject else "OWN"

    # ---- case 2: the claimed metric is not a column in any table -> not_bindable
    metric_columns = [c for c in cells if metric_toks
                      and _col_matches_metric(c.get("column_header", ""), metric_toks)]
    if not metric_columns:
        return {"structured": True, "status": "not_bindable",
                "reason": "claimed metric matches no table column in this paper"}

    def _has(n: str, s) -> bool:
        s = str(s)
        if n == re.sub(r"[^\d.\-]", "", s):
            return True
        # token-boundary match so "0.45" does NOT match inside "0.4502", but
        # "82.1" DOES match inside "82.1 ± 0.3".
        return bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))

    for n in nums:
        col_hits = [c for c in metric_columns if _has(n, c.get("value", ""))]
        if col_hits:
            # ---- case 3: value at the (subject-row, metric-column) cell -> bound
            on_row = [c for c in col_hits if _row_matches_subject(c.get("row_label", ""), subject)]
            if on_row:
                return _bound(n, on_row[0])
            # ---- case 4: value IS in the metric's column but at a different row
            c = col_hits[0]
            return {"structured": True, "status": "wrong_cell", "number": n,
                    "reason": f"value is under column '{c.get('column_header')}' but for row "
                              f"'{c.get('row_label')}', not the claim's subject {subj_lbl}",
                    "candidate": {"row": c.get("row_label"), "col": c.get("column_header")}}
        # ---- case 5b: value not in the metric's column, but IS in some other cell
        #      (wrong column / cross-table) -> REJECT
        elsewhere = [c for c in cells if _has(n, c.get("value", ""))]
        if elsewhere:
            c = elsewhere[0]
            return {"structured": True, "status": "wrong_cell", "number": n,
                    "reason": f"value appears in cell (row '{c.get('row_label')}', column "
                              f"'{c.get('column_header')}'), not under the claimed metric's column",
                    "candidate": {"row": c.get("row_label"), "col": c.get("column_header")}}
    # ---- case 5a: metric IS a column, value is in no cell of ANY table -> prose
    #      aggregate / overall figure -> not a table claim -> fall through
    return {"structured": True, "status": "not_a_table_claim",
            "reason": "claimed metric is a column, but the value appears in no cell at all "
                      "(prose aggregate / overall figure)"}


def _section_context(chunks: list[dict[str, Any]], section: str, limit: int = 6000) -> str:
    parts, used = [], 0
    for c in chunks:
        if c.get("section") == section:
            parts.append(c.get("text", ""))
            used += len(c.get("text", ""))
            if used >= limit:
                break
    return " ".join(parts)


def _gate_value(field: str, value: str, chunks: list[dict[str, Any]],
                surnames: list[str]) -> dict[str, Any]:
    item = _evidence_item(field, value)
    if not _value_sane(field, value):
        item.update(evidence_status=UNSUPPORTED, abstain_reason="value_failed_sanity_check")
        return item
    # BINDING (not attribution): if the claim names a bounded metric, its value
    # must be physically possible for that metric. Closes the cross-row-number /
    # count-misread-as-metric hole. No-op when no bounded metric is named.
    if field in ("metrics", "results"):
        rng = metric_range_check(value)
        if rng is not None:
            item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                        abstain_reason="metric_value_out_of_range", range_check=rng)
            return item
        # STRUCTURAL CELL BINDING — a quantitative claim must bind to the actual
        # (row, column) cell, where a structured representation exists; else it is
        # unverifiable and is not returned as an OWN quantitative result.
        if _NUMVAL.search(value or ""):
            sb = structural_bind(value, chunks)
            item["structural_binding"] = sb
            if not sb["structured"]:                       # case 1 — PDF-only
                item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                            abstain_reason="unverifiable_binding")
                return item
            if sb["status"] == "wrong_cell":               # case 4 — cross-row
                item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                            abstain_reason="binding_wrong_cell")
                return item
            if sb["status"] == "bound":                    # case 3 — value at its cell
                # an ablation / non-results table's numbers are real but are not
                # the paper's headline result (5c) — label and withhold.
                if sb.get("table_type") in ("ablation", "other"):
                    item.update(evidence_status=EXPLICIT, provenance_valid=True, final=ABSTAINED,
                                abstain_reason=f"bound_to_{sb['table_type']}_table")
                    return item
                # results table + bound: fall through to grounding + attribution.
            # cases 2 (not_bindable) & 5 (not_a_table_claim): the claim is not a
            # table-cell claim — fall through to grounding + attribution + the 5a
            # range check, exactly as before structural binding existed.
    grounded = _ground(value, chunks, field=field)
    if grounded is None:
        item.update(evidence_status=UNSUPPORTED,
                    abstain_reason="evidence_span_not_found_in_paper_chunks", confidence=0.2)
        return item
    hit, sentence = grounded
    item.update(
        evidence_span=sentence[:400], source=hit.get("source"),
        representation=hit.get("representation"), section=hit.get("section"),
        page_or_node=hit.get("page_or_node"), block_id=hit.get("block_id"),
        char_start=hit.get("char_start"), char_end=hit.get("char_end"),
        evidence_status=EXPLICIT, provenance_valid=True, confidence=0.8)

    if field in ("metrics", "results"):
        attr = attribute_claim(
            hit.get("text") or "", value,
            block_type=hit.get("block_type"), section=hit.get("section"),
            section_context=_section_context(chunks, hit.get("section") or ""),
            own_author_surnames=surnames)
        item["attribution"] = attr["attribution"]
        item["attribution_confidence"] = attr["confidence"]
        if attr["attribution"] == CITED_PAPER:
            item.update(final=ABSTAINED, abstain_reason="attributed_to_cited_work")
            return item
        if attr["attribution"] == UNKNOWN:
            item.update(final=ABSTAINED, abstain_reason="ownership_unverified")
            return item
    item["final"] = RETURNED
    return item


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def gate_paper(record: dict[str, Any], chunks: list[dict[str, Any]],
               acquisition_status: str, surnames: list[str]) -> dict[str, Any]:
    """Return {datasets, metrics, results, evidence, acquisition_status} for one paper."""
    evidence: dict[str, list[dict[str, Any]]] = {"datasets": [], "metrics": [], "results": []}

    no_full_text = acquisition_status != FULL_TEXT
    for field in ("datasets", "metrics"):
        for value in _as_list(record.get(field)):
            if no_full_text:
                it = _evidence_item(field, value)
                it["abstain_reason"] = "no_validated_full_text"
                evidence[field].append(it)
            else:
                evidence[field].append(_gate_value(field, value, chunks, surnames))

    results_text = record.get("results")
    if isinstance(results_text, str) and results_text.strip():
        if no_full_text:
            it = _evidence_item("results", results_text.strip()[:300])
            it["abstain_reason"] = "no_validated_full_text"
            evidence["results"].append(it)
        else:
            for sent in _SENT.split(results_text.strip()):
                sent = sent.strip()
                if len(sent) < 12 or not _NUM.search(sent):
                    continue
                evidence["results"].append(_gate_value("results", sent, chunks, surnames))

    gated_datasets = [e["value"] for e in evidence["datasets"] if e["final"] == RETURNED]
    gated_metrics = [e["value"] for e in evidence["metrics"] if e["final"] == RETURNED]
    kept_results = [e["value"] for e in evidence["results"] if e["final"] == RETURNED]
    gated_results = " ".join(kept_results) if kept_results else ""

    return {"datasets": gated_datasets, "metrics": gated_metrics, "results": gated_results,
            "acquisition_status": acquisition_status, "evidence": evidence}


def _paper_acquisition_status(meta: dict[str, Any]) -> str:
    if meta.get("acquisition_status"):
        return meta["acquisition_status"]
    return FULL_TEXT if meta.get("has_full_text") else "NO_ACCESSIBLE_FULL_TEXT"


def run_evidence_gate(config: dict) -> dict[str, Any]:
    paths = config["paths"]
    processed = Path(paths["processed_dir"])
    summaries_path = processed / "paper_summaries.json"
    chunks_path = processed / "chunks.json"
    meta_path = Path(paths["raw_metadata_dir"]) / "collected_papers.json"

    summaries = json.loads(summaries_path.read_text(encoding="utf-8"))
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    meta_list = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_by_id = {m.get("paperId") or m.get("paper_id"): m for m in meta_list}

    chunks_by_paper: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        chunks_by_paper[c.get("paper_id")].append(c)

    stats = {"papers": len(summaries), "returned": {"datasets": 0, "metrics": 0, "results": 0},
             "abstained": {"datasets": 0, "metrics": 0, "results": 0},
             "no_full_text_quant_fields": 0, "no_full_text_quant_abstained": 0,
             "provenance_checked": 0, "provenance_valid": 0,
             "attribution": {OWN_PAPER: 0, CITED_PAPER: 0, UNKNOWN: 0}}

    evidence_out = []
    range_rejections: list[dict[str, Any]] = []
    for rec in summaries:
        pid = rec.get("paper_id")
        meta = meta_by_id.get(pid, {})
        acq = _paper_acquisition_status(meta)
        surnames = [a.get("name", "") for a in (meta.get("authors") or []) if isinstance(a, dict)]
        gated = gate_paper(rec, chunks_by_paper.get(pid, []), acq, surnames)

        rec["datasets"] = gated["datasets"]
        rec["metrics"] = gated["metrics"]
        rec["results"] = gated["results"]
        rec["acquisition_status"] = acq
        rec["evidence"] = gated["evidence"]

        for field, items in gated["evidence"].items():
            for it in items:
                if it["final"] == RETURNED:
                    stats["returned"][field] += 1
                else:
                    stats["abstained"][field] += 1
                if it.get("abstain_reason") == "metric_value_out_of_range" and it.get("range_check"):
                    range_rejections.append({"paper_id": pid, "field": field, **it["range_check"]})
                if acq != FULL_TEXT:
                    stats["no_full_text_quant_fields"] += 1
                    if it["final"] == ABSTAINED:
                        stats["no_full_text_quant_abstained"] += 1
                if it["evidence_status"] in (EXPLICIT,):
                    stats["provenance_checked"] += 1
                    stats["provenance_valid"] += 1 if it["provenance_valid"] else 0
                if field in ("metrics", "results") and it["evidence_status"] == EXPLICIT:
                    stats["attribution"][it["attribution"]] = \
                        stats["attribution"].get(it["attribution"], 0) + 1
        evidence_out.append({"paper_id": pid, "acquisition_status": acq,
                             "evidence": gated["evidence"]})

    summaries_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    (processed / "paper_evidence.json").write_text(json.dumps(evidence_out, indent=2), encoding="utf-8")

    stats["provenance_valid_rate"] = (
        round(stats["provenance_valid"] / stats["provenance_checked"], 4)
        if stats["provenance_checked"] else None)
    stats["no_full_text_quant_abstention_rate"] = (
        round(stats["no_full_text_quant_abstained"] / stats["no_full_text_quant_fields"], 4)
        if stats["no_full_text_quant_fields"] else None)
    stats["metric_range_rejections"] = len(range_rejections)
    (processed / "evidence_gate_summary.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    # LOG every metric-range rejection in full (metric, value, paper) — a
    # legitimate count misread by Stage 4 as a metric value shows up here.
    (processed / "evidence_gate_range_rejections.json").write_text(
        json.dumps(range_rejections, indent=2), encoding="utf-8")
    print(f"  Evidence gate: returned {stats['returned']}, abstained {stats['abstained']}, "
          f"provenance {stats['provenance_valid']}/{stats['provenance_checked']}, "
          f"no-full-text abstain {stats['no_full_text_quant_abstained']}/{stats['no_full_text_quant_fields']}")
    if range_rejections:
        print(f"  Metric-range rejections: {len(range_rejections)} — "
              + "; ".join(f"{r['paper_id'][:8]} {r['metric']}={r['value']} !in {r['interval']}"
                          for r in range_rejections[:8])
              + (" …" if len(range_rejections) > 8 else ""))

    # deterministic observability around Stage 5 (NOT a new stage): writes
    # evidence_monitor.json and prints an A/B/C/D status line.
    from .monitor import run_monitor
    run_monitor(evidence_out, stats, str(processed), corpus_size=len(summaries))
    return stats
