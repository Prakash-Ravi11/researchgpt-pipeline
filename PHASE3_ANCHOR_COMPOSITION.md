# PHASE 3 — ANCHOR COMPOSITION

Question: Phase 2's frozen query found no metric name for 83.4 % of anchors. Is that a property
of the anchors, or a limitation of the extractor? This decides whether
**`EVIDENCE_SELECTION/query`** is a real subcategory with mass in it, or an empty bucket.

## Reproducibility header

| | |
|---|---|
| commit | `56ea5038f50937dcdc3a88fe8b9c905225b3c07e`, branch `claude-code-verification` |
| harnesses | `phase3_sample.py` (sampling), `phase3_compose.py` (labels + section B). `src/` read-only. |
| measurement reused | `phase2_ladder.py` — **imported**, its `runs/phase2_ladder/per_anchor.json` consumed as the measurement of record. No retrieval was re-run and the cell-C measurement was not reimplemented. |
| output | `runs/phase3_composition/{labelling_sheet.md, suggested_labels.json, summary.json, sample_*.json, split.json}` |
| not touched | `runs/retrieval_recall/`, `runs/phase2_ladder/` — read only |
| seed | **42** (`random.Random(42)`; 60 unnamed drawn first, then 30 named) |
| population | 3,900 long-paper anchors from `runs/retrieval_recall/anchors.json` |
| split | **NAMED 644 (16.5 %) · UNNAMED 3,256 (83.5 %)** — reproduces Phase 2 exactly |
| extractor under test | frozen `_METRIC` regex, `retrieval_recall.py:41-45`, imported not copied |
| corpus | canonical 60 → 34 full-text papers (31 long). Paper ids in `PHASE2_LADDER.md` header. |

## Labelling authority and status of every number below

Per `RESEARCH_DIRECTIVE.md` § *Labelling authority*: **the 90 labels are Prakash's to make.**
The worksheet is at **`runs/phase3_composition/labelling_sheet.md`** — one block per anchor with
the verbatim window, the paper id, a blank `YOUR LABEL:` field, and a suggested label marked
machine-assisted.

**Every count, percentage and rate in sections A and C of this artifact is
`machine-labelled, unvalidated`.** The suggestions were produced by me (Claude Opus 5) reading
each anchor's ±220-char window and the paper title. No classifier was built, no separate LLM call
was made, and no prompt was issued — so there is no model/prompt pair to quote beyond this
session. They are one reader's judgement, and they are not ground truth.

**This is a pilot by construction.** `n = 60` unnamed and `n = 30` named. Per the directive's
kappa commitment, every bucket here is below the 50-human-labelled-items threshold — the largest
suggested bucket is 19. So: **pilot, n<50**. No kappa is reported. When Prakash returns the
worksheet, agreement is to be reported as raw agreement, not kappa, unless the categories are
first taken to ≥50 labelled items.

Section B is **not** label-dependent: it partitions all 3,900 anchors by the extractor's own
output and uses Phase 2's measured delivery flags. Those numbers stand on their own.

### Verification coverage (reported separately from accuracy, per the directive)

| verification_method | n of 90 | | verification_confidence | n of 90 |
|---|--:|---|---|--:|
| `structural` | 42 | | `high` | 57 |
| `semantic` | 29 | | `medium` | 31 |
| `exact` | 18 | | `low` | 2 |
| `normalized` | 1 | | | |

`exact` = the name string is present verbatim in the window. `normalized` = matches the frozen
regex only after de-hyphenation. `structural` = decided by position or by a check on the record
(e.g. the value is absent from its own chunk; the numeral sits in a reference list; the value
sits under a different column). `semantic` = a judgement about what the quantity is, which is
where the disagreement risk is concentrated — all 29 are `medium` or `low`. No pooled accuracy
number is emitted.

---

## A. WHAT ARE THE UNNAMED ANCHORS?

### A1. 60 unnamed anchors — suggested classification

> **machine-labelled, unvalidated · pilot, n<50**

| bucket | n | % of 60 | dominant verification_method |
|---|--:|--:|---|
| HAS_NAME_MISSED | **11** | **18.3 %** | `exact` (10), `normalized` (1) |
| NAMEABLE_INDIRECT | **19** | **31.7 %** | `semantic` — 17 medium, 2 low |
| GENUINELY_UNNAMEABLE | **13** | **21.7 %** | `structural` (13) |
| MALFORMED | **17** | **28.3 %** | `structural` (17) |

The largest suggested bucket is **MALFORMED**, and it is neither of the two things the phase
question asks about. Under the directive's attribution rule these anchors fail *before*
`EVIDENCE_SELECTION` — the required evidence was never correctly identified in the first place,
so they belong upstream, not in a query bucket. Contents:

- **section/heading numbers** as measured values — `U15` "3 Experimental Setup 3.1 Dataset",
  `U20` "4.3 Standard Evaluation Metrics", `U37` "4.2. Systems and experimental blocks",
  `U52` "5.3 Domain and Turn Analysis", `U10` "the metrics discussed in 4.3".
- **comma-split fragments of larger numbers** — `U35` value `815` cut out of "4,815
  above-plateau pairs"; `U38` value `898` cut out of "1,898 pages".
- **identifier fragments** — `U36` value `10.51584` from "DOI: 10.51584/IJRIAS".
- **superscript citation markers** — `U27` value `33` from "specific cases,32,33".
- **pseudocode line numbers** — `U16`, `U28`.
- **values not present in their own target chunk** — `U02 U11 U26 U33 U43 U55`. Across the full
  population this affects **372 of 3,900 anchors (9.5 %)** (`split.json`) — that figure is not
  label-dependent.

`GENUINELY_UNNAMEABLE` (13) is almost entirely **bibliography numerals**: journal volumes
(`U01`, `U09`, `U31`, `U49`, `U60`), page ranges (`U04`, `U05`, `U13`, `U30`, `U39`), an article
number (`U12`), a conference year (`U21`), a licence version (`U03`). Not naming failures —
numbers that should never have been anchors.

`HAS_NAME_MISSED` (11), with the name quoted per the directive:

| id | quoted name the extractor missed | mechanism |
|---|---|---|
| `U06` | `ArSQUAD` | dataset name — regex lists metrics only |
| `U07`, `U32` | `BioASQ` / `NQ` | dataset names |
| `U25` | `RepliQA` / `SQuAD2` | dataset names |
| `U40` | `FinanceBench` / `ConvFinQA` | dataset names |
| `U44` | `NQ` / `HotpotQA` / `BioASQ` | dataset names |
| `U46` | `CLAPNQ` / `FiQA` | dataset names |
| `U54` | `SaudiWiki` / `QA4MRE` / `Hindawi` | dataset names |
| `U58` | `StackExchange` / `Wikipedia-DPR` | corpus names |
| `U45` | `accuracy`, broken as **"accu- racy"** | PDF line-hyphenation — a representation failure surfacing as an extraction miss (`verification_method: normalized`) |
| `U29` | `beta values (β1, β2)` | named hyperparameter, not a metric (`semantic`/`medium`) |

Nine of the eleven are **dataset names**. The regex enumerates metrics and nothing else, so every
dataset name in the corpus passes it unseen.

### A2. 30 named anchors — is the extractor right when it fires?

> **machine-labelled, unvalidated · pilot, n<50**

| | n | % of 30 |
|---|--:|--:|
| CORRECT — the matched name names *this* value | **9** | **30.0 %** |
| **FALSE_POSITIVE** | **21** | **70.0 %** |

Excluding the 7 anchors whose value is not locatable in its own chunk (arguably not the
extractor's fault): 23 anchors, 14 false positives, **60.9 %**.

The regex binds the *first* metric name anywhere in a 440-character window to the value, with no
check that the two belong together. Suggested failure modes:

- **right table, wrong column** (`verification_method: structural`, `medium`) — `N07` `0.9874` is
  in the `R2` column, labelled `Pearson`; `N19` `99.95` is `Precision`, labelled `mAP`; `N21`
  `0.02` is a std on `Precision`, labelled `mAP`; `N17` `1.00` is in a `Relevance` column,
  labelled `Faithfulness`.
- **name present, value is a different quantity** (`semantic`, `medium`) — `N08` `500` is a
  test-set size labelled `accuracy`; `N18` `1.04` is cents per query labelled `accuracy`; `N11`
  `95` is a confidence level labelled `F1`; `N03` `50` is latency in ms labelled `Accuracy`;
  `N01`/`N13` `16` is a compression factor labelled `Recall@5`; `N15` `2.0` is the Apache licence
  version labelled `Recall@5`.
- **a regex alternative matching an ordinary word** (`exact`, `high`) — `N14`: the `em\b` branch
  matched the **Portuguese preposition "em"** in a reference list, yielding metric `em` for a page
  number. Recorded in `/FINDINGS.md`; not fixed.

---

## B. DOES THE SPLIT EXPLAIN THE RETRIEVAL BEHAVIOUR?

**Not label-dependent.** The partition is the extractor's own output over all 3,900 anchors, and
the delivery flags are Phase 2's measured `C` column, consumed from
`runs/phase2_ladder/per_anchor.json` via an import of `phase2_ladder`. No retrieval was re-run.

### B3. Cell C by partition (per-anchor top-3, `n_results = phase2_ladder.N_SMALL`)

| partition | n | cell C delivery | uniform null | **ratio to random** |
|---|--:|--:|--:|--:|
| NAMED | **644** | 0.0606 | 0.0171 | **3.54×** |
| UNNAMED | **3,256** | 0.0089 | 0.0129 | **0.69×** |
| HAS_NAME_MISSED | **11** | 0.0000 | — | **not computed** |

**HAS_NAME_MISSED is not computable at a meaningful n.** The bucket exists only on the 60-anchor
pilot sample, so n = 11 — and those 11 are themselves unvalidated suggestions. All 60 sampled
anchors were undelivered at cell C, consistent with the 0.0089 base rate and carrying no
information beyond it. Extending the bucket to all 3,256 would require labelling all 3,256, which
this phase does not do. **Left blank rather than estimated.**

### B4. Is the 0.69× uniform, or driven by a subset?

**Not uniform — strongly structured, and the structure is a bias toward title-echoing sections.**
All 3,256 UNNAMED anchors:

| section | n | cell C | null | ratio |
|---|--:|--:|--:|--:|
| introduction_related_work | 117 | 0.0513 | 0.0144 | **3.57×** |
| abstract | 410 | 0.0146 | 0.0124 | **1.18×** |
| experimental_setup | 456 | 0.0132 | 0.0126 | 1.05× |
| method | 601 | 0.0133 | 0.0157 | 0.85× |
| **results** | 310 | 0.0032 | 0.0102 | **0.32×** |
| references | 489 | 0.0000 | 0.0117 | **0.00×** |
| conclusion | 157 | 0.0000 | 0.0146 | **0.00×** |
| discussion | 118 | 0.0000 | 0.0146 | **0.00×** |

| location | n | cell C | null | ratio |
|---|--:|--:|--:|--:|
| prose | 2,127 | 0.0113 | 0.0127 | 0.89× |
| **table** | 1,129 | 0.0044 | 0.0133 | **0.33×** |

Introduction (3.57×) and abstract (1.18×) are the only sections beating random. Everything
carrying measured results is at or below chance: results 0.32×, tables 0.33×, and conclusion,
discussion and references at **exactly zero across 764 anchors**. A title describes what a paper
is *about*, so it retrieves the passages that describe what the paper is about — never the
passages reporting what it measured.

---

## C. CEILING

### C5. Usable query from anchor text + title alone

> **machine-estimated · flagged for Prakash's confirmation on the worksheet**

**30 of 60 = 50 %.** Every item on the worksheet carries a `CEILING(machine-est)` line and a
`YOUR CEILING CALL:` field.

| bucket | n | usable? |
|---|--:|---|
| HAS_NAME_MISSED | 11 | yes — the name is in the window |
| NAMEABLE_INDIRECT | 19 | yes — a row label or named entity gives a handle |
| GENUINELY_UNNAMEABLE | 13 | no — a volume or page range has no field to query |
| MALFORMED | 17 | no — a section number or DOI fragment is not a quantity |

This is a ceiling on **query construction**, not on delivery: writing a good query does not
guarantee the chunk is retrieved. It is far below Phase 2's oracle cell E (0.938), which is built
from text surrounding the answer and is not a fair comparison. Half the ceiling loss is not a
naming problem at all — 17 of the 30 unusable are MALFORMED.

### What this says about `EVIDENCE_SELECTION/query`

**The bucket is not empty, and it is not the whole story.** On the suggested labels, ~50 % of
unnamed anchors could carry a usable query, and B4 shows the query axis is doing real, measurable
damage independent of budget — zero delivery across 764 results/conclusion/discussion/reference
anchors. But ~28 % of unnamed anchors fail upstream of any query stage (MALFORMED) and ~22 % have
no field to query at all, so `EVIDENCE_SELECTION/query` cannot absorb the whole unnamed mass.
These proportions are unvalidated and rest on a pilot of 60.

---

## APPENDIX — the 90 sampled anchors, verbatim

Quoted from `runs/phase3_composition/suggested_labels.json`. Windows are
whitespace-collapsed and truncated to 300 characters; nothing else is altered.
`loc=False` means the value could not be located in its own target chunk.
**Every SUGGESTED label below is machine-assisted and unvalidated** — Prakash's
worksheet is `runs/phase3_composition/labelling_sheet.md`.


### HAS_NAME_MISSED — 11 of 60 (suggested)

**U06** · val `52.35` · experimental_setup/prose · `exact`/`high` · name quoted: `ArSQUAD`  
*Optimizing RAG Pipelines for Arabic: A Systematic Analysis of Core Components*  
> d- size chunking performs best on the SaudiWiki dataset (86.69), likely due to the structured and uniform nature of Wikipedia articles. Recursive chunking performs comparably in ArSQUAD, leading slightly with a score of 52.35 compared to sentence-aware’s 52.21, but both approaches remain significant

**U07** · val `0.03` · experimental_setup/table · `exact`/`high` · name quoted: `BioASQ / NQ`  
*Investigating the Robustness of Retrieval-Augmented Generation at the Query Leve*  
> Type R F A T10 T25 BioASQ RET 0.05 0.04 0.15 0.21↑ 0.23↑ CB 0.21 0.08 0.23 0.05 0.10 OR 0.35↑ 0.15↑ 0.33↑ 0.04 0.12 NQ RET 0.31↑ 0.27↑ 0.30↑ 0.35↑ 0.40↑ CB 0.03 0.04 0.11 0.08 0.16 OR 0.11 0.14 0.15 0.06 0.03

**U25** · val `702` · 4. the llm generates a res/table · `exact`/`high` · name quoted: `RepliQA / SQuAD2`  
*Highlight & Summarize: RAG without the jailbreaks*  
> H&S Span Highlighter 1170 60% H&S Baseline 1145 62% H&S Structured Highlighter 1105 63% Vanilla RAG 1104 61% H&S Two Steps Highlighter 1098 67% H&S BERT Extractor (RepliQA) 702 22% H&S BERT Extractor (SQuAD2) 673 14%

**U29** · val `0.95` · 2017. url http://arxiv.org/prose · `semantic`/`medium` · name quoted: `beta values (beta1, beta2)`  
*Command A: An Enterprise-Ready Large Language Model*  
> Stage 1 large-scale supervised learning. This expert is trained using Adam optimisation, a learning rate peak of 5×10−5, cosine decay to 5×10−6, beta values (β1 = 0.9, β2 = 0.95), weight decay factor of 0.1, and gradient norm clipping at peak 1.0. Our regularisation is inspired by similar code exper

**U32** · val `0.15` · experimental_setup/table · `exact`/`high` · name quoted: `BioASQ / NQ`  
*Investigating the Robustness of Retrieval-Augmented Generation at the Query Leve*  
> Type R F A T10 T25 BioASQ RET 0.05 0.04 0.15 0.21↑ 0.23↑ CB 0.21 0.08 0.23 0.05 0.10 OR 0.35↑ 0.15↑ 0.33↑ 0.04 0.12 NQ RET 0.31↑ 0.27↑ 0.30↑ 0.35↑ 0.40↑ CB 0.03 0.04 0.11 0.08 0.16 OR 0.11 0.14 0.15 0.06 0.03

**U40** · val `150` · 1. query clarification: th/prose · `exact`/`high` · name quoted: `FinanceBench / ConvFinQA`  
*Enhancing Financial RAG with Agentic AI and Multi-HyDE: A Novel Approach to Know*  
> nanceBench (Islam et al., 2023) and ConvFinQA (Chen et al., 2022) datasets. From FinanceBench, we have selected from 150 human-annotated exam- ples provided. These examples include evidence designated as ground truth context, with additional

**U44** · val `1496` · experimental_setup/table · `exact`/`high` · name quoted: `NQ / HotpotQA / BioASQ`  
*Investigating the Robustness of Retrieval-Augmented Generation at the Query Leve*  
> Dataset PERT Corpus NQ 1496 2.68M HotpotQA 1494 5.23M BioASQ 378 14.91M

**U45** · val `51.0` · 5.1. repeated four-system /prose · `normalized`/`high` · name quoted: `accuracy  [broken by line-hyphenation as 'accu- racy']`  
*Evidence-Grounded Constraint Checking in Construction Documents*  
> Region-RAG improves pooled standardized decision accu- racy from 40.3% to 51.0%, a gain of 10.6 percentage points (95% CI 4.3–18.0; exact p = .031). Every source project’s weighted contribution to the pooled contrast is positive. The four system-specific estimates are also positive, ranging fr

**U46** · val `0.4654` · introduction_related_work/table · `exact`/`high` · name quoted: `CLAPNQ / FiQA`  
*NLP-CEIA-UFG at SemEval-2026 Task 8: Iterative Retrieval with Notes-Guided Query*  
> CLAPNQ (Wikipedia) 142 76.8 0.2410 0.4654 Govt 157 77.7 0.2399 0.3839 Cloud 131 65.6 0.2583 0.5170 FiQA 77 85.7 0.2018 0.3557

**U54** · val `69.48` · 3.10 rq3: reranking impact/table · `exact`/`high` · name quoted: `SaudiWiki / QA4MRE / Hindawi`  
*Optimizing RAG Pipelines for Arabic: A Systematic Analysis of Core Components*  
> 8.66 45.55 49.54 51.97 56.55 SaudiWiki 85.21 58.21 83.96 86.87 88.31 88.74 QA4MRE 50.57 34.20 46.54 49.64 48.97 49.16 Quran Tafseer 79.40 53.86 75.53 77.68 82.72 81.16 Hindawi 74.34 45.11 68.15 70.25 73.70 67.84 Average 69.48 45.92 66.46 68.48 70.99 70.31

**U58** · val `1.4` · method/table · `exact`/`high` · name quoted: `StackExchange / Wikipedia-DPR`  
*RAG over Thinking Traces Can Improve Reasoning Tasks*  
> 39.6 (-12.2%) StackExchange 83.3 (-3.9%) 76.7 (-2.0%) 46.7 (-12.4%) 83.3 (-0.6%) 34.3 (-51.5%) 76.8 (-0.6%) 57.4 (0.0%) 55.0 (-5.0%) 42.1 (-6.7%) Wikipedia-DPR 88.3 (+1.8%) 71.7 (-8.4%) 56.7 (+6.4%) 84.3 (+0.6%) 71.7 (+1.4%) 80.3 (+3.9%) 59.9 (+4.4%) 59.4 (+2.6%) 46.5 (+3.1%) Wikipedia-RPJ 90.0 (+3.


### NAMEABLE_INDIRECT — 19 of 60 (suggested)

**U08** · val `20.955` · abstract/prose · `semantic`/`medium`  
*OpRAG: A Resource-Deterministic Runtime for GPU-Backed Multi-Stage RAG Workflows*  
> ine in strong scaling is HigressRAG. At 1024 workers, HigressRAG requires 6.028 s, while OpRAG requires 4.505 s, which is 1.34×. The gap is larger against the other baselines: at 1024 workers, AsyncParallelOnly requires 20.955 s and DaskScalableRAG requires 26.826 s. The stage-wise trends in Fig. 4 

**U14** · val `41.0` · references/table · `semantic`/`medium`  
*Toward Optimal Search and Retrieval for RAG*  
> BGE-base 4.0 13.0 37.0 BGE-large 4.0 13.0 41.0 ColBERTv2 4.0 11.0 31.0

**U17** · val `0.211` · method/table · `semantic`/`medium`  
*GINGER: Grounded Information Nugget-Based Generation of Responses*  
> GINGER-top20 wo/ rewriting 0.427 0.500 0.543 0.659 0.568 GINGER-top10 wo/ rewriting 0.369 0.423 0.502 0.582 0.502 GINGER-top5 wo/ rewriting 0.213 0.263 0.392 0.431 0.362 GINGER-top5 0.211 0.279 0.400 0.451 0.377

**U18** · val `0.423` · method/table · `semantic`/`medium`  
*GINGER: Grounded Information Nugget-Based Generation of Responses*  
> GINGER-top20 wo/ rewriting 0.427 0.500 0.543 0.659 0.568 GINGER-top10 wo/ rewriting 0.369 0.423 0.502 0.582 0.502 GINGER-top5 wo/ rewriting 0.213 0.263 0.392 0.431 0.362 GINGER-top5 0.211 0.279 0.400 0.451 0.377

**U19** · val `27` · experimental_setup/prose · `semantic`/`low`  
*RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture*  
> Somewhat similar 49% 27% 25%

**U22** · val `2.054` · abstract/table · `semantic`/`medium`  
*Test-Time Strategies for More Efficient and Accurate Agentic RAG*  
> base (PPO) 0.292 0.356 1.410 instruct (GRPO) 0.310 0.396 2.054

**U23** · val `0.338` · experimental_setup/table · `semantic`/`medium`  
*Can QPP Choose the Right Query variant? Evaluating Query Variant Selection for R*  
> 8 0.377 0.360 0.239 0.398 0.386 0.532 0.353 IDF𝑠𝑢𝑚 0.386 0.367 0.329 0.217 0.41 0.384 0.519 0.343 ICTF𝑎𝑣𝑔 0.374 0.349 0.275 0.21 0.421 0.392 0.532 0.332 SCQ𝑎𝑣𝑔 0.368 0.341 0.275 0.21 0.421 0.391 0.544 0.337 SCQ𝑚𝑎𝑥 0.362 0.338 0.358 0.213 0.378 0.366 0.521 0.339 SCQ𝑠𝑢𝑚 0.384 0.363 0.339 0.219 0.409 0

**U24** · val `0.442` · method/table · `semantic`/`medium`  
*GINGER: Grounded Information Nugget-Based Generation of Responses*  
> baseline-top5 0.247 0.332 0.468 0.525 0.442 baseline_CoT-top5 — 0.332 0.452 0.500 0.428

**U34** · val `31` · experimental_setup/prose · `semantic`/`medium`  
*Can QPP Choose the Right Query variant? Evaluating Query Variant Selection for R*  
> ork 1. We set the temperature to 0.6 and generated 5 samples per method to capture semantic diversity while managing variance. This results in 30 generated variants per information need plus the original query, totaling 31 variations.

**U41** · val `0.2789` · introduction_related_work/table · `semantic`/`medium`  
*NLP-CEIA-UFG at SemEval-2026 Task 8: Iterative Retrieval with Notes-Guided Query*  
> ANSWERABLE 285 199 (69.8%) 0.2789 PARTIAL 143 121 (84.6%) 0.2009 UNDERSPECIFIED 78 62 (79.5%) 0.1672 UNANSWERABLE 1 1 (—) 0.0000

**U42** · val `184` · abstract/prose · `semantic`/`medium`  
*An Approach for Embedding-Guided Function Reuse Detection in Embedded C Software*  
> peripheral token overlap, parameter count parity, call-graph dependency overlap, and structural branching pattern—filter candidates directly in the retrieval stack. Evaluated on six public embedded C software projects (184 functions, 4,815 above-plateau pairs), the pipeline reveals that SonarQube pr

**U47** · val `273` · experimental_setup/prose · `semantic`/`medium`  
*RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture*  
> dataset, a comprehensive collection of 573 documents entailing approximately 2 million tokens. The answers for the questions were generated from the Llama2-13B-chat model with RAG. The evaluation dataset is composed of 273 human-curated for the state of Washington. Each sample in the evaluation data

**U48** · val `44` · 4. if the text mentioned a/prose · `semantic`/`medium`  
*RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture*  
> and best practices, quality assurance and export regulations, details on assistance programs, as well as insurance and pricing guidelines. Collected data totals more than 23k PDF files with over 50M tokens, representing 44 states in the USA. We downloaded and preprocessed these files, extracting the

**U50** · val `3.83` · experimental_setup/table · `semantic`/`low`  
*RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture*  
> 3.5 External context 3.83 16.36 1.06 0.98 4.75 4.75

**U51** · val `20` · abstract/prose · `semantic`/`medium`  
*Retrieval-Augmented Large Language Models for Schema-Constrained Clinical Inform*  
> er- vation concepts with explicit value types and, for categorical concepts, enumerated allowable values. The schema is dominated by categorical fields (130 single_select and 12 multi_select), with addi- tional numeric (20) and string (31) concepts. Cat- egorical concepts have relatively small label

**U53** · val `0.363` · experimental_setup/table · `semantic`/`medium`  
*Can QPP Choose the Right Query variant? Evaluating Query Variant Selection for R*  
> 6 0.367 0.329 0.217 0.41 0.384 0.519 0.343 ICTF𝑎𝑣𝑔 0.374 0.349 0.275 0.21 0.421 0.392 0.532 0.332 SCQ𝑎𝑣𝑔 0.368 0.341 0.275 0.21 0.421 0.391 0.544 0.337 SCQ𝑚𝑎𝑥 0.362 0.338 0.358 0.213 0.378 0.366 0.521 0.339 SCQ𝑠𝑢𝑚 0.384 0.363 0.339 0.219 0.409 0.386 0.513 0.341 SCSapx 0.274 0.227 0.289 0.177 0.376 0

**U56** · val `5.564287` · conclusion/table · `semantic`/`medium`  
*An Automated Retrieval-Augmented Generation LLaMA-4 109B-based System for Evalua*  
> 1.738065 100.0 98.387097 5.532193 all-distilroberta-v1 4 0.000045 0.999909 0.000045 3.777993 1.770161 100.0 98.387097 5.564284 msmarco-distilbert-base-tas-b 4 0.000045 0.999909 0.000045 3.777997 1.770161 100.0 98.387097 5.564287 stsb-roberta-large 4 0.000076 0.999879 0.000045 3.778000 1.738065 100.0

**U57** · val `90` · method/prose · `semantic`/`medium`  
*A hybrid pipeline for carotid artery segmentation using YOLOv11n and contour mod*  
> ining, validation, and a wholly independent hold-out test set. Specifically, 10% of the total images from both sections were separated before training and preserved untouched to serve as a final benchmark. The remaining 90% of the data underwent 5-fold cross-validation. The development pool was part

**U59** · val `164.995` · abstract/table · `semantic`/`medium`  
*OpRAG: A Resource-Deterministic Runtime for GPU-Backed Multi-Stage RAG Workflows*  
> AsyncParallelOnly 0.032 0.016 152.127 0.096 4.215 156.462 DaskScalableRAG 0.186 0.033 152.135 0.101 4.206 156.615 RayScalableRAG 8.098 0.521 152.215 0.096 4.227 164.995 HigressRAG 0.033 0.022 151.979 0.098 4.224 156.309 OpRAG 0.030 0.019 126.832 0.344 4.193 131.048


### GENUINELY_UNNAMEABLE — 13 of 60 (suggested)

**U01** · val `15` · references/prose · `structural`/`high`  
*Engineering Inferential Composition Control for Federated RAG in Data Spaces*  
> wards the ‘Act-ification’of the Fifth European Freedom for Data? European Journal of Law and Technology, 15(1).

**U03** · val `4.0` · abstract/prose · `structural`/`high`  
*GINGER: Grounded Information Nugget-Based Generation of Responses*  
> This work is licensed under a Creative Commons Attribution 4.0 International License.

**U04** · val `5273` · experimental_setup/prose · `structural`/`high`  
*An Automated Retrieval-Augmented Generation LLaMA-4 109B-based System for Evalua*  
> modeling of dose-volume histograms. Medical physics, 47(10):5260–5273, 2020.

**U05** · val `108` · references/prose · `structural`/`high`  
*Optimizing RAG Pipelines for Arabic: A Systematic Analysis of Core Components*  
> Hajj, H.: Neural arabic question answering. In: Proceedings of the Fourth Arabic Natural Language Processing Workshop, pp. 108–118 (2019)

**U09** · val `153` · references/prose · `structural`/`high`  
*An Automated Retrieval-Augmented Generation LLaMA-4 109B-based System for Evalua*  
> rado-Bruggeman, Nobutaka Mukumoto, Laura Patricia Kaplan, et al. What is plan quality in radiotherapy? the importance of evaluating dose metrics, complexity, and robustness of treatment plans. Radiotherapy and Oncology, 153:26–33, 2020.

**U12** · val `100045` · experimental_setup/prose · `structural`/`high`  
*An Automated Retrieval-Augmented Generation LLaMA-4 109B-based System for Evalua*  
> Zihao Wu, Haixing Dai, Yiwei Li, et al. Artificial general intelligence for radiation oncology. Meta-radiology, 1(3):100045, 2023.

**U13** · val `31227` · 2023. retrieving supportin/prose · `structural`/`high`  
*RAG over Thinking Traces Can Improve Reasoning Tasks*  
> Scales, David Dohan, Ed H Chi, Nathanael Schärli, and Denny Zhou. 2023. Large language models can be easily distracted by irrelevant context. In Inter- national Conference on Machine Learning, pages 31210–31227. PMLR.

**U21** · val `22` · references/prose · `structural`/`high`  
*Investigating the Robustness of Retrieval-Augmented Generation at the Query Leve*  
> rt and self-teaching for improving the robustness of dense retrievers on queries with typos. In Proceed- ings of the 45th International ACM SIGIR Confer- ence on Research and Development in Information Retrieval, SIGIR ’22, page 1444–1454. ACM.

**U30** · val `31210` · 2023. retrieving supportin/prose · `structural`/`high`  
*RAG over Thinking Traces Can Improve Reasoning Tasks*  
> Scales, David Dohan, Ed H Chi, Nathanael Schärli, and Denny Zhou. 2023. Large language models can be easily distracted by irrelevant context. In Inter- national Conference on Machine Learning, pages 31210–31227. PMLR.

**U31** · val `12` · references/table · `structural`/`high`  
*Chunking, Retrieval, and Re-ranking: An Empirical Evaluation of RAG Architecture*  
> P. Liang, “Lost in the middle: How language models use long contexts,” Transactions of the Association for Computational Linguistics, vol. 12, pp. 157–173, 2024, preprint arXiv:2307.03172 (2023). [12] R. Nogueira and K. Cho, “Passage re-ranking with BERT,” 2019. [13] V. Pipitone and N. Alami, “Legal

**U39** · val `68539` · 2017. url http://arxiv.org/prose · `structural`/`high`  
*Command A: An Enterprise-Ready Large Language Model*  
> as Scialom. Toolformer: Language models can teach themselves to use tools. In A. Oh, T. Naumann, A. Globerson, K. Saenko, M. Hardt, and S. Levine (eds.), Advances in Neural Information Processing Systems, volume 36, pp. 68539–68551. Curran Associates, Inc., 2023. URL https://proceedings.neurips.cc/p

**U49** · val `38` · abstract/prose · `structural`/`high`  
*Retrieval-Augmented Large Language Models for Schema-Constrained Clinical Inform*  
> Basilakis, Paula Sanchez, Dominique Estival, Barbara Kelly, and Leif Hanlen. 2014. A usability framework for speech recognition technologies in clinical handover: A pre-implementation study. Journal of medical systems, 38(6):56.

**U60** · val `33` · abstract/prose · `structural`/`high`  
*Retrieval-Augmented Large Language Models for Schema-Constrained Clinical Inform*  
> mir Karpukhin, Naman Goyal, Heinrich Küttler, Mike Lewis, Wen-tau Yih, Tim Rocktäschel, et al. 2020. Retrieval-augmented generation for knowledge-intensive nlp tasks. Ad- vances in neural information processing systems, 33:9459–9474.


### MALFORMED — 17 of 60 (suggested)

**U02** · val `27730` · experimental_setup/prose · **loc=False** · `structural`/`high`  
*RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture*  
> However, when considering the two models, GPT-3.5 and GPT-4, one of the most noticeable differences is their performance speed. GPT-3.5 tends to be faster compared to GPT-4. For example, when using Azure OpenAI, gpt-35-turbo and gpt-35-turbo-16k generate between 240k and 300k tokens per minute depen

**U10** · val `4.3` · experimental_setup/prose · `structural`/`high`  
*RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture*  
> aset consists of a question and an evaluation guideline that describes the contents of a desirable answer. We generated answers for both base and fine-tuned models with and without RAG, and used the metrics discussed in 4.3 to evaluate the answers.

**U11** · val `72.8` · results/table · **loc=False** · `structural`/`high`  
*Command A: An Enterprise-Ready Large Language Model*  
> Command A 93.0 98.2 95.5 94.8 93.5 94.6 84.2 94.9 93.2 93.4 89.6 93.7 93.6 92.2 90.3 Command R+ Refresh 95.5 94.8 98.2 97.2 97.2 96.5 89.0 97.5 96.2 94.7 91.6 96.9 97.8 98.3 90.6 Qwen 2.5 72B Instruct Turbo 93.0 96.4 94.0 94.3 93.7 94.1 86.6 94.0 91.3 93.0 87.9 95.8 95.4 95.7 89.2 Claude 3.7 Sonnet 

**U15** · val `3.1` · experimental_setup/prose · `structural`/`high`  
*Can QPP Choose the Right Query variant? Evaluating Query Variant Selection for R*  
> 3 Experimental Setup 3.1 Dataset

**U16** · val `10` · 1. query clarification: th/prose · `structural`/`high`  
*Enhancing Financial RAG with Agentic AI and Multi-HyDE: A Novel Approach to Know*  
> 10: A generates a sub-query qsub and selects a tool t ∈T

**U20** · val `4.3` · experimental_setup/prose · `structural`/`high`  
*Investigating the Robustness of Retrieval-Augmented Generation at the Query Leve*  
> 4.3 Standard Evaluation Metrics

**U26** · val `9459` · discussion/prose · **loc=False** · `structural`/`high`  
*PlanSightRAG: A Visual-First Multimodal RAG for Automating Question Answering an*  
> structured human validation (Appendix B) mitigate major failure modes. Second, the compliance test sets are parameterized CAD generations. While this design isolates VLM discrimination abilities, it does not fully replicate real-world ambiguities such as overlapping callouts or smudged scans; autono

**U27** · val `33` · discussion/prose · `structural`/`high`  
*Advancing Question-Answering in Ophthalmology With Retrieval-Augmented Generatio*  
> framework has broader applications within ophthalmology and other medical specialties.30,31 In clinical settings, it could support decision making by retrieving guideline-based information tailored to specific cases,32,33 such as glaucoma staging or uveitis workups. It may also generate patient-frie

**U28** · val `25` · results/prose · `structural`/`high`  
*KeyKnowledgeRAG (K^2RAG): An Enhanced RAG method for improved LLM question-answe*  
> 1: Load in QuantizedLLM 2: Define the generation prompt for generation 3: Define the question prompt for question creation 4: Load in embeddingsmodel 5: Load in summariser model 6: Load in knowledge graph 7: Load in BM25 store 8: Load in semantic vector store 9: Obtain user input 10: Retrieve knowle

**U33** · val `88.78` · method/prose · **loc=False** · `structural`/`high`  
*A hybrid pipeline for carotid artery segmentation using YOLOv11n and contour mod*  
> After applying Gamma correction, a more potent denoising phase that is provided by non-local means denoising (NLM)49 successfully smooth the textures inside the carotid lumen boundary area by effectively eliminating granular noise, preventing the active contour from becoming stuck on small tissue fl

**U35** · val `815` · abstract/prose · `structural`/`high`  
*An Approach for Embedding-Guided Function Reuse Detection in Embedded C Software*  
> overlap, parameter count parity, call-graph dependency overlap, and structural branching pattern—filter candidates directly in the retrieval stack. Evaluated on six public embedded C software projects (184 functions, 4,815 above-plateau pairs), the pipeline reveals that SonarQube produces a 93.6% fa

**U36** · val `10.51584` · results/prose · `structural`/`high`  
*A Scalable Retrieval-Augmented Generation Pipeline for Domain-Specific Knowledge*  
> ISSN No. 2454-6194 | DOI: 10.51584/IJRIAS |Volume X Issue X October 2025

**U37** · val `4.2` · 4.2. systems and experimen/prose · `structural`/`high`  
*Evidence-Grounded Constraint Checking in Construction Documents*  
> 4.2. Systems and experimental blocks

**U38** · val `898` · method/prose · `structural`/`high`  
*PlanSightRAG: A Visual-First Multimodal RAG for Automating Question Answering an*  
> e visual index, all headline retrieval, and compliance- pipeline retrieval, and the 400 DPI sliding-window tiling path is the only exception and is evaluated solely as an ablation (Section 7). The combined index spans 1,898 pages: WYDOT (237), Caltrans 2025 (638), Ari- zona DOT 2025 (181), Colorado 

**U43** · val `1024` · method/prose · **loc=False** · `structural`/`high`  
*PlanSightRAG: A Visual-First Multimodal RAG for Automating Question Answering an*  
> resolution choices, we used 200 DPI full-page for the visual index, all headline retrieval, and compliance- pipeline retrieval, and the 400 DPI sliding-window tiling path is the only exception and is evaluated solely as an ablation (Section 7). The combined index spans 1,898 pages: WYDOT (237), Calt

**U52** · val `5.3` · introduction_related_work/prose · `structural`/`high`  
*NLP-CEIA-UFG at SemEval-2026 Task 8: Iterative Retrieval with Notes-Guided Query*  
> 5.3 Domain and Turn Analysis

**U55** · val `5314` · method/table · **loc=False** · `structural`/`high`  
*GINGER: Grounded Information Nugget-Based Generation of Responses*  
> Grave, Yann LeCun, and Thomas Scialom. 2023. Augmented Language Models: a Survey. arXiv:2302.07842 [cs.CL] [24] Dor Muhlgay, Ori Ram, Inbal Magar, Yoav Levine, Nir Ratner, Yonatan Belinkov, Omri Abend, Kevin Leyton-Brown, Amnon Shashua, and Yoav Shoham. 2023. Generating Benchmarks for Factuality Eva


### The 30 NAMED anchors (suggested)

**N01** **FP** · val `16` · matched `Recall@5` · experimental_setup/prose · `semantic`/`medium`  
> backbone—the strongest openly licensed visual retriever on our benchmark and fully deploy- able—and report all main results with it; ColPali serves as a companion backbone for our binary-quantization study (HPC-ColPali, 16× compression) and controlle

**N02** OK · val `71.91` · matched `accuracy` · discussion/prose · `exact`/`high`  
> The performance of the surveyed open-source, quantized language modes with RAG was found to be comparable to that of GPT-4 on both datasets and even surpasses the human reference accuracy of 71.91%.2 This finding is significant as it highlights the p

**N03** **FP** · val `50` · matched `Accuracy` · results/table · `semantic`/`medium`  
> Metric Bi-Encoder Cross-Encoder Model all-MiniLM-L6 ms-marco-MiniLM Latency ∼15ms / 1M docs 50–150ms / 20 docs Accuracy 65–80% relevance 85–90% relevance Interaction Independent Joint Attention Scaling High (billions) Low (dozens)

**N04** OK · val `10.6` · matched `accuracy` · conclusion/prose · `exact`/`high`  
> ally changes constraint decisions in professional documents. Across a repeated four-system test, concentrating a bounded visual packet on one retrieved page and its regions improves expert-reference decision accuracy by 10.6 percentage points, with p

**N05** **FP** · val `41.1` · matched `accuracy` · conclusion/prose · loc=False · `structural`/`high`  
> Evidence allocation materially changes constraint decisions in professional documents. Across a repeated four-system test, concentrating a bounded visual packet on one retrieved page and its regions improves expert-reference decision accuracy by 10.6

**N06** OK · val `99.5` · matched `mAP` · results/table · `structural`/`high`  
> Table 3 YOLOv11n transverse and longitudinal lumen localization results. Section Folds mAP@0.5 mAP@0.5:0.95 Precision Recall Transverse section Fold 1 99.5 91.35 99.94 1 Fold 2 99.5 92.15 99.95 1 Fold 3 99.5 91.08 99.98 1 Fold 4 99.5 91.18 99.95 1 Fo

**N07** **FP** · val `0.9874` · matched `Pearson` · method/table · `structural`/`medium`  
> Pearson r Spearman ρ MAE RMSE R2 %≤5pt %≤10pt Nearest Neighbor 0.9971 0.9959 1.7381 1.9013 0.9942 100.0 100.0 Weighted Average 0.9895 0.9902 2.1361 3.7780 0.9769 91.94 98.39 Weighted Median 0.9944 0.9943 1.9986 2.7962 0.9874 90.32 100.0

**N08** **FP** · val `500` · matched `accuracy` · conclusion/prose · `semantic`/`medium`  
> 8 pp above the strongest hybrid baseline (VisionRAG (Pyramid, RRF)). The agentic Planner–Auditor–Synthesizer com- pliance pipeline, armed with per-drawing pre-resolved rule thresholds, reaches 100% verdict accuracy on a 500-drawing single-doc CAD tes

**N09** **FP** · val `14` · matched `IoU` · results/prose · loc=False · `structural`/`high`  
> Ground-truth annotation status. At the time of sub- mission, the GT-box JSON was seeded with the pre- dicted boxes so that the IoU pipeline could be exercised end-to-end; this configuration trivially yields IoU= 1.0 on every query and is not a meanin

**N10** OK · val `100` · matched `Recall@5` · abstract/prose · `exact`/`high`  
> RAG is 17.77% and 17.48% faster than the best framework baseline. In Higress- style query serving, OpRAG reduces hybrid retrieval latency by 59.20–59.62% and generation-scenario latency by 52.48–53.55%, while preserving 100% Recall@5. These results s

**N11** **FP** · val `95` · matched `F1` · 4. metodologia experimen/prose · `semantic`/`medium`  
> artic¸˜oes. A efetividade dos m´etodos ´e medida pela m´etrica Macro-F1. Para verificar a significˆancia estat´ıstica das diferenc¸as observadas entre os m´etodos, aplicamos o teste t pareado com n´ıvel de confianc¸a de 95%, utilizando correc¸˜ao de 

**N12** OK · val `0.80` · matched `faithfulness` · discussion/prose · `exact`/`high`  
> average scores across both dimensions. The inclusion of the ms-marco-MiniLM-L-6-v2 cross-encoder allowed the system to evaluate token-level alignment, successfully ”re- covering” Question 8 with a faithfulness score of 0.80. By jointly encoding the q

**N13** **FP** · val `16` · matched `Recall@5` · experimental_setup/prose · `semantic`/`medium`  
> backbone—the strongest openly licensed visual retriever on our benchmark and fully deploy- able—and report all main results with it; ColPali serves as a companion backbone for our binary-quantization study (HPC-ColPali, 16× compression) and controlle

**N14** **FP** · val `277` · matched `em` · 6.2. direc¸˜oes futuras/prose · `exact`/`high`  
> s desbalanceadas? n˜ao classifique-ranqueie! uma abordagem ba- seada em retrieval-augmented generation (rag)-labels para classificac¸˜ao textual multi- classe. In Simp´osio Brasileiro de Banco de Dados (SBBD), pages 264–277. SBC.

**N15** **FP** · val `2.0` · matched `Recall@5` · experimental_setup/prose · `semantic`/`medium`  
> ing, tiling, visual grounding, and agentic compliance components are unchanged by the backbone, so any of these retrievers can drop in directly, and the per- agency gains transfer. Complementarily, a lightweight Apache-2.0 visual reranker (MonoQwen2-

**N16** OK · val `5.31` · matched `accuracy` · discussion/prose · `exact`/`high`  
> e most persuasive proof for the pipeline’s architecture emerged in Ablation 2, where excluding the YOLOv11n-based ROI and applying the active contour on the whole enhanced images resulted in a total accuracy collapse of 5.31%. Applying the active con

**N17** **FP** · val `1.00` · matched `Faithfulness` · results/table · `structural`/`medium`  
> QID Faithfulness Relevance Van Bas Adv Van Bas Adv Q1 0.33 0.33 0.67 0.50 1.00 1.00 Q2 0.33 0.67 0.83 0.33 1.00 1.00 Q3 0.33 1.00 1.00 0.67 1.00 1.00 Q4 0.33 0.33 0.16 0.50 0.50 0.50 Q5 0.25 0.50 0.25 0.33 0.67 0.33 Q6 0.33 0.67 1.00 0.33 0.80 1.00 Q

**N18** **FP** · val `1.04` · matched `accuracy` · method/prose · `semantic`/`medium`  
> ntrast, T 3 provides a better cost– accuracy frontier by replacing full trajectories with shorter, more targeted transformed traces. For GPT- 5, T 3 improves accuracy from 76.14 to 80.53 while reducing cost from 1.22 to 1.04 cents per query, a 14.8% 

**N19** **FP** · val `99.95` · matched `mAP` · results/table · `structural`/`medium`  
> Table 3 YOLOv11n transverse and longitudinal lumen localization results. Section Folds mAP@0.5 mAP@0.5:0.95 Precision Recall Transverse section Fold 1 99.5 91.35 99.94 1 Fold 2 99.5 92.15 99.95 1 Fold 3 99.5 91.08 99.98 1 Fold 4 99.5 91.18 99.95 1 Fo

**N20** **FP** · val `37.2` · matched `accuracy` · discussion/prose · loc=False · `structural`/`high`  
> Although overall retrieval accuracy is high, several queries received a judge score of 0.0. Reviewing these zero-score cases reveals five systematic error patterns in the model’s visual–textual reasoning over engineering drawings. (1) Component–dimen

**N21** **FP** · val `0.02` · matched `mAP` · results/table · `structural`/`medium`  
> 0.5 mAP@0.5:0.95 Precision Recall Transverse section Fold 1 99.5 91.35 99.94 1 Fold 2 99.5 92.15 99.95 1 Fold 3 99.5 91.08 99.98 1 Fold 4 99.5 91.18 99.95 1 Fold 5 99.5 90.97 99.95 1 Mean ± Std 99.5 91.35 ± 0.47 99.95 ± 0.02 1 Longitudinal section Fo

**N22** OK · val `0.995` · matched `mAP` · results/prose · `exact`/`high`  
> The YOLOv11n localization model’s exceptional robustness is demonstrated by its quantitative performance, which is represented in Table 3. For both carotid sections, a mean mAP@50 of 0.995 and an almost faultless recall of 1.0 were attained across th

**N23** **FP** · val `4.49` · matched `faithfulness` · 3.10 rq3: reranking impa/prose · `semantic`/`medium`  
> nts). Similarly, QA4MRE saw a 4.6-point increase in overall score, highlighting the reranker’s ability to pro- mote more useful chunks in inference-heavy tasks. ArSQUAD and Hindawi Books also benefited, showing gains of 4.49 and 4.04 points respectiv

**N24** OK · val `68.1` · matched `Accuracy` · abstract/table · `exact`/`high`  
> Retrieval Accuracy 80.3% 89.5% Average Retrieval Time 0.039s 0.015s Answer Accuracy 65.1% 68.1%

**N25** **FP** · val `500` · matched `IoU` · results/prose · loc=False · `structural`/`high`  
> Ground-truth annotation status. At the time of sub- mission, the GT-box JSON was seeded with the pre- dicted boxes so that the IoU pipeline could be exercised end-to-end; this configuration trivially yields IoU= 1.0 on every query and is not a meanin

**N26** **FP** · val `17.5` · matched `accuracy` · conclusion/prose · loc=False · `structural`/`high`  
> Evidence allocation materially changes constraint decisions in professional documents. Across a repeated four-system test, concentrating a bounded visual packet on one retrieved page and its regions improves expert-reference decision accuracy by 10.6

**N27** **FP** · val `75.27` · matched `IoU` · results/prose · loc=False · `structural`/`high`  
> Metric definition. For each query, we compute the maximum IoU over all pairs of ground-truth and predicted boxes associated with that query (many-to- many max-IoU matching). Aggregate metrics include mean IoU, IoU@0.3 (fraction of queries with max Io

**N28** OK · val `60` · matched `accuracy` · results/prose · `exact`/`high`  
> se, P < 0.001). A similar pattern was observed with the OphthoQuestions dataset: GPT-4’s accuracy increased by 7.69% (from 77.69% to 85.38%), Llama-3-70B saw a 27.7% gain (50.38% to 78.08%), Gemma-2-24B improved by 15% (60% to 75%), and Mixtral-8 × 7

**N29** **FP** · val `1.0` · matched `faithfulness` · introduction_related_wor/table · `semantic`/`medium`  
> IDK-conditioned harmonic mean of three compo- nents: RB_agg (aggregate of BertRec, BertKPrec, and RougeL), RL_F (RAGAS faithfulness), and RB_llm (LLM-as-judge). Under IDK-conditioning, responses classified as IDK score 1.0 on UNANSWERABLE queries and

**N30** **FP** · val `39.3` · matched `accuracy` · discussion/prose · loc=False · `structural`/`high`  
> Although overall retrieval accuracy is high, several queries received a judge score of 0.0. Reviewing these zero-score cases reveals five systematic error patterns in the model’s visual–textual reasoning over engineering drawings. (1) Component–dimen


---

## VERDICT

MIXED — 18.3% missed, 21.7% unnameable
