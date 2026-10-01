# PHASE 09B — Pre-registration (committed before any run)

Branch `exp/phase09b-fallthrough`, created from **`864f2e8`** (`exp/phase09a-borderless`, pushed), as the brief
says. The later docs-only commit `92c85e3` (it records `864f2e8`'s hash in the 09A progress docs) is not an
ancestor of this branch. `src/`, `tests/` and `configs/` are identical in both. **Baseline = `864f2e8`.**

## A. Brief (verbatim)

> Evidence motivating this phase (09A, results.json):
> - P3 FAIL: 6 regressions PF001, PF002, PF006, PF017, PF018, PF019. With borderless on, these pairs went
>   pdf_only/ABSTAINED -> not_bindable -> grounding -> RETURNED without a verified bind (gate.py:544 fall-through).
> - The oracle ceiling for the 11 target claims is 2 (C013, C085). P1 (>= 3) was unreachable by construction,
>   so the enable criteria are re-specified below as a NEW pre-registration, disclosed as motivated by 09A.
>
> - New flag fallthrough_policy = legacy | table_value_guard, DEFAULT legacy, resolved exactly like
>   disambiguation_policy / borderless_policy (env RGPT_FALLTHROUGH_POLICY, then configs/staging_config.yaml,
>   then legacy). With legacy, gate output must be byte-identical to 864f2e8 (verify).
>
> THE GUARD (table_value_guard) — one general rule, no claim- or paper-specific logic
> At the fall-through point (gate.py ~544), when the binder status is not_bindable or not_a_table_claim
> AND the paper has attached table cells:
>   if the claim's numeric value occurs in the paper's tables, ABSTAIN with reason `table_value_unbound`;
>   otherwise keep the existing fall-through (prose grounding) unchanged.
> "Occurs in the paper's tables" = the normalized numeric token (reuse borderless.py's G1 normalization:
> U+2212 minus, ±, thin/nbsp spaces, markup, trailing */† markers) equals a numeric token in
> (i) any attached table cell value of that paper, or (ii) the text of any table block of that paper
> (caption + body, including tables still pdf_only).
> Token equality, not substring ("15" must not match "0.15", "150" or "15.2").
> Rationale string in code: a value that lives in a table must be verified by binding to that table;
> only values absent from every table may be grounded in prose.
>
> STEP 2 — IDENTITY: production venv, fallthrough_policy=legacy + borderless_policy=off vs 864f2e8:
>   30/30 PDFs gate records identical; 55-pair evaluation 0 differences.
>
> STEP 3 — 2x2 RUN on the same 16 papers and 55 pairs:
>   L0 = legacy + off (baseline)     L1 = legacy + consensus (= 09A)
>   G0 = guard + off                 G1 = guard + consensus
>   For every arm: per-pair binder status, gate final, bound_correct, returned; per-claim transitions vs L0.
>   Also gate ALL claims in the 16 papers (not just the 55 pairs) and report, per arm: RETURNED total,
>   RETURNED with verified bind, RETURNED without bind, and list every claim whose status changes vs L0
>   (claim id, value, before -> after, reason). This is the recall cost of the guard.
>   Check L1 reproduces 09A's validation numbers exactly; if not, STOP and report.
>
> PASS CRITERIA
> Guard (G0 vs L0, and G1 vs L1):
>   Q1 all 6 09A regressions (PF001, PF002, PF006, PF017, PF018, PF019) are ABSTAINED in G1.
>   Q2 zero pairs/claims that are RETURNED with a verified bind in L0 (or L1) lose that status.
>   Q3 zero new RETURNED-without-bind in G0 vs L0 and in G1 vs L1.
>   (Returns removed by the guard are reported with counts and every item listed; not a fail criterion.)
> Borderless enable (G1 vs L0) — new, re-specified:
>   E1 both oracle-bindable claims C013 and C085 bind to their gold cell.
>   E2 NEG unchanged from 09A: P019 T1/T2 accepted with 48/48 correct cells; P027 T1, P020 T III, P024 T2 rejected.
>   E3 zero pairs go from ABSTAINED in L0 to RETURNED without a verified bind in G1.
>   E4 zero accepted cells absent from the text layer.
>   E5 zero verified binds lost vs L0.
>
> STEP 4 — DECISION (apply mechanically, separate commits)
>   Q1–Q3 all PASS -> commit "enable fallthrough_policy=table_value_guard by default".
>   Q1–Q3 PASS and E1–E5 all PASS -> additional commit "enable borderless_policy=consensus by default".
>   Any Q fails -> both defaults stay as they are; report which item broke it.
>   Q pass, any E fails -> enable only the guard; borderless stays off; report which E failed.

## B. Disclosure: the enable criteria were re-specified after 09A

09A's P1 (≥ 3 of the 11 target claims bound, from ≥ 2 papers) could not pass. The 09A oracle measured the
ceiling at **2** (C013, C085): even with perfect cells, only 2 target claims bind. E1–E5 replace P1–P4 for
the borderless decision. They were written after 09A's results were known, and 09A's results motivated
them. E1 asks for exactly the measured ceiling, so it is not an independent test of the backend's gain. E2
and E4 restate 09A's P2 and P4. E3 and E5 restate P3, scoped to returns without a verified bind and to
lost binds.

## C. Operational definitions (fixed now; any later change is reported as a deviation)

**D1 Flag.** `_fallthrough_policy()` in `gate.py`, read at every call, resolved in this order:
- the environment variable `RGPT_FALLTHROUGH_POLICY`, if it is `legacy` or `table_value_guard`;
- otherwise the `fallthrough_policy:` line of `configs/staging_config.yaml` (value before `#`, stripped,
  lowercased), if valid;
- otherwise `legacy`.

This is the code shape of `represent._borderless_policy()` (`src/evidence/represent.py:413-430`).

**D2 Where the guard runs.** In `_gate_value`, at the fall-through after the binder verdict
(`gate.py:544-547`), inside the numeric branch. It runs iff the policy is `table_value_guard` and the
`structural_bind` status is `not_bindable` or `not_a_table_claim`. Both statuses exist only when the paper
has at least one attached cell: `structural_bind` returns `pdf_only` otherwise (`gate.py:432-434`). So the
brief's "AND the paper has attached table cells" holds by construction. Statuses `pdf_only`, `wrong_cell`
and `bound` are untouched. Items without a numeric anchor never reach the binder (`gate.py:525`) and are
untouched.

**D3 Numeric tokens `tok(text)`.**
1. Split the text on whitespace (`str.split()`, which includes nbsp and thin spaces).
2. Apply `borderless.norm` to each word. This is the G1 normalisation (PREREG_09A O7): U+2212 → `-`,
   `**` and `__` removed, trailing `*†‡§¶` stripped, all whitespace including U+200B removed, casefold.
   It is applied per word because `norm` deletes whitespace, which would fuse neighbouring numbers.
3. A token is a match of `(?<![\w.])(?:\d+(?:\.\d+)?|\.\d+)(?!\d|\.\d)` in the normalised word.

Consequences, fixed now:
- **Whole tokens.** "15" is not a token of "0.15", "150" or "15.2".
- **Unsigned.** `-`, U+2212, `±`, `%`, brackets, `/` and `,` separate tokens: "0.87±0.06" gives {0.87,
  0.06} and "−0.12" gives {0.12}. This matches the binder's value test (`gate.py:459-465`) and the anchor
  rule (`anchors.py:27`), which are both sign-blind.
- **Not glued to an identifier.** No token is read after a letter, digit, `_` or `.`: "BraTS2020",
  "ResNet50", "T1" and "v1.2" give none. A letter after the number is a unit: "15kg" gives 15 and "1.5M"
  gives 1.5.
- **Known limit.** A comma separates, so "1,500" gives {1, 500}.

Equality is string equality of tokens.

**D4 Claim values `C(v)`.** The tokens of the gated value `v` (one gated sentence) that have the binder's
anchor shape (`anchors.py:27`): the token contains `.`, or has ≥ 2 digits.

**D5 Table values `T(paper)`.** The union of `tok` over two sources:
- (i) the value of every attached cell (`paper_table_cells(chunks)`, the binder's own cell set);
- (ii) the text of every chunk with `block_type == "table"`.

Representation note (FACT, `src/evidence/represent.py:193-195`): in the PDF representation a table block
is the caption block, and the table body stays in ordinary text blocks. The exception is body text that
PyMuPDF put in the caption's own block. So (ii) sees the caption text, and any body text in the same block,
of every table, including pdf_only tables. It does not see body text in other blocks. The brief's
"caption + body" is operationalised as the table block's text. This gap is reported, not filled.

**D6 Rule.** If `C(v) ∩ T(paper) ≠ ∅` (any of the claim's values), the item is abstained with
`evidence_status=UNSUPPORTED`, `final=ABSTAINED`, `abstain_reason="table_value_unbound"`. No new item field
is added. Otherwise the legacy fall-through runs unchanged. "Any" is used because a claim that carries a
table value the binder did not verify is unverified, whatever its other numbers. Binder case 5b
(`gate.py:480-488`) already rejects a claim when any of its numbers sits in some other cell.

**D7 Identity (STEP 2).**
- Production `.venv`, `RGPT_FALLTHROUGH_POLICY=legacy`, `RGPT_BORDERLESS_POLICY=off`.
- Old gate: `864f2e8:src/evidence/gate.py` via `git show`, executed in memory as package `src.evidence`.
- **Gate records.** For each of the 30 PDFs in `pdf_identity_manifest_v2.csv` (hash checked), the chunks
  come from `process_paper_grounded`. The records are the `gate_paper` output for two inputs:
  - (a) every harvested candidate claim of that paper (`postfix_candidates.json`), as a `results` string,
    the way `run_case` passes it;
  - (b) the text of every chunk, as a `results` string.

  Serialised with `json.dumps(sort_keys=True)`, they must be identical old vs new on 30/30 PDFs.
- **55 pairs.** `postfix_evaluate.evaluate` runs on the flag-off chunks twice: once with the evaluator's
  gate module (`PE.G`, `O.G`) set to the old gate, once to the new. The full results must be identical
  (0 pair and 0 claim differences).

**D8 Arms and runs (STEP 3).**
- Arms:
  - L0 = legacy + off;
  - L1 = legacy + consensus;
  - G0 = table_value_guard + off;
  - G1 = table_value_guard + consensus.
- Papers: 09A's 16 (the 12 gold papers plus NEG P019, P020, P024, P027).
- Environment: `.venv-09a`, CPU only (`CUDA_VISIBLE_DEVICES=""`).
- **One child process per paper per arm** (16 × 4 = 64). Each child gets both variables of its arm, and is
  09A's child: `process_paper_grounded` with the `build_document` capture, and the same output keys.
- Order: all L0, all G0, all L1, then the reproduction check (D11), then all G1.
- A child output already in the work directory is reused. Such a resume after an interruption is recorded.
- Before the long run, the harness prints a one-line reminder that the laptop must stay plugged in and
  awake.
- Recorded:
  - child wall seconds per paper and arm;
  - per-parser seconds per page (A Docling, B TATR) for L1 and G1;
  - whether L0 = G0 and L1 = G1 records. The children do not gate, so this is a representation-independence
    and determinism check.

**D9 Gating per arm.** All gating runs in the parent, with `RGPT_FALLTHROUGH_POLICY` set to the arm's
policy, on that arm's child records.
- **55 pairs / 18 claims.** The unchanged phase 08 evaluator `postfix_evaluate.evaluate`, with before =
  after = the arm's records; the arm's values are the `after` side.
  - Units: CANONICAL per pair (55) and REAL per claim (18).
  - Recorded per unit: binder status, gate finals and reasons, `bound_correct`, `returned`.
- **Sweep A ("ALL claims").** Every harvested candidate claim in `postfix_candidates.json` whose paper is
  one of the 16: **48 claims**.
  - Per paper: P001 6, P003 3, P004 2, P006 6, P007 1, P008 2, P011 4, P014 7, P015 4, P016 3, P017 5,
    P024 1, P030 4. P019, P020 and P027 have none.
  - Each claim runs through the Stage B oracle's `run_case` (`gate_paper` on the claim text as a
    `results` string).
  - Unit: a gate item (one per gated sentence), id = (claim id, item index). Item values must be equal
    across arms; otherwise that claim is UNMEASURED.
- **Sweep B (supplementary; not an input to any criterion).** The text of every chunk of the 16 papers,
  each as a `results` string. Unit: a gate item, id = (chunk id, item index).
- For each arm and sweep the harness reports:
  - RETURNED total;
  - RETURNED with a verified bind;
  - RETURNED without a bind;
  - every unit whose (final, reason) differs from L0, with its value and reason.
- Every `table_value_unbound` item also records its matched tokens and where each matched (cell or table
  block).

**D10 Verified bind.**
- 55-pair units: `bound_correct` (phase 08: status `bound` and the bound cell is a reconstructed gold
  target cell).
- Sweep units: the item's structural binding status is `bound`. No gold exists for them.

**D11 L1 reproduction.**
- 09A's own `validate_09a.run()` analysis is called in-process, with `RGPT_FALLTHROUGH_POLICY=legacy`.
  Its child call is replaced by the L0 (policy off) and L1 (policy consensus) outputs. Its crops are not
  rewritten, and its `results.json` is not written.
- The payload must equal the stored `validation` section of `borderless_09a/results.json`, after the
  timing and provenance keys `generated_at_utc`, `child_wall_seconds`, `versions`, `seconds` and
  `seconds_page` are removed from both. Everything else is compared, including 09A's computed `decision`
  text. The package versions are compared and reported separately.
- **Any difference → STOP.** The difference goes to `results.json` section `reproduction`. G1 is not run,
  and there are no criteria and no decision.
- The same call with G0/G1 under `table_value_guard` gives the 09A-format payload for the guard arms
  (NEG, P4 and canary).

**D12 Guard criteria.** Units: the 55 CANONICAL pairs, the 18 REAL claims and the Sweep A items.
- **Q1.** The 6 units that regressed in 09A are not RETURNED in G1 (every gate item ABSTAINED). They are
  the CANONICAL probes of PF001, PF002, PF006, PF018 and PF019, and the REAL claim of PF017 (C034).
- **Q2.** No unit that is RETURNED with a verified bind in L0 is not so in G0. Likewise L1 → G1.
- **Q3.** No unit that is RETURNED without a verified bind in G0 was not so in L0. Likewise G1 vs L1.

The returns the guard removes (RETURNED in L\* → ABSTAINED in G\*) are listed in full with counts, Sweep B
included. They are not a criterion.

**D13 Borderless criteria (G1 vs L0).**
- **E1.** The REAL claims C013 and C085 are `bound_correct` in G1.
- **E2.** NEG in G1 (from the D11 guard payload). Any other outcome is a FAIL.
  - P019 Table 1 and Table 2 are accepted with exactly 09A's attached cells: the 48 cells reviewed correct
    in 09A, with the same cell dicts.
  - P027 Table 1, P020 TABLE III and P024 Table 2 are rejected with 09A's codes (G3, G1, no_candidate).
- **E3.** No pair whose CANONICAL probe or REAL claim is not RETURNED in L0 is RETURNED without
  `bound_correct` in G1. This is O16's third clause with before = L0 and after = G1.
- **E4.** Zero accepted borderless cells in G1 whose N(value) is not a contiguous word run of their page
  (09A O17).
- **E5.** No verified bind is lost. No 55-pair unit is `bound_correct` in L0 and not in G1, and no Sweep A
  item is `bound` in L0 and not `bound` in G1.

**D14 Decision (mechanical, separate commits).** The decision follows the brief's STEP 4.
- Enabling adds one new line to `configs/staging_config.yaml`: `fallthrough_policy: table_value_guard`, or
  `borderless_policy: consensus`. No existing key changes, and `gate.py` stays additions-only.
- The full suite is re-run for each enable commit. If the only failures are tests that assert the previous
  default of that flag, their expected default is updated in the same commit and disclosed. One such test
  is known now: `tests/test_borderless.py::test_flag_resolution` asserts `off` with the variable unset. Any
  other failure is reported, and that enable commit is not made.

**D15 Reporting.**
- Anything that cannot run is UNMEASURED, with the exact error. A criterion with an UNMEASURED input is
  not PASS.
- Conclusions use counts only.
- The gold, the 09A crop reviews and any reading of the sweep lists are machine-assisted and not
  human-validated.

Known by construction: the guard only turns RETURNED into ABSTAINED, on items that are not `bound`. So Q2
and Q3 test the implementation, not a design risk. The exception is a REAL claim whose `bound_correct`
comes from the whole claim text while its `returned` comes from a different gated sentence. In that case
Q2 can fail, and is measured.
