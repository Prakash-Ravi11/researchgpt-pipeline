# REPRODUCIBILITY PACKAGE

How to use the files in this directory. Written against `paper-freeze-v1` (`f3b6768`) plus
the post-freeze commits listed in `EXPERIMENT_MATRIX.md`; **no number in any paper table was
regenerated after the freeze.**

This is a **verification kit, not a one-command re-run of the paper.** It lets you confirm
that the deterministic half of the results follows from fixed inputs, and it tells you
exactly which half is not deterministic and by how much. Read §3 before you trust a PASS.

---

## 1. What this package reproduces, and what it does not

### Reproduces

| | |
|---|---|
| the **EXACT** block of `expected_results.json` | 36 checks: anchor counts, retrieval/survival rates, parity-gate decisions, probe outcomes, structural-cell counts, case counts, corpus identity |
| the frozen settings every table depends on | `config/frozen_config.json`, re-derived from source by the verifier (anchor regex, `EXTRACTION_OUTPUT_RESERVATION`, `DEFAULT_PARITY_TOLERANCE`, `latex_ingestion_enabled`) |
| the identity of the four corpora | `manifests/` — identifiers + SHA-256 per paper, so you can fetch and prove you hold the same documents |
| the mutation, probe and Criterion-J definitions | `experiments/definitions.json` — restated so you need not read harness code |
| which harness and run directory produced each table | `experiments/table_to_harness.json` |

### Does not reproduce

- **Anything downstream of generation.** Table 2 matrices A/B/C, Table 3 RAGAS scores and
  Table 5b field coverage all pass through `qwen2.5:7b`. They carry tolerances (§7) and need
  a full re-run with a GPU, Ollama and the pinned model — this package does not automate that.
- **The frozen run artifacts.** `experiments/document_evidence_pipeline/runs/` is gitignored
  (`experiments/document_evidence_pipeline/.gitignore:4`), 528 MB across 56 directories. It
  is **not in the repository**, so a clean clone cannot run 24 of the 36 checks. See §3.
- **The corpora.** No PDF, no XML, no abstract text is shipped — publisher copyright. You
  fetch from the manifests. §5.
- **Model weights.** Pinned by digest and revision, pulled at runtime. §2.3.
- **Credentials.** `config/frozen_config.json` sets `collection.api_key: null` by
  construction; the live key lives only in `configs/config.yaml`, which is gitignored.
- **The five UNTRACEABLE quantities.** §8. None feeds a table.

---

## 2. Prerequisites

### 2.1 Deterministic probes — no third-party packages at all

Python **3.10.18** (any 3.10.x should do) and `git`. That is the whole list.
`verify_deterministic.py` and `manifests/build_manifests.py` import only `json`, `re`, `sys`,
`hashlib` and `pathlib`. Verified: both run under a venv created with
`python -m venv --without-pip`, which has no site-packages at all.

### 2.2 Test suites — five pinned wheels plus pytest

```bash
python -m venv .venv-repro && .venv-repro/Scripts/activate        # Windows
# python -m venv .venv-repro && source .venv-repro/bin/activate   # POSIX
pip install requests==2.34.2 pymupdf==1.28.2 pyyaml==6.0.3 tqdm==4.70.0 numpy==2.2.6
pip install pytest        # NOT pinned in any requirements file — see below
```

`torch`, `sentence-transformers` and `chromadb` are in `environment/requirements-repro.txt`
but **neither test suite needs them**; both suites pass with the five wheels above. Install
the full file only for a generation re-run.

> **`pytest` appears in neither `requirements.txt` nor `requirements-repro.txt`.** Both pin
> runtime dependencies only. Install it separately. Verified with `pytest 9.1.1`.

### 2.3 Full re-run of the APPROXIMATE items

Ollama serving `qwen2.5:7b` at digest
`845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e` (Q4_K_M), `BAAI/bge-m3` at
revision `5617a9f61b028005a4858fdac845db406aefb181`, and `torch==2.11.0+cu128`. All three pins
are in `environment/environment.json`, with the command to verify the digest.

**Pass the bge-m3 revision explicitly.** The frozen harnesses called
`SentenceTransformer('BAAI/bge-m3')` without one, resolving `refs/main` at run time to the
revision above. If HF `main` has since moved, an unpinned run silently uses different weights.

### 2.4 The 6 GB VRAM assumption

**This is a load-bearing assumption of the measurement programme, not a footnote.** Every
APPROXIMATE number was produced on a single **NVIDIA RTX 3050 6 GB Laptop GPU** (driver
581.86, 6144 MiB), and the constraint shaped both the configuration and the results:

- `qwen2.5:7b` loads at ~5.0 GB. With an embedding model resident and roughly 1.6 GB of the
  card held by ordinary desktop applications, the model **spills to CPU and is evicted between
  papers**.
- `EXTRACTION_OUTPUT_RESERVATION` stays **768** for this reason. 4096 was measured corpus-wide
  and rejected: viable, but at 96 % VRAM and +47 % runtime (`LATEX_ACQUISITION_REPORT.md`
  Phase 5x).
- Post-freeze commit `6ae3d55` frees the embedder before Stage 4 on the same grounds:
  extraction went **122.83 → 39.06 s/paper**, and qwen placement from 4.33/5.12 GB with
  repeated eviction to 4.22/5.00 GB (84 %) resident. Those are wall-clock and placement
  numbers; they are in no table and are not results.

**What this means for you.** On **< 6 GB**, expect CPU spill and much longer wall-clock; the
run may not complete. On **≥ 12 GB**, expect faster wall-clock and identical field values —
the extra VRAM removes eviction, not variance. Wall-clock is hardware-bound and is *not* a
reproduction criterion: `expected_results.json` gives it a ±90 s/paper tolerance precisely
because the 122.8 → 39.1 band is placement, not correctness.

---

## 3. Read this before you trust a PASS

**`verify_deterministic.py` exits 0 when its inputs are missing.** Six of its inputs live
under `experiments/document_evidence_pipeline/runs/`, which is gitignored. In a clean clone
they are absent, the verifier prints `SKIP` (or nothing) for those sections, and reports:

```
EXACT checks: 12 passed, 0 failed          <-- exit code 0, and WRONG
```

The correct result is **36 passed, 0 failed**. A run reporting 12 has verified the anchor
rule, three config constants and the manifest counts — one third of the package — and has
silently skipped every result-bearing check.

**Acceptance rule: exit code 0 is not sufficient. Require `passed == 36` and `failed == 0`.**

```bash
python -c "import json,sys;d=json.load(open('reproducibility/verify_results.json'));ok=d['passed']==36 and d['failed']==0;print(('OK' if ok else 'INCOMPLETE'),d['passed'],'passed',d['failed'],'failed');sys.exit(0 if ok else 1)"
# clean clone -> "INCOMPLETE 12 passed 0 failed", exit 1
# artifacts in place -> "OK 36 passed 0 failed", exit 0
```

### The six artifacts the verifier needs

97 KB in total, out of 528 MB of run directories.

| file, under `experiments/document_evidence_pipeline/runs/` | bytes | feeds |
|---|--:|---|
| `parity_gate_precision/per_fallback.json` | 8,521 | Table 4 — 11 checks |
| `binding_validation/task3_probes.json` | 4,269 | Table 2 — 3 checks |
| `binding_validation/task1_verify.json` | 4,911 | Table 5a — 3 checks |
| `structural_binding/binding_probes.json` | 5,209 | Table 2 — 2 checks |
| `gate_sensitivity/crossrow.json` | 5,863 | Table 2 — 2 checks |
| `eval_framework_sensitivity/per_mutant.json` | 70,472 | Table 3 — 2 checks |

Restore them into those exact paths — they come from the authors' run archive, not from this
repository — and re-run. Verified: with these six files and nothing else added, a clean clone
goes from **12/12 to 36/36**.

### `build_manifests.py` is destructive in a clean checkout — do not run it

It rewrites `manifests/*.json` **in place, and exits 0 even when its sources are missing.**
Three of its four inputs are gitignored (`runs/`, `data_test/`, `data/pdfs/`). In a clean
clone it silently replaces the shipped manifests with a degraded set — `index.json` reduced to
a single corpus, `medical50_frozen.json` rewritten with `n_files_hashed: 0` and
`n_full_text_without_local_file: 19` — after which the verifier reports **5 passed, 4 failed**
against corrupted inputs that look exactly like real failures.

Run it **only** if you hold the full run directories and the local PDF store. Otherwise the
shipped manifests are the artifact; treat them as read-only. If you ran it by accident:

```bash
git checkout -- reproducibility/manifests/
```

`verify_deterministic.py` also rewrites `verify_results.json` on every run. That is by design
— but it means a degraded run overwrites the shipped 36/36 record. Restore it the same way:
`git checkout -- reproducibility/verify_results.json`.

---

## 4. Order to run things

Exact commands, in order. Steps 0–3 need no third-party packages.

```bash
# ---- 0. verify the freeze -------------------------------------------------
git log -1 --format=%h paper-freeze-v1        # -> f3b6768     CORRECT
# NOT this:
git rev-parse --short paper-freeze-v1         # -> 61c4ef1     the ANNOTATED TAG OBJECT
```

`paper-freeze-v1` is an **annotated** tag. `rev-parse` returns the tag object (`61c4ef1`),
which looks like the tag was moved off `f3b6768`. It was not. Always resolve with
`git log -1 --format=%h`.

```bash
# what has moved since the freeze
git log --oneline paper-freeze-v1..HEAD | cat
git diff --stat paper-freeze-v1 -- src/ configs/   # -> 3 files, +53/-3, from 6ae3d55 only

# ---- 1. clean clone -------------------------------------------------------
git clone --branch claude-code-verification <repo-url> researchgpt-pipeline
cd researchgpt-pipeline            # ~2.9 MB working tree, ~5 MB .git, ~1 s

# ---- 2. credential scan (must print nothing) ------------------------------
git grep -InE "s2k-[A-Za-z0-9]{20,}" -- .

# ---- 3. deterministic probes ---------------------------------------------
python reproducibility/verify_deterministic.py
#   six run artifacts in place : "EXACT checks: 36 passed, 0 failed"   <- the target
#   clean clone, artifacts absent : "EXACT checks: 12 passed, 0 failed" <- NOT a pass, see §3
# runtime: ~0.2 s

# ---- 4. test suites (needs the venv from §2.2) ---------------------------
python -m pytest tests/test_pipeline.py tests/test_anchors.py -q
#   -> 15 passed                     (~1 s)

cd experiments/document_evidence_pipeline && python -m tests.test_pipeline_units
#   -> 63 passed, 0 failed   IF a real PDF sits in pipeline/cache/
#   -> 62 passed, 1 failed   in a clean checkout — EXPECTED, see below   (~3 s)
cd ../..

# ---- 5. manifests: DO NOT RUN unless you hold the run dirs ----------------
# python reproducibility/manifests/build_manifests.py     # destructive, see §3
```

### The one expected unit-test failure in a clean checkout

`content_validate accepts a big synthetic pdf (no cached pdf present)` fails,
deterministically, for an environmental reason:

- the test prefers a real downloaded PDF from
  `experiments/document_evidence_pipeline/pipeline/cache/`, which is gitignored and therefore
  absent in a clean checkout;
- its fallback builds a synthetic 30-page PDF with PyMuPDF, intending to clear the harness's
  ≥ 20 KB pre-filter. It does not — PyMuPDF 1.28.2 compresses it to **16,610 bytes**, and
  validation returns `pdf_too_small_16610B`.

This is a defect in the *fallback branch of the test*, not in the pipeline, and it touches no
table. To get 63/63, drop any real PDF of ≥ 20 KB into
`experiments/document_evidence_pipeline/pipeline/cache/` and re-run. Verified.

**Treat `62 passed, 1 failed` with exactly that test name as the expected clean-checkout
result. Any other failing test is a real failure.**

---

## 5. Fetching the corpora from the manifests

The manifests ship **pointers and hashes, never content**. Per paper: DOI / arXiv id / PMCID,
acquisition status, representation type, which source accepted it, and the SHA-256 of the
retrieved file where one was held.

| manifest | papers | full-text | files hashed | representation |
|---|--:|--:|--:|---|
| `canonical60.json` | 60 | 34 | 34 | pdf 32 · abstract 26 · jats 2 |
| `data_test8.json` | 8 | 7 | 7 | pdf 7 · abstract 1 |
| `medical50_frozen.json` | 50 | 19 | 19 | abstract 31 · pdf 19 |
| `medical50_reacquired.json` | 50 | 23 | 23 | abstract 27 · pdf 12 · jats 11 |

`index.json` summarises all four. `n_full_text_without_local_file` is **0** for every corpus:
every full-text paper in the frozen state had its file and its hash.

To rebuild a corpus, for each paper with a full-text `representation_type`, fetch by the
identifier in the manifest — arXiv id via `arxiv.org/pdf/<id>`, PMCID via Europe PMC for the
JATS papers, DOI otherwise — then hash the result and compare against the `sha256` field.
Papers whose representation is `abstract` have no file to fetch and were never full-text.

Two corpora deserve care:

- **`medical50_frozen` and `medical50_reacquired` are two different frozen states of the same
  50 papers**, not a corpus and a copy. Table 5b was measured on the 19-full-text frozen state;
  Table 5a on the 23-full-text / 11-JATS reacquired state. Do not merge them.
- **The live `data/` directory is not authoritative and has drifted** from the frozen medical
  corpus. The frozen run directories and these manifests are. `medical50_frozen`'s metadata is
  shipped in full at `manifests/sources/medical50_frozen_collected_papers.json`, so that state
  survives independently of `data/`.

**Corpora are never pooled.** canonical 60 / data_test 8 / medical 50 stay separate in every
table.

---

## 6. `ragas` / `langchain` are deliberately not in `requirements.txt`

Only **Table 3** (the evaluation-framework comparison) needs them. Installing them alongside
the pipeline pulls langchain + langgraph + openai + datasets — about 40 packages — and pins
`langchain-core` hard, which downgrades it and breaks `langgraph`. Tables 1, 2, 4 and 5 import
none of it. Keeping it out of `requirements.txt` is why the other four tables install cleanly.

To reproduce Table 3, use a **separate virtualenv**:

```bash
python -m venv .venv-table3 && .venv-table3/Scripts/activate     # Windows
pip install -r reproducibility/environment/requirements-table3.txt
```

which pins `ragas==0.2.15`, `langchain==0.3.27`, `langchain-core==0.3.79`,
`langchain-community==0.3.31`, `langchain-ollama==0.2.3`. If you install it into the main
environment instead, the resolver conflict warnings you will see affect `langgraph` only,
which nothing here uses.

Table 3's judge is `qwen2.5:7b` via Ollama at `temperature 0`, `seed 42`, `num_ctx 8192`,
scored with RAGAS **Faithfulness**; detection threshold `< 0.5`, secondary marker `< 1.0`,
fixed before results were inspected. `NaN` never counts as a detection.

---

## 7. EXACT vs APPROXIMATE — telling a real failure from expected variance

The dividing line is **generation**. String matching, anchor counting, parity arithmetic and
the gate's decision logic contain no sampling. Everything that passes through `qwen2.5:7b`
does — and at 6 GB it also passes through placement decisions Ollama makes at run time.

### 7.1 Must reproduce bit-identically — any deviation is a real failure

| quantity | value | tolerance |
|---|---|--:|
| anchor regex in `src/evidence/anchors.py` | `\d+\.\d+` or `\b\d{2,}\b` | exact string |
| `EXTRACTION_OUTPUT_RESERVATION` · `DEFAULT_PARITY_TOLERANCE` · `latex_ingestion_enabled` | 768 · 0.0 · false | 0 |
| Table 1 anchor counts (all / table / prose / caption) | 6,530 / 5,405 / 965 / 160 | 0 |
| Table 1 PDF-path survival (vb-lax, vb-strict, bindable, bindable-table) | 0.986 / 0.699 / 0.168 / 0.089 | ±0.001, display rounding only |
| Table 1 LaTeX after parity fix (all / table) | 0.981 / 0.983 | ±0.001 |
| Table 4 parity-gate decisions | 12 justified / 0 over-triggered / precision 1.00 | 0 |
| Table 4 splits fired (prose / table / caption) | 12 / 4 / 1 | 0 |
| Table 4 conservatism block | deficit < 2 %: 4 · < 5 %: 5 · ≥ 20 %: 4 · LaTeX table ≥ PDF: 8 | 0 |
| Table 2 probe outcomes, post-F1 | 13 medical probes · **0** adversarial acceptances · 12 of 13 caught via `wrong_cell` | 0 |
| Table 2 invariant-16 suite | 37 probes · 30 adversarial · **0** acceptances | 0 |
| Table 5a structural cells, medical JATS | 1,371 across 11 papers · 22 tables parsed to cells | 0 |
| Table 5a `bound` rate | 0 of 5 canonical · 0 of 2 medical | 0 |
| Table 3 case count | 106 cases · 0 unscored | 0 |

The verifier asserts all of these. **Any difference here is a real failure** — they are
substring matches and arithmetic over fixed inputs; there is nothing for them to vary with.

One qualifier, carried in `expected_results.json` and repeated here because it is easy to
miss: **Table 3's positive control (2 of 8 cross-row controls accepted) is EXACT only if the
judge reproduces.** Verify the model digest first. If it differs, demote that one item to
APPROXIMATE.

### 7.2 Will vary — judge it against the tolerance, not the point value

| quantity | value | tolerance |
|---|---|---|
| Table 2 Matrix C sensitivity | 0.800 on **5** positives | ±1 count / ±0.20 rate |
| Table 2 Matrix A / B sensitivity | 0.103 / 0.800 | ±0.05 / ±0.20 |
| Table 3 framework detection | 31/67 at `< 0.5`; 44/67 at strict `< 1.0` | ±3 counts |
| Table 3 numeric perturbation | 6/19 at `< 0.5`; 18/19 strict | ±3 counts |
| Table 5b selector isolated | metrics **+16 pp**, results **+26 pp** | ±6 pp / ±1 count |
| Table 5b arm counts | metrics 9/19 → 11/19 → 14/19; results 7/19 → 8/19 → 13/19 | ±1 count |
| extraction wall-clock | 39.1 s/paper | ±90 s |

Why they vary: Matrix C's positives include `paraphrase_llm` mutants whose text qwen
generates. Every Table 3 value is a RAGAS Faithfulness score from a 7B judge, whose claim
decomposition differs run to run. Table 5b's field coverage is whatever qwen emits. Even at
`temperature 0` and `seed 42`, Ollama output moves with model digest, quantisation, context
length, GPU-vs-CPU placement and llama.cpp build.

**Two things to hold onto when reading a re-run:**

1. **Matrix C's denominator is the fragility, not the rate.** At n = 5 positives, one mutant
   flipping moves sensitivity by 0.20. A re-run at 0.600 or 1.000 is inside expected variance;
   it is not evidence about the gate.
2. **In Table 3 the qualitative finding is the reproducible part.** That strict `< 1.0`
   detection vastly exceeds threshold detection on numeric perturbation (18/19 vs 6/19) is the
   result. The exact counts are not.

### 7.3 The documented instance of downstream variance — ~1 pp on the medical arms

The three medical arms were run twice, independently. `MEDICAL_RECHUNK_REPORT.md` reported the
confounded figure as **+27 pp / +31 pp**; `MEDICAL_SELECTOR_CONTROL_REPORT.md`, re-running the
same three arms fresh, reported **+26 pp / +32 pp**.

**The endpoint counts were identical in both runs** — metrics 9/19 → 14/19, results
7/19 → 13/19. The ~1 pp difference is rounding of the same counts, not a different measurement.

That is the calibration to reason from. On the one occasion a generation-dependent arm of this
pipeline was actually re-run, it landed on the same counts, and the ±1 count / ±6 pp tolerances
above are considerably wider than the drift observed. If your re-run moves a count by 1, that
is inside tolerance and inside precedent. If it moves several, check your model digest before
you look at the code.

### 7.4 The decision rule

```
did the number come out of qwen2.5:7b, directly or through a judge?
  no  -> EXACT.        any deviation is a real failure. check inputs, then code.
  yes -> APPROXIMATE.  compare against the tolerance in expected_results.json.
                       inside tolerance  -> reproduced.
                       outside tolerance -> check model digest, quantisation, num_ctx and
                                            VRAM placement BEFORE concluding a code defect.
```

Never treat an APPROXIMATE deviation inside tolerance as a failure, and never treat an EXACT
deviation of any size as acceptable.

---

## 8. Known non-reproducible items

Five quantities from `EXPERIMENT_MATRIX.md` §UNTRACEABLE: each appears in a report or a run but
cannot be tied to both, so each is listed rather than dropped. **None of the five feeds any
table** — which is why they can be non-reproducible without weakening a result.

| quantity | why it cannot be reproduced | table depending on it |
|---|---|---|
| canonical total structured-cell count (1,986 across 13 papers) | exists only in terminal output of `structural_binding_measure.py`; no report carries it, and `BINDING_VALIDATION_REPORT.md` prints that cell as `—` | **none** — Table 5a leaves it blank rather than import a console log |
| RETAINED-subset pooled `vb-lax` (≈ 0.98 L / ≈ 0.99 P) | `LATEX_ACQUISITION_REPORT.md` states it "cannot be rebuilt from this artifact without re-running"; approximate by the author's own admission | **none** — Table 1b carries only macro / gt-wt |
| canonical ABSTAINED-side `structural_bind` case distribution | the canonical run persisted statuses for RETURNED items only; the distribution was never written | **none** — Table 5a gives the medical distribution and states that no canonical counterpart exists |
| pre-F1 medical probe per-class counts | `runs/binding_validation/task3_probes.json` was overwritten by the post-F1 re-run; no artifact holds the split | **none** — Table 2b leaves those cells empty and shows only the sourced totals (20 probes / 3 acceptances) |
| Stage-6 synthesis / `estimate_num_ctx` behaviour after `6ae3d55` | fixed after the freeze; no run directory exists for a post-fix synthesis measurement | **none** — deliberately absent from every table |

A reproducer who cannot obtain these has lost nothing a paper table rests on. Do not substitute
a fresh measurement for any of them: they would then be post-freeze numbers sitting beside
frozen ones.

---

## 9. Field note: the `tldr` field

The frozen corpora were collected with `tldr` in `semantic_scholar.FIELDS`, so the
`collected_papers.json` records — including
`manifests/sources/medical50_frozen_collected_papers.json` — carry a `tldr` key.

**That field was dropped post-freeze**, in commit `6ae3d55`. It is generated by a separate
Semantic Scholar backend, and requesting it alongside `limit=100` made the search endpoint time
out: `limit=100` with `tldr` → 500, `limit=100` without it → 200, a repeat query with it → 504.
`tldr` appeared exactly once in the repository — in `FIELDS` — and **nothing in `src/` ever read
it**.

Consequence for a reproducer: **a fresh collection will differ from the frozen manifests in that
field only.** No result changes, because no result ever consumed it. Each manifest carries this
in its `note_tldr` key so it is not later mistaken for corpus drift. Do not reintroduce the
field to make a diff clean.

---

## 10. Docker — UNTESTED / NEVER BUILT

`docker/Dockerfile` targets the CPU-only deterministic probes. **It has never been executed.**
Neither Docker nor WSL2 is installed on the development machine (`docker --version` → command
not found; `wsl --status` → "The Windows Subsystem for Linux is not installed"), so the image
has never been built, run, or seen by a daemon.

It is shipped as a starting point, not as a supported path. **The supported route is the manual
one in §4.** No GPU passthrough is claimed or configured: `nvidia-container-toolkit` was never
exercised, and the GPU-dependent runs (§2.3) have no container path here. A container that
claims to work and does not is worse than none — treat the file as a draft to verify before
trusting.

---

## 11. Files in this package

```
reproducibility/
  README.md                     this file
  verify_deterministic.py       36 EXACT checks; stdlib only; rewrites verify_results.json
  verify_results.json           last run: 36 passed / 0 failed  (the shipped record)
  expected_results.json         EXACT and APPROXIMATE blocks with per-item tolerances
  config/frozen_config.json     every setting the five tables depend on; api_key null by construction
  environment/
    environment.json            python, model digest, bge-m3 revision, GPU, CUDA
    requirements-repro.txt      runtime pins for a full re-run
    requirements-table3.txt     ragas / langchain, separate venv (§6)
  experiments/
    definitions.json            mutation classes, probe classes, Criterion J
    table_to_harness.json       table -> harness -> run directory
  manifests/
    index.json                  four-corpus summary
    canonical60.json            data_test8.json
    medical50_frozen.json       medical50_reacquired.json
    sources/medical50_frozen_collected_papers.json
    build_manifests.py          DESTRUCTIVE in a clean checkout — see §3
  docker/Dockerfile             UNTESTED / NEVER BUILT — see §10
```

---

## 12. Fastest path to a meaningful verification

```bash
git clone --branch claude-code-verification <repo-url> rgp && cd rgp
git log -1 --format=%h paper-freeze-v1                       # f3b6768
# restore the six run artifacts of §3 into experiments/document_evidence_pipeline/runs/
python reproducibility/verify_deterministic.py               # require 36 passed, 0 failed
```

Under a minute, no venv, no GPU, no network. Everything beyond that is either the test suites
(§4) or a generation re-run (§2.3, §7.2).
