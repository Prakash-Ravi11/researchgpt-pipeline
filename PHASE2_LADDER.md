# PHASE 2 — DECOMPOSING THE DELIVERY GAP

Question: of the 0.938 → 0.071 drop, how much is **budget** (≤15 chunks vs a median
223-chunk paper) and how much is **query quality** (5 fixed generic queries that never name a
metric or dataset)?

## Reproducibility header

| | |
|---|---|
| commit | `56ea5038f50937dcdc3a88fe8b9c905225b3c07e`, branch `claude-code-verification` |
| harness | `experiments/document_evidence_pipeline/phase2_ladder.py` (new; nothing in `src/` modified) |
| output | `experiments/document_evidence_pipeline/runs/phase2_ladder/{ladder.json, per_anchor.json}` (new directory; no existing `runs/` artifact written) |
| embedder | `BAAI/bge-m3`, `normalize_embeddings=True`, `max_seq_length=256`, device cuda (RTX 3050 6 GB) |
| index | `runs/prodab-20260902T004416Z/canonical/chroma_db`, collection `researchgpt_papers`, **9,002 chunks**, cosine |
| chunk store | `runs/prodab-20260902T004416Z/canonical/processed/chunks.json` |
| anchors | `runs/retrieval_recall/anchors.json` — **3,981** anchors, unchanged |
| corpus | canonical 60 → **34 full-text papers** (31 long, 3 short) |
| paper ids | `0549e2e9e6 1016250721 141276ba65 2009dbb5f2 413a184de4 4d6e977f0e 4f3fca4c4f 6437463b4b 68f93a5921 69b02cfebf 78797b7178 81e060664f 93db4f9a32 96285d75a5 a6d08e12d2 a6ecdf6970 a9b2a3fd60 ac8fffa1a4 ae2768758f be7c4dc390 c093b845f6 cf099b7cd7 d3b5f3c050 db78acdc12 ddb170b2ee e0efa866a1 e6f1d66c34 eaec7401af ef1e4a1671 f1f07a37d4 f3b06a9147 f3d7e0165d f42ad6e248 fef0393e99` |
| relevance criterion | unchanged — hit = target chunk **or** any alternate carrying the same value, in the delivered set |
| unit | unchanged — one numeric anchor |

**Self-check.** Cell A reproduces the recorded production number exactly: computed 0.0713 vs
`in_production_selection` 0.0713, delta 0.0000. The harness asserts this and refuses to report
otherwise (`phase2_ladder.py`, final assertion).

## Frozen cell C/D query construction

Written into the harness docstring before the run, not tuned afterwards:

```
metric = first match of the frozen _METRIC regex (retrieval_recall.py:41-45, reused by
         import, not copied) in the ±220-char window around the anchor's value inside its
         target chunk, taken VERBATIM as match.group(0)
title  = the paper title as stored on its chunks in chunks.json
query  = f"{metric} {title}"     — or the title alone when no metric matches
```

No synonyms, no expansion, no prompt engineering, no iteration, no per-cell variation.

**The construction yields no metric name for 3,319 of 3,981 anchors (83.4 %).** For those the
query is the paper title alone. This is reported as a result, not repaired. It is the single
most important fact about cells C and D and it is carried through every number below.

---

## The ladder

Long papers only (31 papers, 3,900 anchors) — the 3 short papers bypass retrieval entirely and
sit at delivery 1.000 in every cell, so including them only dilutes. The all-anchor figures are
in `ladder.json` and differ in the third decimal.

| cell | query | n_results | shape | delivery | uniform null | ratio to random | budget (chunks) | words mean / p95 |
|---|---|--:|---|--:|--:|--:|--:|--:|
| **A** | 5 generic (production) | 3 | per-paper union | **0.0713** | 0.0567 | **1.26×** | 13.2 | 399 / 998 |
| **B** | 5 generic (production) | 50 | per-paper union | **0.6118** | 0.4986 | **1.23×** | 127.4 | 2438 / 2500 |
| **C** | per-anchor field query | 3 | per-anchor top-k | **0.0174** | 0.0136 | **1.28×** | 3.0 | 205 / 553 |
| **D** | per-anchor field query | 50 | per-anchor top-k | **0.3059** | 0.2271 | **1.35×** | 50.0 | 2340 / 2500 |
| **E** | anchor-aware oracle | 10 | per-anchor top-k | **0.9385** | 0.0454 | **20.66×** | 10.0 | 2340 / 2500 |

The uniform null is the anchor-weighted mean of `budget_chunks / n_chunks` for the paper, using
the **actual** delivered set size, not the nominal cap.

**A shape difference the table cannot hide.** A and B are per-paper unions of 5 queries — the
production shape, one context per paper. C, D and E are per-anchor top-k, matching the shape of
the R@10 anchor point that defines cell E. The budgets are therefore not matched across the
query factor: B spends 127.4 chunks where D spends 50. Raw deltas between rows inherit that
mismatch; **ratio to random is the only column comparable across all five cells**, because it
divides out the budget. Both readings are given below.

### The one column that matters

Ratio to random is flat at **1.23–1.35×** for every cell except the oracle, which is **20.66×**.
Raising `n_results` from 3 to 50 moves raw delivery from 0.071 to 0.612, but moves ratio-to-random
from 1.26× to 1.23× — *down*. **Budget buys volume, not precision: a bigger `n_results` delivers
almost exactly as many extra anchors as taking that many more chunks at random would.** Only the
oracle query, which is synthesized from the text surrounding the answer, has precision.

### Where the frozen field query does and does not work

Splitting cells C and D by whether the frozen construction actually produced a metric name — the
same query, the same run, reported as two subgroups, nothing re-tuned:

| subgroup | n | C delivery | C null | **C ÷ random** | D delivery | D null | **D ÷ random** |
|---|--:|--:|--:|--:|--:|--:|--:|
| metric name present | 644 | 0.0606 | 0.0171 | **3.54×** | 0.5186 | 0.2852 | **1.82×** |
| title only | 3,256 | 0.0089 | 0.0129 | **0.69×** | 0.2638 | 0.2157 | 1.22× |

When the query names the metric it beats random by **3.54×** at `n_results=3` — nearly three
times production's 1.26×. When it degenerates to the title it scores **0.69×, worse than
random**: the title retrieves the chunks that echo the title — abstract, header, introduction —
not the chunks carrying results. Pooled at 16.5 % / 83.5 %, these cancel to 1.28×, which is why
cell C looks identical to production while containing a strong effect and a harmful one.

---

## Answers

### 1. At `n_results=50`, does the 2,500-word budget at `configs/config.yaml:37` bind?

**Yes, hard.**

| cell | mean words | median | p95 | max | papers at the 2,500 cap |
|---|--:|--:|--:|--:|--:|
| A (n=3) | 398.6 | 337 | 998 | 1,056 | **0 of 34** |
| B (n=50) | **2,437.7** | 2,500 | **2,500** | 2,500 | **30 of 34** |
| C (n=3) | 205.2 | 192 | 553 | 712 | 0 of 34 |
| D (n=50) | 2,339.5 | 2,500 | 2,500 | 2,500 | 21 of 34 |

At `n_results=3` the budget is untouched — the largest paper assembles 1,056 words against a
2,500-word allowance. At `n_results=50` it is saturated: 30 of 34 papers hit the cap exactly and
the p95 is the cap itself.

**At what n does it start?** *Not determinable from this experiment.* The phase fixes
`n_results` to 3 and 50 and forbids other values, so the onset lies somewhere in the open
interval (3, 50) and I did not measure it. The only bound I can state without another run is
arithmetic: canonical chunks average 30 words, so 2,500 words is roughly 83 chunks of assembled
text, and the union at n=3 already holds 13.2. I am not converting that into an onset estimate —
it would be a guess, and the union grows sublinearly in `n_results` because the 5 queries
overlap.

### 2. Decomposition: is D−A ≈ (B−A) + (C−A)?

**No. They do not add, and the residual is large and negative.**

| term | meaning | value |
|---|---|--:|
| B − A | budget effect | **+0.5405** |
| C − A | query effect | **−0.0539** |
| (B−A) + (C−A) | additive prediction | +0.4866 |
| D − A | both, measured | **+0.2346** |
| D − A − [(B−A)+(C−A)] | residual | **−0.2520** |

**But this residual is mostly not an interaction.** B spends 127.4 chunks per paper; D spends
50. More than half the gap between the additive prediction and the measured D−A is the budget
the two cells were never given equally, not a query×budget effect. The decomposition the ladder
asks for is only clean if the budget is matched across the query factor, and in this design it
is not — B and D differ by 2.5× in chunks spent.

What survives that caveat, because it is budget-normalized: ratio to random is 1.26 → 1.23 along
the budget axis (generic query) and 1.28 → 1.35 along it (field query). Neither query type gains
precision from a larger budget. The two factors are close to **independent in precision terms**;
the apparent interaction lives entirely in the raw rates, which are budget-driven.

### 3. Does the per-anchor query (C) beat random at its budget, unlike production (A)?

**It beats random, but not "unlike production" — production beats random by the same margin.**

- C = **1.28×** random. A = **1.26×** random. The difference is negligible.
- The interesting answer is conditional, and it is in the subgroup table above: on the 644
  anchors where the frozen construction found a metric name, C = **3.54×** random; on the 3,256
  where it degenerated to the title, C = **0.69×** — *below* random.

So the per-anchor query does not uniformly beat production. It beats it decisively when it names
the metric and is actively worse than chance when it does not, and the frozen construction
produces a metric name only 16.5 % of the time.

---

## Correction to PHASE1_DELIVERY_GAP.md

Phase 1 reported production at **1.047× random** and concluded the budget accounted for "~100 %"
of the drop. That ratio used the **nominal** 15-chunk cap as the budget. The union is a `set`
(`src/summarization/retrieval_aware.py:252-256`) and the 5 generic queries overlap, so the actual
delivered set averages **13.2 distinct chunks, not 15**.

| null basis | null | ratio |
|---|--:|--:|
| nominal cap 15/N — what Phase 1 reported | 0.0681 | 1.046× |
| actual union size — correct | 0.0567 | **1.257×** |

Production beats random by **1.26×**, not 1.05×. Budget therefore accounts for about **79 %** of
observed delivery (0.0567 of 0.0713), not ~100 %. Phase 1's verdict — that the gap is real and
that the drop occurs at the 5-query × top-3 union — is unaffected; only the magnitude of the
"no better than random" characterization was overstated.

---

## Observations recorded, not acted on

- The frozen field-query construction finds no metric name for 83.4 % of anchors. Whether a
  better construction exists is not measured here and was not attempted.
- Cell B delivers 0.612 of anchors while saturating the existing 2,500-word budget on 30 of 34
  papers — i.e. within limits the pipeline already permits. Reported per the no-intervention
  constraint; no change was made to `src/`.
- Cell E's 20.66× is an oracle ceiling. Its query is built from the window around the answer, so
  it is not reachable by any policy that does not already know where the answer is.

---

## VERDICT

BUDGET DOMINATES — budget effect +0.5405, query effect -0.0539
