"""Deterministic operating-point sweep for the Stage-5 evidence gate.

Reads the ALREADY-COMPUTED canonical extraction (extraction_cache.json, keyed by
paper_id) + the provenance chunks + acquisition metadata from a production A/B
run, and re-simulates the gate at every combination of its meaningful
parameters. No LLM, no network — pure deterministic replay.

For each operating point it records the full safety/coverage table plus a
rejection-reason histogram, so we can see WHAT the gate rejects and pick the
safest point that maximises verified coverage.

    python results_gate_sweep.py --run runs/prodab-20260902T004416Z

Uses src.evidence.attribute.attribute_claim UNCHANGED.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from src.evidence.attribute import attribute_claim  # noqa: E402
from src.evidence.schema import OWN_PAPER, CITED_PAPER, UNKNOWN, FULL_TEXT  # noqa: E402

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
_NUMVAL = re.compile(r"\d+(?:\.\d+)?")
_SENT_NAIVE = re.compile(r"(?<=[.!?])\s+")
# abbrev-safe: do not split after a known abbreviation or a single-letter initial
_ABBREV = r"(?<!\bet al)(?<!\bi\.e)(?<!\be\.g)(?<!\bvs)(?<!\bFig)(?<!\bcf)(?<!\bno)(?<!\bEq)(?<!\bref)(?<!\b[A-Z])"
_SENT_SAFE = re.compile(_ABBREV + r"(?<=[.!?])\s+(?=[A-Z(])")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _sig(s: str) -> set[str]:
    return {t for t in _WORD.findall((s or "").lower()) if len(t) >= 4 and t not in _STOP}


def _split(text: str, mode: str) -> list[str]:
    rx = _SENT_SAFE if mode == "abbrev_safe" else _SENT_NAIVE
    return [s.strip() for s in rx.split(text or "") if s.strip()]


def _value_sane(field: str, value: str) -> bool:
    if field == "datasets":
        return bool(value and value.strip())
    v = (value or "").lower()
    return bool(_NUM.search(v)) or bool(_sig(v) & _METRIC_TOKENS)


def _supporting_sentence(value: str, text: str, split_mode: str) -> str:
    nv = _norm(value)
    sents = _split(text, split_mode)
    for s in sents:
        if nv and nv in _norm(s):
            return s
    toks = _sig(value)
    if toks:
        best, ov = "", 0.0
        for s in sents:
            o = len(toks & set(_WORD.findall(_norm(s)))) / len(toks)
            if o > ov:
                best, ov = s, o
        if ov >= 0.5:
            return best
    i = _norm(text).find(nv[:30]) if nv else -1
    return text[max(0, i - 140): i + 200].strip() if i >= 0 else value.strip()


def _ground(field: str, value: str, chunks: list[dict], *, thr: float, mode: str,
            prefer_body: bool, split_mode: str) -> tuple[dict, str] | None:
    """mode: 'sentence_overlap' (token containment of the whole value) or
    'number_anchored' (the value's number(s) verbatim in a chunk + >=2 sig
    tokens co-occur)."""
    nv = _norm(value)
    if len(nv) < 4:
        return None
    toks = _sig(value)
    nums = set(_NUMVAL.findall(value))

    def matches(c: dict) -> bool:
        ct = _norm(c.get("text", ""))
        if nv in ct:
            return True
        if mode == "number_anchored" and field == "results" and nums:
            if all(n in c.get("text", "") for n in nums):
                return len(toks & set(_WORD.findall(ct))) >= 2
            return False
        if len(toks) < 2:
            return False
        return len(toks & set(_WORD.findall(ct))) / len(toks) >= thr

    hits = [c for c in chunks if matches(c)]
    if not hits:
        return None
    if prefer_body:
        hits.sort(key=lambda c: (c.get("section") == "abstract",
                                 c.get("section") not in ("results", "experimental_setup", "discussion")))
    return hits[0], _supporting_sentence(value, hits[0].get("text", ""), split_mode)


def _section_context(chunks: list[dict], section: str, limit: int = 6000) -> str:
    parts, used = [], 0
    for c in chunks:
        if c.get("section") == section:
            parts.append(c.get("text", ""))
            used += len(c.get("text", ""))
            if used >= limit:
                break
    return " ".join(parts)


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def gate_value(field: str, value: str, chunks: list[dict], surnames: list[str],
               p: dict) -> dict:
    it = {"field": field, "value": value, "final": "ABSTAINED", "reason": None,
          "attribution": None, "section": None, "span": None, "provenance_valid": False}
    if not _value_sane(field, value):
        it["reason"] = "value_failed_sanity_check"
        return it
    g = _ground(field, value, chunks, thr=p["ground_thr"], mode=p["results_grounding"],
                prefer_body=p["prefer_body"], split_mode=p["splitter"])
    if g is None:
        it["reason"] = "not_grounded"
        return it
    hit, sent = g
    it.update(section=hit.get("section"), span=sent[:400], provenance_valid=True)
    it["span_has_value"] = _norm(value).strip(". ") in _norm(sent) or (
        len(_sig(value) & set(_WORD.findall(_norm(sent)))) / max(1, len(_sig(value))) >= 0.6)
    if field in ("metrics", "results"):
        attr = attribute_claim(hit.get("text") or "", value, block_type=hit.get("block_type"),
                               section=hit.get("section"),
                               section_context=_section_context(chunks, hit.get("section") or ""),
                               own_author_surnames=surnames)
        it["attribution"] = attr["attribution"]
        if attr["attribution"] == CITED_PAPER:
            it["reason"] = "attributed_to_cited_work"
            return it
        if attr["attribution"] == UNKNOWN:
            it["reason"] = "ownership_unverified"
            return it
    it["final"] = "RETURNED"
    return it


def gate_paper(raw: dict, chunks: list[dict], acq: str, surnames: list[str], p: dict) -> dict:
    ev = {"datasets": [], "metrics": [], "results": []}
    no_ft = acq != FULL_TEXT
    for field in ("datasets", "metrics"):
        for v in _as_list(raw.get(field)):
            if no_ft:
                ev[field].append({"field": field, "value": v, "final": "ABSTAINED",
                                  "reason": "no_validated_full_text"})
            else:
                ev[field].append(gate_value(field, v, chunks, surnames, p))
    rt = raw.get("results")
    if isinstance(rt, str) and rt.strip():
        if no_ft:
            ev["results"].append({"field": "results", "value": rt[:200], "final": "ABSTAINED",
                                  "reason": "no_validated_full_text"})
        else:
            for sent in _split(rt.strip(), p["splitter"]):
                if len(sent) < 12:
                    continue
                if p["results_require_number"] and not _NUM.search(sent):
                    ev["results"].append({"field": "results", "value": sent[:200],
                                          "final": "ABSTAINED", "reason": "results_sentence_no_number"})
                    continue
                ev["results"].append(gate_value("results", sent, chunks, surnames, p))
    return ev


def run_point(p: dict, papers: list, chunks_by: dict, meta_by: dict) -> dict:
    ret = Counter()
    reasons = Counter()
    attr = Counter()
    prov_ok = prov_tot = span_ok = span_tot = 0
    papers_with_results = set()
    noft_quant = noft_abstained = 0
    leaked = 0
    own_items = []
    for rec in papers:
        pid = rec["paper_id"]
        m = meta_by.get(pid, {})
        acq = m.get("acquisition_status") or (FULL_TEXT if m.get("has_full_text") else "NO_ACCESSIBLE_FULL_TEXT")
        surnames = [a.get("name", "") for a in (m.get("authors") or []) if isinstance(a, dict)]
        ev = gate_paper(rec, chunks_by.get(pid, []), acq, surnames, p)
        leaked_here = False
        for field, items in ev.items():
            for it in items:
                if it["final"] == "RETURNED":
                    ret[field] += 1
                    if field == "results":
                        papers_with_results.add(pid)
                    if field in ("metrics", "results"):
                        if it.get("attribution") == OWN_PAPER:
                            own_items.append((pid[:10], field, it["value"][:70], it.get("section"), it.get("span_has_value")))
                    if it.get("provenance_valid"):
                        prov_tot += 1; prov_ok += 1
                    if field in ("metrics", "results"):
                        span_tot += 1; span_ok += 1 if it.get("span_has_value") else 0
                    if acq != FULL_TEXT:
                        leaked_here = True
                else:
                    reasons[it.get("reason") or "?"] += 1
                if it.get("attribution"):
                    attr[it["attribution"]] += 1
                if acq != FULL_TEXT:
                    noft_quant += 1
                    if it["final"] == "ABSTAINED":
                        noft_abstained += 1
        if leaked_here:
            leaked += 1
    return {
        "params": p,
        "returned": dict(ret),
        "papers_with_results": len(papers_with_results),
        "provenance_valid_rate": round(prov_ok / prov_tot, 4) if prov_tot else None,
        "span_contains_value_rate": round(span_ok / span_tot, 4) if span_tot else None,
        "attribution": dict(attr),
        "own_returned_quant": len(own_items),
        "no_full_text_quant_fields": noft_quant,
        "no_full_text_quant_abstained": noft_abstained,
        "no_full_text_abstention_ok": noft_quant == noft_abstained,
        "inaccessible_papers_leaking": leaked,
        "rejection_reasons": dict(reasons.most_common()),
        "_own_items": own_items,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="path to a prodab-* run dir (relative to experiments/document_evidence_pipeline or absolute)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = HERE / args.run
    canon = run_dir / "canonical"
    cache = json.loads((canon / "processed" / "extraction_cache.json").read_text(encoding="utf-8"))
    chunks = json.loads((canon / "processed" / "chunks.json").read_text(encoding="utf-8"))
    meta = json.loads((canon / "raw_metadata" / "collected_papers.json").read_text(encoding="utf-8"))
    meta_by = {m.get("paperId") or m.get("paper_id"): m for m in meta}
    chunks_by = defaultdict(list)
    for c in chunks:
        chunks_by[c["paper_id"]].append(c)
    papers = [{"paper_id": pid, **v} for pid, v in cache.items()]

    grid = {
        "splitter": ["naive", "abbrev_safe"],
        "results_require_number": [True, False],
        "results_grounding": ["sentence_overlap", "number_anchored"],
        "ground_thr": [0.8, 0.7, 0.6],
        "prefer_body": [True],
    }
    keys = list(grid)
    points = []
    for combo in itertools.product(*grid.values()):
        p = dict(zip(keys, combo))
        # skip meaningless combos: number_anchored only affects results; still run all for completeness
        points.append(run_point(p, papers, chunks_by, meta_by))

    # current production operating point
    current = run_point({"splitter": "naive", "results_require_number": True,
                         "results_grounding": "sentence_overlap", "ground_thr": 0.8,
                         "prefer_body": True}, papers, chunks_by, meta_by)
    out = {"run": str(run_dir), "corpus_papers": len(papers),
           "current_production_point": current, "sweep": points}
    dest = Path(args.out) if args.out else (run_dir / "results_gate_sweep.json")
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")

    def row(r):
        pr = r["params"]
        rr = r["returned"]
        return (f"sp={pr['splitter']:11} num={str(pr['results_require_number']):5} "
                f"gnd={pr['results_grounding']:16} thr={pr['ground_thr']} | "
                f"R={rr.get('results',0):2} M={rr.get('metrics',0):2} D={rr.get('datasets',0):2} "
                f"pap_R={r['papers_with_results']:2} | prov={r['provenance_valid_rate']} "
                f"span={r['span_contains_value_rate']} OWN={r['own_returned_quant']:2} "
                f"attr={r['attribution']} | noFT_ok={r['no_full_text_abstention_ok']} "
                f"leak={r['inaccessible_papers_leaking']}")

    print("=== CURRENT PRODUCTION POINT ===")
    print(row(current))
    print("  rejections:", current["rejection_reasons"])
    print("\n=== SWEEP ===")
    for r in points:
        print(row(r))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
