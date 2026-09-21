# PHASE 0 — STATE RECONCILIATION

Branch `claude-code-verification` · verifier run at HEAD `09fbc95` (code identical at the
current HEAD; the two commits since touch only `.claude/`, `CLAUDE.md`, `.gitignore`,
`RESEARCH_DIRECTIVE.md` — nothing under `src/`, `experiments/` or `reproducibility/`).

Read-only except this file. One working command run: `python reproducibility/verify_deterministic.py`.

**Entrypoint correction.** There is no `reproducibility/verify_results.py`. The script is
`reproducibility/verify_deterministic.py`; `reproducibility/verify_results.json` is its *output*.

---

## A. GROUND TRUTH OF STATE

### A1. What the verifier asserts, and whether it passes

**Pass/fail summary line, verbatim, exit code 0:**

```
36 passed, 0 failed, 0 skipped, of 36 expected
```

The 36 checks, from `reproducibility/verify_results.json` (`checks[]`, keys
`check / expected / got / tolerance / status`; all 36 `PASS`, all `tolerance: 0`):

| # | check | expected |
|--:|---|---|
| 1 | anchor regex unchanged | `\d+\.\d+|\b\d{2,}\b` |
| 2 | EXTRACTION_OUTPUT_RESERVATION | 768 |
| 3 | DEFAULT_PARITY_TOLERANCE | 0.0 |
| 4 | latex_ingestion_enabled stays false | True |
| 5 | fallbacks measured | 12 |
| 6 | justified | 12 |
| 7 | over-triggered | 0 |
| 8 | prose fired | 12 |
| 9 | table fired | 4 |
| 10 | caption fired | 1 |
| 11 | deficit < 2% | 4 |
| 12 | deficit >= 20% | 4 |
| 13 | latex table survival >= pdf | 8 |
| 14 | f3b06a914702 table survival 1.000/1.000 | [1.0, 1.0] |
| 15 | f3b06a914702 discarded anyway | JUSTIFIED |
| 16 | medical probes | 13 |
| 17 | adversarial acceptances (any route) | 0 |
| 18 | caught via wrong_cell | 12 |
| 19 | canonical probes | 16 |
| 20 | canonical adversarial acceptances | 0 |
| 21 | crossrow probes | 8 |
| 22 | crossrow acceptances | 0 |
| 23 | invariant-16 suite total | 37 |
| 24 | medical JATS structured cells | 1371 |
| 25 | medical JATS papers | 11 |
| 26 | tables parsed to cells | 22 |
| 27 | evaluation-framework cases | 106 |
| 28 | unscored cases | 0 |
| 29 | canonical60 papers | 60 |
| 30 | data_test8 papers | 8 |
| 31 | medical50_frozen full-text | 19 |
| 32 | medical50_reacquired full-text | 23 |
| 33 | canonical60: every full-text file hashed | 0 |
| 34 | data_test8: every full-text file hashed | 0 |
| 35 | medical50_frozen: every full-text file hashed | 0 |
| 36 | medical50_reacquired: every full-text file hashed | 0 |

**What that set is.** Checks 1–4 are frozen config constants; 5–15 the parity-gate fallback
slice; 16–23 adversarial-probe counts and acceptances; 24–26 JATS cell parsing; 27–28 the
evaluation-framework denominator; 29–32 corpus sizes; 33–36 hash completeness (0 unhashed).

**What it does not assert.** The verifier asserts **counts, constants and hashes**, not the
headline rates. No check contains 98.6 %, 16.8 %, 8.9 %, 0.983/0.987, 5.82 vs 9.91, or
+16 pp / +26 pp. Mapping the 36 checks onto the ledger's claims:

- backed by ≥1 check: claims 8, 10, 11, 13 (and claim 9's *denominator* only — 106 cases,
  0 unscored; not its 18/19, 6/19, 19/19, 31/67, 54/67 ratios).
- backed by **no check at all**: claims 1, 2, 3, 4, 5, 6, 14.

Three of the five abstract-eligible claims (1, 3, 14 — `CLAIM_LEDGER.md:100`, `:101`, `:104`)
have **zero verifier coverage**. "36/36 green" is not evidence that the paper's headline
numbers reproduce.

### A2. Claim-by-claim backing

`experiments/document_evidence_pipeline/CLAIM_LEDGER.md` holds **22 rows** carrying **14
distinct claim numbers** (1–14). Rows at `:26`–`:31`, `:39`–`:46`, `:57`–`:62`, `:70`–`:71`.

| row | claim (short) | report cited | run artifact | status |
|---|---|---|---|---|
| 1 | value preservation ≠ evidence preservation | `EXTRACTION_FIDELITY_REPORT.md` §STEP 3 POOLED | `runs/extraction_fidelity/` | SUPPORTED |
| 2 | metric improves while denominator collapses | `LATEX_ACQUISITION_REPORT.md` §MEASURE 1 | `runs/latex_acquisition/` | SUPPORTED |
| 3 | content parity ≠ extraction parity | `LATEX_ACQUISITION_REPORT.md` §MEASURE 1–2 | `runs/latex_acquisition/` | SUPPORTED |
| 4 | constants tuned on one distribution fail silently | `LATEX_ACQUISITION_REPORT.md` §TASK 1 | `runs/reservation_4096/` | SUPPORTED |
| 5 | delivery and coverage not proportional | `SELECTION_POLICY_REPORT.md`, `MEDICAL_RECHUNK_REPORT.md`, `MEDICAL_SELECTOR_CONTROL_REPORT.md` | `runs/selection_policy/`, `runs/medical_rechunk/` | SUPPORTED |
| 6 | failure modes differ across domains | `BINDING_VALIDATION_REPORT.md` §TASK 5 | `runs/binding_validation/` | SUPPORTED |
| 7 | invariants pass on a broken system | `LATEX_ACQUISITION_REPORT.md`, `BINDING_VALIDATION_REPORT.md` | `runs/latex_acquisition/`, `runs/binding_validation/` | SUPPORTED (3 instances) |
| 7b | "15/15 on the pre-5b binding gap" | **none in source set** | none | **UNSUPPORTED** |
| 7c | "a 37/37 suite that was actually 6" | **none in source set** | none | **UNSUPPORTED** |
| 7d | green suite ≠ pipeline runs | **no report** — `PROJECT_STATE.md` §10.5 + commit `6ae3d55` | none | SUPPORTED *(see flag below)* |
| 8 | coverage ≠ completeness | `BINDING_VALIDATION_REPORT.md` §F2 | `runs/binding_validation/` | SUPPORTED |
| 9 | mean-over-claims dilutes single-value errors | `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` | `runs/eval_framework_sensitivity/` | NARROWED |
| 9s | "conventional eval misses structural failures" | withdrawn on its own positive control (n=2, not 8) | — | **WITHDRAWN** |
| 10 | binding sound vs attacks, inert on real claims | `BINDING_VALIDATION_REPORT.md` | `runs/binding_validation/` | SUPPORTED |
| 11 | parity gate fires on real loss, conservative | `PARITY_GATE_PRECISION_REPORT.md` | `runs/parity_gate_precision/` | NARROWED |
| 11s | "gate accurately identifies inferior representations" | "accurate" not measured | — | **WITHDRAWN** |
| 12 | content retention as enforced ingestion gate | `PARITY_GATE_PRECISION_REPORT.md`, `LATEX_ACQUISITION_REPORT.md` | as above | NARROWED |
| 12s | novelty delta vs arXiv 2605.30790 | **no literature survey in source set** | none | **WITHDRAWN + delta UNSUPPORTED** |
| 13 | new mutation class for quantitative binding | `GATE_SENSITIVITY_REPORT.md`, `BINDING_VALIDATION_REPORT.md` | `runs/gate_sensitivity/`, `runs/binding_validation/` | NARROWED |
| 13s | novelty delta vs MetaRAG | **no literature survey in source set** | none | **WITHDRAWN + delta UNSUPPORTED** |
| 14 | content-aware selection isolated contribution | `MEDICAL_SELECTOR_CONTROL_REPORT.md` §Result | `runs/medical_selector_control/` | SUPPORTED |
| 14s | confounded +27/+31 pp version | confounded with prompt-variant flip | — | **WITHDRAWN** |

Every `runs/<name>/` directory named above exists on disk.

**Claims flagged as having no artifact behind them:**

- **7b, 7c** — self-declared UNSUPPORTED at `CLAIM_LEDGER.md:40-41`. 7b's evidence is said to
  live in `STRUCTURAL_BINDING_REPORT.md`, which *does exist in the tree* but was excluded from
  the nominated source set; the exclusion is a scoping decision, not an absence of the file.
- **12s, 13s** — the narrowings stand, but both novelty deltas are UNSUPPORTED; no literature
  survey exists in the repository.
- **7d** — SUPPORTED but its only source is `PROJECT_STATE.md` §10.5 plus commit `6ae3d55`.
  `PROJECT_STATE.md` is demonstrably unreliable (see below). No `*_REPORT.md` covers it. This
  is the one SUPPORTED row whose evidence base is a file this phase has shown to contain errors.
- `PHASE6_REGRESSION_REPORT.md`, nominated as a 13th source, does not exist
  (`CLAIM_LEDGER.md:14-17`). Confirmed: 20 `*_REPORT.md` files are present, that is not one.

---

## B. THE DECIDING QUESTION

### B3. Do the existing reports measure error attribution by pipeline stage?

**No.** No report or artifact states what fraction of failures originated in parsing vs
retrieval vs extraction vs evidence-binding. A case-insensitive search across all 20
`*_REPORT.md` and `EXPERIMENT_MATRIX.md` for `error attribution`, `attributed to stage`,
`failure distribution`, `per-stage` and `stage-level` returns **no matches**.

The closest existing artifact is `EXTRACTION_TRIAGE_REPORT.md`, and it is worth stating
exactly how far it goes and where it stops. Its STEP 3 buckets (`:31`–`:40`) classify 19
full-text papers by *where infrastructure is intact*, not by which stage produced an error:

| bucket | n | meaning |
|---|--:|---|
| A1 NO_TEXT_LAYER | 0 | — |
| A2 LOW_TEXT_DENSITY | 0 | — |
| M MIXED / image-region | 2 geometric → 0 confirmed | figures, not tables-as-images |
| B text present, chunks ~0 | 1 candidate → 0 confirmed | threshold false positive |
| **C text + chunks + embeddings all present; loss is downstream** | **17** | undifferentiated |
| D | 0 | — |

17 of 19 land in one bucket labelled "loss is **downstream**" (`EXTRACTION_TRIAGE_REPORT.md:39`).
That single bucket contains retrieval failure, extraction failure and evidence-binding failure
merged together — precisely the distinctions the directive requires. The report then traces
**5 papers** (STEP 4, `:42`) and attributes those to Stage 4 (`:52`–`:55`):

> "acquisition, the text layer, reference cutting, chunking, and embedding are all **intact**
> (Bucket C). The loss is in **Stage 4 extraction**"

So: a two-way split (infrastructure vs downstream) over n=19 on one corpus, with a hand-traced
5-paper subset. Not a four-way attribution, not a distribution, not corpus-wide.

**What the reports measure instead**, stage by stage, each in isolation:

- **Representation** — `EXTRACTION_FIDELITY_REPORT.md`: verbatim survival of ground-truth
  numeric values through PDF vs LaTeX (98.6 % lax / 69.9 % strict / 16.8 % context-bindable,
  6,530 values over 23 paired papers).
- **Retrieval capability** — `RETRIEVAL_RECALL_REPORT.md:80`: R@5 0.886 / R@10 0.940 /
  R@20 0.975 over 3,981 anchors, 34 papers.
- **Retrieval delivery** — same row, column "in production selection" = **0.090**;
  `SELECTION_POLICY_REPORT.md:24` STEP 0 baseline delivery 0.090 (gate-ZERO 0.055,
  gate-SOME 0.143, table 0.049, prose 0.111).
- **Extraction** — field-presence counts per corpus (e.g. `metrics` missing on 9/19,
  `EXTRACTION_TRIAGE_REPORT.md:60`); selection ablation +16 pp / +26 pp (claim 14).
- **Evidence-binding** — adversarial probe acceptance rates (0 of 30 across 37 probes).
- Plus: ablations of one component, gate precision, evaluator sensitivity, throughput.

These are **per-stage capability measurements on separate populations**, not an attribution of
a common failure set.

### B4. Do the three per-failure flags exist?

The directive's three flags are: (a) present in the parsed representation, (b) present in the
chunk store, (c) present in the top-k passed to the model.

| flag | exists? | where, and with what limitation |
|---|---|---|
| (a) in parsed representation | **partially, as an aggregate** | `EXTRACTION_FIDELITY_REPORT.md` measures value survival PDF vs LaTeX, but only on the **23 paired arXiv papers** that have both representations. For PDF-only papers there is no reference, and `EXTRACTION_TRIAGE_REPORT.md:71-79` reports field-presence **undeterminable for 19/19 (100 %)** — "extraction coverage cannot be computed against a real denominator on any PDF-only paper in this corpus" (`:79`). |
| (b) in chunk store | **not recorded — true by construction** | Anchors in `RETRIEVAL_RECALL_REPORT.md:49` are *derived from* the full-text chunks, so every anchor is in the store by definition. The flag is never written down because the population is defined to make it always true. |
| (c) in top-k passed to the model | **yes, as a rate** | `RETRIEVAL_RECALL_REPORT.md:80` "in production selection" 0.090; per-anchor ranks recorded in `runs/retrieval_recall/`. |

A grep across all reports for `in_chunk`, `in_topk`, `present_in_*`, "reached the model",
"made it to the prompt" returns **no matches**. The flags are never co-recorded on one record.

Two structural reasons they cannot currently be joined:

1. **Different populations.** (a) exists only for 23 paired papers; (c) is measured over 3,981
   self-supervised numeric anchors on 34 canonical papers; extraction outcomes are per-field on
   19 medical papers. No row exists that carries all three.
2. **Anchors are not field values.** A retrieval anchor is any numeric token matching
   `\d+\.\d+|\b\d{2,}\b`. An extraction failure is an empty or wrong `metrics`/`results` field.
   Nothing maps one onto the other, so "the anchor was delivered" cannot be read as "the
   information the extractor needed was delivered".

### B5. Unit of evaluation

**Not consistent.** At least seven different units across the reports:

| unit | reports |
|---|---|
| numeric **value** | `EXTRACTION_FIDELITY_REPORT.md` (6,530; per-value rows at `:197`) |
| numeric **anchor** | `RETRIEVAL_RECALL_REPORT.md` (3,981, `:49`), `SELECTION_POLICY_REPORT.md` (3,981, `:24`), `ANCHOR_CENTRALIZATION_REPORT.md` |
| **paper** | `EXTRACTION_TRIAGE_REPORT.md` (n=19), `MEDICAL_SELECTOR_CONTROL_REPORT.md` (19), `CONTEXT_BUDGET_REPORT.md`, `DIAG_0549E2E9_REPORT.md` |
| **field** (paper × 5 fields) | `EXTRACTION_TRIAGE_REPORT.md:73`, `MEDICAL_RECHUNK_REPORT.md:199` |
| **probe** | `BINDING_VALIDATION_REPORT.md` (37), `STRUCTURAL_BINDING_REPORT.md` |
| **case / mutant** | `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` (106), `GATE_SENSITIVITY_REPORT.md` (98 = 39 pos + 59 neg) |
| **fallback event** | `PARITY_GATE_PRECISION_REPORT.md` (12) |
| **table cell** | JATS cell counts (1,371 cells / 11 papers; verifier checks 24–26) |

No common denominator exists across the set, so the reports cannot be summed or compared into a
single distribution without first choosing a unit and re-deriving every number against it.

---

## C. CORPUS

### C6. Exact corpus of the existing runs

Four manifests in `reproducibility/manifests/`, three distinct paper sets (medical50 appears
twice as two acquisition states of the same 50 papers). Counts from
`reproducibility/manifests/index.json`, all confirmed by verifier checks 29–36:

| manifest | papers | full-text | representation mix | hashed |
|---|--:|--:|---|--:|
| `canonical60.json` | 60 | 34 | pdf 32 · abstract 26 · jats_xml 2 | 34/34 |
| `data_test8.json` | 8 | 7 | pdf 7 · abstract 1 | 7/7 |
| `medical50_frozen.json` | 50 | 19 | abstract 31 · pdf 19 | 19/19 |
| `medical50_reacquired.json` | 50 | 23 | abstract 27 · pdf 12 · jats_xml 11 | 23/23 |

**Distinct papers: 118** (60 + 8 + 50). **Full-text: 34 + 7 + 19→23.**

**Paper ids.** Not enumerated here. They live in the four manifest JSONs above, with per-paper
`doi` / `arxiv` / `pmcid` coverage recorded (canonical60: doi 55, arxiv 24, pmcid 2).

**Is it the same set across all reports? No** — and deliberately so. `PROJECT_STATE.md` §8 item
6 states corpora are **never pooled**: canonical 60 / data_test 8 / medical 50 stay separate.
The ledger's "Corpus" column confirms different rows rest on different sets: claim 1 on 23
paired canonical papers, claim 5 on canonical 34 *and* medical 19 reported separately, claim 9
on all three corpora as 106 cases with the corpus label carried per case and explicitly "never
pooled into a per-corpus rate" (`CLAIM_LEDGER.md:44`), claim 14 on medical 19 only.

**Held-out split: none.** A search for `held-out`, `train/test`, `holdout`, `dev set`,
`validation split` across all reports and harness scripts returns two hits, both incidental
prose — `STRUCTURAL_BINDING_REPORT.md:149` (a keyword in a results-phrase list) and
`gate_sensitivity.py:257` (a sentence template inside a mutation generator). No corpus split is
defined anywhere.

---

## PROJECT_STATE.md errors observed (reported, not corrected, per instruction)

- `PROJECT_STATE.md:6` — records HEAD `2b132ab`; actual HEAD at session start was `09fbc95`.
- `PROJECT_STATE.md:14`, `:22` — call `reproducibility/` "INCOMPLETE, UNCOMMITTED"; it is
  committed, 25 tracked files, across `7926eda`, `d5dc51d`, `09fbc95`.
- `PROJECT_STATE.md:19` — "12 measurement reports"; 20 `*_REPORT.md` files exist. The number 12
  is the ledger's *nominated source set*, not the count of reports in the tree.
- `PROJECT_STATE.md` §1 — "26 rows / 20 claims" for the ledger; the ledger has **22 rows** and
  **14 distinct claim numbers**.
- `PROJECT_STATE.md` §7 — names `reproducibility/verify_deterministic.py` correctly; the
  filename `verify_results.py` used in the Phase 0 brief does not exist.

---

## VERDICT

STAGE ATTRIBUTION NOT MEASURED — existing work measures per-stage capability in isolation (representation survival 98.6 %/16.8 % over 6,530 values, retrieval recall R@10 0.940 vs production delivery 0.090 over 3,981 anchors, per-field extraction presence over 19 papers, 0/30 adversarial binding acceptances) on non-overlapping populations with seven different evaluation units, plus a two-way infrastructure-vs-downstream triage that puts 17 of 19 papers in one undifferentiated "downstream" bucket
