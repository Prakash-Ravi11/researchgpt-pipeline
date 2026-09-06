# PROJECT STATE

Written from the files in this repository. Every number below names the file it came from.
Where a value is not in any file, it says **UNKNOWN** rather than an estimate.

Generated 2026-09-06. Branch `claude-code-verification`. HEAD `2b132ab`.

---

## 1. Current status

A six-stage document-evidence pipeline with an evidence gate, plus a measurement programme
whose results are assembled into a paper. The measurement programme is **complete and
frozen**. The reproducibility package is **partially built and uncommitted**.

| area | state |
|---|---|
| Pipeline stages 1–6 (`src/`) | complete; frozen at `paper-freeze-v1` plus 2 post-freeze source commits |
| 12 measurement reports | complete, committed |
| `CLAIM_LEDGER.md` | complete, committed — 20 claims / 26 rows |
| `EXPERIMENT_MATRIX.md` | complete, committed — 5 tables, cross-checked |
| `reproducibility/` package | **INCOMPLETE, UNCOMMITTED** — see §7 |
| Deterministic verifier | passes 36/36 (`reproducibility/verify_results.json`) |

---

## 2. Validated numbers, each with its source file

All read from committed run artifacts or committed reports. Nothing rounded here that is
not rounded in the source.

### 2.1 Representation fidelity — Table 1

Source: `experiments/document_evidence_pipeline/EXTRACTION_FIDELITY_REPORT.md` §STEP 3 POOLED;
`LATEX_ACQUISITION_REPORT.md` §MEASURE 1. Run dirs `runs/extraction_fidelity/`, `runs/latex_ingestion/`.

| quantity | value |
|---|---|
| meaningful numeric values, 23 paired papers | 6,530 (table 5,405 · prose 965 · caption 160) |
| PDF path verbatim-lax, all | 0.986 |
| PDF path verbatim-strict, all | 0.699 |
| PDF path context-bindable, all | 0.168 |
| PDF path context-bindable, **table** | **0.089** |
| LaTeX verbatim-lax, table — before parity fix | 0.388 |
| LaTeX verbatim-lax, table — after parity fix | 0.983 |
| provenance | conditional on strict survival — see §5 |

### 2.2 Mutation sensitivity — Table 2

Source: `runs/gate_sensitivity/contract_matrices.json` (current, 3 corpora);
`GATE_SENSITIVITY_REPORT.md` (superseded 2-corpus run).

| matrix | n_pos | n_neg | TP | FN | FP | TN | precision | sensitivity | specificity |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| A old oracle, all | 39 | 59 | 4 | 35 | 13 | 46 | 0.235 | 0.103 | 0.780 |
| B new oracle, all | 5 | 93 | 4 | 1 | 13 | 80 | 0.235 | 0.800 | 0.860 |
| **C new oracle, UNCHANGED only** | **5** | 59 | 4 | 1 | 13 | 46 | 0.235 | **0.800 on 5 positives** | 0.780 |

`n_contract_changed` = 34. Adversarial probes post-F1: **0 acceptances**
(`runs/binding_validation/task3_probes.json`, `runs/structural_binding/binding_probes.json`,
`runs/gate_sensitivity/crossrow.json` — 37 probes, 30 adversarial).
Invariants **16/16 PASS** (`runs/binding_validation/invariants.json`).

### 2.3 Evaluation-framework comparison — Table 3

Source: `runs/eval_framework_sensitivity/summary.json`; `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md`.

| quantity | value |
|---|---|
| cases scored / unscored | 106 / 0 |
| should-reject / should-accept | 67 / 39 |
| framework detected at < 0.5 | 31 / 67 |
| framework at strict < 1.0 | 44 / 67 |
| structural diagnostic detected | 54 / 67 |
| framework false-flags on paraphrase | 3 / 39 |
| disagreements | 59 |
| cross-row positive controls accepted | 2 of 8 — arm is **n = 2**, not 8 |
| structural diagnostic on same control | 1 of 5 canonical · 0 of 2 medical |

### 2.4 Parity gate — Table 4

Source: `runs/parity_gate_precision/summary.json`; `PARITY_GATE_PRECISION_REPORT.md`.

| quantity | value |
|---|---|
| fallbacks | 12 |
| justified / over-triggered | 12 / 0 — precision **1.00** |
| splits fired | prose 12 · table 4 · caption 1 (all 12 by construction) |
| Criterion J pre-registered at | commit `eeab489` |

### 2.5 Cross-domain and selection — Table 5

Source: `runs/binding_validation/{task1_verify,task2_binding}.json`;
`runs/medical_selector_control/summary.json`.

| quantity | value |
|---|---|
| medical JATS structured cells | 1,371 across 11 papers |
| tables parsed to cells / fallback | 22 / 1 (of 23) |
| papers with ≥1 table block | 7 of 11 |
| medical RETURNED numeric: structured / PDF-only / total | 2 / 1 / 3 |
| medical `bound` count | **0** |
| medical case distribution | `pdf_only` 11 · `not_bindable` 4 · `bound` 0 · `wrong_cell` 1 · n/a 10 |

Selection control, 19 medical papers:

| arm | metrics | results | mean fields | routing (biomed/cs_ml) |
|---|--:|--:|--:|--:|
| 1 legacy / natural | 9/19 | 7/19 | 8.32 | 3 / 16 |
| 2 legacy / **pinned** | 11/19 | 8/19 | 8.47 | 8 / 11 |
| 3 content_aware / natural | 14/19 | 13/19 | 8.84 | 8 / 11 |

**Selector isolated: metrics +16 pp, results +26 pp. Routing component: +11 pp / +5 pp.**

### 2.6 Corpus manifests

Source: `reproducibility/manifests/index.json`.

| corpus | papers | full-text | files hashed | full-text without local file |
|---|--:|--:|--:|--:|
| canonical60 | 60 | 34 | 34 | 0 |
| data_test8 | 8 | 7 | 7 | 0 |
| medical50_frozen | 50 | 19 | 19 | 0 |
| medical50_reacquired | 50 | 23 | 23 | 0 |

### 2.7 Environment pins

Source: `reproducibility/environment/environment.json`.

| item | value |
|---|---|
| Python | 3.10.18 · Windows 10 |
| qwen2.5:7b digest | `845dbda0ea48ed749caafd9e6037047a…` · Q4_K_M |
| BAAI/bge-m3 revision | `5617a9f61b028005a4858fdac845db406aefb181` |
| GPU | RTX 3050 6 GB Laptop · driver 581.86 · 6144 MiB |

---

## 3. All result / report files

Path prefix: `experiments/document_evidence_pipeline/`.

### 3.1 Current source of truth

| file | role |
|---|---|
| `CLAIM_LEDGER.md` | **authoritative for claim wording.** 20 claims, 26 rows |
| `EXPERIMENT_MATRIX.md` | authoritative for the 5 paper tables |
| `PARITY_GATE_PRECISION_REPORT.md` | Table 4 |
| `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` | Table 3 |
| `BINDING_VALIDATION_REPORT.md` | Tables 2, 5 (current, post-F1) |
| `MEDICAL_SELECTOR_CONTROL_REPORT.md` | Table 5b (current, post-control) |
| `EXTRACTION_FIDELITY_REPORT.md` | Table 1 pooled |
| `LATEX_ACQUISITION_REPORT.md` | Table 1 re-slices; LaTeX decision |
| `MEDICAL_REACQUIRE_REPORT.md` | acquisition of the 11 JATS papers |
| `DIAG_0549E2E9_REPORT.md` · `CONTEXT_BUDGET_REPORT.md` · `EXTRACTION_TRIAGE_REPORT.md` · `STAGE4_HARDENING_REPORT.md` · `ANCHOR_CENTRALIZATION_REPORT.md` · `RETRIEVAL_RECALL_REPORT.md` · `RESULTS_GATE_TUNING_REPORT.md` · `STAGING_VALIDATION_REPORT.md` | diagnostic / historical, not cited by the 5 tables |

### 3.2 Superseded wordings — do not quote from these

The reports below remain accurate about their own runs but contain claim wordings the
ledger later **withdrew**. Quote `CLAIM_LEDGER.md`, not these.

| file | superseded content | replaced by |
|---|---|---|
| `MEDICAL_RECHUNK_REPORT.md` | `metrics` +27 pp / `results` +31 pp presented as a selection result | ledger 14s WITHDRAWN → selector isolated +16 pp / +26 pp |
| `MEDICAL_SELECTOR_CONTROL_REPORT.md` | the confounded +26 pp / +32 pp figure it also reports | same — only its **isolated** column is quotable |
| `GATE_SENSITIVITY_REPORT.md` | Matrix C = 0.667 on 3 positives | superseded by the 3-corpus run: 0.800 on 5 positives |
| `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` | — the report itself withdraws "conventional aggregate evaluation misses structural evidence failures" | ledger 9s WITHDRAWN → the aggregation-dilution wording |
| `PARITY_GATE_PRECISION_REPORT.md` | — the report itself withdraws "the parity gate accurately identifies inferior representations" | ledger 11s WITHDRAWN |
| `STRUCTURAL_BINDING_REPORT.md` | pre-F1 binding results (asymmetric matcher) | `BINDING_VALIDATION_REPORT.md` post-F1 |
| `FINAL_REPORT.md` · `progress.md` · `STAGING_VALIDATION_REPORT.md` | "37/37 tests" — the actual suite is `tests/test_pipeline.py` 6 + `tests/test_anchors.py` 9 = 15 | ledger row 7c marks this UNSUPPORTED within the nominated sources |

---

## 4. Decisions already made, and why

| decision | rationale | recorded in |
|---|---|---|
| `latex_ingestion_enabled: false` | reaches numeric parity but regresses extraction: retained subset 5.82 vs 9.91 fields at the production 768 reservation | `LATEX_ACQUISITION_REPORT.md` |
| `EXTRACTION_OUTPUT_RESERVATION` stays **768** | 4096 was measured corpus-wide and rejected — viable but at 96 % VRAM, +47 % runtime | `LATEX_ACQUISITION_REPORT.md` Phase 5x |
| Production selection stays `legacy` | `content_aware` is staging-only; it silently degrades on legacy chunk schemas | `SELECTION_POLICY_REPORT.md` |
| `DEFAULT_PARITY_TOLERANCE = 0.0` | strict; no alternative threshold was evaluated and none is proposed | `PARITY_GATE_PRECISION_REPORT.md` |
| Invariant 16 is **route-agnostic** | invariants 14/15 keyed on `wrong_cell`/`pdf_only` and could not see 3 acceptances that routed through `not_bindable` | `BINDING_VALIDATION_REPORT.md` §F2 |
| Criterion J pre-registered **before** measuring | so the justification criterion could not be shaped by the result | commit `eeab489` |
| `ragas`/`langchain` kept **out** of `requirements.txt` | pulls ~40 packages, hard-pins `langchain-core`, breaks `langgraph`; only Table 3 needs it | `reproducibility/environment/requirements-table3.txt` |
| Ship no PDFs, no weights, no credentials | publisher copyright; weights pinned by digest instead | `reproducibility/manifests/` |

---

## 5. Open problems

1. **Provenance is not an independent axis.** `extraction_fidelity.py:378` filters the
   provenance denominator to strict survivors, and the predicate at line 345 can only fire
   when `hit_chunk` is set. Table 1 now labels it `provenance | strict survival`. Not a
   defect to fix — a labelling constraint to preserve.
2. **`bound` = 0 in both domains** on real extracted claims (0 of 5 canonical, 0 of 2
   medical). The cell-binding path is inert against LLM-extracted text; it engages only
   against synthetic probes. Reported as a finding, not resolved.
3. **Matrix C rests on 5 positives.** One mutant flipping moves sensitivity by 0.20.
4. **Cross-row arm is uninterpretable** at n = 2 after its positive control; both methods
   fail that control.
5. **Case-2 `not_bindable` residual**: a claim naming no recognised metric word evades
   binding entirely. Symmetric post-F1, so a structural limit rather than a bug.
6. **Five UNTRACEABLE quantities** carried in `EXPERIMENT_MATRIX.md` §UNTRACEABLE —
   canonical structured-cell total (console only), RETAINED pooled vb-lax (cannot be rebuilt),
   canonical ABSTAINED-side distribution (never persisted), pre-F1 per-class probe split
   (`task3_probes.json` overwritten), post-freeze Stage-6 behaviour (no run directory).
7. **Live `data/` has drifted** from the frozen medical corpus: it holds 19 full-text in the
   backup and in `medical50_frozen.json`, but the working `data/raw_metadata` was observed at
   17. The frozen run directories, not `data/`, are authoritative.
8. **Docker is untestable on this machine** — neither Docker nor WSL2 is installed.

---

## 6. The single next task

**Finish and commit the `reproducibility/` package.** It is the only incomplete deliverable.
Built so far: manifests (4), environment pins, frozen config, definitions, table→harness map,
expected results, and a deterministic verifier passing 36/36. Still missing:

1. `reproducibility/README.md`
2. `reproducibility/docker/Dockerfile` — must be marked **UNTESTED / NEVER BUILT**, since
   Docker and WSL2 are both absent here
3. A clean-checkout test of the deterministic probes, with the result appended to
   `EXPERIMENT_MATRIX.md`
4. `git add reproducibility/` and commit

---

## 7. Exact commands to continue

```bash
cd /c/Users/Praka/Downloads/researchgpt-pipeline

# 1. confirm the frozen state
git log -1 --format="%h %s" paper-freeze-v1        # -> f3b6768
git log --oneline paper-freeze-v1..HEAD | cat      # -> 5 post-freeze commits
git diff --stat paper-freeze-v1 -- src/ configs/   # -> 3 files, +53/-3 (6ae3d55 only)

# 2. re-run the deterministic verifier (no LLM, no GPU, no network)
python reproducibility/verify_deterministic.py     # expect: 36 passed, 0 failed, 0 skipped
                                                   # exit 0 iff all 36 ran and passed;
                                                   # a missing input is SKIPPED by name and
                                                   # exits non-zero. Inputs ship in
                                                   # reproducibility/artifacts/ (97 KB).

# 3. rebuild the corpus manifests if any run directory changed
#    HAZARD: only on THIS machine, which holds the full run tree. Three of the four
#    metadata sources and the PDF stores are gitignored, so anywhere else the rebuild
#    would produce a degraded manifest. The script now preflights and REFUSES (exit 2,
#    writes nothing) when a source is absent -- but if an older copy of it already
#    overwrote the shipped manifests:
#        git checkout -- reproducibility/manifests/
python reproducibility/manifests/build_manifests.py

# 4. test suites
python -m pytest tests/test_pipeline.py tests/test_anchors.py -q          # expect 15 passed
cd experiments/document_evidence_pipeline && python -m tests.test_pipeline_units   # expect 63 passed
```

Credential check before writing anything into `reproducibility/`:

```bash
git grep -InE "s2k-[A-Za-z0-9]{20,}" -- .    # must return nothing
```

---

## 8. Assumptions that must not be changed

1. **Seeded path**: `temperature 0`, `seed 42`. `extract_paper_fields` forces
   `max_workers=1` whenever a seed is set — do not raise it.
2. **`EXTRACTION_OUTPUT_RESERVATION = 768`** in production. 4096 is staging-only.
3. **`latex_ingestion_enabled: false`.**
4. **`DEFAULT_PARITY_TOLERANCE = 0.0`.**
5. **Anchor rule** `\d+\.\d+|\b\d{2,}\b` in `src/evidence/anchors.py` is the single source of
   truth, shared by the gate, Test 2 and every harness.
6. **Corpora never pooled**: canonical 60 / data_test 8 / medical 50 stay separate.
7. **6 GB VRAM is load-bearing**, not a footnote — qwen loads at ~5.0 GB and spills to CPU
   under contention.
8. **Mutation definitions, the parity rule, and evaluation criteria are frozen.** They must
   not be changed after seeing results.
9. **Every n below 10 carries its denominator inline**, never in a footnote.
10. **Ship no PDFs, no model weights, no credentials.**

---

## 9. The freeze

**Tag `paper-freeze-v1` → commit `f3b6768`** ("Claim ledger: every paper claim traced to a
number, a report, and a status").

> **Resolving the tag — read this before auditing the freeze.** `paper-freeze-v1` is an
> *annotated* tag, so `git rev-parse --short paper-freeze-v1` returns the tag **object**
> (`61c4ef1`), not the commit. That looks like the tag was moved off `f3b6768`. It was not.
> Confirm with `git log -1 --format=%h paper-freeze-v1` → `f3b6768`.

**What it covers:** the full `src/` pipeline, `configs/`, all 12 measurement reports, every
run directory under `experiments/document_evidence_pipeline/runs/`, and `CLAIM_LEDGER.md`.
Every number in the five paper tables was produced at or before this commit.

**Post-freeze commits — 5:**

| commit | touches `src/`? | effect on any table number |
|---|---|---|
| `6ae3d55` Fix three runtime defects found by running a search end to end | **yes** — 3 files, +53/−3 | none — acquisition robustness, Stage-6 synthesis, extraction wall-clock only |
| `acb89d8` Post-freeze: … track referenced harnesses | no — harness files and `.gitignore` only, despite a message that restates the `src/` work | none |
| `0ffcd88` Experiment matrix | no | none — assembly only |
| `29599e0` Correct the freeze note | no | none |
| `2b132ab` Relabel provenance as conditional | no | none — relabelling, nothing recomputed |

The entire `src/` divergence from the tag is `6ae3d55`: `semantic_scholar.py`,
`retrieval_aware.py`, `corpus_synthesis.py`. **No number in any table was regenerated after
the freeze.**

**Uncommitted at time of writing:** `reproducibility/`, `.claude/`, `.github/`.

---

## 10. Conclusions that existed only in conversation

Everything above is re-derivable from files. The items below were established during working
sessions and, until now, were written **nowhere in the repository**. Each was checked against
the tracked tree before being recorded here; the grep results are noted.

### 10.1 Docker is untestable on this machine — the container was never built

`docker --version` → *command not found*. `wsl --status` → *"The Windows Subsystem for Linux
is not installed."* GPU passthrough via `nvidia-container-toolkit` was therefore never
exercised. **No string matching `nvidia-container` exists anywhere in the tree.**

Consequence: any `Dockerfile` added to `reproducibility/docker/` must be marked
**UNTESTED / NEVER BUILT**. The supported reproduction route is the manual one in §7. A
container that claims to work and does not is worse than none.

### 10.2 `POST /api/search` replaces the corpus — never use it as a probe

`run_search_pipeline` runs Stages 1–4 against the **production config** and overwrites
`data/raw_metadata/collected_papers.json` and `data/processed/`. It is the endpoint the UI's
search box calls. It was once invoked as a smoke test to verify an acquisition fix; it began
replacing the 50-paper medical corpus with results for an unrelated query and downloaded 8
PDFs before it was stopped.

**Rule: back up `data/` before any run that touches Stage 1, and never call `/api/search` to
test something else.**

### 10.3 223 orphaned PDFs were deleted from `data/pdfs/`, without a backup

While cleaning up after that search, a filter of "not referenced by the current corpus" was
applied **without** the date restriction used earlier. It removed 223 PDFs belonging to
earlier, superseded corpora — not just the 8 from the aborted run. `data/` had been backed
up, but **`data/pdfs/` had not**, so those files are gone.

What survived, verified at the time:
- the active corpus is complete — all its full-text papers still have their files
  (`reproducibility/manifests/index.json` shows `n_full_text_without_local_file = 0` for
  every corpus)
- the PDFs the committed experiments depend on live in their own run directories:
  `runs/prodab-20260902T004416Z/canonical/pdfs` (32),
  `runs/medical_reacquire/pdfs` (12 hashed as JATS/PDF),
  `runs/secondcorpus-datatest/pdfs` (7)

No measurement is affected. **No file in the tree recorded this** — `git grep` for
`223 orphan` / `deleted 223` / `orphaned PDF` returns nothing; the incidental `223` and
`orphan` matches in the tree are a parity-gate row count, a sha256 substring, and an
unrelated usage in `CONTEXT_BUDGET_REPORT.md`.

### 10.4 The corpus backup lives outside the repository

`C:/Users/Praka/Downloads/rgpt_data_backup_1801/` holds `raw_metadata/` and `processed/`
captured before the search incident: **50 papers, 19 full-text** — matching every report and
matching `reproducibility/manifests/medical50_frozen.json`. It is the recovery source for the
`data/` drift noted in §5.7. **No string matching `rgpt_data_backup` exists in the tree.**

It is outside the repo and outside version control. If it is deleted, the 19-full-text
medical state survives only as `reproducibility/manifests/sources/medical50_frozen_collected_papers.json`
(metadata only — the PDFs would come from `data/pdfs/`).

### 10.5 The three post-freeze runtime bugs were invisible to the test suite

`6ae3d55` fixed an S2 `tldr` timeout, a Stage-6 `estimate_num_ctx` kwarg rename missed in the
3.2b change, and an embedding-model VRAM leak. **None was reachable from `tests/` or the
experiment suite** — 15/15 and 63/63 passed throughout. All three surfaced only by starting
the API server and running one real search end to end.

The Stage-6 bug is the sharpest case: `corpus_synthesis.py` had been raising `TypeError` on
*every* fresh run since the 3.2b rename, and it went unnoticed because
`data/processed/corpus_synthesis.json` predated the rename and no fresh search had been run.
A green test suite was not evidence the pipeline ran.

This is the same shape as the documented methodology claim that safety invariants can pass on
a materially broken system (`CLAIM_LEDGER.md` claim 7) — a third instance, from a different
layer, and **not currently counted among that claim's instances.**

### 10.6 Measured effect of the VRAM fix

On the same 6-paper search, clean extraction cache, same machine:
extraction **122.83 s/paper → 39.06 s/paper**; qwen placement went from 4.33 GB of a 5.12 GB
model resident with repeated eviction, to 4.22/5.00 GB (84 %) resident. The residual CPU
spill is environmental — roughly 1.6 GB of the 6 GB card is held by desktop applications.
The full run went from crashing at synthesis to completing in 499 s.

These figures are in the `6ae3d55` commit message and in a code comment in
`retrieval_aware.py`, but in **no report** and in none of the five paper tables. They are
wall-clock/placement numbers, not results, and should not enter the paper.
