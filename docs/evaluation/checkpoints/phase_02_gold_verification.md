# Phase 02 — Gold verification of the 44 candidates (Stage A) and the pre-fix oracle (Stage B)

## Objective
- Stage A: verify each of the 44 candidate claim→cell pairs against the physical PDF.
- Stage B: run the verified pairs through the unchanged binder and gate, to find where binding fails
  before any fix.

## Inputs
- The candidate ZIP (Phase 00) and the canonical PDFs (Phase 01).
- Scripts:
  - `src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py`;
  - `src/evaluation/bottleneck_diagnosis/stage_b_gold_binder_oracle.py`;
  - `src/evaluation/bottleneck_diagnosis/test_stage_b_oracle.py`.

## Work Performed
- Stage A: deterministic PDF evidence, plus one recorded adjudication per pair, plus an independent
  second pass. Statuses: VERIFIED_POSITIVE, WRONG_CLAIM, WRONG_TABLE, WRONG_ROW, WRONG_COLUMN, WRONG_CELL,
  AMBIGUOUS, NOT_VERIFIABLE.
- Stage B: GOLD→BINDER oracle on the VERIFIED_POSITIVE pairs, over three representations:
  - R0: the current grounded PDF path;
  - R1: the verified table injected through the production JATS converter, in production column order;
  - R2: the same injection with the entity column first.

  Claims: REAL (verified sentence), CANONICAL (template) and CANONICAL_ROWLABEL.

## Results
FACT, Stage A (44 pairs):

| Status | Pairs |
|---|---|
| VERIFIED_POSITIVE | **1** (P003/G002) |
| WRONG_CLAIM | 37 |
| WRONG_TABLE | 4 |
| WRONG_CELL | 2 |
| WRONG_ROW, WRONG_COLUMN, AMBIGUOUS, NOT_VERIFIABLE | 0 each |

Independent second pass: exact status agreement 43/44 (raw; pilot, n<50).

FACT, Stage B (P003/G002). The claim is on p5 and Table 3 on p6; the cell reads `04 | Proposed Method` ×
`Dice Score (%)` = `92.3`.

| Representation | REAL | CANONICAL |
|---|---|---|
| R0 current PDF (0 cells) | `pdf_only`, ABSTAINED unverifiable_binding | same |
| R1 production convention (8 cells) | `wrong_cell` (row '04'), ABSTAINED binding_wrong_cell | same |
| R2 entity first (8 cells) | `bound`, RETURNED, OWN_PAPER | same |

CANONICAL_ROWLABEL on R1 ("Row 04 achieves a Dice Score (%) of 92.3."): `bound`, but ABSTAINED with
ownership_unverified. The in-process double run was identical.

INTERPRETATION: two defects block P003:
- (A) the PDF path yields no `table_cells` (representation);
- (B) a first-column row label is an index ('04'), so implicit-OWN subject matching fails.

## Evidence
| Artifact | Note |
|---|---|
| `stage_a_adjudications.json` | Stage A adjudications |
| `stage_a_independent_verification.json` | Stage A second pass |
| `verified_gold_pairs.json` | SHA-256 `e75d8ef53047e554` |
| `gold_pair_verification.csv`, `gold_pair_verification_report.md` | Stage A outputs |
| `gold_binder_oracle.json` | SHA-256 `db2862d709c2617b`; pre-fix record |
| `gold_binder_oracle.csv`, `gold_binder_oracle_report.md` | Stage B outputs |

All in `src/evaluation/bottleneck_diagnosis/`.

## Decisions
DECISION: fix both defects in the representation layer only (`src/evidence/represent.py`): PDF table
cells, plus an index-aware row label. `gate.py` and the binder stay unchanged. The verified gold and the
claim wording are never changed.

## Changes
New untracked scripts, tests and artifacts listed above. No tracked file changed.

## Temporary Files
Scratchpad `stage_a_imgs/`, `stage_a_mine/` and `stage_a_pairs_input.json` (renders, crops, labelling input).

## Cleanup
Deleted 2026-09-30. The decisions are in the adjudication JSONs, and the renders are regenerable from the PDFs.

## Current State
Complete. P003/G002 is the only verified pair from the candidate ZIP.

## Next Step
None; superseded.

## Do Not Redo
- Stage A adjudication.
- **Do not run `stage_b_gold_binder_oracle.py` as a script.** Its `main()` overwrites `gold_binder_oracle.*`,
  which would replace the pre-fix record with post-fix results. Import its functions instead, as
  `postfix_evaluate.py` does.

## Reproduction
- `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py`
- `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_stage_b_oracle.py -q` (6 passed)
