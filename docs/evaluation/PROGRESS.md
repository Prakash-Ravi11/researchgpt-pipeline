# ResearchGPT PDF Binding Bottleneck Evaluation — Progress

> **Resume protocol.** After any compaction or new session:
> 1. read this file;
> 2. read ONLY the checkpoint named in *Last Checkpoint*;
> 3. run `git status --short`;
> 4. continue from *Next Action*.
>
> Never reconstruct progress from chat logs. Rules: `RESEARCH_DIRECTIVE.md`. Commits and pushes happen only
> when a phase brief asks for them. Phase 09A did; phases 00–08 did not.

## Current Phase
None active. **Phase 09A (borderless-table backend) is complete.** The default stays
`borderless_policy = off`: P1 FAIL, P2 PASS, P3 FAIL, P4 PASS. The next phase needs the user's choice.

## Status
- Phases 00–08 are complete. Their checkpoints were audited on 2026-09-30: 384 facts, 5 discrepancies found
  and corrected.
- Phase 09A is complete (2026-10-01) on branch `exp/phase09a-borderless`, which is pushed to origin.

## Last Completed Phase
`phase_09a_borderless`, 2026-10-01.

## Next Action
Wait for the user to choose the next change. Do not start it unprompted. The phase 09A report names these
candidates:
- the binder residuals: 3 `not_bindable` (P014 C041, C042, C045) and 2 `wrong_cell` (P006 C021, P008 C027);
- the 9 claims that are binder-blocked even with perfect cells: C005, C012, C025, C034, C035, C048, C052,
  C057, C058;
- two gate findings: an "Ablation-CAM" row label forces ablation classification (C013), and sentence
  splitting at "et al." (C085);
- closing the `not_bindable` → grounding → RETURNED fall-through before any backend adds cells by default
  (this is phase 09A's P3);
- human validation of the 55 machine-assisted gold pairs.

## Repository State
- Branch **`exp/phase09a-borderless`**, pushed. It was created from `30fc85d` (`claude-code-verification`,
  unchanged). Its commits:

  | Commit | Content |
  |---|---|
  | `4d3c183` | bottleneck_diagnosis |
  | `797a922` | phase 04–08 baseline: ruled-table `represent.py`, tests, checkpoints, `BLOCKED.md` |
  | `6c1a8b9` | 09A pre-registration |
  | `189a037` | backend |
  | `6e39fbe` | tests |
  | `671afb8` | validation run |
  | final commit | report + this file |

- Production code on the branch:
  - `src/evidence/represent.py`: ruled path (phase 04) plus 09A additions (+44/−0);
  - `src/evidence/borderless.py`: new, used only when `borderless_policy=consensus`.
- Unchanged: `gate.py` and the binder, `chunker.py`, `pdf_parser.py`, `schema.py`, `requirements.txt`,
  configs, the verified gold, and the candidate ZIP (SHA-256 `a11900f2ea572e89…`; untracked, never touched).
- Environments:
  - `.venv`: production, Python 3.10.18;
  - `.venv-09a`: gitignored, Python 3.13.6, pinned by `requirements-borderless.txt` (docling 2.117.0,
    transformers 5.17.0, timm 1.0.30, torch 2.14.0 CPU).
- Tests, last run 2026-10-01: **191 passed, 0 failed**.
  - pytest 91: borderless 13, pdf_table_cells 30, physical 6, evaluator 4, anchors 9, Stage B 6,
    Phase 2.1 20, portability 3.
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
| `docs/evaluation/checkpoints/phase_00…phase_09a*.md` | one checkpoint per phase | — |

## Important Decisions
- The candidate ZIP is candidate data, never gold. Only verified pairs count.
- PDFs are the hash-pinned canonical copies; never download or substitute.
- Ruled PDF tables use `find_tables` (ruling-line strategy) with validation rules and an index-aware row
  label. No text strategy and no paper-specific rules.
- **Phase 09A:** the Docling + TATR consensus backend exists behind `borderless_policy`, **default `off`**.
  It is not enabled: P1 and P3 fail. Enabling it needs new pre-registered evidence.
- `gate.py` and the binder are unchanged. Change them only when an evaluation proves it necessary.
- Never modify the verified gold or the claim wording to make a test pass.
- Stage B `main()` is never run again. Import its functions.
- Evaluator rules are fixed before results. After results, report defects and do not fix them silently.
- Checkpoint discipline: every phase ends with a checkpoint file and an update of this file.

## Known Issues
- **Binder-blocked claims** (phase 09A oracle): with perfect cells only 2 of 11 target claims bind. The
  causes: metric in the caption or methods as columns; implicit OWN with method-named rows; no metric
  word (counts, ranges, ICC); metric inside the cell text; plural "DSCs"; "R2" parsed as r².
- **Binder limits** (phase 08): the metric vocabulary (`gate.py:455`); comparison claims parsed as a single
  subject (`gate.py:471`); metric only in the caption (`gate.py:482`).
- **Fall-through precision risk**, now measured: once a paper has any cells, `not_bindable` /
  `not_a_table_claim` claims fall through to grounding (`gate.py:544`). With the borderless backend on,
  **6 pairs** gained unverified returns (PF001, PF002, PF006, PF017, PF018, PF019).
- **Gate findings**, reported only:
  - a row label containing "Ablation" (baseline "Ablation-CAM") makes `classify_table` return ablation,
    so the paper's own result (C013) is withheld;
  - `gate_paper` splits sentences at "et al.", so C085's fragment reads `wrong_cell`.
- **Borderless backend limits:**
  - extraction is per page, so continued tables lose their continuation (P016 T4.2: 14 cells);
  - multi-level headers over 40 characters fail G3 (P017 T6);
  - spanning labels cause disagreement (P017 T7);
  - text-only tables can be "accepted" with 0 cells (P020 TABLE I).
- **Borderless still uncovered with the flag off:** 11 of 18 claims fail at representation (phase 08).
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
- No further `src/evidence/represent.py` edit without a new measured reason.
- Do not relabel the phase 07 set with machine readers.
- Do not run `stage_b_gold_binder_oracle.py` as a script.
- Do not enable `borderless_policy` by default without a new pre-registered evaluation.

## Last Checkpoint
`docs/evaluation/checkpoints/phase_09a_borderless.md` (2026-10-01).
