"""Validation of paired_stats against published reference values.

SciPy is unavailable in this project, so correctness is established against
sources that do not depend on it:

  * Student-t critical values from standard t-tables (two-sided alpha = 0.05).
  * Normal quantiles (1.959964, 1.644854, 2.575829).
  * Wilcoxon signed-rank exact tail probabilities derived by construction --
    for n pairs the null distribution of W+ is the subset-sum distribution over
    2^n equally likely sign assignments, so P(W+ = 0) = 1/2^n exactly.
  * McNemar exact = the two-sided binomial tail, computed here from
    math.comb independently of the implementation under test.
  * Wilson interval values from Newcombe (1998) worked examples.

Run:  python experiments/EXP-LATEX-01/tests/test_paired_stats.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paired_stats as ps

PASS = FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    line = f"  [{'PASS' if cond else 'FAIL'}] {label}"
    if detail and not cond:
        line += f" — {detail}"
    print(line)


def close(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


def test_distributions():
    print("\n1. distribution functions vs published tables")
    # Normal quantiles
    check("Phi(1.959964) = 0.975", close(ps.norm_cdf(1.959963985), 0.975, 1e-9))
    check("Phi(1.644854) = 0.95", close(ps.norm_cdf(1.644853627), 0.95, 1e-9))
    check("Phi(2.575829) = 0.995", close(ps.norm_cdf(2.575829304), 0.995, 1e-9))
    # Two-sided t critical values, standard t-table, alpha = 0.05
    for df, tcrit in [(1, 12.70620), (2, 4.302653), (5, 2.570582),
                      (9, 2.262157), (10, 2.228139), (30, 2.042272),
                      (60, 2.000298), (120, 1.979930)]:
        p = ps.t_two_sided(tcrit, df)
        check(f"t-table df={df}: t={tcrit} -> p=0.05", close(p, 0.05, 1e-5), f"p={p!r}")
    # inverse agrees with the table
    for df, tcrit in [(9, 2.262157), (30, 2.042272)]:
        check(f"t_crit(df={df}) recovers {tcrit}", close(ps.t_crit(df), tcrit, 1e-4),
              f"{ps.t_crit(df)!r}")
    # chi-square df=1
    check("chi2_sf_df1(3.841459) = 0.05", close(ps.chi2_sf_df1(3.8414588), 0.05, 1e-7))
    check("chi2_sf_df1(6.634897) = 0.01", close(ps.chi2_sf_df1(6.6348966), 0.01, 1e-7))
    # Closed forms for the two degrees of freedom where the t CDF is elementary.
    # df=1 is Cauchy: two-sided p = 1 - (2/pi) * arctan|t|
    for t in (0.5, 1.0, 2.0, 5.0, 12.7062):
        exact = 1.0 - (2.0 / math.pi) * math.atan(abs(t))
        check(f"df=1 Cauchy closed form at t={t}",
              close(ps.t_two_sided(t, 1), exact, 1e-9),
              f"{ps.t_two_sided(t, 1)} vs {exact}")
    # df=2: two-sided p = 1 - |t| / sqrt(2 + t^2)
    for t in (0.5, 1.0, 2.0, 4.302653, 9.0):
        exact = 1.0 - abs(t) / math.sqrt(2.0 + t * t)
        check(f"df=2 closed form at t={t}",
              close(ps.t_two_sided(t, 2), exact, 1e-9),
              f"{ps.t_two_sided(t, 2)} vs {exact}")


def test_paired_t():
    print("\n2. paired t-test")
    # Constructed so the answer is checkable by hand:
    # differences are 1..10 -> mean 5.5, sd = 3.02765..., n=10
    control = [0.0] * 10
    treatment = [float(i) for i in range(1, 11)]
    r = ps.paired_t(control, treatment, metric="hand")
    sd = math.sqrt(sum((d - 5.5) ** 2 for d in range(1, 11)) / 9.0)
    t_expected = 5.5 / (sd / math.sqrt(10))
    check("mean difference = 5.5", close(r.absolute_delta, 5.5))
    check("t matches the definition", close(r.statistic, t_expected, 1e-9),
          f"{r.statistic} vs {t_expected}")
    check("df = n-1", r.detail["df"] == 9)
    check("Cohen's dz = meandiff/sd", close(r.effect_size, 5.5 / sd, 1e-12))
    check("p is two-sided and small (t=5.7446, df=9 -> p=2.782e-4)",
          close(r.p_value, 0.000278196011, 1e-9), f"{r.p_value!r}")
    # CI must be mean +- t_crit * se
    se = sd / math.sqrt(10)
    tc = ps.t_crit(9)
    check("CI lower = mean - t*se", close(r.ci_low, 5.5 - tc * se, 1e-6))
    check("CI upper = mean + t*se", close(r.ci_high, 5.5 + tc * se, 1e-6))
    # identical arms
    r0 = ps.paired_t([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    check("identical arms -> no p, explicit note",
          r0.p_value is None and "zero variance" in r0.note, r0.note)
    # n<2 refuses rather than inventing
    r1 = ps.paired_t([1.0], [2.0])
    check("n=1 refuses", r1.p_value is None and "n < 2" in r1.note, r1.note)


def test_wilcoxon():
    print("\n3. Wilcoxon signed-rank (exact)")
    # All differences positive -> W+ is maximal, W- = 0.
    # P(W+ = max) = 1/2^n, two-sided p = 2/2^n.
    for n in (5, 6, 8, 10):
        ctl = [0.0] * n
        trt = [float(i) for i in range(1, n + 1)]      # distinct magnitudes, no ties
        r = ps.wilcoxon_signed_rank(ctl, trt)
        expected = min(1.0, 2.0 / (2 ** n))
        check(f"n={n}: all-positive gives exact p=2/2^{n}={expected:.6g}",
              close(r.p_value, expected, 1e-12), f"{r.p_value!r}")
        check(f"n={n}: rank-biserial r = +1", close(r.effect_size, 1.0, 1e-12))
        check(f"n={n}: method is exact", r.detail["method"] == "exact")
    # A mixed case, verified by brute force over all 2^n sign assignments.
    diffs = [3.0, -1.0, 4.0, -2.0, 5.0, 6.0, -7.0, 8.0]
    n = len(diffs)
    r = ps.wilcoxon_signed_rank([0.0] * n, diffs)
    mags = sorted(abs(d) for d in diffs)
    rank = {m: i + 1 for i, m in enumerate(mags)}
    w_plus_obs = sum(rank[abs(d)] for d in diffs if d > 0)
    # brute force the exact null
    tot = 0
    lo = hi = 0
    for mask in range(2 ** n):
        s = sum(i + 1 for i in range(n) if mask >> i & 1)
        tot += 1
        if s <= w_plus_obs:
            lo += 1
        if s >= w_plus_obs:
            hi += 1
    expected = min(1.0, 2.0 * min(lo, hi) / tot)
    check("mixed signs match a brute-force exact null",
          close(r.p_value, expected, 1e-12), f"{r.p_value} vs {expected}")
    # zero differences are dropped and reported
    r2 = ps.wilcoxon_signed_rank([1.0, 2.0, 3.0, 4.0], [1.0, 3.0, 4.0, 5.0])
    check("zero differences dropped from n", r2.n == 3, str(r2.n))
    check("dropped count recorded", r2.detail["n_zero_diff"] == 1)
    # all tied
    r3 = ps.wilcoxon_signed_rank([1.0, 2.0], [1.0, 2.0])
    check("all tied -> no p, explicit note", r3.p_value is None and "tied" in r3.note)
    # ties in magnitude force the normal approximation
    r4 = ps.wilcoxon_signed_rank([0.0] * 30, [1.0] * 15 + [-1.0] * 15)
    check("tied magnitudes use the tie-corrected normal approx",
          r4.detail["method"] == "normal_approx_tie_corrected")


def test_mcnemar():
    print("\n4. McNemar")
    # b = 1 control-only success, c = 9 treatment-only successes.
    control = [True] + [False] * 9 + [True] * 5
    treatment = [False] + [True] * 9 + [True] * 5
    r = ps.mcnemar(control, treatment)
    check("b counted correctly", r.detail["b_control_only"] == 1, str(r.detail))
    check("c counted correctly", r.detail["c_treatment_only"] == 9, str(r.detail))
    expected = 2.0 * (math.comb(10, 0) + math.comb(10, 1)) / 2 ** 10   # 22/1024
    check(f"exact two-sided binomial p = {expected}", close(r.p_value, expected, 1e-12),
          f"{r.p_value!r}")
    check("method is exact", r.detail["method"] == "exact_binomial")
    # large discordant count -> chi2 with continuity correction
    b, c = 20, 40
    ctl = [True] * b + [False] * c
    trt = [False] * b + [True] * c
    r2 = ps.mcnemar(ctl, trt)
    stat = (abs(b - c) - 1.0) ** 2 / (b + c)
    check("chi2 statistic matches Edwards' correction", close(r2.statistic, stat, 1e-12))
    check("p matches chi2 df=1", close(r2.p_value, ps.chi2_sf_df1(stat), 1e-12))
    # no discordance
    r3 = ps.mcnemar([True, False], [True, False])
    check("no discordant pairs -> no p, explicit note",
          r3.p_value is None and "no discordant" in r3.note, r3.note)
    # perfect one-sided discordance: OR unbounded, reported as None not inf
    r4 = ps.mcnemar([False] * 8, [True] * 8)
    check("unbounded odds ratio reported as None with a note",
          r4.effect_size is None and "unbounded" in r4.note, r4.note)
    check("but p is still computed", close(r4.p_value, 2.0 / 2 ** 8, 1e-12))


def test_wilson():
    print("\n5. Wilson score interval (Newcombe 1998)")
    for succ, n, lo, hi in [(0, 10, 0.0000, 0.2775),
                            (10, 10, 0.7225, 1.0000),
                            (5, 10, 0.2366, 0.7634),
                            (81, 263, 0.2553, 0.3662)]:
        got_lo, got_hi = ps.wilson_ci(succ, n)
        check(f"Wilson {succ}/{n} = [{lo}, {hi}]",
              close(got_lo, lo, 5e-4) and close(got_hi, hi, 5e-4),
              f"got [{got_lo:.4f}, {got_hi:.4f}]")
    check("n=0 returns None, not 0", ps.wilson_ci(0, 0) == (None, None))


def test_bootstrap():
    print("\n6. bootstrap")
    vals = [float(i) for i in range(1, 51)]
    a = ps.bootstrap_ci(vals, seed=42)
    b = ps.bootstrap_ci(vals, seed=42)
    c = ps.bootstrap_ci(vals, seed=43)
    check("same seed is reproducible", a == b, f"{a} vs {b}")
    check("different seed differs", a != c)
    check("CI brackets the sample mean", a[0] < 25.5 < a[1], str(a))
    check("n<2 returns None", ps.bootstrap_ci([1.0]) == (None, None))


def test_holm():
    print("\n7. Holm-Bonferroni")
    ps_in = {"a": 0.001, "b": 0.013, "c": 0.02, "d": 0.30}
    out = ps.holm(ps_in, alpha=0.05)
    # m=4: 0.001*4=0.004; 0.013*3=0.039; 0.02*2=0.04; 0.30*1=0.30
    check("a adjusted = 0.004", close(out["a"]["p_adjusted"], 0.004, 1e-12))
    check("b adjusted = 0.039", close(out["b"]["p_adjusted"], 0.039, 1e-12))
    check("c adjusted = 0.04", close(out["c"]["p_adjusted"], 0.04, 1e-12))
    check("d adjusted = 0.30", close(out["d"]["p_adjusted"], 0.30, 1e-12))
    check("rejections follow the adjusted values",
          [out[k]["reject"] for k in "abcd"] == [True, True, True, False])
    # monotonicity enforcement
    out2 = ps.holm({"x": 0.02, "y": 0.021}, alpha=0.05)
    check("adjusted values are non-decreasing",
          out2["x"]["p_adjusted"] <= out2["y"]["p_adjusted"],
          f'{out2["x"]["p_adjusted"]} vs {out2["y"]["p_adjusted"]}')
    # untestable metrics are carried, not dropped, and do not shrink m
    out3 = ps.holm({"a": 0.01, "b": None, "c": 0.04})
    check("None p-value carried through", "b" in out3 and out3["b"]["p_adjusted"] is None)
    check("family size excludes untestable entries",
          close(out3["a"]["p_adjusted"], 0.02, 1e-12), str(out3["a"]))


def test_no_fabrication():
    print("\n8. refuses to fabricate")
    r = ps.paired_t([], [])
    check("empty arms -> None statistic", r.statistic is None and r.p_value is None)
    check("interpret() says NOT TESTABLE", ps.interpret(r).startswith("NOT TESTABLE"),
          ps.interpret(r))
    r2 = ps.paired_t([1.0, 2.0, 3.0], [2.0, 3.0, 4.0])
    check("constant difference -> p None with explanation",
          r2.p_value is None and "zero variance" in r2.note, r2.note)
    check("but the delta is still reported", close(r2.absolute_delta, 1.0))
    txt = ps.interpret(ps.paired_t([0.0] * 10, [float(i) for i in range(1, 11)]))
    check("interpret() always names the effect size caveat",
          "Practical significance" in txt, txt)


def main():
    print("=" * 62)
    print("EXP-LATEX-01 — paired_stats validation")
    print("=" * 62)
    test_distributions()
    test_paired_t()
    test_wilcoxon()
    test_mcnemar()
    test_wilson()
    test_bootstrap()
    test_holm()
    test_no_fabrication()
    print(f"\n{'=' * 62}")
    print(f"{PASS} passed, {FAIL} failed")
    print("=" * 62)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
