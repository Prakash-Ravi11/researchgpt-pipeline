# DIAG — 0549e2e9 non-conformance + the medical timing anomaly

Branch `claude-code-verification` · HEAD `9efd7a4` · 2026-09-03
**Diagnosis only. No production/staging code changed. No decoding parameter, weight, budget,
scoring function, prompt, or repair path touched.** Seeded path (`temperature 0`, `seed 42`).
Harness: `experiments/document_evidence_pipeline/diag_0549e2e9.py` ·
artifacts `runs/selection_policy/diag_0549e2e9/`.

## Reproducibility

Each `0549e2e9` request was **primed** (`prime_ollama_cache`, exactly as `extract_paper_fields`
does) and issued twice. **All three variants: byte-identical across the 2 primed runs, verdict
stable.** The raw bodies were not saved during the coverage run, but the parsed outcomes
reproduce it exactly — legacy `conformant`/10 fields, ca10 `nonconformant_unrepaired`/2, ca15
`salvaged`/6. The coverage numbers are reproducible. (An earlier *un-primed* pass showed
byte drift — that is the Phase-1 Ollama prompt-cache history effect, a harness artifact of
interleaving three prompts without priming, not a property of the seeded path.)

## STEP 2 — failure classification

| variant | chars | tok_out | tok_in | num_ctx | done_reason | valid JSON | **verdict** |
|---|--:|--:|--:|--:|---|---|---|
| legacy | 2612 | 556 | 2496 | 3072 | stop | yes | **OTHER (conforming)** — all 10 schema fields |
| **ca10** | 3244 | **1251** | **1282** | 2560 | stop | yes | **VALID_BUT_WRONG_SHAPE** — top-level keys `Table 5` / `Table 6` / `Table 7`, each a nested object; **0 schema fields** |
| ca15 | 1431 | 300 | 2820 | 3072 | stop | yes | **VALID_BUT_WRONG_SHAPE** — one stray key `system`; 5 schema fields present |

- **No truncation** — no response has `done_reason == "length"`.
- **No repetition loop** — none found in any of the three (`0549e2e9`'s failure is *not* the
  `9879e1cce9` degeneration).
- ca10 raw head: `{ "Table 5": { "Ablation 1 (No Preprocess)": { "Index (%)": 84.82, "Sensitivity (%)": 89.26, … } }` — the model transcribed the ablation / comparison tables cell-by-cell into nested JSON and emitted **no prose fields at all**. Salvage routes the three `Table N` blobs to `results`; `_has_min_content` fails (no core fields); repair fails → `nonconformant_unrepaired`, 2 fields kept (`results`, `datasets`-from-pattern).
- ca15 raw is a normal flat `summary` / `method` / `problem_addressed` / `results` / `inferences` object with one leaked `system` key → salvage recovers 6 fields.

## STEP 3 — the @10 vs @15 inversion

| | legacy | **ca10** | ca15 |
|---|--:|--:|--:|
| passages | 10 | 10 | 15 |
| total chars sent | 7005 | **4824** | 5197 |
| **table share (by chars)** | 0.115 | **0.933** | 0.866 |
| total numeric anchors | 67 | **175** | 175 |
| distinct sections | 5 | 3 | 3 |
| tokens in | 2496 | **1282** | 2820 |
| tokens out | 556 | **1251** | 300 |

**`@15` is a strict superset of `@10`.** It adds exactly 5 chunks — all `figure_caption`, all
0-anchor, 65–81 chars each (373 chars total). `@10` adds nothing that `@15` lacks.

Candidate explanations, checked:

- **(a) "@10 is not actually more table-dense" — REFUTED.** @10 is 93.3 % table characters vs
  @15's 86.6 %.
- **(b) input length ↔ output structure — SUPPORTED; primary mechanism.** `estimate_num_ctx`
  sizes the window from the input, so @10's short 1282-token input gets a 2560 window →
  ~1278 tokens of *output headroom*. Handed a thin, 93 %-table input with that much room, the
  model spent essentially all of it (1251 tokens) transcribing every table cell into nested
  JSON. @15's 2820-token input in a 3072 window leaves only ~250 tokens of headroom → the
  model is forced terse (300 tokens) → a short flat schema-shaped summary.
- **(c) a specific triggering chunk — NO.** The 5 chunks @15 adds are generic 0-anchor
  captions; they do not "fix" anything directly. Their effect is aggregate — they push the
  input to 2820 tokens (collapsing output headroom) and dilute table share.
- **(d) output near a limit — PARTIALLY, and in reverse.** Neither hit `done_reason=length`.
  But @10's 1251-token output consumed ~98 % of its available headroom; @15's lack of headroom
  *prevented* a long response. The limit interaction is: @10 had room to run long and used it
  pathologically.
- **(e) is ca15's "salvaged" close to failure? — MILDLY.** ca15 raw carried only 5/10 schema
  fields plus a stray `system` key; salvage recovered 6. Genuinely better-formed than @10's
  zero-field dump, but not clean.

**Direct answer.** The larger, more table-dense-by-count `@15` selection produced a
better-formed response because its bigger input consumed the context window, leaving almost no
output headroom, which forced the model into a short flat schema-shaped summary instead of a
long cell-by-cell table transcription — and because the added prose captions diluted the pure
table density. `@10` sits in a pathological sweet spot: enough dense-table content to invite
transcription, and (because the window is sized from the short input) enough output headroom to
finish that transcription as valid nested JSON with no schema fields.

## STEP 4 — one paper, or a class?

@10 conformance vs selection composition, 32 long canonical papers (2 are `<=2500 w` passthrough):

| group | n | table share (chars) | total chars | **total anchors** | distinct sections |
|---|--:|--:|--:|--:|--:|
| conformant | 29 | 0.45 | 2020 | **14** | 3.8 |
| salvaged | 1 | 0.48 | 3086 | 24 | 2.0 |
| **nonconformant_unrepaired** (= 0549e2e9) | 1 | **0.93** | **4824** | **175** | 3.0 |

**Table share alone does NOT predict non-conformance.** Four papers have table_share_chars
≥ 0.93 (`413a184d` 1.00, `93db4f9a` 1.00, `fef0393e` 1.00, `f1f07a37` 0.98) and **all four are
conformant**. What isolates `0549e2e9` is **anchor count: 175, versus ≤ 51 for every other
paper** (next highest is 51; the four high-table-share conformant papers carry 1–27), together
with the largest total selection (4824 chars). So **`0549e2e9` is currently a class of one.**
The mechanism is real but only fires when the selection is *both* extremely anchor-dense *and*
still short enough that the input-sized context window leaves large output headroom.

> **The report's stated cause must be corrected:** it is not "table density" that breaks Stage 4
> here, it is **extreme numeric-anchor density in a short selection** (a table with dozens of
> numeric cells the model tries to transcribe), plus an output budget large enough to let it
> finish.

The three smaller canonical regressions are **not the same failure**, and mostly not failures:

| paper | cov outcome | raw @10 verdict | tok_out | nonconf keys | table share |
|---|---|---|--:|---|--:|
| `a6ecdf69` (9→7) | conformant | **OTHER (conforming)** | 396 | — | 0.18 |
| `ddb170b2` (10→9) | conformant | **OTHER (conforming)** | 358 | — | 0.41 |
| `e6f1d66c` (10→8) | salvaged | VALID_BUT_WRONG_SHAPE | 498 | `['code']` | 0.48 |

`a6ecdf69` and `ddb170b2` produced clean, conforming JSON — they simply extracted fewer fields
from a different (content_aware) chunk set. That is ordinary selection variance, not
malformation. `e6f1d66c` is a mild single-stray-key non-conformance (like `ca15`'s `system`),
recovered by salvage.

## STEP 5 — the medical timing anomaly

Per-paper wall-clock, medical `ca@10` run (parsed from the run log's progress bar):

| paper # | paper_id | elapsed | step (s) | conformance |
|--:|---|---|--:|---|
| 1–10 | (various) | → 08:18 | 32–61 each | 9 conformant, 2 salvaged |
| **11** | **`9879e1cce9`** | **7:43:45** | **≈ 27 327 (7.6 h)** | **nonconformant_unrepaired** |
| 12–19 | (various) | → 07:48:03 | 14–45 each | 6 conformant, 2 salvaged |

**The entire 28 095 s runtime is one paper.** Papers 1–10 and 12–19 ran at 14–61 s, on both
sides of the stall — the machine was awake and fast immediately before *and* after. The stalled
paper is **`9879e1cce9`**, the same paper the Stage-4 triage flagged for degenerate
whitespace-loop generation, and it is `nonconformant_unrepaired` here.

7.6 h exceeds the client `timeout=300 s` × 3 retries × ~3 calls (≤ ~45 min), so the client
timeout was *also* not enforced for that one paper (an un-timed-out server hang, possibly
compounded by a laptop sleep during that single paper). Either way:

> **The report's "overnight Ollama slowdown" is wrong as a blanket cause.** 18 of 19 medical
> papers ran normally at 14–61 s. The 42× average is a pure artifact of one paper
> (`9879e1cce9`) hanging. The task's alternative — a degenerate generation cycle on the
> already-observed `9879e1cce9` failure — is confirmed as *which* paper stalled; the magnitude
> means the 300 s timeout did not protect against it.

## Recommendation — evidence supports / rules out

**Supported:**
- A **per-paper wall-clock circuit breaker** on Stage-4 extraction (already agreed as the next
  task). STEP 5 shows one paper consumed 99.98 % of a run and the `requests` timeout did not
  bound it.
- The `0549e2e9` break is driven by **extreme anchor density in a short selection**, not table
  share. A *selection-side* guard — cap total numeric anchors (or total table-cell characters)
  in the assembled context — would remove the transcription trigger. (Do not implement here.)
- `estimate_num_ctx` sizes output headroom from input length, which is largest exactly when the
  input is a dense table dump — the worst case. Decoupling the output budget from input length
  is worth considering.

**Ruled out:**
- Truncation / `num_predict` limit — no response hit `done_reason=length`.
- Repetition loop as the `0549e2e9` cause — none present; that is `9879e1cce9`'s pathology.
- "Table density predicts non-conformance" — 4 papers at ≥ 0.93 table share are all conformant.
- "Overnight machine slowdown across the medical run" — 18/19 papers ran normally.
- `a6ecdf69` / `ddb170b2` as fix targets — clean conforming JSON, ordinary selection variance.

---

# APPENDIX (3.2a) — why the 300 s timeout did not bind, and what replaced it

## Why it did not bind

`call_ollama_json` issued `requests.post(url, json=payload, timeout=timeout)` with a scalar
`timeout` (300). `requests` applies a scalar as `(connect_timeout, read_timeout)`, and the
**read timeout is the maximum gap between received bytes, not total elapsed time**.
`requests` / `urllib3` has no total-request-duration timeout at all.

- It was wired to the correct call site — **not a "never wired" bug**. It is a **semantics**
  problem: this class of timeout cannot bound total call duration.
- A process frozen by laptop sleep defeats it (the `select()` / `poll()` wait does not accrue
  frozen wall-time; on resume it re-arms for another full interval). A server that emits one
  byte every < 300 s indefinitely also defeats it.
- `stream: False` does not help: Ollama computes the whole response server-side then sends it,
  so `requests` sits in one blocking read that simply re-arms across a sleep.

STEP 5's data fits this exactly — `9879e1cce9` alone consumed 7.6 h (27 327 s) while the
`timeout=300` never fired; the other 18 medical papers ran at 14–61 s on both sides.

## What replaced it

Both changes are in the Ollama client (`src/summarization/summarize.py`); nothing else moved.

1. **True total wall-clock deadline.** The request runs in a `daemon` thread;
   `thread.join(timeout=deadline_seconds)` bounds the wait. On expiry the call is abandoned
   (sentinel `{"_deadline_exceeded": True, "_elapsed_s": …}`, **no retry** — a deadline is not
   transient), and `_extract_single_paper` records the paper as `_extraction_failed` with
   `_failure_reason: "wall_clock_exceeded"` and `_elapsed_s` — **never an empty field, never a
   silent skip**. The next paper proceeds immediately. Config: `llm.extraction_deadline_seconds`
   (default 240 s — normal papers run 14–61 s).
2. **`num_predict` hard output cap** = `EXTRACTION_OUTPUT_RESERVATION` (768, schema-derived —
   see the constant in `summarize.py`). The degenerate whitespace/tab loop that produced the
   7.6 h hang can no longer generate unbounded output.

## Verification — `9879e1cce9` alone, seeded

| condition | elapsed | outcome |
|---|--:|---|
| real config (deadline 240 s, `num_predict` 768) | **26.3 s** (was 27 327 s) | `num_predict` caps the whitespace loop → still unparseable → `_extraction_failed` / `no_response`, 0 fields, process continues |
| `extraction_deadline_seconds` forced to 3 s | **3.0 s** | deadline trips exactly; `_extraction_failed` / `_failure_reason: wall_clock_exceeded` / `_elapsed_s: 3.0`; 0 fields; process continues |

One pathological paper can no longer consume a run: the observed 7.6 h hang is eliminated by
the output cap alone, and the wall-clock deadline is the hard backstop for any other
total-duration pathology the read-gap timeout cannot see.
