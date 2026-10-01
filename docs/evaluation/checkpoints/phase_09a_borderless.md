# Phase 09A — Borderless-table backend behind a default-off flag

## Objective
Add a Docling + Table Transformer consensus backend for tables the ruled path rejects as
`no_ruled_table_beside_caption`, behind `borderless_policy` (default `off`). Validate it on the existing
gold set, and enable it only if the pre-registered P1–P4 all pass.

## Inputs
- Gold: `src/evaluation/bottleneck_diagnosis/postfix_claim_cell_gold.json` (55 pairs / 18 claims /
  12 papers; machine-assisted).
- Phase 08 failures: `postfix_binder_oracle.json`.
- The hash-pinned PDFs.
- Pre-registration: `src/evaluation/borderless_09a/PREREG_09A.md`, committed `6c1a8b9` before any run.

## Work Performed
- Target set derived: **10 tables / 11 claims**, exactly as the brief listed.
- Backend `src/evidence/borderless.py`, and `represent.py` additions only (+44/−0).
- `requirements-borderless.txt` and `.venv-09a` (Python 3.13.6).
- Tests; Step 1 oracle; O18 flag-off identity.
- Two validation runs: 16 papers × 2 flags, one CPU process each.
- Agent crop review of 205 cells in 9 accepted tables, plus a manual P2 check.
- Report.

## Results
FACT:
- **Oracle (Step 1):** 2 of 11 target claims bind to a gold cell even with perfect cells (C013, C085; 2
  papers). 9 are binder-blocked: C005, C012, C025, C034, C035, C048, C052, C057, C058.
- **O18:** flag off gives identical blocks and records on 30/30 PDFs vs `797a922`. The 55-pair evaluation
  shows 0 differences.
- **Target tables:**
  - 7/10 accepted: P001 T4, P004 T2, P007 T3, P011 T1, P015 T2, P016 T4.2, P030 T2;
  - 3 rejected: P004 T1 on G1 (merged rows), P017 T6 on G3 (headers > 40 characters), P017 T7 as
    disagree (spanning labels).
  - The 7 accepted tables hold 12/12 gold target cells correct.
  - Crop review: 157/157 attached cells correct.
  - P016 T4.2 is incomplete: its p23 continuation (14 numeric cells) is not captured.
- **Target claims:** 2 bound to gold (C013, C085), equal to the oracle ceiling. 0 RETURNED with a
  verified bind. C013 is withheld by the gate as `bound_to_ablation_table` because a baseline row is named
  "Ablation-CAM".
- **NEG:**
  - P019 T1 and T2 accepted, 48/48 cells correct (the manual check and an independent agent check agree);
  - P027 T1 rejected on G3, P020 T III on G1, P024 T2 as no_candidate.
- **Regressions (P3): 6.** PF001, PF002, PF006, PF017, PF018, PF019, all "unverified return" through the
  `not_bindable` fall-through (`gate.py:544`).
- **P4:** 533 accepted cells, 0 absent from the text layer. Canary 0. UNMEASURED: none.
- **Whole run:** 50 routed captions: 24 accepted / 26 rejected (no_candidate 9, disagree 7, G1 7, G3 3) /
  0 errors.
- **Criteria: P1 FAIL, P2 PASS, P3 FAIL, P4 PASS.**
- **Timing:** Docling 1.28–41.16 s/page, TATR 0.36–6.96 s/page on CPU. The runs are deterministic
  (run 1 = run 2).
- **Tests:** `tests/test_borderless.py` 13 passed (both venvs); full suite 191 passed, 0 failed.

INTERPRETATION: the backend is safe on this set (P2 and P4 hold, and every attached cell reviewed is
correct), and it reconstructs 7 of 10 target tables. But the gain is capped by the binder: the oracle
allows only 2 claims. Adding cells also widens the unverified-return path, which is P3.

DECISION: **the default stays `off`** (mechanical STEP 6). No enable commit.

## Evidence
`src/evaluation/borderless_09a/`:
- `PREREG_09A.md`;
- `validate_09a.py`;
- `results.json`, with sections oracle, identity, validation and review;
- `PHASE09A_REPORT.md`;
- `crops/`: 29 PNGs.

Tests: `tests/test_borderless.py`.

## Decisions
- "Current HEAD" means baseline `797a922`.
- The dependency installs were authorised by the brief, recorded as an exception to the directive's
  new-dependency stop.
- Python 3.13 worked, so 3.11 was not used.
- docling is pinned at 2.117.0 (below 2.118.0).
- Two transformers-5 shims for TATR: config `dilation` null → False, and the structure preprocessor's
  `longest_edge` 800 applied manually.
- The reporting key fix in `validate_09a.py` after run 1 changed no scoring rule. It is disclosed, and
  run 2 reproduced every verdict.

## Changes
Branch `exp/phase09a-borderless` commits: `4d3c183` (bottleneck_diagnosis), `797a922` (baseline), `6c1a8b9`
(prereg), `189a037` (backend), `6e39fbe` (tests), `671afb8` (validation run), `864f2e8` (report, checkpoint,
progress), then a docs-only commit that records this hash.
- Production files changed: `src/evidence/represent.py` (+44/−0) and the new `src/evidence/borderless.py`.
- Also changed: `.gitignore` (+ `.venv-09a/`) and the new `requirements-borderless.txt`.
- Unchanged: `gate.py`, the binder, `requirements.txt`, configs and the gold.

## Temporary Files
Scratchpad:
- `results_run1.json` (for the determinism comparison);
- `verify_09a/accepted_tables.json` (regenerated cells for the crop review).

Logs inside `.venv-09a/` (gitignored): `install.log`, `validate_run.log`, `validate_run2.log`.

## Cleanup
- Both scratchpad files deleted after their results went into `results.json` (review section).
- `.venv-09a/` is kept: it is needed to reproduce the consensus runs.

## Current State
**Phase 09A complete.** Default `off`; branch pushed to origin.

## Next Step
The user chooses the next change. The report names it: the binder residuals (3 `not_bindable`, 2
`wrong_cell`), the 9 oracle-blocked claims, the two gate findings, and closing the `not_bindable`
fall-through (P3).

## Do Not Redo
- Target derivation, pre-registration, oracle, identity check and both validation runs.
- The crop review.
- Do not enable `borderless_policy` without new pre-registered evidence.

## Reproduction
```
py -3.13 -m venv .venv-09a && .venv-09a/Scripts/python.exe -m pip install -r requirements-borderless.txt
PYTHONIOENCODING=utf-8 .venv-09a/Scripts/python.exe -B src/evaluation/borderless_09a/validate_09a.py oracle
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/borderless_09a/validate_09a.py identity
CUDA_VISIBLE_DEVICES="" PYTHONIOENCODING=utf-8 .venv-09a/Scripts/python.exe -B src/evaluation/borderless_09a/validate_09a.py run
.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_borderless.py
```
