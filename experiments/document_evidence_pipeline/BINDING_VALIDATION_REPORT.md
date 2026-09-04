# Binding-contract validation on the expanded structured set

Branch `claude-code-verification` · 2026-09-04
Six stages unchanged. No edits to `src/evidence/gate.py`, the selector, or acquisition.
`configs/` not modified. `latex_ingestion_enabled` stays `false`. Seeded path
(temperature 0, seed 42), clean extraction cache. Medical results are **not**
pooled with canonical or data_test.

Harnesses (all new, isolated to `runs/binding_validation/`):
`binding_validation_measure.py` (Tasks 1–3, 5), `gate_sensitivity.py --medical`
(Task 4), `binding_validation_invariants.py` (15 invariants).

---

## Headline

| | canonical (LaTeX structure) | medical (JATS structure) |
|---|--:|--:|
| structured papers | 13 (11 tex + 2 jats) | **11 jats** |
| structured cells | — | **1371** |
| claims that reached `bound` (real Stage-4 extraction) | **0** | **0** |
| adversarial probe acceptances | **0** | **3  ← STOP CONDITION** |
| Matrix C positives (binding sensitivity denominator) | 3 | **5** |
| 15 safety invariants | 15/15 | **15/15** |

Two findings, both reported without changing the rule (as instructed):

1. **The `bound` path (case 3) has never fired in production-realistic
   measurement — on *either* domain.** Every RETURNED structured quant claim,
   canonical and medical, reaches RETURNED through a *fall-through* case
   (`not_bindable` / `not_a_table_claim`), not through a cell bind. The contract's
   adversarial protection on canonical came from grounding conservatism, not from
   binding.
2. **That grounding conservatism does not hold on compact biomedical JATS table
   chunks.** Task 3 produced **3 adversarial acceptances** (STOP CONDITION),
   all via the documented case-2 `not_bindable` residual gap, all on tables whose
   entire body (caption + headers + every row) sits in one ~300-char chunk.

---

## TASK 1 — 11 JATS medical papers through Stage 2 : structured-cell verify

Re-chunked the re-acquired medical corpus (`runs/medical_reacquire/`) with the
grounded provenance-aware chunker into `runs/binding_validation/processed/chunks.json`.
`table_cells` + `table_caption` flow onto every chunk of a table block, same as
the canonical JATS path.

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

- `block_type` distribution (all JATS chunks): `abstract 22 · paragraph 647 · figure_caption 48 · table 45`
- papers with ≥1 table block: **7/11** (4 case-report / genetics papers carry no data tables — expected for biomedical)
- tables parsed to structured cells: **22/23**
- tables fallen back to PDF: **1/23**
- total structured cells across the 11: **1371**

**Stop condition (near-zero cells): NOT triggered.** JATS parsing produces usable
cells on this corpus.

---

## TASK 2 — binding measurement, medical corpus, gate ACTIVE

Stage 3 (bge-m3/cuda, isolated Chroma) + Stage 4 (`qwen2.5:7b`, seed 42, temp 0,
reservation 768, clean cache) on all 23 full-text medical papers, then the **real**
`gate_paper` per paper.

### RETURNED numeric metrics/results

| subset | RETURNED (numeric) |
|---|--:|
| structured (11 JATS) | **2** |
| PDF-only (12 PDF) | **1** |
| total | **3** |

The two structured RETURNED items (paper `ec45017959`):
`results` — *"Cells were classified into various neural cell types using scRNA-seq,
with 60% of cells matching fetal brain cell types."* (bind `not_bindable` → fall-through);
`metrics` — *"expression of DLX genes and ribosomal subunits RPL39, RPL19"*
(no number in the binding sense).

### `structural_bind` case distribution — all numeric metrics/results items

| status | count |
|---|--:|
| `pdf_only` | 11 |
| `not_bindable` | 4 |
| `bound` | **0** |
| `wrong_cell` | 1 |
| `not_a_table_claim` | 0 |
| (n/a — non-numeric / not reached) | 10 |

**Claims that reached `bound`: 0.** For comparison, on the canonical LaTeX corpus
the real-extraction `bound` count is **also 0** — the "5" figure sometimes quoted
is the RETURNED-on-structured-papers count there, and all 5 are
`not_bindable` (4) / `not_a_table_claim` (1) fall-throughs. **The `bound` (case 3)
path is inert in production-realistic measurement in both domains**, because an
LLM-extracted claim almost never names a metric whose spelling matches a tabulated
column header exactly enough for `metric_toks` (whole-word `_METRIC_TOKENS` hit) to
be non-empty.

---

## TASK 3 — adversarial probes on the 11 JATS papers  ·  STOP CONDITION

20 probes constructed from the actual JATS table cells (subject row × metric column,
then the number swapped per class).

| class | want | n | RETURNED | ABSTAINED | WRONG |
|---|---|--:|--:|--:|--:|
| correct_cell (positive control) | RETURNED | 4 | 1 | 3 | 3 |
| correct_row_wrong_col | ABSTAINED | 1 | 0 | 1 | 0 |
| correct_col_wrong_row (cross-row) | ABSTAINED | 3 | **1** | 2 | 1 |
| correct_metric_wrong_condition | ABSTAINED | 3 | **1** | 2 | 1 |
| cross_table_substitution | ABSTAINED | 9 | **1** | 8 | 1 |

**Adversarial acceptances (FOOLED): 3 — MUST be 0. This is a stop condition.**
Cross-row acceptances: 1.

| # | paper | class | crafted claim | gate |
|---|---|---|---|---|
| 1 | 33fea4124e | correct_col_wrong_row | "CNN reports a **Performance metrics** of 80.52 on the study cohort." (80.52 is GA's row) | RETURNED, OWN_PAPER |
| 2 | 33fea4124e | correct_metric_wrong_condition | "CNN reports a **Performance metrics** of 87.82 on the study cohort." (87.82 is K-SVM's row) | RETURNED, OWN_PAPER |
| 3 | eef59dba16 | cross_table_substitution | "Arsenic (As) reports a **Blood component used for measurement** of 12…" (12 from another table) | RETURNED, OWN_PAPER |

### Mechanism (reported, rule NOT adjusted)

All 3 land in `structural_bind` **case 2 → `not_bindable`**, which by design falls
through to grounding + attribution + the 5a range check. Two compounding causes:

1. **`_col_matches_metric` is asymmetric.** It identifies a column as a metric
   column via a permissive branch: any `_METRIC_TOKENS` entry ≥2 chars appearing
   as a *substring* of the de-punctuated header. `"Performance metrics"` matches
   because `"em"` (from *exact match*) is a substring of `performanc`**`em`**`etrics`;
   `"Blood component used for measurement"` matches similarly. The probe harness
   used this same function to pick "metric columns", so it crafted claims naming
   those group headers. But inside `structural_bind`, the *claim-side*
   `metric_toks` is a strict set — `_sig_tokens(value) & _METRIC_TOKENS` plus
   `_METRIC_NAME_RE` — and `{"performance","metrics"}` intersect `_METRIC_TOKENS`
   is **∅**. Empty `metric_toks` ⇒ `metric_columns == []` ⇒ case 2. A claim can
   thus name a real, tabulated column and still be `not_bindable`.
   *(The real metric columns in that table — "Accuracy (%)", "True positive rate
   (%)" — DO carry `_METRIC_TOKENS` words ("accuracy", "rate"); a probe naming
   "Accuracy" binds and is caught as `wrong_cell`. 12 of the 15 adversarial probes
   were in fact caught via `wrong_cell`.)*

2. **The fall-through safety net is weaker on compact JATS table chunks.**
   `not_bindable` defers to number-anchored grounding: *number verbatim + ≥2
   significant topical tokens co-occur in one chunk*. On canonical LaTeX the same
   `not_bindable` fall-throughs still ABSTAINED (FOOLED 0) because a LaTeX table's
   rows are sprawled across many chunks, so a crafted `subject + wrong-number`
   pair rarely co-occurs. On JATS, the **entire** Table 5 of `33fea4124e` —
   caption, all headers, all five method rows — is a single 285-char chunk:

   > `Table 5 … Methods Performance metrics True positive rate (%) … Accuracy (%) GA 80.52 77.23 80.82 CNN 83.21 79.01 82.13 … K-SVM 87.82 82.71 87.03 …`

   So `"CNN" + "80.52" + "performance" + "metrics"` trivially co-occur; grounding
   passes; attribution is OWN_PAPER (no citation marker); the claim is RETURNED.

### Would these have been caught on canonical?

Yes. The canonical `correct_col_wrong_row` / `cross_table_substitution` probes
were **all** ABSTAINED (FOOLED 0): ~⅓ via `wrong_cell` binding, the rest via the
grounding net that the compact JATS chunk defeats. The regression is specific to
**JATS-derived structure + biomedical column vocabulary**, not to structured
binding in general.

### Residual, and why the rule was left alone

The task is explicit: *report the mechanism, do not adjust the rule*. Closing this
would mean either (a) widening `_METRIC_TOKENS` / rewriting `_col_matches_metric`
to a biomedical vocabulary — a tuning change, out of scope and risky — or
(b) making case 2 reject instead of fall through, which would withhold every
legitimate biomedical prose aggregate (the gate already returns only 2 structured
items on 11 papers; case 2 → reject would take that to ~0). Neither is a
mechanical fix. Logged here and in `binding_validation_measure.py`.

---

## TASK 4 — Test 2 mutation suite incl. medical JATS papers (v2 oracle)

`gate_sensitivity.py --pass all --medical`. Base RETURNED quant items across the
three corpora: **38** (canonical60 22 · data_test 4 · medical_jats 12). Medical
mutants generated: 17.

| matrix | pos | neg | TP | FN | FP | TN | precision | sensitivity | specificity |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **A** old oracle, ALL mutants (pre-5 baseline) | 39 | 59 | 4 | 35 | 13 | 46 | 0.235 | **0.103** | 0.780 |
| **B** new (v2) oracle, ALL mutants | 5 | 93 | 4 | 1 | 13 | 80 | 0.235 | **0.800** | 0.860 |
| **C** new oracle, UNCHANGED mutants only ← reported sensitivity | **5** | 59 | 4 | 1 | 13 | 46 | 0.235 | **0.800** | 0.780 |

- **Matrix C positive set: n = 5** (was **3**). The medical JATS corpus added
  **exactly 2** positives, both true positives:
  `ec45017959` `paraphrase_rule` and `paraphrase_llm` of *"Cells were classified…
  with 60% of cells matching fetal brain cell types."* → both RETURNED (correct).
- **n = 5 is still small. Denominator, explicitly:** the gate returns only
  **2 numeric quant items on all 11 biomedical JATS papers**, and Matrix-C
  positives are should-ACCEPT *paraphrase* mutants, which are generated only from
  `results`-sentence items. The medical corpus produced exactly **one** such
  sentence, yielding 1 rule + 1 LLM paraphrase = 2 positives. The canonical
  contribution to C (3) is likewise capped by `cf099b7cd7` being the only
  canonical paper whose structured result-sentence paraphrases survive the v2
  contract (all other canonical result-sentence papers are PDF-only → their
  paraphrases moved to CONTRACT_CHANGED). **Reported binding sensitivity = 4/5 =
  0.80 on n = 5 should-ACCEPT cases; treat as directional, not a rate.**
- **CONTRACT_CHANGED: 34 mutants** (all `paraphrase_rule` / `paraphrase_llm`),
  every one for the same reason — *numeric OWN claim on a PDF-only paper → post-5
  `unverifiable_binding`*. Full list in `runs/gate_sensitivity/contract_matrices.json`.
  No medical mutant is CONTRACT_CHANGED (the 11 JATS papers have `table_cells`, so
  `_paper_is_pdf_only` is false and the post-5 PDF-only contract change does not
  touch them).
- `_crossrow_probe` (the harness's own canonical-style two-token cross-row probe):
  **8 probes, FOOLED 0** — unchanged. The Task-3 JATS-specific probes are more
  aggressive and are what surface the case-2 gap.
- Pre-existing weakness, not new: `support_deletion_primary` WRONG = 13 (several
  medical) — removing the single primary support chunk still grounds when the
  value recurs in another chunk. Untouched here.

---

## TASK 5 — cross-domain comparison (side by side, NOT pooled)

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
| of RETURNED: (n/a — non-numeric metric-name / PDF-only rep) | 3 | 3 |
| `bound` rate | 0 / 5 | 0 / 2 |
| adversarial probe acceptances | **0** | **3** |
| `wrong_cell` fired on adversarial probes | 2 / 6 cross-row | **12 / 15** |
| `correct_cell` positive-control returned | 1 / 9 | 1 / 4 |
| 15 safety invariants | 15/15 | 15/15 |

(Medical's full case distribution over *all* numeric items — RETURNED and
ABSTAINED — is in Task 2: `pdf_only 11 · not_bindable 4 · bound 0 · wrong_cell 1`.
The canonical run did not persist the ABSTAINED-side distribution.)

**Does the contract behave the same across the two domains and structured
sources? No — and the differences are the finding:**

1. **`bound` (case 3) is inert in both** on real extraction (0/5, 0/2). The
   contract's cell-level bind never engages against LLM-extracted claim text in
   either domain; what engages is `wrong_cell` (case 4/5b) against *synthetic*
   probes whose metric string is copied verbatim from a header.
2. **`wrong_cell` protection is actually stronger on JATS** for well-formed probes
   (12/15 vs 2/6) — because JATS cells are cleaner, so a probe naming a real
   metric column reliably lands in case 4. The LaTeX cell model still carries
   `\cmidrule` / macro debris that degrades column matching.
3. **The fall-through net is weaker on JATS.** Case 2 `not_bindable` +
   compact single-chunk tables = the 3 acceptances. Same case count (4) in both
   domains; different consequence.
4. **`pdf_only` dominates the medical distribution (11)** because 12 of 23
   medical full-text papers are PDF (arXiv/S2), and 4 of the 11 JATS papers carry
   no data tables at all. The structured surface on this corpus is genuinely
   thin — 7 papers, 1371 cells — despite 11 JATS acquisitions.

---

## Tests, suite, invariants

| check | result |
|---|---|
| `tests/test_pipeline.py` + `tests/test_anchors.py` | **15 / 15** |
| experiment suite `tests/test_pipeline_units.py` | **46 / 46** |
| 15 safety invariants — medical binding_validation (`binding_validation_invariants.py`) | **15 / 15 PASS** |
| 15 safety invariants — latest data_test staging run (`staging-20260904T021129Z`) | 15 / 15 PASS (no gate/selector/Stage-2/config code changed) |

Invariants **14** (`cross_row_binding_acceptances_zero`) and **15**
(`no_own_quantitative_from_unverifiable_binding`) both PASS on the medical output
even though Task 3 found 3 adversarial acceptances — because both invariants are
defined against the contract's failure statuses (`wrong_cell` / `pdf_only` /
`no_cell` / `no_metric`), and the 3 acceptances route through `not_bindable`,
which is a by-design fall-through, not a failure. On the **real** Stage-4
extraction output there are **0** such fabricated claims (the gate returns 3
numeric items corpus-wide), so no invariant fires. The probes are synthetic
adversarial injections that expose a domain-transfer hole the invariants, as
currently written, do not police.

---

## Files

- `binding_validation_measure.py` — Tasks 1, 2, 3, 5
- `gate_sensitivity.py` — `--medical` flag added (appends the medical corpus; harness only)
- `binding_validation_invariants.py` — 15 invariants on the medical output
- `runs/binding_validation/` — `processed/{chunks,extraction_cache,paper_evidence}.json`,
  `task1_verify.json`, `task2_binding.json`, `task3_probes.json`,
  `task5_cross_domain.json`, `invariants.json`, `run.log`, `task4_gate_sensitivity.log`
- `runs/gate_sensitivity/` — `mutants.json`, `contract_matrices.json`

## Not in this commit

- No change to `structural_bind`, `_col_matches_metric`, `_METRIC_TOKENS`, or any
  gate/selector/acquisition code. The case-2 `not_bindable` residual gap and the
  compact-JATS-chunk grounding weakness are reported, not patched.
- The medical corpus stays in `runs/binding_validation/` — `data/` untouched.
- No production config change; `latex_ingestion_enabled` stays `false`.
