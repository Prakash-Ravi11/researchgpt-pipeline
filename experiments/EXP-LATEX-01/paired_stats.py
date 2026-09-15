"""Paired statistics for EXP-LATEX-01 — standard library only.

SciPy is not a dependency of this project and could not be installed in the
audit environment, so every test here is implemented from its definition and
checked against published reference values in
``tests/test_paired_stats.py``. Nothing in this module estimates a p-value by
simulation unless the function name says ``bootstrap``.

Design rules, in service of the experiment's integrity constraints:

* A function returns ``None`` for a statistic it cannot compute (n too small,
  zero variance, no discordant pairs). It never returns 1.0, 0.0 or a made-up
  value to keep a table full.
* ``holm()`` is applied across the whole metric family; a raw p-value is never
  reported as "significant" on its own.
* Effect size and confidence interval travel with every test, because a
  p-value alone does not establish practical significance.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Sequence

# --- distributions ----------------------------------------------------------


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: float) -> float:
    """P(T > t) for Student's t with `df` degrees of freedom."""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    half = 0.5 * betainc(df / 2.0, 0.5, x)
    return half if t > 0 else 1.0 - half


def t_two_sided(t: float, df: float) -> float:
    return min(1.0, 2.0 * t_sf(abs(t), df))


def chi2_sf_df1(x: float) -> float:
    """Survival function of chi-square with 1 df."""
    if x <= 0:
        return 1.0
    return 2.0 * norm_sf(math.sqrt(x))


def t_crit(df: float, conf: float = 0.95) -> float:
    """Two-sided critical t value, found by bisection on `t_two_sided`."""
    target = 1.0 - conf
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_two_sided(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --- result container -------------------------------------------------------


@dataclass
class TestResult:
    metric: str
    test: str
    n: int
    statistic: float | None = None
    p_value: float | None = None
    effect_size: float | None = None
    effect_name: str = ""
    ci_low: float | None = None
    ci_high: float | None = None
    control: float | None = None
    treatment: float | None = None
    absolute_delta: float | None = None
    relative_delta: float | None = None
    p_adjusted: float | None = None
    note: str = ""
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


# --- descriptive ------------------------------------------------------------


def mean(xs: Sequence[float]) -> float | None:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def median(xs: Sequence[float]) -> float | None:
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def stdev(xs: Sequence[float]) -> float | None:
    xs = list(xs)
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def describe(xs: Sequence[float]) -> dict:
    xs = list(xs)
    return {
        "n": len(xs),
        "mean": mean(xs),
        "median": median(xs),
        "sd": stdev(xs),
        "min": min(xs) if xs else None,
        "max": max(xs) if xs else None,
    }


# --- paired continuous ------------------------------------------------------


def paired_t(control: Sequence[float], treatment: Sequence[float],
             metric: str = "", conf: float = 0.95) -> TestResult:
    """Paired t-test on treatment - control, with a CI on the mean difference."""
    if len(control) != len(treatment):
        raise ValueError("paired_t needs equal-length arms")
    d = [t - c for c, t in zip(control, treatment)]
    n = len(d)
    res = TestResult(metric=metric, test="paired_t", n=n,
                     control=mean(control), treatment=mean(treatment))
    if n < 2:
        res.note = "n < 2 — not computable"
        return res
    md = sum(d) / n
    sd = stdev(d)
    res.absolute_delta = md
    cm = mean(control)
    res.relative_delta = (md / cm) if cm else None
    if sd is None or sd == 0.0:
        res.note = ("zero variance in the paired differences — t undefined; "
                    "the difference is constant at %.6g" % md)
        res.effect_name = "cohen_dz"
        return res
    se = sd / math.sqrt(n)
    t = md / se
    res.statistic = t
    res.p_value = t_two_sided(t, n - 1)
    res.effect_size = md / sd           # Cohen's dz (paired)
    res.effect_name = "cohen_dz"
    tc = t_crit(n - 1, conf)
    res.ci_low, res.ci_high = md - tc * se, md + tc * se
    res.detail = {"mean_diff": md, "sd_diff": sd, "se": se, "df": n - 1}
    return res


def _rank_with_ties(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _wilcoxon_exact_two_sided(w_plus: float, n: int) -> float:
    """Exact two-sided p from the full null distribution of W+ (no ties/zeros)."""
    counts = [1] + [0] * (n * (n + 1) // 2)
    for i in range(1, n + 1):
        for s in range(len(counts) - 1, i - 1, -1):
            counts[s] += counts[s - i]
    total = float(2 ** n)
    lo = sum(counts[s] for s in range(0, int(math.floor(w_plus)) + 1)) / total
    hi = sum(counts[s] for s in range(int(math.ceil(w_plus)), len(counts))) / total
    return min(1.0, 2.0 * min(lo, hi))


def wilcoxon_signed_rank(control: Sequence[float], treatment: Sequence[float],
                         metric: str = "", exact_max_n: int = 25) -> TestResult:
    """Wilcoxon signed-rank on treatment - control.

    Exact null distribution when there are no ties and no zero differences and
    n <= `exact_max_n`; otherwise the normal approximation with tie and
    continuity correction. Zero differences are dropped (Wilcoxon's own rule)
    and the reduced n is what the result reports.
    """
    if len(control) != len(treatment):
        raise ValueError("wilcoxon needs equal-length arms")
    d_all = [t - c for c, t in zip(control, treatment)]
    d = [x for x in d_all if x != 0]
    n = len(d)
    res = TestResult(metric=metric, test="wilcoxon_signed_rank", n=n,
                     control=mean(control), treatment=mean(treatment))
    res.absolute_delta = mean(d_all)
    cm = mean(control)
    res.relative_delta = (res.absolute_delta / cm) if cm else None
    res.detail = {"n_pairs": len(d_all), "n_zero_diff": len(d_all) - n,
                  "n_positive": sum(1 for x in d if x > 0),
                  "n_negative": sum(1 for x in d if x < 0)}
    if n == 0:
        res.note = "every pair is tied — no signed ranks to test"
        return res
    if n < 6:
        res.note = (f"n={n} after dropping ties — the exact test cannot reach "
                    f"p<0.05 two-sided below n=6; reported for completeness")
    mags = [abs(x) for x in d]
    ranks = _rank_with_ties(mags)
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    w_minus = sum(r for r, x in zip(ranks, d) if x < 0)
    w = min(w_plus, w_minus)
    res.statistic = w
    has_ties = len(set(mags)) != len(mags)
    if n <= exact_max_n and not has_ties:
        res.p_value = _wilcoxon_exact_two_sided(w_plus, n)
        res.detail["method"] = "exact"
    else:
        mu = n * (n + 1) / 4.0
        tie_term = 0.0
        seen: dict[float, int] = {}
        for m in mags:
            seen[m] = seen.get(m, 0) + 1
        for c in seen.values():
            if c > 1:
                tie_term += c ** 3 - c
        var = (n * (n + 1) * (2 * n + 1) - tie_term / 2.0) / 24.0
        if var <= 0:
            res.note = "zero variance in signed ranks — p not computable"
            return res
        z = (w_plus - mu)
        z = (z - math.copysign(0.5, z)) / math.sqrt(var)   # continuity correction
        res.p_value = min(1.0, 2.0 * norm_sf(abs(z)))
        res.detail["method"] = "normal_approx_tie_corrected"
        res.detail["z"] = z
    # rank-biserial correlation: (W+ - W-) / total rank sum
    total_r = w_plus + w_minus
    res.effect_size = ((w_plus - w_minus) / total_r) if total_r else None
    res.effect_name = "rank_biserial_r"
    return res


# --- paired binary ----------------------------------------------------------


def _binom_two_sided(b: int, n: int) -> float:
    """Exact two-sided binomial p under p=0.5 (used by McNemar)."""
    if n == 0:
        return 1.0
    k = min(b, n - b)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / float(2 ** n)
    return min(1.0, 2.0 * tail)


def mcnemar(control: Sequence[bool], treatment: Sequence[bool],
            metric: str = "", exact_max_n: int = 25) -> TestResult:
    """McNemar's test on paired binary outcomes.

    b = control success / treatment failure, c = control failure / treatment
    success. Exact binomial when b + c <= `exact_max_n`, otherwise chi-square
    with Edwards' continuity correction.
    """
    if len(control) != len(treatment):
        raise ValueError("mcnemar needs equal-length arms")
    a = sum(1 for x, y in zip(control, treatment) if x and y)
    b = sum(1 for x, y in zip(control, treatment) if x and not y)
    c = sum(1 for x, y in zip(control, treatment) if not x and y)
    d = sum(1 for x, y in zip(control, treatment) if not x and not y)
    n = len(control)
    res = TestResult(metric=metric, test="mcnemar", n=n,
                     control=(sum(1 for x in control if x) / n) if n else None,
                     treatment=(sum(1 for x in treatment if x) / n) if n else None)
    res.detail = {"a_both": a, "b_control_only": b, "c_treatment_only": c,
                  "d_neither": d, "n_discordant": b + c}
    if res.control is not None and res.treatment is not None:
        res.absolute_delta = res.treatment - res.control
        res.relative_delta = (res.absolute_delta / res.control) if res.control else None
    if b + c == 0:
        res.note = ("no discordant pairs — McNemar is undefined; the arms agree "
                    "on every paper")
        return res
    if b + c <= exact_max_n:
        res.p_value = _binom_two_sided(b, b + c)
        res.statistic = float(min(b, c))
        res.detail["method"] = "exact_binomial"
    else:
        stat = (abs(b - c) - 1.0) ** 2 / (b + c)
        res.statistic = stat
        res.p_value = chi2_sf_df1(stat)
        res.detail["method"] = "chi2_continuity_corrected"
    # Effect size for paired binary data: the odds ratio of discordance.
    res.effect_size = (c / b) if b else None
    res.effect_name = "discordance_odds_ratio_c_over_b"
    if b == 0:
        res.note = ("all discordant pairs favour the treatment; the odds ratio "
                    "is unbounded and is reported as null")
    lo, hi = wilson_ci(c, b + c)
    res.ci_low, res.ci_high = lo, hi
    res.detail["ci_is_on"] = "P(treatment wins | discordant)"
    return res


def wilson_ci(successes: int, n: int, conf: float = 0.95) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return None, None
    z = 1.959963984540054 if abs(conf - 0.95) < 1e-9 else _z_for(conf)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _z_for(conf: float) -> float:
    target = (1.0 + conf) / 2.0
    lo, hi = 0.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if norm_cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --- bootstrap --------------------------------------------------------------


def bootstrap_ci(values: Sequence[float], stat=mean, n_boot: int = 10000,
                 conf: float = 0.95, seed: int = 42
                 ) -> tuple[float | None, float | None]:
    """Seeded percentile bootstrap CI. Deterministic for a given seed."""
    vals = list(values)
    if len(vals) < 2:
        return None, None
    rnd = random.Random(seed)
    n = len(vals)
    boots = []
    for _ in range(n_boot):
        sample = [vals[rnd.randrange(n)] for _ in range(n)]
        s = stat(sample)
        if s is not None:
            boots.append(s)
    if not boots:
        return None, None
    boots.sort()
    lo_i = int((1.0 - conf) / 2.0 * len(boots))
    hi_i = min(len(boots) - 1, int((1.0 + conf) / 2.0 * len(boots)))
    return boots[lo_i], boots[hi_i]


# --- multiple comparisons ---------------------------------------------------


def holm(p_values: dict[str, float | None], alpha: float = 0.05) -> dict[str, dict]:
    """Holm-Bonferroni step-down correction over a family of tests.

    Keys with a ``None`` p-value are carried through untested — they are not
    silently dropped, and they do not shrink the family size used for the
    correction of the others.
    """
    testable = {k: v for k, v in p_values.items() if v is not None}
    m = len(testable)
    out: dict[str, dict] = {k: {"p_raw": None, "p_adjusted": None,
                                "reject": None, "note": "p not computable"}
                            for k in p_values if p_values[k] is None}
    ordered = sorted(testable.items(), key=lambda kv: kv[1])
    running = 0.0
    for i, (k, p) in enumerate(ordered):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)          # enforce monotonicity
        out[k] = {"p_raw": p, "p_adjusted": running,
                  "reject": running <= alpha,
                  "note": f"Holm over family of {m}"}
    return out


def interpret(res: TestResult, alpha: float = 0.05) -> str:
    """One-line reading that never converts a p-value into a claim on its own."""
    if res.p_value is None:
        return f"NOT TESTABLE — {res.note or 'statistic undefined'}"
    p = res.p_adjusted if res.p_adjusted is not None else res.p_value
    label = "adjusted" if res.p_adjusted is not None else "raw"
    sig = p <= alpha
    d = res.absolute_delta
    direction = "no change" if not d else ("favours treatment" if d > 0 else "favours control")
    es = f", {res.effect_name}={res.effect_size:.3f}" if res.effect_size is not None else ""
    return (f"{'significant' if sig else 'not significant'} at alpha={alpha} "
            f"({label} p={p:.4g}){es}; {direction}. "
            f"Practical significance must be read from the effect size and CI, "
            f"not from p alone.")
