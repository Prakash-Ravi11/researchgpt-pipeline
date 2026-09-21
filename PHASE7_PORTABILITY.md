# PHASE 7 — PORTABILITY CORE

First phase in product mode. Step A observes; Steps B onward implement.

| | |
|---|---|
| branch | `phase7-portability`, cut from `claude-code-verification` |
| rollback tag | `pre-phase7` → `83639a1` |
| directive commit | `83639a1` "directive: add product mode" (RESEARCH_DIRECTIVE.md alone) |
| code commits | `8d5b574` "phase7: portability code" · `b1d650a` "phase7: README" |
| clone used | `c:/Users/Praka/Downloads/researchgpt-fresh-clone-1` (round 1; no repair rounds needed) |

---

## STEP A — CONTEXT-WINDOW FACTS (observed, nothing changed)

### A1 — does any Ollama request pass `num_ctx`?

**Yes. Every one of them, unconditionally.** `call_ollama_json` builds
`options = {"temperature": temperature, "num_ctx": num_ctx}` at
`src/summarization/summarize.py:423` — there is no path through that function that omits it,
so Ollama's own default context length never applies to this product.

| call site | `num_ctx` it passes |
|---|---|
| `src/api/main.py:234` | function default, **8192** (`summarize.py:396`) |
| `src/api/main.py:294` | function default, **8192** |
| `src/summarization/summarize.py:528` | `256` (cache-priming probe, `:531`) |
| `src/summarization/summarize.py:737` | `estimate_num_ctx(...)` (`:742`) |
| `src/summarization/summarize.py:827` | `estimate_num_ctx(...)` computed at `:824` — **the production extraction path** |
| `src/summarization/summarize.py:889` | reuses the `num_ctx` from `:824` |
| `src/summarization/summarize.py:1204` | `CLUSTER_NAMING_NUM_CTX` (`:1210`) |
| `src/synthesis/corpus_synthesis.py:159` | `estimate_num_ctx(...)` (`:156`) |
| `src/synthesis/gap_analysis.py:157` | `NOVELTY_NUM_CTX` (`:162`) |

`estimate_num_ctx` (`summarize.py:324-336`) is
`((words(user)+words(system)) * 1.4 + output_reservation)`, rounded up to the next 512 and
**clamped to `[2048, 8192]`**.

### A2 — what Ollama applies when nothing is passed

- `ollama --version` → **0.34.1**
- `ollama show qwen2.5:7b` → **context length 32768**, quantization Q4_K_M
- `ollama show --parameters qwen2.5:7b` → **empty**: the modelfile sets no `num_ctx`, so the
  server default would apply.

Earlier in this session the label-assist harness (Phase 3) deliberately passed no `num_ctx`,
and `GET /api/ps` reported the loaded model at **`context_length: 4096`**. That is the
observed server default on this machine. It is moot for this product, because per A1 the
product always passes an explicit value.

### A3 — the two permitted model calls

Paper `1016250721201821285c39eba5ab77eddf80812e` (first of the Phase 5 development set),
prompt built by the production path at `n_results=50`:

| | |
|---|--:|
| chunks selected by `_select_legacy` | 93 |
| assembled words after `_assemble` | 2,500 |
| `user_content` words (incl. title) | 2,520 |
| prompt variant chosen | `cs_ml` (555-word system prompt) |
| `estimate_num_ctx(...)` → what production sends | **5120** |

| call | `num_ctx` | `prompt_eval_count` |
|---|--:|--:|
| 1 — exactly as the product sends it | 5120 | **2,562** |
| 2 — identical, `num_ctx` 8192 | 8192 | **6,096** |

**Production truncates this prompt by 3,534 tokens — 58 % of it never reaches the model.**

The mechanism is visible in the estimator: it assumes 1.4 tokens/word. This paper is in
Portuguese, which tokenises at ≈2.0 tokens/word for this model (6,096 tokens from 3,075 words),
so the estimate undershoots and the resulting `num_ctx` is too small for the prompt it was
computed for. Ollama then silently drops the overflow.

**This is n=1 and a non-English paper — likely a worst case, not a corpus rate.** What it
establishes is that the failure mode is real and reachable on production settings, not how
often it fires. Nothing was changed; this feeds Phase 8. Recorded in `/FINDINGS.md`.

### A4 — is `prompt_eval_count` in any log?

**No.** It appears nowhere in `src/`, nowhere in `scripts/`, and in no run artifact —
`meta_out` captures only `done_reason` and `elapsed_s`. The only file in the repository
containing it is the one Step A3 just wrote. **There are no historical calls to analyse**, so
the question "how many logged calls sit at or under the context length" cannot be answered
from existing data.

---

## STEP B — THE EDITS

| item | what | where |
|---|---|---|
| **B1** | `configs/config.example.yaml` created from the untracked `config.yaml`; the one secret field blanked — **`api_key`** (name only; no value was read into any output). Paths were already repo-relative (`data/…`), so nothing needed rewriting. `git check-ignore` confirms the example is **not** matched: `.gitignore:1` is the exact path `configs/config.yaml`, so no `.gitignore` change was needed and `config.yaml` stays ignored. `staging_config.yaml` untouched. | `configs/config.example.yaml` |
| | **What the code does when a key field is `""`:** `load_config` normalises empty to `None` (`src/config.py:47`); `semantic_scholar.py:95` sends the `x-api-key` header only when truthy, and `:141` waits **3 s** between calls instead of 1.2 s. Collection works unkeyed, just rate-limited. `S2_API_KEY` in the environment takes precedence (`src/config.py:45`). | |
| **B2** | Missing config → one line naming the copy command, then `sys.exit(1)`. No fallback to the example. | `run_pipeline.py:66-68`, `src/api/main.py:33-35`; message at `src/config.py:20-23` |
| **B3** | `resolve_device()` — returns the configured device, except a configured `cuda` becomes `cpu` with **one** warning when `torch.cuda.is_available()` is False. Placed in the existing shared module rather than a new one; **torch is imported lazily** so config loading never requires it. | `src/config.py:28-55` |
| | All six construction sites routed, one line each: | `semantic_scholar.py:156` · `build_index.py:50` · `retrieval_aware.py:290` · `summarize.py:1036` · `summarize.py:1072` · `gap_analysis.py:118` |
| | `build_index.py` resolves into the local `device` variable at `:50` so the downstream `if device == "cuda": model.half()` (`:58`) cannot fp16 a CPU model. **All six are in `src/`; none are in `experiments/`, which is untouched.** | |
| **B4** | `check_ollama()` / `check_ollama_from_config()` — probes `GET /api/tags`, names the exact fix (`ollama serve` or `ollama pull <model>`). | `src/preflight.py:13-56` |
| | `run_pipeline.py` exits non-zero on failure; the API logs a WARNING and **starts anyway**; live result at `GET /health`. No existing health endpoint existed, so one was added; no other endpoint changed. | `run_pipeline.py:70-73` · `src/api/main.py:38-43` · `src/api/main.py:100-105` |
| **B5** | `openpyxl>=3.1.0` added; `requirements-dev.txt` (pytest); `requirements.lock` with all 13 direct deps pinned exactly, **torch pinned to base `2.11.0` with the `+cu128` tag stripped**; `.python-version` = `3.10.18`. | `requirements.txt` · `requirements-dev.txt` · `requirements.lock` · `.python-version` |
| **B6** | `doctor.py` — eight checks, `PASS`/`WARN`/`FAIL`, non-zero on any FAIL. Reuses `resolve_device` and `check_ollama_from_config`; the reachability and model checks come from **one** probe. Never downloads the embedding model. | `scripts/doctor.py` |
| **B7** | README: prerequisites, CPU and CUDA install, Ollama setup, config copy, doctor, every verified entrypoint, `/health`, tests, fetched-vs-generated data, CPU-mode note. | `README.md` |
| **B8** | Three headless tests: CPU fallback (monkeypatched torch), missing-config message + non-zero exit (subprocess), preflight against an unreachable host. | `tests/test_portability.py` |

---

## STEP C — FRESH-CLONE VERIFICATION

**Clone round 1 — `researchgpt-fresh-clone-1`. No repair rounds were needed.**

| README step / command | result |
|---|---|
| `git clone --branch phase7-portability … researchgpt-fresh-clone-1` | **pass** — `b1d650a` checked out |
| `python -m venv .venv` | **pass** |
| `pip install torch --index-url https://download.pytorch.org/whl/cpu` | **pass** — `torch 2.14.0+cpu`, `cuda_available False` |
| `pip install -r requirements.txt` | **pass** (exit 0) |
| `pip install -r requirements-dev.txt` | **pass** (exit 0) |
| `cp configs/config.example.yaml configs/config.yaml` | **pass** |
| `python scripts/doctor.py` | **pass** — 7 PASS, **1 WARN**, 0 FAIL, exit 0. The WARN is the CPU-mode line, as required. |
| `pytest tests/` | **pass** — **18 passed** |
| **C4** doctor with `base_url` on an unused port (`127.0.0.1:1`) | **pass** — `FAIL  Ollama is not reachable at http://127.0.0.1:1 (URLError). Start Ollama, then retry:  ollama serve`, exit 1. Config restored afterwards. |

The full pipeline was not run and the embedding model was not downloaded in any clone.

---

## STEP D — DEVELOPMENT-MACHINE CHECK

| check | result |
|---|---|
| doctor passes with the GPU detected | **8 PASS / 0 WARN / 0 FAIL**, exit 0; `GPU available; embedding device resolved to 'cuda'` |
| resolved device is `cuda` at every routed site | `resolve_device('cuda') → 'cuda'`; all 6 `SentenceTransformer` sites route through it (5 inline, 1 resolved into the local variable above the call) |
| existing suite + the three new tests | **18 passed** (15 pre-existing + 3 new) |
| `config_after.json` identical to `config_before.json` | **True** — byte-identical |
| API starts, `GET /health` | `{"ok":true,"ollama_reachable":true,"model_present":true,"message":"Ollama reachable at http://localhost:11434; model 'qwen2.5:7b' is installed."}` — then stopped (PID 52272, port 8000 free) |

---

## STEP E — OUTCOME

PORTABLE. Report committed on `phase7-portability`, then `claude-code-verification`
fast-forwarded to it. No merge commit; no history rewritten.

---

## Remaining known limitations

1. **The clone is not a truly fresh machine.** It shares this machine's HuggingFace cache and
   its running Ollama, so two doctor lines — *embedding model cached* and *Ollama reachable /
   model installed* — passed for reasons a genuinely new machine would not reproduce. On a real
   fresh machine the first would be `WARN` (downloads on first run) and the second would `FAIL`
   until Ollama is installed and the model pulled. The install, config, device-fallback and
   test paths were genuinely exercised; the two service checks were not.
2. **`openpyxl` was genuinely missing from the development environment** — Phase 6 blocker #4
   was a live break here, not merely an undeclared dependency. Doctor caught it. I installed
   the project's own declared dependency and pinned it at 3.1.5.
3. **Doctor's em-dash renders as mojibake on a cp1252 console** (`running in CPU mode` line).
   Cosmetic, in code written this phase. Step C did not fail, so under this phase's constraint
   it goes to `/FINDINGS.md` rather than into code.
4. **Step A3 is one paper and a non-English one.** The 58 % truncation is real and reachable
   but is not a corpus rate.
5. **A Phase 6 statement corrected:** `inspect_corpus.py` has no `argparse` and no `__main__` at
   all — it is a helper module, not a script with a missing guard. The README says so.
6. `requirements.lock` pins what is installed here; it is not a resolved transitive lock.
7. The `ui/researchiq` branch was not touched, merged, or examined this phase.

---

## VERDICT

PORTABLE — fresh clone on CPU passes doctor and tests following the README verbatim
