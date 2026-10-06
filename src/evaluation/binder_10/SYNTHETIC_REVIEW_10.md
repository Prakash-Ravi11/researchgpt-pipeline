# Phase 10 recovery: synthetic review and fixes

The recovered input SHA-256 is `52702fb251905f1a0edf7a499c499fb521a6e80f3fcd0d47ee150a5489c37677`. The exact 76-file backup and original timestamps/hashes are preserved at `C:/Users/Praka/Downloads/recovery_phase10/20261004_exact/`; see `recovery_manifest.json`. The surviving rewrite and review2 snapshot were byte-identical. Transcript Read payloads also matched every line. The original second review never executed probes: all four agents hit the usage limit.

## Fresh four-lens review

All findings below came from runnable synthetic reproductions, before any gold evaluation. Full before-output records and review scripts are retained in `runs/phase10_recovery/reviews/`. Compact fixtures and assertions ship in `tests/fixtures/binder_v2_recovery.json`, `tests/test_binder_v2_recovery.py`, and the recovered regression harness. Original external scratch files were not edited.

| Lens | Confirmed issue | General fix |
|---|---|---|
| wrongbind_structure | Parentheses around ± or a unit before ± detach uncertainty from its central value | Parse the complete central-value/unit/uncertainty expression |
| wrongbind_structure | Named or comma-separated confidence intervals are ignored | Attach explicit CI phrases to the central value |
| wrongbind_structure | `cm²` truncates to `cm` | Parse and normalize whole unit tokens, including Unicode exponents |
| wrongbind_structure | Negated equality can bind | Exclude explicitly negated equality from binding |
| wrongbind_structure | Long-form conflicting units are ignored | Normalize millimeter/centimeter spellings before checking dimensions |
| wrongbind_table | Caption quantities override a conflicting row/column quantity | Require caption links to agree with the cell's quantity axis |
| wrongbind_table | Lowercase cohort qualifiers in captions are ignored | Carry caption terms into scoped qualifier checks |
| wrongbind_table | A caption's percent sign contaminates unrelated fraction columns | Scope percent to the cell or the caption's named quantity; preserve explicit fraction context |
| lost_legacy | Literal `Our method/model/approach/system` labels are rejected | Recognize full own-method labels while retaining variant exclusions |
| spec_robust | Verifier trusts candidate uncertainty and qualifier links | Re-read claim and attached raw cell, reconstruct links, and recheck structure/conflicts |
| spec_robust | Judge accepts a paper span omitted from its prompt | Require the span in the actual provided evidence as well as paper text |
| spec_robust | Normalized nonverbatim span accepted; claim-only span suppresses STOP | Check exact text and raise `LLMViolation` for spans absent from source/input |

Negation and spelled-out units extend the preregistered explicit vocabulary conservatively; they prevent false binds and do not use gold-specific strings. Single-character labels, decimal-token equivalence, and unregistered metric synonyms remain strict as preregistered. Correct `respectively` constructions can still safely abstain; this is a disclosed coverage limitation.

## Validation

| Check | Python 3.10.18 | Python 3.13.6 |
|---|---:|---:|
| Recovered original pytest suite | 19 passed | 19 passed |
| Recovered regression expectations | 123 passed | 123 passed |
| New confirmed-defect checks | 52 passed | 52 passed |
| 135-value/1,200-cell stress trace | 98 KB, about 0.60 s | 98 KB, about 0.47 s |

The 52 checks contain 51 parameterized cases and one verifier/judge contract test with six assertions of safe outcomes. The original 19 tests include the legacy starting-commit comparison, which the historical dev runner had deselected. No real LLM was called. The recovered regression's claim-only-span assertion was strengthened from silent rejection to the preregistered STOP; the original remains in the immutable backup.

Complete synthetic decisions were identical for both Python runtimes and `PYTHONHASHSEED=0,7`: SHA-256 `f21dd02bd4add11e1e78e814c0bff96da0b9f3b6d58a005bd764368fbaed75b7`. Logs live under `runs/phase10_recovery/logs/`.

## Validation-driver corrections before measurement

The recovered driver was unfinished. Static inspection identified trace caps incorrectly limiting candidate recall, cell-only sweep comparison suppressing new claim/cell associations, incomplete PDF audit evidence, missing-audit acceptance, permissive verdict booleans, and insufficient cardinality checks. The recovered driver now reports uncapped candidate recall, retains complete item text and claim/cell association, emits crop plus text evidence, requires two distinct review files and literal boolean approvals, rejects missing audit packets/evidence, and requires exactly 30 papers/55 pairs/18 claims for S3. S3 no longer runs a v2 sensitivity measurement before the full-suite prerequisite. These fixes precede measurement; the frozen evaluator, gold, and preregistration are unchanged.

The binder remains experimental with default `legacy`. Synthetic results alone do not satisfy Phase 10 S1/S2/S3 or authorize enabling it.

## Full-suite integration checks

S3 passed: 30/30 legacy gate records identical, no pair or claim differences across the 55-pair/18-claim evaluation, newline canary 0. The full pytest suite passes **180/180** under each of `legacy` and `v2` on both Python 3.10.18 and 3.13.6. The frozen gold/evaluator test assertions were preserved.

Integration exposed two additional general failures: numeric `Row NN` labels were interpreted as measured values/compound names, and split-caption context was unavailable to binding despite contiguous source spans. The binder now excludes explicit row identifiers from measured values, accepts their literal labels, uses existing completed captions, and joins only a short caption continuation with matching page and exact adjacent character offsets. Direct quantity headers and strong entity/own-method subjects take precedence over weak metric-as-subject interpretations and generic caption terms. Eight additional synthetic checks cover these causes and negative adjacency/qualifier controls, bringing the recovery test file to **60 checks**. `test_legacy_output_is_identical_to_864f2e8` now explicitly selects legacy, retaining all its original byte-identity assertions.

The final integrated source SHA-256 is `4b04a848c5e8ce57f8d1fa42e26487f5362be3456549eceab0405442df881d3c`. Its decisions on the 51 preserved parameterized fixtures remain identical under both runtimes and hash seeds 0/7. The 123 regression expectations still pass; final stress times were approximately 0.66 s (3.10) and 0.50 s (3.13), with a 98 KB trace.

The separate Python 3.13 environment lacked scikit-learn. Its existing project pin, `scikit-learn==1.7.2`, was installed there; no project dependency declaration changed. Before that environment repair, the standalone pipeline script reported 31 passed/6 missing-sklearn failures. Both runtimes passed the separate 63-check experiment suite.

Final standalone pipeline result after the environment repair: **37 passed, 0 failed on both runtimes**.
The later frozen measurement failed S1/S2 despite the synthetic suite passing; see `PHASE10_REPORT.md`.
The synthetic result is retained as evidence of covered cases, not a general guarantee of precision.
