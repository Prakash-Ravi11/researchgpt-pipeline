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
room to generate. On `0549e2e9` @10 (1282-token input, ~1278 tokens of headroom) the model
spent that headroom transcribing every ablation-table cell into nested JSON: valid JSON,
**zero schema fields**. `content_aware@15` only "worked" because its larger input starved
the model of output space. The isolating factor for `0549e2e9` (per
`DIAG_0549E2E9_REPORT.md`, commit `5ecef20`) is **numeric-anchor count — 175, versus ≤ 51
for every other canonical paper — in a short selection**, not table share: four canonical
papers sit at ≥ 0.93 table-share and all are conformant.

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

**`0549e2e9`: `nonconformant_unrepaired` → `salvaged`.** Decoupling output headroom from
input length (3.2b) changed *what the model generated*. On `0549e2e9` it produced a
mostly-conforming response that terminated normally (`done_reason: stop`, not truncated),
with one stray top-level key that salvage remapped — **0 keys and 0 characters discarded**
(see §3.2d STEP 2). The paper is `salvaged` rather than `conformant` because of that single
remap, not because content was cut. `num_predict` did not fire; it remains an untested
backstop on this corpus.

> **Forward note — re-test `0549e2e9` after Phase 4.** The over-transcription behaviour was
> **not stopped by a cap** — it changed because the generation budget changed. Phase 4
> supplies denser structured tables to the extractor, which may make transcription *more*
> attractive again; whether the 3.2b budget change still holds under that is genuinely
> unknown. `0549e2e9` must be re-tested specifically after Phase 4 — do **not** assume the
> aggregate ca@10 numbers cover it.

**Papers that got WORSE: none.** Three others improved: `78797b71` 8→10, `c093b845` 7→10,
`e6f1d66c` 8→10 (was salvaged → now conformant). The fixed reservation is a net gain across
the corpus, not just a fix for one paper.

### DECISION POINT

`0549e2e9` reaches `salvaged` (an accepted state — one stray key remapped, 0 content
discarded; not `conformant`) after 3.2b, without the circuit breaker firing. **The anchor /
table-cell cap is NOT built.**
It would treat a symptom and would cost the 3.9× table-anchor delivery gain that is Phase 3's
main result.

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

**16 of 19 full-text papers — an 84 % fallback rate**, not 16 of 50 (32 %). The denominator
is 19, not 50: the other 31 medical papers are abstract-only and go through the 2500-word
passthrough, so they are never selection candidates and cannot fall back. Of the 19 papers
that *are* selection candidates, 16 are long (> 2500-word) full-text medical papers that a
run labelled `content_aware` was silently handling with `legacy` selection because the
medical chunks are legacy schema. Previously invisible; now `mode: legacy_fallback` in the
trace and counted. A `content_aware` measurement on that corpus is 16/19 full-text papers a
legacy run.

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

---

## 3.2d — socket-leak fix + salvage accounting + cap-truncation signal

Three changes, all inside Stage 4 / the Ollama client (`call_ollama_json`,
`salvage_nonconformant`, `_extract_single_paper`). Selector, scoring weights, selection
budgets, prompt, and evidence gate untouched. Production `configs/` unchanged. Seeded path
(temperature 0, seed 42).

### STEP 1 — the socket leak (this was the bug)

**Root cause.** The 3.2 deadline was `threading.Thread` + `th.join(timeout=deadline)`.
`join` bounds *our wait*, not the request: on expiry the daemon worker was still alive,
still holding a socket, and Ollama was still generating. The next paper then issued a
second concurrent request against the 6 GB card; Ollama serialised them; later papers
slowed and could cascade into further deadline hits.

**Fix — neither (a) nor (b); a third option: no worker thread at all.**
`call_ollama_json` now sends `stream: true` and consumes `resp.iter_lines()` on the
*calling* thread, checking `time.monotonic() - start > deadline_seconds` between chunks. On
expiry the calling thread — which owns the socket — calls `resp.close()`, tearing the
connection down immediately, and returns the `{"_deadline_exceeded": True}` sentinel.
Chosen over (a) `requests.Session` + parent `session.close()` and (b) swapping to `httpx`
because it removes the thread (and the cross-thread teardown handshake) entirely rather
than making it safe, and adds no dependency. Rationale is in the `call_ollama_json`
docstring. The `requests` read timeout is kept at ~300 s as a "no bytes at all" guard —
*not* clamped to the deadline, because first-token latency on a cold/large prompt legitimately
exceeds a short deadline.

**Cleanup verification** (`verify_deadline_cleanup.py`, forced `deadline_seconds=3` on
`9879e1cce9…`, 5 iterations in succession, seeded):

| iter | elapsed | `threading.active_count()` | surviving non-main workers |
|-----:|--------:|--------------------------:|:---------------------------|
| 1 | 13.0 s | 1 | none |
| 2 | 13.0 s | 1 | none |
| 3 | 12.7 s | 1 | none |
| 4 | 12.4 s | 1 | none |
| 5 | 12.6 s | 1 | none |

- Thread count: baseline **1 → final 1**. No worker thread survives any iteration.
- Elapsed: **flat, no upward creep** (13.0 → 12.6). A leak would show iter *n* paying for
  the *n−1* still-running orphans as Ollama serialised them; it does not.
- Ollama after the 5th: `/api/ps` responsive, 1 model loaded; a trivial follow-up
  `POST /api/chat` returned **HTTP 200, `done_reason=stop`**.

**Known blind spot (not a leak).** Each iteration takes ~13 s, not ~3 s: the deadline is
only tested once `iter_lines()` has yielded a line, and prompt-eval / first-token for a
2500-word paper on a 6 GB card takes ~12 s. So a deadline shorter than first-token latency
fires at first-token, not at `deadline_seconds`. It is a runaway-*generation* bound, not a
sub-first-token bound. Production `extraction_deadline_seconds` is 240 s, where first-token
latency is noise; the 3 s here is purely a forcing value. Elapsed is flat across iterations,
which is the property that matters for the leak.

### STEP 2 — salvage accounting (per-response, not aggregate)

`salvage_nonconformant` now attaches `_salvage_accounting` to every salvaged record, and
`_extract_single_paper` stamps `response_truncated_before_salvage` (from STEP 3) onto it:

- `direct_fields` — schema fields that arrived as clean scalars/lists in the raw response
- `recovered_fields` — schema fields that only have content because reshaping filled them
- `flattened_fields` — fields that arrived as nested dict/list and were stringified
- `moved_top_level_keys` — `[{key, target, chars}]` for each invented top-level key routed
  into a schema field
- `discarded_top_level_keys` + `discarded_char_volume` — keys dropped (only ever
  empty-valued keys) and their approximate character volume

**Per-paper breakdown, canonical ca@10 (the individual list, not a total):**

| paper | conf. | direct | recovered | flattened | moved (key→target, chars) | discarded | trunc. before salvage |
|-------|-------|--------|-----------|-----------|---------------------------|-----------|-----------------------|
| `0549e2e9e6be` | salvaged | summary, problem_addressed, method, results, inferences, novelty_claim | — | — | `systematic_review`→method (183) | **0 keys / 0 ch** | False |
| `ae2768758f99` | salvaged | results | summary, method, inferences | — | `abstract`→summary (366), `conclusion`→inferences (296), `methodology`→method (170), `components`→results (319), `implications`→inferences (225) | **0 keys / 0 ch** | False |

Both salvages **discarded nothing** — every non-schema key carried content and was routed
into a schema field, none were dropped. This is the place over-permissiveness would hide;
it is not hiding here. `0549e2e9` specifically: `conformance = salvaged` **not** because
content was cut — `done_reason` was `stop`, `trunc. before salvage` is `False`, 0 keys / 0
chars discarded — but because the one stray top-level key `systematic_review` was remapped
into `method`. `selection_fallback = False`.

> `0549e2e9` is present only in the **frozen** canonical corpus
> (`runs/prodab-20260902T004416Z/canonical/`), not the current 60-paper corpus, so the
> breakdown above is from the ca@10 measurement run, which is the cheap place to get it.
> It is `salvaged`, not `conformant`. The 3.2b budget change altered what the model
> generated (it did not cap it); whether that survives Phase 4's denser structured tables
> is unknown, so it must be re-tested then — see the 3.2b forward note.

### STEP 3 — `done_reason` signal (cap-truncation vs pathology)

`call_ollama_json` reads `done_reason` off the terminal stream chunk into `meta_out`;
`_extract_single_paper` records `_done_reason` on every paper record and `_response_truncated`
when it is `"length"`. `context_budget_measure.py` counts them and flags the dangerous
combination (`done_reason == "length"` AND `conformance ∈ {conformant, salvaged}` — the cap
cutting real content rather than stopping a pathology).

- **Canonical 34 @ ca@10: `done_reason == "length"` count = 0.** All 34 ended `stop`.
- `length` AND (conformant | salvaged): **0** — `EXTRACTION_OUTPUT_RESERVATION = 768` is
  **not** truncating any legitimate response.
- `data_test` (8): `length` count = **0**.

Because the count is zero on conformant papers, the constant does **not** need splitting in
this commit. If a future corpus shows a non-zero count here, `num_predict` (stop-runaway)
and the `num_ctx` output term (guarantee-room) should be separated — that is a follow-up.

### MEASURE — canonical ca@10 re-run (34 papers, seeded, clean cache)

3.2b numbers reproduce exactly — every listed change was behaviour-neutral:

| metric | 3.2b target | 3.2d |
|--------|-------------|------|
| mean non-empty fields / paper | 9.65 | **9.65** |
| method | 100% | **100%** (34/34) |
| metrics | 91% | **91%** (31/34) |
| limitations | 94% | **94%** (32/34) |
| conformance | 32 conformant / 2 salvaged / 0 nonconformant | **32 / 2 / 0** |
| circuit-breaker fallbacks | 0 | **0** |
| `_extraction_failed` | 0 | **0** |

Per-paper vs pre-3.2b `cov_canon_ca10.json`: **0 papers worse**; 4 better (`0549e2e9`
2→7 via salvage, `78797b71` 8→10, `c093b845` 7→10, `e6f1d66c` 8→10 — all pre-existing 3.2b
gains, unchanged here). Mean identical with / without fallen-back papers (none fell back).

### Regression + invariants

- **`data_test` (8, grounded, CS/NLP) ca@10 v2:** mean 9.62, 8/8 conformant, 0
  circuit-breaker, 0 legacy-schema, **0 regressions** vs on-disk.
- **`tests/test_pipeline.py` + `tests/test_anchors.py`: 15/15** (6 + 9).
- **Experiment suite `tests/test_pipeline_units.py`: 42/42.**
- **12/12 staging invariants PASS** (`staging_run.py`, run `staging-20260903T035211Z`),
  monitor `overall: OK`, `DECISION: STAGING_PASS`, 0 pipeline errors. No new invariants.
  This run re-extracted all 8 `data_test` papers through the new streaming / `num_predict` /
  deadline path (cache invalid after the `EXTRACTION_PROMPT_VERSION` bump) — 8/8 conformant.
- Medical corpus legacy-schema fallback count unchanged at **16 / 19 full-text papers
  (84 %)** — denominator is the 19 selection candidates, not all 50 (31 are abstract-only,
  never candidates).

### What got worse — 3.2d

Nothing measured. No drift on the canonical 34 or `data_test`; no new failure modes. The
one honest caveat is STEP 1's first-token blind spot (above): a deadline set below
first-token latency will over-run to first-token. Immaterial at the 240 s production
value; documented so a future short-deadline experiment is not surprised.
