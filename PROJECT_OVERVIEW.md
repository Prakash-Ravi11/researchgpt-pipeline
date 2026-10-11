# ResearchIQ: System Architecture, Remediations & Benchmark Overview

## 1. Executive Summary & Purpose

**Project name:** ResearchIQ (ResearchGPT Pipeline).

ResearchIQ is an evidence-bound scientific literature extraction and corpus intelligence workspace. It supports literature discovery and user-uploaded PDF corpora, extracts methods, datasets, metrics, and quantitative results, and produces cross-paper synthesis and category-by-dataset gap counts.

The reliability problems addressed are unsupported quantitative claims, competitor-baseline misattribution, missing source provenance, PDF table/prose binding asymmetry, and duplicated dataset identities. Source grounding establishes support within a paper; it does not independently establish the scientific truth of that paper.

**Source baseline:** `43296724502fb3e640aa90d3f94e20e77297c411` (`4329672`). The `main` documentation consolidation starts directly from this commit. `exp/phase11-binder` remains the historical backup at the same commit; implementation, tests, configuration, and reproducibility assets are preserved.

**Measured run:** `.run/corpus50_final4_20261010`. Its manifest records the starting commit `6a4ee9a`; the final source hashes for the gate, binder, entailment, schema, extraction, dataset resolution, and gap builder match the implementation committed in `4329672`, allowing for Git line-ending normalization. The subsequent evaluation measures these saved outputs rather than replaying the product pipeline.

**Current assessment:** the run demonstrates operational extraction, bounded semantic recovery, provenance checks, and canonical dataset resolution. It does not establish >99% factual precision or comprehensive production readiness. Quantitative coverage is sparse, topic separation is weak, and unresolved dataset labels remain.

## 2. Technical Stack & Environment

| Component | Verified implementation |
|---|---|
| Language/runtime | Python **3.10.18**. Use only `.\.venv\Scripts\python.exe` in this Windows checkout. |
| API and catalog | FastAPI/Uvicorn in `src/api/main.py`; the existing vanilla frontend is served at `/` on port 8000. |
| PDF/layout processing | PyMuPDF for text blocks, reading-order heuristics, figure extraction, and conservative table detection. Structured JATS/LaTeX paths exist when available and enabled. |
| Dense embeddings | `BAAI/bge-m3` through SentenceTransformers, with **1024-dimensional** dense vectors. The run configured CUDA for embeddings. |
| Vector store | Persistent ChromaDB, cosine similarity, and an HNSW index. The current extraction path uses dense queries filtered by paper ID. |
| Structured extraction | Local Ollama with `qwen2.5:7b`; strict ten-field JSON extraction and bounded repair/fallback behavior. |
| Entailment | Local `cross-encoder/nli-deberta-v3-small`, pinned to revision `fa2804872c3b4bd748f38c0185cc85775361e735`, CPU inference, and no implicit model download. |
| Evaluation environment | RAGAS **0.2.15**, BERTScore **0.3.13**, scikit-learn **1.7.2**. Saved BERTScore evaluation uses `distilbert-base-uncased`, without IDF weighting or baseline rescaling. |
| Persistence | JSON corpus/extraction/evidence artifacts, a persistent vector index, extraction caching, and resumable evaluation checkpoints. API job tracking is in memory. |

Important distinctions:

- BGE-M3 supports multiple retrieval modes as a model, but this pipeline does **not** implement a separate sparse/BM25 index or dense-sparse fusion. NLI is a verification cross-encoder, not a retrieval reranker.
- `all-MiniLM-L6-v2` has 384-dimensional vectors, but it is **not** the configured embedding model for this run. Do not combine that dimension with BGE-M3 or describe both as the active baseline. See the [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3) and [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
- Gemini API extraction and automatic Gemini-to-Qwen provider failover are **not implemented** in the audited pipeline. The existing fallback uses the local extraction engine.
- Production evidence grounding is enabled in the local `configs/config.yaml` and tracked example configuration. This is separate from Binder v2 routing: the observed default binder policy is still `legacy`; the verified corpus run explicitly selected `v2`.

## 3. Pipeline Architecture (5-Stage Closed-Loop Agent)

The five stages below are a conceptual architecture map. Executable stage numbering differs: `run_pipeline.py` runs collection, processing, embedding, summarization/evidence, then sanity checking; API orchestration also invokes figure extraction, corpus synthesis, and gap analysis. The feedback loop consists of bounded extraction repair/fallback and verification/abstention, not unlimited autonomous retries.

### Stage 1: Spatial Parsing

Discovery resolves paper metadata and available full-text representations. Uploads skip discovery, register the supplied PDFs, and derive initial titles from filenames; authors and years may remain unavailable.

PyMuPDF obtains text block bounding boxes and uses their positions for approximate reading order and table-caption association. Provenance-bearing chunks retain:

`C_i = {T_i, P_i, S_i, Delta_start, Delta_end, ID_block}`

Here `T_i` is extracted text, `P_i` is a page or structured node, `S_i` is a section, and the deltas are character offsets into the canonical extracted text. Paper ID, source, representation, and chunk ID accompany this record. Structured tables add row/header/value/caption information where parsing succeeds.

These are not raw PDF byte offsets. The emitted evidence does not provide a complete persistent word-by-word pixel coordinate map. Image-only PDFs need an OCR path before equivalent text-grounding guarantees can apply.

### Stage 2: Dense Indexing and Retrieval

Stage 3 of the executable pipeline embeds chunks, normalizes the vectors, and rebuilds the configured Chroma collection. Retrieval restricts candidates to the target paper. Selected passages are assembled into a bounded extraction input; the verified run used a 2,500-word budget.

The saved selection trace records legacy dense selection for 47 full-text papers and passthrough for three abstract-only papers. A content-aware selector also exists with section, numeric-anchor, and table heuristics, but it must not be presented as a measured dense-sparse hybrid or universally enforced section mask.

### Stage 3: Structured Inference

The extraction schema contains eight prose fields and two typed string arrays: `datasets` and `metrics`. Numeric metric identifiers such as `95HD` must not become measurements. Absolute scores and changes must retain their local quantity roles.

The implementation applies bounded conformance repair and targeted dataset fallback, caches usable extractions, and marks failures explicitly. With the saved seed configured, extraction uses a single worker to control Ollama slot/cache effects. The corpus is then clustered by method or topic embeddings and given category labels.

### Stage 4: Verification Gate

The gate filters extracted **datasets, metrics, and results**. It does not independently validate all free-form summary, inference, synthesis, or novelty-verdict text.

For eligible quantitative claims, admission combines atomic metric sanity, numeric range checks, structural table binding, source grounding, and attribution:

- **Table binding:** a measurement must resolve to the appropriate row/column when structured evidence requires binding. Conflicting or ambiguous bindings are withheld.
- **Prose fallback:** missing structured cells can be replaced by verified quantitative prose with valid source offset boundaries. Accepted exact prose is labeled `PROSE_GROUNDED`.
- **Semantic tier:** eligible paraphrases with lexical overlap **0.65-0.85** require NLI entailment confidence **>=0.90**, consistent quantities/roles and claim context, and author ownership. Accepted semantic recovery is labeled `ENTAILED`.
- **Ownership:** metric/result claims are classified as `OWN_PAPER`, `CITED_PAPER`, or `UNKNOWN`. Cited and unverified ownership are withheld from author-owned output.
- **Fail closed:** unavailable NLI weights, oversized pairs, unsupported claims, and unresolved bindings do not acquire fabricated support. Semantic entailment cannot override conflicting table evidence.

Direct and high-overlap matches use the fast tier; not every admitted claim requires NLI. Model confidence and heuristic attribution scores are not calibrated factual precision guarantees.

### Stage 5: Verified Ledger & Synthesis

The gate rewrites the filtered fields in `paper_summaries.json` and records admitted and withheld items in `paper_evidence.json`. Evidence records carry source spans, offsets, statuses, attribution, and rejection reasons. Corpus synthesis is a separate LLM operation over available extracted fields.

Before gap counting, dataset resolution applies registered aliases, regex rules, and normalized unit-cost Levenshtein similarity **>=0.88**. It protects editions, digits, and qualifiers, checks ambiguous alternatives, and preserves unresolved labels rather than forcing a merge. Each paper counts at most once per canonical dataset in its category.

The matrix shape is **K x N**, not a fixed `5 x N`. The measured run produced **2 x 96** cells with **87 empty candidate-gap cells**. Empty cells indicate absence from this extracted corpus; they are not proof of absence from the full literature or of scientific novelty.

## 4. Key Architectural Remediations (Phase 11 Audit Fixes)

1. **PDF Table Binding Fallback** — `src/evidence/gate.py` replaces immediate rejection of missing structured cells with source-grounded prose admission, followed by ownership and final checks. Binder v2 also masks metric-identifier digits and anchors quantity roles locally. The run returned **five quantitative result records**, including **two semantic recoveries**; **63 is the number of returned metric entries**, not recovered quantitative claims. Provenance is page/block/text-offset based, not a universal pixel-coordinate guarantee.
2. **NLI Semantic Entailment Gate** — `src/evidence/entailment.py` implements the local cross-encoder tier for the 0.65-0.85 overlap interval and >=0.90 entailment threshold. Two paraphrased results passed this tier with verified source offsets. This supports recovery under defined constraints; it does not prove that hallucinations are impossible.
3. **Fuzzy Canonical Dataset Normalization** — `src/synthesis/dataset_resolution.py` consolidates **113 distinct raw labels into 96 output labels** before matrix generation. **72 labels remain unresolved**, including descriptive/non-dataset noise, so these 96 labels must not all be claimed as independently verified benchmark identities.
4. **Atomic Schema Enforcement** — `src/evidence/schema.py` and `src/summarization/summarize.py` enforce/normalize atomic metric arrays; the gate checks entries separately, including legacy comma-separated inputs. All **50 output records** passed the array-structure check. The run still rejected **15 non-metric or unsupported descriptions** on sanity grounds; zero format/semantic rejection is not an established end-to-end result.

## 5. Comprehensive Benchmark & Evaluation Metrics (Corpus 50 Run)

Evidence sources are local, normally gitignored, artifacts:

- [Run manifest](.run/corpus50_final4_20261010/manifest.json): configuration, stage timings, source hashes, and regression-test snapshot.
- [Verification](.run/corpus50_final4_20261010/verification.json): output counts, provenance checks, canonical resolution, and remaining limitations.
- [Evaluation](.run/corpus50_final4_20261010/evaluation.json): metric settings, coverage denominators, per-paper errors, and clustering scores.

| Measurement | Observed result | Interpretation |
|---|---:|---|
| Corpus demographics | **50 papers: 47 full-text, 3 abstract-only** | Not a run of 50 full-text PDFs. |
| Provenance-bearing chunks | **20,733** | Parsed chunks, not 20,733 independently verified spatial measurements. |
| Regression tests | **387 passed** | Recorded run-time test snapshot; not a factual precision measurement or a new test execution for this documentation change. |
| Extraction/synthesis failures | **0 / 0** | Successful stage execution does not establish complete claim recovery. |
| Returned fields | **132 datasets, 63 metrics, 5 results** | Five quantitative result records across five papers; 45 papers returned no quantitative result. |
| Provenance validation | **249 / 249 valid** | Includes withheld evidence; not 249 independent correct accepted claims. |
| RAGAS Faithfulness | **1.0000**, 5 result records | Source-conditioned judge score; the two recovered records also averaged 1.0000. |
| BERTScore F1 | **0.9106** overall; **0.9096** recovered | Five overall and two recovered records. Similarity to evidence sentences, not factual accuracy or numeric correctness. |
| RAGAS Context Precision | **0.5789**, 49/50 papers scored | `LLMContextPrecisionWithoutReference` on passages actually supplied in extraction order, conditioned on the extracted response. It is not a gold-label assessment of the raw vector ranking before filtering. |
| Topic silhouette | **0.0665 Euclidean / 0.1271 cosine** | Existing topic labels across all 50 papers; weak separation, with cluster sizes 11 and 39. |
| Dataset resolution | **113 -> 96 labels; 72 unresolved** | Identity consolidation works, but substantial label quality work remains. |
| Metric sanity failures | **15** | Invalid or unsupported descriptions were withheld rather than forced into accepted metrics. |
| Gap matrix | **2 categories x 96 labels; 87 empty cells** | Corpus-relative candidate gaps, dependent on extraction and category quality. |
| Recorded elapsed time | **2,109.11 s run; 2,251.17 s including final verification** | About 35.2/37.5 minutes. Extraction/clustering/evidence dominated at 1,864.44 s. |

The evaluation finished with `complete_with_errors` and process exit code **1**: *Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG* exceeded the 600-second Context Precision limit. Its missing score was excluded from the mean, not converted to zero.

Quality qualifications that future agents must preserve:

- The RAGAS judge was `qwen2.5:7b`, also the extraction model (`judge_is_extractor: true`). This is not independent evaluation.
- Faithfulness checks source support, not external scientific truth. BERTScore is contextual similarity. Neither metric establishes >99% factual precision.
- The evaluation measures returned results; it does not measure recall against all quantitative results present in the papers. Five multi-statement result records are not a representative independent gold corpus.
- The historical verification records production grounding disabled at run time. Grounding was enabled after that run; do not rewrite historical artifacts to imply otherwise. The verified run itself explicitly enabled grounding and Binder v2.
- Topic/category quality, unresolved dataset noise, default legacy binder routing, and incomplete quantitative coverage remain operational considerations. Deterministic matrix counts do not eliminate these upstream limitations.

## 6. Project Structure & Key File Map

| Path | Responsibility |
|---|---|
| `run_pipeline.py` | Collection, processing, embedding, summarization/evidence, and sanity-check CLI. It does not invoke the later corpus synthesis/gap stages itself. |
| `src/orchestration/pipeline.py` | API search/upload orchestration, including figures, corpus synthesis, and gap generation. |
| `src/api/main.py` | Catalog API, upload/search jobs, health endpoint, and static frontend serving. |
| `src/processing/pdf_parser.py` | Representation processing and provenance-bearing chunk records. |
| `src/evidence/represent.py` | Canonical document blocks, spatial reading-order handling, and structured table association. |
| `src/embedding/build_index.py` | Dense embedding generation and persistent Chroma index rebuilding. |
| `src/summarization/retrieval_aware.py` | Paper-filtered dense passage selection, context budgets, and selection traces. |
| `src/summarization/summarize.py` | Structured extraction schema, bounded repair/fallback, caching, clustering, and evidence-gate integration. |
| `src/evidence/schema.py` | Evidence types/statuses and atomic metric normalization. |
| `src/evidence/gate.py` | Metric sanity/ranges, structural binding routing, prose/semantic grounding, attribution, and abstention. |
| `src/evidence/binder_v2.py` | Numeric metric-label masking, local quantity roles, and deterministic candidate/cell binding. |
| `src/evidence/attribute.py` | `OWN_PAPER`, `CITED_PAPER`, and `UNKNOWN` attribution rules. |
| `src/evidence/entailment.py` | Pinned local NLI cross-encoder inference; model/error/length failures return no semantic support. |
| `src/synthesis/dataset_resolution.py` | Regex, alias, and Levenshtein canonical dataset resolution. |
| `src/synthesis/gap_analysis.py` | Category-by-dataset counts and separate corpus-relative novelty comparison. |
| `src/synthesis/corpus_synthesis.py` | LLM-generated corpus/per-category synthesis. |
| `frontend/` | Existing catalog frontend served by the product API. |
| `configs/config.yaml` | Local gitignored production settings; evidence grounding enabled. Contains credentials: never print, commit, or copy its complete contents into documentation. |
| `configs/config.example.yaml` | Tracked setup template; does not encode secrets. |
| `configs/staging_config.yaml` | Staging settings; the binder router also consults its `binder_policy` entry, with environment override taking precedence. |
| `evaluate_pipeline.py` | Local evaluation CLI for RAGAS, BERTScore, provenance/input validation, and topic silhouette. |
| `requirements-evaluation.txt` | Local optional evaluation dependency pins. |
| `tests/test_evaluate_pipeline.py` | Local focused evaluator tests; 30 passed during evaluator implementation, separately from the historical 387-test snapshot. |
| `.run/corpus50_final4_20261010/` | Saved measured corpus and evaluation artifacts; not a versioned production database. |
| `reproducibility/`, `src/evaluation/`, `experiments/` | Historical measurement assets; preserve their code, gold data, scorers, and reports unless explicitly authorized to change them. |

**Version-control boundary:** `evaluate_pipeline.py`, `requirements-evaluation.txt`, and `tests/test_evaluate_pipeline.py` exist locally but are untracked at this documentation consolidation. They are deliberately not added or modified by the documentation-only commit. A fresh clone of `main` therefore needs a separately authorized inclusion of those files before the evaluation commands below are available. Local corpus outputs and model caches likewise must be provisioned separately.

## 7. Operational & Execution Guidance for AI Agents

Use the canonical interpreter for every project command. Do not create additional Python environments, runtime variants, diagnostic documents, or unrequested full-corpus replays. Read this overview and only the source/artifact needed for the current task. Preserve precise denominators, distinguish abstention from execution failure, and validate the desired outcome before changing implementation.

### Preflight and local service

Run from the repository root in PowerShell. Ollama must be reachable and have the configured model installed for extraction. Preflight does not download models.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B scripts/doctor.py

# Select the same binder as the verified run for this process and its children.
# This is separate from evidence_grounding.enabled in the configuration.
$env:RGPT_BINDER_POLICY = 'v2'
.\.venv\Scripts\python.exe -B -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`; `GET /health` reports live Ollama/model readiness. The catalog can start when Ollama is unavailable, but extraction endpoints cannot complete until it is ready. Do not start a second server on an occupied port or terminate unrelated Python/Ollama processes.

### Pipeline execution

The CLI performs a new collection/reacquisition and rebuilds configured outputs. Use it only when a new pipeline run is requested; it is not a command for opening the existing catalog.

```powershell
.\.venv\Scripts\python.exe -B run_pipeline.py --config configs/config.yaml
```

For later synthesis/gap stages after the CLI, when requested:

```powershell
.\.venv\Scripts\python.exe -B -m src.synthesis.corpus_synthesis --config configs/config.yaml
.\.venv\Scripts\python.exe -B -m src.synthesis.gap_analysis --config configs/config.yaml
```

The API upload/search orchestration already invokes those stages. Current uploads write shared corpus paths and rebuild the vector collection; they are not isolated append-only multi-tenant jobs. Job tracking is in memory and is lost on server restart.

### Evaluate saved outputs

These commands require the local untracked evaluation tooling described in Section 6. The exact saved BERT model must be supplied: the CLI default is `roberta-large`, which does not match this evaluation's DistilBERT settings.

```powershell
.\.venv\Scripts\python.exe -B evaluate_pipeline.py --run-dir .run/corpus50_final4_20261010 --bert-model distilbert-base-uncased --prepare-only
.\.venv\Scripts\python.exe -B evaluate_pipeline.py --run-dir .run/corpus50_final4_20261010 --bert-model distilbert-base-uncased --resume
```

Evaluation defaults to `<RUN_DIR>/evaluation.json`, checkpoints completed work, and validates input/settings fingerprints before resuming. It reads saved pipeline outputs rather than running collection/extraction. `--prepare-only` validates inputs/provenance without model scoring. The full Context Precision pass is much slower than claim-only evaluation: the recorded resume session lasted roughly 3 h 52 min.

Completed metric attempts, including recorded errors, are marked processed; `--resume` does not automatically retry the existing timeout. Do not edit checkpoint errors away, change scorer settings silently, or overwrite saved pipeline inputs. Increasing a timeout changes the fingerprint; use a distinct output path and an explicitly scoped evaluation plan if a retry is requested.

### Tests and change scope

Use focused checks relevant to the authorized change. For an explicitly requested full suite:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/ -q --tb=short -p no:cacheprovider
```

The evaluator's 30-test focused command, if its local test file is available:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_evaluate_pipeline.py -q --tb=short -p no:cacheprovider
```

For documentation-only work, verify Markdown, the staged path list, backup branch identity, and protected-file preservation; do not rerun model inference or the corpus. Commit only the explicitly authorized files. Never use a blanket add/cleanup that captures unrelated untracked work or deletes historical measurement assets. Keep this single overview aligned with new verified results, and label projections and unmeasured guarantees clearly.
