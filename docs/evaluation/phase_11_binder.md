# Phase 11 Binder v2 - A4 resumption and F5 STOP

**Status: BLOCKED at F5. The original six experiment assertions now pass, but the frozen
regression has two status failures. No final tag, S3, development measurement or Part B.**

Date: 2026-10-06. Branch: `exp/phase11-binder`. Starting checkpoint: `731ef69`;
starting implementation: `7f0cef3`. Current implementation: `6cc9b5c3500bc68aa7aa6260fc30bdba8249f60c`.
No real LLM calls, pre-existing test edits, frozen artifact edits, or default changes occurred.
All research labels remain **machine-assisted, unvalidated**. The 55-pair/18-claim set is
**development-contaminated** and was not rerun after this STOP. No held-out evidence was produced.

## Baseline and preservation (F0-F2)

Both original logs remain byte-identical, SHA-256:
`55bcd9dc91fb3eb13aaf8e54384c3c4730c972ce0f982b2b5d9700c1e73da3b4`.
They are `runs/phase11_binder/logs/experiment_.venv_v2.txt` and
`runs/phase11_binder/logs/experiment_.venv-09a_v2.txt`.

The unchanged command `python -B -m tests.test_pipeline_units` ran under explicit v2
in the experiment directory of a detached temporary `phase10-binder-final` worktree,
outside this repository. Both runtimes reported **56 passed, 7 failed**; the worktree
was removed after measurement. The seventh failure was adv 4c, already resolved by
Classes A-D at the starting Phase 11 checkpoint.

| Original assertion line | Python 3.10.18 baseline | Python 3.13.6 baseline | Classification |
| --- | --- | --- | --- |
| 262 own-cell return | Failed | Failed | Already failing in Phase 10 |
| 266 cross-row reason | Failed | Failed | Already failing in Phase 10 |
| 277 absent metric column | Failed | Failed | Already failing in Phase 10 |
| 356 generic group probe A | Failed | Failed | Already failing in Phase 10 |
| 358 generic group probe B | Failed | Failed | Already failing in Phase 10 |
| 368 generic measurement/count phrase | Failed | Failed | Already failing in Phase 10 |

Exact observations/commands/hashes: `evidence/phase11_a4_baseline.json`.
The classification-only diagnosis was written before tests/fixes:
`diagnosis/phase11_a4_failures.md`. It identifies compound metric token matching,
quantity scope for absent values, and generic headings incorrectly promoted to quantities.

## Failing-first tests and fixes (F3-F4)

The new `tests/test_binder_v2_phase11_e.py` uses invented tables, quantities and values.
It was committed after **9 failed / 4 passed** was observed, before any fix. No
expectation in that file was revised afterwards. Three separate mechanism commits followed.

| Mechanism | Change | Focused result on each runtime |
| --- | --- | --- |
| E1 | Allow `@` between matched compound-label tokens; retain cutoff tokens | 131 passed, 7 not-yet-fixed E2/E3 cases deselected |
| E2 | Classify an absent value as prose only when a local quantity is represented | 134 passed, 4 not-yet-fixed E3 cases deselected |
| E3 | Generic model/result/score headings cannot supply measurable quantity links | 138 passed, including all 46 A-D checks and Class B boundaries |

The unchanged experiment suite also passed **63/63 under v2 on Python 3.10.18** after
E3. No source change was made to `gate.py` in this resumption. The E2 fix subsequently
failed the broader frozen regression below, so the implementation is not validated.

An initial focused run encountered Windows pytest temporary-directory permissions,
not an assertion failure. The guarded confirmation runs used reviewed escalation and
fresh temporary directories. Every test child had a process-wide network/Ollama guard;
logs record its blocked-loopback self-test. Mocked judge tests did not make real calls.

## Full A4 matrix and exact STOP (F5)

The sequential matrix stopped at the first failing command, as required.

| Runtime / invocation policy | Suite | Result |
| --- | --- | --- |
| 3.10.18 / legacy | Full pytest | 239 passed |
| 3.10.18 / legacy | Standalone `tests/test_pipeline.py` | 37 passed |
| 3.10.18 / legacy | Experiment units | 63 passed |
| 3.10.18 / legacy | Frozen `binder_10/regress.py` | **121 passed, 2 failed: STOP** |
| Remaining 12 runtime/policy/suite combinations | Full matrix | Not run after STOP |

The frozen regression sets `RGPT_BINDER_POLICY=v2` internally at line 20, including
when invoked with legacy in the environment. Neither that script nor its policy
selection was modified; an explicit v2 invocation was not reached in this matrix.

| Frozen expectation | Original claim | Expected | Actual |
| --- | --- | --- | --- |
| `src/evaluation/binder_10/regress.py:105`, B threshold alone | Our method achieves above 0.90. | `not_a_table_claim` | `not_bindable` |
| `src/evaluation/binder_10/regress.py:198`, B delta never binds | Ours improves the Dice by 0.84 over UNet. | `not_a_table_claim` | `not_bindable` |

E2's quantity-scope branch excludes threshold/delta mentions. With no required equality
candidate, those claims now take `not_bindable`. This is a newly introduced status
regression, not evidence that the immutable expectations are irreconcilable. Both
claims remain unbound. No additional fix, rollback, test rerun or measurement followed
the STOP. The two generic/absent-quantity cases still require `not_bindable`; the two
frozen non-equality cases require their original `not_a_table_claim` classification.

The child failure log and matrix JSON were saved before the parent hit a console
UnicodeEncodeError while printing the failure tail. That display error did not hide
or change the recorded child results. Durable records and exact new-file inventory:
`evidence/phase11_a4_validation.json`.

## S1/S2/S3, measurement and Part B (F6-F8)

| Criterion | Current Phase 11 resumption | Frozen Phase 10 history |
| --- | --- | --- |
| S1 zero wrong binds | NOT EVALUATED after F5 STOP | FAIL |
| S2 zero verified binds lost | NOT EVALUATED after F5 STOP | FAIL |
| S3 legacy identity | NOT RUN after F5 STOP | PASS |

The development-contaminated, machine-assisted, unvalidated 55-pair/18-claim
measurement was not run. Synthetic test success is not substituted for it or for
held-out evidence. No `phase11-binder-final` tag was created and no Part B branch or
cached replay was started. There is no new funnel or newly measured bottleneck ranking.
The later request for end-to-end testing and cheap fixes remains downstream of the
explicit F5 STOP. A future Part B remains **CACHED REPLAY - NOT A FRESH PRODUCTION RUN**
with network/LLM calls blocked, missing records disclosed and no enable recommendation.

## Preservation and handoff

`git diff phase10-binder-final -- src/evaluation configs` is empty. The only test diff
from checkpoint `731ef69` is the newly added Class E file. The two original failure
logs were rehashed and match. Defaults remain legacy / table_value_guard / borderless
off. Unrelated untracked `docs/diagnosis/`, `out/`, and `src/evaluation/candidate_gold/`
remain untouched. The temporary baseline worktree was removed.

Next work requires continuation past the two frozen regression failures, with all
expectations preserved. Diagnose the non-equality classification boundary without
changing the evaluator or tests, then resume F5 only under that authorization. The
stopped state is committed/pushed on `exp/phase11-binder`; no success tag is warranted.

## New commit ledger

| Full hash | Work |
| --- | --- |
| `5ef7bc89f03623e6991236b6605237157021827d` | Read-only baseline evidence and mechanism diagnosis |
| `089aa6202ffbc01c8b34cb17cb4870695b6e44f8` | 13 synthetic tests committed failing: 9 failed, 4 passed |
| `0184ebb881b03decaa7fd0f1b9d7165e4b101f1c` | E1: preserve compound metric separators and cutoff tokens |
| `198c9225d506b2eee04e3ac2df93e605ed18da15` | E2: require quantity scope before absent-value classification |
| `6cc9b5c3500bc68aa7aa6260fc30bdba8249f60c` | E3: exclude generic group headings from quantity links |

The final report/checkpoint commit hash is supplied in the reply; a commit cannot
embed its own hash. Historical A-D commits remain unchanged:

| Full hash | Work |
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

## Exact absolute paths of every new resumption file

Committed evidence/test files and ignored local helpers, receipts and logs are all
listed here. SHA-256 values and persistence are in `phase11_a4_validation.json`.
Existing modified files are `src/evidence/binder_v2.py`, this report,
`docs/evaluation/PROGRESS.md`, `docs/evaluation/checkpoints/phase_11_binder.md`, and
`BLOCKED.md`. Prior STOP logs and evidence files remain unchanged.

```text
C:\Users\Praka\Downloads\researchgpt-pipeline\docs\evaluation\evidence\phase11_a4_baseline.json
C:\Users\Praka\Downloads\researchgpt-pipeline\docs\evaluation\diagnosis\phase11_a4_failures.md
C:\Users\Praka\Downloads\researchgpt-pipeline\tests\test_binder_v2_phase11_e.py
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e1_after_focused_.venv_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e1_confirmed_focused_.venv-09a_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e1_confirmed_focused_.venv_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e2_after_focused_.venv-09a_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e2_after_focused_.venv_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e3_after_experiment_.venv_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e3_after_focused_.venv-09a_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e3_after_focused_.venv_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_e_before_synthetic_.venv_v2.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_final_matrix.json
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_guard\sitecustomize.py
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_matrix.py
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_report.py
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_run.py
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_baseline_experiment_.venv-09a_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_baseline_experiment_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e1_after_focused_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e1_confirmed_focused_.venv-09a_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e1_confirmed_focused_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e1_verified_focused_.venv-09a_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e1_verified_focused_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e2_after_focused_.venv-09a_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e2_after_focused_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e3_after_experiment_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e3_after_focused_.venv-09a_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e3_after_focused_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_e_before_synthetic_.venv_v2.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_final_experiment_.venv_legacy.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_final_full_.venv_legacy.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_final_pipeline_.venv_legacy.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\logs\a4_final_regression_.venv_legacy.txt
C:\Users\Praka\Downloads\researchgpt-pipeline\docs\evaluation\evidence\phase11_a4_validation.json
```

Earlier A-D scope, mechanism descriptions and validation receipts remain in checkpoint
commit `731ef69` and the unchanged `preregistration/phase_11_scope.md`,
`diagnosis/phase11_failure_classes.md` and `evidence/phase11_class_*` artifacts.
