# CONTEXT BUDGET + CONFORMANCE CIRCUIT BREAKER

Branch `claude-code-verification` · HEAD `5ecef20` (+ this change) · 2026-09-03
All inside Stage 4 / the Ollama client (`src/summarization/summarize.py`,
`src/summarization/retrieval_aware.py`). Production `configs/config.yaml` not modified.
Selector, scoring weights, selection budgets, prompt and repair path unchanged. Seeded
path (`temperature 0`, `seed 42`). Harnesses: `verify_deadline.py`, `context_budget_measure.py`.

## 3.2b — output budget is now a fixed reservation, not a remainder

### Root cause (from DIAG_0549E2E9_REPORT.md)

`estimate_num_ctx` sized the context window from input length; output headroom was therefore
`window − input`, which **inversely couples** the two — a shorter input buys the model more
room to generate. On `0549e2e9` @10 (1282-token, 93 %-table input, ~1278 tokens of headroom)
the model spent that headroom transcribing every ablation-table cell into nested JSON: valid
JSON, **zero schema fields**. `content_aware@15` only "worked" because its larger input
starved the model of output space.

### The fix

One schema-derived constant, `EXTRACTION_OUTPUT_RESERVATION = 768` (config
`llm.extraction_output_reservation`), used two ways and **stated in one place**:

1. `num_predict` — a hard output-token cap.
2. the output term of `estimate_num_ctx`: `num_ctx = ceil_512(est_input_tokens + RESERVATION)`,
   **not** "window minus input".

Derivation (in the constant's comment): 8 prose fields (~60 tok each for summary / problem /
inferences, ~110 for method, ~55 for results / limitations / key_findings, ~35 for
novelty_claim) + 2 short lists (~55 tok each) + JSON structure (~60 tok) ≈ **660 tok** for a
full concise conforming response (legacy on `0549e2e9` used 556); 768 = that + ~15 % margin
on a clean boundary.

### MEASURE — canonical (frozen 60), 34 full-text papers, content_aware@10, seeded, clean cache

| | pre-3.2b (ca@10) | **post-3.2b (v2)** |
|---|--:|--:|
| mean non-empty fields / paper | 9.29 | **9.65** |
| method | 97 % | **100 %** |
| datasets | 97 % | 97 % |
| metrics | 82 % | **91 %** |
| results | 94 % | 94 % |
| limitations | 91 % | **94 %** |
| conformance | 29 conformant / 4 salvaged / **1 nonconformant_unrepaired** | **32 conformant / 2 salvaged / 0 nonconformant** |
| `_extraction_failed` | — | **0** |
| runtime | 35 s/paper | **32 s/paper** |

**`0549e2e9`: 2 → 7 fields, now `salvaged`** (was `nonconformant_unrepaired`). Capped at 768
output tokens the model can no longer complete the table transcription; it produces a
mostly-flat response that salvage recovers to 7 fields.

**Papers that got WORSE: none.** Three others improved: `78797b71` 8→10, `c093b845` 7→10,
`e6f1d66c` 8→10 (was salvaged → now conformant). The fixed reservation is a net gain across
the corpus, not just a fix for one paper.

### DECISION POINT

`0549e2e9` conforms (`salvaged`, an accepted state) after 3.2b, without the circuit breaker
firing. **The anchor / table-cell cap is NOT built.** It would treat a symptom and would cost
the 3.9× table-anchor delivery gain that is Phase 3's main result.

## 3.2c — conformance circuit breaker

Flow (in `run_summarization`, `_apply_selection_circuit_breaker`): a paper whose
`content_aware` extraction ends `nonconformant_unrepaired` or `wall_clock_exceeded` gets
**ONE** retry under `legacy` selection. Recovered (`conformant` / `salvaged` / `repaired` /
`repaired_salvaged`) → accepted with `_selection_fallback: true` on the **paper record**.
Still failing → `_extraction_failed` + `_failure_reason: nonconformant_both_selections`
(never an empty field). Not a loop, not a cascade through budgets. No-op unless the run is
`content_aware`.

The Phase-2.6 distinction survives: "failed to conform" and "field genuinely absent" remain
separate — a paper that fails both attempts is `_extraction_failed`, not empty fields.

### Fallback visibility (both kinds)

- **Circuit-breaker fallback** — `_selection_fallback: true` on the paper record; count
  printed in `run_summarization` and reported here.
- **Legacy-schema fallback** (the pre-existing silent path — `content_aware` → `legacy` when
  chunks lack `block_type`) — the `retrieval_selection.json` trace `mode` is now
  `"legacy_fallback"`, distinct from `"legacy"`. Behaviour unchanged; only now countable.
  `_legacy_schema_fallback_count()` reads it; `run_summarization` prints it.

A run with a non-zero fallback count of either kind is **partly a legacy run**; aggregates
are reported both ways (with / without the fallen-back papers).

### MEASURE — canonical ca@10 (post-3.2b), fallback counts

- **Circuit-breaker fallbacks: 0.** After 3.2b the breaker does not fire — 3.2b fixed the
  cause, it did not just mask it. (Per the task: a non-zero count here would have meant 3.2b
  was incomplete.)
- **Legacy-schema fallbacks: 0** (the canonical corpus is grounded schema).
- Mean with / without fallen-back papers is identical (9.65 / 9.65 over n = 34) — nothing
  fell back.

### Medical corpus — the now-visible legacy-schema fallback count

**16 of 50 papers.** These are the long (> 2500-word) full-text medical papers that a run
labelled `content_aware` was silently handling with `legacy` selection because the medical
chunks are legacy schema. Previously invisible; now `mode: legacy_fallback` in the trace and
counted. A `content_aware` measurement on that corpus is 16/19 full-text papers a legacy run.

## Regression checks

- **`data_test` (8, grounded, CS/NLP), ca@10 v2:** mean 9.62, 8/8 conformant, 0 circuit-breaker,
  0 legacy-schema, **0 regressions** vs on-disk. Identical to pre-3.2b.
- **`tests/test_pipeline.py` 6/6 · `tests/test_anchors.py` 9/9 · experiment suite 42/42.**
- **12/12 staging invariants PASS** (`staging_run.py`, `content_aware` + new caps active),
  monitor `overall: OK`, `DECISION: STAGING_PASS`. No new invariants added. (That run's 8
  `data_test` extractions were served from cache; the fresh-extraction path with the new
  `num_predict` / deadline was exercised separately in `context_budget_measure.py` — 8/8
  conformant, 0 regressions.)
- `EXTRACTION_PROMPT_VERSION` bumped to `2026-09-03.numpredict-deadline` — `num_predict`
  changes generation, so pre-change cache entries are no longer reused (they re-extract).

## What got worse

Nothing measured on the frozen 60 or `data_test`. The only cost is the legacy-schema
fallback *visibility* revealing that `content_aware` on a legacy-schema corpus is mostly a
legacy run — that was always true, it is now merely reported.
