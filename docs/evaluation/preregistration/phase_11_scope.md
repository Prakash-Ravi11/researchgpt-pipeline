# Phase 11 scope: general Binder v2 safety and preservation fixes

Recorded before implementation on `exp/phase11-binder`, based on
`phase10-binder-final` (`050f8de76b8eabf04bb46fd863beee152a760975`).

## Goal and immutable boundary

Remove the S1 wrong-binding and S2 lost-verified-binding blockers through general mechanisms.
The frozen Phase 10 gold, evaluator, scoring, results, preregistration and audit artifacts remain
unchanged. Every tracked file under `src/evaluation/binder_10/`, the earlier gold/evaluation packages,
and configurations is frozen. Preserve their bytes and Git diff identity to the starting tag.

No tuning against evaluated identifiers (PF0xx, C0xx), paper IDs, or exact evaluated claims.
Code and new synthetic tests use invented subjects, values and contexts only. Historical IDs may
appear in the read-only diagnosis for traceability, never as implementation conditions or fixtures.
No new dependency, real LLM call, or v2_llm run. Defaults remain `binder_policy=legacy`,
`fallthrough_policy=table_value_guard`, `borderless_policy=off`. No default-branch merge.
Leave untracked `docs/diagnosis/`, `out/`, and `src/evaluation/candidate_gold/` untouched.

## Failure classes and test-before-fix sequence

Each class gets general synthetic reproductions, committed with observed failures before its fix.
Then commit that class's general fix separately. This gives one failing-test commit and one fix commit
per class; the explicit requirement to commit failing tests precedes the class's implementation.
Do not weaken an existing test to accommodate the change. Tests include positive controls and
semantic near-miss negatives. Implementation scope is `src/evidence/binder_v2.py`, and `gate.py`
only if routing requires it; tests live under `tests/`.

### A. Equal number, incompatible quantity or subject

A threshold, confidence setting, hyperparameter or count must not bind to a metric cell merely
because its numeric token matches. Require a compatible quantity type and the correct model/class
subject for the value's local scope; otherwise abstain. Include mixed clauses where another number
really is the metric, and cross-model/class negatives, rather than only one isolated trigger word.

### B. Extra cells and multi-value completeness

Every chosen cell must have independent subject and quantity support from its associated value
mention. A mention may not borrow a different value's model, class or metric, nor reuse one explicit
mention as evidence for multiple unrelated cells. Partial or ambiguous required coverage abstains.
Include equal-valued measurements with different metrics/subjects, coordinated clauses, and a
complete comparison positive control. Do not solve coverage by returning only the first metric.

**Explicit user amendment, 2026-10-06, after the recorded Class B STOP:** completeness applies only
to table-measurable claim values: the value appears in at least one candidate cell of the claim's
table(s). A value matching no table cell is non-table/text-only and does not block a supported bind.
Existing tests define this supported-bind behavior; forcing abstention would lose verified bindings
and violate S2. A matching value in another row/column remains table-measurable: if its required
binding cannot be covered without semantic conflict, the whole claim must still abstain.

Only the NEW Phase 11 Class B tests may be revised to reflect this clarified scope. Preserve their
original failing-first commit and document the revision; no pre-existing test or frozen artifact may
change. Include paired boundary tests for an absent second value (keep the supported bind) and a
second value matching a conflicting row/column (partial_binding). Keep extra-cell negative controls.
The S1/S2 trade-off is explicit: a text-only value supplies no table binding and cannot itself cause
a wrong cell selection, but it is also not verified by the table. A supported table bind must not be
reported as verification of every text-only statement in the claim. This amendment is committed
separately before further implementation, as instructed by the user.

### C. Decorated labels, values and hierarchy

Normalize general formatting while preserving semantics: `X (Proposed)`, `Proposed Method`, `Ours`,
`Method [55]`, arrow-decorated headers such as `Dice↑`, uncertainty, percent, trailing significance
asterisks, split tokens such as `Mas k`, and hierarchical `Group / Metric` headers. Decorative text
must not suppress a supported bind; meaningful qualifiers, uncertainty and units must still conflict
when different. Include negative controls for real group, method-variant, uncertainty and unit changes.

### D. Verified legacy preservation

When v2 has no verified whole-claim binding, consider a legacy result only if it passes the SAME raw
claim/cell verifier and all required-value completeness checks. Do not trust legacy's bound status.
Do not preserve a cell rejected by v2 for quantity mismatch, subject mismatch, table mismatch, or
ownership; ambiguity and partial coverage cannot be bypassed to satisfy S2. Recompute these checks
from attached raw evidence. Record the exact fallback conditions in code/tests/report.

S1 takes precedence over preservation: a legacy success is not an exemption from precision checks.
The class must include a legacy-wrong / v2-correctly-rejected synthetic case that remains rejected,
as well as a general verified legacy success that can be retained without semantic override. If a
legacy bind cannot satisfy the verifier or completeness, leave it rejected and report the S2 cost.

## Validation and STOP rule

Unchanged criteria: S1 zero wrong bindings, including two independent PDF checks for every new
non-gold association; S2 zero previously verified bindings lost in any unit/representation; S3
byte-identical legacy output on 30 PDFs and the 55-pair/18-claim comparison, newline canary zero.
All new synthetic tests must pass on Python 3.10.18 and 3.13.6; full pytest must pass under legacy and v2.
Also run the standalone pipeline tests, experiment unit suite, and frozen 123-check binder regression
in both environments. No real model calls are allowed even during tests.

For S3, import the unchanged `validate_10.py identity` function with `RESULTS` redirected to a new
Phase 11 output. Never run its CLI directly against the frozen `results.json`. Likewise, any regression
measurement imports unchanged scoring with output paths redirected under `runs/phase11_binder/`.
Keep commands, observed failing-before/passing-after output and hashes in that directory, and commit
the durable summary/evidence in `docs/evaluation/`. No Phase 10 output file is overwritten.

If A4 introduces a regression against the starting behavior or fails a required test, STOP and report;
do not begin Part B or edit tests to turn failure into success. Existing frozen S1/S2 failures must
remain visible even if they arise from reconstruction limitations rather than semantic wrong cells.
No enablement is authorized by development results alone.

## Measurement plan and held-out primary evidence (not built in this task)

The frozen 55-pair/18-claim set is a **development-contaminated regression check only**. Record old
and new results using the unchanged evaluator; do not use those results to tune this implementation.
Separate pairs and real claims, representations, precision and coverage. Preserve the existing
conservative treatment of absent reconstructed gold cells. Do not reinterpret failures as passes.

Primary evidence requires a NEW held-out set, to be constructed in a later authorized task:

1. Freeze a manifest of **12 new papers and 60 claims**, five claims per paper. Exclude all 16 Phase 10
   papers, their preprint/version duplicates, and every claim/paper already used to develop the binder.
   Freeze content hashes and bibliographic/version identity before running either binder.
2. Construct a pool by reading complete tables and nearby text without binder predictions. Choose
   40 positive claim-to-cell cases and 20 numeric near-miss/no-bind controls. Cover simple metrics,
   multi-value comparisons, counts/settings, hierarchical tables, decorated labels and meaningful
   qualifiers. Fix the source-pool manifest and use hash ordering within the registered strata; do not
   select items because a particular binder succeeds or fails. If quotas cannot be met, record the
   shortfall before prediction and seek an amended scope rather than silently substituting easier items.
3. For each positive claim, enumerate ALL required target cells and their page/table/row/header/value
   evidence, including units/uncertainty. For each negative, record why matching numbers do not support
   the claim. Keep PDF crops and text layers. A held-out custodian keeps claim/cell labels unavailable
   to implementation work until code and analysis are frozen.
4. Use two independent blinded readings of the PDF, with disagreements marked unresolved; label all
   suggested gold **machine-assisted, unvalidated**. Human validation belongs to the project owner.
   Do not report machine labels as human ground truth or use unresolved labels to award correctness.
5. Freeze labels, criteria and scoring before evaluation. Compare legacy and v2 on the same artifacts,
   applying unchanged S1/S2/S3 requirements and independent checks for new bindings. Report coverage
   separately from correctness and leave unresolved evidence explicit. Held-out release evidence is
   not available in this task, so this task cannot justify enabling v2.

Do not acquire papers, construct labels, or run this held-out evaluation now.

## Deliverables and Part B boundary

Commit this scope alone, then the read-only class diagnosis, then the per-class test/fix commits.
Write `docs/evaluation/phase_11_binder.md`, update `PROGRESS.md`, and write the Phase 11 checkpoint.
Commit and push Part A before tagging `phase11-binder-final` or starting Part B. If a STOP fires,
report the blocker and leave Part B unstarted.

Part B cannot call a real LLM. Production extraction normally does (`run_pipeline.py:39`,
`src/summarization/summarize.py:828`), so a fresh full pipeline run conflicts with that hard rule.
Clarification is pending on a cached extraction replay. Any replay must be identified as such and
must report unavailable source records instead of inventing a fresh end-to-end result. Part B changes
no source, tests, configs, gold or evaluator and commits only its requested bottleneck map.
