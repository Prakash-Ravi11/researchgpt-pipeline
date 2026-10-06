# Phase 10 - Binder v2 recovery and measurement

Completed 2026-10-06 on `exp/phase10-binder`, from recovery HEAD `408137e`.

## Decision

**No enable: S1 and S2 fail; S3 passes.** The recovery and experiment are complete. Binder v2 is
implemented and tested, but remains experimental. Legacy is the default, the fallthrough guard stays
enabled, borderless stays off, and no real v2_llm evaluation was attempted to rescue deterministic v2.

Main report: `src/evaluation/binder_10/PHASE10_REPORT.md`.
Machine-readable results: `src/evaluation/binder_10/results.json` and `results.csv`.
Runtime/log/output evidence: `src/evaluation/binder_10/validation_10.json`.

## Recovery and implementation

Recovered the exact 62,827-byte precision-first rewrite from surviving scratch, identical to review2.
Original SHA-256: `52702fb251905f1a0edf7a499c499fb521a6e80f3fcd0d47ee150a5489c37677`.
Preserved 76 exact artifacts outside the repo at
`C:/Users/Praka/Downloads/recovery_phase10/20261004_exact/`; manifest committed.
The interrupted second four-lens review did not finish: all agents failed at the usage limit.

Fresh synthetic review confirmed and fixed structural-number parsing, scoped quantity/qualifier links,
own-method labels, raw verification, and invalid judge-span handling. Full-suite integration added
general row-identifier and adjacent-caption handling. All fixes preceded gold measurement.
See `SYNTHETIC_REVIEW_10.md:7` and `tests/test_binder_v2_recovery.py:10`.

## Validation

- Python 3.10.18 and 3.13.6: full pytest **180 passed** under each of legacy and v2 (four green runs).
- Separate pipeline **37 passed**, experiment suite **63 passed**, binder regression **123 passed**,
  in each runtime. The 19 original + 60 recovery binder tests are included in the 180 pytest total.
- Mocked LLM safety passed; no real LLM calls. Determinism matched both runtimes and hash seeds 0/7.
- Stress: 135 values / 1,200 cells; about 98 KB trace, 0.66 s / 0.50 s.
- S3: **30/30 PDF gate outputs identical**, 55 pairs / 18 claims unchanged, newline canary **0**.
- Installed only the existing `scikit-learn==1.7.2` project pin in the incomplete 3.13 environment.

## Frozen measurement and audit

| Unit | Legacy correct | v2 correct | v2 wrong (frozen scoring) | Previously correct lost |
| --- | --- | --- | --- | --- |
| R-prod pairs /55 | 4 | 23 | 8 | 0 |
| R-prod real claims /18 | 2 | 3 | 1 | 1 |
| R-eval pairs /55 | 6 | 28 | 9 | 1 |
| R-eval real claims /18 | 4 | 4 | 1 | 3 |
| R-oracle pairs /12 (upper bound) | 6 | 12 | 0 | 0 |
| R-oracle claims /3 (upper bound) | 0 | 1 | 0 | 0 |

All wrong canonical units have absent reconstructed gold targets; the driver counts them
conservatively. C021 overlaps bound-correct and wrong because the frozen evaluator checks its first
cell while S1 checks every selected cell. These qualifications do not change the recorded score.

Two independent PDF reviewers inspected **all 22 distinct new bindings / 51 occurrences** with crops
and text layers. Both accept 21 and reject `28be140170be`: a YOLOv7 confidence threshold is linked to
YOLOv5 glioma-mask mAP. This confirms a semantic wrong bind independently of the scoring caveats.
Verdicts: `src/evaluation/binder_10/audit/verdicts_reviewer_a.json` and `_b.json`.
All labels are **machine-assisted, unvalidated**. No missing audits or disagreements.

S2 also loses 9 R-prod and 13 R-eval sweep associations. Every failed item is listed in the report and
`results.json.criteria.v2`. No product bindings are gained or lost: still zero verified bindings across
75 items; five internal statuses change, but final decisions/reasons do not.

Candidate recall among represented real claims: R-prod **7/7**, R-eval **13/15**, oracle **3/3**;
median candidate-set size 1 and maximum 3, 3, 1 respectively. The denominator is conditional on gold
reconstruction, not all 18 claims. R-prod's earliest-stage distribution is representation 11, linking 3,
ranking 1, gate 1, no failure 2. R-eval: representation 3, candidate recall 2, linking 8, ranking 1,
gate 2, no failure 2. Product coverage is still 3/18 at the gate.

## Commits

- `7f55789`: recovered/fixed implementation, router, recovery inventory and manifest.
- `1cfea2c`: synthetic tests, fixtures, regressions, review evidence.
- `c805cf4`: final pre-measurement validation driver.
- `ad92c87`: measurements, two independent PDF audits and validation record.
- The following report commit records this checkpoint, the report and progress updates.

Secret scans of each intended diff were clean. Raw PDF text trailing whitespace is intentionally
preserved. Gold, evaluator, preregistration, 09A/09B artifacts and configs are unchanged from `408137e`.
The authorized branch is pushed after the report commit; it is not merged into the default branch.
Unrelated untracked `docs/diagnosis/`, `out/`, and `src/evaluation/candidate_gold/` remain untouched.

## Resume boundary

Phase 10 ends here. Do not rerun recovery, measurement or audits. Do not tune this code against its
evaluated claim IDs or revise its ruler after results. A next implementation phase needs explicit scope
and new general synthetic evidence for subject/quantity precision and preservation of legacy successes.
Product claim availability and representation remain earlier bottlenecks; improved candidate recall
alone did not create product gains. Borderless and v2_llm remain disabled.
