# MEDICAL CORPUS RE-CHUNK — Phase 3 re-measured on grounded chunks

Branch `claude-code-verification` · HEAD `dc7ee24` (+ this change) · 2026-09-03
Six stages unchanged. No retrieval / selection / gate / scoring-weight code touched.
Production `configs/` not modified. Seeded path (`temperature 0`, `seed 42`).
Medical corpus isolated from the canonical 60 and `data_test` at every step — all output
under `experiments/document_evidence_pipeline/runs/medical_rechunk/`; `data/processed/` was
not written.

Harnesses: `medical_rechunk.py` (re-chunk + STEP 1), `medical_rechunk_measure.py` (3.3b/3.3c).

## Why

The medical chunks were legacy schema (no `block_type`, no `section`). `content_aware`
detected that and fell back to `legacy` — correct behaviour, but it meant **16 of the 19
full-text papers in a run labelled `content_aware` were legacy runs**. The corpus users
actually query received nothing from Phase 3. This re-runs Stage 2 on the 19 full-text
papers with the grounded, provenance-aware chunker already used for the canonical corpus
and `data_test` (same chunker, `CHUNK_WORDS=220` / `CHUNK_OVERLAP=40`, no parser change),
then re-measures Phase 3 with **both selectors on the new chunks**.

---

## STEP 1 — the re-chunk produced structure (verified before any measurement)

Grounded chunker on all 50 medical papers; structure checked on the 19 full-text.
Section/`block_type` here come from **PyMuPDF heuristics** — triage established there is no
JATS and no LaTeX; these are publisher-typeset clinical PDFs.

### block_type distribution (4329 full-text chunks)

| block_type | count | share |
|---|--:|--:|
| paragraph | 3977 | 91.9 % |
| heading | 188 | 4.3 % |
| figure_caption | 101 | 2.3 % |
| **table** | **63** | **1.5 %** |

### section values

73 distinct. Canonical labels dominate — `references` 865, `method` 733, `body` 446,
`introduction_related_work` 369, `discussion` 324, `results` 262, `abstract` 156,
`experimental_setup` 129, `conclusion` 111, `limitations` 5 — but ~55 of the 73 are
numbered sub-headings that the heading regex promoted to section labels
(`"3.4. training strategy"`, `"2.1.1 datasets"`, `"10 suppl:s18-25 doi:…"`). Junk/unparsed
(`body` / empty): **446 / 4329 (10 %)** by the strict definition; higher if the numbered
sub-headings are counted as noise.

### per-paper table / results-heading presence

| paper | chunks | `table` blocks | results heading |
|---|--:|--:|:--|
| 9879e1cce991 | 203 | 15 | results, discussion |
| dddc6e8d0623 | 132 | 4 | — |
| 67d7236f524d | 238 | 8 | results, experimental_setup, discussion |
| 7e5f30e77806 | 247 | 3 | results, experimental_setup, discussion |
| 33fea4124ef0 | 428 | 0 | results |
| fdd51ec02684 | 466 | 6 | results, experimental_setup, discussion |
| 295fc8094b39 | 88 | 1 | — |
| c458eeae3a91 | 329 | 14 | results, discussion |
| 330377dabc3f | 379 | 6 | experimental_setup, discussion |
| 913b6b3cb4c4 | 127 | 0 | results, discussion |
| d1f8a7f02d6c | 6 | 0 | — |
| 7cc53dfe80d5 | 212 | 0 | discussion |
| 506958c71c4b | 150 | 4 | results, discussion |
| f09cd60900e0 | 28 | 0 | — |
| f82c20907921 | 582 | 2 | results, experimental_setup, discussion |
| dd7cacac10d3 | 44 | 0 | discussion |
| 20f7c8717108 | 208 | 0 | discussion |
| da119f5f19f3 | 109 | 0 | results, discussion |
| 4e8aa13b4455 | 353 | 0 | — |

- papers with ≥ 1 `table` block: **10 / 19**
- papers with a recognised results/evaluation heading: **14 / 19**
- total `table` blocks: **63**

### STOP condition — NOT met, with a caveat

`table` blocks are **not** near zero (63 across 10 papers), so the run continued. But these
are **caption-anchored** blocks — `blocks_from_pdf` labels a block `table` only when its
first line starts `"table "` (i.e. a "Table 1. …" caption line), not by recognising tabular
layout. So `content_aware`'s table-structure signal on this corpus is **real but thin**:
present on 10/19 papers, ~3 blocks/paper median, and it is caption text, not extracted
cells. This is weaker than the canonical corpus and is the honest limit on how much
`content_aware` can do here. It is a Stage-2 parsing property, recorded, not a blocker.

---

## STEP 2 — what the re-chunk invalidates

New chunk IDs (`{block_id}#{i}`) mean **no pre-re-chunk medical number is comparable to a
post-re-chunk one**. Explicitly:

- **Medical extraction cache** (`data/processed/extraction_cache.json`, 415 entries):
  confirmed not reusable — entries carry no `_prompt_version` and no `_text_hash` in the
  current format, `EXTRACTION_PROMPT_VERSION` is now `2026-09-03.numpredict-deadline`, and
  the assembled selected-text differs anyway. The measurement ran `cache={}` (clean
  re-extraction both arms) regardless.
- **`data/processed/paper_summaries.json`** — the on-disk baseline used as the "before" in
  the last medical regression check — is **stale**. It was produced from the 182-chunk
  legacy corpus. Not a valid "before" for anything here.
- **Any prior medical delivery / coverage / fallback figure** (e.g. "16/19 legacy-schema
  fallback", the old per-field percentages) was computed on the old chunks and is **not
  comparable**. The baseline in this report is **legacy-on-new-chunks**, measured fresh.

### chunk count

| | chunks | papers | note |
|---|--:|--:|---|
| old (legacy schema) | 182 | 50 | ~3.6 chunks/paper — very coarse |
| new (grounded) | 4383 | 50 | 4329 full-text + 54 abstract; ~228 full-text chunks/paper |

The ~24× increase is the grounded chunker (220-word chunks within blocks) applied to long
clinical PDFs. It is the reason a fixed passage budget delivers a small fraction below.

---

## 3.3b — anchor-chunk delivery, both selectors on the NEW chunks

Anchor set built with the same rule as canonical (`src/evidence/anchors.find_anchors`;
table vs prose via `block_type == "table"` OR a ≥ 6-number / ≤ 1-verb ±220-char window;
surplus table cells capped at 60/paper). **3117 anchors — 991 table, 2126 prose.**

| variant | mean passages | all anchors | table | prose |
|---|--:|--:|--:|--:|
| **legacy** (baseline, new chunks) | 14.2 | **6.06 %** | 4.64 % | 6.73 % |
| **content_aware@10** (new chunks) | 12.4 | **13.06 %** | **15.94 %** | **11.71 %** |

- `content_aware` beats `legacy` on **every** split: ×2.16 all, **×3.44 table**, ×1.74 prose.
- Same direction as the canonical result — `content_aware`'s number/table-aware scoring
  pulls anchor-bearing chunks that `legacy`'s 5 fixed queries miss.
- **Absolute delivery is low** (13 %). With ~228 chunks/paper and a ~12-passage budget,
  most anchors are never selected. This is a corpus property (very long PDFs, fine
  chunks), not a selector regression; a higher budget would raise it at a context cost
  not evaluated here.

### legacy-schema fallback count: **0** ✓

Both coverage arms report `legacy-schema fallback count: 0`. The re-chunk took on **all 19**
papers — `content_aware` now runs as `content_aware`, not `legacy_fallback`, on this corpus.

---

## 3.3c — extraction coverage, both selectors, 19 full-text papers, seeded, clean cache

| metric | legacy (new chunks) | content_aware@10 (new chunks) |
|---|--:|--:|
| mean non-empty fields / paper | 8.32 | **8.84** |
| method | 18/19 (95 %) | 18/19 (95 %) |
| datasets | 16/19 (84 %) | 16/19 (84 %) |
| metrics | 9/19 (47 %) | **14/19 (74 %)** |
| results | 7/19 (37 %) | **13/19 (68 %)** |
| limitations | 18/19 (95 %) | 18/19 (95 %) |
| conformance | 19 conformant | 18 conformant / 1 salvaged |
| circuit-breaker fallbacks | 0 | 0 |
| `_extraction_failed` | 0 | 0 |
| runtime | 26 s/paper (492 s) | 29 s/paper (543 s) |

### papers that changed under content_aware (vs legacy, both on new chunks)

| paper | legacy | ca@10 | | conformance |
|---|--:|--:|:--|:--|
| 33fea4124ef0 | 8 | 10 | better | conformant |
| 7e5f30e77806 | 8 | 10 | better | conformant |
| 913b6b3cb4c4 | 8 | 10 | better | conformant |
| 506958c71c4b | 8 | 10 | better | conformant |
| c458eeae3a91 | 9 | 10 | better | conformant |
| f82c20907921 | 8 | 9 | better | conformant |
| 20f7c8717108 | 8 | 9 | better | conformant |
| 7cc53dfe80d5 | 7 | 8 | better | conformant |
| **295fc8094b39** | **10** | **8** | **WORSE** | **salvaged** |

**8 better, 1 worse.** The one regression, `295fc8094b39` (88 chunks, 1 `table` block, no
results heading), drops 10 → 8 and lands `salvaged` — `content_aware`'s number-aware scoring
pulls a denser, less prose-like selection that the extractor conforms less cleanly on. Same
failure shape as `0549e2e9` on the canonical corpus; bounded (salvaged, not failed).

### WATCH items

- **`9879e1cce9`** (the degenerate-generation paper): **conformant** in both arms,
  `done_reason == "stop"`, `n = 10` fields, `_extraction_failed = False`. It did **not**
  hang — `num_predict` + the wall-clock deadline (3.2/3.2d) bound it. (Per-paper elapsed is
  not recorded on the normal-completion path — only on a deadline hit — so no seconds figure;
  the whole 19-paper arm ran in 492–543 s, so no single paper stalled.)
- **Domain routing** (biomed vs cs_ml), on the assembled text actually handed to the
  extractor:
  - legacy selection: **cs_ml 16 / biomed 3**
  - content_aware@10 selection: **biomed 8 / cs_ml 11**
  - prior (old chunks): 15 / 4
  Re-chunking + `content_aware` selection surfaces more clinical section text, flipping 5
  papers to the biomedical prompt variant. Not an error — the variant switch is the intended
  content-adaptive behaviour — but it means the two arms are not extracting under identical
  prompts, which is part of why `content_aware` lifts `metrics`/`results` here.
- **Field-presence determinability**: all 19 are `representation: pdf`. **0 / 19
  determinable** — no JATS/structured representation on this corpus. Three-way split:
  **determinable-present 0 / determinable-absent 0 / undeterminable 19.** PyMuPDF gives
  heuristic section headings only; these are a **lower bound** on presence, **not a
  denominator**. `undeterminable` is not upgraded to `determinable` on the strength of a
  regex heading match. The per-field percentages above are the usable numbers, over all 19,
  with no presence normalisation.

---

## Does content_aware help on this corpus?

**Yes — and this is the first comparable content_aware result for it** (both arms on the
same new chunks, clean cache, seeded):

- anchor delivery ×2.2 overall, ×3.4 on table anchors, ×1.7 on prose
- `metrics` coverage 47 % → 74 %, `results` 37 % → 68 %, mean fields 8.32 → 8.84
- 8 of 19 papers improve, 1 regresses (bounded: `salvaged`), 10 unchanged
- 0 legacy-schema fallbacks, 0 circuit-breaker fallbacks, 0 `_extraction_failed`,
  `9879e1cce9` bounded

**Honest caveats:**
1. Absolute delivery is low (13 %) — the grounded chunker yields ~228 chunks/paper for
   these long PDFs against a ~12-passage budget. The *gain* is real; the *ceiling* on this
   corpus is set by budget-vs-corpus-length, not the selector.
2. `table` structure is caption-prefix heuristic only (63 blocks, 10/19 papers), not
   extracted cells — thinner signal than canonical.
3. The `metrics`/`results` lift is partly the **domain-routing flip** (3 → 8 biomed):
   `content_aware` and `legacy` are not running the same extraction prompt here.
   **Quantified in `MEDICAL_SELECTOR_CONTROL_REPORT.md`** (3-arm control, legacy +
   pinned routing): of the confounded +26pp metrics / +32pp results, the selector's
   isolated contribution is **+16pp / +26pp**; routing accounts for **+11pp / +5pp**.
   Do not quote the confounded figure as a selection result.
4. `content_aware` on this corpus was previously **not measurable** — it fell back to
   `legacy` on 16/19 papers. That is now fixed; the numbers above are the real ones.

**Recommendation:** the grounded re-chunk is a prerequisite for `content_aware` to do
anything on the medical corpus, and with it `content_aware@10` is a net gain on every
measured axis. It is not free — routing shifts and one paper regresses to `salvaged` — so
the same staging-first path applies: enable behind the existing flag, watch
`295fc8094b39`-class regressions and the biomed-routing share, before any production flip.
The delivery ceiling (caveat 1) is a separate follow-up (budget tuning for long-PDF
corpora), not part of this change.

---

## Tests / invariants

- **`tests/test_pipeline.py` + `tests/test_anchors.py`: 15/15** (6 + 9).
- **Experiment suite `tests/test_pipeline_units.py`: 42/42.**
- **12/12 staging invariants PASS** (`staging_run.py`, run `staging-20260903T094118Z`),
  monitor `overall: OK`, `DECISION: STAGING_PASS`, 0 pipeline errors, runtime 229 s. No new
  invariants added. (Staging runs on `data_test`, not the medical corpus — the medical
  re-chunk output stayed isolated under `runs/medical_rechunk/` and was not part of this.)
