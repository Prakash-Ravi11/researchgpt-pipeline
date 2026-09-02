# ANCHOR RULE CENTRALIZATION — neutrality report

Branch `claude-code-verification` · HEAD `cc016cb` (+ this change) · 2026-09-02
Pure refactor. No behaviour change intended; neutrality is the point of the commit.

## What moved

New module **`src/evidence/anchors.py`** — single source of truth for the meaningful
numeric anchor rule (a decimal, or an integer of ≥ 2 digits; `find_anchors` additionally
drops 4-digit years, bracketed reference ids, numbers after `Section`/`Table`/`Eq.`/`v`/…,
and arXiv-id fragments). No single-digit-with-unit extension — it was never adopted in the
gate, so it is not part of the rule.

| file | before | after |
|---|---|---|
| `src/evidence/gate.py` | local `_NUMVAL = re.compile(r"\d+\.\d+|\b\d{2,}\b")` | `from .anchors import NUMERIC_ANCHOR_RE as _NUMVAL` |
| `experiments/…/gate_sensitivity.py` (Test 2) | `from src.evidence.gate import … _NUMVAL …` | `from src.evidence.anchors import NUMERIC_ANCHOR_RE as _NUMVAL` |
| `experiments/…/retrieval_recall.py` (Test 3) | local `_NUMVAL`, `_YEAR`, `_EXCLUDE_PREFIX`, `is_anchor()`, `anchors_in_text()` | `from src.evidence.anchors import NUMERIC_ANCHOR_RE as _NUMVAL, find_anchors as anchors_in_text` — the 4 local defs deleted |

Tests: **`tests/test_anchors.py`** (new, 9 cases) covers the token rule, every
`is_meaningful_anchor` exclusion branch, and a neutrality assertion against an inline
verbatim copy of the pre-centralization `anchors_in_text`/`is_anchor`.
`experiments/…/anchor_neutrality_check.py` runs the same comparison over the whole corpus.

Not touched (deliberately — not the anchor rule): `gate_sensitivity.py`'s `_SD_UNIT` /
`_SD_BYNUM` single-digit-*scan* (it counts what the rule *excludes*), its `_ROW_RE`
cross-row table regex, and the separate `NUMVAL` copies in `extraction_fidelity.py` /
`results_gate_sweep.py` (different tests, out of scope for this task).

## Neutrality — CONFIRMED

### 1. Raw rule, per chunk, whole canonical corpus

`anchor_neutrality_check.py`: for every one of **8 967 chunks across 34 papers**, the new
`find_anchors` returns a byte-identical list to the inline pre-centralization
implementation. Total raw anchors **13 828 (new) == 13 828 (old)**. Zero chunks differ.

Per-paper raw anchor count, before vs after (all equal):

| paper | before | after | | paper | before | after |
|---|--:|--:|---|---|--:|--:|
| 0549e2e9 | 421 | 421 | | be7c4dc3 | 206 | 206 |
| 10162507 | 161 | 161 | | c093b845 | 37 | 37 |
| 141276ba | 184 | 184 | | cf099b7c | 871 | 871 |
| 2009dbb5 | 166 | 166 | | d3b5f3c0 | 139 | 139 |
| 413a184d | 1382 | 1382 | | db78acdc | 183 | 183 |
| 4d6e977f | 824 | 824 | | ddb170b2 | 159 | 159 |
| 4f3fca4c | 144 | 144 | | e0efa866 | 592 | 592 |
| 6437463b | 276 | 276 | | e6f1d66c | 191 | 191 |
| 68f93a59 | 64 | 64 | | eaec7401 | 571 | 571 |
| 69b02cfe | 215 | 215 | | ef1e4a16 | 157 | 157 |
| 78797b71 | 73 | 73 | | f1f07a37 | 3104 | 3104 |
| 81e06066 | 154 | 154 | | f3b06a91 | 1656 | 1656 |
| 93db4f9a | 299 | 299 | | f3d7e016 | 122 | 122 |
| 96285d75 | 422 | 422 | | f42ad6e2 | 165 | 165 |
| a6d08e12 | 276 | 276 | | fef0393e | 334 | 334 |
| a6ecdf69 | 41 | 41 | | ac8fffa1 | 148 | 148 |
| a9b2a3fd | 58 | 58 | | ae276875 | 33 | 33 |

### 2. Test 3 — `retrieval_recall.py` re-run over the 34-paper canonical corpus

```
papers: 34   anchors: 3981   (dropped 0 non-de-numberable; capped 2015 surplus table cells at 60/paper)
retrieval deterministic across 2 runs: True
ALL anchors            n=3981   R@5=0.886  R@10=0.940  R@20=0.975
  location=table       n=1336   R@5=0.882  R@10=0.952  R@20=0.991
  location=prose       n=2645   R@5=0.888  R@10=0.933  R@20=0.967
  representation=jats_xml  n=311   R@5=0.942  R@10=0.974  R@20=0.997
loss decomposition: 10 absent from embedder candidate set / 88 ranked below 20
```

**`anchors: 3981` — identical to the previous run.** Every recall figure and the loss
decomposition reproduce unchanged.

### 3. Test 2 — `gate_sensitivity.py --pass all` mutation suite

```
numeric_perturbation   18/18 ABSTAIN     paraphrase_rule  22/23 ACCEPT
fabrication            14/14 ABSTAIN     paraphrase_llm   14/14 ACCEPT (seed 42)
support_deletion_primary  7 WRONG        support_deletion_full  14/14 ABSTAIN
CONFUSION MATRIX: TP=36  FN=1  FP=7  TN=65
precision = 0.837   recall / sensitivity = 0.973   specificity = 0.903
two-token cross-row binding: 7 probes, 4 FOOLED
```

**Confusion matrix identical** to the pre-refactor figures (precision 0.837, sensitivity
0.973, specificity 0.903). The single `paraphrase_rule` false negative (`T 3-59K
outperform → surpass`) and the 4 fooled cross-row probes are the same items.

### 4. Test suites

`tests/test_anchors.py` 9/9 · `tests/test_pipeline.py` 6/6 · experiment suite
(`tests/test_pipeline_units.py`) 42/42.

## Statement

**Neutrality was confirmed.** The centralized `src/evidence/anchors.py` reproduces the
pre-centralization behaviour exactly: identical per-chunk anchor sets across the full
corpus, identical Test-3 anchor count (3 981) and recall numbers, and an identical Test-2
confusion matrix. The two former copies had **not** diverged in the code paths this task
covers (the gate and the Test 2 / Test 3 harnesses all used `\d+\.\d+|\b\d{2,}\b`; only
Test 3 additionally applied the year / ref-id / section / arXiv exclusions, which are now
in `find_anchors` and produce the same output). Earlier anchor-count numbers stand as
reported.
