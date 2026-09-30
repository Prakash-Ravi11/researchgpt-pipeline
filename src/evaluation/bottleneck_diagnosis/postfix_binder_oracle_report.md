# Post-fix GOLD→BINDER evaluation (PDF table-cell fix)

Run 2026-09-30T05:46:03+00:00, git `30fc85d75d9e` (`claude-code-verification`) + working-tree `src/evidence/represent.py` (SHA-256 `b413d68dc3e9795b…`); PyMuPDF 1.28.2. In-process double run identical: **True**. Gold labels are machine-assisted, unvalidated.

BEFORE = git HEAD `blocks_from_pdf` (executed from `git show`); AFTER = working tree. Everything else — `process_paper_grounded`, `chunk_document`, `structural_bind`, `gate_paper` and the Stage B oracle — is unchanged. REAL claims are scored per claim (the binder returns one cell per claim), CANONICAL probes per pair; this unit split was fixed before any evaluation output was read (see the script docstring).

## 1. P003/G002 — the unchanged Stage B oracle (`load_verified` + `run_all`)

Verified gold cell: `Proposed Method` × `Dice Score (%)` = `92.3`. Live BEFORE identical to the stored `gold_binder_oracle.json`: **True**.

| Claim | Before (stored Stage B) | Before (live HEAD) | After | Bound cell = verified gold cell |
|---|---|---|---|---|
| REAL | `pdf_only`, ABSTAINED (unverifiable_binding), attribution UNKNOWN | `pdf_only`, ABSTAINED (unverifiable_binding), attribution UNKNOWN | `bound`, RETURNED, attribution OWN_PAPER; cell `{"row": "Proposed Method", "col": "Dice Score (%)", "value": "92.3"}` | True |
| CANONICAL | `pdf_only`, ABSTAINED (unverifiable_binding), attribution UNKNOWN | `pdf_only`, ABSTAINED (unverifiable_binding), attribution UNKNOWN | `bound`, RETURNED, attribution OWN_PAPER; cell `{"row": "Proposed Method", "col": "Dice Score (%)", "value": "92.3"}` | True |

Oracle verdict production_path: before `PDF_ONLY_NO_STRUCTURED_CELLS` → after `bound`. The oracle's own `bound_to_gold_cell` flag is always False for R0 (it passes no target for R0, stage_b_gold_binder_oracle.py:174); gold identity is checked in the last column.

R1/R2 (verified table injected on top of R0) changed because their R0 base now carries PDF cells:

- REAL|R1_gold_production_convention: `wrong_cell` (8 cells) → `bound` (77 cells), bound `{"row": "Proposed Method", "col": "Dice Score (%)"}`, gate RETURNED
- CANONICAL|R1_gold_production_convention: `wrong_cell` (8 cells) → `bound` (77 cells), bound `{"row": "Proposed Method", "col": "Dice Score (%)"}`, gate RETURNED
- CANONICAL_ROWLABEL|R1_gold_production_convention: `bound` (8 cells) → `wrong_cell` (77 cells), bound `{"row": null, "col": null}`, gate ABSTAINED
- REAL|R2_gold_entity_first: `bound` (8 cells) → `bound` (77 cells), bound `{"row": "Proposed Method", "col": "Dice Score (%)"}`, gate RETURNED
- CANONICAL|R2_gold_entity_first: `bound` (8 cells) → `bound` (77 cells), bound `{"row": "Proposed Method", "col": "Dice Score (%)"}`, gate RETURNED

## 2. Mined verified set — before → after

18 claims / 55 pairs from 12 papers; claim subjects {'own_method': 12, 'dataset_or_cohort': 4, 'baseline_or_cited': 2}.

| | Before | After |
|---|---|---|
| Pairs: table structured (cells on the table page) | 0 | 31 |
| Pairs: target value in a reconstructed cell | 0 | 31 |
| Pairs: target cell correctly reconstructed (table, row, column, value) | 0 | 23 |
| CANONICAL (pairs): binder status | {'pdf_only': 55} | {'pdf_only': 13, 'bound': 4, 'not_bindable': 38} |
| CANONICAL (pairs): bound to the correct cell | 0 | 4 |
| CANONICAL (pairs): RETURNED | 0 | 5 |
| REAL (claims): binder status | {'pdf_only': 18} | {'pdf_only': 9, 'bound': 2, 'wrong_cell': 2, 'not_bindable': 5} |
| REAL (claims): bound to one of its verified cells | 0 | 2 |
| REAL (claims): RETURNED | 0 | 2 |
| REAL own-method claims bound correctly and RETURNED | 0/12 | 2/12 |

Row match of the reconstructed target (after): {'None': 24, 'exact': 25, 'wrong': 6}; column match: {'None': 24, 'exact': 29, 'wrong': 1, 'whitespace_artifact': 1}.

## 3. Failure categories after the fix (earliest stage)

- **REAL claims**: representation:table_not_reconstructed: 11; binder:not_bindable: 3; none: 2; binder:wrong_cell: 2
  - gate abstain reasons: {'unverifiable_binding': 9, 'binding_wrong_cell': 2, 'ownership_unverified': 4, 'evidence_span_not_found_in_paper_chunks': 1}
- **CANONICAL pairs** (representation → binder; gate reported, not judged): representation:table_not_reconstructed: 24; binder:not_bindable: 19; representation:target_cell_row_wrong: 6; none: 4; representation:target_cell_column_wrong: 1; representation:target_cell_column_whitespace_artifact: 1

## 4. Per claim (REAL, after)

| Claim | Paper | Subject | Pairs | Correctly reconstructed | Binder → bound cell | Gate | Failure |
|---|---|---|---|---|---|---|---|
| C005 | P001 | own_method | PF001, PF002 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C010 | P003 | own_method | PF003 | PF003 | `bound` {"row": "Proposed Method", "col": "Dice Score (%)", "value": "92.3"} ✓ | RETURNED  | none |
| C012 | P004 | own_method | PF004 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C013 | P004 | own_method | PF005, PF006 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C021 | P006 | own_method | PF007, PF008, PF009, PF010 | PF007, PF009 | `wrong_cell` | ABSTAINED binding_wrong_cell | binder:wrong_cell |
| C025 | P007 | dataset_or_cohort | PF011 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C026 | P008 | own_method | PF012, PF013, PF014 | PF012, PF013, PF014 | `bound` {"row": "Ours", "col": "Dice↑", "value": "0.87±0.06"} ✓ | RETURNED  | none |
| C027 | P008 | own_method | PF015, PF016 | PF015, PF016 | `wrong_cell` | ABSTAINED binding_wrong_cell | binder:wrong_cell |
| C034 | P011 | dataset_or_cohort | PF017 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C035 | P011 | dataset_or_cohort | PF018, PF019 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C041 | P014 | own_method | PF020, PF021, PF022, PF023, PF024, PF025 | PF020, PF021, PF022, PF023, PF024, PF025 | `not_bindable` | ABSTAINED ownership_unverified | binder:not_bindable |
| C042 | P014 | own_method | PF026, PF027, PF028, PF029, PF030, PF031, PF032, PF033, PF034 | PF029, PF030, PF031, PF032, PF033, PF034 | `not_bindable` | ABSTAINED ownership_unverified | binder:not_bindable |
| C045 | P014 | dataset_or_cohort | PF035, PF036, PF037, PF038, PF039, PF040 | PF035, PF036, PF037 | `not_bindable` | ABSTAINED ownership_unverified | binder:not_bindable |
| C048 | P015 | own_method | PF041 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C052 | P016 | baseline_or_cited | PF042, PF043 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |
| C057 | P017 | own_method | PF044, PF045 | — | `not_bindable` | ABSTAINED ownership_unverified | representation:table_not_reconstructed |
| C058 | P017 | own_method | PF046, PF047, PF048, PF049, PF050, PF051, PF052, PF053, PF054 | — | `not_bindable` | ABSTAINED evidence_span_not_found_in_paper_chunks | representation:table_not_reconstructed |
| C085 | P030 | baseline_or_cited | PF055 | — | `pdf_only` | ABSTAINED unverifiable_binding | representation:table_not_reconstructed |

## 5. Per pair (after)

| Pair | Paper | Table | Structured | Reconstructed target (row/col/value) | CANONICAL binder → gate | CANONICAL failure |
|---|---|---|---|---|---|---|
| PF001 | P001 | Table 4 p13 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF002 | P001 | Table 4 p13 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF003 | P003 | Table 3 p6 | True | exact/exact/exact | `bound` ✓ → RETURNED | none |
| PF004 | P004 | Table 1 p7 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF005 | P004 | Table 2 p8 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF006 | P004 | Table 2 p8 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF007 | P006 | TABLE V p14 | True | exact/exact/whitespace_artifact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF008 | P006 | TABLE V p14 | True | exact/wrong/whitespace_artifact | `not_bindable` → ABSTAINED | representation:target_cell_column_wrong |
| PF009 | P006 | TABLE V p14 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF010 | P006 | TABLE V p14 | True | exact/whitespace_artifact/exact | `not_bindable` → ABSTAINED | representation:target_cell_column_whitespace_artifact |
| PF011 | P007 | Table 3 p10 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF012 | P008 | TABLE I p7 | True | exact/exact/exact | `bound` ✓ → RETURNED | none |
| PF013 | P008 | TABLE I p7 | True | exact/exact/exact | `not_bindable` → RETURNED | binder:not_bindable |
| PF014 | P008 | TABLE I p7 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF015 | P008 | TABLE I p7 | True | exact/exact/exact | `bound` ✓ → RETURNED | none |
| PF016 | P008 | TABLE I p7 | True | exact/exact/exact | `bound` ✓ → RETURNED | none |
| PF017 | P011 | Table 1 p2 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF018 | P011 | Table 1 p2 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF019 | P011 | Table 1 p2 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF020 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF021 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF022 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF023 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF024 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF025 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF026 | P014 | Table 2 p5 | True | wrong/exact/exact | `not_bindable` → ABSTAINED | representation:target_cell_row_wrong |
| PF027 | P014 | Table 2 p5 | True | wrong/exact/exact | `not_bindable` → ABSTAINED | representation:target_cell_row_wrong |
| PF028 | P014 | Table 2 p5 | True | wrong/exact/exact | `not_bindable` → ABSTAINED | representation:target_cell_row_wrong |
| PF029 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF030 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF031 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF032 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF033 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF034 | P014 | Table 2 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF035 | P014 | Table 3 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF036 | P014 | Table 3 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF037 | P014 | Table 3 p5 | True | exact/exact/exact | `not_bindable` → ABSTAINED | binder:not_bindable |
| PF038 | P014 | Table 3 p5 | True | wrong/exact/exact | `not_bindable` → ABSTAINED | representation:target_cell_row_wrong |
| PF039 | P014 | Table 3 p5 | True | wrong/exact/exact | `not_bindable` → ABSTAINED | representation:target_cell_row_wrong |
| PF040 | P014 | Table 3 p5 | True | wrong/exact/exact | `not_bindable` → ABSTAINED | representation:target_cell_row_wrong |
| PF041 | P015 | Table 2 p9 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF042 | P016 | Table 4.2 p22 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF043 | P016 | Table 4.2 p22 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |
| PF044 | P017 | Table 6 p22 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF045 | P017 | Table 6 p22 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF046 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF047 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF048 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF049 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF050 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF051 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF052 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF053 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF054 | P017 | Table 7 p28 | False | None/None/None | `not_bindable` → ABSTAINED | representation:table_not_reconstructed |
| PF055 | P030 | Table 2 p5 | False | None/None/None | `pdf_only` → ABSTAINED | representation:table_not_reconstructed |

## 6. Tables that were not reconstructed (caption block status after the fix)

- P001 "Table 4: Average Dice scores obtained using MAS, nnU-Net [17": fallback_pdf — no_ruled_table_beside_caption
- P004 "Table 1. Ablation study on the validation set to validate th": fallback_pdf — no_ruled_table_beside_caption
- P004 "Table 2. Comparison between ours and existing weakly-supervi": fallback_pdf — no_ruled_table_beside_caption
- P007 "Table 3. Inter-rater agreement results for dHCP dataset. The": fallback_pdf — no_ruled_table_beside_caption
- P011 "Table 1: Summary of the data used for training and quantitat": fallback_pdf — no_ruled_table_beside_caption
- P015 "Table 2: Mean Dice scores (multiplied by 100 for readability": fallback_pdf — no_ruled_table_beside_caption
- P016 "Table 4.2: Performance comparison of the proposed model with": fallback_pdf — no_ruled_table_beside_caption
- P017 "Table 6. GMH-IVH Lesion Segmentation Performance. Abbreviati": fallback_pdf — no_ruled_table_beside_caption
- P017 "Table 7. Diagnostic Performance with and without FreeHemoSeg": fallback_pdf — no_ruled_table_beside_caption
- P030 "Table 2 A brief summary of the deep learn-based methods for ": fallback_pdf — no_ruled_table_beside_caption

Reproduce: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/postfix_evaluate.py <labels.json> <candidates.json>` (inputs recorded by SHA-256 in the JSON).
