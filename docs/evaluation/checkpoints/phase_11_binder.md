# Phase 11 checkpoint - guarded A4 and R5 complete, NO ENABLE

Date: 2026-10-07. Branch: exp/phase11-binder.
Binder implementation: 6536d5c883ea208dce18986b6d0e35153139b0d6 (unchanged here).

G1 reproduced subprocess.Popen(executable, args, cwd, env) as
(NoneType, str, str, dict). The old guard scanned environment keys. One helper-only
fix now inspects executable/argv, preserves socket and LLM-entry-point blocking,
and is inherited by Python children through PYTHONPATH. Required self-tests a-d
and additional guard checks all passed.

All 16 sequential A4 combinations passed: Python 3.10.18 and 3.13.6, legacy and
explicit v2, each with full pytest 243, standalone pipeline 37, experiment 63 and
frozen regression 123. Frozen lines 105/198 both return not_a_table_claim. The
frozen regression internally selects v2 under either invocation policy.

S3 PASS: 30/30 PDF gate records identical, 55 pairs/18 claims unchanged, newline
canary zero. The development-contaminated, machine-assisted, unvalidated regression
completed with unchanged scoring. S1 FAIL: 19 gold wrong-bind flags; 61 new
non-gold association occurrences have no new independent audit here. S2 FAIL:
3 lost gold units + 22 lost sweep associations. Cached product verified returns
remain 0/75 for each policy. NO ENABLE; default legacy stays unchanged.

Receipts:
- runs/phase11_binder/a4_guard_selftest.json
- runs/phase11_binder/a4_guard_resume_matrix.json
- runs/phase11_binder/r5_results.json
- runs/phase11_binder/r5_legacy.json and r5_v2.json (local ignored raw outputs)
- runs/phase11_binder/r5_console.txt
Full report and exact file paths: docs/evaluation/phase_11_binder.md.

Publication status AT THIS REPORT COMMIT: local only. The previous push was
rejected. One authorized push to origin exp/phase11-binder follows; its actual
result is in the final session reply. Do not infer success from this checkpoint.
No tag exists at report time. Tagging requires a successful branch push and no
execution STOP; a completion tag cannot imply release approval.

No src/, tests/, config or frozen Phase 10 file changed in this guard resumption.
The original STOP logs retain their hashes. Unrelated untracked directories remain
untouched. R1/R2/R3 commits: a0ed08d, d619db9, 6536d5c.

NEXT: stop after R5 publication handling. Do not start cell-selection evaluation,
end-to-end testing, Part B, or bottleneck fixes in this session. A later task must
have explicit scope; no further tuning is justified by this development set.
