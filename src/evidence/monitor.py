"""Lightweight deterministic monitoring for the Stage-5 evidence gate.

This is OBSERVABILITY around the existing six stages — not a new stage. It is
called at the end of `run_evidence_gate`, reads the gate's own outputs, and
writes `evidence_monitor.json` next to `evidence_gate_summary.json`.

Four signals (see STAGING_VALIDATION_REPORT.md):
  A  RETURNED quantitative count + drift vs a recorded reference (same corpus only)
  B  attribution safety   — every RETURNED metric/result must be OWN_PAPER
  C  provenance           — provenance_valid / provenance_checked must be 1.0
  D  no-full-text leakage  — no RETURNED Dataset/Metric/Result on a non-FULL_TEXT paper

The monitor never raises: it records status. Callers (e.g. the staging runner)
decide whether to STOP.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import OWN_PAPER, FULL_TEXT, RETURNED

# Recorded reference point from the validated primary-corpus production A/B
# (runs/prodab-20260902T004416Z, number-anchored results gate). Used ONLY for
# same-corpus drift context — a different corpus is never a failure.
REFERENCE = {"corpus_size": 60, "datasets": 52, "metrics": 10, "results": 12, "total": 74}
# a same-corpus total outside this band is flagged for a human to look at
DRIFT_LOW, DRIFT_HIGH = 0.5, 2.0

_OK, _WARN, _FAIL, _CRIT = "OK", "WARN", "FAIL", "CRITICAL"


def evaluate(evidence_out: list[dict[str, Any]], gate_stats: dict[str, Any],
             *, corpus_size: int) -> dict[str, Any]:
    ret = gate_stats.get("returned", {})
    total = sum(int(ret.get(k, 0)) for k in ("datasets", "metrics", "results"))

    # A — count drift (same-corpus only)
    a: dict[str, Any] = {"datasets": ret.get("datasets", 0), "metrics": ret.get("metrics", 0),
                         "results": ret.get("results", 0), "total": total,
                         "reference": REFERENCE, "corpus_size": corpus_size}
    if corpus_size == REFERENCE["corpus_size"] and REFERENCE["total"]:
        ratio = total / REFERENCE["total"]
        a["ratio_vs_reference"] = round(ratio, 3)
        a["status"] = _WARN if (ratio < DRIFT_LOW or ratio > DRIFT_HIGH) else _OK
        a["note"] = ("same corpus as reference; total outside "
                     f"[{DRIFT_LOW}x, {DRIFT_HIGH}x]" if a["status"] == _WARN
                     else "same corpus as reference; total within expected band")
    else:
        a["status"] = "INFO"
        a["note"] = "different corpus than the recorded reference — counts recorded, no drift verdict"

    # B — attribution safety: every RETURNED metric/result must be OWN_PAPER
    bad_attr = []
    for rec in evidence_out:
        for field in ("metrics", "results"):
            for it in rec.get("evidence", {}).get(field, []):
                if it.get("final") == RETURNED and it.get("attribution") != OWN_PAPER:
                    bad_attr.append({"paper_id": rec.get("paper_id"), "field": field,
                                     "attribution": it.get("attribution"),
                                     "value": (it.get("value") or "")[:120]})
    b = {"returned_quant_items": sum(
             1 for rec in evidence_out for f in ("metrics", "results")
             for it in rec.get("evidence", {}).get(f, []) if it.get("final") == RETURNED),
         "not_own_paper": len(bad_attr), "offenders": bad_attr,
         "status": _OK if not bad_attr else _FAIL}

    # C — provenance
    pv, pc = gate_stats.get("provenance_valid", 0), gate_stats.get("provenance_checked", 0)
    rate = (pv / pc) if pc else None
    c = {"provenance_valid": pv, "provenance_checked": pc, "rate": rate,
         "status": _OK if (pc > 0 and rate == 1.0) else (_FAIL if pc and rate is not None and rate < 1.0 else _WARN),
         "note": "no EXPLICIT evidence items to check" if not pc else ""}

    # D — no-full-text leakage (tripwire; the gate already forces these to abstain)
    leaks = []
    for rec in evidence_out:
        if rec.get("acquisition_status") == FULL_TEXT:
            continue
        for field in ("datasets", "metrics", "results"):
            for it in rec.get("evidence", {}).get(field, []):
                if it.get("final") == RETURNED:
                    leaks.append({"paper_id": rec.get("paper_id"), "field": field,
                                  "acquisition_status": rec.get("acquisition_status"),
                                  "value": (it.get("value") or "")[:120]})
    d = {"no_full_text_returned_items": len(leaks), "offenders": leaks,
         "status": _OK if not leaks else _CRIT}

    order = {_OK: 0, "INFO": 0, _WARN: 1, _FAIL: 2, _CRIT: 3}
    worst = max((a["status"], b["status"], c["status"], d["status"]), key=lambda s: order.get(s, 2))
    overall = {_OK: "OK", "INFO": "OK", _WARN: "WARN", _FAIL: "FAIL", _CRIT: "CRITICAL"}[worst]

    return {"overall": overall,
            "A_returned_quant_count": a, "B_attribution_safety": b,
            "C_provenance": c, "D_no_full_text_leakage": d}


def run_monitor(evidence_out: list[dict[str, Any]], gate_stats: dict[str, Any],
                processed_dir: str | Path, corpus_size: int) -> dict[str, Any]:
    report = evaluate(evidence_out, gate_stats, corpus_size=corpus_size)
    Path(processed_dir, "evidence_monitor.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    a, b, c, d = (report["A_returned_quant_count"], report["B_attribution_safety"],
                  report["C_provenance"], report["D_no_full_text_leakage"])
    print(f"  Evidence monitor [{report['overall']}]: "
          f"A quant total={a['total']} ({a['status']}) | "
          f"B not-OWN returned={b['not_own_paper']} ({b['status']}) | "
          f"C provenance={c['rate']} ({c['status']}) | "
          f"D no-full-text leaks={d['no_full_text_returned_items']} ({d['status']})")
    return report
