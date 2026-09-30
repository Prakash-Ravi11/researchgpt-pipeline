# Phase 01 — PDF identity (Phases 2 and 2.1)

## Objective
Prove that each of the 30 physical PDFs is the paper the candidate dataset describes, and pin one
canonical, hash-verified PDF per paper.

## Inputs
- PDFs: `C:\Users\Praka\Downloads\rgpt-exp-parser\data\medical30_eval\pdfs\` (62 copies recorded across
  locations for 30 papers).
- Acquisition record: `C:\Users\Praka\Downloads\rgpt-exp-parser\data\medical30_eval\raw_metadata\collected_papers.json`.
- The candidate ZIP (Phase 00).
- Scripts:
  - `src/evaluation/bottleneck_diagnosis/phase2_pdf_identity.py` (Phase 2);
  - `src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py` (Phase 2.1, evaluator-only fixes);
  - `src/evaluation/bottleneck_diagnosis/test_phase2_1_pdf_identity.py`.

## Work Performed
Phase 2 ran tests T1–T9: SHA-256, page count, filename, title, authors, arXiv id, and so on. Phase 2.1
fixed three evaluator defects:
- T5: a `NOT_REPORTED` title is now N/A;
- T6: surname matching is superscript-aware;
- T7: only the page-1 arXiv stamp counts.

Phase 2.1 re-ran with every other rule unchanged.

## Results
FACT:
- Phase 2: MATCH_VERIFIED 12, MATCH_WITH_DISCREPANCY 18.
- Phase 2.1, 30 papers: **MATCH_VERIFIED 25, MATCH_WITH_DISCREPANCY 5**, MISMATCH 0, AMBIGUOUS 0, MISSING 0.

  | Test | PASS | FAIL | N/A |
  |---|---|---|---|
  | T1–T4, T8, T9 (each) | 30 | 0 | 0 |
  | T5 | 29 | 0 | 1 |
  | T6 | 29 | 0 | 1 |
  | T7 | 14 | 5 | 11 |

- All 5 remaining discrepancies are T7 (no arXiv stamp on page 1): P006, P012, P017, P020, P030.
- All 62 PDF copies hash to their recorded SHA-256 and were stable after the run.
- Phase 2 artifacts were byte-identical after Phase 2.1.
- Tests: `test_phase2_1_pdf_identity.py` 20 passed (re-run 2026-09-30).

INTERPRETATION: all 30 PDFs are the right papers. The T7 discrepancies concern arXiv stamps, not identity.

## Evidence
| Artifact | SHA-256 prefix |
|---|---|
| `src/evaluation/bottleneck_diagnosis/pdf_identity_manifest.csv` (Phase 2) | `909119d41c523e67` |
| `src/evaluation/bottleneck_diagnosis/pdf_identity_details.json` (Phase 2) | `888f775186ee9728` |
| `src/evaluation/bottleneck_diagnosis/pdf_identity_manifest_v2.csv` (source of truth; `canonical_pdf_path` + `sha256` per paper) | `2177a036cb3ace23` |

Also: `pdf_identity_details_v2.json` and `phase2_1_pdf_identity_report.md`.

## Decisions
DECISION: the PDF for a paper is its `canonical_pdf_path` in `pdf_identity_manifest_v2.csv`. Every later
phase re-hashes it before use and aborts on a mismatch. PDFs are never downloaded or substituted.

## Changes
New untracked scripts, test and artifacts listed above. No tracked file changed.

## Temporary Files
Scratchpad `p012_page1.png` (visual check).

## Cleanup
Deleted 2026-09-30. It was regenerable from the PDF.

## Current State
Complete.

## Next Step
None; superseded.

## Do Not Redo
Identity verification. Use `pdf_identity_manifest_v2.csv`.

## Reproduction
- `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py`
- `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_phase2_1_pdf_identity.py -q`
