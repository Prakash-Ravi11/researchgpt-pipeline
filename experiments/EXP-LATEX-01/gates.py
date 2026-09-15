"""Part 15 — pre-defined acceptance gates for EXP-LATEX-01.

These are DECISION CRITERIA fixed before measurement, not predictions. This
script reports each gate as PASS / FAIL / NOT MEASURED against whatever
`metrics_summary.csv` actually contains. It has no way to adjust a metric, and
a gate with no data reads NOT MEASURED — never PASS.

    python experiments/EXP-LATEX-01/gates.py --summary runs/exp-latex-01/metrics_summary.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard  # noqa: E402


@dataclass(frozen=True)
class Gate:
    gate_id: str
    metric: str
    label: str
    rule: str
    threshold: float
    direction: str          # "ge" | "le" | "eq"
    on: str = "treatment"   # "treatment" | "relative_delta"
    primary: bool = False
    baseline_note: str = ""


GATES: tuple[Gate, ...] = (
    Gate("G1", "table_binding_latex_eligible",
         "Table binding, LaTeX-eligible subset", ">= 0.60", 0.60, "ge",
         primary=True,
         baseline_note="Phase-4b measured 0.142 (gt-wt) / 0.241 (macro) on the "
                       "11 LaTeX-retained papers. This gate is ~2.5-4x that."),
    Gate("G2", "table_binding_rate", "Overall table binding", ">= 0.089", 0.089, "ge",
         primary=True, baseline_note="frozen baseline 0.089"),
    Gate("G3", "numeric_survival_lax", "Numeric survival", ">= 0.980", 0.980, "ge",
         primary=True, baseline_note="frozen baseline 0.986 PDF / 0.981 LaTeX"),
    Gate("G4", "anchor_delivery", "Anchor delivery", ">= 0.167", 0.167, "ge",
         primary=True, baseline_note="frozen baseline 0.167"),
    Gate("G5", "provenance_valid", "Provenance validity", "== 1.00", 1.0, "eq",
         primary=True, baseline_note="frozen baseline 146/146 = 100%"),
    Gate("G6", "wrong_paper_attrib", "Wrong-paper attribution", "== 0", 0.0, "eq",
         primary=True, baseline_note="frozen baseline 0"),
    Gate("G7", "false_own_paper", "False OWN_PAPER attribution", "== 0", 0.0, "eq",
         primary=True, baseline_note="frozen baseline 0"),
    Gate("G8", "abstention_correct", "Abstention correctness", "== 1.00", 1.0, "eq",
         primary=True, baseline_note="frozen baseline 81/81 = 100%"),
    Gate("G9", "runtime_total_s", "Runtime penalty", "<= +0.50 relative", 0.50, "le",
         on="relative_delta",
         baseline_note="Phase-5x measured +47% at reservation 4096"),
    Gate("G10", "peak_vram_mib", "Peak VRAM", "<= 5632 MiB (5.5 GB)", 5632.0, "le",
         baseline_note="Phase-5x measured 5909/6144 MiB (96%) on the 6 GB "
                       "reference GPU. On a 16 GB T4 this gate is about local "
                       "deployability, not about whether the run fits."),
)

#: Gates that cannot be read from metrics_summary.csv and must be checked by
#: running the suites directly. Listed so they are never silently skipped.
EXTERNAL_GATES = (
    # The protocol's "Tests: 91/91" is not a test count: 91/91 is a
    # provenance-valid rate from an earlier phase (FINAL_REPORT.md:236/:274,
    # later superseded by 108/108 in RESULTS_GATE_TUNING_REPORT.md:93). The
    # documented suite sizes are 15/15 and 42/42, so the gate is restated
    # against those rather than against a number that cannot be met by
    # definition. See docs/experiments/EXP-LATEX-01-AUDIT.md §3.
    ("G11", "Test suite (restated)",
     "no regression vs 15/15 + 42/42, plus new suites green",
     "run tests/test_pipeline.py, tests/test_anchors.py, "
     "experiments/document_evidence_pipeline/tests/test_pipeline_units.py, "
     "tests/test_table_atomic.py and "
     "experiments/EXP-LATEX-01/tests/test_paired_stats.py"),
)


def _f(row, key):
    v = (row.get(key) or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def evaluate(summary_path: Path) -> dict:
    rows = {r["metric"]: r for r in csv.DictReader(summary_path.open())}
    results = []
    for g in GATES:
        row = rows.get(g.metric)
        val = None
        if row is not None:
            val = _f(row, "relative_delta") if g.on == "relative_delta" else _f(row, "treatment")
        n_paired = int(row["n_paired"]) if row and row.get("n_paired") else 0
        if val is None or n_paired == 0:
            status = "NOT MEASURED"
            detail = ("no paired observations for this metric in this run"
                      if n_paired == 0 else "metric present but value is blank")
        else:
            if g.direction == "ge":
                ok = val >= g.threshold
            elif g.direction == "le":
                ok = val <= g.threshold
            else:
                ok = abs(val - g.threshold) < 1e-9
            status = "PASS" if ok else "FAIL"
            detail = f"observed {val:.6g} vs rule {g.rule}"
        results.append({"gate_id": g.gate_id, "metric": g.metric, "label": g.label,
                        "rule": g.rule, "primary": g.primary, "n_paired": n_paired,
                        "observed": val, "status": status, "detail": detail,
                        "baseline_note": g.baseline_note})
    for gid, label, rule, how in EXTERNAL_GATES:
        results.append({"gate_id": gid, "metric": "-", "label": label, "rule": rule,
                        "primary": True, "n_paired": 0, "observed": None,
                        "status": "NOT MEASURED",
                        "detail": f"not derivable from metrics_summary.csv; {how}",
                        "baseline_note": ""})
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_nm = sum(1 for r in results if r["status"] == "NOT MEASURED")
    verdict = ("PASS" if n_fail == 0 and n_nm == 0 else
               "FAIL" if n_fail else "INCOMPLETE")
    return {"experiment_id": "EXP-LATEX-01", "summary": str(summary_path),
            "gates": results, "n_pass": n_pass, "n_fail": n_fail,
            "n_not_measured": n_nm, "verdict": verdict,
            "verdict_meaning": {
                "PASS": "every gate measured and met",
                "FAIL": "at least one gate measured and not met",
                "INCOMPLETE": "no gate failed, but some were never measured — "
                              "this is NOT a pass"}[verdict]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary",
                    default=f"{guard.EXPERIMENT_ROOT}/metrics_summary.csv")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    p = Path(a.summary)
    if not p.is_absolute():
        p = guard.repo_root() / p
    if not p.exists():
        print(f"no metrics_summary.csv at {p}\n"
              f"Run the arms and experiments/EXP-LATEX-01/analyze.py first. "
              f"Gates are not evaluated against absent data.")
        return 2
    res = evaluate(p)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0 if res["verdict"] == "PASS" else 1
    print(f"EXP-LATEX-01 — Part 15 acceptance gates")
    print(f"source: {p}\n")
    w = max(len(g["label"]) for g in res["gates"])
    for g in res["gates"]:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "NOT MEASURED": "  --"}[g["status"]]
        star = "*" if g["primary"] else " "
        print(f" {mark} {star} {g['gate_id']:<4} {g['label']:<{w}}  {g['rule']:<24} {g['detail']}")
    print(f"\n{res['n_pass']} pass, {res['n_fail']} fail, "
          f"{res['n_not_measured']} not measured")
    print(f"VERDICT: {res['verdict']} — {res['verdict_meaning']}")
    print("\n* = primary gate.  A gate with no data reads NOT MEASURED, never PASS.")
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
