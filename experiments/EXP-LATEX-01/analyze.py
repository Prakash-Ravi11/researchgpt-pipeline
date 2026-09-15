"""EXP-LATEX-01 paired analysis: per-paper arms -> CSVs, statistics, plots.

Input  : runs/exp-latex-01/<arm>/per_paper.json for each arm being compared.
         Shape: {"arm": "...", "papers": {"<paper_id>": {"<metric>": value, ...}}}
Output : runs/exp-latex-01/
           paper_level_results.csv        (Part 14, one row per paper per metric)
           metrics_summary.csv            (Part 14, exact column set)
           statistical_analysis/*.json
           plots/*.svg                    (Part 27)

Integrity rules enforced here, not left to the writer of the report:

* A metric absent from a paper in EITHER arm is dropped from that metric's
  paired sample and COUNTED in `n_missing`. It is never imputed.
* A metric with no usable pairs still gets a row, with every statistic blank
  and `interpretation` = "NOT MEASURED".
* p-values are Holm-corrected across the pre-registered confirmatory family
  (metrics_registry.CONFIRMATORY); exploratory metrics are reported with raw
  p-values and labelled exploratory.
* No plot is drawn for a metric with fewer than 3 paired observations.

Usage:
    python experiments/EXP-LATEX-01/analyze.py --control control --treatment latex
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guard
import paired_stats as ps
from metrics_registry import BY_KEY, CONFIRMATORY, METRICS

MISSING = object()


# --- loading ----------------------------------------------------------------

def load_arm(arm: str, root: Path) -> dict[str, dict]:
    path = guard.assert_experiment_output(root / arm / "per_paper.json")
    if not path.exists():
        raise SystemExit(
            f"arm data not found: {path}\n"
            f"EXP-LATEX-01 has no results for arm {arm!r}. Run the arm first "
            f"(experiments/EXP-LATEX-01/run_arm.py) — this analyser will not "
            f"invent values."
        )
    data = json.loads(path.read_text())
    return data["papers"]


def paired_values(ctl: dict, trt: dict, key: str):
    """Papers present in BOTH arms with a non-null value for `key`."""
    pairs, missing = [], []
    for pid in sorted(set(ctl) | set(trt)):
        a = ctl.get(pid, {}).get(key, MISSING)
        b = trt.get(pid, {}).get(key, MISSING)
        if a is MISSING or b is MISSING or a is None or b is None:
            missing.append(pid)
            continue
        pairs.append((pid, a, b))
    return pairs, missing


# --- testing ----------------------------------------------------------------

def test_metric(metric, pairs) -> list[ps.TestResult]:
    """Pre-registered test(s) for one metric. Returns [] when untestable."""
    if not pairs:
        return []
    ctl = [p[1] for p in pairs]
    trt = [p[2] for p in pairs]
    out: list[ps.TestResult] = []
    if metric.kind == "binary":
        out.append(ps.mcnemar([bool(x) for x in ctl], [bool(x) for x in trt],
                              metric=metric.key))
    elif metric.kind in ("continuous",):
        out.append(ps.paired_t([float(x) for x in ctl], [float(x) for x in trt],
                               metric=metric.key))
        out.append(ps.wilcoxon_signed_rank([float(x) for x in ctl],
                                           [float(x) for x in trt], metric=metric.key))
    else:  # proportion, count
        out.append(ps.wilcoxon_signed_rank([float(x) for x in ctl],
                                           [float(x) for x in trt], metric=metric.key))
    return out


def primary_result(results: list[ps.TestResult]) -> ps.TestResult | None:
    """The row that goes into metrics_summary.csv.

    For continuous metrics both a t-test and a Wilcoxon are run; the Wilcoxon is
    reported as primary because n=60 paper-level metrics in this project are
    bounded rates and counts, which are not plausibly normal. The t-test is
    kept in the JSON so the choice is auditable, not hidden.
    """
    if not results:
        return None
    for r in results:
        if r.test == "wilcoxon_signed_rank":
            return r
    return results[0]


# --- SVG plotting (no matplotlib in this project) ---------------------------

def _svg_header(w, h, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="Helvetica,Arial,sans-serif">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>'
            f'<text x="{w/2}" y="24" text-anchor="middle" font-size="15" '
            f'font-weight="600" fill="#111">{title}</text>')


def plot_paired_diff(metric_key: str, label: str, pairs, out_path: Path):
    """Per-paper difference distribution with a mean and a bootstrap CI."""
    diffs = sorted(float(b) - float(a) for _, a, b in pairs)
    n = len(diffs)
    if n < 3:
        return None
    W, H = 760, 360
    L, R, T, B = 70, 30, 50, 60
    pw, ph = W - L - R, H - T - B
    lo, hi = min(diffs + [0.0]), max(diffs + [0.0])
    if hi == lo:
        hi = lo + 1e-9
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    def x(i):  return L + (pw * (i + 0.5) / n)
    def y(v):  return T + ph - (v - lo) / (hi - lo) * ph

    m = ps.mean(diffs)
    ci = ps.bootstrap_ci(diffs, seed=42)
    parts = [_svg_header(W, H, f"{label} — per-paper change (treatment − control)")]
    # zero line
    parts.append(f'<line x1="{L}" y1="{y(0):.1f}" x2="{W-R}" y2="{y(0):.1f}" '
                 f'stroke="#888" stroke-dasharray="4 3"/>')
    # CI band
    if ci[0] is not None:
        parts.append(f'<rect x="{L}" y="{y(ci[1]):.1f}" width="{pw}" '
                     f'height="{abs(y(ci[0])-y(ci[1])):.1f}" fill="#4C78A8" '
                     f'opacity="0.13"/>')
    # bars
    for i, d in enumerate(diffs):
        col = "#2E7D32" if d > 0 else ("#C62828" if d < 0 else "#9E9E9E")
        y0, y1 = (y(d), y(0)) if d >= 0 else (y(0), y(d))
        parts.append(f'<rect x="{x(i)-max(1.0,pw/n*0.4):.1f}" y="{y0:.1f}" '
                     f'width="{max(2.0,pw/n*0.8):.1f}" height="{abs(y1-y0):.1f}" '
                     f'fill="{col}"/>')
    # mean line
    parts.append(f'<line x1="{L}" y1="{y(m):.1f}" x2="{W-R}" y2="{y(m):.1f}" '
                 f'stroke="#4C78A8" stroke-width="2"/>')
    # axes
    parts.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{T+ph}" stroke="#333"/>')
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        v = lo + (hi - lo) * frac
        parts.append(f'<text x="{L-8}" y="{y(v)+4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#444">{v:.3g}</text>')
    up = sum(1 for d in diffs if d > 0)
    dn = sum(1 for d in diffs if d < 0)
    citxt = (f"95% CI [{ci[0]:.3g}, {ci[1]:.3g}]" if ci[0] is not None else "CI n/a")
    parts.append(f'<text x="{L}" y="{H-24}" font-size="11" fill="#333">'
                 f'n={n} papers · {up} improved · {dn} regressed · '
                 f'{n-up-dn} unchanged · mean={m:.3g} · {citxt} (seeded bootstrap)</text>')
    parts.append(f'<text x="{L}" y="{H-8}" font-size="10" fill="#777">'
                 f'Each bar is one paper. Shaded band = bootstrap CI of the mean '
                 f'difference. Zero line dashed.</text>')
    parts.append("</svg>")
    out_path.write_text("".join(parts), encoding="utf-8")
    return out_path


def plot_arm_comparison(rows, out_path: Path, title):
    """Control vs treatment for metrics on a 0-1 scale, with CIs where present."""
    sel = [r for r in rows
           if r["control"] not in ("", None) and r["treatment"] not in ("", None)
           and 0.0 <= float(r["control"]) <= 1.0 and 0.0 <= float(r["treatment"]) <= 1.0]
    if not sel:
        return None
    W = 780
    H = 90 + 34 * len(sel)
    L, R = 250, 60
    pw = W - L - R
    parts = [_svg_header(W, H, title)]
    for i, r in enumerate(sel):
        yy = 60 + 34 * i
        c, t = float(r["control"]), float(r["treatment"])
        parts.append(f'<text x="{L-10}" y="{yy+4}" text-anchor="end" font-size="11" '
                     f'fill="#222">{r["metric_label"][:40]}</text>')
        parts.append(f'<line x1="{L}" y1="{yy}" x2="{L+pw}" y2="{yy}" stroke="#e5e5e5"/>')
        parts.append(f'<circle cx="{L+pw*c:.1f}" cy="{yy}" r="5" fill="#9E9E9E"/>')
        parts.append(f'<circle cx="{L+pw*t:.1f}" cy="{yy}" r="5" fill="#4C78A8"/>')
        parts.append(f'<line x1="{L+pw*c:.1f}" y1="{yy}" x2="{L+pw*t:.1f}" y2="{yy}" '
                     f'stroke="#4C78A8" stroke-width="2" opacity="0.6"/>')
        parts.append(f'<text x="{L+pw+8}" y="{yy+4}" font-size="10" fill="#444">'
                     f'{c:.3f}&#8594;{t:.3f}</text>')
    parts.append(f'<text x="{L}" y="{H-18}" font-size="11" fill="#333">'
                 f'grey = control · blue = treatment · only 0–1 scaled metrics shown</text>')
    parts.append("</svg>")
    out_path.write_text("".join(parts), encoding="utf-8")
    return out_path


# --- main -------------------------------------------------------------------

def run(control_arm: str, treatment_arm: str, root: Path, alpha: float = 0.05):
    ctl = load_arm(control_arm, root)
    trt = load_arm(treatment_arm, root)

    guard.ensure_tree(root)
    plots_dir = guard.assert_experiment_output(root / "plots")
    plots_dir.mkdir(parents=True, exist_ok=True)
    stats_dir = guard.assert_experiment_output(root / "statistical_analysis")

    per_metric: dict[str, dict] = {}
    paper_rows: list[dict] = []

    for metric in METRICS:
        pairs, missing = paired_values(ctl, trt, metric.key)
        results = test_metric(metric, pairs)
        per_metric[metric.key] = {
            "metric": metric.key, "label": metric.label, "group": metric.group,
            "kind": metric.kind, "higher_is_better": metric.higher_is_better,
            "gate": metric.gate, "note": metric.note,
            "n_paired": len(pairs), "n_missing": len(missing),
            "missing_papers": missing,
            "control_desc": ps.describe([float(p[1]) for p in pairs]) if pairs else None,
            "treatment_desc": ps.describe([float(p[2]) for p in pairs]) if pairs else None,
            "tests": [r.as_dict() for r in results],
        }
        for pid, a, b in pairs:
            try:
                fa, fb = float(a), float(b)
                diff = fb - fa
                rel = (diff / fa) if fa else None
            except (TypeError, ValueError):
                fa = fb = diff = rel = None
            paper_rows.append({
                "paper_id": pid, "metric": metric.key, "metric_label": metric.label,
                "control_score": fa, "latex_score": fb,
                "difference": diff,
                "relative_difference": "" if rel is None else f"{rel:.6f}",
            })

    # Holm across the pre-registered confirmatory family only
    fam = {}
    for k in CONFIRMATORY:
        r = primary_result([ps.TestResult(**t) for t in per_metric[k]["tests"]]) \
            if per_metric[k]["tests"] else None
        fam[k] = r.p_value if r else None
    adjusted = ps.holm(fam, alpha=alpha)

    # --- metrics_summary.csv (Part 14 column set) ---
    summary_rows = []
    for metric in METRICS:
        rec = per_metric[metric.key]
        tests = [ps.TestResult(**t) for t in rec["tests"]]
        r = primary_result(tests)
        in_family = metric.key in CONFIRMATORY
        p_adj = adjusted.get(metric.key, {}).get("p_adjusted") if in_family else None
        if r:
            r.p_adjusted = p_adj
        if r is None or rec["n_paired"] == 0:
            interp = "NOT MEASURED — no paired observations in this run"
        else:
            interp = ps.interpret(r, alpha=alpha)
            if not in_family:
                interp = "EXPLORATORY (not in the corrected family) — " + interp
        summary_rows.append({
            "metric": metric.key,
            "metric_label": metric.label,
            "group": metric.group,
            "n_paired": rec["n_paired"],
            "n_missing": rec["n_missing"],
            "control": "" if r is None or r.control is None else f"{r.control:.6f}",
            "treatment": "" if r is None or r.treatment is None else f"{r.treatment:.6f}",
            "absolute_delta": "" if r is None or r.absolute_delta is None else f"{r.absolute_delta:.6f}",
            "relative_delta": "" if r is None or r.relative_delta is None else f"{r.relative_delta:.6f}",
            "CI_low": "" if r is None or r.ci_low is None else f"{r.ci_low:.6f}",
            "CI_high": "" if r is None or r.ci_high is None else f"{r.ci_high:.6f}",
            "statistical_test": "" if r is None else r.test,
            "test_statistic": "" if r is None or r.statistic is None else f"{r.statistic:.6f}",
            "p_value": "" if r is None or r.p_value is None else f"{r.p_value:.6g}",
            "p_adjusted": "" if p_adj is None else f"{p_adj:.6g}",
            "effect_size": "" if r is None or r.effect_size is None else f"{r.effect_size:.6f}",
            "effect_name": "" if r is None else r.effect_name,
            "gate": metric.gate or "",
            "interpretation": interp,
        })

    out_summary = guard.assert_experiment_output(root / "metrics_summary.csv")
    with out_summary.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader(); w.writerows(summary_rows)

    out_papers = guard.assert_experiment_output(root / "paper_level_results.csv")
    with out_papers.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "metric", "metric_label",
                                          "control_score", "latex_score",
                                          "difference", "relative_difference"])
        w.writeheader(); w.writerows(paper_rows)

    (stats_dir / "per_metric.json").write_text(
        json.dumps({"control_arm": control_arm, "treatment_arm": treatment_arm,
                    "alpha": alpha, "confirmatory_family": list(CONFIRMATORY),
                    "holm": adjusted, "metrics": per_metric}, indent=2, default=str))

    # --- plots ---
    made = []
    for metric in METRICS:
        pairs, _ = paired_values(ctl, trt, metric.key)
        p = plot_paired_diff(metric.key, metric.label, pairs,
                             plots_dir / f"paired_{metric.key}.svg")
        if p:
            made.append(p.name)
    p = plot_arm_comparison(summary_rows, plots_dir / "arm_comparison.svg",
                            f"{control_arm} vs {treatment_arm} — rate metrics")
    if p:
        made.append(p.name)

    n_measured = sum(1 for r in summary_rows if r["n_paired"])
    print(f"metrics_summary.csv      -> {out_summary}")
    print(f"paper_level_results.csv  -> {out_papers}")
    print(f"statistical_analysis     -> {stats_dir / 'per_metric.json'}")
    print(f"plots                    -> {len(made)} SVG in {plots_dir}")
    print(f"metrics with paired data : {n_measured}/{len(summary_rows)}")
    if n_measured == 0:
        print("NOTE: no metric had paired observations — every row reads NOT MEASURED.")
    return summary_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", default="control")
    ap.add_argument("--treatment", default="latex")
    ap.add_argument("--root", default=guard.EXPERIMENT_ROOT)
    ap.add_argument("--alpha", type=float, default=0.05)
    a = ap.parse_args()
    run(a.control, a.treatment, Path(guard.assert_experiment_output(a.root)), a.alpha)


if __name__ == "__main__":
    main()
