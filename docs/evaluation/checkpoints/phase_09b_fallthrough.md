# Phase 09B — Fall-through guard (`table_value_guard`) and the borderless re-decision

## Objective
Close the `not_bindable` / `not_a_table_claim` → grounding → RETURNED fall-through (09A's P3, `gate.py:544`)
behind a new flag, `fallthrough_policy`, with default `legacy`. Then re-decide `borderless_policy` with
newly pre-registered criteria E1–E5. They replace 09A's P1, which could not pass: the oracle ceiling is 2.

## Inputs
- 09A results: `src/evaluation/borderless_09a/results.json` (6 regressions, oracle ceiling 2).
- Gold: `postfix_claim_cell_gold.json` (55 pairs / 18 claims; machine-assisted).
- Harvested claims: `postfix_candidates.json` (48 in the 16 papers).
- The hash-pinned PDFs.
- Pre-registration: `src/evaluation/fallthrough_09b/PREREG_09B.md`, committed `591d063` before any run.

## Work Performed
- Guard in `gate.py`: additions only, +69/−0. Committed `e58dd34`.
- Tests: 8 in `23c1ab9`, plus 2 from a read-only review in `a1b6414`.
- STEP 2 identity vs `864f2e8`, in the production `.venv`.
- STEP 3 2x2 run on 16 papers: 64 child processes on CPU in `.venv-09a`, gating per arm in the parent,
  and the L1 reproduction check against 09A.
- Two independent recomputations of every criterion from the raw child outputs.
- Report.

## Results
FACT:
- **Identity:** gate records identical on 30/30 PDFs (11,128 inputs, 9,507 items). The 55-pair
  evaluation shows 0 differences. Under the guard, 8 PDFs differ (sensitivity control).
- **L1 = 09A:** 09A's own analysis gives an identical validation payload, and identical versions.
  Representation is the same with either fall-through policy: L0 = G0 and L1 = G1 on 16/16 papers.
- **2x2**, as RETURNED (verified / without bind), over 55 pairs / 18 claims / Sweep A 96 items / Sweep B
  5,285 items:

  | Arm | Pairs | Claims | Sweep A | Sweep B |
  |---|---|---|---|---|
  | L0 | 5 (4/1) | 2 (2/0) | 4 (1/3) | 533 (5/528) |
  | G0 | 4 (4/0) | 2 (2/0) | 4 (1/3) | 501 (5/496) |
  | L1 | 10 (4/6) | 3 (2/1) | 10 (1/9) | 778 (5/773) |
  | G1 | 4 (4/0) | 2 (2/0) | 6 (1/5) | 669 (5/664) |

- **Q1 PASS:** the 6 regressions from 09A are ABSTAINED in G1 with `table_value_unbound`. Each matched an
  attached cell that holds the value the binder did not bind.
- **Q2, Q3: 0 violations each, PASS.**
- **E1 PASS:** C013 and C085 are `bound_correct`.
- **E2 PASS:** P019's 48 cells are identical to 09A's; P027 G3, P020 G1 and P024 no_candidate.
- **E3 PASS:** 0.
- **E4 PASS:** 0 of 533 cells absent from the text layer.
- **E5 PASS:** 0.
- **Returns removed by the guard:**

  | Comparison | Pairs | Claims | Sweep A | Sweep B |
  |---|---|---|---|---|
  | L0→G0 | 1 | 0 | 0 | 32 |
  | L1→G1 | 6 | 1 | 4 | 109 |

  - All 7 pair and claim removals were unverified returns.
  - The sweep removals include coincidental token matches (dates, years, section numbers, prose typed as
    a table).
- **Not closed, outside the criteria:** in G1 vs L0, 2 Sweep A items (C036#0, C047#0) and 169 Sweep B items
  go from `pdf_only`/ABSTAINED to RETURNED without a bind.
  - The guard cannot see the body of a pdf_only table, which sits in ordinary text blocks
    (`represent.py:193-195`).
  - 26 of the 171 carry a value from a rejected borderless candidate grid (machine-assisted).
  - E3 is pair-scoped, so it passes. With Sweep A in scope it would fail.
- **Timing:** child wall L0 17.4 s, G0 17.0 s, L1 506.9 s, G1 460.7 s. Docling 1.22–44.21 s per page,
  TATR 0.28–5.52 s. 09A's 24,361.6 s was mostly one suspended child (P017, 23,517.2 s).
- **Tests:** full suite 201 passed, 0 failed. Also 201/201 with both flags enabled through the
  environment.

INTERPRETATION:
- The guard closes the measured P3 path for the 55 pairs. It does so without losing a verified return, and
  without adding an unverified one in either representation.
- Enabling borderless still lets values of pdf_only table bodies through on non-gold claims (D5 gap). The
  pre-registered criteria do not cover that.

DECISION (mechanical, STEP 4): enable both defaults, in two separate commits after the report commit:
- "enable fallthrough_policy=table_value_guard by default";
- "enable borderless_policy=consensus by default".

Each adds one line to `configs/staging_config.yaml`. The borderless commit also updates the two
old-default assertions in `tests/test_borderless.py::test_flag_resolution` (D14). Reverting the borderless
commit alone restores `borderless_policy=off`.

## Evidence
`src/evaluation/fallthrough_09b/`:
- `PREREG_09B.md`;
- `validate_09b.py`;
- `results.json`, with sections identity, reproduction and run;
- `PHASE09B_REPORT.md`, which lists every removed return in Appendix A.

Tests: `tests/test_fallthrough_guard.py`.

## Decisions
- The branch starts at `864f2e8`, as the brief says. The docs-only `92c85e3` is not an ancestor.
- "ALL claims" means the 48 harvested claims in the 16 papers (Sweep A). Every chunk's text (Sweep B) is
  supplementary.
- Tokens are unsigned and whole, and are not read after a letter. A comma separates them. Claim values are
  anchor-shaped. Table text means the `block_type == table` chunks (PREREG D3–D5).
- One child per paper per arm was run literally (64 children). Representation does not depend on the
  fall-through flag (16/16 identical).

## Changes
Commits on `exp/phase09b-fallthrough`, in order:
- `591d063` prereg;
- `e58dd34` guard;
- `23c1ab9` tests;
- `a1b6414` two more tests;
- `8879681` validation run;
- the report commit;
- two enable commits.

Files:
- Production code changed: `src/evidence/gate.py`, +69/−0. The binder, `represent.py`, `borderless.py`, the
  gold and `requirements.txt` are unchanged.
- Configs: two new lines in `configs/staging_config.yaml`, one per enable commit. No existing key changed.

## Temporary Files
- Scratchpad, all deleted at the end of the phase:
  - `p09b_run/` (64 child outputs and the children log);
  - `p09b_run.log`;
  - `smoke/`, `smoke2/` and their results;
  - `verify/` (the two recomputation scripts and their outputs);
  - report fragments.
- `.venv-09a/` is kept.

## Cleanup
The scratchpad was emptied after `results.json` and the report were committed.

## Current State
**Phase 09B complete.** On the branch tip, `fallthrough_policy = table_value_guard` and
`borderless_policy = consensus` are the defaults. The branch is pushed to origin.

## Next Step
Phase 10: the binder. Its scope includes:
- the 9 oracle-blocked claims;
- the binder residuals (3 `not_bindable`, 2 `wrong_cell`);
- the two gate findings (Ablation-CAM, the "et al." split);
- 09B's D5 gap (pdf_only table bodies are invisible to the guard);
- the guard's recall cost.

## Do Not Redo
- The 09B pre-registration, identity, 2x2 run, reproduction check and both recomputations.
- Do not re-decide the two defaults without a new pre-registered evaluation.

## Reproduction
```
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/fallthrough_09b/validate_09b.py identity
CUDA_VISIBLE_DEVICES="" PYTHONIOENCODING=utf-8 .venv-09a/Scripts/python.exe -B src/evaluation/fallthrough_09b/validate_09b.py run <workdir>
.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_fallthrough_guard.py
```
To reproduce the pre-enable arms on the post-enable branch tip, set both variables explicitly. For example,
L0 is `RGPT_FALLTHROUGH_POLICY=legacy` with `RGPT_BORDERLESS_POLICY=off`. `validate_09b.py` sets both per
arm.
