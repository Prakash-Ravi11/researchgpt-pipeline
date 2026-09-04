# Sensitivity of an established automated RAG evaluation framework to controlled structural evidence mutations

Branch `claude-code-verification` · 2026-09-04
Six stages unchanged. `configs/` not modified. `latex_ingestion_enabled` stays `false`.
Seeded (temperature 0, seed 42), clean cache. Corpora kept separate (canonical 60,
data_test 8, medical 50) — every case carries its `corpus` label and results are
never pooled into a per-corpus claim.

Harnesses: `eval_framework_sensitivity.py` (main run), `eval_framework_control.py`
(positive control). Outputs in `runs/eval_framework_sensitivity/`.

## Research question

**How sensitive is an established automated RAG evaluation framework to controlled
structural evidence mutations?**

Stated hypothesis-neutrally and answered as measured. No mutant, prompt, threshold
or example was chosen because the framework was expected to fail it; the design
below can falsify this project's thesis, and in one arm it does.

This is an **evaluation-method comparison**, not a benchmark of ResearchGPT quality.

## Method

**Mutants — the existing suite, unchanged and unfiltered.** Every scored case in
`runs/gate_sensitivity/{mutants,crossrow}.json`: **106 cases** across numeric
perturbation (19), fabricated value (15), support deletion — primary (24) and full
(1), paraphrase — rule (24) and LLM (15), and cross-row structural mutation (8).
Nothing added, nothing removed, no mutation definition changed.

**Framework — one fixed configuration for every case.** RAGAS 0.2.15,
`Faithfulness`: the response is decomposed into atomic claims and each is
NLI-checked against the retrieved context. It is the RAGAS metric whose stated
purpose — *is the answer grounded in the evidence* — matches the question the
structural diagnostic asks.

| parameter | value |
|---|---|
| judge LLM | `qwen2.5:7b` via Ollama, temperature 0, seed 42, `num_ctx` 8192 |
| embeddings | `BAAI/bge-m3` (the pipeline's embedding model) |
| `retrieved_contexts` | top-8 chunks of the case's paper by cosine similarity to the **original, pre-mutation** claim — held constant within a mutation family so only the response varies |
| support-deletion handling | `drop_chunk_ids` removed from the candidate pool *before* retrieval, mirroring what the gate sees |
| `user_input` | one fixed question per field |

**Detection criterion — fixed before any result was inspected.**

- A should-REJECT mutant is **detected** iff `faithfulness < 0.5` (a majority of the
  response's atomic claims judged unsupported).
- A should-ACCEPT mutant (paraphrase) is **correctly passed** iff `faithfulness ≥ 0.5`.
- Secondary marker, reported alongside but *not* the criterion: `faithfulness < 1.0`
  (any unsupported claim at all).
- NaN / judge failure → "no score"; counted separately, never as a detection.
  **0 of 106 cases failed to score.**

**Structural diagnostic result** = the gate's recorded `gate_final` (`ABSTAINED` =
flagged, `RETURNED` = accepted). **Disagreement** = the two approaches' flag
verdicts differ on the same case.

## Result — 106 cases, 0 unscored

| mutation type | n | framework detected (<0.5) | strict marker (<1.0) | structural detected | framework false-flags | disagreements |
|---|--:|--:|--:|--:|--:|--:|
| fabricated value | 15 | **15/15** | 15/15 | **15/15** | — | 0 |
| cross-row structural | 8 | 8/8 *(see control)* | 8/8 | 8/8 | — | 0 |
| numeric perturbation | 19 | **6/19** | 18/19 | **19/19** | — | 13 |
| support deletion — primary | 24 | **2/24** | 2/24 | **11/24** | — | 13 |
| support deletion — full | 1 | 0/1 | 1/1 | 1/1 | — | 1 |
| paraphrase — rule | 24 | — | — | — | 2/24 | 20 |
| paraphrase — LLM | 15 | — | — | — | 1/15 | 12 |
| **all** | **106** | **31/67** | **44/67** | **54/67** | **3/39** | **59** |

Per-case detail (original case, mutation type, RAGAS score, detection flag,
structural result, disagreement) is in `runs/eval_framework_sensitivity/per_mutant.json`.

## Positive control on the cross-row arm — and what it removes

All 8 cross-row mutants scored exactly `0.0`, as did all 15 fabrications. A uniform
floor is not by itself evidence of structural sensitivity: the cross-row claims come
from a stilted crafted template (*"X reports a Y of Z on the benchmark."*), and a
judge may be rejecting the template rather than the misattribution.

So the same template, the same paper, the same retrieved context, carrying the row's
**own correct number**, was scored as a positive control. Interpretation was fixed
before running: control ≥ 0.5 *and* mutant < 0.5 ⇒ detection specific to the
structural error; both < 0.5 ⇒ not specific, arm uninformative.

| # | control (correct cell) | mutant (cross-row) | interpretable? |
|--:|--:|--:|:--|
| 0 | 0.0 | 0.0 | no |
| 1 | **1.0** | 0.0 | **yes** |
| 2 | **1.0** | 0.0 | **yes** |
| 3 | 0.0 | 0.0 | no |
| 4 | 0.0 | 0.0 | no |
| 5 | 0.0 | 0.0 | no |
| 6 | 0.0 | 0.0 | no |
| 7 | 0.0 | 0.0 | no |

**Only 2 of 8 controls were accepted.** In the other 6 the framework rejects the
correct-cell claim exactly as it rejects the cross-row one, so those `0.0` scores
carry no information about structural sensitivity.

**The cross-row arm is therefore n = 2, not n = 8, and on those 2 the framework
detected 2/2.** The raw "8/8" must not be reported as sensitivity.

**The structural diagnostic fails the same style of control**, stated symmetrically
rather than in this project's favour: on the Phase-5 adversarial harnesses its
`correct_cell` positive controls were accepted **1/5** (canonical LaTeX) and **0/2**
(medical JATS). Both methods are strongly conservative on this crafted claim
template. Neither side's cross-row number is a clean sensitivity estimate at this n.

## Outcome — reported narrowly

Against the pre-registered options this is **Outcome B**, with one arm withdrawn:

> **The framework detected some failure classes completely and others only
> partially. The cross-row structural arm could not be interpreted at this n,
> because its positive control failed in 6 of 8 cases.**

What the measurement actually shows:

1. **Fabricated values — complete agreement, no additional detection.** 15/15 for
   both. For this class the structural diagnostic supplies **localisation, not
   additional detection**.
2. **Numeric perturbation — a threshold/aggregation effect, not blindness.** The
   framework registered the perturbation in **18/19** cases (score < 1.0) but only
   **6/19** fell below the 0.5 criterion: one wrong number inside a sentence
   carrying several true claims is diluted by a mean-over-claims score. The
   structural diagnostic caught **19/19** because it anchors on the number itself.
   This is the clearest divergence in the study, and it is about *how the score
   aggregates*, not about the framework failing to notice.
3. **Support deletion (primary) — both weak, framework weaker.** Framework 2/24
   (22 of 24 scored exactly 1.0); structural 11/24. Removing the single primary
   supporting chunk left the value present in another chunk that top-8 retrieval
   surfaced, so the framework saw a fully grounded answer. The structural
   diagnostic's own 11/24 here is a previously documented weakness, not a win.
4. **Paraphrase — the framework has good specificity.** It wrongly flagged only
   **3/39** faithful paraphrases.
5. **Disagreements are dominated by contract, not capability.** 32 of the 59
   disagreements are paraphrase cases where the framework passes the claim and the
   structural diagnostic withholds it under the documented post-Phase-5 contract
   (numeric OWN claim on a PDF-only paper → `unverifiable_binding`). That is a
   deliberate contract difference and must not be read as the framework missing
   something.

## Threats to validity — all of these limit the claim

- **One framework, one metric.** RAGAS `Faithfulness` only. One framework does not
  represent the evaluation literature, and one metric does not represent RAGAS.
- **A 7B judge.** `qwen2.5:7b` is the only LLM available in this environment. A
  stronger judge would plausibly change the numeric-perturbation and cross-row
  results. These scores are not a property of RAGAS in general.
- **Small structural arm.** 8 cross-row cases, 2 interpretable. No rate should be
  quoted from n = 2.
- **Template artifact.** The crafted cross-row claims are rejected by *both* methods
  regardless of correctness in most cases; the probe template, not the mutation,
  drives much of that arm.
- **Retrieval choice.** Top-8 by similarity to the pre-mutation claim is one
  reasonable construction; a different `k` or query would move the support-deletion
  arm in particular.
- **Threshold choice.** The 0.5 criterion was fixed in advance, but the
  numeric-perturbation result is highly threshold-sensitive (6/19 at <0.5 vs 18/19
  at <1.0). Both are reported so the finding does not rest on the cut point.

## What may and may not be claimed

**May be claimed, as measured on this suite with this configuration:**

- Under a fixed, pre-registered majority-of-claims criterion, the framework detected
  **31/67** should-reject mutants against the structural diagnostic's **54/67**.
- The gap is concentrated in **numeric perturbation** (6/19 vs 19/19 — an
  aggregation effect; the framework registered 18/19 at the strict marker) and
  **support deletion — primary** (2/24 vs 11/24).
- On **fabricated values** the two agree completely (15/15 each); there the
  structural diagnostic adds localisation, not detection.
- The framework's specificity on faithful paraphrases is high (3/39 false flags).

**May not be claimed:**

- That the framework is blind to cross-row structural errors. It scored 8/8 raw, and
  both interpretable cases were detected. That arm is uninformative, not supportive.
- Any rate derived from the cross-row arm (n = 2 after control).
- Anything about automated RAG evaluation frameworks in general, about RAGAS with a
  stronger judge, or about RAGAS metrics other than `Faithfulness`.
- That the structural diagnostic is the better instrument overall — it fails its own
  correct-cell positive control (1/5 and 0/2) as badly as the framework fails its.

## Effect on the paper's thesis

The paper's claim that conventional aggregate evaluation can miss structural evidence
failures **is not supported by the cross-row arm** of this experiment, which is the
arm that would most directly support it. It **is** supported, in a narrower and
differently-shaped form, by the numeric-perturbation and support-deletion arms: a
mean-over-claims faithfulness score under a majority threshold left 13 of 19
number-substitution mutants and 22 of 24 support-deletion mutants unflagged, where a
number-anchored structural check flagged them. The honest statement is about **score
aggregation diluting single-value errors**, not about blindness to table structure.
