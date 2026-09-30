# ResearchGPT PDF Binding Bottleneck Evaluation — Progress

> **Resume protocol.** After any compaction or new session:
> 1. read this file;
> 2. read ONLY the checkpoint named in *Last Checkpoint*;
> 3. run `git status --short`;
> 4. continue from *Next Action*.
>
> Never reconstruct progress from chat logs. Rules: `RESEARCH_DIRECTIVE.md`. Nothing is committed or pushed.

## Current Phase
None active. Phase 08 (30-paper post-fix evaluation) is complete. Phase 09 is **not started** and needs
the user's scope decision.

## Status
Phases 00–08 are complete. The checkpoint documentation was created on 2026-09-30 from the repository
artifacts.

Two read-only verifier agents audited it against those artifacts: 384 facts checked, 5 discrepancies
found, all corrected on 2026-09-30:
- PF013 misattributed to the unparsed-table case;
- `test_postfix_evaluate.py` misattributed to Phase 05;
- the P001 contextual-tier example, which revealed the harvest recall limit;
- "meet" corrected to "exceed" for the 30–50-pair aim;
- a stale test-docstring path.

## Last Completed Phase
`phase_08_30paper_evaluation`, 2026-09-30.

## Next Action
Wait for the user to choose Phase 09. Do not start any option unprompted. Candidate scopes:
- (A) borderless-table reconstruction: blocks 11 of 18 claims;
- (B) the binder's metric/subject model: `not_bindable`, comparison claims, metric in the caption;
- (C) the fall-through gate path (`not_bindable` / `not_a_table_claim` fall through to grounding once a
  paper has any cells);
- (D) human validation of the 55 machine-assisted pairs.

## Repository State
- Branch `claude-code-verification`, HEAD `30fc85d75d9ec5aaf8d354d38c0cddab82930418`. Not committed, not pushed.
- Tracked, modified:
  - `src/evidence/represent.py`: +220/−1, the only production change; SHA-256 `b413d68dc3e9795b…`;
  - `BLOCKED.md`: +46, the directive stop log.
- Untracked, new this programme:
  - `docs/evaluation/` (this file and the checkpoints);
  - `tests/test_pdf_table_cells.py`;
  - `src/evaluation/bottleneck_diagnosis/*` (scripts, tests, artifacts).

  `docs/`, `out/` and `src/evaluation/` were already untracked.
- Unchanged: `gate.py` and the binder, `chunker.py`, `pdf_parser.py`, `schema.py`, configs, the verified gold,
  and the candidate ZIP (SHA-256 `a11900f2ea572e89…`, re-checked 2026-09-30).
- Tests, last run 2026-09-30: **178 passed, 0 failed, 0 skipped**.
  - pytest 78: new 30 + 6 + 4; `test_anchors` 9; Stage B 6; Phase 2.1 20; portability 3.
  - `tests/test_pipeline.py`: 37.
  - experiments unit suite: 63.
- The scratchpad is empty; nothing important lives outside the repository.

## Important Artifacts
All in `src/evaluation/bottleneck_diagnosis/` unless noted.

| Artifact | What | SHA-256 prefix |
|---|---|---|
| `pdf_identity_manifest_v2.csv` | canonical PDF path + hash per paper (PDF source of truth) | `2177a036cb3ace23` |
| `verified_gold_pairs.json` | Stage A verified gold (P003/G002 only) | `e75d8ef53047e554` |
| `gold_binder_oracle.json/.csv/_report.md` | Stage B **pre-fix** oracle record | json `db2862d709c2617b` |
| `postfix_candidates.json` | 85 harvested candidates (evaluator input) | `df94a0071f3892cf` |
| `postfix_blind_readings.json` | raw blind readings, 2 readers × 85 (evaluator input) | `450a327af10e03ae` |
| `postfix_labelling_workflow.js` | blind-reader protocol (prompts) | `e8eed1c5d8588a2b` |
| `postfix_claim_cell_gold.json/.csv`, `postfix_claim_cell_report.md` | gold: 18 claims / 55 pairs / 12 papers | json `29ac3c4bd250b61e` |
| `postfix_binder_oracle.json/.csv/_report.md` | before/after evaluation + P003 acceptance | json `f48dcb6ee98ba7d1` |
| `postfix_mine_claims.py`, `postfix_evaluate.py` | harvest; gold assembly + evaluation | — |
| `tests/test_pdf_table_cells.py`, `test_postfix_physical_pdfs.py`, `test_postfix_evaluate.py` | regression tests (30 / 6 / 4) | — |
| `docs/evaluation/checkpoints/phase_00…phase_08*.md` | one checkpoint per phase | — |

## Important Decisions
- The candidate ZIP is candidate data, never gold. Only verified pairs count.
- PDFs are the hash-pinned canonical copies from `pdf_identity_manifest_v2.csv`; never download or substitute.
- The fix lives in the representation layer only: ruled PDF tables via `find_tables` (ruling-line
  strategy), cells attached to caption blocks, malformed grids rejected, and an index-aware row label.
  No text strategy; no paper-specific rules.
- `gate.py` and the binder are unchanged. Change them only if a later evaluation independently proves it
  necessary.
- Never modify the verified gold or the claim wording to make a test pass.
- Stage B `main()` is never run again (it would overwrite the pre-fix record). Import its functions.
- Evaluator rules are fixed before results. After results, report defects; do not fix them silently.
- Checkpoint discipline (2026-09-30): every phase ends with a checkpoint file and an update of this file.

## Known Issues
- **Borderless tables get no cells.** 11 of 18 claims fail at representation because of this (Phase 08).
- **Binder limits** (not fixed):
  - metric vocabulary (`gate.py:455`): 3 P014 claims;
  - comparison claims with a single-subject parse (`gate.py:471`);
  - metric only in the caption (`gate.py:482`).
- **Fall-through precision risk.** Once a PDF paper has any cells, claims the binder cannot bind
  (`not_bindable`, `not_a_table_claim`) fall through to grounding (`gate.py:544`) instead of abstaining as
  `pdf_only`.
  - PF013 (parsed table; the metric "95HD" is not recognised) was RETURNED without a bind.
  - P017 C057/C058 (unparsed tables) still abstained.

  Unmeasured beyond this set.
- **Harvest recall limit.** A table is found only when its caption starts a text block. 17 of 129
  referenced table labels had no such caption (for example P001 Table 5, whose caption is merged below the
  table), so 17 explicit numeric sentences were never candidates. The P001 p13 claim that motivated the
  contextual tier is among the misses.
- **Index cells** are kept as ordinary cells. The Stage B R1 CANONICAL_ROWLABEL probe flipped from `bound`
  to `wrong_cell`.
- **Text artifacts:** ligatures expanded in table text but not in block text; subscripts garbled
  ("ADC D _"); narrow-cell wraps ("0.94 7", "Mas k", "BLE U"); P003 Table 3 caption truncated.
- **Evaluator caveats** (disclosed, not changed): PF026–PF028 ligature mismatch (true correct count
  26/55, not 23/55); PF008 tie-break mislabel.
- All Phase 07 labels are machine-assisted and unvalidated; human validation is pending.
- `tests/test_portability.py` subprocesses write `src/__pycache__/*.pyc` even under `-B` (git-ignored;
  delete after runs).

## Do Not Redo
- Phases 00–08: the ZIP inventory, PDF identity, Stage A, the Stage B pre-fix oracle, the prototype and
  rule measurement, the production edit, test design, P003 acceptance, harvest + blind labelling, and the
  post-fix evaluation.
- No further `src/evidence/represent.py` edit without a new measured reason.
- Do not relabel the Phase 07 set with machine readers.
- Do not run `stage_b_gold_binder_oracle.py` as a script.

## Last Checkpoint
`docs/evaluation/checkpoints/phase_08_30paper_evaluation.md` (2026-09-30).
