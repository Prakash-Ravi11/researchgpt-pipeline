# Phase 10 forensic recovery

Recovery started 2026-10-04. This inventory precedes production edits. It is not a declaration that Binder v2 passes review or measurement.

## Starting repository state

- Branch: `exp/phase10-binder`; HEAD: `408137e`.
- `afe1488`: committed `FAILURE_MAP_10.md` (STEP 0).
- `408137e`: committed `PREREG_10.md` (STEP 1).
- `acceptance/pre-phase10`: `6ed2434`; `claude-code-verification` and `exp/phase09b-fallthrough`: `2d61f3c`.
- Reflog contains no later Phase 10 implementation commit. Stash list is empty.
- Existing tracked modification: `src/evidence/gate.py`, +37/-0, the binder-policy router. Preserved.
- Existing untracked paths: `docs/diagnosis/`, `out/`, `src/evaluation/candidate_gold/`. Preserved; outside this task's commit scope.
- Missing from repository: `src/evidence/binder_v2.py`, `tests/test_binder_v2.py`, `src/evaluation/binder_10/validate_10.py`.

## Exact recovery sources

Scratch root:
`C:/Users/Praka/AppData/Local/Temp/claude/c--Users-Praka-Downloads-researchgpt-pipeline/9fe1cf2b-4656-4e21-9780-cce5de20ea51/scratchpad`

Session root:
`C:/Users/Praka/.claude/projects/c--Users-Praka-Downloads-researchgpt-pipeline/9fe1cf2b-4656-4e21-9780-cce5de20ea51`

The current scratch implementation and review2 frozen snapshot both survive and are byte-identical by SHA-256. The first draft is rejected and will not be used as the final implementation. No reconstruction from partial transcript text is needed for the current binder.

| Scratch artifact | Bytes | SHA-256 before modification |
|---|---:|---|
| `binder_v2.py` | 62827 | `52702fb251905f1a0edf7a499c499fb521a6e80f3fcd0d47ee150a5489c37677` |
| `review2/binder_v2_under_review.py` | 62827 | `52702fb251905f1a0edf7a499c499fb521a6e80f3fcd0d47ee150a5489c37677` |
| `test_binder_v2.py` | 13811 | `fb3a4dc0a9dc13fb02b67514c73960d4b633ee3f8aff7f82d19aca784af51627` |
| `regress.py` | 21034 | `7de18d8be60809c43dbb3f77bd9e015199d933ffd9a881cc50fdc5364ca253f6` |
| `validate_10.py` | 29294 | `777b80a2db413b215b08018642a849782bc8a8911589f37eac0d23d82b97a110` |
| `dev_run.py` | 670 | `fe839909c897feeab73805e81c5ba2fbb033c96fc940a42fefa3a899709484ccc` |
| `regress_out.txt` | 6840 | `2ea4b7330ba618087aaa0d60d95a6830a7777ab7f237089998bfe952d19d3308` |
| `prof.py` | 649 | `231622b669950a621c2a0dbf62217ce3110d389413e9b53fc846344ad200fdd9` |

Also discovered: `validate_10_modes.py`, `dbg.py`, four first-draft fix scripts, and first-review precision/specification/robustness reproduction scripts and outputs. Source timestamps and complete selected-file hashes will be persisted in the recovery manifest alongside the outside-repository backup.

## Second review workflow

Discovered `workflows/wf_88a01c89-073.json`, `workflows/scripts/binder-v2-rewrite-review-wf_88a01c89-073.js`, and `subagents/workflows/wf_88a01c89-073/` containing four JSONL transcripts, four metadata files, and `journal.jsonl`.

All four lenses started: `wrongbind_structure`, `wrongbind_table`, `lost_legacy`, `spec_robust`. All failed at the weekly usage limit. The workflow's top-level completed status and empty finding arrays are not a completed review. The journal records four starts and four failures. `review2/` contains only the frozen binder snapshot and no reproduction scripts. An equivalent fresh adversarial review is therefore required.

## Safety boundary and next work

1. Preserve exact artifacts outside the repository and verify hashes before editing any recovered copy.
2. Review the recovered implementation and harnesses, using synthetic inputs only.
3. Re-run the four adversarial lenses and both Python environments before integration.
4. Keep `binder_policy=legacy`, `fallthrough_policy=table_value_guard`, and `borderless_policy=off` until the preregistered decision.
5. Do not access the 55-pair evaluation data during synthetic review. Do not run gold measurement until synthetic review, full tests, and S3 allow it.

No production changes, integrations, measurement runs, or commits have been performed by this recovery at inventory creation. Further results will be appended with their artifacts.

## Recovery resumed 2026-10-05

- The outside-repository backup completed: 76 artifacts copied and SHA-256 checked at `C:/Users/Praka/Downloads/recovery_phase10/20261004_exact/`. Exact timestamps and hashes are in `recovery_manifest.json`.
- The source in the four interrupted reviewer transcripts was read-only; no second-review findings were lost. All four failed at the weekly usage limit despite the workflow wrapper's completed status.
- Fresh synthetic reviews found confirmed defects. General fixes and both-runtime results are recorded in `SYNTHETIC_REVIEW_10.md`.
- Integrated the synthetically validated binder and recovered tests/driver. Default remains `legacy`; no borderless or LLM policy was enabled.
- The user-provided `C:/Users/Praka/Downloads/New Text Document.txt` was checked once and is empty (0 bytes), so it supplies no additional interrupted-command details.
- S3 identity and full-suite validation are the next prerequisites; no Phase 10 v2 gold measurement has been run at this checkpoint.

## Completed 2026-10-06

The preceding inventory and resumed-checkpoint statements describe their original times. Recovery,
integration and the authorized Phase 10 experiment are now complete. All four full pytest runs passed
180 tests; both environments passed the standalone 37-test pipeline script, 63-test experiment suite,
and 123-expectation binder regression. S3 passed before measurement.

The deterministic measurement completed on 2026-10-05. Two independent reviewers audited all 22 new
claim/cell bindings using crops and text layers: 21 agreed matches and one agreed semantic mismatch.
The frozen criteria yield **S1 FAIL, S2 FAIL, S3 PASS**. Default remains legacy; v2_llm was not run.
Implementation/test/driver commits are `7f55789`, `1cfea2c`, `c805cf4`; measurement/audit is `ad92c87`.
See `PHASE10_REPORT.md`, `results.json`, and `validation_10.json` for the complete results and remaining
bottleneck. No binder, gold, evaluator, preregistration or configuration changes followed measurement.
