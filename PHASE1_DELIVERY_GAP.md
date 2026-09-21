# PHASE 1 — RETRIEVAL DELIVERY GAP

Question: is `RETRIEVAL_RECALL_REPORT.md:80` (R@10 = 0.940 vs production delivery = 0.090) one
real failure or two incomparable numbers?

Nothing was fixed, no pipeline or experiment was re-run. All numbers below are recomputed
read-only from the existing artifact `runs/retrieval_recall/anchors.json` (3,981 records) and
`runs/prodab-20260902T004416Z/canonical/processed/chunks.json` (9,002 chunks).

---

## A. ARE THEY THE SAME MEASUREMENT?

### A1. R@10 = 0.940

| | |
|---|---|
| **query set** | **3,981 distinct synthesized queries — one per anchor**, each built from the ±220-char window *around that anchor* (`RETRIEVAL_RECALL_REPORT.md:52-66`): a metric-regex match, a dataset name, then noun-ish backfill, capped at 12 tokens, with every `\d{2,}`/`\d+\.\d+` and the anchor's own value string deleted (`:64-66`). |
| **what counts as relevant** | The target chunk **or** any alternate chunk containing the same value, in the top-k (`:76`). Not "the chunk a reader would want" — "any chunk carrying this number". |
| **unit** | one numeric anchor (a token matching `\d+\.\d+|\b\d{2,}\b`, deduped per paper by `(value, section)`, `:38-44`) |
| **corpus** | canonical 60, the 34 full-text papers (`:38`) |
| **n** | 3,981 anchors (2,645 prose, 1,336 table); 2,015 surplus table cells dropped by a 60/paper cap (`:46-48`) |
| **retrieval call** | `collection.query(n_results=min(n_chunks, 100), where={"paper_id": pid})` (`:70-72`) |

### A2. Production delivery = 0.090

| | |
|---|---|
| **query set** | **5 fixed generic queries, per paper, identical for every anchor in it** — `_GENERIC_QUERIES` at `src/summarization/retrieval_aware.py:35-41` ("problem statement research gap motivation background", "method approach study design procedure participants sample", "results findings outcomes performance evaluation", "dataset survey data collection measures instruments", "limitations discussion conclusion implications future work"). None names a metric or a dataset. |
| **what counts as relevant** | identical criterion — target **or** any alternate in the delivered set (`retrieval_recall.py:228`) |
| **unit** | identical — the same anchor records |
| **corpus** | identical — same 34 papers |
| **n** | identical — the same 3,981 rows |
| **retrieval call** | `n_results=3` per query, union into a set (`retrieval_aware.py:252-256`), so ≤ 15 chunk ids per paper regardless of paper size |

### A3. Are these computed over the same records?

**Yes.** Both are fields on the *same row* of the same artifact:
`runs/retrieval_recall/anchors.json` carries `rank_r1` / `best_alt_rank_r1` (the R@k numbers) and
`in_production_selection` (the delivery number) on every one of the 3,981 records. I verified the
join by recomputing both columns from that file: ALL R@10 = 0.940, production = 0.090 — matching
`RETRIEVAL_RECALL_REPORT.md:80` exactly.

Same corpus, same index, same chunk store, same unit, same relevance criterion, same n. They are
**not** two populations. Section C is therefore possible and is answered below.

They differ on exactly **two** dimensions, and both are properties of the production policy
itself, not confounds:

1. **Query specificity.** R@10 asks a question synthesized from the text surrounding the answer;
   production asks 5 generic questions that never name a metric or dataset.
2. **Budget allocation.** R@10 gives each anchor its own 10-chunk window. Production gives the
   *whole paper* one ≤15-chunk set, shared across all its anchors (median 130 anchors/paper).

**One limit on the interpretation, stated because the directive forbids blurring it.** R@10 =
0.940 is a **ceiling measured under an anchor-aware query**. The query is built from the window
around the target; the value itself is stripped, but the metric name, dataset name and
surrounding nouns are not. Production cannot construct that query without already knowing where
the answer is. So 0.940 is "the index can find it if you ask well", not "a better policy would
deliver 94 %". The report says as much at `:222-225`. The gap below is real; 0.940 is not a
reachable target.

---

## B. WHERE DOES THE DROP HAPPEN?

### B4. Traced path, retriever candidates → text in the LLM prompt

| # | step | file:line |
|--:|---|---|
| 1 | `run_summarization` reads `max_context_words` from config | `src/summarization/summarize.py:1285` |
| 2 | dispatches to retrieval-aware selection when `context_selection == "retrieval_aware"` | `src/summarization/summarize.py:1286-1288` |
| 3 | `build_retrieval_aware_papers(config, max_context_words)` | `src/summarization/retrieval_aware.py:275` |
| 4 | per paper, `total_words = sum(len(c["text"].split()) …)` | `src/summarization/retrieval_aware.py:310` |
| 5 | **short-paper branch** — `total_words <= max_words` → passthrough, *every* chunk assembled | `src/summarization/retrieval_aware.py:312-314` |
| 6 | **long-paper branch** — `_select_legacy(...)` (production default; config has no `selection:` block) | `src/summarization/retrieval_aware.py:320`, mode default at `:47` |
| 7 | 5 generic queries, `n_results=3` each, union into a set | `src/summarization/retrieval_aware.py:252-256` |
| 8 | keep paper chunks whose id is in that set, sort by `chunk_index` | `src/summarization/retrieval_aware.py:257-258` |
| 9 | `_assemble` — word budget, truncates mid-chunk | `src/summarization/retrieval_aware.py:263-273` |
| 10 | assembled text → `extract_paper_fields` → the prompt | `src/summarization/summarize.py:1296` |

### B5. What reduces the candidate set at each step

| step | reduction | value | file:line | binding? |
|---|---|---|---|---|
| 7 | per-query top-k | `n_results=3` | `retrieval_aware.py:253` | **yes** |
| 7 | number of queries | 5 fixed | `retrieval_aware.py:35-41` | **yes** |
| 7 | union dedup (set) | ≤ 15 ids, fewer when queries overlap | `retrieval_aware.py:252,256` | **yes** |
| 5 | short-paper bypass | `max_words` = 2500 (`configs/config.yaml:37`, `reproducibility/config/frozen_config.json:14`) | `retrieval_aware.py:312` | n/a — 3 of 34 papers |
| 9 | word budget | 2500 words | `retrieval_aware.py:266-271` | **no — see below** |
| — | score threshold | **none exists** | — | — |
| — | reranker | **none exists** — `src/retrieval/*.py` are stale `.pyc` only, config block is dead | `RETRIEVAL_RECALL_REPORT.md:21-26` | — |

**The word budget never binds in the legacy path.** Recomputed from `chunks.json`: canonical
chunks are **mean 30 words, median 13, p90 84, max 220**. Fifteen median chunks ≈ 195 words;
fifteen mean chunks ≈ 456 words — against a 2500-word allowance. The selection policy delivers
roughly **18 % of the context budget it is already permitted**, and `_assemble` truncates
nothing. Step 9 is inert; step 7 is the whole story.

**One further reduction is not in the 0.090 number at all.** `retrieval_recall.py:210-228`
computes `in_production_selection` as membership in the ≤15-id union *before* `_assemble` runs.
It happens not to matter here, since the budget does not bind — but 0.090 is structurally an
**upper bound** on delivery, not a measurement of the assembled text.

### B6. Does the arithmetic account for 0.940 → 0.090?

**Yes, and the accounting is almost entirely budget, not relevance.**

Restricting to the 31 long papers where retrieval actually runs (the 3 short papers pass through
at delivery 1.000 and R@10 1.000, and only dilute):

| quantity | value |
|---|--:|
| long-paper anchors | 3,900 |
| long-paper R@10 | 0.938 |
| long-paper observed delivery | **0.0713** |
| chunks per long paper | min 67 · **median 223** · max 1,160 · mean 284 |
| anchor-weighted uniform null, 15/N | **0.0681** |
| observed ÷ null | **1.047×** |
| papers delivering *below* the uniform null | **21 of 31** |

The null is: pick 15 chunks per paper *at random* and ask what fraction of anchors land in them.
That predicts **0.068**. The production policy — BGE-M3 dense retrieval against 5 hand-written
topical queries — achieves **0.071**.

So of the 0.867 absolute drop from 0.938 to 0.071, the ≤15-chunk-per-paper budget against a
median 223-chunk paper accounts for **~100 %**. Query relevance contributes a 1.047× factor,
about **0.003 absolute**, and on 21 of 31 papers it is *worse than random*.

**Nothing is unaccounted for.** The drop needs no additional mechanism: 10 chunk-slots chosen
per anchor versus 15 chunk-slots chosen once per paper and shared by a median 130 anchors is, on
its own, the entire effect.

---

## C. THREE CASES

The datasets join at record level (A3), so these are real rows, not constructions. All three are
`rank_r1 == 1` — the dense index ranked the exact target chunk **first** for its targeted query —
and `in_production_selection == False`. **2,287 records** meet that pair of conditions; **3,395 of
3,900** long-paper anchors (87.1 %) are R@10 hits that production never delivered.

### Case 1 — `4f3fca4c4f…`, value `24`, results/table, 213-chunk paper

- chunk `4f3fca4c4fa8471dfef57857a2bfc4c86a7735f1:105#0`, `block_type: table`, 31 words
- passage: *"Table 1: Recall@500 for different query rewriting strategies on the TREC RAG'24 dataset. The best-performing configuration is shown in bold. Teal background indicates the configuration used in the final submission."*
- targeted query `"Recall@ Table Recall different rewriting strategies TREC dat…"` → **rank 1 of 213**
- **dropped at step 7**, `retrieval_aware.py:252-256`: the chunk was never in the 5-generic-query × top-3 union.
- why: no generic query contains "Recall@500", "TREC" or "query rewriting". The chunk competes for 3 slots on "results findings outcomes performance evaluation" against every other results chunk in the paper. This paper delivered **4 of 90** anchors (0.044) against a 15/213 = 0.070 random expectation.

### Case 2 — `ef1e4a1671…`, value `10`, results/prose, 165-chunk paper

- chunk `ef1e4a1671918fbed15a7a0e3996fe3dbd8bffc4:56#0`, `block_type: paragraph`, 50 words
- passage: *"The chunking strategy employing spaCy's sentence tokenizer with a fixed size of 10 sentences per chunk proved effective. This approach resulted in 1,843 text chunks with an average token count of 183.61 (approximately 734 characters), well within the embedding model's 384-token capacity limit."*
- targeted query → **rank 1 of 165**
- **dropped at step 7**, same line.
- why: this paper delivered **0 of 101** anchors — delivery exactly zero, against a 15/165 = 0.091 random expectation. All 101 anchors (53 conclusion, 28 results, 11 experimental_setup, 8 method) missed. The 15 chunks the generic queries selected contained no anchor at all.

### Case 3 — `fef0393e99…`, value `47`, experimental_setup/prose, 511-chunk paper

- chunk `fef0393e997ec51b184e39c712be63197d99fd46:391#0`, `block_type: paragraph`, 93 words
- passage: *"The results from our study, as shown in Table 22, were quite promising. The data revealed that GPT-4 was only able to learn 47% of the new knowledge presented to it. However, with the help of fine-tuning, we were able to significantly increase this percentage. Specifically, the fine-tuned model was able to learn up to 72% and 74% of the new knowledge, depending on whether we used RAG or not."*
- targeted query `"The promising revealed GPT-4 knowledge presented However"` → **rank 1 of 511**
- **dropped at step 7**, same line.
- why: a 511-chunk paper receives the same ≤15-chunk allowance as a 67-chunk one. `_select_legacy` has no paper-size term — `n_results=3` is a literal at `retrieval_aware.py:253`. The headline finding of the paper is rank 1 for a query about it and still never reaches the extractor.

All three failures are the same failure, at the same line, for the same reason: the delivered set
is chosen once per paper by 5 queries that cannot name what is being looked for, and it is capped
at 15 chunks no matter how large the paper is.

**Terminology, per `RESEARCH_DIRECTIVE.md`.** These are **retrieval failures**: the information
exists in the chunk store, is indexed, is rank-1 retrievable, and did not reach the model. They
are not representation failures — the parser preserved all three passages intact — and not
extraction failures, because the extractor was never shown the text.

---

## Observations recorded, not acted on

- The word budget (step 9) is inert in the legacy path: ~456 words delivered against a 2,500-word
  allowance. Reported per the no-fix constraint.
- `in_production_selection` is measured pre-`_assemble` (`retrieval_recall.py:228`), so 0.090 is
  an upper bound on true delivery.
- 21 of 31 long papers deliver below a uniform-random null; one (`ef1e4a1671…`) delivers zero.
- The `retrieval:` config block (`mode: hybrid_rerank`, a reranker model, bm25 params) is read by
  no source file — `RETRIEVAL_RECALL_REPORT.md:21-26`. Unchanged.

---

## VERDICT

DELIVERY GAP IS REAL — drop occurs at the 5-generic-query × top-3 union in `_select_legacy`, `src/summarization/retrieval_aware.py:252-256`, accounts for ~100% (a uniform-random 15-of-N null predicts delivery 0.068 against 0.071 observed, so the ≤15-chunk per-paper budget explains the entire 0.938 → 0.071 long-paper drop while query relevance contributes only 1.047×)
