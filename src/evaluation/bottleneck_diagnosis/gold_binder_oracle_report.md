# Stage B — GOLD→BINDER oracle

Input: `verified_gold_pairs.json` (SHA-256 `e75d8ef53047e554…`), **VERIFIED_POSITIVE pairs only**: P003/G002 (statuses in input: VERIFIED_POSITIVE). The verified labels are machine-assisted and not validated by a human (see the Stage A report).

| | |
|---|---|
| Run | 2026-09-30T00:40:57+00:00, git `30fc85d75d9e` (`claude-code-verification`), PyMuPDF 1.28.2 |
| Production code called (never modified) | `process_paper_grounded`, `blocks_from_jats`/`_jats_table_cells`, `chunk_document`, `structural_bind`, `gate_paper` |
| Determinism | no LLM / retrieval / network; structural_bind and gate_paper are deterministic; in-process double run identical: **True** |
| Reproduce | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_b_gold_binder_oracle.py` |

## 1. Counts

- VERIFIED_POSITIVE pairs: **1**. Tested with the real claim: **1**; with the canonical claim: **1**.
- Cases run: 7 (claim variant × representation), plus a supplementary row sweep over the verified table.

| Claim | Representation | Cells visible to binder | Raw binder status | Bound to the gold cell | Gate final | Abstain reason | First failure |
|---|---|---|---|---|---|---|---|
| REAL | R0_current_pdf | 0 | `pdf_only` | False | ABSTAINED | unverifiable_binding | stage2_representation: PDF table has no structured cells (pdf_only) |
| CANONICAL | R0_current_pdf | 0 | `pdf_only` | False | ABSTAINED | unverifiable_binding | stage2_representation: PDF table has no structured cells (pdf_only) |
| REAL | R1_gold_production_convention | 8 | `wrong_cell` | False | ABSTAINED | binding_wrong_cell | binder: wrong_cell (value is under column 'Dice Score (%)' but for row '04', not the claim's subject OWN) |
| CANONICAL | R1_gold_production_convention | 8 | `wrong_cell` | False | ABSTAINED | binding_wrong_cell | binder: wrong_cell (value is under column 'Dice Score (%)' but for row '04', not the claim's subject OWN) |
| CANONICAL_ROWLABEL | R1_gold_production_convention | 8 | `bound` | True | ABSTAINED | ownership_unverified | gate: ownership_unverified |
| REAL | R2_gold_entity_first | 8 | `bound` | True | RETURNED | — | none (bound to the gold cell and RETURNED) |
| CANONICAL | R2_gold_entity_first | 8 | `bound` | True | RETURNED | — | none (bound to the gold cell and RETURNED) |

Real vs canonical, per representation (bound to the gold cell):

| Representation | REAL bound | CANONICAL bound | Diagnostic class | Gate-rejected although bound |
|---|---|---|---|---|
| R1_gold_production_convention | False | False | **REAL_FAIL_CANONICAL_FAIL** | none |
| R2_gold_entity_first | True | True | **REAL_BOUND_CANONICAL_BOUND** | none |
| R0_current_pdf (production path) | False | False | **PDF_ONLY_NO_STRUCTURED_CELLS** | — |

## 2. Per pair

### P003/G002

- Gold: claim p5 → Table 3 p6: `04 | Proposed Method` × `Dice Score (%)` = `92.3`

- **REAL|R0_current_pdf** — claim: "On the ISLES dataset for ischemic stroke lesion segmentation, our method achieves a remarkable average Dice score of 92.3%, outperforming several state-of-the-art methods, as shown in Table 3."
  - parse: numbers ['92.3'], metric tokens ['dice', 'score'], subject `OWN (implicit)`; binder sees 0 cells (0 under a matching metric column)
  - binder: `{"structured": false, "status": "pdf_only"}`
  - gate: ABSTAINED (unverifiable_binding; evidence UNSUPPORTED, attribution UNKNOWN, provenance None)
- **CANONICAL|R0_current_pdf** — claim: "The Proposed Method achieves a Dice Score (%) of 92.3."
  - parse: numbers ['92.3'], metric tokens ['dice', 'score'], subject `OWN (implicit)`; binder sees 0 cells (0 under a matching metric column)
  - binder: `{"structured": false, "status": "pdf_only"}`
  - gate: ABSTAINED (unverifiable_binding; evidence UNSUPPORTED, attribution UNKNOWN, provenance None)
- **REAL|R1_gold_production_convention** — claim: "On the ISLES dataset for ischemic stroke lesion segmentation, our method achieves a remarkable average Dice score of 92.3%, outperforming several state-of-the-art methods, as shown in Table 3."
  - parse: numbers ['92.3'], metric tokens ['dice', 'score'], subject `OWN (implicit)`; binder sees 8 cells (4 under a matching metric column)
  - binder: `{"structured": true, "status": "wrong_cell", "number": "92.3", "reason": "value is under column 'Dice Score (%)' but for row '04', not the claim's subject OWN", "candidate": {"row": "04", "col": "Dice Score (%)"}}`
  - gate: ABSTAINED (binding_wrong_cell; evidence UNSUPPORTED, attribution UNKNOWN, provenance None)
- **CANONICAL|R1_gold_production_convention** — claim: "The Proposed Method achieves a Dice Score (%) of 92.3."
  - parse: numbers ['92.3'], metric tokens ['dice', 'score'], subject `OWN (implicit)`; binder sees 8 cells (4 under a matching metric column)
  - binder: `{"structured": true, "status": "wrong_cell", "number": "92.3", "reason": "value is under column 'Dice Score (%)' but for row '04', not the claim's subject OWN", "candidate": {"row": "04", "col": "Dice Score (%)"}}`
  - gate: ABSTAINED (binding_wrong_cell; evidence UNSUPPORTED, attribution UNKNOWN, provenance None)
- **CANONICAL_ROWLABEL|R1_gold_production_convention** — claim: "Row 04 achieves a Dice Score (%) of 92.3."
  - parse: numbers ['04', '92.3'], metric tokens ['dice', 'score'], subject `Row 04`; binder sees 8 cells (4 under a matching metric column)
  - binder: `{"structured": true, "status": "bound", "number": "92.3", "table_type": "results", "cell": {"row": "04", "col": "Dice Score (%)", "value": "92.3", "caption": "Table 3: Comparison with state-of-the-art methods on the ISLES dataset."}}`
  - gate: ABSTAINED (ownership_unverified; evidence EXPLICIT, attribution UNKNOWN, provenance body/sec[0]/table-wrap[1])
- **REAL|R2_gold_entity_first** — claim: "On the ISLES dataset for ischemic stroke lesion segmentation, our method achieves a remarkable average Dice score of 92.3%, outperforming several state-of-the-art methods, as shown in Table 3."
  - parse: numbers ['92.3'], metric tokens ['dice', 'score'], subject `OWN (implicit)`; binder sees 8 cells (4 under a matching metric column)
  - binder: `{"structured": true, "status": "bound", "number": "92.3", "table_type": "results", "cell": {"row": "Proposed Method", "col": "Dice Score (%)", "value": "92.3", "caption": "Table 3: Comparison with state-of-the-art methods on the ISLES dataset."}}`
  - gate: RETURNED (returned; evidence EXPLICIT, attribution OWN_PAPER, provenance p8)
- **CANONICAL|R2_gold_entity_first** — claim: "The Proposed Method achieves a Dice Score (%) of 92.3."
  - parse: numbers ['92.3'], metric tokens ['dice', 'score'], subject `OWN (implicit)`; binder sees 8 cells (4 under a matching metric column)
  - binder: `{"structured": true, "status": "bound", "number": "92.3", "table_type": "results", "cell": {"row": "Proposed Method", "col": "Dice Score (%)", "value": "92.3", "caption": "Table 3: Comparison with state-of-the-art methods on the ISLES dataset."}}`
  - gate: RETURNED (returned; evidence EXPLICIT, attribution OWN_PAPER, provenance p8)

Supplementary row sweep (canonical claim for every row of the verified table; not counted as pairs):

| Row | Representation | Claim | Binder | Bound to gold cell | Gate |
|---|---|---|---|---|---|
| 0 | R1_gold_production_convention | The 3D U-Net achieves a Dice Score (%) of 89.7. | `wrong_cell` | False | ABSTAINED binding_wrong_cell |
| 0 | R2_gold_entity_first | The 3D U-Net achieves a Dice Score (%) of 89.7. | `bound` | True | ABSTAINED ownership_unverified |
| 1 | R1_gold_production_convention | The Attention U-Net achieves a Dice Score (%) of 90.5. | `wrong_cell` | False | ABSTAINED binding_wrong_cell |
| 1 | R2_gold_entity_first | The Attention U-Net achieves a Dice Score (%) of 90.5. | `bound` | True | ABSTAINED ownership_unverified |
| 2 | R1_gold_production_convention | The DualSeg achieves a Dice Score (%) of 91.2. | `wrong_cell` | False | ABSTAINED binding_wrong_cell |
| 2 | R2_gold_entity_first | The DualSeg achieves a Dice Score (%) of 91.2. | `bound` | True | ABSTAINED ownership_unverified |
| 3 | R1_gold_production_convention | The Proposed Method achieves a Dice Score (%) of 92.3. | `wrong_cell` | False | ABSTAINED binding_wrong_cell |
| 3 | R2_gold_entity_first | The Proposed Method achieves a Dice Score (%) of 92.3. | `bound` | True | RETURNED  |

## 3. What the production PDF path gives the binder (R0)

- P003: 221 chunks (pdf), **0 with table_cells**; 6 blocks typed `table`: p3: "Table 1: Comparison Table for Exiting Method"; p5: "Table 2: BraTS dataset compared to state-of-the-art"; p6: "Table 3: Comparison with state-of-the-art methods on"; p6: "Table 4: Examples of generated natural language"; p6: "Table 5: Evaluation of natural language explanations"; p7: "Table 6: Segmentation performance on BraTS and". The target value occurs as plain text in chunks from p1, p5, p6, p7, p8.

Code path (read, not modified) that leaves PDF tables without cells:

- `src/evidence/represent.py:12-15` — module contract: 'PDF table blocks do not [carry table_cells] (that is the bindability loss)'
- `src/evidence/represent.py:172-176` — blocks_from_pdf types a block 'table' from its first line and attaches no table_cells
- `src/evidence/represent.py:436-437` — build_document routes representation 'pdf' to blocks_from_pdf
- `src/processing/pdf_parser.py:193-196` — Stage 2 copies table_cells onto chunk records only when the block has them
- `src/evidence/chunker.py:50-52` — chunk_document carries table_cells only from blocks that have them
- `src/evidence/gate.py:273-284` — paper_table_cells pools table_cells from the chunks (empty for a PDF paper)
- `src/evidence/gate.py:432-434` — structural_bind returns status 'pdf_only' when no cells exist
- `src/evidence/gate.py:528-531` — _gate_value abstains with 'unverifiable_binding' on pdf_only
- `src/summarization/summarize.py:1344-1346` — the gate runs only when evidence_grounding.enabled

Configuration facts: `configs/config.yaml`: evidence_grounding.enabled = False; `configs/staging_config.yaml`: evidence_grounding.enabled = True. With the production config the gate (and therefore the binder) is not run at all; R0 is the grounded (staging) path.

