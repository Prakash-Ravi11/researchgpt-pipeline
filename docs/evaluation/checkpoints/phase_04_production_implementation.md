# Phase 04 — Production implementation (single final edit)

## Objective
Insert the validated prototype into `src/evidence/represent.py` exactly, in one final edit, without
redesign.

## Inputs
- The final Phase 03 prototype: marked BEGIN/END helper block plus `blocks_from_pdf`.
- `src/evidence/represent.py` with the two inert Phase 03 edits.

## Work Performed
A script copied the prototype's marked helper block byte-for-byte. It replaced the unique tail of
`blocks_from_pdf` with the version that records caption blocks and calls `_attach_pdf_table_cells`. Then
`inspect.getsource` of every function and all constants were compared, production against prototype.

## Results
FACT:
- Source equality holds for all 10 functions and every constant. The functions: `blocks_from_pdf`, `_ws`,
  `_lines`, `_pdf_table_grid`, `_pdf_grid_problem`, `_is_index_column`, `_is_entity_column`,
  `_pdf_row_label_column`, `_pdf_grid_cells`, `_attach_pdf_table_cells`. The constants: the `_PDF_*`
  constants, `_INDEX_*_RE` and `_WORD_RE`.
- `git diff --numstat`: `src/evidence/represent.py` 220 insertions, 1 deletion.
- Working-tree `represent.py` SHA-256 `b413d68dc3e9795b…`; HEAD version `8abac689a243a26b…`.
- Wiring: `represent.py:182-184`. Helpers: `represent.py:189-397`.
- `represent.py` edits in this phase: 3 in total (the two inert Phase 03 edits plus this final insertion).
  No 4th edit.

## Evidence
- `git diff src/evidence/represent.py`
- Tests in Phase 05.

## Decisions
DECISION:
- No further `represent.py` edit in this programme without a new measured reason. The user said: "Do not
  make a fourth edit to represent.py."
- Defects are reported, not patched around.

## Changes
Production files changed: **only `src/evidence/represent.py`**.
- Not changed: `gate.py`, the binder, `chunker.py`, `pdf_parser.py`, `schema.py`, configs.
- `BLOCKED.md` (+46 lines) holds the directive stop log.
- Nothing committed or pushed.

## Temporary Files
Scratchpad `apply_edit.py` and `represent_head.py` (a copy of HEAD).

## Cleanup
Deleted 2026-09-30. HEAD is available via `git show HEAD:src/evidence/represent.py`.

## Current State
Complete. Production represent.py = validated prototype.

## Next Step
None; superseded by Phase 05.

## Do Not Redo
The implementation and the byte-equivalence check.

## Reproduction
`git diff src/evidence/represent.py` (the full diff is 220+/1−).
