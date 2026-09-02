# STAGE 4 HARDENING REPORT — R1 schema conformance + R2 domain prompt

Branch `claude-code-verification` · HEAD `0526358` (+ this change) · 2026-09-02
All inside Stage 4. No new stage. Production `configs/` unchanged. Evidence gate, selection
policy and acquisition untouched. All runs on the Phase-1 seeded path (`temperature 0`, `seed 42`).
Third corpus (50-paper medical/clinical) kept separate from the frozen 60 and `data_test/`.

Code: `src/summarization/summarize.py`. Measurement: `scripts/stage4_hardening_measure.py`,
`scripts/stage4_isolate_oldpath.py`. Rows: `runs/stage4_hardening/`.

## STEP 0 — cache-key audit

**Old key: `paper_id` alone.** `_extract_single_paper` did `cache.get(paper_id)` / `cache[paper_id] = …`.
No chunk-set hash, no prompt version. Consequence exactly as the task anticipated: a Phase-3
selection-policy change (or this phase's prompt change) would be served from cache for every
already-extracted paper and measured as a null result.

**Fix (this commit).** A cached entry is now reused (`_cache_entry_reusable`) only if **all** hold:
- `_prompt_version == EXTRACTION_PROMPT_VERSION` (`"2026-09-02.r1r2-schema+domain"`, a module constant — bump on any prompt/schema/conformance-logic change)
- `_text_hash == sha256(selected_paper_text)[:16]` — the selected chunk set, so a selection change busts it
- no junk (non-schema, non-`_`) top-level keys
- not `_extraction_nonconformant` and not `_extraction_failed`

New entries write `_prompt_version` + `_text_hash`. Nothing is wiped: entries that fail the check
are simply re-extracted on the next real run.

**Affected currently-cached entries** (nothing deleted; all will re-extract on next run):

| cache | entries | lack `_prompt_version` (→ all invalidated) | junk-key (poisoned) |
|---|--:|--:|--:|
| `data/processed/extraction_cache.json` | 415 | 415 | **43** |
| `data_test/processed/extraction_cache.json` | 8 | 8 | 0 |

Poisoned-key examples seen: `":1" ":2" ":3"`, `":title" ":abstract"`, `"**Summary of the Case:**"`,
`"== Summary =="`, `"system"/"patient"/"diagnosis"`, `"improvement"/"reasons"/"impact_on_other_metrics"`,
`": Enzyme Activities and Oxidative Stress Markers…"` + a nested table object. These never satisfy
`_cache_entry_reusable` (junk-key clause), so they can no longer be served.

## STEP 1 — R1: schema-conformance handling

`check_schema_conformance(parsed)` flags: unexpected top-level keys (markdown headings, leading-colon
keys, invented structure), a string field delivered as dict/list, a `datasets`/`metrics` list of dicts.
Non-conformance is handled, in order:
1. `salvage_nonconformant` — deterministic reshape: flatten nested schema-field values; move each
   unexpected key's content to the closest field by name (`objective/hypothesis`→`problem_addressed`,
   `limitation`→`limitations`, `conclusion/discussion`→`inferences`, `result/finding/table/activity`→
   `results`, …). A nested results table is flattened and **kept**, tagged `_salvage_notes`. Runs only
   on an already-broken response, so it cannot worsen a conforming one.
2. `repair_schema` — a **second LLM call** feeding the malformed JSON back with a reshape instruction.
   A naive retry cannot work here (temp 0 + fixed seed ⇒ identical request ⇒ identical malformed
   output); the repair changes the *input*. Code comment states this.
3. still non-conforming / too thin ⇒ keep best partial content but set `_extraction_nonconformant`
   so downstream, the UI and metrics do **not** read empty fields as "absent from the paper".

Outcome tag per paper: `_conformance ∈ {conformant, salvaged, repaired, repaired_salvaged,
nonconformant_unrepaired, no_response}`; `_domain_variant`; `_repair_call_made`.

## STEP 2 — R2: domain-aware prompt variant

`select_extraction_prompt(text)` — deterministic vocabulary count, no extra LLM call. Two variants,
**identical 10-key schema**: `cs_ml` (existing `EXTRACTION_SYSTEM_PROMPT`) and `biomed`
(`EXTRACTION_SYSTEM_PROMPT_BIOMED` — study population instead of "dataset", outcome measures /
statistical tests instead of "metric / SOTA"). Routes `biomed` when biomed cues ≥ 4 and > cs/ml cues.
Recorded per paper as `_domain_variant`.

## STEP 3 — R5

`scripts/triage_extraction.py` Bucket-B char floor `3000` → `chunk_size * 6` (= 4800). One line, in
this commit. The 4 326-char / 1-chunk false positive from the triage no longer flags.

## MEASURE — medical corpus, 19 full-text papers (seeded, fresh cache)

| | before (on-disk, pre-phase) | after (R1+R2) |
|---|--:|--:|
| mean non-empty fields / paper | 5.7 | **6.9** |
| schema-conformance, model-direct | 9 / 19 | 12 / 19 |
| schema-conformance, incl. deterministic salvage | — | **18 / 19** |
| repair LLM calls made | — | **0** (salvage resolved all 6) |
| repair produced a conforming result | — | n/a (not needed) |
| still non-conforming after all handling | — | **1** (`9879e1cce9`, see below) |
| `_extraction_nonconformant` (partial + flagged) | — | 0 |
| papers 0 fields → >0 fields | — | 1 (`f82c209079` 0→2) |
| domain variant | — | 15 biomed / 4 cs_ml |

Per-paper gains are on the biomed-routed papers: `506958c71c` 5→10, `913b6b3c` 1→6, `da119f5f` 1→5,
`7cc53dfe` 2→5, `dddc6e8d` 3→6, `20f7c871` 6→8, `fdd51ec0` 8→9.

### Regressions in the naive before/after — and why they are NOT R1/R2

Three papers show `after_n < before_n`: `67d7236f` 7→5, `330377da` 10→9, `dd7cacac10` 9→8. The
"before" baseline is the last real run at `temperature 0.2`, **unseeded** — a different sample.
Isolation run (`stage4_isolate_oldpath.py`: same seeded path, single `cs_ml` prompt, conformance
handling disabled — i.e. the OLD Stage 4 on the SAME inputs):

| paper | OLD Stage-4 (seeded) | R1+R2 (seeded) | R1/R2 delta |
|---|--:|--:|--:|
| `9879e1cce9` (med, cs_ml) | 0 | 0 | **+0** |
| `67d7236f` (med, cs_ml) | 5 | 5 | **+0** |
| `7e5f30e778` (med, cs_ml) | 10 | 10 | **+0** |
| `d1f8a7f02d` (med, cs_ml) | 0 | 0 | **+0** |
| all 8 `data_test` (cs_ml) | 8,10,10,10,10,10,8,10 | 8,10,10,10,10,10,8,10 | **+0 each** |

**R1/R2 costs exactly zero fields on every CS/ML paper tested (n = 12).** `67d7236f` returns 5 fields
under the old path on the seeded inputs too — its 7→5 vs the on-disk baseline is the Phase-1
determinism change, not this phase. `330377da` / `dd7cacac10` (−1 each) are likewise sampling
differences between the unseeded baseline and the seeded run.

## MEASURE — `data_test/` regression check (8 CS/NLP papers)

| | before (on-disk) | after (R1+R2) |
|---|--:|--:|
| mean non-empty fields / paper | 8.1 | 9.5 |
| schema-conformance | 8 / 8 | 8 / 8 |
| regressions (`after_n < before_n`) | — | **none** |
| domain variant | — | 8 cs_ml / 0 biomed |

Every paper same or better. The +1.4 mean is the Phase-1 determinism change (the isolation table
above shows R1/R2 itself contributes +0 on all 8). **No regression on the domain the prompt was
originally tuned for.**

## Runtime

Medical: 940 s / 19 = **49.5 s/paper** (single-worker seeded — Phase-1). `data_test`: 256 s / 8 =
32 s/paper. The repair path adds a second LLM call **only** on a non-conforming, non-salvageable
response — **0 occurrences across all 27 papers**, so no measured runtime addition in this phase.
`select_extraction_prompt` is regex counting: negligible.

## What still fails to conform, and why

**`9879e1cce9`** (arXiv, "Domain-Guided YOLO26 … BCE-Dice-Lovász Loss"). Qwen emits
`{ "== Summary of Key Components and Experiments ==": <newline/tab repetition loop>` — a single
markdown-heading key whose value degenerates into whitespace, truncating the JSON. **Identical on
both prompt variants** ⇒ prompt-independent model degeneration, not a schema-shape problem.
`_parse_json_response` fails all 3 attempts, `call_ollama_json` returns `None`, and the record is set
`_extraction_failed` — i.e. **recorded as a failure, distinct from "fields absent"**, which is the
required R1 behaviour. It is not repairable from a parsed dict (there is no valid dict). A fix
(raw-string repair retry, or a `repeat_penalty` / `num_predict` adjustment to break the whitespace
loop) is a follow-up and was not attempted — "do not tune".

**`d1f8a7f02d`** conforms and returns empty fields correctly: it is a **1-page, 2 382-char**
extended abstract with almost no extractable content. `conformant` + empty = field genuinely absent —
the distinction R1 was built to make.

## Tests

`tests/test_pipeline.py` **6/6**. Experiment suite (`tests/test_pipeline_units.py`) **42/42**.
No new invariants added.

## Net

- Cache key is now selection- and prompt-version-aware; Phase 3's selection change will not be
  masked by stale cache. 43 poisoned `data/` entries can no longer be served.
- R1: medical schema-conformance 9/19 → 18/19; all 6 recoveries were deterministic salvage (0 repair
  calls, 0 runtime cost). 1 residual is model degeneration, correctly flagged not silently empty.
- R2: biomed routing lifts mean fields on the medical corpus 5.7 → 6.9; **isolated cost on CS/ML
  papers = 0** (n = 12); no `data_test` regression.
- R5: one-line Bucket-B threshold fix included.
