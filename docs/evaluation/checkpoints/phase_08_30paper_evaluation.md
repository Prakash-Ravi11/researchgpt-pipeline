# Phase 08 — 30-paper post-fix evaluation (before → after)

## Objective
Run every verified pair and claim from Phase 07 through the actual pipeline before and after the fix,
with no binder or gate change.
- REAL: the verbatim sentence, scored per claim.
- CANONICAL: the Stage B template, scored per pair.

Record, per stage: structured cell, correct table/row/column/value, binder status, gate status,
returned/abstained, and failure category.

## Inputs
- `src/evaluation/bottleneck_diagnosis/postfix_evaluate.py`.
- `postfix_blind_readings.json` and `postfix_candidates.json` (Phase 07).
- The hash-pinned PDFs.
- Stage B oracle functions (`run_case`, `canonical_claim`, `load_verified`, `run_all`), imported unchanged.
- BEFORE = HEAD `blocks_from_pdf` (from `git show`); AFTER = the working tree.

## Work Performed
Each paper went through `process_paper_grounded` (before and after) → `structural_bind` + `gate_paper`,
via the oracle's `run_case`. The whole evaluation ran twice in-process; the runs were identical.

## Results
FACT (55 pairs / 18 claims / 12 papers; claim subjects: own_method 12, dataset_or_cohort 4,
baseline_or_cited 2):

| | Before | After |
|---|---|---|
| Pairs: table structured (cells on the table page) | 0 | **31** |
| Pairs: target value in a reconstructed cell | 0 | 31 |
| Pairs: target cell correctly reconstructed (table, row, column, value) | 0 | **23** |
| CANONICAL pairs: binder status | `pdf_only` 55 | `pdf_only` 13, `bound` 4, `not_bindable` 38 |
| CANONICAL pairs: bound to the correct cell | 0 | **4** |
| CANONICAL pairs: RETURNED | 0 | 5 |
| REAL claims: binder status | `pdf_only` 18 | `pdf_only` 9, `bound` 2, `wrong_cell` 2, `not_bindable` 5 |
| REAL claims: bound to one of their verified cells | 0 | **2** |
| REAL claims: RETURNED | 0 | **2** |
| REAL own-method claims bound correctly and RETURNED | 0/12 | **2/12** |

- The 2 successes: C010 (P003) → (Proposed Method, Dice Score (%), 92.3), and C026 (P008) →
  (Ours, Dice↑, 0.87±0.06).
- Row match after: exact 25, wrong 6, no cell 24. Column match after: exact 29, wrong 1,
  whitespace_artifact 1, no cell 24.

FACT, failure categories after the fix (earliest stage):

| REAL claims (18) | Count |
|---|---|
| representation: table not reconstructed | 11 |
| binder: `not_bindable` | 3 |
| binder: `wrong_cell` | 2 |
| none | 2 |

REAL gate abstain reasons: unverifiable_binding 9, ownership_unverified 4, binding_wrong_cell 2,
evidence_span_not_found_in_paper_chunks 1.

| CANONICAL pairs (55) | Count |
|---|---|
| representation: table not reconstructed | 24 |
| binder: `not_bindable` | 19 |
| representation: target cell row wrong | 6 |
| none | 4 |
| representation: target cell column wrong | 1 |
| representation: target cell column whitespace artifact | 1 |

Tables not reconstructed (all `fallback_pdf` — `no_ruled_table_beside_caption`): P001 Table 4; P004 Tables 1
and 2; P007 Table 3; P011 Table 1; P015 Table 2; P016 Table 4.2; P017 Tables 6 and 7; P030 Table 2.

FACT, evaluator caveats (reported; the evaluator was not changed after seeing results):
- PF026–PF028 score "row wrong" only because the gold label keeps the ligature "gyri**ﬁ**cation" (U+FB01,
  copied from the text layer) while the cell reads "gyrification". Normalised, correctly reconstructed
  would be **26/55**.
- PF008 scores "column wrong" because the evaluator's tie-break picked the "YOLOv5 / Box" cell, which holds
  the same value 0.947. The Mask cell exists, with the header artifact "Mas k".
- The REAL unit was changed to per-claim before any output was read. The binder returns one cell per
  claim (`gate.py:467-479`). This is disclosed in the script docstring and the report.

INTERPRETATION:
1. **The fix works where it applies** (ruled tables): P003 and P008 claims bind and are RETURNED.
2. **Second bottleneck, the dominant one: borderless tables** (representation). 11 of 18 claims point
   at tables with no ruling lines, which the fix deliberately does not reconstruct.
3. **Binder limits** where the cells are correct (`gate.py`, unchanged):
   - metric vocabulary: 3 P014 claims (volumes, gyrification index, curvedness, placenta) are
     `not_bindable` (`gate.py:455`);
   - comparison claims: "from 0.84 by DSRNet to 0.87 by Ours" is read as a single OWN subject with the
     first number deciding → `wrong_cell` (`gate.py:471`);
   - metric in the caption, not the column header: P006 Table V → `wrong_cell`, case 5b (`gate.py:482`).
4. **Cells anywhere in a paper change the gate path.** Before the fix, every numeric claim in a PDF paper
   was `pdf_only` and abstained. Once any table of the paper has cells, a claim the binder cannot bind
   falls through to grounding and attribution (`gate.py:544`), as JATS/LaTeX papers do. That covers
   `not_bindable` (the metric is not a recognised column) and `not_a_table_claim` (the value is in no cell),
   whether or not the claim's own table was parsed. Seen here:
   - PF013 (P008 TABLE I, parsed, target cell exact): "95HD" is not a recognised metric → `not_bindable` →
     RETURNED without a bind (its value is correct);
   - P017 C057/C058 (Tables 6 and 7 not reconstructed): `unverifiable_binding` → `not_bindable`, still
     ABSTAINED.

   This precision risk is not measured beyond this set. (Corrected 2026-09-30 after the checkpoint audit: an
   earlier wording cited PF013 as an unparsed-table case.)
5. **Index cells** kept as ordinary cells flip a Stage B probe from `bound` to `wrong_cell` (Phase 06).
6. **Text artifacts:** table text expands ligatures, subscripts garble labels ("ADC D _"), and narrow-cell
   wraps insert spaces ("0.94 7", "Mas k", "BLE U").

## Evidence
All in `src/evaluation/bottleneck_diagnosis/`:

| Artifact | SHA-256 prefix |
|---|---|
| `postfix_binder_oracle.json` (per-pair and per-claim before/after, summary, P003 acceptance) | `f48dcb6ee98ba7d1` |
| `postfix_binder_oracle.csv` (one row per unit × representation × variant) | `5599405d38fe0860` |
| `postfix_binder_oracle_report.md` | `0dc3856c63bd717f` |

## Decisions
DECISION:
- **STOP here.** Report the second bottleneck; do not modify the system again.
- No binder, gate, claim-parser or `represent.py` change.
- The next phase needs the user's choice (see `PROGRESS.md`).

## Changes
New untracked artifacts above plus `postfix_evaluate.py` and `test_postfix_evaluate.py`. No tracked file
changed.

## Temporary Files
A first evaluation run wrote the misnamed `postfix_claim_cell_gold_report.md`.

## Cleanup
Deleted 2026-09-30, before the corrected run that wrote `postfix_claim_cell_report.md`.

## Current State
**Complete.** Awaiting the user's choice of the next phase.

## Next Step
Wait for the user's decision on the Phase 09 scope.

## Do Not Redo
The evaluation (deterministic; inputs hash-pinned). Re-run it only after a deliberate, new change.

## Reproduction
```
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/postfix_evaluate.py src/evaluation/bottleneck_diagnosis/postfix_blind_readings.json src/evaluation/bottleneck_diagnosis/postfix_candidates.json
```
This rewrites the 6 `postfix_*` artifacts; the content is identical apart from timestamps.
