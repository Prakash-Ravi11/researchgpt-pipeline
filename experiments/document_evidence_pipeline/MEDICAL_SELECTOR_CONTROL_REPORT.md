# Medical `content_aware` gain — 3-arm routing control

Branch `claude-code-verification` · 2026-09-04
Six stages unchanged. `configs/` not modified. `latex_ingestion_enabled` stays
`false`. Seeded (temp 0, seed 42), clean extraction cache per arm. Medical corpus
only — not pooled. `medical_selector_control.py`, isolated to
`runs/medical_selector_control/`.

## Defect this addresses

`MEDICAL_RECHUNK_REPORT.md` reported `content_aware@10` lifting the re-chunked
medical corpus from `metrics 47% / results 37%` to `74% / 68%` (≈ +27pp / +31pp).
But `content_aware` selection surfaces more clinical section text, which flips the
Stage-4 domain prompt variant on 5 papers: routing goes `cs_ml 16 / biomed 3` →
`biomed 8 / cs_ml 11`. Phase 2.6 measured the biomed variant as a **real gain on
clinical papers**. So the headline confounds two changes — *which passages the
extractor sees* and *which prompt it runs* — and cannot on its own support a
selection claim.

## Design — three arms, same 19 re-chunked papers, same Chroma index

| arm | selection | domain routing |
|---|---|---|
| **1** | legacy | natural (routed on the assembled text) |
| **2** — the control | legacy | **pinned** per paper to whatever arm 3 assigned |
| **3** | content_aware@10 (+ circuit breaker, as deployed) | natural |

- **arm 3 − arm 2** = the selector's isolated contribution (identical routing on
  both; only the passage selection differs).
- **arm 2 − arm 1** = the prompt-variant / routing component (identical legacy
  selection on both; only the prompt differs).

Arm 2 is a per-paper serial loop with `select_extraction_prompt` monkeypatched to
return the pinned variant; everything else (priming, seed, `num_ctx`, reservation,
deadline, schema repair) is the production path. Circuit breaker is a no-op in
legacy mode, so arms 1 and 2 get identical treatment apart from the pinned prompt.
No `src/` change.

## Result

| metric | 1 legacy / natural | 2 legacy / **pinned** | 3 ca@10 / natural |
|---|--:|--:|--:|
| mean non-empty fields / paper | 8.32 | 8.47 | 8.84 |
| method | 18/19 (95%) | 18/19 (95%) | 18/19 (95%) |
| datasets | 16/19 (84%) | 16/19 (84%) | 16/19 (84%) |
| **metrics** | **9/19 (47%)** | **11/19 (58%)** | **14/19 (74%)** |
| **results** | **7/19 (37%)** | **8/19 (42%)** | **13/19 (68%)** |
| limitations | 18/19 (95%) | 18/19 (95%) | 18/19 (95%) |
| routing (biomed / cs_ml) | 3 / 16 | 8 / 11 | 8 / 11 |
| conformance | 19 conformant | 19 conformant | 18 conformant / 1 salvaged |
| circuit-breaker fallbacks | 0 | 0 | 0 |
| `_extraction_failed` | 0 | 0 | 0 |

### Decomposition (percentage points)

| field | confounded (3−1) | routing (2−1) | **selector isolated (3−2)** |
|---|--:|--:|--:|
| metrics | +26pp | +11pp | **+16pp** |
| results | +32pp | +5pp | **+26pp** |

*(The confounded figure is +26pp / +32pp in this fresh seeded run vs the +27pp /
+31pp quoted in `MEDICAL_RECHUNK_REPORT.md` — reproducibility drift of ~1pp from a
separate clean-cache run, not a change of substance.)*

## Outcome: **improvement shrinks → partly routing; both components reported**

The selection improvement **survives the control** but is smaller than the
headline:

- **`results`** — the selector carries **+26pp of the +32pp** (81%). Routing adds
  only +5pp (one paper, `f82c20907921`). This is a genuine, qualified selection
  improvement.
- **`metrics`** — the selector carries **+16pp of the +26pp** (≈62%). Routing
  adds +11pp — a larger share, and not clean (see per-paper below): the biomed
  prompt helps 3 papers and *hurts* 1 on legacy-selected text.

Neither field's headline is safe to quote as a pure selection result; the
+16pp / +26pp isolated figures are.

### Per-paper movement (papers whose `metrics`/`results` presence changes)

`metrics` (9 → 11 → 14):

| paper | 1→2→3 | variant 1→2→3 | note |
|---|:--|:--|---|
| 506958c71c4b | · → Y → Y | cs_ml → biomed | routing gain |
| 913b6b3cb4c4 | · → Y → Y | cs_ml → biomed | routing gain |
| f82c20907921 | · → Y → Y | cs_ml → biomed | routing gain |
| c458eeae3a91 | **Y → · → Y** | cs_ml → biomed | routing **loses** it, selector recovers it |
| 20f7c8717108 | · → · → Y | cs_ml → biomed | selector gain (biomed alone did nothing) |
| 33fea4124ef0 | · → · → Y | **biomed → cs_ml** | selector gain **against** the routing flip |
| 7e5f30e77806 | · → · → Y | cs_ml → biomed | selector gain |
| 295fc8094b39 | **Y → Y → ·** | cs_ml (all) | selector **regression** (lands `salvaged`) |

`results` (7 → 8 → 13):

| paper | 1→2→3 | variant 1→2→3 |
|---|:--|:--|
| f82c20907921 | · → Y → Y | cs_ml → biomed  (routing gain) |
| 33fea4124ef0 | · → · → Y | biomed → cs_ml  (selector gain against the flip) |
| 506958c71c4b | · → · → Y | cs_ml → biomed |
| 913b6b3cb4c4 | · → · → Y | cs_ml → biomed |
| c458eeae3a91 | · → · → Y | cs_ml → biomed |
| 7e5f30e77806 | · → · → Y | cs_ml → biomed |

`33fea4124ef0` gains both fields under content_aware selection *while routed away
from biomed* — an unambiguous selector effect. `295fc8094b39` is the known
`salvaged` regression (same failure shape as `0549e2e9` on canonical); bounded,
not failed.

## Caveats

1. The pinned variant in arm 2 is `content_aware`'s routing decision, which was
   itself computed on the richer `content_aware`-selected text. Arm 2 applies it
   to legacy-selected text. This is the control the task specifies and it isolates
   the selector cleanly (arm 3 − arm 2: routing identical by construction). The
   arm 2 − arm 1 delta is therefore a reasonable *estimate* of the routing
   component, not a perfectly clean one — the biomed cue counts that triggered the
   flip are lower on legacy text.
2. Absolute coverage is still budget-limited (~228 chunks/paper vs ~12-passage
   budget) — the `MEDICAL_RECHUNK_REPORT.md` ceiling caveat is unchanged.
3. One `salvaged` regression under content_aware (`295fc8094b39`) persists across
   this control.

## Files

- `medical_selector_control.py` — the 3-arm harness
- `runs/medical_selector_control/` — `arm_{1,2,3}_*.json`, `summary.json`, `run.log`
- reads `runs/medical_rechunk/processed/chunks.json` + `runs/medical_rechunk/chroma_db`
  (from `medical_rechunk.py` / `medical_rechunk_measure.py`)

## What may be quoted

- **Selector isolated contribution on the re-chunked medical corpus:
  `metrics` +16pp (58% → 74%), `results` +26pp (42% → 68%), seeded, 19 papers.**
- The routing/prompt-variant component (`metrics` +11pp, `results` +5pp) is
  reported separately, not folded into the selection figure.
- The pre-control +26pp / +32pp (≈ the previously-quoted +27pp / +31pp) is
  **diagnostic history** — it is the sum of the two components and is not a
  selection result.
