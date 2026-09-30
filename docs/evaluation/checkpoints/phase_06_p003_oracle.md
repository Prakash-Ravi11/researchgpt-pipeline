# Phase 06 — P003 acceptance with the unchanged Stage B oracle

## Objective
Show, on the actual P003 PDF with no manual injection and no binder or gate change, that the verified
P003/G002 claim moves from `pdf_only` to bound, and that the gate RETURNS it.

## Inputs
- `stage_b_gold_binder_oracle.py`, imported unchanged: `load_verified` + `run_all`. Its `main()` was never
  called.
- `verified_gold_pairs.json` (SHA-256 `e75d8ef53047e554`).
- The hash-pinned P003 PDF.
- "Before" = HEAD `blocks_from_pdf` executed from `git show`; "after" = the working tree.

## Work Performed
The oracle's context was built exactly as its `main()` builds it (lines 226-238): hash check, then
`process_paper_grounded`, then author surnames. `run_all` ran after the fix and, live, before it. Both
were compared with the stored `gold_binder_oracle.json`.

## Results
FACT (R0 = the production PDF path; verified cell `Proposed Method` × `Dice Score (%)` = `92.3`):

| Claim | Before (stored = live HEAD) | After | Bound cell = verified cell |
|---|---|---|---|
| REAL (the p5 sentence) | `pdf_only`, ABSTAINED unverifiable_binding, 0 cells | `bound` (Proposed Method, Dice Score (%), 92.3), **RETURNED**, OWN_PAPER, provenance p8, 69 cells | True |
| CANONICAL "The Proposed Method achieves a Dice Score (%) of 92.3." | same | same | True |

- The oracle verdict `production_path` went from `PDF_ONLY_NO_STRUCTURED_CELLS` to `bound`.
- The live "before" run was identical to the stored record: True.
- Acceptance checklist, all PASS:
  - Table 3 structured;
  - 92.3 is a cell;
  - entity row label "Proposed Method" chosen over "S.no";
  - cells propagate to chunks;
  - the real claim binds;
  - the canonical claim binds;
  - the gate returns both.

FACT, R1/R2 cases vs the stored record. These changed because their R0 base now carries 69 PDF cells
(77 in total):

| Case | Stored | Now |
|---|---|---|
| REAL\|R1 | `wrong_cell` | `bound` to Proposed Method |
| CANONICAL\|R1 | `wrong_cell` | `bound` to Proposed Method |
| CANONICAL_ROWLABEL\|R1 | `bound` | `wrong_cell` |
| REAL\|R2, CANONICAL\|R2 | `bound` | `bound` |

INTERPRETATION:
- The oracle's own `bound_to_gold_cell` flag is always False for R0: it passes no target
  (`stage_b_gold_binder_oracle.py:174`). Gold identity was checked separately.
- CANONICAL_ROWLABEL flipped because the S.no value "04" is now an ordinary cell. The probe's number "04"
  hits that cell first (`gate.py:482`, case 5b). The direction is to abstain, not to return falsely.

## Evidence
- `src/evaluation/bottleneck_diagnosis/postfix_binder_oracle.json`, key `p003_stage_b_acceptance`
  (SHA-256 `f48dcb6ee98ba7d1`).
- `src/evaluation/bottleneck_diagnosis/postfix_binder_oracle_report.md` §1.
- `src/evaluation/bottleneck_diagnosis/test_postfix_physical_pdfs.py`.

## Decisions
DECISION:
- P003 acceptance is PASSED. Proceed to the larger evaluation (Phases 07–08).
- `gold_binder_oracle.*` stays as the pre-fix record.

## Changes
No source change. New artifacts only (shared with Phase 08).

## Temporary Files
None beyond Phase 08's.

## Cleanup
n/a

## Current State
Complete: PASS.

## Next Step
None; superseded.

## Do Not Redo
- P003 acceptance.
- Never run `stage_b_gold_binder_oracle.py` as a script (it overwrites the pre-fix record).

## Reproduction
Produced by `postfix_evaluate.py` (see Phase 08 for the command), function `p003_stage_b`.
