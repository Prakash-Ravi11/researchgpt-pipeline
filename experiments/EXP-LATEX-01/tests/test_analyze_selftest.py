"""End-to-end self-test of the EXP-LATEX-01 analyser on SYNTHETIC data.

This proves the analysis pipeline works — it produces NO experimental result.
The synthetic arms are written under runs/exp-latex-01/_selftest/ and every
file it creates carries a SYNTHETIC marker, so its output can never be mistaken
for a measurement of the real corpus.

Run:  python experiments/EXP-LATEX-01/tests/test_analyze_selftest.py
"""
import csv
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze
import guard
import paired_stats as ps

PASS = FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail and not cond else ""))


def build_synthetic(root: Path, n_papers=60, seed=11):
    rnd = random.Random(seed)
    ctl, trt = {}, {}
    for i in range(n_papers):
        pid = f"SYNTH{i:03d}"
        base_bind = rnd.uniform(0.02, 0.20)
        ctl[pid] = {
            "table_binding_rate": round(base_bind, 4),
            # deliberate: treatment adds a known +0.05 on average
            "numeric_survival_lax": round(rnd.uniform(0.95, 1.0), 4),
            "evidence_fields_nonempty": rnd.randint(6, 10),
            "runtime_total_s": round(rnd.uniform(25, 40), 2),
            "acquisition_full_text": rnd.random() < 0.57,
            "tables_split": rnd.randint(0, 6),
            "provenance_valid": 1.0,
            "wrong_paper_attrib": 0,
        }
        trt[pid] = {
            "table_binding_rate": round(min(1.0, base_bind + rnd.gauss(0.05, 0.02)), 4),
            "numeric_survival_lax": round(rnd.uniform(0.95, 1.0), 4),
            "evidence_fields_nonempty": max(0, ctl[pid]["evidence_fields_nonempty"]
                                            - rnd.choice([0, 0, 1, 4])),
            "runtime_total_s": round(ctl[pid]["runtime_total_s"] * rnd.uniform(1.3, 1.6), 2),
            "acquisition_full_text": ctl[pid]["acquisition_full_text"],
            "tables_split": 0,                       # atomic arm: never split
            "provenance_valid": 1.0,
            "wrong_paper_attrib": 0,
        }
    # one paper missing a metric in the treatment arm -> must be dropped, not imputed
    del trt["SYNTH007"]["table_binding_rate"]
    for arm, papers in (("control", ctl), ("latex", trt)):
        d = guard.assert_experiment_output(root / arm)
        d.mkdir(parents=True, exist_ok=True)
        (d / "per_paper.json").write_text(json.dumps({
            "arm": arm,
            "SYNTHETIC": True,
            "warning": "SYNTHETIC SELF-TEST DATA — NOT A MEASUREMENT OF ANY CORPUS",
            "papers": papers}, indent=2))
    return ctl, trt


def main():
    print("=" * 62)
    print("EXP-LATEX-01 — analyser self-test (SYNTHETIC DATA, NOT A RESULT)")
    print("=" * 62)
    root = Path(guard.assert_experiment_output(Path(guard.EXPERIMENT_ROOT) / "_selftest"))
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    ctl, trt = build_synthetic(root)

    print("\n1. analyser runs end to end")
    rows = analyze.run("control", "latex", root)
    check("returned one row per registered metric",
          len(rows) == len(analyze.METRICS), f"{len(rows)}")

    by = {r["metric"]: r for r in rows}

    print("\n2. missing values are dropped, never imputed")
    tb = by["table_binding_rate"]
    check("one paper dropped from the paired sample", tb["n_paired"] == 59, tb["n_paired"])
    check("the drop is counted", tb["n_missing"] == 1, tb["n_missing"])
    pl = list(csv.DictReader((root / "paper_level_results.csv").open()))
    tb_rows = [r for r in pl if r["metric"] == "table_binding_rate"]
    check("paper_level_results.csv has no row for the dropped paper",
          not any(r["paper_id"] == "SYNTH007" for r in tb_rows))
    check("and still has the other 59", len(tb_rows) == 59, str(len(tb_rows)))

    print("\n3. metrics with no data are reported, not hidden")
    nd = by["ndcg_at_10"]
    check("unmeasured metric present in the summary", nd is not None)
    check("marked NOT MEASURED", nd["interpretation"].startswith("NOT MEASURED"),
          nd["interpretation"])
    check("no fabricated statistic", nd["p_value"] == "" and nd["control"] == "")

    print("\n4. statistics match a direct computation")
    pairs = [(p, ctl[p]["runtime_total_s"], trt[p]["runtime_total_s"]) for p in ctl]
    direct = ps.wilcoxon_signed_rank([x[1] for x in pairs], [x[2] for x in pairs])
    rt = by["runtime_total_s"]
    check("runtime test statistic matches paired_stats directly",
          abs(float(rt["test_statistic"]) - direct.statistic) < 1e-9,
          f'{rt["test_statistic"]} vs {direct.statistic}')
    check("runtime p matches", abs(float(rt["p_value"]) - direct.p_value) < 1e-12)
    check("runtime regression detected (treatment slower)",
          float(rt["absolute_delta"]) > 0, rt["absolute_delta"])

    print("\n5. Holm correction is applied to the confirmatory family only")
    check("confirmatory metric carries an adjusted p",
          by["table_binding_rate"]["p_adjusted"] != "")
    check("adjusted p >= raw p",
          float(by["table_binding_rate"]["p_adjusted"]) >=
          float(by["table_binding_rate"]["p_value"]))
    check("exploratory metric has no adjusted p and says so",
          by["tables_split"]["p_adjusted"] == ""
          and by["tables_split"]["interpretation"].startswith("EXPLORATORY"),
          by["tables_split"]["interpretation"][:60])

    print("\n6. degenerate metrics do not produce fake results")
    pv = by["provenance_valid"]
    check("constant-at-1.0 metric gives no p", pv["p_value"] == "", pv["p_value"])
    check("and explains why", "tied" in pv["interpretation"] or
          "NOT TESTABLE" in pv["interpretation"], pv["interpretation"])
    ac = by["acquisition_full_text"]
    check("identical binary arms give no p", ac["p_value"] == "", ac["p_value"])

    print("\n7. the secondary hypothesis is visible in the output")
    ts = by["tables_split"]
    check("tables_split drops to zero in the treatment arm",
          float(ts["treatment"]) == 0.0, ts["treatment"])
    check("and the delta is negative", float(ts["absolute_delta"]) < 0, ts["absolute_delta"])

    print("\n8. plots and artefacts exist")
    plots = sorted((root / "plots").glob("*.svg"))
    check("SVG plots written", len(plots) >= 5, f"{len(plots)} files")
    check("arm comparison plot written", (root / "plots" / "arm_comparison.svg").exists())
    svg = (root / "plots" / "paired_table_binding_rate.svg").read_text()
    check("paired plot states n, improved and regressed counts",
          "papers" in svg and "improved" in svg and "regressed" in svg)
    check("paired plot labels the CI as bootstrap", "bootstrap" in svg)
    stats = json.loads((root / "statistical_analysis" / "per_metric.json").read_text())
    check("per-metric JSON records missing papers",
          stats["metrics"]["table_binding_rate"]["missing_papers"] == ["SYNTH007"])
    check("per-metric JSON keeps BOTH tests for continuous metrics",
          len(stats["metrics"]["evidence_fields_nonempty"]["tests"]) == 2)

    print("\n9. the guard still holds during analysis")
    try:
        analyze.run("control", "latex", Path("runs"))
        check("analyser refuses the canonical runs/ root", False, "no exception")
    except guard.CanonicalWriteRefused:
        check("analyser refuses the canonical runs/ root", True)
    except SystemExit:
        check("analyser refuses the canonical runs/ root", False, "wrong error type")

    print(f"\n{'=' * 62}")
    print(f"{PASS} passed, {FAIL} failed")
    print("SYNTHETIC SELF-TEST — produces no experimental result")
    print("=" * 62)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
