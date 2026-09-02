# RETRIEVAL RECALL REPORT — does Stage 3 surface the result chunk?

Branch `claude-code-verification` · HEAD `73bf889` · 2026-09-02
Harness `experiments/document_evidence_pipeline/retrieval_recall.py` · artifacts `runs/retrieval_recall/`
Measurement only — retrieval, chunking and reranking are unchanged.

## What the Stage-3 → Stage-4 retrieval path actually is

Read before measuring: `src/embedding/build_index.py` (index build) and
`src/summarization/retrieval_aware.py` (`build_retrieval_aware_papers`, the only retrieval consumer,
called from `run_summarization` when `context_selection == "retrieval_aware"` — the config default and
what every evidence run used).

- **Index:** BGE-M3 (`BAAI/bge-m3`, 1024-d, `normalize_embeddings=True`) → one persistent ChromaDB
  collection, cosine (`hnsw:space=cosine`). Canonical run index: `researchgpt_papers`, 9,002 chunks.
- **Query time:** 5 **hard-coded generic** `TARGET_QUERIES` ("results findings outcomes performance
  evaluation", "dataset survey data collection measures instruments", …), each encoded with BGE-M3
  (`max_seq_length=256`), then `collection.query(n_results=3, where={"paper_id": pid})`. The union
  (≤ 15 chunk ids) is the context handed to the extractor — **but only when the paper exceeds 2,500
  words**; shorter papers use every chunk and retrieval never runs.
- **There is no reranker.** `src/retrieval/{dense,bm25,hybrid,reranker,factory}.py` exist **only as
  stale `__pycache__/*.pyc`** — no source files, and nothing imports `src.retrieval`. The config
  `retrieval:` block (`mode: hybrid_rerank`, `reranker_model: cross-encoder/ms-marco-MiniLM-L-6-v2`,
  bm25 params) **is dead config — no source file reads it.** So "BGE-M3 plus reranking" is BGE-M3
  dense only.

## Determinism

- **Retrieval: deterministic.** BGE-M3 `SentenceTransformer.encode` has no sampling; the ChromaDB HNSW
  query is deterministic for a fixed index. The harness ran the full pass **twice** — `rank_r1 == rank_r2`
  for **all 3,981 anchors** (`retrieval_deterministic: true` in `summary.json`). No temperature/seed
  applies.
- **Generation (Stage 4 LLM): NOT deterministic** — Ollama `qwen2.5:7b`, `temperature: 0.2`, no seed
  set in `call_ollama_json`. Out of scope here (this report is retrieval only), stated for completeness.

## Method

### 1. Anchors (self-supervised ground truth)

From the full-text chunks of the 34 canonical full-text papers, every token matching the gate's rule
`\d+\.\d+ | \b\d{2,}\b`, excluding: bare 4-digit years, numbers inside `[...]` (reference ids),
numbers immediately after "Section/Eq./Fig./Table/Appendix/v" (structure numbers), and `\d{4}\.\d{4,5}`
(arXiv-id fragments). Deduped per paper by `(value, section)`. The chunk the anchor is in is the
**target**; other chunks with the same value are **alternates** (a retrieval "hit" = target OR any
alternate in top-k — the value is what matters). When the first occurrence is outside a result-y
section, the target is reassigned to the first `{results, experimental_setup, discussion, conclusion,
method}` chunk that also contains the value.

**3,981 anchors** across 34 papers (2,645 prose, 1,336 table). Table cells capped at 60/paper
(deterministic, by position) so a handful of huge appendix tables don't dominate; 2,015 surplus table
cells were dropped by that cap. An anchor is "table" if its chunk `block_type == "table"` or its
±220-char window has ≥ 6 numbers and ≤ 1 result verb.

### 2. Query synthesis (deterministic, reproducible)

From the target's ±220-char window (`w = collapse_whitespace(window)`):
1. **metric** — first match of a fixed metric regex (`nDCG@k`, `recall@k`, `exact match`, `accuracy`,
   `precision`, `recall`, `dice`, `F1`, `BLEU`, `ROUGE`, `MAE`, `RMSE`, `MRR`, `pearson`, …).
2. **dataset** — first capitalised token near "dataset/benchmark/corpus/test set/questions", else the
   first of the paper's own extracted `datasets` (from `extraction_cache.json`) whose tokens appear in
   `w`.
3. **noun-ish backfill** — up to 6 tokens from `w`, in order of appearance, that are capitalised or
   ≥ 6 chars, not in a stop list, not already used.
4. `query = " ".join([metric?, dataset?, *nouns])[:12 tokens]`, then **every `\d{2,}` / `\d+\.\d+` and
   the anchor's own value string are deleted** — a real user query never contains the answer. Anchors
   whose query ends up < 2 tokens are dropped (0 here).

### 3. Retrieval

Each query → BGE-M3 encode (`max_seq_length=256`, normalised) → `collection.query(
query_embeddings=[v], n_results=min(n_chunks, 100), where={"paper_id": pid})`. Record the 1-indexed
rank of the target (and best alternate). This is the exact primitive `retrieval_aware.py` uses.

## 4. Recall

Hit = target **or** an alternate chunk with the same value in the top-k, per-paper dense query.

| slice | n | **R@5** | **R@10** | **R@20** | in production selection\* |
|---|---:|---:|---:|---:|---:|
| **ALL anchors** | 3,981 | **0.886** | **0.940** | **0.975** | 0.090 |
| location = table | 1,336 | 0.882 | 0.952 | 0.991 | 0.049 |
| location = prose | 2,645 | 0.888 | 0.933 | 0.967 | 0.111 |
| representation = JATS/XML | 311 | 0.942 | 0.974 | 0.997 | 0.277 |
| representation = PDF | 3,670 | 0.881 | 0.937 | 0.974 | 0.074 |
| source = arXiv | 3,193 | 0.874 | 0.932 | 0.972 | 0.052 |
| source = Europe PMC | 311 | 0.942 | 0.974 | 0.997 | 0.277 |
| source = OpenAlex | 101 | 0.832 | 0.911 | 0.941 | 0.000 |
| source = Semantic Scholar | 376 | 0.957 | 0.984 | 0.995 | 0.285 |
| **gate returns SOME quant** (18 papers) | 1,576 | **0.938** | 0.962 | 0.984 | 0.143 |
| **gate returns ZERO quant** (16 papers) | 2,405 | **0.852** | 0.925 | 0.970 | 0.055 |

\* *in production selection* = the target/alternate is in the actual set
`build_retrieval_aware_papers` hands the extractor (5 fixed queries × top-3 union; or ALL chunks if the
paper ≤ 2,500 words).

### The zero-return breakdown (the important one)

- Dense recall on ZERO-return papers: **R@5 0.852 / R@10 0.925 / R@20 0.970** — vs SOME-return
  **0.938 / 0.962 / 0.984**. A real **~8.6-point gap at k=5** that **closes to ~1.4 points by k=20**.
- So: **on the zero-return papers the result chunk IS retrievable — the dense index surfaces it 97 %
  of the time by k=20.** Low quantitative coverage on those papers is **not** primarily a
  dense-retrieval recall failure. §17's "survey-style papers genuinely report fewer measured results"
  is **not overturned** by this measurement — but see §"production selection" below for the part that
  *is* a retrieval-side problem.

### Production selection — where retrieval actually loses

Split by whether retrieval even runs:

| | anchors | in production selection | R@20 |
|---|---:|---:|---:|
| SHORT papers (≤ 2,500 w, 3 papers) | 81 | **1.000** | 1.000 |
| **LONG papers (retrieval runs, 31 papers)** | 3,900 | **0.071** | 0.975 |
| &nbsp;&nbsp;LONG ∧ gate returns ZERO | 2,389 | **0.049** | — |
| &nbsp;&nbsp;LONG ∧ gate returns SOME | 1,511 | **0.107** | — |

**On long papers the dense index can retrieve the result chunk at R@20 = 0.975, but the production
policy delivers only ~7 % of result chunks to the extractor** (4.9 % for zero-return papers, 10.7 % for
some-return). The 5 fixed generic queries × top-3 = ≤ 15 chunks, regardless of a 600–1,160-chunk paper,
and none of those queries targets a specific metric or dataset. The extractor never sees the chunk that
holds "nDCG@5 = 0.4502 on TREC RAG'24". **The retrieval-side deficit is the selection policy, not the
embedder** — and it is slightly worse on zero-return papers, so §17's assumption is *partially*
confounded by a policy gap.

## 5. Loss decomposition

Misses at k = 20: **98 / 3,981 (2.5 %)**.

| | count | meaning |
|---|---:|---|
| absent from the embedder candidate set (not in top-100) | **10** | dense retrieval never surfaced target **or** any alternate |
| surfaced by the embedder, ranked 21–100 | **88** | present in the dense candidate set, ranked out |

There is **no reranker**, so there is no "reranker dropped it" bucket — every miss is a dense-retrieval
ranking loss. Of the 10 "absent", all fall in two 500–640-chunk papers (`413a184de4`, `fef0393e`) and
correlate with **degenerate synthesized queries** (see #1, #5, #7 below — "For etrieval findings thesis
maintain correctness example"), i.e. a query-synthesis-quality ceiling more than an embedder blind
spot. Many of the 88 are near-hits: the alternate chunk ranks 34/63/73 — just outside k = 20.

## Ten worst misses

query / target chunk / top-3 retrieved instead (from `runs/retrieval_recall/worst_misses.json`):

1. **`413a184de4`** value `37.2` (prose, gate-zero) — target rank **none**, best-alt **99**/638
   query: `"accuracy Although overall retrieval several queries received Reviewing"`
   TARGET [discussion]: *"Although overall retrieval accuracy is high, several queries received a judge score of 0.0. Reviewing these zero-score cases reveals five systematic error patterns…"*
   got: [5.10 cross-agency…] *"…retrieval stays high and balanced across all five agencies (89–93% Recall@…"* · [experimental_setup] *"Recall@5 (Retrieval Hit): The percentage of queries…"* · [discussion] *"Table 17 Judge accuracy of full-page vs. tile-level retrieval…"*

2. **`413a184de4`** value `0.56` (prose, gate-zero) — target **97**, best-alt **63**/638
   query: `"Component systematic patterns visual textual reasoning engineering"`
   TARGET [discussion]: *"…five systematic error patterns in the model's visual–textual reasoning…"*
   got: [body] *"Keywords: Multimodal RAG Vision-Language Models…"* · [limitations] *"…visual-first retrieval, multimodal reasoning… are a viable foundation"* · [discussion] *"…incorrect component–dimension binding and symbol misalignment…"*

3. **`ef1e4a1671`** value `1877` (table, gate-zero) — target **92**, best-alt **92**/165
   query: `"Chess Clark Berner McCandlish Radford Sutskever Amodei"`  ← author-name run from a references chunk
   TARGET [conclusion/refs]: *"1. K. I. Roumeliotis, N. D. Tselikas… 'Llms in e-commerce: a comparative analysis of gpt and llama models…'"*
   got: [method] *"Tokenization was handled by AutoTokenizer."* · [results] *"RESULTS AND DISCUSSION"* · [results] *"Minimum chunk size: 12 characters (3 tokens)"*

4. **`ef1e4a1671`** value `33` (table, gate-zero) — target **85**, best-alt **85**/165
   query: `"Litwin Gray Chess Clark Berner McCandlish Radford"`  ← again a references chunk mis-tagged as an anchor
   TARGET [conclusion/refs]: same reference list as #3
   got: [results] *"RESULTS AND DISCUSSION"* · [discussion] *"Answer generation was reliable, achieving high relevancy and faithfulness."* · [method] *"Tokenization was handled by AutoTokenizer."*

5. **`413a184de4`** value `62.5` (prose, gate-zero) — target **82**, best-alt **34**/638
   query: `"For etrieval findings thesis maintain correctness example"`  ← window cut mid-word ("etrieval")
   TARGET [results]: *"On the 8-query PASS set, the agentic pipeline reaches 100% verdict accuracy. The Planner safely over-decomposes queries (averaging 8.6 steps per query)…"*
   got: [6. sample cases] *"6. Sample Cases"* · [5.7 compliance validation…] *"5.7. Compliance Validation on a"* · [discussion] *"7. Failure Case Analysis"*

6. **`93db4f9a32`** value `184` (prose, gate-SOME) — target **80**, best-alt **80**/236
   query: `"Evaluated peripheral overlap parameter parity call-graph dependency"`
   TARGET [abstract]: *"…the same functionality implemented for two different microcontroller platforms can be entirely incompatible at the hardware level…"*
   got: [method] *"• Vcall — Call-footprint similarity (Section IV-D3)"* · [intro] *"…CoCoMIC [31] reports +33.94% exact match from cross-file call-graph…"* · [method] *"…pattern set Πhw: GPIO_*, ADC_*, UART_*…"*

7. **`eaec7401af`** value `20.71` (prose, gate-zero) — target **none**, best-alt **73**/426
   query: `"BF16 ention execution chunks end-to-end pipeline experiments"`  ← "ention" — window boundary artifact
   TARGET [abstract]: *"Agentic retrieval-augmented generation (RAG) systems combine preprocessing, embedding, retrieval, memory access, context construction, generation, and vector-index updates…"*
   got: [abstract] *"Table 1: GPU end-to-end pipeline benchmark on two A100 GPUs and 32K chunks…"* · [abstract] *"We report stage-wise runtime for Load, Transform, Embed, Upsert, and Generate…"* · [abstract] *"Framework Embed Upsert Generate Total Chunks/s"*

8. **`f1f07a37d4`** value `1.75` (prose, gate-zero) — target **73**, best-alt **73**/1160
   query: `"This ational overhead comparable models particular importance"`  ← "ational" — boundary artifact
   TARGET [abstract]: *"Command A focuses on delivering competitive performance as efficiently as possible. With a serving footprint of just two A100s or H100s…"*
   got: [results] *"A strongly outperforms comparison models in its ability to adhere to dialect."* · [results] *"Figure 5: Head-to-head human evaluations against comparable models."* · [refs] *"This technical report was written with the assistance of the models…"*

9. **`93db4f9a32`** value `815` (prose, gate-SOME) — target **72**, best-alt **72**/236
   query: `"Evaluated overlap parameter parity call-graph dependency structural"`
   TARGET [abstract]: same abstract sentence as #6
   got: [method] *"• Vcall — Call-footprint similarity (Section IV-D3)"* · [method] *"2) Vsig — Parameter Count Parity…"* · [method] *"TABLE VII PER-MODEL RESULTS. τ*: PLATEAU THRESHOLD…"*

10. **`413a184de4`** value `37.2` (prose, gate-zero) — target **57**, best-alt **57**/638
    query: `"Recall@5 Recall unseen agency essentially matching distribution performance"`
    TARGET [conclusion]: *"On the 4,056-pair five-DOT benchmark… the adopted ColNomic-3B retriever reaches 92.69% Recall@5—55.90 pp above t[he baseline]"*
    got: [5.2 overall end-to-end…] *"Agency N Zero-shot Recall@5 (%)"* · [intro] *"Recall@5: 45.99%"* · [intro] *"Recall@5: 58.02%"*

Pattern: the misses are dominated by (a) **degenerate synthesized queries** — window boundaries cutting
words ("etrieval", "ention", "ational"), author-name runs from references chunks that were wrongly
kept as anchors (#3, #4) — and (b) **near-duplicate distractor chunks** — the same paper repeats
"Recall@5: NN%" in five places (#10), so the specific one is ranked ~57 among its own near-clones. Both
are properties of the corpus/query, not an embedder defect: R@20 is still 97.5 %.

## Verdict

- **The BGE-M3 dense index is not the bottleneck.** Given a targeted query it surfaces the
  result-bearing chunk at **R@5 0.886 / R@10 0.940 / R@20 0.975**, equally for table and prose,
  deterministically. Even on the zero-return papers, R@20 = 0.970.
- **The retrieval-side problem is the production selection policy**, not the embedder: on the 31 long
  papers where retrieval runs, `build_retrieval_aware_papers` (5 fixed generic queries × top-3, ≤ 15
  chunks total, no per-metric/per-dataset query, no reranker) delivers only **~7 %** of result chunks
  to the extractor (4.9 % on zero-return papers). This is the "retrieval fails to surface the chunk"
  case, and it is real and systematic — but it lives in the selection policy / dead reranker config,
  not in Stage 3's index.
- **§17 caveat:** the low quantitative coverage on zero-return papers is *partly* confounded — those
  papers' result chunks reach the extractor only 4.9 % of the time — so "survey papers just have fewer
  results" cannot be fully separated from a policy deficit without first fixing the selection policy
  and re-measuring. The dense recall gap itself (8.6 pts @ k=5, 1.4 pts @ k=20) is small.
- **Measurement caveat:** the deterministic query synthesis is weak for anchors not adjacent to a
  metric name (garbled queries in the worst-miss list); a stronger query would likely raise R@k above
  what is reported here, which strengthens rather than weakens the "embedder is fine" conclusion.

### Reproduce

```
python experiments/document_evidence_pipeline/retrieval_recall.py
```
Artifacts: `runs/retrieval_recall/{anchors.json, worst_misses.json, summary.json}`.
Index: `runs/prodab-20260902T004416Z/canonical/chroma_db` (BGE-M3, 9,002 chunks). No seed needed —
retrieval is deterministic (verified over 2 runs).
