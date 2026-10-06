# ResearchGPT PDF Binding Bottleneck Evaluation — Progress

> **Resume protocol.** After any compaction or new session:
> 1. read this file;
> 2. read ONLY the checkpoint named in *Last Checkpoint*;
> 3. run `git status --short`;
> 4. continue from *Next Action*.
>
> Never reconstruct progress from chat logs. Rules: `RESEARCH_DIRECTIVE.md`. Commits and pushes happen only
> when a phase brief asks for them. Phases 09A, 09B and the phase 10 package do; phases 00–08 did not.

## Current Phase
**Phase 10 package, complete (2026-10-06).** It has three parts:
1. Freeze 09B: **complete**.
2. Product acceptance before Phase 10: **complete** on `acceptance/pre-phase10`.
   - 0 RETURNED-with-verified-bind in either arm.
   - Gold coverage 3/18.
   - `src/evaluation/acceptance_pre10/ACCEPTANCE_REPORT.md`.
3. Binder v2: recovered, implemented, tested, measured and independently audited.
   - **NO ENABLE: S1 and S2 fail; S3 passes.** Legacy remains default.
   - `src/evaluation/binder_10/PHASE10_REPORT.md` and `checkpoints/phase_10_binder.md`.

## Status
- Phases 00–08 are complete. Their checkpoints were audited on 2026-09-30: 384 facts, 5 discrepancies found
  and corrected.
- Phase 09A is complete (2026-10-01) on branch `exp/phase09a-borderless`, pushed.
- Phase 09B is complete and frozen (2026-10-01) on branch `exp/phase09b-fallthrough`, pushed and
  fast-forwarded into `claude-code-verification`.
  - `fallthrough_policy = table_value_guard` is the default.
  - `borderless_policy` is back to `off` (`42c08c8` reverts `d1b7506`).
- **Phase 09C — Region Guard. STATUS: DEFERRED.** Borderless consensus produced 171 unverified returns vs L0
  (legacy, borderless off). The guard alone added 0 unbound returns in all four unit kinds (Sweep B 528 -> 496
  = exactly its 32 removals). A region guard can only remove returns; it is needed only to enable
  borderless, which Phase 10 does not require.

## Last Completed Phase
`phase_10_binder`, 2026-10-06. The experiment is complete; the binder is not approved for production.

## Next Action
Phase 10 is closed with a no-enable decision. Read `checkpoints/phase_10_binder.md` for the exact resume
boundary. A next implementation phase needs explicit scope; do not repeat recovery or tune against
these measured claims. Immediate release blockers are wrong subject/quantity linking and lost verified
bindings. Earlier product bottlenecks remain claim availability and representation.

## Repository State
- Active experiment branch: `exp/phase10-binder`, recovered from `408137e`. Implementation/test/driver
  commits: `7f55789`, `1cfea2c`, `c805cf4`; measurement/audit: `ad92c87`. No merge into the default branch.
- `claude-code-verification` is the default branch. It now contains `exp/phase09b-fallthrough`
  (fast-forward). The 09B commits after its base `864f2e8`:

  | Commit | Content |
  |---|---|
  | `591d063` | 09B pre-registration |
  | `e58dd34` | guard, `gate.py` +69/−0 |
  | `23c1ab9` | tests (8) |
  | `a1b6414` | two more tests, from the review |
  | `8879681` | validation run |
  | `28b3a26` | 09B report, checkpoint, progress |
  | `534dd4b` | enable `fallthrough_policy=table_value_guard` by default |
  | `d1b7506` | enable `borderless_policy=consensus` by default; **reverted by `42c08c8`** |
  | `42c08c8` | revert, with the reasons in its message |
  | `6d53d4b` | `.gitignore`: `runs/`, `data_acceptance/` |
  | next commit | Freeze docs: 09B report §14, checkpoint, this file |

- Production code:
  - `src/evidence/represent.py`: ruled path (phase 04) plus 09A additions (+44/−0);
  - `src/evidence/borderless.py`: 09A; off by default;
  - `src/evidence/gate.py`: 09B additions (+69/−0), plus Phase 10 router (+37/−0) on this experiment branch.
  - `src/evidence/binder_v2.py`: optional Phase 10 implementation; legacy fallback remains the default.
- `configs/staging_config.yaml`: one new line, `fallthrough_policy: table_value_guard`. No `borderless_policy`
  line, so the code default `off` applies.
- **`runs/p09b_run/`** (gitignored) holds the 64 09B child records: 16 papers × L0/G0/L1/G1.
  - The originals were deleted in the 09B scratchpad cleanup.
  - These were regenerated with the unmodified harness. Re-analysis gives 0 differences from the committed
    results.
- Unchanged: the legacy binder behavior, `chunker.py`, `pdf_parser.py`, `schema.py`, `requirements.txt`, the
  verified gold, and the candidate ZIP (SHA-256 `a11900f2ea572e89…`; untracked, never touched).
- Environments:
  - `.venv`: production, Python 3.10.18, with no docling or torch.
  - `.venv-09a`: gitignored, Python 3.13.6, pinned by `requirements-borderless.txt`.
- Tests, last run 2026-10-05: **180 pytest passed** under both policies in both Python environments.
  - Includes 19 recovered Binder v2 tests and 60 recovery checks, plus the 101 existing tests.
  - `tests/test_pipeline.py`: 37 passed; experiments unit suite: 63 passed, in both runtimes.
  - Separate binder regression: 123 expectations passed in both runtimes.
  - S3: 30/30 PDF gate identity, 55 pairs/18 claims unchanged, newline canary 0.
  - The 3.13 environment's missing existing scikit-learn pin was installed; requirements unchanged.
- Still untracked and not ours: `docs/diagnosis/`, `out/`, `src/evaluation/candidate_gold/`.

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
| `src/evaluation/fallthrough_09b/PHASE09B_REPORT.md` | 09B report; §14 Freeze has the guard recall check | — |
| `runs/p09b_run/` | 09B child records (gitignored, regenerable) | — |
| `docs/evaluation/checkpoints/phase_00…phase_09b*.md` | one checkpoint per phase | — |

## Important Decisions
- The candidate ZIP is candidate data, never gold. Only verified pairs count.
- PDFs are the hash-pinned canonical copies; never download or substitute.
- Ruled PDF tables use `find_tables` (ruling-line strategy) with validation rules and an index-aware row
  label. No text strategy and no paper-specific rules.
- **Phase 09A:** the Docling + TATR consensus backend sits behind `borderless_policy`, which is **off**.
- **Phase 09B:**
  - the fall-through guard is enabled by default (`fallthrough_policy = table_value_guard`);
  - the borderless enable was reverted by the freeze. Reasons: 171 unbound returns outside E3; no docling in
    the production `.venv`.
- `gate.py` changes are additions only. Legacy behavior is byte-identical; v2 is opt-in and experimental.
- Never modify the verified gold or the claim wording to make a test pass.
- Stage B `main()` is never run again. Import its functions.
- Evaluator rules are fixed before results. After results, report defects and do not fix them silently.
- Checkpoint discipline: every phase ends with a checkpoint file and an update of this file.

## Known Issues
- **Phase 10 release blocked.** S1 records 9 R-prod / 10 R-eval gold-unit violations under conservative
  frozen reconstruction, plus one semantically wrong sweep binding confirmed by both PDF reviewers.
  S2 loses 1 R-prod / 4 R-eval gold units and 9 / 13 sweep associations. All 22 new bindings were audited.
  Product verified bindings remain zero. Full failure lists and scoring caveats are in the Phase 10 report.
- **D5 gap (09B).** A pdf_only table's body text sits in ordinary paragraph blocks (`represent.py:193-195`),
  so the guard cannot see its values. With borderless on, this gives 171 new unbound returns vs L0. It is the
  reason borderless stays off and Phase 09C is deferred.
- **Guard recall cost (09B; checked in the freeze).** Of the 33 returns the guard removes without borderless,
  13 are coincidental matches by two independent agent checks (machine-assisted):

  | Kind | Count |
  |---|---|
  | different quantity | 6 |
  | prose typed as a table | 3 |
  | section/table/page number | 3 |
  | date | 1 |

  The other 20 are correct abstentions.
- **Reproducing phase 08 / 09A gate results** now needs `RGPT_FALLTHROUGH_POLICY=legacy`, because the guard is
  the default.
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
- All gold labels, crop reviews and agent checks are machine-assisted and unvalidated.
- `tests/test_portability.py` subprocesses write `src/__pycache__/*.pyc` even under `-B` (git-ignored).

## Do Not Redo
- Phase 10 recovery, synthetic validation, S3, deterministic measurement and two independent PDF audits.
  Preserve the failed release decision; no post-result tuning or evaluator changes.
- Phases 00–08, as recorded in their checkpoints.
- Phase 09A: target derivation, pre-registration, oracle ceiling, flag-off identity, both validation runs,
  and the crop review.
- Phase 09B: pre-registration, identity, the 2x2 run, the L1 reproduction check and both recomputations.
- The 09B freeze: the revert, the guard recall check (33 items), and the regeneration of `runs/p09b_run/`.
- No further `src/evidence/represent.py` edit without a new measured reason.
- Do not relabel the phase 07 set with machine readers.
- Do not run `stage_b_gold_binder_oracle.py` as a script.
- Do not enable `borderless_policy` without a region guard and a new pre-registered evaluation.

## Last Checkpoint
`docs/evaluation/checkpoints/phase_10_binder.md` (2026-10-06). Full report:
`src/evaluation/binder_10/PHASE10_REPORT.md`. The 09B freeze remains recorded in `phase_09b_fallthrough.md`.
