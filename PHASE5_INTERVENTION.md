# PHASE 5 — INTERVENTION: SELECTION BUDGET

`n_results` 3 → 50 in the production selection path. One variable.

## Header

| | |
|---|---|
| commit (measurement) | `56ea5038f50937dcdc3a88fe8b9c905225b3c07e`, branch `claude-code-verification` |
| seed | 42 (held-out split; Phase 3 sample seed carried) |
| corpus | canonical 60 → 34 full-text → **31 long papers**, 3,900 anchors. 21 development / 10 held-out. |
| harness | `experiments/document_evidence_pipeline/phase5_intervention.py` |
| detector | `phase4_denominator.detect` **imported**, not reimplemented |
| assembler | `src.summarization.retrieval_aware._assemble` imported and used unmodified |
| input files | `runs/retrieval_recall/anchors.json` · `runs/prodab-20260902T004416Z/canonical/processed/chunks.json` · `runs/prodab-20260902T004416Z/canonical/chroma_db` (collection `researchgpt_papers`, 9,002 chunks) · `runs/phase5_intervention/split.json` |
| output | `runs/phase5_intervention/{PREREGISTRATION.md, split.json, results_development.json, results_heldout.json, union_sizes.json}` |

### Fidelity checks — these are what license the comparison

- The n=3 arm reproduces **Phase 2 cell A exactly: 0.0713** raw pre-assembly delivery,
  ratio-to-random 1.259 against Phase 2's reported 1.258.
- The n=50 arm reproduces **Phase 2 cell B exactly: 0.6118** raw pre-assembly.
- The assembly accounting is asserted equal to the real `_assemble` word count on every
  paper-arm pair; the run fails loudly otherwise.
- Cleaned denominator reconciles exactly: 2,691 = 3,900 − 1,209.

### Carried-forward correction, applied

Phase 1 established that `in_production_selection` is computed before `_assemble`
(`retrieval_recall.py:228`), so Phase 2's 0.6118 is an upper bound. This phase measures
delivery on the text `_assemble` actually returns. **Post-assembly is the headline.**

### A correction to PHASE4_DENOMINATOR.md, reported not applied

Phase 4's B4 keyed its flags by `(paper_id, value, section)`, which collides on 244 of the
3,900 anchors, so its numerator was counted over 3,656 keys against a denominator of 3,900.
Published: 1,167/3,900 = 29.92 %. **Correct, per anchor: 1,209/3,900 = 31.00 %**, and
cleaned n is 2,691, not 2,733. The detector itself is correct and deterministic; the
aggregation was not. Phase 4's artifact is left unmodified per this phase's constraints;
recorded in `/FINDINGS.md`.

---

## STEP 0 — PRE-REGISTRATION (reproduced verbatim, not revised)

> # PHASE 5 — PRE-REGISTRATION
>
> Written before any code was changed. Not revised afterwards.
>
> commit `56ea5038f50937dcdc3a88fe8b9c905225b3c07e` · branch `claude-code-verification` · seed **42**
>
> ## 0.1 The exact change
>
> | | |
> |---|---|
> | file | `src/summarization/retrieval_aware.py` |
> | function | `_select_legacy`, the production selection path |
> | line | 253 (call site inside the loop opened at 252) |
> | old value | `n_results=3` |
> | new value | `n_results=50` |
>
> Nothing else changes: not the 5 generic queries, not the union, not `_assemble`,
> not the 2,500-word budget, not chunking, not the retriever, not the extractor.
>
> ## 0.2 Held-out split of the 31 long papers
>
> Created now, seed 42, `random.Random(42).sample(sorted(papers), 10)`.
> **10 held-out / 21 development.** Nothing is computed on the held-out papers until 3.4.
>
> ### Held-out (10)
>    1. `0549e2e9e6bec759723fded85a49c2c076b6a978`
>    2. `2009dbb5f2903221c2452ecde1d9b5be2fb5fcfd`
>    3. `413a184de4b1c752466fbfca3cd3b1f039f99d48`
>    4. `6437463b4b13b7cc1cc75f3a9bfce4e2281ed79d`
>    5. `68f93a5921c1c6bbc5e0032f87366e46a06fded0`
>    6. `db78acdc12fda41813ab97cd7d0dd1f300e70fe6`
>    7. `ddb170b2eeb8f645b63915992196b0bcfbf3f46b`
>    8. `e6f1d66c34b525dc480ced9902cf46419b6a37fa`
>    9. `ef1e4a1671918fbed15a7a0e3996fe3dbd8bffc4`
>   10. `f42ad6e24897246e3cc55746c34f153f6bfcdc76`
>
> ### Development (21)
>    1. `1016250721201821285c39eba5ab77eddf80812e`
>    2. `141276ba659da6e5aca1d3499713104eb3ca3c78`
>    3. `4d6e977f0e5c096f334fab7b50e3e72b1979ebe9`
>    4. `4f3fca4c4fa8471dfef57857a2bfc4c86a7735f1`
>    5. `69b02cfebf3cb23711c9a261748e3de2f4442aed`
>    6. `81e060664f2446a3c2b8f6597c5ccf0984e744d5`
>    7. `93db4f9a329da15f5aa6ba6cf7fdc3903eefa89e`
>    8. `96285d75a5258dbbb883b31e23ff292605fa6f5a`
>    9. `a6d08e12d2ef4936f9a65279e73627d4f861145e`
>   10. `a6ecdf69703d98cc3e05176a930276d4480d7ced`
>   11. `a9b2a3fd6070b35eb74611255bee4f581d1274a9`
>   12. `ac8fffa1a4ae940d0810a52af515f572bfda183d`
>   13. `be7c4dc39030508deb495c9f689526ca1b4289cf`
>   14. `cf099b7cd7e8d567efbcf748d30e616b683a2f2b`
>   15. `d3b5f3c050b4e155c80620a0c1f831ee5fdb73ce`
>   16. `e0efa866a1e464e65e3a217fd67d6c18bc422302`
>   17. `eaec7401af70c7c80370d056fa847ed267a10ca6`
>   18. `f1f07a37d4cd44daab987ff19c0bcd185910f50c`
>   19. `f3b06a91470232d1587b194e2bc82fa9a50f3c9f`
>   20. `f3d7e0165df8da3fad6cbfb776e0371c31d68c48`
>   21. `fef0393e997ec51b184e39c712be63197d99fd46`
>
> ## 0.3 Predicted POST-ASSEMBLY delivery, cleaned denominator, development papers
>
> **Prediction: 0.35** (I would regard 0.28-0.45 as consistent with the hypothesis).
>
> Reasoning: at `n_results=50` the per-paper union is ~127 chunks, and canonical chunks
> average ~30 words, so the union carries ~3,800 words into a 2,500-word cap -- roughly
> two thirds survives. `_select_legacy` sorts by `chunk_index` before `_assemble`, so
> truncation keeps the earliest chunks in document order and discards the latest.
> Result-bearing content sits late in a paper, so I expect post-assembly delivery to land
> somewhat below the naive two-thirds of the ~0.59 pre-assembly cleaned figure.
>
> ## 0.4 What would falsify the budget hypothesis
>
> The budget hypothesis is falsified if **either**:
>
> 1. post-assembly cleaned delivery on the development papers fails to exceed **0.135**
>    (2x the 0.0677 baseline) -- i.e. raising the budget 3 -> 50 does not materially
>    increase what reaches the model; **or**
> 2. post-assembly cleaned delivery improves on the development papers but does **not**
>    improve on the held-out papers.
>
> Explicitly NOT falsifying: ratio-to-random staying flat. Phase 2 already established
> that budget buys volume rather than precision (ratio ~1.25 across cells A-D). A flat
> ratio with higher delivery is the predicted result, not a refutation.

---

## STEP 1 — PERSISTENCE FIX

`phase2_ladder.py` now persists the per-paper budget. Measurement logic untouched:

```diff
+    # Phase 5 step 1: persist the per-paper budget (the union size for cells A/B),
+    # which Phase 4 needed for ratio-to-random and could not recover. Output only --
+    # no measurement logic above this line is altered.
+    report["budget_per_paper"] = budget
     (OUT / "ladder.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
```

**Re-emitting Phase 2's cells from cached data: not possible.** The per-paper union sizes
were never written to disk — only their mean survives in `ladder.json` — so no cached
source exists to retro-fill. Regenerating them requires re-running the retrieval, and
re-running `phase2_ladder.py` would overwrite `runs/phase2_ladder/`, a Phase 2 artifact
this phase may not modify.

The missing figures are instead recovered from this phase's n=3 arm, which reproduces cell
A's delivery to four decimal places. **The two ratios Phase 4 marked "not recomputable":**

| cell | ratio-to-random (raw, all 31 papers) |
|---|--:|
| A (`n_results=3`) | **1.259** |
| B (`n_results=50`) | **1.227** |

Both match Phase 2's originally reported 1.258 / 1.227.

---

## STEP 2 — THE CHANGE

```diff
--- a/src/summarization/retrieval_aware.py
+++ b/src/summarization/retrieval_aware.py
@@ -250,7 +250,7 @@ def _select_content_aware(paper_chunks, collection, model, paper_id, cfg, max_wo
 def _select_legacy(paper_chunks, collection, query_vecs, paper_id, max_words):
     selected_ids = set()
     for qv in query_vecs:
-        res = collection.query(query_embeddings=[qv.tolist()], n_results=3,
+        res = collection.query(query_embeddings=[qv.tolist()], n_results=50,
                                where={"paper_id": paper_id})
         for cid in res["ids"][0]:
             selected_ids.add(cid)
```

One line. Query construction, the 5 generic queries, the union, `_assemble`, the word
budget, chunking, the retriever and the extractor are untouched.

---

## STEP 3 — MEASURE

### 3.1 / 3.2 / 3.3 — development papers (21 papers · 2,357 anchors raw · 1,622 cleaned)

| stage | denominator | n | n_results=3 | n_results=50 | change |
|---|---|--:|--:|--:|--:|
| pre-assembly | raw | 2,357 | 0.0429 | 0.5367 | +0.4938 |
| pre-assembly | cleaned | 1,622 | 0.0358 | 0.5049 | +0.4691 |
| **post-assembly** | raw | 2,357 | 0.0429 | 0.2202 | +0.1773 |
| **post-assembly** | **cleaned** | **1,622** | **0.0358** | **0.2170** | **+0.1812** |

Ratio-to-random, null computed from the chunk count actually delivered at each stage:

| stage | denominator | n_results=3 | n_results=50 |
|---|---|--:|--:|
| pre-assembly | raw | 0.870 (budget 13.6) | 1.173 (budget 134.7) |
| pre-assembly | cleaned | 0.719 (budget 13.5) | 1.090 (budget 134.2) |
| post-assembly | raw | 0.870 (budget 13.6) | 1.063 (budget 55.9) |
| post-assembly | cleaned | 0.719 (budget 13.5) | 1.049 (budget 55.1) |

At n=3 pre- and post-assembly are identical — the word budget never binds, exactly as
Phase 2 found. At n=50 the delivered chunk count falls from 134.2 to 55.1: assembly
discards ~59 % of the selected chunks.

### 3.4 — held-out papers (10 papers · 1,543 anchors raw · 1,069 cleaned)

Computed only after 3.1–3.3 were written.

| stage | denominator | n | n_results=3 | n_results=50 | change |
|---|---|--:|--:|--:|--:|
| pre-assembly | raw | 1,543 | 0.1147 | 0.7265 | +0.6118 |
| pre-assembly | cleaned | 1,069 | 0.1094 | 0.7081 | +0.5987 |
| **post-assembly** | raw | 1,543 | 0.1147 | 0.4057 | +0.2910 |
| **post-assembly** | **cleaned** | **1,069** | **0.1094** | **0.3611** | **+0.2517** |

Ratio-to-random, post-assembly cleaned: **1.502 → 1.111**.

The held-out baseline (0.1094) is three times the development baseline (0.0358). The split
was drawn at random on paper id and the two halves are not equivalent; the within-arm
before/after comparison is the valid one, and it improves in both.

### Combined, all 31 papers

| measure | n_results=3 | n_results=50 |
|---|--:|--:|
| pre-assembly raw | 0.0713 | 0.6118 |
| pre-assembly cleaned | 0.0650 | 0.5856 |
| **post-assembly cleaned** | **0.0650** | **0.2742** |
| post-assembly cleaned ratio-to-random | 1.104 | 1.081 |

### 3.5 — assembled words and truncation

| | n_results=3 | n_results=50 |
|---|--:|--:|
| mean words, development | 334.1 | 2,498.6 |
| p95 words, development | 618 | 2,500 |
| papers truncated, development | **0 / 21 (0 %)** | **20 / 21 (95.2 %)** |
| papers truncated, held-out | 0 / 10 | **10 / 10 (100 %)** |
| cleaned anchors selected then truncated out, development | 0 | **467** |
| cleaned anchors selected then truncated out, held-out | 0 | **371** |

838 cleaned anchors across all 31 papers are retrieved into the union and then discarded
by the word budget before the model sees them.

### 3.6 — per-section, cleaned, post-assembly

Development:

| section | n | n=3 delivery | n=3 ratio | n=50 delivery | n=50 ratio |
|---|--:|--:|--:|--:|--:|
| abstract | 345 | 0.0435 | 0.800 | 0.2899 | 1.220 |
| experimental_setup | 305 | 0.0295 | 0.556 | 0.1082 | 0.564 |
| method | 287 | 0.0383 | 0.873 | 0.1533 | 0.901 |
| references | 187 | 0.0428 | 0.836 | 0.0909 | **0.427** |
| results | 156 | 0.0192 | 0.525 | 0.2949 | **1.510** |
| conclusion | 78 | 0.0513 | 0.785 | 0.2564 | 1.229 |
| discussion | 18 | **0.0000** | **0.000** | 0.3889 | 1.375 |

Held-out:

| section | n | n=3 delivery | n=3 ratio | n=50 delivery | n=50 ratio |
|---|--:|--:|--:|--:|--:|
| method | 223 | 0.1390 | 1.551 | 0.3587 | 1.037 |
| results | 170 | 0.0824 | 0.864 | 0.2529 | 0.850 |
| discussion | 96 | 0.2604 | 3.725 | 0.3854 | 1.688 |
| references | 77 | 0.0779 | 1.253 | 0.1299 | **0.364** |
| experimental_setup | 76 | 0.1053 | 1.974 | 0.5000 | 2.020 |
| conclusion | 51 | 0.1373 | 2.637 | 0.4706 | 1.174 |
| abstract | 32 | 0.2188 | 3.381 | 1.0000 | 2.664 |

**Do references, conclusion and discussion leave 0.000×?** In this arm only `discussion`
on development papers sat at 0.000×, and it leaves it (0.3889, ratio 1.375). This is not
the like-for-like comparison it appears to be: Phase 3/4's 0.000× figures were measured on
**cell C** — the per-anchor field query at `n_results=3` — not on the production cell A
path measured here. On the production path those sections were never at zero. The honest
statement is that the one 0.000× cell in *this* arm is gone, and Phase 3's cell C zeros
were not retested.

`references` is the one section whose ratio-to-random falls sharply (0.836 → 0.427
development; 1.253 → 0.364 held-out). Its absolute delivery still roughly doubles — it
simply grows far more slowly than the budget does.

### 3.7 — latency per paper, measured not estimated

Wall-clock for the full selection call (5 Chroma queries, union, sort, assemble), per paper:

| | n_results=3 | n_results=50 |
|---|--:|--:|
| mean, development | 0.048 s | 0.053 s |
| median, development | 0.048 s | 0.053 s |
| max, development | 0.072 s | 0.070 s |
| mean, held-out | 0.087 s | 0.053 s |
| median, held-out | 0.043 s | 0.051 s |

**+0.005 s per paper at the median.** The held-out n=3 mean is inflated by a single 0.47 s
first-call outlier; its median is 0.043 s. Latency is not a consideration at this scale.

---

## STEP 4 — ACCOUNTING

### 4.1 Prediction vs outcome, both quoted

> **Prediction: 0.35** (I would regard 0.28-0.45 as consistent with the hypothesis).

**Outcome: 0.2170** post-assembly cleaned delivery on development papers.

**The prediction missed, low, outside its own stated range.** The mechanism in 0.3 was
right and the magnitude was wrong: it assumed roughly two thirds of the union's words
survive the cap, when in practice only ~41 % of the *selected chunks* survive (134.2 →
55.1). The stated risk — that document-order truncation discards late, result-bearing
content — was real and larger than allowed for. Held-out landed at 0.3611, inside the
predicted range, but the prediction was made for development papers and is scored against
them.

### 4.2 Does precision move, or only volume?

**Only volume.** Combined post-assembly cleaned ratio-to-random goes **1.104 → 1.081** —
flat, marginally down. The halves move in opposite directions and cancel: development
0.719 → 1.049 (up, crossing the random line), held-out 1.502 → 1.111 (down). Delivery
rises 4.2× while the ratio does not move. This is Phase 2's finding — budget buys volume,
not precision — reproduced under a real assembly constraint.

### 4.3 How much of the pre-assembly gain does `_assemble` give back?

**Most of it.**

| | pre-assembly gain | post-assembly gain | given back | % of gain lost |
|---|--:|--:|--:|--:|
| development | +0.4691 | +0.1812 | −0.2879 | **61.4 %** |
| held-out | +0.5987 | +0.2517 | −0.3470 | **58.0 %** |
| combined | +0.5206 | +0.2092 | −0.3114 | **59.8 %** |

Roughly 60 % of everything the larger budget retrieves is discarded by the 2,500-word
assembly cap before the model sees it, in `chunk_index` order — the end of the document
goes first. **That names the next lever: the word budget at `configs/config.yaml:37`, not
the retrieval budget.** Recorded in `/FINDINGS.md`. Not fixed here — one variable per phase.

### 4.4 What did not improve

- **Ratio-to-random.** Flat at ~1.08–1.10 combined. No precision gain anywhere in the pooled
  figures.
- **`experimental_setup`**, development: 0.556 → 0.564. Delivery rose 3.7×, the ratio did
  not move at all.
- **`method`**, held-out: 1.551 → 1.037 — relative precision fell.
- **`results`**, held-out: 0.864 → 0.850, flat, despite delivery tripling. The strong
  development result (0.525 → 1.510) does **not** replicate on held-out.
- **`references`** ratio falls hard in both halves while its absolute delivery doubles — the
  extra budget is still spending itself on bibliography.
- **Nothing about the 5 generic queries changed.** The Phase 2/3 finding that they cannot
  name a metric or dataset is untouched by this intervention.

---

## STEP 5 — SHIP OR HOLD

VALIDATED requires post-assembly cleaned delivery to improve on **both** halves, with
neither 0.4 falsification condition firing.

| condition | result |
|---|---|
| development post-assembly cleaned improves | 0.0358 → **0.2170** ✓ |
| held-out post-assembly cleaned improves | 0.1094 → **0.3611** ✓ |
| 0.4(1) dev delivery must exceed 0.135 | 0.2170 > 0.135 ✓ not falsified |
| 0.4(2) dev improves but held-out does not | held-out improves ✓ not falsified |

**VALIDATED.** The `src` change ships as its own commit; harness and artifacts follow in a
separate commit.

---

## VERDICT

INTERVENTION VALIDATED — post-assembly delivery 0.0358 -> 0.2170 cleaned, held-out 0.1094 -> 0.3611
