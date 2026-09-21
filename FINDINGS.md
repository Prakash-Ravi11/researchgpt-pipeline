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
