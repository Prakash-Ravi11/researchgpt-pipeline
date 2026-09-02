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
            "provenance_valid": False, "final": ABSTAINED, "abstain_reason": None}


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
    (processed / "evidence_gate_summary.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"  Evidence gate: returned {stats['returned']}, abstained {stats['abstained']}, "
          f"provenance {stats['provenance_valid']}/{stats['provenance_checked']}, "
          f"no-full-text abstain {stats['no_full_text_quant_abstained']}/{stats['no_full_text_quant_fields']}")

    # deterministic observability around Stage 5 (NOT a new stage): writes
    # evidence_monitor.json and prints an A/B/C/D status line.
    from .monitor import run_monitor
    run_monitor(evidence_out, stats, str(processed), corpus_size=len(summaries))
    return stats
