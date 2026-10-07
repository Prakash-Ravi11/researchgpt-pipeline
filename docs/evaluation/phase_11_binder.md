# Phase 11 Binder v2 - guarded A4 and development regression complete

**R4 passed all 16 combinations. R5 measurement completed. S1 FAIL / S2 FAIL / S3 PASS.
Legacy remains default. No end-to-end run, new cell-selection evaluation or bottleneck fixes.**

Report date: 2026-10-07. Branch: `exp/phase11-binder`. This guard-only resumption
started at `6536d5c883ea208dce18986b6d0e35153139b0d6`; that remains the binder
implementation commit. No `src/`, `tests/`, evaluator, frozen artifact or config
was changed in this resumption.

## Publication status

At this report commit the work is **local only**. The earlier branch push was
rejected by automatic approval review and did not run. The previous report's
?committed/pushed? wording was incorrect and is replaced here.

One authorized `git push origin exp/phase11-binder` follows this commit. Its
destination, read from local Git configuration, is
`https://github.com/Prakash-Ravi11/researchgpt-pipeline.git`. The final session
reply records the actual result; this report does not predict success. No final
tag exists at report time. A tag requires completed R4/S3/regression without a
STOP and a successful branch push; it cannot imply release approval.

## G1-G3: guard diagnosis, one fix and verification

The failing audit event was `subprocess.Popen(executable, args, cwd, env)`.
Observed Windows types were `(NoneType, str, str, dict)`: no separate executable,
a Python command-line string, the repository cwd, and an explicit environment
mapping. The old guard searched `str(args)`, so `OLLAMA_HOST` in that mapping
rejected a harmless Python subprocess. Environment values were not logged.

Only `runs/phase11_binder/a4_guard/sitecustomize.py` was fixed, in one attempt.
Process-event inspection now takes executable/argv only. It does not inspect cwd
or environment. It handles Popen, exec, posix_spawn, spawn and system argument
shapes and blocks named network/LLM command-line clients. Python children inherit
the guard through PYTHONPATH. Socket connections/DNS/sends remain blocked,
including 127.0.0.1:11434; non-loopback binds are blocked. Import hooks block
the repository's real Ollama call functions and known Ollama/OpenAI/Anthropic
client entry points. Mocked judge tests and cache-only replay remain available.

| Required guard self-test | Result |
| --- | --- |
| a. External connection canary raises | PASS |
| b. Localhost:11434 canary raises | PASS |
| c. Python child with explicit OLLAMA_HOST/API-key-like environment keys succeeds | PASS |
| d. Child inherits guard and its connection canary raises | PASS |

CLI-event, ignored-cwd/environment, non-loopback-bind, loopback-bind and real
repository LLM-entry-point checks also passed. The exact event shape, exceptions,
sentinel key names, child output and helper SHA-256 are in
`runs/phase11_binder/a4_guard_selftest.json`. No actual LLM/network call occurred.

## R1-R3 history retained, not changed in this resumption

E2 `198c922` conflated threshold/delta-only claims with ordinary equality claims
whose quantity is absent. Mechanism-only diagnosis was committed as `a0ed08d`.
Four invented tests were appended without editing existing expectations, then
committed failing as `d619db9` (two failures, two passing controls). The single
R3 fix `6536d5c` restores `not_a_table_claim` when every numeric mention is a
threshold or delta, leaving the ordinary/mixed-claim quantity-scope path intact.
Its 142 focused checks passed on both runtimes.

| Frozen assertion | Expected | Actual, all four R4 regression invocations |
| --- | --- | --- |
| `regress.py:105`, B threshold alone | `not_a_table_claim` | `not_a_table_claim`, PASS |
| `regress.py:198`, B delta never binds | `not_a_table_claim` | `not_a_table_claim`, PASS |

The absent-metric and generic-count controls remain `not_bindable`. All E1-E3,
Classes A-D and Class B boundary tests are included in the full A4 runs.

## R4: complete sequential matrix

Every invocation used PYTHONIOENCODING=utf-8, disabled bytecode/cache writing,
and the blocked guard. Pytest basetemp and temporary regression cache fixtures
were confined to `runs/phase11_binder/` and removed after each combination.
The matrix ran sequentially and encountered no failure.

| Python | Invocation policy | Suite | Result |
| --- | --- | --- | --- |
| 3.10.18 | legacy | full_pytest | PASS, 243 checks |
| 3.10.18 | legacy | pipeline | PASS, 37 checks |
| 3.10.18 | legacy | experiment | PASS, 63 checks |
| 3.10.18 | legacy | regress | PASS, 123 checks |
| 3.10.18 | v2 | full_pytest | PASS, 243 checks |
| 3.10.18 | v2 | pipeline | PASS, 37 checks |
| 3.10.18 | v2 | experiment | PASS, 63 checks |
| 3.10.18 | v2 | regress | PASS, 123 checks |
| 3.13.6 | legacy | full_pytest | PASS, 243 checks |
| 3.13.6 | legacy | pipeline | PASS, 37 checks |
| 3.13.6 | legacy | experiment | PASS, 63 checks |
| 3.13.6 | legacy | regress | PASS, 123 checks |
| 3.13.6 | v2 | full_pytest | PASS, 243 checks |
| 3.13.6 | v2 | pipeline | PASS, 37 checks |
| 3.13.6 | v2 | experiment | PASS, 63 checks |
| 3.13.6 | v2 | regress | PASS, 123 checks |

Full pytest scope: `tests/ src/evaluation/bottleneck_diagnosis/`, excluding
`tests/test_pipeline.py` because it runs separately. The unchanged frozen
`regress.py` selects v2 internally at line 20 even when invoked with legacy in
the environment. Both environment invocations were executed on both runtimes;
no policy was forced to hide v2 behavior. Exact commands, complete child output,
guard proof, hashes and both frozen assertion receipts are in
`runs/phase11_binder/a4_guard_resume_matrix.json`.

## R5: development-contaminated, machine-assisted, unvalidated

S3 imported the unchanged `validate_10.py.identity()` with RESULTS redirected to
`runs/phase11_binder/r5_results.json`. It compared current legacy output with the
frozen starting implementation: **30/30 PDF gate records identical, no differences
for 55 pairs or 18 claims, newline canary zero**.

Then unchanged `load_rep`, `run_arm`, `compare` and `summary` evaluated legacy
and deterministic v2 on R-prod, R-eval and the existing R-oracle subset. The
55-pair/18-claim regression and its frozen sweep/cached-product comparisons used
existing records. No fresh extraction, LLM arm, independent new PDF audit,
held-out construction, end-to-end pipeline or new cell-selection study ran.
No evaluator or reconstruction criterion was changed.

**The following regression counts are development-contaminated, machine-assisted,
unvalidated.** Bound-correct and wrong-bind flags can overlap for a multi-cell
claim under the unchanged scorer; they are not disjoint precision categories.

| Representation | Policy | Unit | Total | Bound | Bound-correct | Wrong-bind flags | Returned with correct bind |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-prod | legacy | pairs | 55 | 4 | 4 | 0 | 4 |
| R-prod | legacy | claims | 18 | 2 | 2 | 0 | 2 |
| R-prod | v2 | pairs | 55 | 31 | 23 | 8 | 5 |
| R-prod | v2 | claims | 18 | 3 | 3 | 1 | 2 |
| R-eval | legacy | pairs | 55 | 7 | 6 | 1 | 4 |
| R-eval | legacy | claims | 18 | 5 | 4 | 1 | 2 |
| R-eval | v2 | pairs | 55 | 39 | 30 | 9 | 5 |
| R-eval | v2 | claims | 18 | 5 | 5 | 1 | 2 |
| R-oracle | legacy | pairs | 12 | 6 | 6 | 0 | 0 |
| R-oracle | legacy | claims | 3 | 0 | 0 | 0 | 0 |
| R-oracle | v2 | pairs | 12 | 12 | 12 | 0 | 0 |
| R-oracle | v2 | claims | 3 | 1 | 1 | 0 | 0 |

**Development-contaminated, machine-assisted, unvalidated comparisons with legacy:**

| Representation | S1 gold wrong-bind flags | S2 lost gold units | S2 lost sweep associations | New non-gold associations |
| --- | --- | --- | --- | --- |
| R-prod | 9 | 1 | 10 | 25 |
| R-eval | 10 | 2 | 12 | 36 |
| R-oracle | 0 | 0 | 0 | 0 |

S1 remains FAIL on **19 gold-unit wrong-binding flags**. 17 flags have no
reconstructed gold target under the frozen scorer; those conservative failures
are retained, not reinterpreted as passes. The 61 new non-gold association
occurrences across representations received no new independent PDF audit here.
They remain unvalidated and cannot establish S1 safety.

S2 remains FAIL on **3 lost gold claim units plus 22 lost sweep associations**,
25 occurrences across representations; overlapping claims are not independent
samples. Exact identities, claims and cell associations are preserved in
`r5_results.json`. No tuning or corrective patch followed the measurement.

The cached product comparison still has **0/75 returned-with-verified-bind items**
for both policies. This is part of the frozen deterministic regression, not a
fresh production run or a new bottleneck investigation.

| Criterion | Current verdict | Evidence |
| --- | --- | --- |
| S1 zero wrong binds | FAIL | 9 R-prod / 10 R-eval gold flags; new associations unvalidated |
| S2 zero verified binds lost | FAIL | R-prod 1 gold + 10 sweep; R-eval 2 gold + 12 sweep |
| S3 legacy identity | PASS | 30/30 PDFs; 55 pairs/18 claims identical; newline canary 0 |

**NO ENABLE.** Successful unit tests and completed development measurement do not
replace held-out evidence. Legacy / table_value_guard / borderless off remain the
defaults. R5 execution itself completed with exit code zero; failed S1/S2 release
criteria are reported plainly rather than silently treated as test success.

## Preservation and session boundary

The original two failing-before experiment logs retain SHA-256
`55bcd9dc91fb3eb13aaf8e54384c3c4730c972ce0f982b2b5d9700c1e73da3b4`.
The F1 baseline remains unchanged: all six original experiment assertions already
failed at Phase 10 on both runtimes. See `evidence/phase11_a4_baseline.json`.

`git diff 6536d5c -- src tests configs experiments/document_evidence_pipeline/tests`
and `git diff phase10-binder-final -- src/evaluation configs` are empty.
Unrelated untracked docs/diagnosis, out and src/evaluation/candidate_gold remain
untouched. The session stops after R5 publication handling. No Part B branch,
end-to-end replay, bottleneck ranking or bottleneck fix is authorized here.

## Every new or changed file in this guard resumption

Raw legacy/v2 arm outputs remain local ignored receipts. The helper, self-test,
matrix, results summary, console receipt and four documentation files are included
in the report commit. File hashes and this inventory are in `r5_results.json`.

```text
changed: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_guard\sitecustomize.py
new: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_guard_selftest.json
new: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\a4_guard_resume_matrix.json
new: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\r5_results.json
new: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\r5_legacy.json
new: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\r5_v2.json
new: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\r5_console.txt
changed: C:\Users\Praka\Downloads\researchgpt-pipeline\docs\evaluation\phase_11_binder.md
changed: C:\Users\Praka\Downloads\researchgpt-pipeline\docs\evaluation\PROGRESS.md
changed: C:\Users\Praka\Downloads\researchgpt-pipeline\docs\evaluation\checkpoints\phase_11_binder.md
changed: C:\Users\Praka\Downloads\researchgpt-pipeline\BLOCKED.md
```

## R1-R3 commit ledger

| Full hash | Work |
| --- | --- |
| `a0ed08db53d89e475a98eb5883a543069c4daa33` | Diagnose E2 threshold/delta status regression |
| `d619db9198dcc3e438a65e5e37209cdd9b8ac3a3` | Append failing-first non-equality tests and controls |
| `6536d5c883ea208dce18986b6d0e35153139b0d6` | Single R3 fix |

The guard/report commit hash is supplied in the final reply; the commit cannot
contain its own hash. Earlier implementation and failing-first history follows.

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
