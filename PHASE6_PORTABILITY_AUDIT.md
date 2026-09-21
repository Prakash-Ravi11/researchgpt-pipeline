# PHASE 6 — PORTABILITY AUDIT

Read-only. Nothing was installed, run, downloaded, started or checked out. No branch was
switched; `ui/researchiq` was inspected with `git ls-tree` / `git show` / `git grep <branch>`
only. Nothing is fixed in this phase.

commit `64dd807` · branch `claude-code-verification` · 2026-09-21

---

## A. WHAT IS THE PRODUCT

### A1 — branches

| branch | last commit | purpose |
|---|---|---|
| **`claude-code-verification`** | 2026-09-21 `64dd807` | **The working pipeline.** Stages 1–6 in `src/`, the measurement programme in `experiments/`, the reproducibility package, Phases 0–5. |
| `ui/researchiq` | 2026-09-18 `cc58984` | **The UI.** Parked React workspace (`web/`, 38 files), a separate FastAPI service (`backend/`, 21 files), Supabase config, Windows launchers. |
| `master` | 2026-08-25 `af6de8e` | "initial checkpoint" — a single commit, 8 top-level entries, no `experiments/`, no `reproducibility/`. A stub, not a release. |
| `exp/parser-backend` | 2026-09-18 `92a7455` | experiment worktree (`C:/Users/Praka/Downloads/rgpt-exp-parser`) |
| `exp/stage-a` | 2026-09-18 `078577f` | experiment worktree (`C:/Users/Praka/Downloads/rgpt-stage-a`) |

**How far apart, and do they touch the same files?** `claude-code-verification` and
`ui/researchiq` diverge by **4 commits left / 1 right**. They are not disjoint — they modify
**the same five files** under `src/`:

```
src/api/main.py                      |  69 ++++++
src/collection/semantic_scholar.py   | 228 +++++++++++++-----
src/orchestration/jobs.py            |  37 ++++
src/summarization/retrieval_aware.py |   2 +-
src/synthesis/concern_questions.py   | 238 ++++++++++++++++++
5 files changed, 545 insertions(+), 29 deletions(-)
```

`src/summarization/retrieval_aware.py` is the live conflict: `ui/researchiq` carries
`n_results=3`, this branch now carries `n_results=50` from Phase 5. Any integration of the UI
must resolve that line deliberately, not by taking one side wholesale.

### A2 — every way to run the product

| # | how | exact command | entrypoint |
|--:|---|---|---|
| 1 | CLI pipeline | `python run_pipeline.py --config configs/config.yaml` | `run_pipeline.py:58` (`__main__`), default config at `run_pipeline.py:60`, loaded at `:63` |
| 2 | Product API + old vanilla UI at `/` | `uvicorn src.api.main:app --port 8000` | `src/api/main.py:27` (`app = FastAPI(...)`), config path `src/api/main.py:29` |
| 3 | Collection stage alone | `python -m src.collection.semantic_scholar --config configs/config.yaml --limit 20` | `src/collection/semantic_scholar.py:9` (documented invocation), `:19` config load |
| 4 | Sanity check | `python sanity_check.py` | `sanity_check.py:180` |
| 5 | Corpus inspector | `python inspect_corpus.py` | no `__main__` guard found — invoked as a script but has no guarded entrypoint |
| 6 | React workspace *(ui branch)* | `cd web && npm run dev` (Vite, :5173) | `web/package.json` → `"dev": "vite"` |
| 7 | Auth/SSE service *(ui branch)* | uvicorn against `backend/app/main.py` | `backend/app/main.py` |
| 8 | Windows one-click *(ui branch)* | double-click `start-researchiq.bat` | `start-researchiq.bat` → `scripts/start_researchiq.ps1` |

### A3 — is a second pipeline present?

**Not in this repo.** Searched all five branches by path for `data_50/`,
`scripts/run_novelty_and_comparison_tests.py`, `scripts/generate_evaluation_sheet.py` and
`configs/evaluation_50_config.yaml` — **zero hits on any branch**.

**No Gemini client anywhere.** A case-insensitive search across all five branches for
`google.generativeai`, `google-genai`, `gemini` and `GOOGLE_API_KEY` returns exactly one class
of hit: the literal token `gemini` inside a model-name regex at
`experiments/document_evidence_pipeline/gate_sensitivity.py:62`
(`(?:gpt|llama|qwen|mistral|mixtral|gemma|gemini|claude|bert|…)`). That is a pattern for
recognising model names in paper text, not an API client. No `GOOGLE_API_KEY`, no SDK import,
no network call to Google.

---

## B. WHAT BREAKS ON ANOTHER MACHINE

### B1 — hardcoded paths

| group | finding |
|---|---|
| **runtime product code** | **Zero.** `git grep -E "C:[\\/]\|/c/Users\|Praka\|Downloads[\\/]"` over `src/`, `configs/`, `scripts/`, `run_pipeline.py`, `sanity_check.py`, `inspect_corpus.py` returns nothing. The product code is path-clean. |
| **experiment harness** | **One.** `experiments/document_evidence_pipeline/diag_0549e2e9.py:246` — `Path("C:/Users/Praka/AppData/Local/Temp/claude/c--Users-Praka-Downloads-researchgpt-pipeline/…")`, a Claude scratch directory. |
| **docs / comments** | `scripts/start_researchiq.ps1:110` and `:623` on `ui/researchiq` mention `C:\Windows\Temp` and `C:\Users\Praka\miniconda3\python.exe` — both inside comment blocks explaining venv redirector behaviour. Not load-bearing; grep for non-comment `C:\` in that file returns only the comment line. |

Other `Praka` matches (`phase3_compose.py:1,14,136`, etc.) are the **name "Prakash"** in
docstrings, not paths.

### B2 — Python environment

- **No lockfile, no `pyproject.toml`, no `setup.py`, no `Pipfile`, no `.python-version`.**
- `requirements.txt` has 11 entries, **every one `>=` with no upper bound**:
  `requests>=2.31.0`, `sentence-transformers>=3.0.0`, `pyyaml>=6.0`, `tqdm>=4.66.0`,
  `pymupdf>=1.24.0`, `chromadb>=0.5.0`, `scikit-learn>=1.4.0`, `numpy>=1.26.0`,
  `fastapi>=0.110.0`, `uvicorn[standard]>=0.29.0`, `python-multipart>=0.0.9`.
- A **pinned** file exists but is scoped to the paper tables, not the product:
  `reproducibility/environment/requirements-repro.txt` (`requests==2.34.2`, `numpy==2.2.6`, …).
- **Python version assumed: 3.10.18** (`reproducibility/environment/environment.json`).
  `src/` uses PEP-604/585 syntax (`str | None`, `list[dict]`) in at least 8 modules, so **≥3.10
  is a hard floor** — and it is declared nowhere a packaging tool would read.

**Imported but not declared:**

| package | where | note |
|---|---|---|
| **`openpyxl`** | `src/reporting/corpus_table.py:110-112` | lazily imported; the XLSX export path raises `ModuleNotFoundError` on a fresh install |
| `pydantic` | `src/api/` | arrives transitively via `fastapi`; not pinned directly |
| `torch` | via `sentence_transformers` | arrives transitively; the CUDA/CPU build is therefore whatever pip resolves |

**Declared and genuinely used:** all 11 — `scikit-learn` is lazily imported at
`src/summarization/summarize.py:1096-1097`, `python-multipart` is required by FastAPI's
`UploadFile`. No dead entries found.

**Not declared and needed to run the tests:** `pytest`.

### B3 — hardware

`device` is read from config and passed straight through, with **no availability check**:

| site | code |
|---|---|
| `src/embedding/build_index.py:49` | `SentenceTransformer(model_name, device=device)` |
| `src/collection/semantic_scholar.py:156`, `:416` | same, `device=emb_cfg["device"]` |
| `src/summarization/retrieval_aware.py:289` | same |
| `src/summarization/summarize.py:1035`, `:1071` | same |
| `src/synthesis/gap_analysis.py:117` | same |

**With no GPU, does it fall back or crash?** It **crashes**, if the config says `cuda`. Nothing
consults `torch.cuda.is_available()` before constructing the model; torch raises at load time.
There is exactly one guarded site — `src/summarization/retrieval_aware.py:348`,
`if torch.cuda.is_available(): torch.cuda.empty_cache()` — which protects cache-clearing, not
model construction.

`src/embedding/build_index.py:58` (`if device == "cuda": model.half()`) means the CPU path runs
fp32 — correct but substantially slower.

6 GB VRAM is recorded as load-bearing, not incidental: `environment.json` carries
`gpu.vram_total_mib: 6144` with an explicit `ASSUMPTION` key.

### B4 — external services

| service | configured at | absent behaviour |
|---|---|---|
| **Ollama** | `configs/staging_config.yaml:25` `provider: "ollama"`, `:27` `base_url: "http://localhost:11434"`, model `qwen2.5:7b` | `call_ollama_json` (`src/summarization/summarize.py:394`) calls `resp.raise_for_status()`; on connection refusal requests raises, the retry loop (`max_retries=2`) exhausts, and the function **returns `None`**. Extraction then yields empty fields — a silent degradation, not a clear "Ollama is not running" error. |
| **BGE-M3** | `configs/staging_config.yaml:21` `model: "BAAI/bge-m3"` | downloaded by `sentence-transformers` from HuggingFace on first load (~2.2 GB). **Requires network on first run**; no vendored copy, no offline path, no documented pre-fetch step. |
| **Semantic Scholar** | `configs/staging_config.yaml:8` `api_key: null` | key is optional. `src/collection/semantic_scholar.py:95` sends `x-api-key` only when present; `:141` sleeps **3 s between calls without a key vs 1.2 s with one**. Works unkeyed, ~2.5× slower, and more exposed to 429s. |
| OpenAlex / arXiv / Europe PMC | — | no keys configured or required anywhere. |

### B5 — secrets in tracked files

**None.** `git grep` across `claude-code-verification`, `ui/researchiq` and `master` for
`s2k-…`, `sk-…`, `eyJ…` (JWT) and `sb_secret_…` returns nothing. The only credential slot in a
tracked file is `configs/staging_config.yaml:8`, which is `api_key: null`. On `ui/researchiq`,
`backend/.env` and `web/.env.local` are gitignored and only `.env.example` templates are
tracked. Nothing to redact; no values printed.

### B6 — what a fresh clone lacks

| item | status | size here |
|---|---|--:|
| **`configs/config.yaml`** | **gitignored (`.gitignore:1`) and untracked — and it is the default path for both entrypoints** (`run_pipeline.py:60`, `src/api/main.py:29`) | — |
| `configs/test_config.yaml` | gitignored (`.gitignore:2`), untracked | — |
| `data/pdfs/` | **fetched** (downloaded per paper) | 378 MB |
| `data/figures/` | generated | 438 MB |
| `data/chroma_db/` | generated (embedding index) | 36 MB |
| `data/processed/` | generated | 4.8 MB |
| `data/raw_metadata/` | **fetched** (API metadata) | 156 KB |
| `data_test/` | gitignored — **and it is what the only tracked config points at** | absent |
| `experiments/.../runs/` | generated; not needed to run the product | 530 MB |

The one tracked config, `configs/staging_config.yaml`, sets every path under `data_test/`
(`raw_metadata_dir: "data_test/raw_metadata"` …), which `.gitignore` excludes. So a fresh
clone has **no usable config**: the default one is absent, and the tracked one points into an
absent tree.

### B7 — OS assumptions

- **`claude-code-verification` product code is OS-clean.** A grep over `src/`, `scripts/`,
  `tests/`, `run_pipeline.py` for `.venv\Scripts`, `powershell`, `.bat`, `cmd.exe`,
  `os.name == "nt"`, `sys.platform == "win"` returns **nothing**. Paths are built with
  `pathlib.Path` throughout.
- **`ui/researchiq` is Windows-only to launch**: `start-researchiq.bat`, `stop-researchiq.bat`
  and `scripts/start_researchiq.ps1` (PowerShell, Windows job objects). No `.sh` equivalent
  exists on any branch. The underlying services are portable; only the launchers are not.

### B8 — README

**There is no root README on any branch.** The only READMEs are
`experiments/document_evidence_pipeline/README.md` and `reproducibility/README.md`, both
scoped to the measurement programme. `ui/researchiq` adds `RESEARCH_IQ_SETUP.md`.

So there are **no product setup steps to evaluate** — the failure is their absence, not their
content. A newcomer cloning this repo has no documented path to a running system, and would
have to infer: Python ≥3.10, `pip install -r requirements.txt`, plus `openpyxl`, plus an
Ollama install with `qwen2.5:7b` pulled, plus a `configs/config.yaml` that does not exist in
the clone and has no template.

### B9 — tests

| suite | files |
|---|---|
| product | `tests/test_anchors.py` (9 tests), `tests/test_pipeline.py` (6 tests) — 15 total per `PROJECT_STATE.md` |
| experiments | `experiments/document_evidence_pipeline/tests/test_pipeline_units.py` (63) |

**Could they run on a fresh machine with no GPU, no Ollama, no data? Yes — for `tests/`.**
They exercise pure functions (`chunk_text`, `clean_text`, `stringify/listify`,
`find_weak_extractions`, `cluster_papers`, anchor regex behaviour). Module-level imports pull
only `numpy`, `requests`, `yaml`, `tqdm` — no torch, no chromadb, no sentence-transformers at
import time, so nothing touches a GPU or a network service. The only gap is that **`pytest`
itself is not in `requirements.txt`**.

---

## C. RANKED BLOCKERS

| # | severity | effort | file:line | fix (one line, not applied) |
|--:|---|--:|---|---|
| 1 | **blocks run** | 0.5 h | `.gitignore:1`, `run_pipeline.py:60`, `src/api/main.py:29` | Track a `configs/config.example.yaml` and have the loaders fall back to it when `config.yaml` is absent. |
| 2 | **blocks install** | 2 h | repo root (no file) | Write a root README with prerequisites, install, Ollama/model setup and first-run steps. |
| 3 | **blocks run** | 1 h | `src/embedding/build_index.py:49` (and 5 sibling sites in B3) | Resolve `device` through a `torch.cuda.is_available()` check defaulting to `cpu`. |
| 4 | **blocks run** | 0.1 h | `src/reporting/corpus_table.py:110`, `requirements.txt` | Add `openpyxl` to `requirements.txt`. |
| 5 | **blocks run** | 0.5 h | `configs/staging_config.yaml` `paths:` block | Point the tracked config at a path that exists in a clone, or ship the `data_test/` skeleton. |
| 6 | **blocks run** | 3 h | `src/summarization/retrieval_aware.py` + 4 files (A1) | Reconcile the five `src/` files that `ui/researchiq` and this branch both modify before any UI integration. |
| 7 | degrades | 1 h | `requirements.txt` (all 11 lines) | Pin upper bounds or add a lockfile; `requirements-repro.txt` is the model. |
| 8 | degrades | 1 h | `src/summarization/summarize.py:394` | Distinguish connection-refused from a bad response and surface "Ollama unreachable" instead of `None`. |
| 9 | degrades | 0.5 h | `configs/staging_config.yaml:21` | Document the ~2.2 GB BGE-M3 first-run download and offer a pre-fetch step. |
| 10 | degrades | 2 h | `start-researchiq.bat`, `scripts/start_researchiq.ps1` (ui branch) | Add a POSIX launcher alongside the Windows one. |
| 11 | degrades | 0.1 h | `requirements.txt` | Add `pytest` (or a dev-requirements file). |
| 12 | degrades | 0.1 h | `requirements.txt` / packaging metadata | Declare `python_requires >= 3.10`. |
| 13 | cosmetic | 0.1 h | `experiments/document_evidence_pipeline/diag_0549e2e9.py:246` | Replace the absolute Claude temp path with a relative or parameterised one. |

**13 blockers · 6 block install or run · ~12 hours total.**

Nothing found is structurally un-portable. The product code has no hardcoded paths, no secrets,
no OS-specific constructs, and its tests run headless. Every blocker is configuration,
packaging or documentation — the two that actually stop a fresh machine are the missing
`config.yaml` and the missing README.

The two one-line fixes (#4 `openpyxl`, #13 the temp path) are recorded in `/FINDINGS.md` per
the read-only constraint and were not applied.

---

## VERDICT

PORTABLE WITH FIXES — 13 blockers, 6 block install or run, est 12 hours
