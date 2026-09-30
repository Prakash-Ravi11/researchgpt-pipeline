# Phase 09A — Borderless-table backend (Docling + Table Transformer consensus)

**Decision: the default stays `borderless_policy = off`.** No enable commit. Result per criterion:

| Criterion | Result |
|---|---|
| P1 | **FAIL** |
| P2 | **PASS** |
| P3 | **FAIL** |
| P4 | **PASS** |

Branch `exp/phase09a-borderless`:

| Commit | Content |
|---|---|
| `4d3c183` | `src/evaluation/bottleneck_diagnosis/` |
| `797a922` | phase 04–08 baseline (= "current HEAD") |
| `6c1a8b9` | pre-registration, committed before any run |
| `189a037` | backend |
| `6e39fbe` | tests |
| `671afb8` | validation run |
| this commit | report |

Everything below is counted over n = 10 target tables / 11 target claims / 5 NEG tables / 55 gold pairs.
Gold labels, NEG checks and crop reviews are machine-assisted and not validated by a human.

## 1. What was built
- `src/evidence/borderless.py` (new):
  - Parser A: Docling, TableFormer **ACCURATE**, `do_cell_matching=True`, no OCR, CPU.
  - Parser B: Table Transformer detection + `structure-recognition-v1.1-all` on a **150-dpi** render. Cells
    are filled from PyMuPDF words by overlap. No OCR, CPU.
  - Gates G1 (text-layer fidelity), G2 (coverage) and G3 (structure).
  - A/B consensus on every numeric (row label, column header, value) triple.
  - Reason codes `borderless_rejected:{no_candidate|G1|G2|G3|disagree}`; crashes become `borderless_error`.
- `src/evidence/represent.py`: **additions only, +44/−0**.
  - `_borderless_policy()` resolves `RGPT_BORDERLESS_POLICY`, then `configs/staging_config.yaml`, then
    `off`, the same way `disambiguation_policy` is read.
  - `_attach_borderless_cells` routes only `no_ruled_table_beside_caption` rejects, and imports nothing
    when the policy is off.
- `requirements-borderless.txt`: exact pins. `requirements.txt` is unchanged.
- Venv `.venv-09a` (gitignored), **Python 3.13.6**: the 3.13 wheels installed, so Python 3.11 was not needed.

| Package | Version |
|---|---|
| docling / docling-slim | **2.117.0** (below 2.118.0, per issue #4255) |
| docling-core | 2.99.0 |
| docling-ibm-models | 3.15.0 |
| docling-parse | 7.22.1 |
| transformers | **5.17.0** |
| timm | 1.0.30 |
| torch | **2.14.0** (CPU) |
| torchvision | 0.29.0 |
| pymupdf | 1.28.2 (same as production) |

- TATR model commits: detection `2357cbe2b5a5…`; structure v1.1-all `7587a7ef111d…`.
- Two transformers-5 compatibility shims, both documented in the code:
  1. the v1.1-all config ships `"dilation": null`, now rejected; it is set to `False`, which is how
     transformers 4 read it;
  2. the v1.1-all preprocessor gives only `longest_edge: 800`, which transformers 5 rejects; the crop is
     resized to that longest edge and the processor is called with `do_resize=False`.
- Tests: `tests/test_borderless.py`, **13 passed** in both venvs. Full suite: **191 passed, 0 failed**.

## 2. Step 1 — oracle ceiling
Each claim's table gets only its gold target cells; then the real `structural_bind` + `gate_paper` run.

| Claim | Table | Binder under oracle | Bound to gold cell | Gate | Why |
|---|---|---|---|---|---|
| C005 | P001 T4 | `not_bindable` | no | RETURNED | methods are columns: the claim metric (Dice) is in no header |
| C012 | P004 T1 | `wrong_cell` | no | ABSTAINED | implicit-OWN subject; the row "UM-CAM+SPL" is not recognised as own |
| C013 | P004 T2 | **`bound`** | **yes** | ABSTAINED | `bound_to_other_table`, from the single-row oracle table |
| C025 | P007 T3 | `not_bindable` | no | ABSTAINED | no recognised metric (ICC) |
| C034 | P011 T1 | `not_bindable` | no | RETURNED | a count ("15 healthy fetal brains"); no metric |
| C035 | P011 T1 | `not_bindable` | no | ABSTAINED | an age range; no metric |
| C048 | P015 T2 | `not_bindable` | no | ABSTAINED | metric "Dice" is only in the caption; the header is "Global" |
| C052 | P016 T4.2 | `not_bindable` | no | ABSTAINED | metric inside the cell text ("DSC: 83.79%") |
| C057 | P017 T6 | `not_bindable` | no | ABSTAINED | plural "DSCs" not recognised |
| C058 | P017 T7 | `wrong_cell` | no | ABSTAINED | "R2" (reader 2) parsed as the r² metric; implicit OWN |
| C085 | P030 T2 | **`bound`** | **yes** | ABSTAINED | `gate_paper` splits the sentence at "et al."; the fragment is `wrong_cell` |

**Bindable under the oracle: 2 of 11 (C013, C085), from 2 papers. Binder-blocked: 9** (C005, C012, C025,
C034, C035, C048, C052, C057, C058). **P1 (≥ 3 claims bound) is therefore unreachable for any
representation backend on this gold set.**

## 3. Flag-off identity (O18)
Production venv, flag off, compared with baseline `797a922`:
- `build_document` blocks identical on **30/30** PDFs;
- `process_paper_grounded` records identical on **30/30**;
- 55-pair evaluation: **0 pairs and 0 claims differ**.

## 4. Target tables (10)
Timing is per page on CPU from run 2 (A = Docling, B = TATR). A verdict of "accepted" means both parsers
passed G1–G3 and agreed on every numeric triple.

| Table | Verdict | A shape | B shape | Target cells correct (A / B) | Crop review of attached cells | Wall s (A / B) |
|---|---|---|---|---|---|---|
| P001 T4 p13 | **accepted** | 9×5 | 9×5 | 2/2 / 2/2 | 36/36 correct | 14.4 / 2.1 |
| P004 T1 p7 | rejected **G1** | 5×4 | 5×4 | 0/1 / 0/1 | — | 35.6 / 6.0 |
| P004 T2 p8 | **accepted** | 7×5 | 7×5 | 2/2 / 2/2 | 28/28 correct | 8.6 / 1.5 |
| P007 T3 p10 | **accepted** | 5×4 | 5×4 | 1/1 / 1/1 | 15/15 correct | 7.2 / 1.9 |
| P011 T1 p2 | **accepted** | 3×7 | 3×7 | 3/3 / 3/3 | 15/15 correct | 36.0 / 6.5 |
| P015 T2 p9 | **accepted** | 5×8 | 5×8 | 1/1 / 1/1 | 35/35 correct | 10.7 / 1.4 |
| P016 T4.2 p22 | **accepted** | 2×6 | 2×6 | 2/2 / 2/2 | 8/8 correct; **14 numeric cells missing** | 6.1 / 1.7 |
| P017 T6 p22 | rejected **G3** | 7×6 | 11×6 | 0/2 / 1/2 | — | 6.7 / 0.8 |
| P017 T7 p28 | rejected **disagree** | 6×6 | 6×6 | 0/9 / 0/9 | — | 3.4 / 0.5 |
| P030 T2 p5 | **accepted** | 13×4 | 13×4 | 1/1 / 1/1 | 20/20 correct | 17.1 / 3.8 |

Why each rejected table was rejected:
- **P004 T1 (G1):** both parsers merged several rows into one cell (e.g. `74.48±13.26 77.40±13.28`).
  Those joined strings are not a contiguous text-layer run.
- **P017 T6 (G3):** folded headers exceed 40 characters ("Subgroup analysis / Grade I (n = 914 slices)").
  The parsers also disagree on the rows (7 vs 11).
- **P017 T7 (disagree):** Docling leaves the spanning "Radiologist" labels empty, while TATR fills them
  (R1/R2).

Across the 7 accepted target tables:
- all 12 gold target cells are reconstructed correctly by both parsers;
- the crop review found **0 incorrect cells** among the 157 attached, and no absorbed non-table text;
- headers and row labels are correct.

One completeness defect: **P016 T4.2 continues on p23**, and extraction is per page. The p23 rows,
including the "Proposed Model" row, are absent (14 numeric cells).

## 5. Target claims (11): before (flag off) → after (flag on), next to the oracle

| Claim | Oracle | Before | After | Bound to gold cell | Gate after | Earliest failure after |
|---|---|---|---|---|---|---|
| C005 | not_bindable | pdf_only, ABSTAINED | wrong_cell | no | ABSTAINED | binder:wrong_cell |
| C012 | wrong_cell | pdf_only, ABSTAINED | bound, to the same value in **Table 2** | no | ABSTAINED | representation (T1 rejected) |
| C013 | **bound** | pdf_only, ABSTAINED | **bound** | **yes** | ABSTAINED | gate: `bound_to_ablation_table` |
| C025 | not_bindable | pdf_only, ABSTAINED | not_bindable | no | ABSTAINED | binder:not_bindable |
| C034 | not_bindable | pdf_only, ABSTAINED | not_bindable | no | **RETURNED**, unverified | binder:not_bindable |
| C035 | not_bindable | pdf_only, ABSTAINED | not_bindable | no | ABSTAINED | binder:not_bindable |
| C048 | not_bindable | pdf_only, ABSTAINED | not_bindable | no | ABSTAINED | binder:not_bindable |
| C052 | not_bindable | pdf_only, ABSTAINED | wrong_cell | no | ABSTAINED | binder:wrong_cell |
| C057 | not_bindable | not_bindable, ABSTAINED | not_bindable | no | ABSTAINED | representation (T6 rejected) |
| C058 | wrong_cell | not_bindable, ABSTAINED | not_bindable | no | ABSTAINED | representation (T7 rejected) |
| C085 | **bound** | pdf_only, ABSTAINED | **bound** | **yes** | ABSTAINED | none (cited claim, correctly withheld) |

**Gain: 2 target claims now bind to their gold cell (C013, C085), from 2 papers. This equals the oracle
ceiling.** Zero target claims are RETURNED with a verified bind.

C013 is the paper's own headline result, but the gate withholds it as an ablation table. `classify_table`
searches caption + headers + row labels, and a baseline row is named "Ablation-CAM". That is a gate
classification false positive, reported and not changed.

Across all 55 pairs (before → after):

| | Before | After |
|---|---|---|
| Pairs whose table is structured | 31 | 43 |
| Pairs with the target cell correctly reconstructed | 23 | 35 |
| CANONICAL probes bound correctly | 4 | 6 |
| REAL claims bound to a verified cell | 2 | 4 |
| REAL claims RETURNED | 2 | 3 |
| Own-method claims bound and RETURNED | 2/12 | 2/12 |

## 6. NEG tables (5)

| Table | Verdict | Check |
|---|---|---|
| P019 T1 p9 | **accepted**, 24 cells | 24/24 correct (manual + independent agent check) |
| P019 T2 p10 | **accepted**, 24 cells | 24/24 correct. SwinUNetR's DHCP and CRL values are identical *in the PDF itself*; reproduced faithfully |
| P027 T1 p6 | rejected **G3** | — |
| P020 T III p14 | rejected **G1** | — |
| P024 T2 p8 | rejected **no_candidate** | — |

All 5 were located, and none is UNMEASURED. The two accepted P019 tables are the stacked-row grids the
ruled path had to reject; the consensus backend reconstructs them correctly. **P2 PASS.**

## 7. Regression (P3): 6 pairs, all "unverified return"

| Pair | Unit | Before | After |
|---|---|---|---|
| PF001, PF002 | CANONICAL probes of C005 | pdf_only, ABSTAINED | not_bindable → grounding → RETURNED |
| PF006 | CANONICAL probe (HD95) of C013 | pdf_only, ABSTAINED | not_bindable → RETURNED |
| PF017 | REAL claim C034 ("…15 healthy fetal brains…") | pdf_only, ABSTAINED | not_bindable → RETURNED |
| PF018, PF019 | CANONICAL probes of C035 | pdf_only, ABSTAINED | not_bindable → RETURNED |

The mechanism was flagged in phase 08. Once a paper has any cells, a claim the binder cannot bind falls
through to grounding and attribution (`gate.py:544`) instead of abstaining as `pdf_only`. The backend adds
cells to more papers, so more claims take this path. None of the six returned values is shown to be false,
but none is structurally verified. By the pre-registered rule O16 that makes each one a regression.
**P3 FAIL.**

## 8. Pass criteria and decision

| Criterion | Result | Counts |
|---|---|---|
| P1: ≥ 3 of 11 target claims bound, from ≥ 2 papers | **FAIL** | 2 claims (C013, C085), 2 papers; the oracle ceiling is 2 |
| P2: no NEG table accepted with an incorrect cell | **PASS** | 2 accepted (48/48 cells correct), 3 rejected |
| P3: no regression across the 55 pairs | **FAIL** | 6 regressions (unverified returns) |
| P4: no accepted cell absent from the text layer | **PASS** | 533 accepted cells, 0 absent |

The newline canary is **0**. **UNMEASURED: none** (32/32 child processes returned 0).

**Decision (mechanical, STEP 6):** not all four pass, so `borderless_policy` stays `off` and there is no
enable commit. P2 and P4 pass, so no table or cell broke safety. The failures are P1, where the gain is 2
claims (as many as the oracle allows), and P3 (6 unverified returns).

## 9. Whole run (16 papers, all 50 captions routed to the backend)
- Verdicts: **24 accepted / 26 rejected / 0 errors**. Rejection codes: no_candidate 9, disagree 7, G1 7, G3 3.
- Accepted: 533 numeric cells. Crops of every accepted table and every NEG table are in `crops/` (29 PNGs).
- P020 TABLE I was accepted with **0** numeric cells. It is a text-only table (two empty triple sets agree),
  and nothing is attached.
- The runs are **deterministic**. Run 1 and run 2 are identical on every verdict, claim, NEG, criteria and
  summary field. All 24 accepted tables were re-derived afterwards and reproduced the same verdicts and
  cell counts.
- CPU wall time over the 50 routed captions: Docling **1.28–41.16 s per page**, TATR **0.36–6.96 s per
  page**. A consensus child took 25.4–156.5 s per paper with routed tables, model loading included.
  - Exception: the run-2 P017 child took 23,517 s. The gap lies *outside* the parsers (its per-page
    parser seconds are normal). A system suspend at the date change is suspected; it is not compute cost.

## 10. Disclosures
- An API smoke test of both parsers on P001 p13 (a target page) ran before the backend commit. No
  pre-registered rule changed afterwards.
- `validate_09a.py` was edited after run 1 for reporting only. Per-table seconds were read under the wrong
  key and came out empty, and some extra diagnostics were persisted. No scoring rule changed, and run 2
  reproduced every verdict.
- P1 and the oracle use the whole-claim `structural_bind`, as phases 06–08 did. `gate_paper` evaluates
  sentence fragments (C085's fragment reads `wrong_cell`).

## 11. Next change
The representation is no longer what blocks these claims; the binder is. Next, in order:
1. **The binder residuals from phase 08:**
   - 3 `not_bindable`: P014 C041, C042, C045 (clinical measures outside the metric vocabulary);
   - 2 `wrong_cell`: P006 C021 (the metric is in the caption and the columns are models) and P008 C027
     (a comparison claim parsed as a single OWN subject).
2. **The 9 oracle-blocked claims:**
   - C005, C048: metric in the caption, or methods as columns;
   - C012, C058: implicit OWN with a method-named row; "R2" misparsed as r²;
   - C025, C034, C035: no metric (ICC, counts, ranges);
   - C052: metric inside the cell text;
   - C057: plural "DSCs".
3. **Two gate findings, reported only:** the "Ablation-CAM" row label forces ablation classification
   (C013), and sentence splitting at "et al." (C085).
4. **P3's fall-through path**, which must be closed before any backend adds cells by default:
   `not_bindable` → grounding → RETURNED.
