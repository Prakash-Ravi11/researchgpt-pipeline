# GATE SENSITIVITY REPORT — mutation testing of the Stage-5 evidence gate

Branch `claude-code-verification` · HEAD `2511e01` · 2026-09-02
Unit under test: `src.evidence.gate._gate_value(field, value, chunks, surnames)` (the real
production grounding + number-anchored `_ground` from `008397f` + `attribute_claim` + decide).
Harness: `experiments/document_evidence_pipeline/gate_sensitivity.py` · artifacts under
`runs/gate_sensitivity/`. **No thresholds were tuned.**

## Why

`false OWN = 0`, `provenance = 100%`, `numbers verbatim = 22/22` are true **by construction** — they
restate the gate's admission criteria, so they measure **specificity** and say nothing about
**sensitivity** (does the gate accept claims it should?). Mutation testing gives mechanical ground
truth: the mutation class fixes the expected verdict, no human annotation.

## Base set

The 26 quantitative items the gate currently **RETURNS**: 22 from the 60-paper canonical run
(`runs/prodab-20260902T004416Z/canonical_paper_evidence.json`) + 4 from `data_test`
(`runs/staging-20260902T030714Z/paper_evidence.json`). 12 metrics + 14 results. All 26 re-RETURN
under the current gate (no drift). Mutants are derived from these.

## Mutant counts and verdicts

| class | n | expected | correct | **wrong** | note |
|---|---:|---|---:|---:|---|
| 1 numeric_perturbation | 18 | ABSTAIN | 18 | **0** | number changed so it matches no chunk |
| 2a paraphrase_rule | 23 | ACCEPT | 22 | **1** | deterministic synonym / voice / reorder, numbers + metric tokens kept |
| 2b paraphrase_llm | 14 | ACCEPT | 14 | **0** | Qwen2.5:7B, temperature 0, **seed 42** |
| 3 fabrication | 14 | ABSTAIN | 14 | **0** | plausible claim, number absent from every chunk |
| 4a support_deletion (primary chunk) | 26 | ABSTAIN | 19 | **7** | remove only the chunk `_ground` selected |
| 4b support_deletion (all number-chunks) | 14 | ABSTAIN | 14 | **0** | remove every chunk containing the value's number(s) |

(Numeric perturbation applies to results only, and only to free result numbers — model/version
tokens like "GPT-5.2", "Llama-3", "T3-59K" are excluded; 18 mutants over 14 results items.
Paraphrase is restricted to result *sentences* — a 1–3-word metric name is not a sentence.)

## Confusion matrix (SYNTHETIC ground truth — see caveats)

Positives = should-ACCEPT = paraphrase mutants (rule + LLM), n=37.
Negatives = should-REJECT/ABSTAIN = numeric_perturbation + fabrication + support_deletion (4a+4b), n=72.

|  | gate RETURNED | gate ABSTAINED |
|---|---:|---:|
| should ACCEPT (n=37) | **TP = 36** | FN = 1 |
| should REJECT (n=72) | **FP = 7** | TN = 65 |

- **precision = 0.837** · **recall / sensitivity = 0.973** · **specificity = 0.903**

**Caveats — ground truth is mechanical, not human:**
- A rule paraphrase that a human might judge "meaning drifted" still counts as should-ACCEPT.
- All 7 FPs are `support_deletion_primary`: the value is genuinely **restated in another chunk**
  (abstract restates a body result; a metric name recurs). Corroboration is arguably *stronger*
  evidence, so counting these as "should REJECT" is the strict reading of the task's expectation
  ("abstain, not accept on a weaker match elsewhere"), not an obvious hallucination.
- With `support_deletion_primary` scored as neutral instead of negative: FP = 0, specificity = 1.00.

## Paraphrase pass rates (separate figures)

### Rule-based (deterministic): **22 / 23 pass**

One false negative — our actual sensitivity defect:

| paper | gate reason | base claim | mutant |
|---|---|---|---|
| `cf099b7cd7` | `evidence_span_not_found_in_paper_chunks` | *"Transformed traces from T 3-59K **outperform** those from T 3-114K on AIME and GPQA, despite T 3-114K being derived from a larger…"* | *"…T 3-59K **surpass** those from T 3-114K…"* |

This claim has **no `_NUMVAL`-anchorable number** ("3-59K" / "3-114K" are identifier-glued). For a
numberless result claim `_ground` falls back to pure **≥ 0.8 significant-token overlap** with a chunk
sentence. Swapping one non-anchor verb (`outperform` → `surpass`; the chunk contains "outperform",
not "surpass") drops the overlap below 0.8 and the claim is lost. This is exactly the §11 residual —
the number-anchor fix does not help claims that carry no anchorable number.

### LLM (Qwen2.5:7B, temperature 0, **seed 42**): **14 / 14 pass**

Every LLM paraphrase of a numbered result was re-accepted. The number-anchored grounding (`008397f`)
is robust to LLM rewording as long as the numbers and ≥ 2 significant tokens survive — which they did
at temp 0. The pre-`008397f` LLM-paraphrase sensitivity hole (whole-sentence token overlap) is closed
**for numbered results**; it remains open for numberless ones (the rule FN above).

### support_deletion_primary — the 7 that still RETURNED

| paper | field | claim | why it re-grounded |
|---|---|---|---|
| `f3b06a91` | metrics | "ANN search accuracy" | metric name recurs across many chunks |
| `93db4f9a` | metrics | "precision" | metric name recurs |
| `69b02cfe` | metrics | "Percentage of test cases … within 5 or 10 points…" | phrase recurs |
| `ef62f95c` | metrics | "Spearman's r2 correlation between …" | phrase recurs |
| `e6f1d66c` | results | "The system achieved an nDCG@5 score of **0.4502** …" | `0.4502` restated in the abstract |
| `c093b845` | results | "The system achieved an Exact Match accuracy of **0.72** …" | `0.72` restated in the abstract |
| `ef62f95c` | results | "A positive relationship (Spearman's r2 = **0.36**) was found …" | `0.36` restated in the abstract |

**Finding:** the gate has **no notion of chunk-level support identity**. Removing the specific chunk
it grounded on does not force abstention when the value/metric recurs elsewhere. For the 3 results
cases the re-ground is a legitimate abstract restatement (body-preference sort simply falls back to
the abstract); it is not a hallucination. When the number is *truly* removed (4b, every chunk with the
number), the gate abstains **14/14**.

## Two-significant-token binding rule — cross-row / cross-baseline probe

Construction: a real multi-row result-table chunk; take a number from **row B**, bind it to **row A's**
method label + a real column-metric token, craft `"{labelA} reports a {metric} of {numB}…"`. If the
gate RETURNS it, the ≥ 2-token co-occurrence rule was fooled — the number belongs to a different row.

**7 probes constructed, 4 FOOLED (RETURNED):**

| paper | crafted claim | verdict |
|---|---|---|
| `0549e2e9` | "**Active Oblongs 2D US** reports a **dice** of **407** on the benchmark." | **RETURNED** — and `407` is impossible as a Dice value (Dice ≤ 100 %); it is an `N`/count cell from the same table |
| `0549e2e9` | "**Proposed** reports a **accuracy** of **94.9** on the benchmark." | **RETURNED** — `94.9` is the *longitudinal Dice*, not an accuracy |
| `93db4f9a` | "**Validator-pass total** reports a **precision** of **136** on the benchmark." | **RETURNED** — `136` is a count from another row |
| `69b02cfe` | "**Nearest Neighbor** reports a **pearson** of **0.9895** on the benchmark." | **RETURNED** — `0.9895` is a different baseline's row |
| `f3d7e016` | "Van Bas Adv Q1 reports a faithfulness of 0.35 …" | ABSTAINED — `0.35` not actually in the chunk |
| `0549e2e9` | "GVF-Snake reports a dice of 56 …" | ABSTAINED — **attribution** caught it (`attributed_to_cited_work`; "GVF-Snake" is a cited baseline) |
| `0549e2e9` | "Adaptive Triple Dice Loss reports a dice of 2165 …" | ABSTAINED — `attributed_to_cited_work` |

**The gate is fooled whenever the fabricated number is genuinely present in the table chunk and the
row label does not trip the cited-work attribution rule.** Grounding verifies only "the number and
≥ 2 topical words share one chunk" — never that the number is *this row's value for this metric*,
and it has no range/plausibility check (a "Dice of 407" passes). Attribution is the only backstop, and
it only fires when the crafted subject looks like a citation.

## Single-digit anchor exclusion

`_NUMVAL = \d+\.\d+ | \b\d{2,}\b` deliberately drops lone single digits (to avoid "BLEU-4" → "4").
Scanning the LLM `results` / `key_findings` / `inferences` fields **and** the result/abstract/setup/
discussion chunks of all 68 papers for single-digit quantitative phrasings the gate can never anchor:

- **59 distinct single-digit quantitative mentions across 19 papers.**
- Origin: extraction `results` 3 · extraction `key_findings` 1 · chunk `abstract` 15 ·
  chunk `experimental_setup` 9 · chunk `results` 11 · chunk `discussion` 1.

Examples (all genuine first-party quantitative results, all unreachable):

| paper | phrase | sentence |
|---|---|---|
| `9feadf3c` | "8 percentage points" | "…GRPO improves answer accuracy to 87.62 % while **reducing hallucination by over 8 percentage points**" |
| `ef62f95c` | "8 %" | "**Accuracy drops of up to 8 %** were observed for several model families when evaluated on GSM1k" |
| `fef0393e` | "over 6" | "We see an **accuracy increase of over 6 p.p.**" |
| `fef0393e` | "by 5" | "…this is cumulative with RAG, which **increases accuracy by 5 p.p.**" |
| `f3b06a91` | "1 point" | "…injecting more similar neighbors only **drops performance by ~1 point**" |
| `db6965ad` | "8 %" | "**+8 % BERTScore**, +47 % ROUGE-L, +21.25 % BLEU … with **10 % fewer tokens** on HotpotQA" |

Only ~4 of these are in the *extracted* `results` text the gate directly consumes today — the LLM
often rounds to ≥ 2 digits or a decimal, which masks the gap. But the underlying claims exist in
**19 / 68 papers**, and any result phrased as an integer delta ("improves by 3 points", "5 % gain",
"2× faster", "6 p.p.") is **structurally unreachable** by the current gate.

## Summary of measured defects (report only — fixes are a separate task)

| # | class | measurement | severity |
|---|---|---|---|
| A | numberless result claims | rule paraphrase 22/23; the 1 FN is a synonym swap on a claim with no anchorable number (≥ 0.8 lexical overlap is brittle) | sensitivity — 1 observed FN; affects results with no ≥ 2-digit number |
| B | two-token binding | 4/7 crafted cross-row claims accepted; number-in-chunk + 2 tokens ≠ number belongs to this row/metric; no range/plausibility check ("Dice 407" passes) | **specificity — real; only attribution (cited-work) backstops it** |
| C | single-digit exclusion | 59 single-digit quantitative mentions in 19/68 papers are unreachable; ~4 already in extracted `results` | sensitivity — latent, corpus-wide |
| D | support identity | removing the one chunk `_ground` picked does not force abstention when the value recurs (7/26); removing *all* number-chunks does (14/14) | mild — gate tracks values, not which chunk supported them |

**Not measured as defects:** numeric perturbation (18/18 reject), fabrication (14/14 reject),
true support removal (14/14 abstain), LLM paraphrase of numbered results (14/14 accept).

### Reproduce

```
python experiments/document_evidence_pipeline/gate_sensitivity.py --pass all
```
Artifacts: `runs/gate_sensitivity/{mutants.json, crossrow.json, single_digit.json}`.
LLM paraphrase: `qwen2.5:7b`, `temperature=0`, `seed=42`.
