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
python experiments/document_evidence_pipeline/gate_sensitivity.py --pass all --no-range   # pre-fix baseline
```
Artifacts: `runs/gate_sensitivity/{mutants.json, crossrow.json, single_digit.json}`.
LLM paraphrase: `qwen2.5:7b`, `temperature=0`, `seed=42`.

---

# FIX for defect B — metric range plausibility

## ATTRIBUTION ≠ BINDING (stated in `src/evidence/gate.py`)

**ATTRIBUTION** answers *whose* result this is (own vs cited). **BINDING** answers
*which* result this is — is this number the value of this metric, for this row/subject.
Both must hold for a quantitative claim to be true. The gate verified attribution and
grounding ("number + ≥ 2 topical tokens co-occur in one chunk"); it **never verified
binding**. A cross-row number, or a count Stage 4 misread as a metric value, satisfies
grounding just as well as the real value. Test 2's 7 crafted cross-row claims: **4
RETURNED**; attribution backstopped only 2, and only when the fake subject resembled a
citation. **"false OWN = 0" was never evidence of binding correctness.**

This fix is a **one-directional plausibility floor**, not a full binding check: when a
claim *names* a bounded metric, its value must be physically possible for that metric. It
cannot tell that a *plausible* number belongs to the wrong row.

## Metric range table

Metric list **derived from the corpora** — every metric name appearing in a RETURNED
`metrics`/`results` item across `canonical60` + `data_test` — union the phase brief's list.
Only metrics with a **finite upper bound** are in the table.

| family | metrics | plausible interval |
|---|---|---|
| percentage-family | Dice / DSC, F1 (micro/macro), accuracy (balanced, top-k), precision, recall, IoU / mIoU, Jaccard, AUROC, AUPRC, AUC / ROC-AUC, AP, sensitivity, specificity, TPR, TNR, nDCG, MAP, MRR, hit/success/pass rate, pass@1, BLEU / sacreBLEU, ROUGE(-L/-1/-2), METEOR, chrF, TER, exact match / EM, SSIM, faithfulness, relevance, win rate, coverage | **[0, 100]** |
| correlation-family | Pearson, Spearman, Kendall τ, Cohen κ, MCC, R² | **[−100, 100]** |
| **not checked** (no finite ceiling) | MAE, RMSE, MSE, MAPE, perplexity, Hausdorff / HD95, PSNR, latency, throughput | — |

### 0–1 vs 0–100 — decided rule (not a per-value guess)

A percentage-family metric is reported in the literature on **either** a 0–1 **or** a 0–100
scale. The gate **accepts both** and takes the plausible interval as **[0, 100]**. It does
**not** infer which scale a given number uses — it only rejects the physically impossible
(`< 0`, or `> 100`; correlation `|x| > 100`). So `Dice 0.914` and `Dice 91.4` both pass;
`Dice 407` and `accuracy 216` do not.

### When it applies

Only when a table metric is **named in the claim**, and only to the number **adjacent** to
that name — `"F1 of 0.88"`, `"dice = 94.9"`, `"94.9% Dice"`. A number several words away
does **not** bind: `"72.69% accuracy on emotion recognition with 216 test samples"` binds
`72.69`, not the sample count `216`. A value with no named metric is never range-checked —
silent over-rejection would be worse than the bug.

### Logging

`run_evidence_gate` writes **`evidence_gate_range_rejections.json`** — one entry per
rejection: `{paper_id, field, metric, value, interval, claim}`. Prints a one-line count +
the first 8. `stats["metric_range_rejections"]` in `evidence_gate_summary.json`.

## MEASURE — Test 2 re-run, current corpora (`--no-range` vs default)

### Confusion matrix — UNCHANGED

| | phase-brief baseline | measured **before** (`--no-range`) | measured **after** |
|---|---|---|---|
| should-ACCEPT (paraphrase) | TP 36 / FN 1 | TP 36 / FN 1 | **TP 36 / FN 1** |
| should-REJECT (pert/fab/del) | FP 7 / TN 65 | FP 7 / TN 65 | **FP 7 / TN 65** |
| precision / sensitivity / specificity | .837 / .973 / .903 | .837 / .973 / .903 | **.837 / .973 / .903** |

The standard mutation classes (numeric perturbation, fabrication, support deletion,
paraphrase) never produce an out-of-range named-metric value, so the range check leaves the
matrix **exactly** as-is. The 1 FN is `cf099b7cd7` (`evidence_span_not_found`, a
comparative sentence with no anchorable number — pre-existing, not range-related).

### Cross-row probes: 4 accepted → **2**; range alone rejects **2 of the 4**

| probe (crafted) | before | after | caught by |
|---|---|---|---|
| `93db4f9a32` "Validator-pass total reports a **precision of 136**" | RETURNED | ABSTAINED | **range** (136 ∉ [0,100]) |
| `0549e2e9e6` "Active Oblongs 2D US reports a **dice of 407**" | RETURNED | ABSTAINED | **range** (407 ∉ [0,100]) |
| `0549e2e9e6` "Proposed reports an **accuracy of 94.9**" | RETURNED | **RETURNED** | — (94.9 is a plausible accuracy — wrong row, range can't tell) |
| `69b02cfebf` "Nearest Neighbor reports a **pearson of 0.9895**" | RETURNED | **RETURNED** | — (0.9895 is a plausible ρ — wrong row) |
| `0549e2e9e6` "Adaptive Triple Dice Loss reports a **dice of 2165**" | ABSTAINED (attribution) | ABSTAINED (range, fires first) | range or attribution |
| `0549e2e9e6` "GVF-Snake reports a **dice of 56**" | ABSTAINED (attribution — cited baseline) | ABSTAINED (attribution) | attribution |
| `f3d7e0165d` "Van Bas Adv Q1 reports a **faithfulness of 0.35**" | ABSTAINED (grounding) | ABSTAINED (grounding) | grounding |

**Rejection log — full (every entry, all crafted probes; 0 organic corpora rejections):**

| paper | field | metric | value | interval | claim |
|---|---|---|---|---|---|
| `93db4f9a329d` | results | precision | 136.0 | [0, 100] | "Validator-pass total reports a precision of 136 on the benchmark." |
| `0549e2e9e6be` | results | dice | 407.0 | [0, 100] | "Active Oblongs 2D US reports a dice of 407 on the benchmark." |
| `0549e2e9e6be` | results | dice | 2165.0 | [0, 100] | "Adaptive Triple Dice Loss reports a dice of 2165 on the benchmark." |

Dry-run of `metric_range_check` over all **26 RETURNED** `metrics`/`results` items in both
corpora: **0 flagged.** (`78797b71788b` "72.69% accuracy … 216 test samples" is *not*
flagged — the adjacency rule binds `72.69`, not `216`.)

### New false negatives introduced (real claim rejected by the range check)

**None.** First cut of the check bound the *nearest* number regardless of distance and
flagged `78797b71788b` accuracy=216 (the sample count) — 3 FN in Test 2 + 1 on the corpora.
Fixed by requiring the number be **adjacent** to the metric name (`_NUM_AFTER_RE` /
`_NUM_BEFORE_RE`, ≤ 24 chars after with an `of`/`=`/`:`/`%` connector, ≤ 14 before). Post-fix:
confusion matrix identical to baseline, 0/26 corpora items flagged.

## Invariant 13

`13_out_of_range_metric_values_zero` — no RETURNED `metrics`/`results` claim asserts a
value outside its named bounded metric's range. Added to `staging_run.py`
(`_check_invariants`), applied post-gate to the gated evidence.

## Honest limit

Range plausibility closes the *impossible-value* half of defect B (a count or a cross-row
number that lands outside the metric's range). It does **not** close the
*plausible-but-wrong-row* half — 2 of the 7 cross-row probes still pass because 94.9 is a
valid accuracy and 0.9895 a valid ρ; only the row is wrong. That requires positional
row/column binding at parse time (Phase 4's structured cells were built for exactly this,
and Phase 4 is blocked). Reported, not tuned.

---

# Contract-versioned Test 2 oracle (post-5a/5b/5c)

The Test 2 harness oracle predates 5a/5b/5c. It labels `expected=RETURNED` for mutants
the new contract now correctly withholds — chiefly **numeric OWN claims on PDF-only
papers**, which are `unverifiable_binding` by design (task 1's mandated correction). So the
raw post-5 matrix mixes contract change with capability, and reads as a broken system.

`gate_sensitivity.py` now carries a second oracle (`expected_v2`) and splits every mutant:

- **CONTRACT_CHANGED** — the correct outcome legitimately differs under the post-5 contract.
  A mutant moves here ONLY with a one-sentence justification, never because it fails.
- **UNCHANGED** — same correct outcome under both contracts.

`_v2_oracle` derives `expected_v2` deterministically: a `RETURNED`-expected mutant becomes
`ABSTAINED` iff (5a) its value is out of range for a named bounded metric, OR (5c) it binds
to an ablation/other table, OR (5b) it carries a meaningful numeric anchor and the paper is
PDF-only (no `table_cells`). Everything else keeps its v1 expectation.

## Three matrices (`--pass all`, seed 42)

| matrix | oracle | mutants | pos | neg | TP | FN | FP | TN | precision | sensitivity | specificity |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **A** old oracle, ALL (pre-5 baseline) | v1 | 81 | 37 | 44 | 2 | 35 | 3 | 41 | 0.40 | **0.054** | 0.932 |
| **B** new oracle, ALL | v2 | 81 | 3 | 78 | 2 | 1 | 3 | 75 | 0.40 | 0.667 | 0.962 |
| **C** new oracle, UNCHANGED only | v2 | 47 | 3 | 44 | 2 | 1 | 3 | 41 | 0.40 | **0.667** | **0.932** |

**Matrix C is the reported sensitivity. Matrix A is the pre-contract baseline: its
sensitivity 0.054 is not capability loss — 34 numeric-OWN-on-PDF paraphrases whose *correct*
answer became "withhold" under 5b account for the entire A→B/C gap.**

## CONTRACT_CHANGED — 34 mutants, each justified

All 34 are numeric OWN paraphrases (`paraphrase_rule` 20 + `paraphrase_llm` 14) on a
PDF-only paper. Identical reason per mutant: *the post-5 contract cannot structurally verify
a numeric OWN claim on a collapsed PDF, so the correct outcome is `unverifiable_binding`
(ABSTAINED), not RETURNED*. All 34: the gate ABSTAINED — matches `expected_v2`. Full list
with per-mutant value/reason in `runs/gate_sensitivity/contract_matrices.json`.

**0** mutants moved for 5a (out-of-range) or 5c (ablation binding): Test 2's corpora
(`canonical60` + `data_test`) are entirely PDF-only with no structured `table_cells`, so
those contract changes cannot arise here.

## What matrix C actually measures

- **Positives: 3** — all from `cf099b7cd7`, one comparative claim ("Transformed traces from
  T 3-59K outperform those from T 3-114K on AIME and GPQA…") with **no meaningful numeric
  anchor**, so structural binding is never invoked. Gate: 2 RETURNED, 1 ABSTAINED
  (`evidence_span_not_found` — a synonym swap broke grounding). TP 2 / FN 1.
- **Negatives: 44** — the unchanged `numeric_perturbation` / `fabrication` /
  `support_deletion_*` set. FP 3 / TN 41. The 3 FP are the pre-existing
  `support_deletion_primary` recurrence escapes (defect D — the value re-grounds in another
  chunk); unchanged by 5x.
- **Honest limit:** the acceptance path has only 3 test cases on these corpora because
  every numeric OWN paraphrase is now (correctly) a contract-changed / unverifiable case.
  Meaningful acceptance-sensitivity measurement needs **structured papers**, which
  `canonical60` and `data_test` do not contain (LaTeX ingestion disabled since Phase 4b;
  only ~2 JATS papers corpus-wide, none in Test 2's base set).

### Reproduce

```
python experiments/document_evidence_pipeline/gate_sensitivity.py --pass all
```
Artifacts: `runs/gate_sensitivity/{mutants.json (with expected_v2), contract_matrices.json}`.
