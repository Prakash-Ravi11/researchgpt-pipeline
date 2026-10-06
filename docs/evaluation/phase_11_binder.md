# Phase 11 Binder v2 - implementation, validation STOP and full handoff

**Status: implementation of Classes A-D is committed; A4 is BLOCKED by six pre-existing experiment-suite failures under v2 in each Python runtime. Phase 11 is not complete. Do not enable v2. Part B has not started.**

This report records the completed work and exact remaining blocker. No pre-existing test or frozen Phase 10 artifact was modified. All historical evaluation/classification labels remain **machine-assisted, unvalidated**, and the old evaluation set is **development-contaminated**.

## Repository and constraints

- Repository: `C:/Users/Praka/Downloads/researchgpt-pipeline`.
- Current branch: `exp/phase11-binder`, created from `050f8de76b8eabf04bb46fd863beee152a760975`.
- Phase 10 was confirmed pushed; annotated tag `phase10-binder-final` was created and pushed at that commit.
- All required Phase 10 commits were confirmed: `7f55789`, `1cfea2c`, `c805cf4`, `ad92c87`, `050f8de`.
- The final Phase 11 implementation commit is `7f0cef3399833362763f30a5fc51c2be58fd55ec`. There is no remaining uncommitted binder source patch.
- Defaults remain `binder_policy=legacy`, `fallthrough_policy=table_value_guard`, `borderless_policy=off`. No real LLM or v2_llm run occurred. No default-branch merge.
- The user approved **cached replay with all real LLM calls blocked** for eventual Part B. It must not be represented as a fresh extraction run. Missing records must be disclosed.
- Unrelated untracked `docs/diagnosis/`, `out/`, `src/evaluation/candidate_gold/` were not touched.
- The early automatic-approval usage-limit error was resolved by retrying through the same check after its stated retry time. It is not the current blocker.

## Work completed and remaining

| Step | Result |
| --- | --- |
| A0 state, Phase 10 push/tag, Phase 11 branch | Complete |
| A1 scope committed alone before code | Complete, including the separate user-authorized Class B amendment |
| A2 read-only violation classification | Complete: 47 inventory rows |
| A3 Classes A-D, failing tests before fixes | Implemented and committed; 46 new synthetic checks |
| A4 full pytest | 226 passed in all four runtime/policy combinations |
| A4 standalone pipeline | 37 passed in all four combinations |
| A4 experiment suite, legacy | 63 passed in each runtime |
| A4 experiment suite, v2 | **57 passed, 6 failed in each runtime: STOP** |
| A4 frozen binder regression | 123 expectations pass in each runtime under the legacy invocation; the explicit v2 invocation was not reached after the experiment STOP |
| A4 new S3 identity / development measurement | Not run after STOP |
| A5 successful completion/tag | Not complete; only a blocked report/checkpoint is delivered |
| Part B replay/funnel/upper bounds/ranking | Not started because Part A did not complete |

No `phase11-binder-final` tag or Part B branch exists. The Phase 11 work/checkpoint branch is pushed as incomplete work, not marked final.

## Scope, classification and held-out evidence

The scope was committed before code. It requires general synthetic evidence, no evaluated-ID tuning, unchanged S1/S2/S3 definitions, unchanged frozen artifacts, and a new held-out primary evaluation later. The 55-pair/18-claim set may only be used as a development-contaminated regression check. It was not re-run in this attempt because A4 stopped first.

The registered future held-out design is 12 new papers / 60 claims: 40 positive claim/cell cases and 20 numeric near-miss controls. It excludes Phase 10 and development papers/versions, freezes PDF hashes and strata before prediction, enumerates all required target cells, and uses blinded independent readings with unresolved disagreements explicit. Labels remain machine-assisted/unvalidated pending owner validation. **The held-out set was not built**, as requested. See `preregistration/phase_11_scope.md`.

The read-only diagnosis inventories 19 gold S1 occurrences, 5 gold S2 occurrences, 22 lost sweep associations, and one distinct audited S1 mismatch. These overlap units/representations. All 17 canonical-pair S1 occurrences have absent reconstructed gold targets and remain **other**, without changed scoring. Two real-claim occurrences have extra cells outside the reconstructed target subset, with reconstruction caveats. The independently confirmed quantity/subject mismatch motivates Class A. C/D classifications are hypotheses requiring synthetic proof, not automatic instructions to restore old bindings. Full row-level evidence and hashes: `diagnosis/phase11_failure_classes.md`.

## Classes and failing-before evidence

| Class | New checks | Before | After focused checks, each runtime | Committed mechanism |
| --- | --- | --- | --- | --- |
| A | 15 | 5 failed, 10 passed | 94 passed including original/recovery tests | Local setting type must agree with chosen quantity source; raw verifier rebuilds links |
| B original | 6 | 4 failed, 2 passed | Initial candidate: 98 passed, 2 old failures; STOP recorded | Over-broad absent-value requirement was rejected |
| B amended | 8 | New boundary: 1 failed, 7 passed against the rejected candidate | 102 passed | Independent quantity support, strong subject evidence, existing required-value semantics |
| C | 15 | 4 failed, 11 passed | 117 passed | Exact bracketed ownership markers and percent-before-uncertainty parsing |
| D | 8 | 2 failed, 6 passed | 125 passed | Guarded legacy preservation with fresh raw checks and complete required coverage |

The focused totals include 19 original + 60 recovery tests and accumulated Phase 11 tests. The full 226 pytest total is the prior 180 plus 46 Phase 11 checks. Existing tests were not edited. Before/after JSON records under `docs/evaluation/evidence/` include source hashes, log paths and observed failures.

### A - equal numbers do not prove equal quantities

Synthetic claims previously bound a confidence threshold, learning rate, dropout probability or batch size to an equal-valued metric cell. The raw verifier also accepted the invalid threshold case. Per-value local type checks now require the cell's quantity source to agree, while nearer explicit measured quantities supersede earlier setting cues. Positive metric/setting cases and wrong-model/group controls remain covered. Code: `src/evidence/binder_v2.py:553` and the `quantity_type` conflict check.

### B - explicit user decision and S1/S2 trade-off

The first candidate required a number absent from every cell, which broke two pre-existing tests. Work stopped. The user explicitly selected Option 1: **preserve the existing required-value rule and revise only the NEW Class B scope/tests**. The amendment was committed separately as `9a8fc9a` before further code. Only the new tests changed in `cd53e13`; their original failing-first history remains in `d32f367`.

Completeness applies only to table-measurable values: values present in candidate cells of the claim's tables. A value matching no cell is non-table/text-only and does not block a supported bind. The paired boundary test keeps a supported bind when the second value is absent everywhere, and requires `partial_binding` when that second value instead matches a conflicting row. Extra-cell negative controls remain. The over-broad absent-value logic was removed; the original supported-bind and prose-only tests pass unchanged.

**Trade-off:** a value in no table cell supplies no table binding, so that wrong text-only value cannot itself cause a wrong cell selection. It also cannot be verified by the table. A supported table binding does **not** verify every text-only statement in the claim. This preserves existing S2 behavior while S1 still governs every selected cell and table-measurable value.

The historical rejected patch and its two-runtime failures are preserved as `phase11_class_b_uncommitted.patch` and `phase11_class_b_blocked.json`. The filename describes its state at the earlier STOP; it is an archival rejected patch, not the current working tree.

### C - formatting without erasing semantics

Own-method markers exactly inside `(Proposed)`, `[Proposed]` or `(Ours)` survive label-core cleanup. Meaningful model variants remain excluded. A percent sign before `±` is parsed as part of the same numeric structure. Positive controls cover `Proposed Method`, `Ours`, cited labels, arrow headers, significance marks, hierarchy and split tokens; negative controls preserve variant, cohort, uncertainty and unit conflicts. Code: `src/evidence/binder_v2.py:138` and `_C_PM`.

### D - preservation is conditional, not a bypass

The original legacy body now has a direct internal entry point at `src/evidence/gate.py:438`, so fallback does not mutate the policy environment or recurse through routing. The wrapper at `src/evidence/binder_v2.py:1233` only considers conservative no-bind outcomes with no recorded semantic conflict. It re-reads raw evidence, reconstructs required values and links, requires exactly one required value, rejects ambiguity, requires the unique eligible cell to equal the legacy cell, and re-runs the raw verifier. Multiple required values, partial coverage, wrong quantity, wrong table, ownership conflicts and ambiguity are not rescued. Text-only values remain outside the required set.

The positive synthetic reproduction deliberately injects an omitted initial candidate index, while keeping attached evidence and fresh verification intact. This tests a preservation failure path; it is **not** evidence of a naturally occurring historical S2 recovery. Negative controls prove that legacy-wrong numeric/quantity and table choices stay rejected even with that candidate omission. No historical gain is claimed without measurement.

## Full A4 results and exact current STOP

| Suite | Python 3.10 legacy | Python 3.10 v2 | Python 3.13 legacy | Python 3.13 v2 |
| --- | --- | --- | --- | --- |
| Full pytest | 226 pass | 226 pass | 226 pass | 226 pass |
| Standalone pipeline | 37 pass | 37 pass | 37 pass | 37 pass |
| Experiment units | 63 pass | **57 pass / 6 fail** | 63 pass | **57 pass / 6 fail** |
| Frozen binder regression | 123 pass | Not reached | 123 pass | Not reached |

The legacy-invoked frozen regression itself directly exercises v2 internally. Its explicit v2-policy invocation was not reached because the per-policy validation runner stopped immediately at the experiment failure. The two independently running legacy-policy validations completed successfully. No validation was rerun or implementation changed after observing this STOP.

Commands: `python -B -m pytest -p no:cacheprovider tests/ src/evaluation/bottleneck_diagnosis/ --ignore=tests/test_pipeline.py -q --tb=short`; `python -B tests/test_pipeline.py`; `python -B -m tests.test_pipeline_units` from `experiments/document_evidence_pipeline`; and `python -B src/evaluation/binder_10/regress.py`. Each invocation selects its Python runtime and policy, disables bytecode and uses UTF-8 output. Pytest plugin autoload was disabled. Exact standalone commands, working directories, output paths, return codes and hashes are in `evidence/phase11_validation.json` and the local execution records.

All six current failures occur in the unchanged `experiments/document_evidence_pipeline/tests/test_pipeline_units.py`:

| Line | Assertion | Observed v2 behavior |
| --- | --- | --- |
| 262 | Own-cell nDCG@5 must bind and RETURN | `wrong_cell`, `name_unexplained`; final `ABSTAINED` |
| 266 | Cross-row nDCG@5 must produce `binding_wrong_cell` | `not_bindable`; gate reason `table_value_unbound` |
| 277 | Metric absent from columns must be `not_bindable` | `not_a_table_claim` |
| 356 | Generic performance-metrics probe A must be `not_bindable` | `wrong_cell`, name/subject conflicts |
| 358 | Generic performance-metrics probe B must be `not_bindable` | `wrong_cell`, name/subject conflicts |
| 368 | Generic count probe must be `not_bindable` | `not_a_table_claim` |

The own-cell case is a supported-return failure, not merely a status-name difference. The other cases also fail their existing expectations and cannot be silently waived. It is not established whether each failure predates Phase 11, because no extra baseline rerun was performed after the STOP. Earlier Phase 10 experiment checks were not a documented four-way policy matrix. No test expectations were changed and no legacy-only forcing was inserted to conceal these results.

The user's instruction is explicit: **"If any pre-existing test fails, STOP and report. No test edits to make them pass."** This is the current stopping boundary. The earlier Class B contract STOP was resolved by the user's amendment; it is not the current blocker.

## Part A S1/S2/S3 verdict and default decision

| Criterion | Phase 11 | Frozen Phase 10 historical result |
| --- | --- | --- |
| S1 zero wrong binds | NOT EVALUATED after A4 STOP | FAIL |
| S2 zero verified binds lost | NOT EVALUATED after A4 STOP | FAIL |
| S3 30-PDF identity | NOT RE-RUN after A4 STOP | PASS: 30/30, 55 pairs / 18 claims identical, newline canary 0 |

**NO ENABLE.** All four classes having focused tests does not establish release safety. Full A4 validation has failures; new S3/regression measurement and held-out primary evidence remain absent. Phase 10 gold, scorer, results, preregistration, audit artifacts, earlier evaluation packages and configs have no diff from `phase10-binder-final`. All pre-existing tests are unchanged. Defaults remain legacy/guard-on/borderless-off.

## Part B funnel and top three historical bottlenecks

Part B was not started. The approved cached replay, stage funnel, isolated-stage upper bounds and new ranked bottleneck map remain undone. No new measured count is fabricated:

| Requested stage | Legacy remaining / lost | v2 remaining / lost |
| --- | --- | --- |
| 1. Claim detected in text | Not measured | Not measured |
| 2. Reaches gate | Not measured | Not measured |
| 3. Table/gold cell represented | Not measured | Not measured |
| 4. Candidate recall | Not measured | Not measured |
| 5. Correct binding chosen | Not measured | Not measured |
| 6. Raw verification passes | Not measured | Not measured |
| 7. Returned verified bind | Not measured | Not measured |

The following are **historical Phase 10 observations only**, not a new Part B funnel or isolated-stage estimate:

1. Product claim availability: 15/18 gold claims do not reach the gate. Extraction versus claim-detection attribution still needs the requested trace.
2. Production table representation: 11/18 real claims lack reconstructed gold cells in R-prod. Reconstruction/scoring qualifications remain explicit.
3. Binding precision/preservation: one independently confirmed new wrong binding; one lost R-prod correct claim plus nine lost sweep associations. The recorded real-claim stage map has three linking and one ranking failure.

Counts overlap and use different units; they are not additive. Product verified bindings were zero across 75 items. All these historical labels are machine-assisted, unvalidated and development-contaminated. They are not a recommendation to enable any policy.

## Commit ledger

Every Phase 11 implementation/test/scope commit before this report is listed below. The final report commit cannot contain its own hash; it is supplied in the final reply and by `git log -1 -- docs/evaluation/phase_11_binder.md`.

| Full commit hash | Work |
| --- | --- |
| `537658dd17e7b7d3516e9e3f72f634ec14036cef` | preregister Phase 11 binder safety and preservation scope |
| `5bd4c0f448061eb61e21f305b85b32bdc121fbb2` | classify frozen Phase 10 safety and preservation violations |
| `ad5bc9e7f9eb1ea6c52ef0a84009d69d2e5148a7` | test Phase 11 class A quantity-type failures before fixing |
| `d64cd91cf647c16a00dacf73a5240a2b9b02434b` | reject class A setting-to-metric bindings through raw quantity checks |
| `d32f367e6901c3c56b567aa341cde71e98dec3e9` | test Phase 11 class B independent-value and completeness failures |
| `9a8fc9ab42bc1162b65d560971f174be07d0d7bd` | amend Class B scope to preserve existing table-measurable value rule |
| `cd53e134805c3aff8b5f785aa623d723a6f2b64f` | revise only new Class B tests: absent values keep binds; conflicting candidates still abstain to preserve S2 |
| `176de61e2973824cbb9a9964076abf9e12aca9ac` | bind Class B values independently while preserving absent-value semantics |
| `c3e77ba7e11a406e35ad7458dece429d9a3e1da6` | test Class C bracketed ownership and percent uncertainty failures |
| `85bee812c57879b6cca31a8019b60bb972150f51` | normalize Class C ownership decorations and percent uncertainty |
| `2415bb9c7e14da4f1306dc58ab32c567280181fe` | test Class D verified preservation and legacy-wrong vetoes first |
| `7f0cef3399833362763f30a5fc51c2be58fd55ec` | preserve only raw-verified unambiguous legacy binds without semantic override |

## Exact absolute paths of all new files

This inventory includes durable task files plus local ignored commands/logs. Existing files modified are `src/evidence/binder_v2.py`, `src/evidence/gate.py`, `docs/evaluation/PROGRESS.md`, and `BLOCKED.md`. No unrelated untracked file is included. File hashes and persistence status are also recorded in `evidence/phase11_artifact_manifest.json`.

- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/checkpoints/phase_11_binder.md`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/diagnosis/phase11_failure_classes.md`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_artifact_manifest.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_a_after.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_a_before.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_b_after.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_b_amended_before.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_b_before.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_b_blocked.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_b_uncommitted.patch`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_c_after.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_c_before.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_d_after.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_class_d_before.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/evidence/phase11_validation.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/phase_11_binder.md`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/docs/evaluation/preregistration/phase_11_scope.md`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/checks_.venv-09a_legacy.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/checks_.venv-09a_v2.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/checks_.venv_legacy.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/checks_.venv_v2.json`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_a_after_.venv-09a.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_a_after_.venv.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_a_after_310.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_a_before.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_b_after_.venv-09a.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_b_after_.venv.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_b_amended_before.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_b_before.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_b_final_.venv-09a.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_b_final_.venv.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_c_after_.venv-09a.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_c_after_.venv.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_c_before.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_d_after_.venv-09a.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_d_after_.venv.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/class_d_before.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/experiment_.venv-09a_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/experiment_.venv-09a_v2.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/experiment_.venv_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/experiment_.venv_v2.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/full_.venv-09a_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/full_.venv-09a_v2.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/full_.venv_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/full_.venv_v2.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/pipeline_.venv-09a_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/pipeline_.venv-09a_v2.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/pipeline_.venv_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/pipeline_.venv_v2.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/regression_.venv-09a_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/logs/regression_.venv_legacy.txt`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/record_evidence.py`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/run_checks.py`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/runs/phase11_binder/write_report.py`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/tests/test_binder_v2_phase11_a.py`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/tests/test_binder_v2_phase11_b.py`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/tests/test_binder_v2_phase11_c.py`
- `C:/Users/Praka/Downloads/researchgpt-pipeline/tests/test_binder_v2_phase11_d.py`

## Resume boundary

The Class B decision is settled; do not reopen it or modify pre-existing tests. The current blocker is the six A4 experiment failures. A resumed task must explicitly authorize diagnosis/fixes of those failures while retaining all original expectations. Preserve their current logs as failing-before evidence, use general synthetic causes, and repeat only the checks justified by changes. Keep all frozen artifacts untouched.

Once all A4 requirements pass, run S3 and the development-contaminated regression with output redirected away from frozen Phase 10 files. Record S1/S2/S3 without substituting synthetic success for primary held-out evidence. Only then complete/push/tag Part A and start the approved cached Part B replay. Do not create a final-success tag or manufacture the missing Part B funnel now.
