# ResearchGPT PDF Binding Bottleneck Evaluation — Progress

> **Resume protocol.** After any compaction or new session:
> 1. read this file;
> 2. read ONLY the checkpoint named in *Last Checkpoint*;
> 3. run `git status --short`;
> 4. continue from *Next Action*.
>
> Never reconstruct progress from chat logs. Rules: `RESEARCH_DIRECTIVE.md`. Commits and pushes happen only
> when a phase brief asks for them. Phases 09A and 09B did; phases 00–08 did not.

## Current Phase
None active. **Phase 09B (fall-through guard) is complete.** Q1–Q3 PASS and E1–E5 PASS. By the mechanical
STEP 4 both defaults are enabled, in two separate commits after the report commit:
- `fallthrough_policy = table_value_guard`;
- `borderless_policy = consensus`.

## Status
- Phases 00–08 are complete. Their checkpoints were audited on 2026-09-30: 384 facts, 5 discrepancies found
  and corrected.
- Phase 09A is complete (2026-10-01) on branch `exp/phase09a-borderless`, pushed.
- Phase 09B is complete (2026-10-01) on branch `exp/phase09b-fallthrough`, pushed. The branch was created
  from `864f2e8`.

## Last Completed Phase
`phase_09b_fallthrough`, 2026-10-01.

## Next Action
**Phase 10: the binder.** Wait for the user's brief; do not start it unprompted. 09A and 09B name these
candidates:
- the 9 claims that are binder-blocked even with perfect cells: C005, C012, C025, C034, C035, C048, C052,
  C057, C058;
- the binder residuals: 3 `not_bindable` (P014 C041, C042, C045) and 2 `wrong_cell` (P006 C021, P008 C027);
- two gate findings: an "Ablation-CAM" row forces ablation classification (C013), and sentence splitting at
  "et al." (C085);
- 09B's D5 gap: the guard cannot see a pdf_only table's body text (§8 of the 09B report);
- the guard's recall cost: coincidental token matches (§7 of the 09B report);
- human validation of the 55 machine-assisted gold pairs.

## Repository State
- Branch **`exp/phase09b-fallthrough`**, pushed. It was created from `864f2e8`, the tip of
  `exp/phase09a-borderless` named in the 09B brief. The docs-only `92c85e3` is not an ancestor. Commits:

  | Commit | Content |
  |---|---|
  | `591d063` | 09B pre-registration |
  | `e58dd34` | guard, `gate.py` +69/−0 |
  | `23c1ab9` | tests (8) |
  | `a1b6414` | two more tests, from the review |
  | `8879681` | validation run |
  | report commit | report, checkpoint, this file |
  | next commit | `enable fallthrough_policy=table_value_guard by default` |
  | following commit | `enable borderless_policy=consensus by default` |

- Production code on the branch:
  - `src/evidence/represent.py`: ruled path (phase 04) plus 09A additions (+44/−0);
  - `src/evidence/borderless.py`: 09A;
  - `src/evidence/gate.py`: 09B additions (+69/−0): `_fallthrough_policy`, `numeric_tokens`,
    `claim_value_tokens`, `table_value_tokens` and the guard at the fall-through.
- `configs/staging_config.yaml`: two new lines, `fallthrough_policy: table_value_guard` and
  `borderless_policy: consensus`. No existing key changed.
- Unchanged: the binder matching logic, `chunker.py`, `pdf_parser.py`, `schema.py`, `requirements.txt`, the
  verified gold, and the candidate ZIP (SHA-256 `a11900f2ea572e89…`; untracked, never touched).
- Environments:
  - `.venv`: production, Python 3.10.18, with no docling or torch. Here `borderless_policy=consensus`
    records `borderless_error:…` per routed caption and attaches no cells.
  - `.venv-09a`: gitignored, Python 3.13.6, pinned by `requirements-borderless.txt` (docling 2.117.0,
    transformers 5.17.0, timm 1.0.30, torch 2.14.0 CPU).
- Tests, last run 2026-10-01: **201 passed, 0 failed**.
  - pytest 101: fall-through guard 10, borderless 13, pdf_table_cells 30, physical 6, evaluator 4, anchors 9,
    Stage B 6, Phase 2.1 20, portability 3.
  - `tests/test_pipeline.py`: 37.
  - experiments unit suite: 63.
- Still untracked and not ours: `docs/diagnosis/`, `out/`, `src/evaluation/candidate_gold/`. The scratchpad
  is empty.

## Important Artifacts

| Artifact | What | SHA-256 prefix / note |
|---|---|---|
| `src/evaluation/bottleneck_diagnosis/pdf_identity_manifest_v2.csv` | canonical PDF path + hash per paper | `2177a036cb3ace23` |
| `…/verified_gold_pairs.json` | Stage A verified gold (P003/G002) | `e75d8ef53047e554` |
| `…/gold_binder_oracle.json/.csv/_report.md` | Stage B **pre-fix** oracle record | json `db2862d709c2617b` |
| `…/postfix_candidates.json`, `…/postfix_blind_readings.json`, `…/postfix_labelling_workflow.js` | phase 07 inputs and protocol | `df94a007…`, `450a327a…`, `e8eed1c5…` |
| `…/postfix_claim_cell_gold.json/.csv`, `…/postfix_claim_cell_report.md` | gold: 18 claims / 55 pairs / 12 papers | json `29ac3c4bd250b61e` |
| `…/postfix_binder_oracle.json/.csv/_report.md` | phase 08 before/after + P003 acceptance | json `f48dcb6ee98ba7d1` |
| `src/evaluation/borderless_09a/PREREG_09A.md` | 09A pre-registration | commit `6c1a8b9` |
| `src/evaluation/borderless_09a/results.json` | 09A oracle, identity, validation, review | sections of the same names |
| `src/evaluation/borderless_09a/PHASE09A_REPORT.md`, `crops/` | 09A report; 29 crops | — |
| `src/evaluation/fallthrough_09b/PREREG_09B.md` | 09B pre-registration | commit `591d063` |
| `src/evaluation/fallthrough_09b/results.json` | 09B identity, reproduction, 2x2 run | commit `8879681` |
| `src/evaluation/fallthrough_09b/PHASE09B_REPORT.md` | 09B report; every removed return in Appendix A | — |
| `docs/evaluation/checkpoints/phase_00…phase_09b*.md` | one checkpoint per phase | — |

## Important Decisions
- The candidate ZIP is candidate data, never gold. Only verified pairs count.
- PDFs are the hash-pinned canonical copies; never download or substitute.
- Ruled PDF tables use `find_tables` (ruling-line strategy) with validation rules and an index-aware row
  label. No text strategy and no paper-specific rules.
- **Phase 09A:** the Docling + TATR consensus backend sits behind `borderless_policy`. 09A kept it off
  (P1 and P3 failed).
- **Phase 09B:** the fall-through guard sits behind `fallthrough_policy`, and its code default is `legacy`.
  The pre-registered Q1–Q3 and the re-specified E1–E5 all pass. Both are enabled by default through
  `configs/staging_config.yaml`. E1–E5 were written after 09A and disclosed as motivated by it.
- `gate.py` changes are additions only. The binder matching logic is unchanged.
- Never modify the verified gold or the claim wording to make a test pass.
- Stage B `main()` is never run again. Import its functions.
- Evaluator rules are fixed before results. After results, report defects and do not fix them silently.
- Checkpoint discipline: every phase ends with a checkpoint file and an update of this file.

## Known Issues
- **D5 gap (09B).** A pdf_only table's body text sits in ordinary paragraph blocks (`represent.py:193-195`),
  so the guard cannot see its values.
  - With borderless on, G1 vs L0 has 2 Sweep A items (C036#0, C047#0) and 169 Sweep B items that go from
    `pdf_only`/ABSTAINED to RETURNED without a bind.
  - 26 of them carry a value from a rejected borderless candidate grid (machine-assisted).
  - E3 is pair-scoped and passes; with Sweep A in scope it would fail.
- **Guard recall cost (09B).** Whole-token matches also hit dates, years, section numbers ("Table 4.3"),
  `p < 0.05` and prose blocks typed `table` because their first line starts with "Table " (24 Sweep B
  removals).
- **Reproducing earlier phases after the 09B enables.** The new defaults are borderless `consensus` and
  fall-through `table_value_guard`.
  - Pin `RGPT_BORDERLESS_POLICY=off` and `RGPT_FALLTHROUGH_POLICY=legacy` to reproduce phase 08 or 09A.
  - `validate_09a.py identity` resolves the default borderless policy, so it needs `off` set.
- **Binder-blocked claims** (09A oracle): with perfect cells only 2 of 11 target claims bind. The causes:
  - metric in the caption, or methods as columns;
  - implicit OWN with method-named rows;
  - no metric word (counts, ranges, ICC);
  - metric inside the cell text;
  - plural "DSCs";
  - "R2" parsed as r².
- **Binder limits** (phase 08): the metric vocabulary (`gate.py:455`); comparison claims parsed as a single
  subject (`gate.py:471`); metric only in the caption (`gate.py:482`).
- **Gate findings**, reported only:
  - a row label containing "Ablation" (baseline "Ablation-CAM") makes `classify_table` return ablation, so
    the paper's own result (C013) is withheld;
  - `gate_paper` splits sentences at "et al.", so C085's fragment reads `wrong_cell`.
- **Borderless backend limits:**
  - extraction is per page, so continued tables lose their continuation (P016 T4.2: 14 cells);
  - multi-level headers over 40 characters fail G3 (P017 T6);
  - spanning labels cause disagreement (P017 T7);
  - text-only tables can be "accepted" with 0 cells (P020 TABLE I).
- **Harvest recall limit:** 17 of 129 referenced table labels have no caption that starts a text block.
- **Index cells** are kept as ordinary cells (the Stage B R1 probe flipped from `bound` to `wrong_cell`).
- **Text artifacts:** ligatures, subscripts ("ADC D _"), narrow-cell wraps ("0.94 7", "Mas k", "BLE U").
- **Evaluator caveats** (phase 08): PF026–PF028 ligature mismatch; PF008 tie-break mislabel.
- All gold labels and crop reviews are machine-assisted and unvalidated.
- `tests/test_portability.py` subprocesses write `src/__pycache__/*.pyc` even under `-B` (git-ignored).

## Do Not Redo
- Phases 00–08, as recorded in their checkpoints.
- Phase 09A: target derivation, pre-registration, oracle ceiling, flag-off identity, both validation runs,
  and the crop review.
- Phase 09B: pre-registration, identity, the 2x2 run, the L1 reproduction check and both recomputations.
- No further `src/evidence/represent.py` edit without a new measured reason.
- Do not relabel the phase 07 set with machine readers.
- Do not run `stage_b_gold_binder_oracle.py` as a script.
- Do not change either default (`fallthrough_policy`, `borderless_policy`) without a new pre-registered
  evaluation.

## Last Checkpoint
`docs/evaluation/checkpoints/phase_09b_fallthrough.md` (2026-10-01).
