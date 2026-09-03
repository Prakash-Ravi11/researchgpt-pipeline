# SELECTION POLICY REPORT — content-aware chunk selection for Stage 4

Branch `claude-code-verification` · HEAD `354a9bf` (+ this change) · 2026-09-03
All inside Stage 4 (`src/summarization/retrieval_aware.py`). Evidence gate untouched.
Production `configs/config.yaml` unchanged. All runs on the Phase-1 seeded path
(`temperature 0`, `seed 42`) — **do not compare any number here to the older unseeded 7%.**

Scripts: `selection_delivery_sweep.py` (no LLM), `selection_coverage_run.py` (LLM).
Rows: `runs/selection_policy/`. Per-paper query sets: `…/processed/retrieval_selection.json`.

## What was built

`build_retrieval_aware_papers` now has two modes (`config['selection']['mode']`):

- **`legacy`** — unchanged: 5 fixed generic queries × top-3, union, word-budget cap. Production default (config.yaml has no `selection:` block → defaults to legacy).
- **`content_aware`** — queries derived from the paper itself (metric names via `src.evidence.anchors`-adjacent regex, results/eval **headings**, **table & figure captions**); candidate chunks scored on `retrieval rank + numeric-anchor density (anchors from src/evidence/anchors.py) + table structure`; near-duplicate anchor content de-duplicated (>0.8 Jaccard on anchor set) and same-value chunks capped at 2; assembled up to `max_passages` (default **10**) and `token_budget_chars` (9000). Degenerate-query guard rejects reference-list text and word-boundary-broken fragments. Falls back to `legacy` per corpus when the chunk schema is legacy (no `block_type`) — see regressions.

`configs/staging_config.yaml` opts in: `selection: {mode: content_aware, max_passages: 10}`.

## STEP 0 — seeded baseline (legacy), frozen-60 canonical, 3981 anchors

| slice | delivery | n |
|---|--:|--:|
| ALL | **0.090** | 3981 |
| gate-ZERO | **0.055** | 2405 |
| gate-SOME | **0.143** | 1576 |
| long papers only (>2500 w) | 0.071 | 3900 |
| table-location anchors | 0.049 | 1336 |
| prose-location anchors | 0.111 | 2645 |

mean 12.9 passages, 2599 chars/paper delivered.

## MEASURE 1 — anchor-chunk delivery, budget sweep (no LLM)

| variant | passes | chars | ALL | gate-0 | gate-S | table | prose | sel s |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **legacy** | 12.9 | 2599 | 0.090 | 0.055 | 0.143 | 0.049 | 0.111 | 3.9 |
| content_aware@5 | 5.0 | 1032 | 0.106 | 0.080 | 0.145 | 0.131 | 0.093 | 11 |
| **content_aware@10** | 9.9 | 2145 | **0.167** | **0.107** | **0.259** | 0.189 | 0.156 | 11 |
| content_aware@15 | 14.0 | 2925 | 0.204 | 0.141 | 0.300 | 0.210 | 0.201 | 11 |
| content_aware@20 | 17.5 | 3654 | 0.211 | 0.144 | 0.314 | 0.214 | 0.210 | 11 |

**Curve: steep 5→10, moderate 10→15, flat 15→20.** @10 delivers **1.85×** legacy overall
(1.8× gate-SOME, 1.95× gate-ZERO, **3.9× on table-resident anchors**) with **fewer** passages
(9.9 vs 12.9) — better chunks under a smaller budget, as intended. Absolute delivery is still
low (83% of anchor mentions never reach the extractor at @10) but see MEASURE 2 — you do not
need every anchor chunk, only enough of the right ones.

## MEASURE 2 — extraction coverage, frozen-60 canonical (34 full-text, seeded, fresh cache)

| variant | mean fields | method | datasets | **metrics** | **results** | limitations | conformance | runtime |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| legacy | 8.94 | 97% | 97% | 71% | 65% | 88% | 29 conf / 5 salv | 33 s/paper |
| **content_aware@10** | 9.29 | 97% | 97% | **82%** | **94%** | 91% | 29 conf / 4 salv / **1 nonconf** | 35 s/paper |
| content_aware@15 | 9.38 | 100% | 97% | 79% | 97% | 91% | 28 conf / 6 salv | 49 s/paper |

Per-paper vs legacy at @10: **14 papers gained fields** (several 5→10, 7→10, 8→10),
**4 regressed**, 16 unchanged. `results` field coverage **65% → 94%** and `metrics` **71% → 82%** —
the two fields the delivery problem targeted. @10→@15 costs +40% runtime for `results` +3 pts and
`metrics` −3 pts and mean +0.09 — a wash to slightly negative, matching the OpenScholar
peak-near-10 prediction. **Default = 10.**

### Coverage split + three-way denominator (per the triage)

- **acquisition coverage** = usable full text / all papers = **34 / 60**.
- **extraction coverage** (≥1 core field / full-text paper) = 34 / 34 under both selectors.
- **field-presence determinability**: a structured representation (JATS/LaTeX) exists for only
  **2 / 34** canonical papers, 0 / 8 data_test, 0 / 19 medical. So per field the split is:
  `determinable-present` ≤ 2, `determinable-absent` ≈ 0, `undeterminable` ≈ 32 (canonical).
  **Coverage-when-present over determinable-present (n ≤ 2) is not meaningful** and is not
  reported as a rate. The all-papers per-field percentages above are the usable number, with the
  standing caveat that they cannot be normalised to a real presence denominator on PDF-only
  papers — `undeterminable` is never folded into either bucket.

## What got worse — reported, not absorbed

1. **`0549e2e9` (canonical ablation-table paper): 10 → 2 fields.** content_aware's number-aware
   scoring pulls the paper's many ablation-table chunks; Stage 4 then emits non-conforming JSON
   that R1 repair (commit `cc016cb`) cannot fix → `nonconformant_unrepaired`. It was `conformant`
   / 10 fields under legacy. This is the interaction of number-aware prioritisation with Stage-4
   fragility on dense tables — the single serious individual regression. Follow-up: cap table-chunk
   share in the score, or strengthen R1's table-response repair. Not fixed here.
2. Three smaller canonical regressions: `a6ecdf69` 9→7, `e6f1d66c` 10→8, `ddb170b2` 10→9.
3. **Medical corpus (legacy chunk schema): 5 / 19 papers regressed** — `330377da` 10→3,
   `c458eeae3a` 10→5, `295fc8094b` 10→7, `dd7cacac10` 9→8, `f09cd60900` 9→8. Root cause:
   content_aware derives queries from `section`/`block_type` and scores on table structure — none
   of which exist in legacy chunks, so it degrades below legacy's simple 5-query selection.
   **Fixed in code**: `build_retrieval_aware_papers` detects the absence of `block_type` and falls
   back to `legacy` for that corpus, so content_aware is safe to enable without knowing the corpus.
   (Medical run wall-clock was anomalous — 1479 s/paper vs ~35 s elsewhere — an overnight Ollama
   slowdown; field counts come from parsed JSON and are unaffected.)

## Regression checks (not averaged into any coverage number)

- **data_test** (8, grounded schema, CS/NLP): mean fields 8.1 (on-disk) → 9.62, **0 regressions**,
  8/8 conformant.
- **medical** (19, legacy schema): 5 regressions → now routed to `legacy` fallback (above).

## Cache

`_cache_entry_reusable` (commit `cc016cb`) keys reuse on `_text_hash = sha256(selected_text)[:16]`
+ `_prompt_version`. A selector change changes the assembled text → new hash → the entry is not
reused. The coverage runs used `cache={}` (clean re-extraction both sides); the staging E2E
re-extracted (no "served from cache" line). Verified: not a false null.

## Tests / invariants

`tests/test_pipeline.py` 6/6 · `tests/test_anchors.py` 9/9 · experiment suite 42/42.
Staging E2E on `data_test` with `content_aware` active: **12/12 safety invariants PASS**, monitor
`overall: OK`, `DECISION: STAGING_PASS`. No new invariants added.

## Recommendation

Enable `content_aware` (budget **10**) for corpora built with the grounded chunk schema — on the
frozen 60 it nearly doubles anchor delivery and lifts `results`/`metrics` extraction coverage
65→94 % / 71→82 %, at +6 % runtime, with `data_test` clean and 12/12 invariants held. Keep the
production default at `legacy` (unchanged); staging opts in. Two things gate a production flip:
the `0549e2e9`-class table-density → Stage-4 non-conformance regression, and the still-missing
structural denominator for a real coverage measurement.
