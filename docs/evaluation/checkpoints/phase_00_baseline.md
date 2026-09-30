# Phase 00 — Baseline: repository and candidate-dataset inventory

## Objective
Establish what the repository contains for claim → table-cell binding, and inventory the candidate
claim–cell dataset without treating it as gold.

## Inputs
- Repository at git `30fc85d75d9e` (branch `claude-code-verification`).
- Candidate ZIP `src/evaluation/candidate_gold/researchgpt_candidate_gold_30_2026-09-28 (1).zip`,
  SHA-256 `a11900f2ea572e89e9a4dd9424bf9279c256799f6cdbaca44ed0f60e0ee745ce` (528,329 bytes). It was read
  in place and never extracted, moved or modified. The hash was re-checked unchanged on 2026-09-30.
- Script `src/evaluation/bottleneck_diagnosis/phase1_candidate_gold_inventory.py`.

## Work Performed
- Phase 0: read-only inventory of branches/worktrees, pipeline stages, the table/cell representation,
  the binder (`structural_bind`), the gate, attribution, harnesses and tests → `repository_inventory.md`.
- Phase 1: the script measured the ZIP (integrity, schema, declared vs measured counts, structural checks).

## Results
FACT:
- ZIP: 32 members (`INDEX.json`, `README.txt`, `P001.json` … `P030.json`); CRC test passed; 31/31 JSON
  members parse; `paper_id` matches the file name 30/30.
- Declared = measured: tables 128; cells 8,322 (2,490 with `numeric_value`); claims 661; claim–table
  relationships 87 (21 papers, 86 claims); candidate claim–cell pairs **44** (18 papers), holding 329 cell
  references to 318 unique cells.
- Structural checks: cell `raw_text` equals the table grid for 8,322/8,322 cells. Pair → claim/table/cells
  is consistent for 44/44 pairs and 329/329 cell references.

INTERPRETATION: the dataset is internally consistent, but it is CANDIDATE data. Nothing is verified
against a PDF in this phase.

## Evidence
- `src/evaluation/bottleneck_diagnosis/repository_inventory.md`
- `src/evaluation/bottleneck_diagnosis/candidate_gold_inventory.json`
- `src/evaluation/bottleneck_diagnosis/candidate_gold_schema_report.md`

## Decisions
DECISION: the ZIP is candidate data only. Pairs count as gold only after verification against the
physical PDFs (Phase 02). The ZIP is never moved, renamed, extracted or modified.

## Changes
New untracked files: `phase1_candidate_gold_inventory.py` and the three evidence files. No tracked file
changed.

## Temporary Files
Scratchpad Phase 0 notes: `p0_branches`, `p0_evidence`, `p0_harnesses` and `p0_stages`, each as `.md`
and `.json`.

## Cleanup
Deleted 2026-09-30. Their content is synthesized in `repository_inventory.md`.

## Current State
Complete.

## Next Step
None; superseded by later phases.

## Do Not Redo
- Re-inventorying the ZIP: its hash and counts are fixed above.
- Never touch the ZIP itself.

## Reproduction
`PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase1_candidate_gold_inventory.py`
