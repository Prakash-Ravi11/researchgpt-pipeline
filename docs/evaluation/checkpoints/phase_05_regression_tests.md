# Phase 05 — Regression tests

## Objective
Deterministic tests for PDF table detection, cell extraction, chunk propagation, caption/page
preservation, index/entity row labels, and prose rejection. The tests also cover P003, plus at least one
test running physical PDF → representation → cells → grounded chunk → binder/gate. No test injects
`table_cells` by hand.

## Inputs
- Production `src/evidence/represent.py` (Phase 04).
- The hash-pinned P003 and P005 PDFs.
- `verified_gold_pairs.json` (expected P003 values come from the verified gold, not from the code).

## Work Performed
Two test files were added in this phase (36 tests). The synthetic tests build real PDFs with PyMuPDF
(ruling lines as vector graphics). A third file, `test_postfix_evaluate.py` (4 tests), was added in
Phase 08 after `postfix_evaluate.py` existed. It is listed below because the final run includes it.

## Results
FACT: tests added in this phase = 36 (30 + 6). With Phase 08's `test_postfix_evaluate.py`, 40 new tests in
total.

| File | Tests | Covers |
|---|---|---|
| `tests/test_pdf_table_cells.py` | 30 | detection, cells, caption/section, page, chunk propagation, index detection (10 cases), entity row label, row-label rule (4 cases), genuine first-column label, prose/boxed prose/borderless → no cells, `stacked_records` rejection, grid validation (6 cases), text stream unchanged, end to end → gate RETURNED; cross-row → `wrong_cell`; pre-fix → `pdf_only` |
| `src/evaluation/bottleneck_diagnosis/test_postfix_physical_pdfs.py` | 6 | P003 Table 3 = verified grid; target cell 92.3; entity row label; split captions completed; real + canonical claims bound and RETURNED; P005 caption pairing |
| `src/evaluation/bottleneck_diagnosis/test_postfix_evaluate.py` (added in Phase 08) | 4 | evaluator gold-assembly and matching rules |

FACT, final run 2026-09-30 (0 failed, 0 skipped):

| Suite | Passed |
|---|---|
| `tests/test_pdf_table_cells.py` | 30 |
| `test_postfix_physical_pdfs.py` | 6 |
| `test_postfix_evaluate.py` | 4 |
| `tests/test_anchors.py` | 9 |
| `test_stage_b_oracle.py` | 6 |
| `test_phase2_1_pdf_identity.py` | 20 |
| `tests/test_portability.py` | 3 |
| **pytest subtotal** | **78** |
| `tests/test_pipeline.py` (script-style) | 37 |
| experiments unit suite (`experiments/document_evidence_pipeline`, own frozen `pipeline/` copy) | 63 |
| **Total** | **178** |

## Evidence
The three test files above.

## Decisions
DECISION: the synthetic tests use generic values only. The P003-specific values live only in the physical
acceptance tests.

## Changes
New untracked test files listed above. No existing test was modified.

## Temporary Files
Scratchpad `probe_synth.py` (layout probe). Also `src/__pycache__/preflight.cpython-310.pyc`, written by
the subprocess in `tests/test_portability.py` despite `-B`.

## Cleanup
Both deleted 2026-09-30. The `.pyc` is git-ignored.

## Current State
Complete. All suites green.

## Next Step
None; superseded.

## Do Not Redo
Test design. Re-run the tests only to verify a new change.

## Reproduction
```
.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_pdf_table_cells.py src/evaluation/bottleneck_diagnosis/test_postfix_physical_pdfs.py src/evaluation/bottleneck_diagnosis/test_postfix_evaluate.py tests/test_anchors.py src/evaluation/bottleneck_diagnosis/test_stage_b_oracle.py src/evaluation/bottleneck_diagnosis/test_phase2_1_pdf_identity.py tests/test_portability.py
.venv/Scripts/python.exe -B tests/test_pipeline.py
cd experiments/document_evidence_pipeline && ../../.venv/Scripts/python.exe -B -m tests.test_pipeline_units
```
