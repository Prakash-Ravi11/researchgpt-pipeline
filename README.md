# ResearchGPT

A local, six-stage literature-extraction pipeline: collect papers → parse PDFs → embed and
index → extract structured fields with a local LLM → synthesise → check evidence. Everything
runs on your own machine. No paper text is sent to a hosted model.

---

## Prerequisites

| | |
|---|---|
| **Python** | **3.10.18**, the canonical project runtime pinned in `.python-version` |
| **Ollama** | running locally, with the configured model pulled |
| **Disk** | ~2 GB for the embedding model, plus whatever your corpus needs |
| **GPU** | optional. CUDA is used when present; without it everything still runs on CPU, **substantially slower** |

---

## Install

Use Python 3.10.18 to create the environment. In the existing Windows checkout, use
`.\.venv\Scripts\python.exe` for project commands and checks. Activate that environment
before using the shorter `python` and `pip` commands below. The optional historical
borderless environment is not the production runtime; its dependencies have not been
consolidated into this environment. See [current project state](PROJECT_STATE.md).

```bash
git clone <this-repo> researchgpt
cd researchgpt
python -c "import sys; assert sys.version_info[:3] == (3, 10, 18), sys.version"
python -m venv .venv
```

Activate it — `.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on
macOS/Linux — then install PyTorch for your hardware **first**, because the default wheel
differs by platform:

```bash
# CPU only
pip install torch --index-url https://download.pytorch.org/whl/cpu

# or, NVIDIA GPU with CUDA 12.8
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

Then the rest:

```bash
pip install -r requirements.txt
```

To reproduce the exact versions used during development, use `requirements.lock` instead of
`requirements.txt`. It pins torch to its base version with no `+cu` tag, so pick your torch
wheel with one of the commands above first.

For the tests:

```bash
pip install -r requirements-dev.txt
```

---

## Set up Ollama

Install Ollama from <https://ollama.com>, make sure it is running, and pull the model named in
your config:

```bash
ollama serve          # if it is not already running as a service
ollama pull qwen2.5:7b
```

---

## Create your config

`configs/config.yaml` is not in the repository — it is per-machine and gitignored. Copy the
tracked example and edit it:

```bash
cp configs/config.example.yaml configs/config.yaml
```

Every secret field in the example is blank. `collection.api_key` is a Semantic Scholar API
key: **optional**. Leave it empty and collection still works, just rate-limited (the code
waits 3 s between calls without a key instead of 1.2 s). It can also be supplied as the
`S2_API_KEY` environment variable, which takes precedence over the file.

---

## Check your environment

```bash
python scripts/doctor.py
```

One line per check, `PASS` / `WARN` / `FAIL`; it exits non-zero if anything is `FAIL`.
It verifies the Python version, that every required package imports, that the config exists
and parses, that the data directories can be created, whether a GPU is available, that Ollama
is reachable, that the configured model is pulled, and whether the embedding model is already
cached. **`WARN` is not a failure** — no GPU and an uncached embedding model are both `WARN`.
Doctor never downloads anything.

---

## Running it

### Full pipeline

```bash
python run_pipeline.py --config configs/config.yaml
```

Runs Stage 1 → 2 → 3 → 4 then the sanity check, stopping at the first failure. It refuses to
start if the config is missing or if Ollama is unreachable or the model is not pulled.

### API and the catalog UI

```bash
uvicorn src.api.main:app --port 8000
```

Then open <http://localhost:8000>. Unlike the CLI, the API **starts even when Ollama is
down** — the catalog stays browsable and only the extraction endpoints fail. The preflight
result is logged as a warning at startup and exposed live at:

```bash
curl http://localhost:8000/health
```

```json
{"ok": true, "ollama_reachable": true, "model_present": true,
 "message": "Ollama reachable at http://localhost:11434; model 'qwen2.5:7b' is installed."}
```

### Individual stages

```bash
# Stage 1 only — collect papers
python -m src.collection.semantic_scholar --config configs/config.yaml --limit 20

# Sanity check an existing corpus
python sanity_check.py --config configs/config.yaml
```

`inspect_corpus.py` is a helper module, not a runnable script — it has no command-line
entrypoint.

The React workspace and the auth/SSE service live on the `ui/researchiq` branch and are not
part of this branch.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

`tests/` is headless: no GPU, no Ollama and no corpus data are needed. `tests/test_portability.py`
covers the CPU fallback, the missing-config message and the Ollama preflight.

---

## Data

Nothing under `data/` ships with the repository; it is created as you run the pipeline.

| directory | how it gets there |
|---|---|
| `data/raw_metadata/` | **fetched** — paper metadata from the source APIs (Stage 1) |
| `data/pdfs/` | **fetched** — PDFs downloaded per paper (Stage 1) |
| `data/processed/` | generated — parsed text, chunks, extraction cache (Stages 2 and 4) |
| `data/chroma_db/` | generated — the embedding index (Stage 3) |
| `data/figures/` | generated — extracted figures (Stage 2) |

The embedding model (`BAAI/bge-m3`, ~2 GB) is downloaded to the HuggingFace cache on first use,
not into this repository. Doctor reports whether it is already cached but never fetches it.

---

## A note on CPU mode

Without a GPU the pipeline is correct but much slower — embedding is the dominant cost, and it
runs fp32 on CPU instead of fp16 on the GPU. A configured `embedding.device: cuda` is
downgraded to `cpu` automatically, with one warning, rather than crashing.
