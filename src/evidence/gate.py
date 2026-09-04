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


def _col_matches_metric(col_header: str, metric_toks: set[str]) -> bool:
    ch = _tok(col_header)
    if metric_toks & ch:
        return True
    # "F1" vs "f1-score", "AUC" vs "auroc" — substring on the joined header
    j = re.sub(r"[^a-z0-9]", "", (col_header or "").lower())
    return any(re.sub(r"[^a-z0-9]", "", m) in j for m in metric_toks if len(m) >= 2)


def _row_matches_subject(row_label: str, subject: str | None) -> bool:
    rl = (row_label or "").lower()
    if subject is None:                       # implicit OWN claim
        return bool(_OWN_ROW.search(rl))
    st = _tok(subject)
    return bool(st and (st & _tok(row_label) or
                        re.sub(r"[^a-z0-9]", "", subject.lower())[:12] in
                        re.sub(r"[^a-z0-9]", "", rl)))


def structural_bind(value: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Verdict on whether `value`'s number(s) bind to the cell its subject+metric
    imply.

      structured=False                     -> paper is PDF-only, cannot verify
      status = bound                       -> value is at the (subject-row, metric-col) cell
               wrong_cell                  -> value IS in a cell, but wrong row and/or column
               no_cell                     -> value in no cell of a structured paper
               no_metric                   -> claim names no metric to key a column on
    """
    cells = paper_table_cells(chunks)
    if not cells:
        return {"structured": False, "status": "pdf_only"}

    nums = [n for n in _NUMVAL.findall(value or "")]
    if not nums:
        return {"structured": True, "status": "no_number"}
    metric_toks = (_sig_tokens(value) & _METRIC_TOKENS) | {
        m.group(0).lower() for m in _METRIC_NAME_RE.finditer(value or "")}
    sm = _SUBJECT_RE.match(value or "")
    subject = sm.group(1).strip() if sm else None
    if subject and _OWN_ROW.search(subject):
        subject = None                        # "Our method reports ..." -> implicit OWN

    # does the paper have ANY column whose header matches the claimed metric?
    metric_col_exists = bool(metric_toks) and any(
        _col_matches_metric(c.get("column_header", ""), metric_toks) for c in cells)

    for n in nums:
        val_cells = [c for c in cells if n == re.sub(r"[^\d.\-]", "", str(c.get("value", "")))
                     or (len(n) >= 3 and n in str(c.get("value", "")))]
        if not val_cells:
            continue
        row_cells = [c for c in val_cells if _row_matches_subject(c.get("row_label", ""), subject)]
        col_cells = ([c for c in val_cells if _col_matches_metric(c.get("column_header", ""), metric_toks)]
                     if metric_toks else [])
        subj_lbl = repr(subject) if subject else "OWN"

        # (a) value at the (subject-row, metric-column) cell -> BOUND
        both = [c for c in row_cells if c in col_cells]
        if both:
            b = both[0]
            return {"structured": True, "status": "bound", "number": n,
                    "cell": {"row": b.get("row_label"), "col": b.get("column_header"),
                             "value": b.get("value"), "caption": b.get("caption")}}
        # (b) the paper HAS a column for this metric, and the value sits under it
        #     but for a DIFFERENT row -> cross-row
        if col_cells and not row_cells:
            c = col_cells[0]
            return {"structured": True, "status": "wrong_cell", "number": n,
                    "reason": f"value is under column '{c.get('column_header')}' but for row "
                              f"'{c.get('row_label')}', not the claim's subject {subj_lbl}",
                    "candidate": {"row": c.get("row_label"), "col": c.get("column_header")}}
        # (c) the paper HAS a column for this metric; the value is at the subject's
        #     row but under a DIFFERENT column -> wrong column
        if metric_col_exists and row_cells and not col_cells:
            c = row_cells[0]
            return {"structured": True, "status": "wrong_cell", "number": n,
                    "reason": f"value is at row '{c.get('row_label')}' but under column "
                              f"'{c.get('column_header')}', not one matching the claimed metric",
                    "candidate": {"row": c.get("row_label"), "col": c.get("column_header")}}
        # (d) no identifiable metric column anywhere (non-standard headers): fall
        #     back to value+row. Row matches subject -> BOUND; value only at other
        #     rows -> cross-row.
        if not metric_col_exists:
            if row_cells:
                b = row_cells[0]
                return {"structured": True, "status": "bound", "number": n,
                        "cell": {"row": b.get("row_label"), "col": b.get("column_header"),
                                 "value": b.get("value"), "caption": b.get("caption")}}
            c = val_cells[0]
            return {"structured": True, "status": "wrong_cell", "number": n,
                    "reason": f"value is at row '{c.get('row_label')}', not the claim's subject {subj_lbl}",
                    "candidate": {"row": c.get("row_label"), "col": c.get("column_header")}}
        # metric column exists but value not under it and not at subject's row
        return {"structured": True, "status": "wrong_cell", "number": n,
                "reason": "value present in a table but not at the (subject-row, metric-column) cell",
                "candidate": {"row": val_cells[0].get("row_label"),
                              "col": val_cells[0].get("column_header")}}
    return {"structured": True, "status": "no_cell", "number": nums[0]}


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
            if not sb["structured"]:
                item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                            abstain_reason="unverifiable_binding")
                return item
            if sb["status"] == "wrong_cell":
                item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                            abstain_reason="binding_wrong_cell")
                return item
            if sb["status"] in ("no_cell", "no_metric"):
                item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                            abstain_reason="unverifiable_binding")
                return item
            # status == "bound": structurally verified — fall through to grounding
            # + attribution (still required: bound cell != own-authored).
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
