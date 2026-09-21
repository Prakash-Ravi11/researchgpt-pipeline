# FINDINGS — bugs found outside the current phase's scope, not fixed

## 2026-09-19 · Phase 3 · `_METRIC` regex matches the Portuguese preposition "em"

`experiments/document_evidence_pipeline/retrieval_recall.py:41-45` — the alternation
ends with `|em\b|correlation)` . The `em\b` branch is intended as the "exact match"
abbreviation (EM). It also matches the ordinary Portuguese word **"em"** ("in"), which
appears throughout the two Portuguese-language papers in the canonical corpus.

Observed: sampled anchor `N14`, paper `9f...` (see
`runs/phase3_composition/sample_named.json`), value `277` taken from a reference list
entry *"...(SBBD), pages 264-277. SBC."* was labelled with metric `em`. The anchor is a
page number in a bibliography; the "metric name" is a preposition.

Effect: inflates the NAMED partition with false positives, and feeds the preposition into
the Phase 2 cell C/D query as if it were a metric name.

Obvious fix (NOT applied — out of scope for Phase 3, which classifies the extractor's
misses rather than repairing it): require the uppercase form, e.g. `\bEM\b` case-sensitively
instead of the case-insensitive `em\b`.

Not fixed. Recorded per RESEARCH_DIRECTIVE.md ("If you find a bug unrelated to the current
phase, write it to /FINDINGS.md and keep going. Do not fix it.").

## 2026-09-21 · Phase 5 · PHASE4_DENOMINATOR.md B4 mixes two denominators

`phase4_denominator.py` built its corpus-wide malformed flags as
`flags[(paper_id, value, section)] = ...`. That key is not unique across the 3,900
long-paper anchors — there are **244 collisions**, leaving 3,656 distinct keys. The
numerator was then counted over `flags.values()` (3,656 entries) while the denominator
printed was `len(longa)` (3,900).

Published in PHASE4_DENOMINATOR.md B4: **1,167 / 3,900 = 29.92 %**.
Correct, counted per anchor:            **1,209 / 3,900 = 31.00 %**.
(1,167 / 3,656 = 31.92 % is the other internally-consistent pair.)

Knock-on: B5's `cleaned_n` of 2,733 should be **2,691**. The B5 deltas are unaffected in
sign or in kind — the largest delivery move stays ~0.02 — but every cleaned figure there
rests on 42 anchors too many.

The detector itself is correct and deterministic; this is an aggregation bug only.
Phase 5 uses the per-anchor application (1,209 / 3,900) and reconciles exactly:
2,691 cleaned anchors = 3,900 − 1,209.

NOT FIXED. PHASE4_DENOMINATOR.md is left unmodified per the Phase 5 constraint
("Do not modify Phase 0-4 artifacts").

## 2026-09-21 · Phase 5 · the next lever is the 2,500-word assembly budget

Measured in Phase 5, recorded here rather than acted on (one variable per phase).

At `n_results=50`, `_assemble` (`src/summarization/retrieval_aware.py:263-273`) truncates
in **30 of 31 papers** against `llm.max_context_words: 2500` (`configs/config.yaml:37`),
and gives back **59.8 % of the pre-assembly delivery gain** — cleaned delivery is 0.5856
before assembly and 0.2742 after. 838 cleaned anchors are selected and then truncated away.

Truncation is in `chunk_index` order, so it discards the end of the document
preferentially — where results sections live.

NOT FIXED. Raising or reallocating that budget is a separate intervention with its own
pre-registration; it was not touched in Phase 5.

## 2026-09-21 · Phase 6 · two one-line portability fixes, found read-only, not applied

Phase 6 was a read-only audit; both of these are one-liners and both are left undone per
that constraint. Full context in /PHASE6_PORTABILITY_AUDIT.md section C.

1. `openpyxl` is imported at `src/reporting/corpus_table.py:110-112` and is absent from
   `requirements.txt`. The XLSX export path raises ModuleNotFoundError on a fresh install.
   Fix: add `openpyxl` to requirements.txt.

2. `experiments/document_evidence_pipeline/diag_0549e2e9.py:246` hardcodes
   `Path("C:/Users/Praka/AppData/Local/Temp/claude/...")`, a machine-specific scratch
   directory. It is the ONLY absolute path in any .py file in the repo.
   Fix: parameterise it or make it relative.

NOT FIXED.

## 2026-09-21 · Phase 7 Step A · estimate_num_ctx undershoots and Ollama silently truncates

Measured, not inferred. Feeds Phase 8. NOT FIXED — Step A observes only, and this phase
is forbidden from changing num_ctx.

Every Ollama call in src/ passes an explicit options.num_ctx (built unconditionally at
src/summarization/summarize.py:423), so Ollama's own default never applies. The
production extraction path sizes it with estimate_num_ctx (summarize.py:324-336), which
assumes 1.4 tokens/word and clamps to [2048, 8192].

On Phase 5 development paper 1016250721... at n_results=50 (93 chunks, 2,500 assembled
words, 2,520-word user_content):

    call 1, num_ctx=5120 (what production sends)   prompt_eval_count = 2,562
    call 2, num_ctx=8192 (same prompt)             prompt_eval_count = 6,096

3,534 tokens - 58% of the prompt - never reached the model. The paper is Portuguese and
tokenises at ~2.0 tokens/word, so the 1.4 factor undershoots badly and Ollama drops the
overflow without error.

n=1, and a non-English paper: this establishes the failure mode is reachable on production
settings, not how often it fires. Two further facts for whoever sizes this properly:
  - estimate_num_ctx is clamped at max_ctx=8192 while qwen2.5:7b declares 32768.
  - prompt_eval_count is recorded NOWHERE in src/ or any run artifact, so the historical
    rate cannot be recovered - it would need new instrumentation.

## 2026-09-21 · Phase 7 · doctor.py em-dash is mojibake on a cp1252 console

scripts/doctor.py's CPU-mode WARN line contains an em-dash, which renders as a
replacement character on a Windows console using cp1252 (observed in the fresh clone).
Cosmetic, one character. Step C did not fail, so per this phase's constraint it is
recorded here rather than fixed in code.

## 2026-09-21 · Phase 7 · correction to PHASE6_PORTABILITY_AUDIT.md A2

Phase 6 listed inspect_corpus.py as an entrypoint with "no __main__ guard found - invoked
as a script but has no guarded entrypoint". It has no argparse and no __main__ at all: it
is a helper module, not a script. README.md states this. Phase 6's artifact is left
unmodified.
