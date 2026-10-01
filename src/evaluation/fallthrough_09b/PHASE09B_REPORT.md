# Phase 09B — Fall-through guard (`table_value_guard`) and the borderless re-decision

**Decision (mechanical, STEP 4): enable both defaults.**
> **Superseded by §14 Freeze:** `borderless_policy` was reverted to `off` (`42c08c8`); the guard stays enabled.

- Q1–Q3 all PASS → `fallthrough_policy = table_value_guard`.
- E1–E5 all PASS → `borderless_policy = consensus`.

They are applied in two separate commits after this report. Read §8 before relying on the borderless
enable: E3 is scoped to pairs, as pre-registered, and the same transition occurs on 2 harvested claims
outside the pairs.

| Criterion | Result |
|---|---|
| Q1: the 6 regressions from 09A are ABSTAINED in G1 | **PASS**: 6/6, all `table_value_unbound` |
| Q2: no RETURNED-with-verified-bind lost (L0→G0, L1→G1) | **PASS**: 0 |
| Q3: no new RETURNED-without-bind (G0 vs L0, G1 vs L1) | **PASS**: 0 |
| E1: C013 and C085 bind to their gold cell in G1 | **PASS**: 2/2 |
| E2: NEG unchanged from 09A | **PASS**: 5/5; P019's 48 cells identical |
| E3: no pair goes from ABSTAINED in L0 to RETURNED without a verified bind in G1 | **PASS**: 0 |
| E4: accepted cells absent from the text layer | **PASS**: 0 of 533 |
| E5: no verified bind lost vs L0 | **PASS**: 0 |

Branch `exp/phase09b-fallthrough`, created from `864f2e8`:

| Commit | Content |
|---|---|
| `591d063` | pre-registration, committed before any run |
| `e58dd34` | guard, `gate.py` +69/−0 |
| `23c1ab9` | tests (8) |
| `a1b6414` | two more tests, from the review (§12) |
| `8879681` | validation run: `validate_09b.py`, `results.json` |
| this commit | report, checkpoint, progress |
| next two commits | `enable fallthrough_policy=table_value_guard by default`; `enable borderless_policy=consensus by default` |

Everything below is counted over these units:
- **55 gold pairs**: one CANONICAL probe each.
- **18 gold claims**: REAL.
- **Sweep A**: the 48 harvested claims in the 16 papers, giving 96 gate items.
- **Sweep B** (supplementary): 5,285 gate items, from the text of every chunk of the 16 papers.

Gold labels, NEG checks, the 09A crop reviews and the §8 characterisation are machine-assisted and not
validated by a human.

## 1. What was built
- `src/evidence/gate.py`, **additions only (+69/−0)**:
  - `_fallthrough_policy()` (`gate.py:510-525`) resolves, in order:
    - `RGPT_FALLTHROUGH_POLICY`;
    - the `fallthrough_policy:` line of `configs/staging_config.yaml`;
    - `legacy`.

    It is read at every call, and has the code shape of `represent._borderless_policy()`
    (`represent.py:413-430`).
  - `numeric_tokens`, `claim_value_tokens` and `table_value_tokens` (`gate.py:528-552`).
    - Tokens are whole, unsigned numeric tokens, read per word after `borderless.norm` (the G1
      normalisation).
    - Claim values are the tokens that have a `.` or at least 2 digits.
    - Table values are the tokens of every attached cell value and of the text of every chunk whose
      `block_type` is `table`.
  - The guard (`gate.py:606-615`) runs at the fall-through point, and only when all three hold:
    - the binder status is `not_bindable` or `not_a_table_claim`;
    - the policy is `table_value_guard`;
    - some claim value is a table token.

    Then the claim is ABSTAINED with reason `table_value_unbound`. The rationale string is the code
    comment.
- `tests/test_fallthrough_guard.py`: 10 tests.
  - The brief's 7.
  - Flag resolution, tested against a temporary config.
  - Two added after the review: `bound` and `wrong_cell` claims are untouched by the guard; token
    equality holds on table-block text too.
- `src/evaluation/fallthrough_09b/validate_09b.py` has four modes: `identity`, `children`, `run` and
  `analyze`.
  - It imports 09A's harness unchanged.
  - The L1 reproduction check calls 09A's own `run()` analysis, with its child call replaced by our
    outputs.
- Not touched: the binder matching logic, `represent.py`, `borderless.py`, the gold, `requirements.txt` and
  every existing config key.
- **Full suite: 201 passed, 0 failed.**
  - pytest: 101, including the 10 guard tests;
  - `tests/test_pipeline.py`: 37;
  - experiments unit suite: 63.
- Dry run for D14: also 201/201 with both flags enabled through the environment.

## 2. STEP 2 — identity vs `864f2e8` (production `.venv`, legacy + off)
- Gate records are identical on **30/30 PDFs**: 11,128 inputs (every harvested claim plus every chunk
  text), giving 9,507 gate items.
- 55-pair evaluation, old gate vs new gate: **0 pair differences, 0 claim differences**.
- Sensitivity control: the same records under `table_value_guard` differ on 8 PDFs (P003, P005, P006,
  P008, P009, P012, P014, P023). So the comparison can detect the guard.

## 3. STEP 3 — the 2x2 run
- Arms:
  - L0 = legacy + off;
  - G0 = guard + off;
  - L1 = legacy + consensus;
  - G1 = guard + consensus.
- Papers: 09A's 16 (the 12 gold papers plus NEG P019, P020, P024, P027).
- Children:
  - 4 × 16 = 64 child processes (09A's child), in `.venv-09a`, CPU only;
  - run in the order L0, G0, L1, then the reproduction check, then G1.
- Gating runs in the parent, with `RGPT_FALLTHROUGH_POLICY` set per arm.
- **L1 reproduces 09A exactly.** 09A's own analysis on the L0/L1 outputs gives a payload identical to
  `borderless_09a/results.json#validation`. That is 0 differences once the timing keys are removed, and
  the package versions are identical too.
- **Representation does not depend on the fall-through flag.** Records are identical L0 = G0 on 16/16
  papers and L1 = G1 on 16/16. The table blocks differ only in timing.
- The run took two invocations (§12, disclosure 2).

## 4. 2x2 summary — units / RETURNED (with verified bind / without bind)

| Arm | 55 pairs (CANONICAL) | 18 claims (REAL) | Sweep A (96 items) | Sweep B (5,285 items) |
|---|---|---|---|---|
| L0 legacy + off | 5 (4 / 1) | 2 (2 / 0) | 4 (1 / 3) | 533 (5 / 528) |
| G0 guard + off | 4 (4 / 0) | 2 (2 / 0) | 4 (1 / 3) | 501 (5 / 496) |
| L1 legacy + consensus | 10 (4 / 6) | 3 (2 / 1) | 10 (1 / 9) | 778 (5 / 773) |
| G1 guard + consensus | 4 (4 / 0) | 2 (2 / 0) | 6 (1 / 5) | 669 (5 / 664) |

"Verified bind" means `bound_correct` for pairs and claims, and binder status `bound` for sweep items
(PREREG D10).

Binder status of the 55 CANONICAL probes:

| Arms | `pdf_only` | `bound` | `not_bindable` |
|---|---|---|---|
| L0, G0 | 13 | 4 | 38 |
| L1, G1 | 0 | 7 | 48 |

Abstain reasons of the 55 CANONICAL probes:

| Reason | L0 | G0 | L1 | G1 |
|---|---|---|---|---|
| `table_value_unbound` | — | 27 | — | 39 |
| `unverifiable_binding` | 13 | 13 | — | — |
| `evidence_span_not_found_in_paper_chunks` | 29 | 11 | 33 | 9 |
| `ownership_unverified` | 8 | — | 9 | — |
| `bound_to_ablation_table` | — | — | 2 | 2 |
| `binding_wrong_cell` | — | — | 1 | 1 |

## 5. Guard criteria
**Q1.** All 6 units are ABSTAINED in G1 with `table_value_unbound`. Each matched an attached
(borderless-accepted) cell that holds the value the binder did not bind:

| 09A regression (unit) | Matched value | Cell (row \| column) = value, table |
|---|---|---|
| PF001 (CANONICAL) | 0.926 | [Average \| Ours] = `0.926 ± 0.012`, P001 Table 4 |
| PF002 (CANONICAL) | 0.920 | [Average \| nnU-Net] = `0.920 ± 0.014`, P001 Table 4 |
| PF006 (CANONICAL) | 4.04 | [UM-CAM+SPL (ours) \| Test set / HD95 (pixels)] = `4.04±4.26*`, P004 Table 2 |
| PF017 (REAL, claim C034) | 15 | [TRAINING \| Number of subjects] = `15`, P011 Table 1 |
| PF018 (CANONICAL) | 21 | [EVALUATION Quantitative \| Gestational age (weeks)] = `21-38`, P011 Table 1 |
| PF019 (CANONICAL) | 38 | the same cell, `21-38` |

**Q2: 0.** RETURNED with a verified bind, in both L0 and L1: pairs 4, claims 2, Sweep A 1. All are kept.

**Q3: 0.** RETURNED without a bind in G0 / G1: pairs 0 / 0, claims 0 / 0, Sweep A 3 / 5. Each of these
was already so in L0 / L1.

## 6. Borderless criteria (G1 vs L0)
- **E1.** C013 and C085 are `bound_correct` in G1. The gate still withholds both, for the two gate
  findings from 09A, which are unchanged:
  - C013 is `bound_to_ablation_table`, because of the "Ablation-CAM" row;
  - C085's gated sentence is `binding_wrong_cell`, because of the split at "et al.".
- **E2.**
  - P019 Table 1 is accepted with 24 cells and Table 2 with 24. These 48 cells are identical to 09A's
    reviewed cells.
  - P027 Table 1 is rejected (G3), P020 TABLE III rejected (G1), and P024 Table 2 rejected
    (no_candidate). These are 09A's codes.
- **E3.** 0, out of 101 pair units that are not RETURNED in L0.
- **E4.** 533 accepted borderless cells in 10 papers; 0 are absent from the text layer.
- **E5.** 0. Bound in L0: pairs 4, claims 2, Sweep A 2.

## 7. Returns removed by the guard (the recall cost)
Counts below; every item is listed in Appendix A and in `results.json` (`run.returns_removed_by_guard`).

| Comparison | Pairs | Claims | Sweep A | Sweep B |
|---|---|---|---|---|
| L0 → G0 | 1 | 0 | 0 | 32 |
| L1 → G1 | 6 | 1 | 4 | 109 |

Which source the matched value came from:

| Comparison | Units | Attached cell | Caption-block text only | Prose typed as a table only |
|---|---|---|---|---|
| L0 → G0 | pairs | 1 | 0 | 0 |
| L0 → G0 | Sweep B | 28 | 1 | 3 |
| L1 → G1 | pairs | 6 | 0 | 0 |
| L1 → G1 | claims | 1 | 0 | 0 |
| L1 → G1 | Sweep A | 3 | 1 | 0 |
| L1 → G1 | Sweep B | 75 | 13 | 21 |

- All 7 pair and claim removals were RETURNED without a verified bind. No verified return was removed (Q2).
- "Prose typed as a table" (FACT): a PDF block whose first line starts with "Table " is typed `table`
  (`represent.py:178-179`). An example is "Table 4 presents the segmentation results …". Under D5(ii) its
  numbers count as table values, and 24 removals rest only on such blocks (3 + 21).
- FACT (Appendix A, not labelled): some removals match numbers that are not table values in the claim's
  sense. Examples:
  - dates: L0 → G0 Sweep B #6, "Received : 02 October 2024";
  - years, via prose typed as a table: "FeTA 2024", "MICCAI 2024";
  - table and section numbers: "Table 4.3", "4.4 Ablation";
  - a "p < 0.05" matching a caption's 0.05.

  Many others are table-body rows that ended up in ordinary text, such as "88.7 ± 3.2 4.6 ± 2.1".

## 8. What the guard does not close (G1 vs L0; outside the pre-registered criteria)
- **Sweep A: 2 items** go from ABSTAINED (`pdf_only`) in L0 to RETURNED without a bind (`not_bindable`) in
  G1: C036#0 (P011) and C047#0 (P015). Both are also RETURNED in L1.
- **Sweep B: 169 items** do the same (153 `not_bindable`, 16 `not_a_table_claim`). All are also RETURNED
  in L1. Separately, the guard abstains 33 other items that L0 returns.
- Mechanism (FACT):
  - Once a paper has any attached cell, its other numeric claims are no longer `pdf_only`
    (`gate.py:432-434`). They reach the fall-through.
  - The guard sees only attached cells and table-block text. The body of a pdf_only table sits in ordinary
    paragraph blocks (`represent.py:193-195`), so its values are invisible to the guard (PREREG D5).
  - C036#0 is exactly this case. Its value is the verbatim body of P011 Table 2, which is still pdf_only,
    while P011's 15 attached cells come from Table 1.
- Characterisation (machine-assisted, unvalidated; two independent recomputations agree):
  - **26 of the 171** items (Sweep A 2/2, Sweep B 24/169) carry a value that a borderless parser grid of a
    *rejected* table recorded as a cell. 145 do not.
  - 38 of the Sweep B items sit on a page with a non-parsed table caption block.
  - C047#0's match looks coincidental: integers 24 and 33, in cells `24/16` and `33/7` of a rejected grid
    on another page. C036#0 is a clear case.
- **Consequence for the decision.** E3 is scoped to pairs, as the brief and D13 say, and it passes. If E3
  had covered Sweep A, as E5 does, it would fail on C036#0 and C047#0, and STEP 4 would enable only the
  guard. The decision here follows the pre-registration. Reverting only the borderless enable commit
  restores `borderless_policy=off` without touching the guard.

## 9. Decision
Applied mechanically (STEP 4, D14):
- Q1–Q3 PASS → commit "enable fallthrough_policy=table_value_guard by default".
- E1–E5 PASS → commit "enable borderless_policy=consensus by default".

How the two commits change the repo:
- Each adds one line to `configs/staging_config.yaml`. No existing key changes, and `gate.py` stays
  +69/−0.
- The borderless commit also updates the two expected defaults in
  `tests/test_borderless.py::test_flag_resolution` (lines 135 and 139, `off` → `consensus`), as D14
  allows.
- The full suite is re-run for each commit.

FACT: the production `.venv` has no docling or torch. With `borderless_policy=consensus` there, a routed
caption records `borderless_error:<exception>` and stays pdf_only (`borderless.py:409-415`, `430-434`;
never a silent rejection). The backend needs an environment built from `requirements-borderless.txt`.

## 10. Timing
- Child wall time per arm:

  | L0 | G0 | L1 | G1 |
  |---|---|---|---|
  | 17.4 s | 17.0 s | 506.9 s | 460.7 s |

- Per-parser seconds per page (49 pages per consensus arm):

  | Parser | L1: range | L1: total | G1: range | G1: total |
  |---|---|---|---|---|
  | A (Docling) | 1.22–44.21 | 388.5 | 1.27–17.83 | 346.6 |
  | B (TATR) | 0.28–5.52 | 75.4 | 0.30–4.20 | 72.1 |

  09A measured Docling 1.28–41.16 s per page.
- The harness reminder estimated about 7 h per consensus arm, from 09A's total of 24,361.6 s. Of that total,
  23,517.2 s was one child (P017), where 09A suspected a system suspend. The other 15 children of 09A took
  844.4 s, against 780.5 s of their parser time. 09B had no gap: each consensus arm took about 8 minutes.

## 11. Versions
- Identity (`.venv`): Python 3.10.18, pymupdf 1.28.2, pyyaml 6.0.3, tqdm 4.70.0.
- Run (`.venv-09a`): Python 3.13.6, docling 2.117.0, transformers 5.17.0, torch 2.14.0, pymupdf 1.28.2.
  The full list is in Appendix A. It is identical to 09A's versions (checked by the reproduction).

## 12. Disclosures
1. **Branch base.** The branch starts at `864f2e8`, as the brief says. The docs-only `92c85e3` is not an
   ancestor; `src/`, `tests/` and `configs/` are identical in both.
2. **Two run invocations.**
   - Invocation 1 started at 00:46:17Z. It ran L0, G0 and L1, passed the reproduction check, and ran 15 of
     the 16 G1 children.
   - A read-only review of the harness then found three deviations from the pre-registration in its
     analysis code. The review used 3 agents, and no analysis existed yet. The deviations:
     - any missing child made all criteria UNMEASURED, while D15 says per criterion;
     - resumes were not logged (D8);
     - the 55-pair units had no matched tokens (D9).
   - At about 01:02Z I stopped invocation 1 while P030 G1 was running (logged as exit 127), before its
     analysis started.
   - I fixed the analysis and logging code. The child code path, `validate_09a.child`, is unchanged. I
     checked the fix on smoke data.
   - Invocation 2 started at 01:06:37Z. It reused 63 outputs, ran P030 G1, re-checked the reproduction,
     then ran the only analysis. No result was computed before the fix.
   - `_invocations` lists only invocation 2, because the logging was part of the fix. The per-child start
     and end times of invocation 1 are in the same log.
3. **Two tests added** after the review (`a1b6414`), before the analysis.
4. **Verification.** Two independent agents recomputed every criterion and count from the 64 raw child
   outputs with their own code: 0 mismatches. Their scripts were scratch files and are not kept.
5. **Truncated values.** `results.json` stores sweep item values cut to 300 characters; 11 Sweep A items
   per arm are longer. The final, reason and binding fields are complete.
6. **Superseded 09A fields.** The 09A-format guard payload (`run.guard_arms_in_09A_format`) still reports
   09A's P1–P4 (P1 false, P2 MANUAL_CHECK_REQUIRED). Per PREREG §B these are superseded by E1–E5 and are
   not decision inputs.
7. **P024 Table 2.** Two caption blocks on p8 match it. The first is used, as in 09A.
8. **Timing estimate.** The reminder's "~7 h per arm" was wrong (§10).
9. **UNMEASURED: none.** 64/64 child outputs are present, all with return code 0.

## 13. Next change
Phase 10 is the binder. 09B adds two measured items to its scope:
- the D5 gap, which lets the values of a pdf_only table's body through once the paper has any cells (§8);
- the guard's recall cost: dates, years, section numbers and prose typed as a table matched by token
  (§7).

## 14. Freeze (phase 10 package, Part 1, 2026-10-01)
- **Borderless default reverted.** `42c08c8` reverts `d1b7506` ("enable borderless_policy=consensus by
  default"). Reasons:
  - with borderless on, G1 vs L0 has 171 unbound returns outside E3's scope (§8);
  - the production `.venv` has no docling, so consensus there records `borderless_error` and attaches no
    cells.

  `borderless_policy` is back to its code default, `off`, and `tests/test_borderless.py::test_flag_resolution`
  is back to the `off` default. The guard (`534dd4b`) stays enabled. Full suite: 201 passed, 0 failed.
- **Phase 09C — Region Guard. STATUS: DEFERRED.** Borderless consensus produced 171 unverified returns vs
  L0 (legacy, borderless off). The guard alone added 0 unbound returns in all four unit kinds (Sweep B
  528 -> 496 = exactly its 32 removals). A region guard can only remove returns; it is needed only to
  enable borderless, which Phase 10 does not require.
- **Guard recall check (L0 → G0, read-only).** These are the 33 returns the guard removed without borderless
  (`run.returns_removed_by_guard["L0->G0"]`: 1 pair, 32 Sweep B items).
  - Each item had two independent agent checks against the PDF (crop + text layer).
  - **correct abstention**: the same quantity is printed in a table.
  - **coincidental**: a date, section/table/page number, prose typed as a table, or a different quantity.
  - **unclear**: the two checks disagree.
  - The verdicts are machine-assisted and not human-validated.

  | Verdict | Count |
  |---|---|
  | correct abstention | **20** |
  | coincidental | **13**: different quantity 6, prose typed as a table 3, section/table/page number 3, date 1 |
  | unclear (the checks disagree) | **0** |

  Every item:

| # | Unit | Paper | Compared tokens | Verdict (both checkers) | Kind | Checker 1: why | Checker 2: why |
|---|---|---|---|---|---|---|---|
| 1 | PF013 | P008 | 0.96, 95 | correct abstention | — | The probe's 0.96 is the 95HD (mm) of 'Ours', and Table I (p7) prints Ours 95HD(mm)↓ = 0.96±0.38. The extra '95' match is the same metric name '95HD' i… | The synthetic probe's 0.96 is Ours' 95HD (mm), and the matched cell is Table I Ours / 95HD(mm)↓ = 0.96±0.38, the same quantity (its '95' token also hi… |
| 2 | Sweep B 380729d6:125#0#0 | P003 | 0.38, 0.41, 0.44, 0.47, 0.56, 0.59… | correct abstention | — | The item is Table 5 body text (p6): rows '01 BraTS 0.41 0.62 0.47 0.59' and '02 ISLES 0.38 0.59 0.44 0.56' are the S.no and the BLEU/ROUGE-1/ROUGE-2/R… | The item is Table 5 body text (01 BraTS BLEU 0.41, ROUGE-1 0.62, ROUGE-2 0.47, ROUGE-L 0.59; 02 ISLES 0.38/0.59/0.44/0.56) and matches those same Tabl… |
| 3 | Sweep B 380729d6:147#0#0 | P003 | 2.1, 3.2, 4.6, 88.7 | correct abstention | — | The item is Table 6 body text (p7), row BraTS Whole Tumor: Dice 88.7 ± 3.2 and Hausdorff 4.6 ± 2.1. These are the same as the Table 6 cells and as Tab… | The item is Table 6 body text for BraTS Whole Tumor (Dice 88.7 ± 3.2 %, Hausdorff 4.6 ± 2.1 mm) and matches the same Table 6 cells, plus Table 2's Pro… |
| 4 | Sweep B 380729d6:148#0#0 | P003 | 3.4, 4.7, 5.9, 85.4 | correct abstention | — | The item is the Table 6 row BraTS Tumor Core (Dice 85.4 ± 4.7, HD 5.9 ± 3.4), the same quantities as the matched Table 6 cells and Table 2's Proposed … | The item is Table 6 body text for BraTS Tumor Core (Dice 85.4 ± 4.7 %, Hausdorff 5.9 ± 3.4 mm) and matches the same Table 6 cells, plus Table 2's Prop… |
| 5 | Sweep B 380729d6:150#0#0 | P003 | 4.2, 6.8, 7.1, 79.2 | correct abstention | — | The item is the Table 6 row BraTS Enhancing Tumor (Dice 79.2 ± 6.8, HD 7.1 ± 4.2), the same quantities as the matched Table 6 cells and Table 2's Prop… | The item is Table 6 body text for BraTS Enhancing Tumor (Dice 79.2 ± 6.8 %, Hausdorff 7.1 ± 4.2 mm) and matches the same Table 6 cells, plus Table 2's… |
| 6 | Sweep B 380729d6:152#0#0 | P003 | 1.7, 2.8, 3.1, 92.3 | correct abstention | — | The item is the Table 6 row ISLES Ischemic Lesion (Dice 92.3 ± 2.8, HD 3.1 ± 1.7), the same quantities as the matched Table 6 cells and Table 3's Prop… | The item is Table 6 body text for ISLES Ischemic Lesion (Dice 92.3 ± 2.8 %, Hausdorff 3.1 ± 1.7 mm) and matches the same Table 6 cells, plus Table 3's… |
| 7 | Sweep B 380729d6:19#0#0 | P003 | 02, 03, 10.22399, 2024 | coincidental | date | The item's 02 and 03 are the days in 'Received: 02 October 2024' and 'Accepted: 03 October 2024' (p1 front matter). They matched the row serial number… | The item's 02 and 03 are the days of the month in the page-1 article dates 'Received: 02 October 2024 / Accepted: 03 October 2024', while the matched … |
| 8 | Sweep B 380729d6:37#0#0 | P003 | 90.1 | correct abstention | — | The item is Table 1 body text (p3), row Attention U-Net [14]: 'BraTS MRI 90.1 -'. Its 90.1 is the matched Dice Score (%) cell 90.1. | The item is Table 1 body text for Attention U-Net [14] (BraTS, MRI, Dice 90.1 %, '-') and matches that same Dice Score (%) cell, 90.1. |
| 9 | Sweep B 380729d6:41#0#0 | P003 | 91.5, 96.2 | correct abstention | — | The item is Table 1 body text (p3), row Wang et al. [23]: BraTS, LiTS / MRI, CT / 91.5, 96.2 / Textual. Its 91.5 and 96.2 are the matched Dice Score (… | The item is Table 1 body text for Wang et al. [23] (BraTS, LiTS / MRI, CT / Dice 91.5, 96.2 % / Textual) and matches that same Dice Score (%) cell, '9… |
| 10 | Sweep B 562fa0fc:10#1#0 | P006 | 0.657, 0.666 | correct abstention | — | The abstract gives YOLOv5 mAP@0.5:0.95 as 0.666 (box) and 0.657 (mask). Table VI (p15), row All, prints YOLOv5 Box 0.666 and Mask 0.657, so the matche… | The abstract's 0.657 is YOLOv5's all-class mask-segmentation mAP@.5:.95, the same as Table VI row All / YOLOv5 Mask = 0.657; the paired 0.666 is the B… |
| 11 | Sweep B 562fa0fc:33#0#4 | P006 | 2018, 2019, 95 | coincidental | different quantity | The item's 95% is the accuracy of ref [37] (DenseNet201 DSS with SVM), which has no row in Table I. It matched the 95% accuracy/recall of the differen… | The item's 95% is the accuracy of ref [37]'s DenseNet201+SVM DSS, which has no TABLE I row, while the matched 95% cells are the accuracies of other wo… |
| 12 | Sweep B 562fa0fc:36#0#5 | P006 | 95 | correct abstention | — | The item reports 95% accuracy on the BT dataset for ref [39] (residual network with transfer learning). Table I row [39], 'Deep residual network with … | The item's 95% is the accuracy of ref [39]'s deep residual transfer-learning model on the BT dataset, the same quantity as TABLE I row [39] Performanc… |
| 13 | Sweep B 6890f2eb:101#0#0 | P008 | 15 | coincidental | prose typed as table | The item's 15 (fetal MRI scans in the blind expert evaluation, p6) matched the 15 in the p7 Results paragraph 'Table IV shows ... for 15 test subjects… | The item's 15 (fetal MRI scans in the blind expert evaluation) matched only '15 test subjects' in the 'Table IV shows…' prose paragraph that the parse… |
| 14 | Sweep B 6890f2eb:128#0#1 | P008 | 10 | correct abstention | — | The item is Table II body text (p7, inside the table bbox), row '3D U-Net vs. Ours': p-values 10−5, 10−3, 10−10. The compared '10' is the base of thos… | The item is Table II body text, the '3D U-Net vs. Ours' p-value row (10−5, 10−3, 10−10), and its '10' token matched exactly those same Table II cells … |
| 15 | Sweep B 6890f2eb:129#0#0 | P008 | 15 | coincidental | prose typed as table | The item is the first sentence of the 'Table IV shows ...' Results paragraph (p7). Its 15 (test subjects) matched that same paragraph, which the parse… | The item is the first sentence of the 'Table IV shows… for 15 test subjects' prose paragraph, and its 15 matched that same paragraph (typed as a table… |
| 16 | Sweep B 6890f2eb:129#0#3 | P008 | 20 | coincidental | prose typed as table | The item's 20 (MAS took about 20 minutes) matched the '20 minutes' in the same 'Table IV shows ...' prose paragraph on p7, which was typed as a table.… | The item's 20 (MAS took approximately 20 minutes) matched its own 'Table IV shows…' prose paragraph, which was typed as a table; no table prints 20 (T… |
| 17 | Sweep B 6890f2eb:130#0#0 | P008 | 0.21, 0.92, 10 | correct abstention | — | The item is Table II body text, row 'PAUNet vs. Ours': Dice 10−3, 95HD 0.21, ASD 0.92. These are exactly the matched Table II p-value cells. | The item is Table II body text for 'PAUNet vs. Ours' (p = 10−3, 0.21, 0.92) and matches those same cells: Dice 10−3, 95HD 0.21, ASD 0.92. |
| 18 | Sweep B 6890f2eb:130#0#1 | P008 | 0.12, 0.70, 10 | correct abstention | — | The item is Table II body text, row 'Attention UNet vs. Ours': p = 0.12 (Dice), 0.70 (95HD), 10−3 (ASD), the same as the matched cells. | The item is Table II body text for 'Attention UNet vs. Ours' (p = 0.12, 0.70, 10−3) and matches those same cells: Dice 0.12, 95HD 0.70, ASD 10−3. |
| 19 | Sweep B 6890f2eb:131#0#0 | P008 | 0.01, 10 | correct abstention | — | The item is Table II body text, row 'SE-FCN vs. Ours': p = 10−3 (Dice), 0.01 (95HD), 10−4 (ASD), the same as the matched cells. | The item is Table II body text for 'SE-FCN vs. Ours' (p = 10−3, 0.01, 10−4) and matches those same cells: Dice 10−3, 95HD 0.01, ASD 10−4. |
| 20 | Sweep B 6890f2eb:132#0#0 | P008 | 0.02, 0.09, 10 | correct abstention | — | The item is Table II body text, row 'DSRNet vs. Ours': p = 0.02 (Dice), 0.09 (95HD), 10−3 (ASD), the same as the matched cells. The extra match to the… | The item is Table II body text for 'DSRNet vs. Ours' (p = 0.02, 0.09, 10−3) and matches those same cells, Dice 0.02 and 95HD 0.09, plus a coincidental… |
| 21 | Sweep B 6890f2eb:158#0#0 | P008 | 0.443, 0.83, 1.13, 95 | coincidental | different quantity | The item is the Figure 6 (p9) single-case label for UNet (Dice 0.83, 95HD 1.13, ASD 0.443). Only its '95', the percentile prefix of the metric name 95… | The item is a Fig. 6 overlay label for the UNet representative case (Dice 0.83, 95HD 1.13, ASD 0.443, values found in no table), and its only match is… |
| 22 | Sweep B 6890f2eb:176#0#0 | P008 | 10 | coincidental | section table or page number | The item's 10 is the page number in the running header 'ACCEPTED BY IEEE TRANSACTIONS ON MEDICAL IMAGING 10'. It matched the base 10 of the exponent-f… | The item's 10 is the page number in the page-10 running header, matched against the base '10' of Table II's p-value notation (10−5, 10−3, 10−10, …). |
| 23 | Sweep B 8edc7465:118#0#0 | P014 | 10, 29 | coincidental | different quantity | The item's 10 is the EPDS score cut-off (≥10, with 29% of SRI women above it). It matched Table 1 cells where 10 is a participant count (alcohol use, … | The item's 10 is the EPDS screening cutoff (score ≥10; the 29% proportion appears only in prose), while the matched Table 1 cells are counts (alcohol … |
| 24 | Sweep B 8edc7465:122#0#0 | P014 | 20, 40 | coincidental | different quantity | The item's 40 is the upper bound of the imaging span (40 weeks' gestation). It matched Table 1 Primigravida, SRI-exposed '25 (40)', which is 40% of mo… | The item's 40 is the upper bound of the 20–40 weeks' gestation imaging span, while the matched Table 1 cell 25 (40) is the 40% primigravida rate in th… |
| 25 | Sweep B 8edc7465:126#0#0 | P014 | 38, 40 | coincidental | section table or page number | The item's 40 is a citation number in '[38–40]'. It matched Table 1 Primigravida, SRI-exposed '25 (40)', which is 40%. | The item's 40 is a citation reference number in '[38–40]', while the matched Table 1 cell 25 (40) is the 40% primigravida rate in the SRI-exposed grou… |
| 26 | Sweep B 8edc7465:17#0#1 | P014 | 10 | coincidental | different quantity | The item's 10 is the EPDS high-symptom cut-off (≥10). It matched Table 1 counts and percentages that happen to equal 10 (alcohol use n=10, Non-Hispani… | The item's 10 is the EPDS high-symptom category cutoff (≥10), while the matched Table 1 cells are counts (alcohol use 10 (16), other/unknown race 10 (… |
| 27 | Sweep B 8edc7465:17#0#2 | P014 | 38, 40 | coincidental | section table or page number | The item's 40 is a citation number in '[38–40]'. It matched Table 1 Primigravida, SRI-exposed '25 (40)', which is 40%. | The item's 40 is a citation reference number in '[38–40]', while the matched Table 1 cell 25 (40) is the 40% primigravida rate in the SRI-exposed grou… |
| 28 | Sweep B 8edc7465:33#0#1 | P014 | 20.0, 23.57, 31.72, 32.04, 38.57, 39.71… | correct abstention | — | The item restates the Table 1 row 'GA at MRI, mean (SD) [range], week': SRI-exposed 31.72 (4.05) [20.0–38.57] and Unexposed 32.04 (4.32) [23.57–39.71]… | The item restates Table 1 row 'GA at MRI, mean (SD) [range], week': SRI-exposed 31.72 (4.05) [20.0–38.57] and unexposed 32.04 (4.32) [23.57–39.71]. |
| 29 | Sweep B 8edc7465:33#0#2 | P014 | 27, 44, 56, 67 | correct abstention | — | The item restates the Table 1 row 'Male, N (%)': SRI-exposed 27 (44) and Unexposed 67 (56). The extra 44 matches to Primigravida and Non-Hispanic Whit… | The item's male-fetus counts, 27 (44%) and 67 (56%), restate Table 1 row 'Male, N (%)': SRI-exposed 27 (44) and unexposed 67 (56). |
| 30 | Sweep B 8edc7465:33#0#3 | P014 | 0.0001, 76.58, 86.21 | correct abstention | — | The item restates the Table 1 row 'Maternal weight at MRI': SRI 86.21 kg, Unexposed 76.58 kg, P = 0.0001. | The item's maternal weight of 86.21 vs 76.58 kg with p = 0.0001 restates Table 1 row 'Maternal weight at MRI' (86.21, 76.58, P = 0.0001). |
| 31 | Sweep B 8edc7465:33#0#4 | P014 | 0.02, 16 | correct abstention | — | The item restates the Table 1 row 'Maternal alcohol use during pregnancy': SRI 10 (16), i.e. 16%, with P = 0.02. The extra 0.02 matches in Table 2 are… | The item's 16% alcohol use and p = 0.02 restate Table 1 row 'Maternal alcohol use during pregnancy, N (%)' (SRI-exposed 10 (16), P = 0.02). |
| 32 | Sweep B 8edc7465:33#0#5 | P014 | 82, 84, 90 | correct abstention | — | The item's 82% and 84% professional employment restate Table 1 'Professional': SRI 51 (82) and Unexposed 101 (84). | The item's 82% and 84% professional employment restate the Table 1 'Professional' cells, 51 (82) for SRI-exposed and 101 (84) for unexposed. |
| 33 | Sweep B 8edc7465:74#0#0 | P014 | 0.0001 | coincidental | different quantity | The item's p < 0.0001 is the significance of fetal brain measures increasing with gestational age. It matched Table 1's P value of 0.0001 for the betw… | The item's p < 0.0001 is the significance of the GA-related increase in fetal brain volume and folding, while the matched Table 1 cell 0.0001 is the P… |

- **Child records.** The 09B child outputs were deleted in the 09B scratchpad cleanup.
  - They were regenerated with the unmodified harness (`validate_09b.py children`, 64/64 return code 0) into
    `runs/p09b_run/`.
  - `.gitignore` excludes that folder (`6d53d4b`), and `git check-ignore` confirms it.
  - The unmodified harness re-analysed the regenerated records: 0 differences from the committed `run` and
    `reproduction` sections, with timing and generation timestamps excluded. The package versions are
    identical.
- **Branch.** After this commit, `exp/phase09b-fallthrough` is fast-forwarded into `claude-code-verification`.

---

## Appendix A — tables generated from `results.json`
### Pairs whose CANONICAL unit differs between any two arms

| Pair | Claim | L0 | G0 | L1 | G1 |
|---|---|---|---|---|---|
| PF001 | C005 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · RET | not_bindable · ABS table_value_unbound |
| PF002 | C005 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · RET | not_bindable · ABS table_value_unbound |
| PF004 | C012 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | bound · ABS bound_to_ablation_table | bound · ABS bound_to_ablation_table |
| PF005 | C013 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | bound · ABS bound_to_ablation_table · bound✓ | bound · ABS bound_to_ablation_table · bound✓ |
| PF006 | C013 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · RET | not_bindable · ABS table_value_unbound |
| PF007 | C021 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF008 | C021 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF009 | C021 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF010 | C021 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF011 | C025 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF013 | C026 | not_bindable · RET | not_bindable · ABS table_value_unbound | not_bindable · RET | not_bindable · ABS table_value_unbound |
| PF014 | C026 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF017 | C034 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF018 | C035 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · RET | not_bindable · ABS table_value_unbound |
| PF019 | C035 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · RET | not_bindable · ABS table_value_unbound |
| PF020 | C041 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF021 | C041 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF022 | C041 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF023 | C041 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF024 | C041 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF025 | C041 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF026 | C042 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF027 | C042 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF028 | C042 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF029 | C042 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF030 | C042 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF031 | C042 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF032 | C042 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF033 | C042 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF034 | C042 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF035 | C045 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF036 | C045 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF037 | C045 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF038 | C045 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF039 | C045 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF040 | C045 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF041 | C048 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| PF042 | C052 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF043 | C052 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF044 | C057 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF045 | C057 | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS evidence_span_not_found_in_paper_chunks | not_bindable · ABS table_value_unbound |
| PF055 | C085 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | bound · ABS binding_wrong_cell · bound✓ | bound · ABS binding_wrong_cell · bound✓ |

13 of 55 pairs are identical in all four arms.

### REAL claims whose unit differs between any two arms

| Claim | L0 | G0 | L1 | G1 |
|---|---|---|---|---|
| C005 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | wrong_cell · ABS binding_wrong_cell | wrong_cell · ABS binding_wrong_cell |
| C012 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | bound · ABS bound_to_ablation_table | bound · ABS bound_to_ablation_table |
| C013 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | bound · ABS bound_to_ablation_table · bound✓ | bound · ABS bound_to_ablation_table · bound✓ |
| C025 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS attributed_to_cited_work | not_bindable · ABS table_value_unbound |
| C034 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · RET | not_bindable · ABS table_value_unbound |
| C035 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS attributed_to_cited_work | not_bindable · ABS table_value_unbound |
| C041 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| C042 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| C045 | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| C048 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | not_bindable · ABS ownership_unverified | not_bindable · ABS table_value_unbound |
| C052 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | wrong_cell · ABS binding_wrong_cell | wrong_cell · ABS binding_wrong_cell |
| C085 | pdf_only · ABS unverifiable_binding | pdf_only · ABS unverifiable_binding | bound · ABS binding_wrong_cell · bound✓ | bound · ABS binding_wrong_cell · bound✓ |

6 of 18 claims are identical in all four arms.

### Returns removed by the guard, L0 → G0

**pairs: 1**

| # | Unit | Binder | Matched value tokens (source) | Value |
|---|---|---|---|---|
| 1 | PF013 | not_bindable | 0.96 (cell); 95 (caption) |  |

**claims: 0**

**sweep_A: 0**

**sweep_B: 32**

| # | Unit | Binder | Matched value tokens (source) | Value |
|---|---|---|---|---|
| 1 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:125#0#0 | not_bindable | 0.38 (cell); 0.41 (cell); 0.44 (cell); 0.47 (cell); 0.56 (cell); 0.59 (cell); 0.62 (cell); 01 (cell); 02 (cell) | ROUG E-L 01 BraTS 0.41 0.62 0.47 0.59 02 ISLES 0.38 0.59 0.44 0.56 |
| 2 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:147#0#0 | not_bindable | 2.1 (cell); 3.2 (cell); 4.6 (cell); 88.7 (cell) | 88.7 ± 3.2 4.6 ± 2.1 |
| 3 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:148#0#0 | not_bindable | 3.4 (cell); 4.7 (cell); 5.9 (cell); 85.4 (cell) | BraTS Tumor Core 85.4 ± 4.7 5.9 ± 3.4 |
| 4 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:150#0#0 | not_bindable | 4.2 (cell); 6.8 (cell); 7.1 (cell); 79.2 (cell) | 79.2 ± 6.8 7.1 ± 4.2 |
| 5 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:152#0#0 | not_bindable | 1.7 (cell); 2.8 (cell); 3.1 (cell); 92.3 (cell) | 92.3 ± 2.8 3.1 ± 1.7 |
| 6 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:19#0#0 | not_bindable | 02 (cell); 03 (cell) | DOI: 10.22399/ijcesen.479 Received : 02 October 2024 Accepted : 03 October 2024 |
| 7 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:37#0#0 | not_bindable | 90.1 (cell) | BraTS MRI 90.1 - |
| 8 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:41#0#0 | not_bindable | 91.5 (cell); 96.2 (cell) | BraTS, LiTS MRI, CT 91.5, 96.2 Textual |
| 9 | 562fa0fc542863477a8d86985bf4ac02654fb4f8:10#1#0 | not_bindable | 0.657 (cell) | 0.666 and 0.657, respectively. |
| 10 | 562fa0fc542863477a8d86985bf4ac02654fb4f8:33#0#4 | not_bindable | 2018 (cell); 95 (cell) | The model is trained and evaluated using BraTS 2018 and BraTS 2019 datasets and achieves a… |
| 11 | 562fa0fc542863477a8d86985bf4ac02654fb4f8:36#0#5 | not_bindable | 95 (cell) | The proposed model achieved accuracy of 95% using the BT dataset. |
| 12 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:101#0#0 | not_bindable | 15 (prose-typed-table) | For this purpose, on a set of 15 fetal MRI scans from the test set, three experts independ… |
| 13 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:128#0#1 | not_bindable | 10 (cell) | Ours 10−5 10−3 10−10 |
| 14 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:129#0#0 | not_bindable | 15 (prose-typed-table) | Table IV shows the expert evaluation results of CP segmen- tation using our method against… |
| 15 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:129#0#3 | not_bindable | 20 (prose-typed-table) | MAS, on the other hand, took approximately 20 minutes because of the need for deformable r… |
| 16 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:130#0#0 | not_bindable | 0.21 (cell); 0.92 (cell); 10 (cell) | Ours 10−3 0.21 0.92 Attention UNet vs. |
| 17 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:130#0#1 | not_bindable | 0.12 (cell); 0.70 (cell); 10 (cell) | Ours 0.12 0.70 10−3 |
| 18 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:131#0#0 | not_bindable | 0.01 (cell); 10 (cell) | Ours 10−3 0.01 10−4 |
| 19 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:132#0#0 | not_bindable | 0.02 (cell); 0.09 (cell); 10 (cell) | Ours 0.02 0.09 10−3 |
| 20 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:158#0#0 | not_a_table_claim | 95 (caption) | Dice:0.83 95HD:1.13 ASD:0.443 |
| 21 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:176#0#0 | not_bindable | 10 (cell) | ACCEPTED BY IEEE TRANSACTIONS ON MEDICAL IMAGING 10 |
| 22 | 8edc746500c5c033a80aee9b7890c8ec610e5988:118#0#0 | not_bindable | 10 (cell) | We observed an unsettling 29% of women in the SRI-treated group continued to report EPDS s… |
| 23 | 8edc746500c5c033a80aee9b7890c8ec610e5988:122#0#0 | not_bindable | 40 (cell) | Second, although GA at MRI was included as a covariate in all analyses, the span of imagin… |
| 24 | 8edc746500c5c033a80aee9b7890c8ec610e5988:126#0#0 | not_bindable | 40 (cell) | The signiﬁ- cance of maternal depressive symptoms can also vary based on assigned cut-off … |
| 25 | 8edc746500c5c033a80aee9b7890c8ec610e5988:17#0#1 | not_bindable | 10 (cell) | We assigned EPDS scores into categories of ≤4, 5–9, and ≥10 as low, moderate, and high sym… |
| 26 | 8edc746500c5c033a80aee9b7890c8ec610e5988:17#0#2 | not_bindable | 40 (cell) | These clinically relevant cutoffs are well established and commonly used in obstetric and … |
| 27 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#1 | not_bindable | 20.0 (cell); 23.57 (cell); 31.72 (cell); 32.04 (cell); 38.57 (cell); 39.71 (cell); 4.05 (cell); 4.32 (cell) | The mean (SD) [range] GA at MRI was 31.72 (4.05) [20.0-38.57] weeks for the SRI-exposed gr… |
| 28 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#2 | not_bindable | 27 (cell); 44 (cell); 56 (cell); 67 (cell) | There were 27 (44%) and 67 (56%) of women carrying male fetuses for the SRI- exposed group… |
| 29 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#3 | not_bindable | 0.0001 (cell); 76.58 (cell); 86.21 (cell) | Maternal weight at MRI was higher in the SRI group versus controls (86.21 vs 76.58 kg, p =… |
| 30 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#4 | not_bindable | 0.02 (cell); 16 (cell) | Maternal alcohol use during pregnancy was higher in the SRI versus the unexposed group (16… |
| 31 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#5 | not_bindable | 82 (cell); 84 (cell) | More than 90% and 84% of women were college graduates, and 82% and 84% reported profession… |
| 32 | 8edc746500c5c033a80aee9b7890c8ec610e5988:74#0#0 | not_bindable | 0.0001 (cell) | Fetal brain volume and cortical folding All measured fetal brain volume and cortical foldi… |

### Returns removed by the guard, L1 → G1

**pairs: 6**

| # | Unit | Binder | Matched value tokens (source) | Value |
|---|---|---|---|---|
| 1 | PF001 | not_bindable | 0.926 (cell+prose-typed-table) |  |
| 2 | PF002 | not_bindable | 0.920 (cell+prose-typed-table) |  |
| 3 | PF006 | not_bindable | 4.04 (cell) |  |
| 4 | PF013 | not_bindable | 0.96 (cell); 95 (caption) |  |
| 5 | PF018 | not_bindable | 21 (cell) |  |
| 6 | PF019 | not_bindable | 38 (cell) |  |

**claims: 1**

| # | Unit | Binder | Matched value tokens (source) | Value |
|---|---|---|---|---|
| 1 | C034 | not_bindable | 15 (cell) |  |

**sweep_A: 4**

| # | Unit | Binder | Matched value tokens (source) | Value |
|---|---|---|---|---|
| 1 | C034#0 | not_bindable | 15 (cell) | Dis-carding pathological and non-annotated brains, our training dataset results in 15 heal… |
| 2 | C047#1 | not_bindable | 0.55 (cell) | Thomas’ Hospital, London, on a Siemens FreeMax 0.55T scanner, with similar parameters as t… |
| 3 | C049#0 | not_bindable | 2024 (prose-typed-table); 4.3 (cell) | 4.3 Comparison with state-of-the-art models Table 3 compares FetalSynthSeg, FetalRealSeg a… |
| 4 | C051#0 | not_bindable | 4.2 (caption) | 4.2 Comparison with state-of-the-art We compare the performance of our proposed model with… |

**sweep_B: 109**

| # | Unit | Binder | Matched value tokens (source) | Value |
|---|---|---|---|---|
| 1 | 291198a6c58f36f37af3215a9a5270db92925bf9:115#0#0 | not_bindable | 30 (cell); 60 (cell) | For the same single segmentation task, classical approaches require from 30 minutes up to … |
| 2 | 291198a6c58f36f37af3215a9a5270db92925bf9:116#0#0 | not_bindable | 0.002 (cell); 0.003 (cell); 0.004 (cell); 0.005 (cell); 0.006 (cell); 0.01 (cell); 0.011 (cell); 0.012 (cell+prose-typed-table); 0.014 (cell+prose-typed-table); 0.02 (cell); 0.03 (cell); 0.04 (cell); 0.05 (cell); 0.07 (cell); 0.66 (cell); 0.73 (cell); 0.76 (cell); 0.79 (cell); 0.81 (cell+prose-typed-table); 0.83 (cell); 0.85 (cell); 0.87 (cell+prose-typed-table); 0.871 (cell); 0.877 (cell); 0.879 (cell); 0.88 (cell); 0.89 (cell); 0.897 (cell); 0.90 (cell); 0.902 (cell); 0.91 (cell); 0.915 (cell); 0.919 (cell); 0.92 (cell); 0.920 (cell+prose-typed-table); 0.923 (cell); 0.926 (cell+prose-typed-table); 0.93 (cell); 0.950 (cell); 0.953 (cell); 0.955 (cell); 0.957 (cell); 0.964 (cell); 0.965 (cell); 30 (cell); 60 (cell); 80 (cell) | Label Ours nnU-Net PP dHCP CSF 0.923 ± 0.006 0.897 ± 0.011 0.83 ± 0.04 0.79 ± 0.02 Grey Ma… |
| 3 | 291198a6c58f36f37af3215a9a5270db92925bf9:118#0#2 | not_bindable | 20 (prose-typed-table); 32 (prose-typed-table); 35 (prose-typed-table); 37 (prose-typed-table) | Moreover, the dataset encompasses a broader range of gestational ages, from 20 to 35 weeks… |
| 4 | 291198a6c58f36f37af3215a9a5270db92925bf9:74#0#4 | not_bindable | 20 (prose-typed-table) | The dataset is split into 140-10-20 for training, validation and test sets, respectively. |
| 5 | 291198a6c58f36f37af3215a9a5270db92925bf9:98#0#0 | not_bindable | 0.003 (cell); 0.004 (cell); 0.005 (cell); 0.006 (cell); 0.008 (prose-typed-table); 0.011 (cell); 0.012 (cell+prose-typed-table); 0.013 (prose-typed-table); 0.014 (cell+prose-typed-table); 0.020 (cell); 0.021 (cell); 0.023 (cell); 0.856 (cell); 0.866 (cell+prose-typed-table); 0.871 (cell); 0.915 (cell); 0.919 (cell) | Label Rigid VoxelMorph TransMorph CasReg CasReg-acc CSF 0.516 ± 0.008 0.802 ± 0.007 0.796 … |
| 6 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:125#0#0 | not_bindable | 0.38 (cell); 0.41 (cell); 0.44 (cell); 0.47 (cell); 0.56 (cell); 0.59 (cell); 0.62 (cell); 01 (cell); 02 (cell) | ROUG E-L 01 BraTS 0.41 0.62 0.47 0.59 02 ISLES 0.38 0.59 0.44 0.56 |
| 7 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:147#0#0 | not_bindable | 2.1 (cell); 3.2 (cell); 4.6 (cell); 88.7 (cell) | 88.7 ± 3.2 4.6 ± 2.1 |
| 8 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:148#0#0 | not_bindable | 3.4 (cell); 4.7 (cell); 5.9 (cell); 85.4 (cell) | BraTS Tumor Core 85.4 ± 4.7 5.9 ± 3.4 |
| 9 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:150#0#0 | not_bindable | 4.2 (cell); 6.8 (cell); 7.1 (cell); 79.2 (cell) | 79.2 ± 6.8 7.1 ± 4.2 |
| 10 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:152#0#0 | not_bindable | 1.7 (cell); 2.8 (cell); 3.1 (cell); 92.3 (cell) | 92.3 ± 2.8 3.1 ± 1.7 |
| 11 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:19#0#0 | not_bindable | 02 (cell); 03 (cell) | DOI: 10.22399/ijcesen.479 Received : 02 October 2024 Accepted : 03 October 2024 |
| 12 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:37#0#0 | not_bindable | 90.1 (cell) | BraTS MRI 90.1 - |
| 13 | 380729d6b9650ea4b8cb7e4325606e30cdd3b727:41#0#0 | not_bindable | 91.5 (cell); 96.2 (cell) | BraTS, LiTS MRI, CT 91.5, 96.2 Textual |
| 14 | 3c9b838a0b36d032a86ffe582f55b3583fd4a815:100#0#0 | not_bindable | 2.61 (cell); 3.10 (cell); 5.09 (cell); 89.76 (cell) | Grad-CAM (baseline) 78.69±10.02 22.17±16.60 UM-CAM 85.22±6.62 5.26±4.23 SPL 89.05±4.30 3.8… |
| 15 | 3c9b838a0b36d032a86ffe582f55b3583fd4a815:107#0#0 | not_bindable | 0.05 (caption) | * denotes p-value < 0.05 when comparing with the second place weakly supervised method. |
| 16 | 3c9b838a0b36d032a86ffe582f55b3583fd4a815:112#0#0 | not_bindable | 0.40 (cell); 0.65 (cell); 1.10 (cell); 1.22 (cell); 2.67 (cell); 3.17 (cell); 95.98 (cell); 96.51 (cell) | FullySup 95.98±3.17 1.22±0.65 96.51±2.67 1.10±0.40 |
| 17 | 3c9b838a0b36d032a86ffe582f55b3583fd4a815:95#0#0 | not_bindable | 0.05 (caption) | * denotes p-value < 0.05 when comparing with the second place method. |
| 18 | 3c9b838a0b36d032a86ffe582f55b3583fd4a815:97#0#0 | not_bindable | 39.88 (cell) | Grad-CAM (baseline) 74.48±13.26 39.88±14.66 Average-CAM 77.40±13.28 38.70±19.75 UM-CAM 79.… |
| 19 | 562fa0fc542863477a8d86985bf4ac02654fb4f8:10#1#0 | not_bindable | 0.657 (cell) | 0.666 and 0.657, respectively. |
| 20 | 562fa0fc542863477a8d86985bf4ac02654fb4f8:33#0#4 | not_bindable | 2018 (cell); 95 (cell) | The model is trained and evaluated using BraTS 2018 and BraTS 2019 datasets and achieves a… |
| 21 | 562fa0fc542863477a8d86985bf4ac02654fb4f8:36#0#5 | not_bindable | 95 (cell) | The proposed model achieved accuracy of 95% using the BT dataset. |
| 22 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:120#0#2 | not_bindable | 10 (cell) | Consistent with the overall analysis, a statistically significant difference is observed o… |
| 23 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:120#0#5 | not_bindable | 0.85 (cell); 0.99 (cell) | Correlation values are consistently high (R = 0.85–0.99), indicating a strong to very stro… |
| 24 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:124#0#0 | not_bindable | 2.56 (cell); 3.08 (cell); 4.04 (cell); 4.26 (cell) | LCC 4.04 ± 3.08 4.26 ± 2.56 |
| 25 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:125#0#0 | not_bindable | 1.44 (cell); 1.67 (cell); 2.44 (cell); 2.68 (cell) | HV 2.68 ± 1.44 2.44 ± 1.67 |
| 26 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:126#0#0 | not_bindable | 3.07 (cell); 3.69 (cell); 4.89 (cell); 6.00 (cell) | bBIP 6.00 ± 3.69 4.89 ± 3.07 |
| 27 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:127#0#0 | not_bindable | 1.89 (cell); 3.07 (cell); 4.62 (cell); 5.42 (cell) | sBIP 5.42 ± 3.07 4.62 ± 1.89 |
| 28 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:128#0#0 | not_bindable | 0.93 (cell); 1.47 (cell); 2.43 (cell); 2.53 (cell) | TCD 2.53 ± 1.47 2.43 ± 0.93 |
| 29 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:129#0#1 | not_bindable | 0.143 (prose-typed-table); 0.243 (prose-typed-table); 0.263 (prose-typed-table); 0.279 (prose-typed-table); 0.3028 (prose-typed-table); 0.5935 (prose-typed-table) | Paired Wilcoxon signed-rank tests show no significant differences for HV (p = 0.5935), bBI… |
| 30 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:129#0#2 | not_bindable | 0.0001 (prose-typed-table); 0.0007 (prose-typed-table); 0.821 (prose-typed-table); 0.843 (prose-typed-table) | Significant differences are observed for LCC (p = 0.0007), where the competitor method dem… |
| 31 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:135#0#0 | not_bindable | 0.85 (cell); 0.92 (cell); 0.98 (cell); 0.99 (cell) | Pearson R 0.85 / 0.92 0.94 / 0.92 0.98 / 0.98 0.99 / 0.99 0.96 / 0.99 |
| 32 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:214#0#0 | not_bindable | 19 (prose-typed-table) | Mapping of the 19 tissue labels produced by BOUNTI to the 8-tissue label maps used as inpu… |
| 33 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:89#0#0 | not_bindable | 10 (cell) | The two datasets are combined into a single collection, which is split into train, validat… |
| 34 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:90#0#0 | not_bindable | 10 (cell) | Training uses Adam optimizer with randomly initialized weights and a learning rate of 5e-5… |
| 35 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:90#0#1 | not_bindable | 10 (cell) | No cross-validation is applied but we consider 10% of the samples for validation during hy… |
| 36 | 67d7236f524dae3bcf88b8f2726261d1acb5206b:90#0#2 | not_bindable | 10 (cell) | The model is trained with a batch size of 16 for up to 300 epochs, with an early stopping … |
| 37 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:101#0#0 | not_bindable | 15 (prose-typed-table) | For this purpose, on a set of 15 fetal MRI scans from the test set, three experts independ… |
| 38 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:112#0#2 | not_bindable | 0.05 (cell) | In our paired t-tests, the signiﬁcance level was set as 0.05. |
| 39 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:128#0#1 | not_bindable | 10 (cell) | Ours 10−5 10−3 10−10 |
| 40 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:129#0#0 | not_bindable | 15 (prose-typed-table) | Table IV shows the expert evaluation results of CP segmen- tation using our method against… |
| 41 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:129#0#3 | not_bindable | 20 (prose-typed-table) | MAS, on the other hand, took approximately 20 minutes because of the need for deformable r… |
| 42 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:130#0#0 | not_bindable | 0.21 (cell); 0.92 (cell); 10 (cell) | Ours 10−3 0.21 0.92 Attention UNet vs. |
| 43 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:130#0#1 | not_bindable | 0.12 (cell); 0.70 (cell); 10 (cell) | Ours 0.12 0.70 10−3 |
| 44 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:131#0#0 | not_bindable | 0.01 (cell); 10 (cell) | Ours 10−3 0.01 10−4 |
| 45 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:132#0#0 | not_bindable | 0.02 (cell); 0.09 (cell); 10 (cell) | Ours 0.02 0.09 10−3 |
| 46 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:158#0#0 | not_a_table_claim | 95 (caption) | Dice:0.83 95HD:1.13 ASD:0.443 |
| 47 | 6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:176#0#0 | not_bindable | 10 (cell) | ACCEPTED BY IEEE TRANSACTIONS ON MEDICAL IMAGING 10 |
| 48 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:24#0#0 | not_bindable | 0.5 (cell); 1.5 (cell); 15 (cell); 22.6 (cell); 33.4 (cell) | TRAINING 1.5T; 3T General Electric 0.5x0.5x0.5 15 [22.6 - 33.4] |
| 49 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:29#0#0 | not_bindable | 0.8 (cell); 1.5 (cell); 18 (cell); 21 (cell); 38 (cell) | Quantitative 1.5T; 3T Siemens; Philips 0.8x0.8x0.8 18 21-38 Gholipour et. |
| 50 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:37#0#0 | not_bindable | 0.5 (cell); 14 (cell) | adopted the following optimization strategy: 1) our baseline model was trained over 23 epo… |
| 51 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:57#0#0 | not_bindable | 26 (cell) | In order to better represent the diversity of the cortical vari- ability and to prove the … |
| 52 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:71#0#0 | not_bindable | 21 (cell); 38 (cell) | 3: Evolution of the performance metrics for atlas images from 21 to 38 weeks of gestation. |
| 53 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:9#0#0 | not_bindable | 18 (cell); 21 (cell); 38 (cell) | We quantitatively evaluate our method on 18 fetal brain atlases ranging from 21 to 38 week… |
| 54 | 86359e887f98737c2ccdb5c0b25840cdb3edb719:9#0#1 | not_bindable | 26 (cell) | Furthermore, qualitative evaluation by three different experts on 130 randomly selected sl… |
| 55 | 8edc746500c5c033a80aee9b7890c8ec610e5988:118#0#0 | not_bindable | 10 (cell) | We observed an unsettling 29% of women in the SRI-treated group continued to report EPDS s… |
| 56 | 8edc746500c5c033a80aee9b7890c8ec610e5988:122#0#0 | not_bindable | 40 (cell) | Second, although GA at MRI was included as a covariate in all analyses, the span of imagin… |
| 57 | 8edc746500c5c033a80aee9b7890c8ec610e5988:126#0#0 | not_bindable | 40 (cell) | The signiﬁ- cance of maternal depressive symptoms can also vary based on assigned cut-off … |
| 58 | 8edc746500c5c033a80aee9b7890c8ec610e5988:17#0#1 | not_bindable | 10 (cell) | We assigned EPDS scores into categories of ≤4, 5–9, and ≥10 as low, moderate, and high sym… |
| 59 | 8edc746500c5c033a80aee9b7890c8ec610e5988:17#0#2 | not_bindable | 40 (cell) | These clinically relevant cutoffs are well established and commonly used in obstetric and … |
| 60 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#1 | not_bindable | 20.0 (cell); 23.57 (cell); 31.72 (cell); 32.04 (cell); 38.57 (cell); 39.71 (cell); 4.05 (cell); 4.32 (cell) | The mean (SD) [range] GA at MRI was 31.72 (4.05) [20.0-38.57] weeks for the SRI-exposed gr… |
| 61 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#2 | not_bindable | 27 (cell); 44 (cell); 56 (cell); 67 (cell) | There were 27 (44%) and 67 (56%) of women carrying male fetuses for the SRI- exposed group… |
| 62 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#3 | not_bindable | 0.0001 (cell); 76.58 (cell); 86.21 (cell) | Maternal weight at MRI was higher in the SRI group versus controls (86.21 vs 76.58 kg, p =… |
| 63 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#4 | not_bindable | 0.02 (cell); 16 (cell) | Maternal alcohol use during pregnancy was higher in the SRI versus the unexposed group (16… |
| 64 | 8edc746500c5c033a80aee9b7890c8ec610e5988:33#0#5 | not_bindable | 82 (cell); 84 (cell) | More than 90% and 84% of women were college graduates, and 82% and 84% reported profession… |
| 65 | 8edc746500c5c033a80aee9b7890c8ec610e5988:74#0#0 | not_bindable | 0.0001 (cell) | Fetal brain volume and cortical folding All measured fetal brain volume and cortical foldi… |
| 66 | 902ac09c780901e1645101f2b5b817093381dcc8:136#0#0 | not_bindable | 4.3 (cell) | ure mode analysis (4.3). |
| 67 | 902ac09c780901e1645101f2b5b817093381dcc8:136#0#1 | not_bindable | 2024 (prose-typed-table) | We retrain FetalSynthSeg, FetalRealSeg and RealSynthHybrid on the full FeTA 2024 training … |
| 68 | 902ac09c780901e1645101f2b5b817093381dcc8:140#0#0 | not_bindable | 0.55 (cell); 1.5 (cell); 2024 (prose-typed-table) | All models are evaluated on 348 subjects from the dHCP dataset and a subset of FeTA 2024 t… |
| 69 | 902ac09c780901e1645101f2b5b817093381dcc8:140#0#1 | not_bindable | 2024 (prose-typed-table) | We use the default implementations and publicly available weights for the FeTA 2024 challe… |
| 70 | 902ac09c780901e1645101f2b5b817093381dcc8:140#0#2 | not_bindable | 2024 (prose-typed-table) | For BOUNTI, we use the publicly available Docker image 3 with weights trained on a larger … |
| 71 | 902ac09c780901e1645101f2b5b817093381dcc8:17#0#0 | not_bindable | 2024 (prose-typed-table) | Contributions This work extends our MICCAI 2024 pub- lication (Zalevskyi et al., 2024) by … |
| 72 | 902ac09c780901e1645101f2b5b817093381dcc8:173#0#0 | not_bindable | 0.05 (caption) | Results with p < 0.05 are considered statistically significant. |
| 73 | 902ac09c780901e1645101f2b5b817093381dcc8:189#0#0 | not_bindable | 2024 (prose-typed-table) | Table 3 compares FetalSynthSeg, FetalRealSeg and RealSynthHybrid (trained on the full FeTA… |
| 74 | 902ac09c780901e1645101f2b5b817093381dcc8:221#0#2 | not_bindable | 2024 (prose-typed-table) | Notably, both FetalSynthSeg and the FeTA 2024 model outper- form BOUNTI in this regime. |
| 75 | 902ac09c780901e1645101f2b5b817093381dcc8:231#0#1 | not_bindable | 2024 (prose-typed-table) | All methods except for BOUNTI trained on the FeTA 2024 training data. |
| 76 | 902ac09c780901e1645101f2b5b817093381dcc8:452#0#0 | not_bindable | 0.1 (prose-typed-table); 1.5 (cell) | We re-trained the models using the following augmentations, each applied with a random pro… |
| 77 | 902ac09c780901e1645101f2b5b817093381dcc8:472#0#1 | not_bindable | 68.3 (cell); 72.2 (cell) | Table S2 shows that although this model achieves slightly lower results than FetalSynthSeg… |
| 78 | 902ac09c780901e1645101f2b5b817093381dcc8:6#0#0 | not_bindable | 0.55 (cell); 2024 (prose-typed-table) | Evaluated on 348 fetal subjects from four sites spanning 0.55–3T and both T1w and T2w cont… |
| 79 | 902ac09c780901e1645101f2b5b817093381dcc8:6#0#1 | not_bindable | 2024 (prose-typed-table) | Compared with state-of-the-art methods such as BOUNTI, nnU-Net ensemble, and the FeTA 2024… |
| 80 | 902ac09c780901e1645101f2b5b817093381dcc8:91#0#0 | not_bindable | 2024 (prose-typed-table) | We use subsets of both train- ing and testing datasets employed in the FeTA 2024 Chal- |
| 81 | 902ac09c780901e1645101f2b5b817093381dcc8:94#0#1 | not_bindable | 0.55 (cell) | Thomas’ Hospital, London, on a Siemens FreeMax 0.55T scanner, with similar parameters as t… |
| 82 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:138#0#0 | not_bindable | 2021 (cell) | This study employs the Fetal Tissue Annotation (FeTA) 2021 dataset, a publicly available, … |
| 83 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:148#0#0 | not_bindable | 2021 (cell) | FeTA 2021 was selected due to its combination of anatomical diversity and rich expert anno… |
| 84 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:22#0#0 | not_bindable | 2021 (cell) | Trained and validated on the FeTA 2021 dataset using 5-fold cross-validation, the proposed… |
| 85 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:517#0#0 | not_bindable | 4.2 (caption) | Table 4.2: Performance comparison of the proposed model with state-of-the-art methods. |
| 86 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:572#0#0 | not_bindable | 2021 (cell) | Proposed Model FetA 2021 T2w MRI |
| 87 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:589#0#0 | not_bindable | 4.3 (caption) | The quantitative comparison is summarized in Table 4.3. |
| 88 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:591#0#0 | not_bindable | 21.87 (cell) | Specifically, the proposed model contains 21.87 million |
| 89 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:596#0#0 | not_bindable | 4.3 (caption) | Table 4.3: Computational complexity comparison of the proposed model with baseline archite… |
| 90 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:606#0#0 | not_bindable | 0.0211 (cell); 2.03 (cell); 21.87 (cell) | Proposed Model 21.87 2.03 0.0211 |
| 91 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:616#0#0 | not_bindable | 4.4 (caption) | 4.4 Ablation and Sensitivity Analysis |
| 92 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:650#0#0 | not_bindable | 4.5 (caption) | The quantitative results are presented in Table 4.5. |
| 93 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:651#0#0 | not_bindable | 4.5 (caption) | Table 4.5: Contrast-stratified performance across models. |
| 94 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:678#0#0 | not_bindable | 4.6 (caption) | quantitative results are presented in Table 4.6. |
| 95 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:679#0#0 | not_bindable | 4.6 (caption) | Table 4.6: Contrast-stratified performance across models. |
| 96 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:683#0#0 | not_bindable | 14.00 (cell); 80.05 (cell); 94.05 (cell) | ResNet34-UNet 94.05 80.05 14.00 |
| 97 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:684#0#0 | not_bindable | 17.66 (cell); 75.52 (cell); 93.18 (cell) | ResNet34-Unet++ 93.18 75.52 17.66 |
| 98 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:685#0#0 | not_bindable | 13.32 (cell); 79.09 (cell); 93.41 (cell) | ResNet34-DeepLabV3 93.41 79.09 13.32 |
| 99 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:686#0#0 | not_bindable | 14.40 (cell); 79.93 (cell); 94.33 (cell) | ResNet34-DeepLabV3++ 94.33 79.93 14.40 |
| 100 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:687#0#0 | not_bindable | 12.68 (cell); 83.99 (cell); 96.67 (cell) | Proposed Model 96.67 83.99 12.68 |
| 101 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:691#0#0 | not_bindable | 12.68 (cell) | (12.68%) relative to the baseline decoders. |
| 102 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:692#0#0 | not_bindable | 17.66 (cell) | to 17.66%, with UNet++ showing the largest degradation. |
| 103 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:703#0#0 | not_bindable | 4.5 (caption) | The resulting performance metrics are summarized in Table 4.5. |
| 104 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:760#0#0 | not_bindable | 2021 (cell) | was evaluated on the FeTA 2021 dataset using five-fold cross-validation and consistently o… |
| 105 | a363d05b9e3fefe1c99929d3b867d9cc7c33d7ec:767#0#0 | not_bindable | 2021 (cell) | distribution of the FeTA 2021 dataset, the proposed approach provides a robust and scalabl… |
| 106 | aa901a8a5bd2fac9b54e7a8ded5b1289c4e337dc:116#0#0 | not_bindable | 23 (prose-typed-table) | To verify the difficulty of labeling these smaller tissue structures, we asked four clinic… |
| 107 | aa901a8a5bd2fac9b54e7a8ded5b1289c4e337dc:116#0#4 | not_a_table_claim | 60 (prose-typed-table) | Clearly, all four experts struggled to produce labels consistent with the ground truth, wi… |
| 108 | aa901a8a5bd2fac9b54e7a8ded5b1289c4e337dc:97#0#3 | not_a_table_claim | 49.3 (prose-typed-table); 60 (prose-typed-table) | The DSC scores for the DHCP and CRL datasets increased to 60% and 49.3%, respectively. |
| 109 | aa901a8a5bd2fac9b54e7a8ded5b1289c4e337dc:97#0#4 | not_bindable | 4.0 (prose-typed-table) | The overall average HD95 was reduced to <4.0 mm. |

### Sweep A items newly RETURNED in G1 vs L0

- C036#0: pdf_only / unverifiable_binding → RETURNED / not_bindable — Method DSC↑ ASD (mm)↓ HD95 (mm)↓ Betti Error↓ Baseline U-Net 0.54±0.16 <2e-16 2.51±2.34 <2e-16 7.32±6.57 <2e-16 0.74±1.3 0.023 TopoCP 0.70±0…
- C047#0: pdf_only / unverifiable_binding → RETURNED / not_bindable — Evaluating Synthetic Data Generation for Domain Generalization in Fetal Brain MRI Segmentation Prospective multi-echo KCL dataset Data were …

### Versions

```
{
 "identity (.venv)": {
  "python": "3.10.18",
  "pymupdf": "1.28.2",
  "pyyaml": "6.0.3",
  "tqdm": "4.70.0"
 },
 "run L1/G1 (.venv-09a)": {
  "python": "3.13.6",
  "pymupdf": "1.28.2",
  "pyyaml": "6.0.3",
  "tqdm": "4.70.0",
  "docling": "2.117.0",
  "docling-core": "2.99.0",
  "docling-ibm-models": "3.15.0",
  "docling-parse": "7.22.1",
  "transformers": "5.17.0",
  "timm": "1.0.30",
  "torch": "2.14.0",
  "torchvision": "0.29.0"
 },
 "run L0/G0 (.venv-09a)": {
  "python": "3.13.6",
  "pymupdf": "1.28.2",
  "pyyaml": "6.0.3",
  "tqdm": "4.70.0"
 }
}
```

### Timing

```
{
 "child_wall_seconds_total": {
  "L0": 17.4,
  "G0": 17.0,
  "L1": 506.9,
  "G1": 460.7
 },
 "per_parser_summary": {
  "L1": {
   "A": {
    "pages": 49,
    "min": 1.22,
    "max": 44.21,
    "total": 388.5
   },
   "B": {
    "pages": 49,
    "min": 0.28,
    "max": 5.52,
    "total": 75.4
   }
  },
  "G1": {
   "A": {
    "pages": 49,
    "min": 1.27,
    "max": 17.83,
    "total": 346.6
   },
   "B": {
    "pages": 49,
    "min": 0.3,
    "max": 4.2,
    "total": 72.1
   }
  }
 },
 "invocations": [
  {
   "started_utc": "2026-10-01T01:06:38+00:00",
   "arms": [
    "L0",
    "G0",
    "L1"
   ],
   "reused_outputs": [
    "P001:L0",
    "P003:L0",
    "P004:L0",
    "P006:L0",
    "P007:L0",
    "P008:L0",
    "P011:L0",
    "P014:L0",
    "P015:L0",
    "P016:L0",
    "P017:L0",
    "P019:L0",
    "P020:L0",
    "P024:L0",
    "P027:L0",
    "P030:L0",
    "P001:G0",
    "P003:G0",
    "P004:G0",
    "P006:G0",
    "P007:G0",
    "P008:G0",
    "P011:G0",
    "P014:G0",
    "P015:G0",
    "P016:G0",
    "P017:G0",
    "P019:G0",
    "P020:G0",
    "P024:G0",
    "P027:G0",
    "P030:G0",
    "P001:L1",
    "P003:L1",
    "P004:L1",
    "P006:L1",
    "P007:L1",
    "P008:L1",
    "P011:L1",
    "P014:L1",
    "P015:L1",
    "P016:L1",
    "P017:L1",
    "P019:L1",
    "P020:L1",
    "P024:L1",
    "P027:L1",
    "P030:L1"
   ]
  },
  {
   "started_utc": "2026-10-01T01:06:42+00:00",
   "arms": [
    "G1"
   ],
   "reused_outputs": [
    "P001:G1",
    "P003:G1",
    "P004:G1",
    "P006:G1",
    "P007:G1",
    "P008:G1",
    "P011:G1",
    "P014:G1",
    "P015:G1",
    "P016:G1",
    "P017:G1",
    "P019:G1",
    "P020:G1",
    "P024:G1",
    "P027:G1"
   ]
  }
 ]
}
```