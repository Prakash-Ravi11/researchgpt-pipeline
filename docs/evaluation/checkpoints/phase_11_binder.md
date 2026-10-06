# Phase 11 checkpoint - STOP on A4 pre-existing experiment failures

Date: 2026-10-06. Branch: `exp/phase11-binder`.
Full report: `docs/evaluation/phase_11_binder.md`.

## Completed

- Phase 10 confirmed pushed at `050f8de`; `phase10-binder-final` tag created and pushed.
- Phase 11 scope committed alone: `537658d`.
- Read-only failure classification: `5bd4c0f` (47 inventory rows).
- Class A failing tests committed: `ad5bc9e` (5 failed / 10 passed).
- Class A fix committed: `d64cd91` (94 focused checks passed in each runtime).
- Class B failing tests committed: `d32f367` (4 failed / 2 passed).
- The user resolved the initial Class B STOP: preserve the existing required-value rule and revise
  only NEW tests. Separate scope amendment `9a8fc9a`, revised tests `cd53e13`, validated fix `176de61`.
- Class C failing tests `c3e77ba`; normalization fix `85bee81` (117 focused checks pass per runtime).
- Class D failing tests `2415bb9`; guarded preservation fix `7f0cef3` (125 focused checks pass per runtime).
- Full pytest: **226 passed in all four Python/runtime policy combinations**. Standalone pipeline:
  **37 passed in all four**. Legacy experiment suite: **63 passed in each runtime**. Legacy-invoked
  frozen binder regression: **123 expectations passed in each runtime**.

## STOP

The unchanged experiment unit suite reports **57 passed, 6 failed under v2 in each runtime**.
Its own-cell nDCG@5 case is withheld, its cross-row case has the wrong abstention reason, and four
cases have unexpected not-bindable/wrong-cell/non-table statuses. Exact assertions are in
`experiments/document_evidence_pipeline/tests/test_pipeline_units.py:262`, `:266`, `:277`, `:356`,
`:358`, `:368`. Full failures/commands/hashes are in `docs/evaluation/evidence/phase11_validation.json`.

The latest user instruction requires STOP on ANY pre-existing test failure. No code or test edits,
S3 run, measurement, or Part B work followed this STOP. No baseline rerun was made after it, so
which failures predate Phase 11 is not established. Do not silently force this suite to legacy.

The earlier Class B STOP is resolved, and its rejected candidate patch is archived only. There is
no uncommitted binder source patch now. The last implementation commit is `7f0cef3`.

## Not done

- Completion of A4, new S3 run, development regression measurement. The v2-policy frozen regression
  invocation was not reached after the experiment-suite failure.
- Phase 11 S1/S2/S3 are **not evaluated**. Phase 10 FAIL/FAIL/PASS remains historical, unchanged.
- No `phase11-binder-final` tag. No Part B branch, replay, funnel or upper bounds.
- No held-out gold construction (explicitly excluded from this task).

## Fixed constraints

The user approved **cached replay with all real LLM calls blocked** for eventual Part B. Do not run
a fresh extraction model. Defaults stay legacy / table_value_guard / borderless off. No merge.
Frozen Phase 10 packages/configs have no diff from the starting tag. No old tests were changed.
Untracked `docs/diagnosis/`, `out/`, `src/evaluation/candidate_gold/` remain untouched.

The complete absolute-path inventory, commit ledger, test commands/evidence, historical bottlenecks
and resume procedure are in the full report. The Class B contract is settled: text-only values do
not block a supported table bind, and are not verified by that bind. The next authorization must
address the six A4 failures without editing pre-existing tests or frozen artifacts.
