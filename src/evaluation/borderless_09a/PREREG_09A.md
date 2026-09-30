# PHASE 09A — Pre-registration (committed before any run)

Branch `exp/phase09a-borderless`, created from `30fc85d` with:
- `4d3c183`: commits `src/evaluation/bottleneck_diagnosis/`;
- `797a922`: the phase 04–08 baseline, i.e. the ruled-table `represent.py`, its tests and the checkpoints.

**Baseline = `797a922`.** "Current HEAD" in the brief means this commit: the state on which the 55
pairs were evaluated in phase 08. The phase 04 `represent.py` change was uncommitted before this branch.

## A. Brief — design, gate, controls, pass criteria (verbatim)

> Target set = claims whose earliest failure is "table not reconstructed" (no_ruled_table_beside_caption):
>   P001 T4, P004 T1+T2, P007 T3, P011 T1, P015 T2, P016 T4.2, P017 T6+T7, P030 T2 -> 10 tables / 11 claims.
> Derive from the gold file + report. If it is not exactly 10 tables / 11 claims, STOP and report.
>
> - Do not change the gold file, the binder, or any existing gate logic. Zero deletions in existing src/evidence/ files; additions only.
> - New flag borderless_policy = off | consensus, DEFAULT off, read the same way as disambiguation_policy.
>   With off, output must be byte-identical to current HEAD on all 55 pairs (verify).
> - Only tables currently rejected with reason no_ruled_table_beside_caption go to the new path. Ruled tables never touch it.
> - New deps (docling, transformers, timm, torch) go in <repo root>/requirements-borderless.txt, NOT requirements.txt. Lazy-import them only when borderless_policy != off.
> - Venv: <repo root>/.venv-09a (gitignored). If Python 3.13 wheels fail, use Python 3.11 and record it. Pin exact versions.
>   Docling: pin < 2.118.0 (ACCURATE-mode OTSL regression, docling issue #4255) unless you verify the fix.
> - Run table models on CPU (production qwen2.5:7b needs the 6 GB GPU). Record wall time per table.
> - One process per paper for the validation run. Canary: 0 cell values containing "\n".
> - Counts only in conclusions (n = 10). Anything that cannot run -> UNMEASURED with the exact error; never substitute silently.
>
> STEP 1 — ORACLE CEILING: for each of the 11 target claims, attach ONLY the gold target cell as that table's cells, run the real gate_paper path, record binding status. This is an upper bound (no distractor cells). List claims that do not bind even under the oracle (= binder-blocked, not representation-blocked).
>
> STEP 2 — BACKENDS in src/evidence/borderless.py
>   Parser A: Docling, TableFormerMode.ACCURATE, do_cell_matching=True (structure from model, text from PDF text layer). Keep table bbox.
>   Parser B: microsoft/table-transformer-detection + microsoft/table-transformer-structure-recognition-v1.1-all on the page render (record DPI). Fill cells from PyMuPDF page.get_text("words") by bbox intersection. No OCR.
>   Match each parser's table to the target by page + caption proximity.
>   Convert to the existing table_cell schema (value, column_header, row_label, caption, section).
>   Add a reason code for every rejection: borderless_rejected:{no_candidate|G1|G2|G3|disagree}.
>
> STEP 3 — GATE (per table; any failure -> table stays pdf_only)
>   G1 text-layer fidelity: every numeric cell value (normalize U+2212 minus, ±, thin/nbsp spaces, bold/italic markup, trailing */† markers) occurs as a contiguous word sequence in the PDF text layer inside the table bbox.
>   G2 coverage: every numeric token in the text layer inside the table bbox (excluding caption/footnote lines) is assigned to exactly one cell; no missing, no duplicated.
>   G3 existing structural checks (header <= 40 chars, row label <= 60 chars, >= 2 data rows, >= 2 columns, no newline in headers).
>   CONSENSUS: attach cells only if A and B both pass G1–G3 AND agree on the normalized (row_label, column_header, value) triple for every numeric cell. Otherwise pdf_only.
>
> STEP 5 — VALIDATION (validate_09a.py; same code path as production, flag = consensus)
>   TARGET: the 10 tables / 11 claims. Per table: candidate exists (A, B); rows, columns, headers correct; target cell correct vs gold; non-table text absorbed; false-cell count; gate verdict + reason. Per claim: status before vs after, next to the oracle ceiling.
>   NEG: P019 T1, P019 T2, P027 T1, P020 T III, P024 T2 (the tables where the earlier borderless prototype produced corrupted grids). Accepted/rejected; if accepted, list every cell that differs from the PDF (check against the crop). If any NEG paper cannot be located -> UNMEASURED and P2 cannot pass.
>   REGRESSION: all 55 pairs end to end with flag on vs flag off. Any pair whose status gets worse = regression.
>
> PASS CRITERIA (pre-registered)
>   P1 >= 3 of the 11 target claims bound, from >= 2 papers.
>   P2 zero NEG tables accepted with any incorrect cell.
>   P3 zero regressions across the 55 pairs.
>   P4 zero accepted cells whose value is absent from the text layer.
>
> STEP 6 — DECISION (apply mechanically)
>   All four PASS -> final separate commit "enable borderless_policy=consensus by default", listing P1–P4 in the message.
>   P2 or P4 FAIL -> leave default off; report which table and cell broke it.
>   Only P1 FAIL (safe, but < 3 claims gained) -> leave default off; the report states the gain in counts.
>   In every case, the report ends by naming the next change: the binder residuals (3 not_bindable, 2 wrong_cell) plus any claims the oracle showed as binder-blocked.

## B. Target set (derived before this pre-registration was written)
Derived from `postfix_claim_cell_gold.json` together with the phase 08 per-claim failures in
`postfix_binder_oracle.json`: REAL claims whose failure is `representation:table_not_reconstructed`,
and whose caption block has `table_fallback` = `no_ruled_table_beside_caption`.
**Result: exactly 10 tables / 11 claims.**

| Table (page) | Claims (pairs) |
|---|---|
| P001 Table 4 (p13) | C005 (PF001, PF002) |
| P004 Table 1 (p7) | C012 (PF004) |
| P004 Table 2 (p8) | C013 (PF005, PF006) |
| P007 Table 3 (p10) | C025 (PF011) |
| P011 Table 1 (p2) | C034 (PF017); C035 (PF018, PF019) |
| P015 Table 2 (p9) | C048 (PF041) |
| P016 Table 4.2 (p22) | C052 (PF042, PF043) |
| P017 Table 6 (p22) | C057 (PF044, PF045) |
| P017 Table 7 (p28) | C058 (PF046–PF054) |
| P030 Table 2 (p5) | C085 (PF055) |

## C. Operational definitions (fixed now; any later change is reported as a deviation)

**O1 Flag.** `_borderless_policy()` in `represent.py`, resolved in this order:
- the environment variable `RGPT_BORDERLESS_POLICY`, if it is `off` or `consensus`;
- otherwise the `borderless_policy:` line of `configs/staging_config.yaml` (value before `#`, lowercased), if valid;
- otherwise `off`.

This mirrors `_disambiguation_policy()` on `exp/r4-disambiguation` (`src/evidence/gate.py:541-557`).

**O2 Routing.** Runs after the ruled path, in `blocks_from_pdf`. A caption block goes to `borderless.py`
iff `table_parse_status == "fallback_pdf"` and `table_fallback` starts with
`no_ruled_table_beside_caption`. The reason may carry a suffix `(page grids rejected: …)`; such blocks are
routed too. When the flag is off the hook returns before any import.

**O3 Parser A (Docling).**
- Version `< 2.118.0`, exact pin in `requirements-borderless.txt`.
- Options: `do_ocr=False`, `do_table_structure=True`, `TableFormerMode.ACCURATE`, `do_cell_matching=True`;
  accelerator device CPU.
- Scope: only the caption's page is converted.
- Output: tables on that page, with their bbox (converted to PyMuPDF top-left coordinates) and
  cell grid, including header flags and spans.

**O4 Parser B (TATR).**
- Page render at **150 DPI**.
- Detection: `microsoft/table-transformer-detection`, score ≥ 0.9.
- Structure: `microsoft/table-transformer-structure-recognition-v1.1-all`, run on the detected table
  crop (padding 10 px), score ≥ 0.5, using the classes "table row", "table column" and
  "table column header".
- Cell = row box ∩ column box.
- Cell text: `page.get_text("words")` words assigned to the row and the column of largest overlap with
  the word box, joined in native word order with single spaces. No OCR. CPU.

**O5 Matching a parser table to the target caption.** Same page. Gap rules, exactly the ruled path's
(`represent.py` `_attach_pdf_table_cells`):
- table below the caption: gap = max(0, t.y0 − c.y1);
- table overlapping the caption: 0;
- table above the caption: gap = max(0, c.y0 − t.y1) + 0.5.

A table qualifies when gap ≤ 60 pt and horizontal overlap ≥ 30 % of the narrower width. The smallest gap
wins. No qualifying table means `no_candidate`.

**O6 Grid conversion (both parsers).**
- Header rows: rows flagged as column header (A: any cell with `column_header`; B: row centre inside a
  "table column header" box). If none is flagged, row 0 is the header.
- Several header rows fold per column into "top / sub" (distinct non-empty levels joined with " / ").
- A spanning cell's text sits at its top-left grid position; positions it covers get `None`.
- Row label and cells come from the unchanged ruled-path helpers `_pdf_row_label_column` and
  `_pdf_grid_cells`, giving the `table_cell` schema plus `page`.

**O7 Normalisation N(s).**
1. U+2212 → `-`;
2. remove `**` and `__`;
3. strip trailing `*†‡§¶` markers;
4. remove all whitespace (including U+00A0, U+2002–U+200B, U+202F);
5. casefold.

Whitespace removal makes `0.87±0.06` ≡ `0.87 ± 0.06`. N′ (labels and headers) is the same function.

**O8 G1.** Every body cell whose value contains a digit ("numeric cell") must satisfy: N(value) equals N of
the concatenation of a contiguous run (length ≤ 12) of text-layer words. The run is taken in native order
(block, line, word) from words whose centre lies inside the parser's table bbox.

**O9 G2.**
- Digit words: words inside the table bbox that contain a digit. Excluded: words on caption/footnote
  lines, meaning lines overlapping the caption block bbox, or whose first word (trailing `:.` stripped)
  matches `table|tab|fig|figure|note|notes|abbreviation|abbreviations|*|†|‡|§|¶` (case-insensitive).
- Every grid text containing a digit (headers, row labels, body cells) is assigned the matching run
  nearest its cell centre.
- G2 passes iff every digit word is covered exactly once. Uncovered = missing; covered twice = duplicated.

**O10 G3.** Every header ≤ 40 characters; every row label ≤ 60 characters; ≥ 2 body rows; ≥ 2 columns;
no newline in any header.

**O11 Consensus and output.**
- Accept iff A and B each pass G1–G3, and their multisets of (N′(row_label), N′(column_header), N(value))
  over numeric cells are equal.
- Attached cells: parser A's numeric cells only, with no text-only cells. Block keys: `table_cells`,
  `table_caption` (whitespace-collapsed caption block text), `table_parse_status="parsed"`,
  `table_fallback=None`, `table_backend="borderless:consensus"`, `table_bbox`, `table_row_label_rule`,
  `table_shape`, `table_borderless` (per-parser detail and seconds).
- Rejection: `table_fallback` = original + `; borderless_rejected:<code>`. The code is the first hit in
  the order no_candidate → G1 → G2 → G3 → disagree, over either parser.

**O12 Oracle ceiling (Step 1).**
- Start from the flag-off grounded chunks of the paper.
- The target table's caption-block chunks get `table_cells` = only the claim's gold target cells. Each
  cell: value = `cell_text`, column_header = `" / ".join(column_header_levels)`,
  row_label = `row_label_levels[-1]`, caption = the caption block text, section = the caption block section.
- Run the Stage B oracle's `run_case` (i.e. `structural_bind` + `gate_paper`) with the REAL claim.
- Binder-blocked = not bound to one of its gold cells under the oracle.

**O13 Validation run (Step 5).**
- `.venv-09a`, CPU only (`CUDA_VISIBLE_DEVICES=""`), `RGPT_BORDERLESS_POLICY=consensus`.
- One subprocess per paper calls `process_paper_grounded` and `build_document`. The parent evaluates with
  the unchanged phase 08 evaluator functions (`postfix_evaluate.py`: `reconstruction`, `run_claim`,
  `binding_failure`, `gate_failure`).
- Papers: the 12 gold papers plus the NEG papers P019, P020, P024, P027.
- The same run with the flag off, in `.venv-09a`, is the regression baseline.

**O14 Per-table metrics.**
- Candidate exists (A, B); shape; headers.
- Target cell correct vs gold: the phase 08 rule, row exact AND column exact.
- Non-table text absorbed: any grid text > 60 characters or ≥ 8 words.
- False-cell count: numeric cells failing G1.
- Verdict and reason; wall seconds per parser.

**O15 NEG.** Caption blocks: P019 "Table 1" p9 and "Table 2" p10; P027 "Table 1" p6; P020 "TABLE III" p14;
P024 "Table 2" p8.
- Not located → UNMEASURED, and then P2 cannot pass.
- Accepted → every attached cell is checked against the crop and the text layer (machine-assisted
  reading by the agent).

**O16 Regression (P3).** For each of the 55 pairs, flag off vs flag on, any of the following is a
regression. For the pair's CANONICAL probe, and separately for the pair's REAL claim:
- `bound_correct` True → False;
- `returned` True → False;
- `returned` False → True without `bound_correct`.

For the pair itself: reconstruction `correct` True → False.

**O17 P4.** Every accepted borderless cell is independently re-checked: N(value) must equal N of a
contiguous run anywhere in its page's word layer.

**O18 Flag-off identity.**
- Main `.venv` (production Python 3.10), all 30 PDFs.
- `build_document` blocks and `process_paper_grounded` records, serialised
  `json.dumps(sort_keys=True)`, must be identical between `797a922` (represent.py via `git show`) and the
  new code with the flag off.
- The 55-pair evaluation must also be identical.

**O19 Canary.** Zero cell values containing `\n` across all flag-on outputs.

**O20 P1 counting.** A target claim counts as bound when its REAL claim is `bound_correct` with the flag on
(bound to one of its verified cells), counted by claims and by distinct papers.

**O21** Anything that cannot run is recorded as UNMEASURED with the exact error. Conclusions use counts only.

Known by construction: G1 guarantees that accepted numeric values are in the text layer, so P4 is an
implementation check rather than an independent risk.
