# Phase 03 — PDF table-cell prototype (scratchpad; production untouched)

## Objective
Design and validate PDF table reconstruction and an index-aware row-label rule on all 30 PDFs before
changing production code.

## Inputs
- The 30 canonical PDFs (Phase 01).
- HEAD `src/evidence/represent.py`.
- Integration pattern from the experimental branch file `src/evidence/represent_layout.py`: cells attach
  only to existing caption blocks.
- PyMuPDF 1.28.2 `page.find_tables()`.

## Work Performed
- Backend: `find_tables()` with its default ruling-line strategy. The text-alignment strategy was probed
  and rejected: it split words across columns and merged rows.
- Integration: cells are attached only to caption-like blocks already typed `table`. Block text, ids,
  char spans and types are unchanged.
- Row label: column 0, unless column 0 is an index and a later column is entity-bearing.
  - Index column: small consecutive integers from 0 or 1, and zero-padded, or index-headed, or unheaded.
  - Entity-bearing column: every cell holds a word and all values are distinct.
- Defects found by the 30-PDF checks and fixed in the prototype:
  1. **Caption pairing bug:** a "table above caption" gap could go negative (−0.4 pt), which swapped P005
     Tables 4 and 5. Fix: gaps are clamped at 0.
  2. **Five garbage grids accepted.** Fix: three validation rules.
     - `stacked_records`: rows stacked into one cell (P019 T1/T2, P027 T1);
     - `wrapped_text_rows`: prose lines as rows (P020 T III);
     - `header_has_no_words`: a data row as the header (P024 T2).
  3. **Caption as header:** PyMuPDF reported the caption line as an "external header" (P005 T1/T7/T8).
     Fix: such headers are ignored.
  4. **Split captions:** captions split across text blocks are completed. All 5 completions are genuine:
     P003 T2/T6, P008 T I/II, P023 T3.

## Results
FACT:

| | First prototype | Final prototype |
|---|---|---|
| Table-typed blocks | — | 158 (122 caption-like) |
| Tables parsed | 33 | **28** |
| Cells | 677 | **643** |
| Row-label rule `first_column` | 31 | 26 |
| Row-label rule `entity_column:1` | 2 | 2 |
| Fallback `no_ruled_table_beside_caption` | 89 | 94 |

- The final prototype's text stream is identical to HEAD on all 30 PDFs; extra keys appear only on table
  blocks.
- Measured over every `find_tables` grid in the 30 PDFs:
  - external-header-is-caption fired only on P005 p4, p13, p18;
  - `stacked_records` fired, on otherwise-accepted grids, only on P019 p9, P019 p10 and P027 p6;
  - `header_has_no_words` fired only on figure and garbage grids;
  - `wrapped_text_rows` fired only on P006 p19, P006 p20, P015 p11, P020 p14 (×2) and P020 p15.

  `wrapped_text_rows` counts a row when column 0 is empty and another cell starts lowercase with ≥ 30
  characters; it fires at ≥ 2 such rows.
- P003 Table 3: rule `entity_column:1 (column 0 'S.no' is an index)`. Cell 92.3 → row "Proposed Method",
  column "Dice Score (%)", page 6.

INTERPRETATION:
- Ruled tables reconstruct reliably. Borderless tables are the coverage gap.
- A malformed grid is worse than none: the binder's token match (`gate.py:459-465`) would bind any row
  named in a merged label.

## Evidence
- `BLOCKED.md`, entry "2026-09-30 Phase — PDF table-cell implementation (after Stage B)", records these
  findings.
- The prototype code now lives, identical, in production: see Phase 04.

## Decisions
DECISION:
- Ship ruled tables only.
- Reject malformed grids.
- No text strategy.
- No hard-coding of P003, "Proposed Method", Table 3 or 92.3.
- Row labels come only from the table's own cells, never from claims.

Stop: directive stop conditions fired (`represent.py` edited 2×, the check script re-run 4×, >20 tool
calls). Recorded in `BLOCKED.md`; the user replied "Proceed".

## Changes
`src/evidence/represent.py` got two inert edits in this phase:
- docstring + `from collections import defaultdict`;
- `captions` list initialisation.

Behaviour stayed identical to HEAD. `BLOCKED.md` +46 lines.

## Temporary Files
Scratchpad `proto/`: `pdf_tables_proto.py`, `check_proto.py`, `rules.py`, `raw.py`, `geom.py`,
`probe_synth.py`, `apply_edit.py`.

## Cleanup
Deleted 2026-09-30. Production equals the prototype (Phase 04), and the findings are recorded here.

## Current State
Complete.

## Next Step
None; superseded by Phase 04.

## Do Not Redo
- Probing the text strategy.
- Measuring the validation rules.
- Any represent.py design iteration without a new, measured reason.

Known limitations (not fixed):
- borderless tables get no cells;
- narrow-cell wraps become spaces ("S.n o", "BLE U");
- multi-row headers are folded once ("top / sub");
- a caption is truncated when the PDF merges it with the table body (P003 Table 3 caption ends "…methods on").

## Reproduction
Not separately reproducible (the scratchpad is deleted). The code is `src/evidence/represent.py:189-397`, and
the behaviour is pinned by `tests/test_pdf_table_cells.py` and `test_postfix_physical_pdfs.py`.
