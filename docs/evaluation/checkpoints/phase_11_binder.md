# Phase 11 checkpoint - F5 STOP on frozen non-equality statuses

Date: 2026-10-06. Branch: `exp/phase11-binder`.
Implementation: `6cc9b5c3500bc68aa7aa6260fc30bdba8249f60c`. Report: `docs/evaluation/phase_11_binder.md`.

The user authorized diagnosis/fix of six original experiment assertions after the
earlier A4 STOP. F0-F4 completed: original logs preserved; Phase 10 baseline on both
runtimes proves all six already failed; temporary worktree removed; classification
written before implementation; 13 new synthetic tests committed failing (9/4); three
mechanism fixes committed separately. All 138 focused binder tests pass on Python
3.10.18 and 3.13.6, including all 46 A-D tests and Class B boundaries. The unchanged
experiment suite passes 63/63 under v2 on Python 3.10.18.

## Current STOP

F5 full matrix: first 3.10.18/legacy invocation passed full pytest 239, standalone
pipeline 37, experiment units 63. Frozen `src/evaluation/binder_10/regress.py` then
passed 121 and failed 2. It internally selects v2 even under a legacy invocation.

- Line 105, `B threshold alone`: expected `not_a_table_claim`, actual `not_bindable`.
- Line 198, `B delta never binds`: expected `not_a_table_claim`, actual `not_bindable`.

E2 excludes non-equality mentions from quantity scope, changing their residual
status. No fix or additional test run followed this STOP. The remaining twelve
matrix invocations were not run. S1/S2 not evaluated; S3 and development measurement
not run. No final tag, Part B branch, cached replay, funnel or new bottleneck ranking.

## Evidence and preservation

- `docs/evaluation/evidence/phase11_a4_baseline.json`: per-assertion baseline, original hashes.
- `docs/evaluation/diagnosis/phase11_a4_failures.md`: pre-fix mechanism diagnosis.
- `docs/evaluation/evidence/phase11_a4_validation.json`: commands, results, guard proof, new paths/hashes.
- Original `experiment_.venv_v2.txt` / `experiment_.venv-09a_v2.txt` unchanged.
- No pre-existing tests, frozen evaluation artifacts or configs changed.
- Defaults legacy / table_value_guard / borderless off. No real LLM call.
- Untracked docs/diagnosis, out, src/evaluation/candidate_gold untouched.

## Next action

Obtain continuation authorization for the two frozen non-equality status failures,
preserving their expectations and all six repaired experiment expectations. No
waiver or evaluator edit is authorized. Complete F5 before F6; tag only if A4, S3
and the development regression complete without STOP. Part B stays cached replay,
with all network/Ollama calls blocked, missing records explicit, machine-assisted,
unvalidated and development-contaminated. Do not claim a fresh production run.

## New commits

- `5ef7bc89f03623e6991236b6605237157021827d`: Read-only baseline evidence and mechanism diagnosis.
- `089aa6202ffbc01c8b34cb17cb4870695b6e44f8`: 13 synthetic tests committed failing: 9 failed, 4 passed.
- `0184ebb881b03decaa7fd0f1b9d7165e4b101f1c`: E1: preserve compound metric separators and cutoff tokens.
- `198c9225d506b2eee04e3ac2df93e605ed18da15`: E2: require quantity scope before absent-value classification.
- `6cc9b5c3500bc68aa7aa6260fc30bdba8249f60c`: E3: exclude generic group headings from quantity links.
