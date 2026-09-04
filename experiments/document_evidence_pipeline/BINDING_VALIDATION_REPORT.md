# Binding-contract validation on the expanded structured set

Branch `claude-code-verification` · 2026-09-04
Six stages unchanged. `configs/` not modified. `latex_ingestion_enabled` stays
`false`. Seeded path (temperature 0, seed 42), clean cache. Medical results are
**not** pooled with canonical or data_test.

**This report has two passes.** The first (diagnostic) run surfaced a confound in
`structural_bind`'s metric matching. It was fixed (**F1**, commit for this
report), regression-tested, and Tasks 2/3/4 were re-run on both domains. **Only
the post-F1 numbers are eligible for the paper**; the pre-F1 numbers are recorded
as diagnostic history and clearly marked.

Harnesses (isolated to `runs/binding_validation/`): `binding_validation_measure.py`
(Tasks 1–3, 5), `gate_sensitivity.py --medical` (Task 4),
`binding_validation_invariants.py` (15 invariants).

---

## F1 — symmetric metric matching (the fix)

### Defect

`structural_bind` decided "is the claimed metric a column in this paper?" with
**two different rules on the two sides**:

| side | rule (pre-F1) | consequence |
|---|---|---|
| claim | `_sig_tokens(value) & _METRIC_TOKENS` — words of **length ≥ 4** only | `f1`, `auc`, `iou`, `map`, `mrr` in a claim were invisible → a claim naming a genuinely tabulated column came back `not_bindable` |
| column | `_col_matches_metric`: whole-token **OR ≥2-char free substring** | `"Performance metrics"` matched `"em"` (from *exact match*) inside `performanc`**`em`**`etrics`; a non-metric column looked bindable from one direction |

This single asymmetry confounded **both** of Phase 5's headline results:
`bound = 0` in both domains, and the 3 pre-F1 adversarial acceptances (Task 3).
The probe harness used the loose `_col_matches_metric(header, _METRIC_TOKENS)` to
*pick* which column to attack, so on biomedical JATS it selected non-metric group
headers (`"Performance metrics"`, `"Blood component used for measurement"`) and
crafted claims naming them — claims that then evaded binding via the claim-side
`not_bindable` path.

### Fix

One rule, `_metric_tokens(text)`, applied identically to a claim string and to a
column header:

- split on any non-alphanumeric boundary (`"F1-score (%)"` → `{f1, score}`,
  `"Accuracy (%)"` → `{accuracy}`),
- intersect **whole tokens** with `_METRIC_TOKENS` (no length filter, no
  substring),
- add any bounded-range metric **name** matched by `_METRIC_NAME_RE`
  (`"exact match"`, `"dice coefficient"`, `"r2"`).

`_col_matches_metric(h, toks)` is now exactly `_metric_tokens(h) & toks`.
`structural_bind` builds `metric_toks = _metric_tokens(value)`. Symmetric by
construction: `_col_matches_metric(h, _metric_tokens(c)) == bool(_metric_tokens(h)
& _metric_tokens(c))` for every `(h, c)`.

Not broadened beyond symmetry: `"performance metrics"` / `"blood component used
for measurement"` contain no recognised metric word and resolve to `∅` on **both**
sides. `_col_matches_metric("Performance metrics", _METRIC_TOKENS)` is now `False`
(was `True`).

### Regression tests — `tests/test_pipeline_units.py` (46 → 61)

15 new checks pin the exact asymmetry so a future refactor cannot silently
reintroduce it:

| group | checks |
|---|---|
| **1 — valid pair that previously failed** | `_metric_tokens` sees `f1`/`auc`; claim `"F1 of 0.88"` at an own `F1` cell → `bound` (was `not_bindable`); `"F1 of 0.71"` at another row → `wrong_cell` (was `not_bindable`) |
| **2 — genuine non-match still doesn't match** | `_metric_tokens("Performance metrics") == ∅`; `…("Blood component used for measurement") == ∅`; `_col_matches_metric(…, full vocab)` is `False` for both (was `True` via `"em"`) |
| **3 — same normalisation both sides** | `"F1-score" ∩ "F1"` → `{f1}`; `_col_matches_metric` reduces its header arg too (`"F1-score",{f1}`→True; `"F1-score",{em}`→False); `_metric_tokens` never introduces `"em"` from `"exact match"` as a substring; `_col_matches_metric(h, toks(c)) == (toks(h) & toks(c))` over 5 `(h,c)` pairs |
| **4 — the 3 previously-accepted adversarial cases, re-evaluated** | `"Performance metrics of 80.52"` / `"… of 87.82"` → `not_bindable` (names no metric — now a symmetric residual, not a confound); the **same cross-row attack via the real column `"Accuracy"`** → `wrong_cell` (caught); `"Blood component used for measurement of 12"` → `not_bindable` |

`tests/test_pipeline.py` + `tests/test_anchors.py` 15/15 unchanged.

---

## Headline (post-F1)

| | canonical (LaTeX structure) | medical (JATS structure) |
|---|--:|--:|
| structured papers | 13 (11 tex + 2 jats) | **11 jats** |
| structured cells | — | **1371** |
| claims that reached `bound` (real Stage-4 extraction) | **0** | **0** |
| adversarial probe acceptances (Task 3) | **0** | **0** *(was 3 pre-F1)* |
| Matrix C positives / sensitivity (Task 4) | — | **5 / 0.800** |
| 15 safety invariants | 15/15 | 15/15 |

**Outcome A + Outcome C, per the pre-registered options:**

- **A — `bound` stays 0 in both domains after removing the confound.** This is
  the *stronger* result: real LLM-extracted claims still do not resolve to
  structured table cells, and that is now a clean finding, not an artifact of a
  length-4 token filter. The `bound` (case 3) path has never fired in
  production-realistic measurement in either domain. **Not chased** — no attempt
  made to make binding fire.
- **C — adversarial acceptance count corrected 3 → 0.** The 3 pre-F1 acceptances
  were an implementation artifact: the asymmetric matcher let the probe harness
  craft claims naming non-metric group headers, which then evaded binding via
  case-2 `not_bindable`. Post-F1 the harness selects real metric columns
  (`"Accuracy (%)"`, `"True positive rate (%)"`), and every cross-row /
  cross-condition / cross-table number substitution is caught as `wrong_cell`.
  The old number is not preserved for narrative continuity.

---

## TASK 1 — 11 JATS medical papers through Stage 2 : structured-cell verify

*(Unchanged by F1 — Stage 2 only.)* Re-chunked the re-acquired medical corpus
(`runs/medical_reacquire/`) with the grounded provenance-aware chunker.
`table_cells` + `table_caption` flow onto every chunk of a table block.

| paper | chunks | cells | tables | structured | fallback | title |
|---|--:|--:|--:|--:|--:|---|
| 3aeeb4d31b0d | 100 | 54 | 2 | 2 | 0 | Trajectories of human brain functional connectome maturation |
| 33fea4124ef0 | 138 | 119 | 7 | 6 | 1 | Exploring fetal brain tumor glioblastoma symptom verification |
| 913b6b3cb4c4 | 48 | 0 | 0 | 0 | 0 | Biallelic variants in the UTRN gene… |
| 819f9eacf36c | 77 | 400 | 5 | 5 | 0 | Second-Trimester Placental and Thyroid Hormones… |
| 7cc53dfe80d5 | 47 | 170 | 1 | 1 | 0 | Large vestibular schwannomas in late pregnancy |
| 506958c71c4b | 52 | 218 | 4 | 4 | 0 | Exposure to Perfluoroalkyl Substances During Pregnancy |
| dd7cacac10d3 | 14 | 0 | 0 | 0 | 0 | Congenital Dislocation of the Knee |
| ec45017959a4 | 95 | 98 | 1 | 1 | 0 | Joint profiling of cell morphology and gene expression |
| 20f7c8717108 | 61 | 0 | 0 | 0 | 0 | Paradoxical Effects of a Cytokine and an Anticonvulsant |
| eef59dba1650 | 77 | 312 | 3 | 3 | 0 | Mixtures of Metals and Micronutrients in Early Pregnancy |
| 4e8aa13b4455 | 53 | 0 | 0 | 0 | 0 | Interaction of the pre- and postnatal environment |

- `block_type` (all JATS chunks): `abstract 22 · paragraph 647 · figure_caption 48 · table 45`
- papers with ≥1 table block: **7/11** (4 case-report / genetics papers carry no data tables)
- tables parsed to structured cells: **22/23** · fallen back to PDF: **1/23**
- total structured cells across the 11: **1371**

**Stop condition (near-zero cells): NOT triggered.**

---

## TASK 2 — binding measurement, medical corpus, gate ACTIVE  (post-F1)

Stage 3 (bge-m3/cuda, isolated Chroma) + Stage 4 (`qwen2.5:7b`, seed 42, temp 0,
reservation 768, clean cache) on all 23 full-text medical papers, then the **real**
`gate_paper` per paper.

### RETURNED numeric metrics/results

| subset | RETURNED (numeric) |
|---|--:|
| structured (11 JATS) | **2** |
| PDF-only (12 PDF) | **1** |
| total | **3** |

### `structural_bind` case distribution — all numeric metrics/results items

| status | count | (pre-F1) |
|---|--:|--:|
| `pdf_only` | 11 | 11 |
| `not_bindable` | 4 | 4 |
| `bound` | **0** | **0** |
| `wrong_cell` | 1 | 1 |
| `not_a_table_claim` | 0 | 0 |
| (n/a — non-numeric / not reached) | 10 | 10 |

**Identical to pre-F1.** On the real Stage-4 extraction output, the medical
claims that carry a number either sit on PDF-only papers (`pdf_only`), name no
recognised metric (`not_bindable`), or — one case — land at the wrong cell
(`wrong_cell`, correctly rejected). **Zero reach `bound`.** The canonical LaTeX
real-extraction `bound` count is also **0** (its "5" is the RETURNED-on-
structured-papers count, all `not_bindable` / `not_a_table_claim` fall-throughs).
**The case-3 bind path is inert in production-realistic measurement in both
domains — and this now holds under symmetric matching.**

---

## TASK 3 — adversarial probes on the 11 JATS papers  (post-F1)

13 probes constructed from the actual JATS table cells (post-F1 the harness
identifies metric columns with the symmetric matcher, so it no longer picks
non-metric group headers; probe count 20 → 13).

| class | want | n | RETURNED | ABSTAINED | via `wrong_cell` |
|---|---|--:|--:|--:|--:|
| correct_cell (positive control) | RETURNED | 2 | 0 | 2 | 1 |
| correct_row_wrong_col | ABSTAINED | 1 | 0 | 1 | 1 |
| correct_col_wrong_row (cross-row) | ABSTAINED | 2 | 0 | 2 | 2 |
| correct_metric_wrong_condition | ABSTAINED | 2 | 0 | 2 | 2 |
| cross_table_substitution | ABSTAINED | 6 | 0 | 6 | 6 |

**Adversarial acceptances (FOOLED): 0** (was 3). **Cross-row acceptances: 0**
(was 1). Every adversarial number substitution now binds to a real metric column
and is caught as `wrong_cell`.

The 2 `correct_cell` positive controls ABSTAINED (grounding/attribution
conservatism, as on canonical where it is 1/9) — the row labels the JATS parser
gives that table are noisy (`"10"`, `"1"`), so the crafted "correct" claim's
subject doesn't `_row_matches_subject` the intended row; one lands `wrong_cell`,
one `None`. This is the same Phase-5 conservatism already documented, not a new
regression.

### The 3 pre-F1 acceptances, re-evaluated

| pre-F1 crafted claim | pre-F1 | post-F1 |
|---|---|---|
| "CNN reports a **Performance metrics** of 80.52…" | RETURNED (not_bindable → grounded) | **not constructed** — `"Performance metrics"` is no longer accepted as a metric column; the equivalent attack via the real column `"Accuracy (%)"` → `wrong_cell` → ABSTAINED |
| "CNN reports a **Performance metrics** of 87.82…" | RETURNED | same as above |
| "Arsenic reports a **Blood component used for measurement** of 12…" | RETURNED | **not constructed** — header carries no metric word; no real-metric counterpart exists in that table, so no probe |

Pinned permanently by regression-test group 4 (`adv 4a–4d`).

### Residual (structural, symmetric — not an artifact)

A claim whose metric phrase contains **no recognised metric word at all** still
routes to case-2 `not_bindable` and is checked only by grounding + attribution +
the 5a range check. Post-F1 this is symmetric — both sides agree the phrase names
no metric — so it is a true limit of structured binding, not a confound. Closing
it would require a domain metric vocabulary (tuning) or making case 2 reject
(which would withhold every legitimate biomedical prose aggregate); neither is in
scope. Logged in `structural_bind`'s docstring.

---

## TASK 4 — Test 2 mutation suite incl. medical JATS papers (v2 oracle)  (post-F1)

`gate_sensitivity.py --pass all --medical`. Base RETURNED quant items across the
three corpora: **38** (canonical60 22 · data_test 4 · medical_jats 12). Medical
mutants: 17.

| matrix | pos | neg | TP | FN | FP | TN | precision | sensitivity | specificity |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **A** old oracle, ALL mutants (pre-5 baseline) | 39 | 59 | 4 | 35 | 13 | 46 | 0.235 | **0.103** | 0.780 |
| **B** new (v2) oracle, ALL mutants | 5 | 93 | 4 | 1 | 13 | 80 | 0.235 | **0.800** | 0.860 |
| **C** new oracle, UNCHANGED mutants only ← reported sensitivity | **5** | 59 | 4 | 1 | 13 | 46 | 0.235 | **0.800** | 0.780 |

**Identical to pre-F1.** The F1 fix does not move the Test-2 numbers, and this is
expected: Matrix-C positives are should-ACCEPT *paraphrase* mutants on prose
result sentences, not cell-bound claims, and the FP=13 are `support_deletion`
leaks unrelated to binding.

- **Matrix C positive set: n = 5** (was 3 before the medical corpus was added).
  The medical JATS corpus adds **exactly 2**, both true positives:
  `ec45017959` `paraphrase_rule` + `paraphrase_llm` of *"Cells were classified…
  with 60% of cells matching fetal brain cell types."* → both RETURNED (correct).
- **n = 5 is small. Denominator, explicitly:** the gate returns only **2 numeric
  quant items on all 11 biomedical JATS papers**; Matrix-C positives are
  generated only from `results`-sentence items; the medical corpus produced
  exactly **one** such sentence → 2 positives. The canonical contribution (3) is
  capped by `cf099b7cd7` being the only canonical paper whose structured
  result-sentence paraphrases survive the v2 contract (the rest are PDF-only →
  CONTRACT_CHANGED). **Reported binding sensitivity = 4/5 = 0.80 on n = 5
  should-ACCEPT cases — directional, not a rate.**
- **CONTRACT_CHANGED: 34 mutants**, all `paraphrase_rule` / `paraphrase_llm`,
  every one for the same reason — *numeric OWN claim on a PDF-only paper →
  post-5 `unverifiable_binding`*. Full list in
  `runs/gate_sensitivity/contract_matrices.json`. No medical mutant is
  CONTRACT_CHANGED (the 11 JATS papers have `table_cells`, so `_paper_is_pdf_only`
  is false).
- `_crossrow_probe` (harness's own canonical-style two-token cross-row probe):
  **8 probes, FOOLED 0** — unchanged.
- Pre-existing weakness, not touched: `support_deletion_primary` WRONG = 13
  (several medical) — removing the single primary support chunk still grounds
  when the value recurs in another chunk.

---

## TASK 5 — cross-domain comparison (side by side, NOT pooled)  (post-F1)

Binding status of **RETURNED** numeric quant items (apples-to-apples; the
canonical run stores statuses for RETURNED items only):

| | canonical (LaTeX) | medical (JATS) |
|---|--:|--:|
| structured papers | 13 (11 tex + 2 jats) | 11 jats |
| RETURNED quant — structured | 5 | 2 |
| RETURNED quant — PDF-only | 3 | 1 |
| of RETURNED: `bound` | **0** | **0** |
| of RETURNED: `not_bindable` | 4 | 1 |
| of RETURNED: `not_a_table_claim` | 1 | 0 |
| of RETURNED: (n/a — non-numeric / PDF-only rep) | 3 | 3 |
| `bound` rate | 0 / 5 | 0 / 2 |
| adversarial probe acceptances (Task 3) | **0** | **0** *(was 3)* |
| `wrong_cell` fired on all probes | 2 / 6 cross-row | **12 / 13** |
| `correct_cell` positive-control returned | 1 / 9 | 0 / 2 |
| 15 safety invariants | 15/15 | 15/15 |

(Medical's full case distribution over *all* numeric items is in Task 2:
`pdf_only 11 · not_bindable 4 · bound 0 · wrong_cell 1`. The canonical run did not
persist the ABSTAINED-side distribution.)

**Does the contract behave the same across the two domains and structured
sources? Post-F1, more so than the diagnostic run suggested — but still not
identically:**

1. **`bound` (case 3) is inert in both** on real extraction (0/5, 0/2). The
   cell-level bind never engages against LLM-extracted claim text in either
   domain; what engages against *synthetic* probes is `wrong_cell` (case 4/5b).
2. **`wrong_cell` protection is now comparable or stronger on JATS**
   (12/13 probes vs 2/6 cross-row on canonical) — cleaner cells, and post-F1 the
   probes name real metric columns.
3. **The case-2 `not_bindable` residual is the same size in both** (4 items). It
   is now symmetric, so a claim reaches it only when it genuinely names no
   recognised metric — common on biomedical prose ("60% of cells matching…"),
   rarer on CS/NLP.
4. **`pdf_only` dominates the medical distribution (11)** because 12 of 23
   medical full-text papers are PDF and 4 of the 11 JATS papers carry no data
   tables. The structured surface on this corpus is genuinely thin — 7 papers,
   1371 cells.

---

## Tests, suite, invariants  (post-F1)

| check | result |
|---|---|
| `tests/test_pipeline.py` + `tests/test_anchors.py` | **15 / 15** |
| experiment suite `tests/test_pipeline_units.py` | **61 / 61** (46 + 15 F1 regression checks) |
| 15 safety invariants — medical binding_validation (`binding_validation_invariants.py`) | **15 / 15 PASS** |
| 15 safety invariants — latest data_test staging run (`staging-20260904T021129Z`) | 15 / 15 PASS |

Invariants 14 (`cross_row_binding_acceptances_zero`) and 15
(`no_own_quantitative_from_unverifiable_binding`) PASS on real Stage-4 output in
both passes — there are 0 fabricated claims in real extraction (the gate returns
3 numeric items corpus-wide). Post-F1 they also hold against the Task-3 synthetic
probes, which pre-F1 they did not police (the 3 acceptances routed through
`not_bindable`, a by-design fall-through outside both invariants' failure sets).

---

## Files

- `src/evidence/gate.py` — **F1**: `_metric_tokens()` added; `_col_matches_metric`
  made symmetric; `structural_bind` uses `_metric_tokens(value)`. No other gate,
  selector, or acquisition change.
- `experiments/document_evidence_pipeline/tests/test_pipeline_units.py` — 15 F1
  regression checks (`sym 1a`–`sym 3d`, `adv 4a`–`adv 4d`).
- `binding_validation_measure.py` — Tasks 1, 2, 3, 5
- `gate_sensitivity.py` — `--medical` flag (harness only)
- `binding_validation_invariants.py` — 15 invariants on the medical output
- `runs/binding_validation/` — `processed/{chunks,extraction_cache,paper_evidence}.json`,
  `task{1,2,3,5}_*.json`, `invariants.json`, `run.log`, `task4_gate_sensitivity.log`
- `runs/gate_sensitivity/` — `mutants.json`, `contract_matrices.json`

## Not in this commit

- `_METRIC_TOKENS` was **not** broadened to a biomedical vocabulary — the F1 fix
  only removes the asymmetry, it does not add metric names. The case-2
  `not_bindable` residual (a claim naming no recognised metric word) is a
  symmetric structural limit, reported not patched.
- `configs/` unchanged; `latex_ingestion_enabled` stays `false`.
- The medical corpus stays in `runs/binding_validation/`; `data/` untouched.
