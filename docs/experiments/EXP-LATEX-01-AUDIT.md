# EXP-LATEX-01 — Pre-experiment repository audit

Branch `claude/busy-rubin-q2j212` · base commit `acb89d8` · 2026-09-15
Audit performed before any code was written, per Part 1 of the experiment protocol.

---

## 0. Two findings that change the experiment before it starts

**Finding A — the primary question has already been measured on this corpus, twice, and the answer was negative.**

`experiments/document_evidence_pipeline/LATEX_ACQUISITION_REPORT.md` documents
Phase 4 (arXiv LaTeX e-print ingestion), Phase 4b (MEASURE 1–4, Task 1, Task 2)
and Phase 5x (corpus-wide at reservation 4096). LaTeX-aware ingestion is
implemented, parity-gated, measured end-to-end, and **disabled by default** on
the evidence. The relevant measured values:

| Quantity | Measured | Part-15 gate | Verdict against the gate |
|---|--:|--:|---|
| Table binding, LaTeX-retained subset (gt-weighted) | **0.142** | ≥ 0.60 | fails by ~4x |
| Table binding, LaTeX-retained subset (macro) | **0.241** | ≥ 0.60 | fails by ~2.5x |
| Table binding, pooled all-papers | 0.110 (vs PDF 0.089) | ≥ 0.089 | would pass |
| Numeric survival, verbatim-lax | 0.981 (vs PDF 0.986) | ≥ 0.980 | would pass |
| Runtime | **+47 %** (32 → 47 s/paper) | ≤ +50 % | would pass, narrowly |
| Peak VRAM | **5909 / 6144 MiB (96 %)** = 5.77 GB | ≤ 5.5 GB | fails |
| Extraction, LaTeX-retained mean fields | **9.91 → 5.82** @768, 9.00 @4096 | — | regression |

The Part-15 **primary** gate (LaTeX-eligible table binding ≥ 60 %) is not
marginally missed; the best existing measurement is 24 % on the most favourable
aggregation. Re-running the same comparison is very unlikely to change this.

**Finding B — the secondary hypothesis is genuinely untested, and it is the part worth running.**

Part 5's requirement — never split a `tabular` block across chunks — is **not
implemented anywhere in the repository**. `src/evidence/chunker.py` splits every
block, table blocks included, at `CHUNK_WORDS = 220` with a 40-word overlap.
That is the real, unmeasured gap.

One correction to the protocol's framing: the "768-token chunking problem"
conflates two different constants. In this project **768 is
`EXTRACTION_OUTPUT_RESERVATION`** — the `num_predict` output cap on qwen2.5:7b
(`src/summarization/summarize.py:314`) — not a chunk size. Chunking is 220 words
(`src/evidence/chunker.py`) or 800 characters (`src/processing/pdf_parser.py`,
legacy path). Table splitting and output-cap truncation are separate failure
modes with separate fixes; EXP-LATEX-01 addresses the first.

---

## 1. Repository architecture

Six stages, plus an evidence-grounding path that runs inside stages 1–2.

```
Stage 1  Collection    src/collection/semantic_scholar.py   (+ arxiv_fallback.py)
         Acquisition   src/evidence/acquire.py              4 acquisition states,
                                                            identity + content validation
Stage 2  Processing    src/processing/pdf_parser.py         PyMuPDF text + legacy chunking
         Representation src/evidence/represent.py           blocks_from_pdf / _jats / _latex
         Structure     src/evidence/latex_tables.py         structural cell model
                       src/evidence/latex_source.py         arXiv e-print fetch (stdlib tar/gzip)
                       src/evidence/latex_parity.py         the parity gate
         Chunking      src/evidence/chunker.py              CHUNK_WORDS=220, OVERLAP=40
Stage 3  Embedding     src/embedding/build_index.py         BGE-M3 -> ChromaDB
         Selection     src/summarization/retrieval_aware.py legacy | content_aware
Stage 4  Extraction    src/summarization/summarize.py       qwen2.5:7b via Ollama
         Evidence gate src/evidence/gate.py                 numeric anchors, structural binding
         Attribution   src/evidence/attribute.py            OWN_PAPER / CITED
Stage 5  Synthesis     src/synthesis/{corpus_synthesis,review_synthesis,gap_analysis}.py
Stage 6  API/UI        src/api/main.py, frontend/
```

Supporting: `src/evidence/schema.py` (canonical record shapes, `structured_table`,
`table_cell`, `validate_acquisition_record`), `src/evidence/anchors.py`
(centralised numeric-anchor regex), `src/evidence/monitor.py`,
`src/evidence/verifier.py`, `src/reporting/corpus_table.py`.

Measurement lives in `experiments/document_evidence_pipeline/` (23 harnesses,
23 reports), kept read-only against production data and writing only to its own
gitignored `runs/`.

## 2. Existing modules relevant to this experiment

| Concern | Module | State |
|---|---|---|
| LaTeX acquisition | `src/evidence/latex_source.py` | complete; e-print fetch, `\input`/`\include` resolution, throttled 1/3 s |
| LaTeX table structure | `src/evidence/latex_tables.py` | complete; `tabular`/`tabular*`/`tabularx`/`array`/`longtable`, floats `table`/`table*`/`sidewaystable`, `\multicolumn`/`\multirow` |
| Content-parity enforcement | `src/evidence/latex_parity.py` | complete; per-split verbatim survival, whole-paper PDF fallback, tolerance 0.0 |
| JATS structure | `represent._jats_table_cells` | complete; same `structured_table` shape |
| Chunking | `src/evidence/chunker.py` | **no table awareness** — the gap |
| Feature flags | — | **none existed**; config had `latex_ingestion_enabled` only |
| Paired statistics | — | **none existed** |
| Experiment output isolation | — | **none existed** |

Searches performed (Part 1 list): `paper-freeze`, `provenance`, `attribution`,
`abstention`, `deterministic`, `mutation`, `table binding`, `anchor`,
`numeric survival`, `BGE-M3`, `LaTeX`, `JATS`, `Chroma`, `canonical`,
`60-paper`, `146/146`, `81/81`, `91/91`.

Two search results worth recording:

* **There is no `paper-freeze` tag, and no tags at all.** `git tag -l` is empty;
  the only refs are `claude-code-verification` and `claude/busy-rubin-q2j212`.
  There is also no `main` branch, locally or on the remote. The "frozen
  baseline" is therefore a **documentary** freeze (the reports and
  `CLAIM_LEDGER.md`), not a git object. Rule 1 is satisfied by not modifying
  those reports — which this work does not — but the freeze is not
  cryptographically pinned, and that is a reproducibility weakness worth fixing
  independently of this experiment.
* **`91/91` exists in the repository, but it is a provenance rate, not a test
  count** (`FINAL_REPORT.md:236`, `:274`), and it was later superseded by
  108/108 (`RESULTS_GATE_TUNING_REPORT.md:93`). The documented test counts are
  15/15 and 42/42. See §3 for the full reconciliation of this and two other
  figures in the task brief.

## 3. Current baseline metrics, as recorded in the repository

From `experiments/document_evidence_pipeline/README.md`,
`LATEX_ACQUISITION_REPORT.md` and `CLAIM_LEDGER.md`. These are **historical
project values**, not measurements taken during this audit.

| Metric | Value | Source | Note |
|---|--:|---|---|
| Corpus | 60 papers | README headline | 34 full-text, 26 closed-access |
| Full-text acquisition | 34/60 = 56.7 % | README | up from 31/60 = 51.7 % |
| Numeric survival (verbatim-lax) | 98.6 % | Test 1, 6530 values / 23 papers | PDF path |
| Context-bindable, all | 16.8 % | Test 1 | |
| Context-bindable, table-resident | **8.9 %** | Test 1 | the motivating gap |
| Provenance | 100 % (**150/150**) | README, `FINAL_REPORT.md` §84 | |
| Wrong-paper attribution | 0 | README | |
| False OWN_PAPER | 0 observed | README | |
| Abstention | **78/78** abstain on inaccessible papers | README, `FINAL_REPORT.md` §117 | |
| Tests | **15/15** (`test_pipeline` + `test_anchors`) + **42/42** (experiment suite) | `LATEX_ACQUISITION_REPORT.md` §Tests | |
| Anchor delivery | 16.7 % | `SELECTION_POLICY_REPORT.md` §MEASURE 1 | `content_aware@10`, 0.167 |
| Runtime | 51 min / corpus, 2.65 GB VRAM | README | RTX 3050 6 GB |

### Reconciliation of the three figures in the task brief

All three were traced. None is a live value; two are superseded and one is a
category error.

| Brief says | Actually | Evidence |
|---|---|---|
| Provenance **146/146** | **Superseded.** 146/146 was the pre-attribution-rework figure; the current value is 150/150. | `progress.md:56` records 146/146; `FINAL_REPORT.md:86` states the transition explicitly — "Regression vs the pre-attribution-rework run (146/146 → 150/150): no provenance loss". |
| Abstention **81/81** | **Superseded.** 81/81 appears at an earlier point in the log; the run of record is 78/78. | `progress.md:57` = 81/81, `progress.md:72` = 78/78; `FINAL_REPORT.md:117` and the run-of-record row (`:193`) both carry 78/78. |
| Tests **91/91 = 100 %** | **Category error.** 91/91 is a *provenance-valid rate* from an earlier phase, not a test count — and it was itself later superseded by 108/108. | `FINAL_REPORT.md:236` and `:274` list "provenance-valid rate … 91/91 = 100%"; `RESULTS_GATE_TUNING_REPORT.md:93` shows "7 provenance-valid rate | 91/91 = 100% | **108/108 = 100%**". No test suite in this tree has 91 cases. |

This matters beyond bookkeeping. `CLAIM_LEDGER.md`'s preamble records that "this
project has three documented cases of a wrong number propagating, and the ledger
is the last guard against a fourth" — and row 7c records a suite reported as
37/37 that was actually 6. The 91/91 figure in the brief is that failure mode
recurring: a provenance rate migrating into a test-count slot across a document
boundary. **The Part-15 "Tests: 91/91 or better" gate cannot be evaluated as
written**; the defensible restatement is "no regression against 15/15 + 42/42,
plus the new suites".

## 4. Files that must change

| File | Change | Default behaviour |
|---|---|---|
| `src/evidence/flags.py` | **new** — `RQ_LATEX_CHUNKING`, `RQ_TABLE_ATOMIC`, strict boolean parsing | both OFF |
| `src/evidence/chunker.py` | table blocks kept whole when `RQ_TABLE_ATOMIC=1` | unchanged when OFF |
| `src/config.py` | tri-state env override for `evidence_grounding.latex_ingestion_enabled` | unchanged when unset |
| `src/evidence/latex_tables.py` | nested-grid detection (see §6) | reachable only on the LaTeX path, which is off by default |
| `tests/test_table_atomic.py` | **new** — the eight required table cases | — |
| `experiments/EXP-LATEX-01/**` | **new** — harness, statistics, gates, Kaggle | — |
| `docs/experiments/`, `docs/RESEARCHGPT_NOVELTY_EVIDENCE_REPORT.md` | **new** | — |

## 5. Files that must NOT change

* `configs/staging_config.yaml` — `latex_ingestion_enabled: false` stays false.
* `configs/config.yaml` — gitignored, production; never carried `evidence_grounding`.
* `EXTRACTION_OUTPUT_RESERVATION = 768` (`src/summarization/summarize.py:314`).
* `CHUNK_WORDS = 220`, `CHUNK_OVERLAP = 40` default values.
* Every report under `experiments/document_evidence_pipeline/` — these are the freeze.
* `experiments/document_evidence_pipeline/runs/` — frozen measurement artefacts.
* `src/evidence/latex_parity.py` — the parity gate's decision rule.
* Selector weights, prompt text, gate thresholds, scoring.

## 6. A defect found during the audit

Probing the eight required table shapes surfaced a silent-corruption bug in the
existing LaTeX parser.

`_TABULAR_RE` is non-greedy and closes on the *same* environment name, so for
`\begin{tabular} … \begin{tabular} … \end{tabular} … \end{tabular}` it stops at
the **inner** `\end{tabular}`. Observed on the nested fixture:

```
before:  status=parsed  cells=3
         cell value '\begintabularcc x'          <- markup parsed as a measurement
         row_label 'y' for the outer row 'B'     <- wrong row binding
         raw_text  'Group | Detail A | tabular cc x | 1 y | 2'
                                                 <- the value 7.5 is GONE
```

The row after the nested block is dropped from the structured cells **and** from
`raw_text`, while `parse_status` reports `"parsed"`. That violates the module's
own stated contract ("Partial success per paper is fine; silent failure is not")
and it is a numeric-fidelity loss the paper-level parity gate would only catch
if the aggregate deficit crossed tolerance.

Fix: `_true_env_body()` walks begin/end pairs across the whole grid family and
returns the body up to the *matching* closer; a table containing a nested grid
is marked `parse_status="fallback_pdf"`, `fallback="nested_tabular"`, with no
structured cells and a `raw_text` spanning the whole outer environment.

```
after:   status=fallback_pdf  fallback=nested_tabular  cells=0
         raw_text 'Group | Detail A | tabular cc x | 1 y | 2 tabular B | 7.5'
         7.5 recovered: True
```

Differential test over 300 generated tables: **226 identical, 74 differ, all 74
nested, 0 unexpected differences.**

**Consequence for the experiment**: the treatment arm is no longer byte-identical
to the Phase-4 LaTeX arm. EXP-LATEX-01's LaTeX results must be re-measured, not
differenced against Phase-4 numbers. The prevalence of nested tabular in the
canonical 24 arXiv papers is **unknown** — Phase 4 never checked for it, and the
corpus is not present in this environment.

## 7. Experiment design

**Independent variable**: LaTeX-aware structural ingestion (`RQ_LATEX_CHUNKING`)
and atomic tabular chunking (`RQ_TABLE_ATOMIC`).

**Held constant**: corpus, retrieval questions, evaluation queries, BGE-M3,
retrieval parameters, `CHUNK_WORDS`/`CHUNK_OVERLAP`, `EXTRACTION_OUTPUT_RESERVATION`,
qwen2.5:7b at temperature 0 / seed 42, `content_aware` selection at
`max_passages=10`, evaluation code, metric definitions.

**Arms.** The protocol specifies two. Because the two flags are independently
switchable, a two-arm design cannot attribute an observed effect to either, so
the harness supports the full 2×2:

| Arm | `RQ_LATEX_CHUNKING` | `RQ_TABLE_ATOMIC` | Role |
|---|:--:|:--:|---|
| `control` | 0 | 0 | protocol control |
| `latex` | 1 | 1 | protocol treatment |
| `atomic` | 0 | 1 | isolates the untested secondary hypothesis |
| `latex_only` | 1 | 0 | reproduces the already-negative Phase-4/5x config |

`atomic` is the arm with the most information value: it is the only cell of the
design that has never been measured.

**Statistics** (pre-registered in `experiments/EXP-LATEX-01/metrics_registry.py`
before any arm runs): paired t-test and Wilcoxon signed-rank for continuous;
Wilcoxon for proportions and counts; McNemar for paired binary; Wilson intervals
for pooled proportions; seeded percentile bootstrap for the mean difference;
Cohen's *dz* and rank-biserial *r* for effect size; Holm–Bonferroni across a
six-metric confirmatory family, with everything else labelled exploratory.

**Output isolation**: everything under `runs/exp-latex-01/`. `guard.py` refuses
`runs/`, `data/`, `data_test/`, `experiments/document_evidence_pipeline/runs/`,
and anything outside the experiment root — verified 18/18.

## 8. Risks

| # | Risk | Severity | Mitigation / status |
|---|---|---|---|
| R1 | The experiment re-measures a question already answered negatively and burns effort | **high** | Finding A is stated up front; `atomic` arm added as the informative cell |
| R2 | Atomic chunks exceed BGE-M3's 8192-token window and are silently truncated | **high** | chunks carry `table_n_words`, `table_oversized`, `table_over_embed_soft_limit`; **not yet measured with a tokenizer** |
| R3 | Atomic table chunks are less model-legible, repeating the Phase-4b extraction collapse | **high** | `atomic` arm measures it directly; this is the main way the experiment can fail |
| R4 | `RQ_TABLE_ATOMIC` also affects JATS and PDF table blocks, confounding "LaTeX effect" | medium | analysis stratifies by representation; documented, not silently scoped |
| R5 | Nested-tabular fix makes the LaTeX arm incomparable to Phase 4 | medium | stated in §6; Phase-4 numbers must not be used as this experiment's control |
| R6 | Fewer, larger chunks change retrieval behaviour independently of structure | medium | `n_chunks` and `n_table_chunks` recorded per paper |
| R7 | Kaggle T4 (16 GB) cannot test the 6 GB VRAM gate | medium | gate reframed as local deployability; both `torch` and `nvidia-smi` figures recorded |
| R8 | Ollama absent on Kaggle -> no Stage-4 extraction -> metric families D–G unmeasurable | **high** | script records the skip explicitly; those metrics read NOT MEASURED |
| R9 | Corpus absent from the repository | **realised** | arms cannot run here; runner refuses to emit partial output |

## 9. Proposed implementation

1. `src/evidence/flags.py` — strict tri-state flag reader. **Done.**
2. `src/evidence/chunker.py` — atomic table blocks under the flag; byte-identical when off. **Done**, verified against the pre-change implementation over 4,295 chunks / 400 randomised documents, 0 mismatches.
3. `src/config.py` — tri-state override, narrow (never enables `evidence_grounding.enabled`). **Done.**
4. `src/evidence/latex_tables.py` — nested-grid handling. **Done**, 0 unexpected differences over 300 generated tables.
5. `tests/test_table_atomic.py` — the eight cases plus flag and control-parity tests. **Done, 54/54.**
6. `experiments/EXP-LATEX-01/` — guard, environment capture, metric registry, paired statistics, analyser, gates, arm runner, Kaggle script and notebook. **Done**; statistics 82/82 against published references, analyser self-test 26/26 on synthetic data, guard 18/18.
7. Run the arms. **NOT DONE — blocked, see §10.**

## 10. Execution status

**No arm of EXP-LATEX-01 has been run.** The audit environment cannot run one:

```
python : 3.11.15          torch                : unavailable (ModuleNotFoundError)
cpu    : 4                sentence_transformers: unavailable
RAM    : 15 GB            chromadb             : unavailable
GPU    : none             pymupdf              : unavailable
nvidia-smi: absent        numpy / scipy        : unavailable
Ollama : absent           corpus (data/)       : absent (gitignored)
```

`pip install numpy scipy` failed against PyPI (read timeout through the proxy),
so even the CPU-only statistical dependencies were unavailable; the statistics
module is stdlib-only as a result.

`experiments/EXP-LATEX-01/run_arm.py --arm control --preflight-only` exits 2 and
writes `preflight.json` naming every blocker. It deliberately does not write a
`per_paper.json`, so no partial run can later be mistaken for a measurement.

**Every EXP-LATEX-01 metric in this repository is therefore NOT MEASURED.** The
deliverable of this work is the audit, the implementation, the defect fix, and a
verified harness — not a result.

## 11. Next step

Run on Kaggle T4×2 with the corpus attached, in this order: `env` → `benchmark`
(10 papers) → `atomic` arm → `control` arm → `latex` arm → `latex_only` arm →
`analyze` → `gates`. Start with `atomic` versus `control`: it is the cheapest
arm, it needs no arXiv e-print fetching, and it is the only comparison whose
outcome is genuinely unknown.
