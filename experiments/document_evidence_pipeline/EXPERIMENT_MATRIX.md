# EXPERIMENT MATRIX

Assembly of the five result tables the paper draws on. Every number carries the report it
appears in **and** the run directory that produced it; anything missing either is in
§UNTRACEABLE, not in a table. Wordings follow `CLAIM_LEDGER.md` — where a claim is NARROWED
or WITHDRAWN, only the current version appears here. Corpora are never pooled.

**Freeze note.** The tag `paper-freeze-v1` points at `f3b6768`. Three commits now sit past
it: `6ae3d55` (the only one that touches `src/` — three runtime fixes: S2 `tldr`/5xx retry, a
Stage-6 `estimate_num_ctx` kwarg rename, and an embedding-model VRAM release), `acb89d8`
(harness files and `.gitignore` only; its message restates the `src/` work but the diff
contains none of it), and this commit. The whole `src/` divergence from the tag is therefore
`6ae3d55`: 3 files, +53/−3. **None of those three fixes touches any quantity in these
tables** — they affect acquisition robustness, Stage-6 synthesis, and extraction wall-clock
only. No number here was regenerated after the freeze.

---

## TABLE 1 — Representation fidelity

**Caption.** Numeric-value survival and context binding through the structured (LaTeX)
representation versus the PDF path, over 6,530 meaningful numeric values in 23 paired
arXiv papers. `L` = LaTeX path, `P` = PDF path. "before"/"after" are pre- and post- the
Phase-4a parity fix; the parity gate is what decides which representation a paper keeps.

### 1a — Pooled, all 23 paired papers (occurrence-weighted)

| split | n | vb-lax before L/P | vb-lax after L/P | vb-strict after L/P | provenance L/P | context-bindable after L/P |
|---|--:|--:|--:|--:|--:|--:|
| all | 6,530 | 0.441 / 0.986 | 0.981 / 0.986 | 0.752 / 0.699 | — / 1.000 | 0.184 / 0.168 |
| table | 5,405 | **0.388** / 0.987 | 0.983 / 0.987 | 0.708 / 0.643 | — / 1.000 | 0.110 / **0.089** |
| prose | 965 | 0.688 / 0.982 | 0.971 / 0.982 | 0.959 / 0.966 | — / 1.000 | 0.542 / 0.555 |
| caption | 160 | 0.744 / 1.000 | 0.981 / 1.000 | 0.981 / 1.000 | — / 1.000 | 0.525 / 0.531 |

Provenance is reported only for the PDF path in the source (100 % on every split); the
LaTeX-side pooled provenance column is not in either report — see §UNTRACEABLE.

### 1b — RETAINED subset (11 papers that passed the parity gate)

Reported as **macro** (mean of per-paper rates) and **gt-wt** (per-paper rates weighted by
that paper's ground-truth count). The pooled block above is diluted by the 12 papers the
gate sent back to PDF, where L and P are identical by construction.

| split | vb-strict L/P (macro) | vb-strict L/P (gt-wt) | bindable L/P (macro) | bindable L/P (gt-wt) | prov L/P (macro) |
|---|--:|--:|--:|--:|--:|
| all | 0.837 / 0.840 | **0.877 / 0.786** | 0.311 / 0.249 | **0.210 / 0.174** | 0.837 / 0.840 |
| table | 0.825 / 0.817 | **0.866 / 0.768** | **0.241 / 0.134** | **0.142 / 0.085** | 0.825 / 0.817 |
| prose | 0.896 / 0.955 | 0.964 / 0.961 | 0.528 / 0.587 | 0.597 / 0.559 | 0.896 / 0.955 |
| caption | 0.857 / 1.000 | 0.963 / 1.000 | 0.359 / 0.243 | 0.500 / 0.272 | 0.857 / 1.000 |

### 1c — FALLBACK control (12 papers the gate sent back to PDF)

| split | vb-strict L/P (macro) | bindable L/P (macro) | prov L/P (macro) |
|---|--:|--:|--:|
| all | 0.817 / 0.817 | 0.249 / 0.249 | 0.817 / 0.817 |
| table | 0.791 / 0.791 | 0.154 / 0.154 | 0.791 / 0.791 |
| prose | 0.965 / 0.965 | 0.567 / 0.567 | 0.965 / 0.965 |

- **Source reports:** `EXTRACTION_FIDELITY_REPORT.md` §STEP 3 POOLED (PDF-path column);
  `LATEX_ACQUISITION_REPORT.md` §MEASURE 1, §RETAINED only (n = 11), §FALLBACK control (n = 12).
- **Run directories:** `runs/extraction_fidelity/` (`fidelity.json`, `pooled.json`) ·
  `runs/latex_ingestion/` (`m1_per_paper.json`) · PDFs from
  `runs/prodab-20260902T004416Z/canonical/pdfs/`.
- **Corpus:** canonical 60 — the 23 arXiv PDF↔LaTeX pairs. Not pooled with data_test or medical.
- **Take-away.** The digits survive either path; the *binding* does not. On the PDF path only
  16.8 % of values keep a metric/dataset within reach, and 8.9 % of table values do. On the
  11 papers where LaTeX reaches numeric parity, table bindability roughly doubles
  (0.142 vs 0.085 gt-wt) — real, still low, and confined to the subset the gate retains.

---

## TABLE 2 — Mutation sensitivity

**Caption.** Confusion matrices for the Stage-5 evidence gate under mutation testing, with a
contract-versioned oracle. **A** is the pre-contract baseline; **B** re-scores every mutant
under the post-Phase-5 contract; **C** restricts to mutants whose correct outcome the
contract did not change — **C is the matrix the paper reports.**

### 2a — The three matrices

The suite was run twice. The **current** run adds the medical corpus; the earlier run is the
two-corpus version and is superseded (see §CROSS-CHECK item 1).

**Current — canonical 60 + data_test 8 + medical 50, 98 mutants** (`BINDING_VALIDATION_REPORT.md`)

| matrix | n_pos | n_neg | TP | FN | FP | TN | precision | sensitivity | specificity |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| A — old oracle, all | 39 | 59 | 4 | 35 | 13 | 46 | 0.235 | 0.103 | 0.780 |
| B — new oracle, all | 5 | 93 | 4 | 1 | 13 | 80 | 0.235 | 0.800 | 0.860 |
| **C — new oracle, UNCHANGED only** | **5** | 59 | 4 | 1 | 13 | 46 | 0.235 | **0.800 on 5 positives** | 0.780 |

**Superseded — canonical 60 + data_test 8 only, 81 mutants** (`GATE_SENSITIVITY_REPORT.md`)

| matrix | n_pos | n_neg | TP | FN | FP | TN | precision | sensitivity | specificity |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| A — old oracle, all | 37 | 44 | 2 | 35 | 3 | 41 | 0.40 | 0.054 | 0.932 |
| B — new oracle, all | 3 | 78 | 2 | 1 | 3 | 75 | 0.40 | 0.667 | 0.962 |
| C — new oracle, UNCHANGED only | **3** | 44 | 2 | 1 | 3 | 41 | 0.40 | 0.667 on 3 positives | 0.932 |

### 2b — Adversarial probes, pre-F1 vs post-F1 (medical JATS, Task 3)

F1 = the symmetric-metric-matching fix. Pre-F1 the harness attacked non-metric group headers,
which is why the probe count differs.

Per-class figures exist in the report for the **post-F1** run only. The pre-F1 run is
sourced at the totals level (`probe count 20 → 13`, `was 3 pre-F1`) and its per-class split
is **not in any report or surviving artifact** — those cells are left empty rather than
reconstructed. See §UNTRACEABLE.

| probe class | pre-F1 n | pre-F1 acceptances | post-F1 n | post-F1 acceptances | post-F1 caught via `wrong_cell` |
|---|--:|--:|--:|--:|--:|
| correct_cell (positive control) | — | — | 2 | — | 1 of 2 |
| correct_row_wrong_col | — | — | 1 | **0 of 1** | 1 of 1 |
| correct_col_wrong_row (cross-row) | — | — | 2 | **0 of 2** | 2 of 2 |
| correct_metric_wrong_condition | — | — | 2 | **0 of 2** | 2 of 2 |
| cross_table_substitution | — | — | 6 | **0 of 6** | 6 of 6 |
| **total** | **20** | **3** | **13** | **0** | 12 of 13 |

The three pre-F1 acceptances are individually named in the report — two on
`"Performance metrics"` and one on `"Blood component used for measurement"`, all on the
medical corpus, all routed through `not_bindable`.

### 2c — Invariant-16 suite, both domains, post-F1

| probe source | domain | probes | adversarial | route-agnostic acceptances |
|---|---|--:|--:|--:|
| Task 3 | medical JATS | 13 | 11 | **0** |
| `structural_binding_measure` | canonical LaTeX | 16 | 11 | **0** |
| `_crossrow_probe` | both | 8 | 8 | **0** |
| **total** | | **37** | **30** | **0** |

- **Source reports:** `GATE_SENSITIVITY_REPORT.md` §Contract-versioned Test 2 oracle;
  `BINDING_VALIDATION_REPORT.md` §TASK 4, §TASK 3, §F2 invariant 16.
- **Run directories:** `runs/gate_sensitivity/` (`mutants.json`, `contract_matrices.json`,
  `crossrow.json`) · `runs/binding_validation/` (`task3_probes.json`) ·
  `runs/structural_binding/` (`binding_probes.json`). Evidence inputs:
  `runs/prodab-20260902T004416Z/canonical_paper_evidence.json`,
  `runs/staging-20260902T030714Z/paper_evidence.json`.
- **Corpora:** canonical 60, data_test 8, medical 50 — each mutant carries its corpus label;
  the matrices are over the labelled union and are not presented as any per-corpus rate.
- **Take-away.** Sensitivity 0.800 rests on **5 should-accept positives**; the A→B collapse
  is the contract changing what "correct" means, not capability loss. The adversarial probes
  go 3 acceptances → 0 after F1, and 0 of 30 across both domains under the route-agnostic check.

---

## TABLE 3 — Evaluation-framework comparison

**Caption.** Sensitivity of an established automated RAG evaluation framework (RAGAS 0.2.15
`Faithfulness`, `qwen2.5:7b` judge, one fixed configuration) to the existing mutation suite,
against the structural diagnostic. Detection criterion fixed before results were inspected:
a should-reject mutant is detected iff `faithfulness < 0.5`; the `< 1.0` column is a
secondary marker, not the criterion. 106 cases, 0 unscored.

| mutation type | n | framework <0.5 | framework <1.0 | structural diagnostic | framework false-flags | disagreements |
|---|--:|--:|--:|--:|--:|--:|
| fabricated value | 15 | **15/15** | 15/15 | **15/15** | — | 0 |
| cross-row structural | 8 raw | *see control row* | 8/8 | 8/8 | — | 0 |
| numeric perturbation | 19 | **6/19** | 18/19 | **19/19** | — | 13 |
| support deletion — primary | 24 | **2/24** | 2/24 | **11/24** | — | 13 |
| support deletion — full | 1 | 0 of 1 | 1 of 1 | 1 of 1 | — | 1 of 1 |
| paraphrase — rule | 24 | — | — | — | 2/24 | 20 |
| paraphrase — LLM | 15 | — | — | — | 1/15 | 12 |
| **all** | **106** | **31/67** | **44/67** | **54/67** | **3/39** | **59** |

### Cross-row control row — mandatory qualifier

| quantity | value |
|---|---|
| raw framework detection | 8 of 8 — **must not be read as sensitivity** |
| positive controls accepted (same template, same context, row's own correct number) | **2 of 8** |
| interpretable cases after control | **n = 2**, framework detected **2 of 2** |
| structural diagnostic on the same control | **1 of 5** (canonical LaTeX), **0 of 2** (medical JATS) |

All 8 cross-row mutants scored exactly 0.0, but so did 6 of 8 correct-cell controls — the
judge is rejecting the crafted template, not the misattribution. Both methods fail this
control; neither side has a clean cross-row estimate at this n.

- **Source report:** `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` §Result, §Positive control.
- **Run directories:** `runs/eval_framework_sensitivity/` (`per_mutant.json`, `summary.json`,
  `scores.json`, `crossrow_control.json`); mutants read from `runs/gate_sensitivity/`.
- **Corpora:** canonical 60 + data_test 8 + medical 50, corpus label carried per case; no
  per-corpus rate is claimed.
- **Take-away.** The divergence is **aggregation, not blindness**: the framework registered
  18 of 19 numeric perturbations at the strict marker but only 6 of 19 crossed a
  majority-of-claims threshold, where a number-anchored check flagged 19 of 19. The cross-row
  arm is uninformative at n = 2 and supports nothing in either direction.

---

## TABLE 4 — Parity gate

**Caption.** All 12 LaTeX→PDF fallbacks re-sliced against **Criterion J**, pre-registered and
committed at **`eeab489`** before any number below was computed: a fallback is JUSTIFIED iff
`pdf_survival(all) > latex_survival(all)`, i.e. the PDF preserved ground-truth numeric-anchor
occurrences the LaTeX representation lost.

| paper | latex_survival (all) | pdf_survival (all) | aggregate deficit | occurrences lost | splits fired | verdict |
|---|--:|--:|--:|--:|---|---|
| 141276ba659d | 0.712 | 0.990 | 0.278 | 53 | all, prose | JUSTIFIED |
| 2009dbb5f290 | 0.593 | 0.951 | 0.358 | 58 | all, prose | JUSTIFIED |
| 413a184de4b1 | 0.928 | 0.943 | 0.015 | 27 | all, prose, caption | JUSTIFIED |
| 4f3fca4c4fa8 | 0.565 | 0.939 | 0.374 | 49 | all, table, prose | JUSTIFIED |
| 6437463b4b13 | 0.834 | 0.852 | 0.018 | 4 | all, prose | JUSTIFIED |
| 68f93a5921c1 | 0.548 | 0.935 | 0.387 | 12 | all, table, prose | JUSTIFIED |
| 81e060664f24 | 0.606 | 0.775 | 0.169 | 12 | all, table, prose | JUSTIFIED |
| 96285d75a525 | 0.983 | 0.985 | 0.003 | 1 | all, prose | JUSTIFIED |
| be7c4dc39030 | 0.960 | 1.000 | 0.040 | 6 | all, prose | JUSTIFIED |
| d3b5f3c050b4 | 0.682 | 0.841 | 0.159 | 10 | all, prose | JUSTIFIED |
| f3b06a914702 | 0.998 | 1.000 | 0.002 | 3 | all, prose | JUSTIFIED |
| fef0393e997e | 0.839 | 0.894 | 0.056 | 18 | all, table, prose | JUSTIFIED |
| **precision** | | | | | | **12/12 justified, 0 over-triggered = 1.00** |

### Conservatism block

| quantity | value |
|---|---|
| fired on an aggregate deficit **< 2 %** | 4 of 12 — `413a184de4b1`, `6437463b4b13`, `96285d75a525`, `f3b06a914702` |
| fired on an aggregate deficit **< 5 %** | 5 of 12 |
| lost **≥ 20 %** of occurrences | 4 of 12 |
| occurrences lost on `all` | min 1 · median 12 · max 58 |
| **LaTeX table survival ≥ PDF table survival** | **8 of 12** (exactly equal at 1.000/1.000 in 4) |
| splits that fired | prose **12 of 12** · table **4 of 12** · caption **1 of 12** |
| sharpest case — `f3b06a914702` | preserved **1522 of 1522** table anchors verbatim, lost **3 prose occurrences of 71** (0.2 % aggregate) — representation **discarded entirely** |

- **Source report:** `PARITY_GATE_PRECISION_REPORT.md` §DEFINITION, §Result, §Reading.
- **Run directories:** `runs/parity_gate_precision/` (`per_fallback.json`, `summary.json`);
  frozen input measurements from `runs/latex_ingestion/processed/chunks.json`
  (`latex_parity_fallback` records) and `runs/latex_ingestion/reps.json`.
- **Corpus:** canonical 60 — the 12 arXiv fallbacks.
- **Take-away.** The gate never fired without real, countable lost evidence (precision 1.00 on
  n = 12) — and it is conservative as well as safe: a third of fallbacks discarded a
  representation over a sub-2 % deficit, and two-thirds discarded one whose tables were
  intact. Precision says *why* it fired, not that discarding the whole paper was proportionate.

---

## TABLE 5 — Cross-domain and selection

### 5a — Cross-domain: canonical LaTeX vs medical JATS (post-F1, side by side, not pooled)

| quantity | canonical (LaTeX structure) | medical (JATS structure) |
|---|--:|--:|
| structured papers | 13 (11 tex + 2 jats) | 11 jats |
| structured cells | see §UNTRACEABLE | **1,371** |
| RETURNED quant — structured | 5 | 2 |
| RETURNED quant — PDF-only | 3 | 1 |
| of RETURNED: `bound` | **0 of 5** | **0 of 2** |
| of RETURNED: `not_bindable` | 4 of 5 | 1 of 2 |
| of RETURNED: `not_a_table_claim` | 1 of 5 | 0 of 2 |
| of RETURNED: n/a (non-numeric / PDF-only rep) | 3 | 3 |
| **bound rate** | **0 of 5** | **0 of 2** |
| probe protection — `wrong_cell` fired | **2 of 6** cross-row | **12 of 13** probes |
| `correct_cell` positive control returned | **1 of 9** | **0 of 2** |
| adversarial acceptances | **0** | **0** (was 3 pre-F1) |
| 16 safety invariants | 16/16 | 16/16 |

**Medical full case distribution** over all numeric metrics/results items (canonical did not
persist the abstained side — see §UNTRACEABLE): `pdf_only` 11 · `not_bindable` 4 · `bound` 0 ·
`wrong_cell` 1 · `not_a_table_claim` 0 · n/a 10.

### 5b — Selection control: three medical arms, 19 papers, seeded, clean cache

Arm 2 holds selection at legacy while pinning the Stage-4 domain prompt variant to the
routing content-aware would have produced — it isolates the selector from the routing flip.

| quantity | 1 legacy / natural | 2 legacy / **pinned** (control) | 3 content_aware@10 / natural |
|---|--:|--:|--:|
| mean non-empty fields / paper | 8.32 | 8.47 | 8.84 |
| `metrics` | 9/19 (47 %) | 11/19 (58 %) | **14/19 (74 %)** |
| `results` | 7/19 (37 %) | 8/19 (42 %) | **13/19 (68 %)** |
| routing (biomed / cs_ml) | 3 / 16 | 8 / 11 | 8 / 11 |
| conformance | 19 conformant | 19 conformant | 18 conformant / 1 salvaged |
| circuit-breaker fallbacks | 0 | 0 | 0 |
| `_extraction_failed` | 0 | 0 | 0 |

**Decomposition (percentage points).** Only the isolated column may be quoted as a selection
result; the confounded column is diagnostic history (`CLAIM_LEDGER.md` row 14s, WITHDRAWN).

| field | confounded (3−1) — WITHDRAWN | routing (2−1) | **selector isolated (3−2)** |
|---|--:|--:|--:|
| `metrics` | +26 pp | +11 pp | **+16 pp (11/19 → 14/19)** |
| `results` | +32 pp | +5 pp | **+26 pp (8/19 → 13/19)** |

- **Source reports:** `BINDING_VALIDATION_REPORT.md` §TASK 2, §TASK 5;
  `MEDICAL_SELECTOR_CONTROL_REPORT.md` §Result, §Decomposition.
- **Run directories:** `runs/binding_validation/` (`task1_verify.json`, `task2_binding.json`,
  `task3_probes.json`, `task5_cross_domain.json`, `invariants.json`) ·
  `runs/medical_reacquire/` (acquisition) · `runs/structural_binding/` (canonical side) ·
  `runs/medical_selector_control/` (`arm_1_legacy_natural.json`, `arm_2_legacy_pinned.json`,
  `arm_3_ca_natural.json`, `summary.json`), reading
  `runs/medical_rechunk/processed/chunks.json` + `runs/medical_rechunk/chroma_db`.
- **Corpora:** canonical 60 and medical 50, separate columns throughout; never averaged.
- **Take-away.** The cell-binding path is inert on real extracted claims in **both** domains
  (0 of 5, 0 of 2) — it engages only against synthetic probes, and more reliably on JATS
  (12 of 13) than on LaTeX (2 of 6). The selection gain survives its control but shrinks:
  +16 pp / +26 pp isolated, with a further +11 pp / +5 pp attributable to the prompt-variant flip.

---

## CROSS-CHECK

Every number above was read back against its source report. Findings:

1. **Matrix C appears twice with different values — both correct, one current.**
   `GATE_SENSITIVITY_REPORT.md` reports C as sensitivity **0.667 on 3 positives**
   (specificity 0.932, 47 mutants, canonical 60 + data_test 8).
   `BINDING_VALIDATION_REPORT.md` reports C as sensitivity **0.800 on 5 positives**
   (specificity 0.780, 59 negatives) after adding the medical corpus.
   **Current = 0.800 on 5 positives**, matching `CLAIM_LEDGER.md` ("Matrix C positives /
   sensitivity — 5 / 0.800"). The 0.667 figure is the earlier two-corpus run, not an error.
   Both are shown in Table 2a so the difference cannot be mistaken for drift.

2. **Medical confounded figure — the known ~1 pp reproducibility drift.**
   `MEDICAL_RECHUNK_REPORT.md` §3.3c reports `metrics` 47 → 74 % and `results` 37 → 68 %,
   i.e. **+27 pp / +31 pp**. `MEDICAL_SELECTOR_CONTROL_REPORT.md`, re-running the same three
   arms fresh, reports **+26 pp / +32 pp**. The endpoints are identical (9/19→14/19,
   7/19→13/19); the difference is rounding of the same counts, not a different measurement.
   **Neither may be quoted as a selection result** — `CLAIM_LEDGER.md` row 14s marks both
   WITHDRAWN. The current selection figures are the isolated +16 pp / +26 pp.

3. **Table 1 pooled figures agree across the two reports.** `EXTRACTION_FIDELITY_REPORT.md`
   gives the PDF path as 98.6 % vb-lax / 69.9 % vb-strict / 100 % provenance / 16.8 %
   bindable (all), 8.9 % bindable (table). `LATEX_ACQUISITION_REPORT.md` gives the same
   values as its `P` column (0.986 / 0.699 / 0.168 / 0.089). No discrepancy. Readers should
   note the two reports label the *same* PDF column differently — EF as a standalone rate,
   LATEX as the denominator of an L/P pair.

4. **RETAINED provenance is byte-identical to RETAINED vb-strict on every split**
   (0.837/0.840 all, 0.825/0.817 table, 0.896/0.955 prose, 0.857/1.000 caption). That is
   almost certainly because the harness computes provenance conditioned on strict survival,
   not independently. Reported as-is; flagged because a reader would otherwise read it as
   two agreeing measurements when it is likely one.

5. **Rounding.** Table 4 aggregate deficits are quoted to 3 dp as the report gives them;
   `96285d75a525` (0.003) and `f3b06a914702` (0.002) round to 0.0 % at one decimal and are
   shown at three so the sub-2 % conservatism claim stays legible.

6. No other discrepancy found between matrix and source.

---

## UNTRACEABLE

Numbers that appear in a report or a run but cannot be tied to **both**. Listed, not dropped,
and not used in any table.

| quantity | where it appears | why untraceable |
|---|---|---|
| Canonical total structured-cell count (**1,986** across 13 papers) | terminal output of `structural_binding_measure.py`; run `runs/structural_binding/` | **Not in any report.** `BINDING_VALIDATION_REPORT.md` Table 5 prints the canonical structured-cells cell as `—`. Table 5a therefore leaves it blank rather than importing a number from a console log. |
| RETAINED-subset pooled `vb-lax` (**≈ 0.98 L / ≈ 0.99 P**) | `LATEX_ACQUISITION_REPORT.md` §RETAINED re-slice preamble | The report states plainly it "cannot be rebuilt from this artifact without re-running". Approximate by the author's own admission — excluded from Table 1b, which carries only macro/gt-wt. |
| Canonical ABSTAINED-side `structural_bind` case distribution | implied by `BINDING_VALIDATION_REPORT.md` §TASK 5 | The canonical run persisted statuses for RETURNED items only. Table 5a gives the medical full distribution and says so; no canonical counterpart exists. |
| Pre-F1 medical probe **per-class** counts | `BINDING_VALIDATION_REPORT.md` gives only the totals (20 probes, 3 acceptances) and the post-F1 per-class table | `runs/binding_validation/task3_probes.json` was overwritten by the post-F1 re-run, so no artifact holds the pre-F1 split. Table 2b leaves those cells empty; only the sourced totals (20 / 3) appear. |
| `estimate_num_ctx` / Stage-6 synthesis behaviour after `6ae3d55` | no report | Fixed after the freeze; no run directory exists for a post-fix synthesis measurement. Deliberately absent from every table. |

---

## FIGURE CANDIDATES

Four tables would read better as figures. Not created here.

1. **Table 1a/1b — grouped bar, "survival vs binding".** Four split groups (all / table /
   prose / caption) × two bars each (verbatim-strict, context-bindable), PDF path in one
   colour and LaTeX in another, with the RETAINED subset as a second panel. Shows the whole
   thesis in one image: the survival bars are near-ceiling and near-equal while the binding
   bars collapse, worst in tables.

2. **Table 2a — three stacked confusion matrices, A → B → C.** Small 2×2 heat blocks side by
   side with n_positives printed under each. Makes visible that the A→B sensitivity jump is
   the positive set shrinking from 39 to 5, not the gate improving.

3. **Table 3 — paired dot plot, framework vs structural diagnostic.** One row per mutation
   type, two dots (framework detection rate, structural detection rate) joined by a line, with
   a third open marker for the framework's strict `<1.0` rate. The numeric-perturbation row
   shows the open marker at 18/19 and the filled one at 6/19 — the aggregation effect made
   visual — and the cross-row row is drawn greyed with "n = 2 after control".

4. **Table 4 — sorted deficit plot with a proportionality overlay.** The 12 fallbacks ordered
   by aggregate deficit on a log x-axis, each marked for whether LaTeX table survival ≥ PDF's.
   `f3b06a914702` sits at 0.2 % with the "tables intact" marker, making the conservatism
   argument without prose.
