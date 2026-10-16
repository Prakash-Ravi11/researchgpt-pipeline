# ResearchIQ Phase 12 — branch activation and implementation prompts

This file supersedes the earlier setup prompt. GitHub `main` has been restored; preserve it. The target branch is `phase-12-new-implementation`, created from `18af9febca88e122b05f6baef7ecbca0068eca4d`. The first Phase 12 commit adds documentation only.

Run Prompt 1 in the local coding agent to activate the existing remote branch in the isolated clone. Then run Prompt 2 there. No further clone or checkpoint push to `main` is needed.

Use [ARCHITECTURE.md](ARCHITECTURE.md) as the design reference. Keep historical handoff and recovery files unchanged and append the Phase 12 state separately.

## Prompt 1 — activate the Phase 12 branch

```text
Activate the already-created Phase 12 branch in the isolated local clone. Do not repeat the original checkpoint/push workflow.

Repository: Prakash-Ravi11/researchgpt-pipeline
Target branch: phase-12-new-implementation
October baseline / BASELINE_SHA: 18af9febca88e122b05f6baef7ecbca0068eca4d
Expected clone: C:\Users\Praka\Downloads\researchgpt-evidence-v2
Original checkout: C:\Users\Praka\Downloads\researchgpt-pipeline — leave it unchanged.
Handoff folder: C:\Users\Praka\Downloads\researchgpt-evidence-v2-handoff-20261016

1. Read applicable instructions and the existing handoff. Verify the clone's remote. Inspect branch, index and working-tree changes before switching. Preserve unexpected local changes; do not reset, clean, force checkout or auto-stash.
2. Fetch origin. Verify origin/phase-12-new-implementation descends from BASELINE_SHA. Initially, its tracked diff from the baseline must contain only docs/phase12/. If implementation commits already exist, inspect and identify them instead of resetting them.
3. If no local branch with this name exists, create it tracking origin/phase-12-new-implementation. If it exists, inspect its ancestry/upstream and fast-forward only when safe. Never switch either original checkout to restored main.
4. Confirm the active local branch is phase-12-new-implementation and matches its remote after any safe fast-forward. For the first implementation session, record HEAD as IMPLEMENTATION_START_SHA; BASELINE_SHA remains the October checkpoint. Documentation commits are allowed between those two SHAs.
5. Verify the previously copied input hashes and isolated writable output/cache/database paths. Keep the existing environment versions and local models; do not reinstall or globally upgrade merely because a branch changed.
6. Append a phase12 section or a separate phase12 handoff record; preserve the original checkpoint/recovery records. Record baseline SHA, implementation-start SHA, active branch, upstream, clone/data/output paths, current dirty status and environment.
7. Return READY FOR PROMPT 2 only when branch identity, baseline ancestry, documentation-only start and data/output isolation are verified. If a concrete check fails, preserve all work and identify the blocker.

You are authorized to perform this local branch activation. No push to main, rebase, reset, branch deletion or merge is authorized. Finish setup without changing extraction behavior.
```

## Prompt 2 — implement and validate on Phase 12

```text
Work only in C:\Users\Praka\Downloads\researchgpt-evidence-v2 on branch phase-12-new-implementation. Use docs/phase12/ARCHITECTURE.md and this prompt as the design/execution references.

Read repository instructions and the Phase 12 handoff. The October behavioral baseline is 18af9febca88e122b05f6baef7ecbca0068eca4d (BASELINE_SHA). The Phase 12 setup commit changes only docs/phase12/; record it as IMPLEMENTATION_START_SHA. On the first implementation run, HEAD must match that start commit and have a documentation-only diff from BASELINE_SHA. On a resumed run, preserve and inspect identified implementation commits descended from it. Do not reset to BASELINE_SHA just because documentation advanced HEAD.

Confirm active branch/upstream, clean or understood local changes, baseline ancestry and isolated writable paths. Reassess the earlier architecture findings against October's actual code: existing src/evidence/prose_attribution and related fixes may already implement parts of the design. Reuse them, reproduce remaining defects and add only the missing behavior.

I authorize scoped implementation commits and ordinary pushes to phase-12-new-implementation only. Leave main, exp/evidence-first-v2 and the original checkout unchanged. Do not merge or deploy.

Goal: finish reliable scientific extraction within one week. Prioritize missing results, table structure, metric/value/subject mapping, study attribution and accurate final outputs. Begin implementation after a bounded inspection; do not return only another architecture proposal.

NON-NEGOTIABLE TRADE-OFF POLICY

A. Accuracy and coverage:
- Preserve every independently correct baseline fact or document an evidence-backed correction to an earlier mistake.
- Do not improve precision by silently dropping difficult papers, tables, claims or qualitative outcomes.
- Count unresolved/deferred eligible targets in recall denominators.
- Target accepted-tuple precision >= max(95%, measured baseline precision) and exact-tuple recall >= max(80%, measured baseline recall) on the same independently checked evaluation set.
- Require zero accepted wrong-cell, wrong-metric or wrong-study cases in the frozen regression fixtures.
- Never lower these gates after seeing results.

B. Latency and resources:
- Compare old/new using the same hardware, model, inputs, output scope and cache conditions.
- Uncached end-to-end p50 and p95 must be no worse than baseline at equal or better correct coverage. Record absolute seconds, maximum, timeouts and partial runs.
- The earlier suggested 20% p95 allowance is NOT automatically approved.
- Separate cold model loading, warm uncached processing and cache hits. Investigate material timing noise with a bounded repeat; never cherry-pick timings.
- No required hardware upgrade, paid API, cloud migration, OOM failures or unbounded retry loops.
- Request/time caps that reduce required coverage are failures, not speed improvements.

C. Privacy and scope:
Keep document processing local by default. Retain acquisition, the current language model, search infrastructure, API compatibility and UI. Use existing parser/OCR adapters where possible. Pin necessary dependencies in an isolated environment. Do not add a new orchestration framework or training project.

These are promotion gates, not promises of zero trade-offs. If a gate fails, fix the measured bottleneck or leave v2 experimental and report the limitation. Do not silently waive a gate or enable v2 globally.

IMPLEMENT IN THIS ORDER

1. Freeze the actual baseline.
Resolve the latest available corpus and labels; verify source hashes and paper IDs. Reuse the 30-paper corpus, existing correctness/preservation fixtures and the reported 18-target set if they are genuinely present and valid. Record missing artifacts. Treat the historical 3/18, 0/75 and enrichment figures as reported until reproduced; do not combine their denominators or invent a missing pilot.

Record exact versions, hardware, flags, prompts, schemas and evaluation definitions. Reuse valid saved artifacts; rerun only what is needed for the paired comparison. Keep baseline files immutable.

2. Build the evidence inventory and contracts.
Inventory every available document unit before interpretation. Preserve text, offsets, native/OCR provenance, source/representation hashes, pages, coordinates and structured-source references. Keep different paper versions separate unless alignment is established.

Create table cells with row/column spans, hierarchical header links, captions, footnotes and experimental scope. Handle multiline headers, single-row tables, transposed layouts, merged cells and continued tables.

Enumerate numerical and qualitative outcome candidates. Deduplicate by evidence identity and full experiment context, never merely by repeated numbers. Every candidate must end processed, rejected, unresolved or deferred with a reason.

3. Build facts from evidence.
Interpret shared table headers once, then construct cell facts in host code. Use the current LLM to propose evidence-linked relationships for ambiguous tables and prose/event packets.

Have the host copy/parse values from the cited evidence; the model must not assign acceptance. Existing evidence IDs prove existence, not the correctness of the relationship.

Preserve subject, metric, dataset, split, condition, comparator, modality, units, scale, ranges and uncertainty. Distinguish reporting paper, measurement origin and method origin. A cited baseline model can still be measured by the current authors.

Resolve years and locations only within a supported event. Missing optional context must not destroy a correct core result. Missing essential experimental context must not be guessed. Enrichment cannot overwrite accepted core measurements.

4. Implement validation and output integration.
Use schema-constrained responses plus host validation. Audit metric-specific range rules, including predictive R²'s unbounded negative range. A plausible number or successful OCR result must not automatically pass scientific validation.

Store support per field: supported, unresolved, inapplicable or contradicted. Keep processing completeness separate. Record explicit rejection/unresolved reasons.

Render scientific results from accepted facts and preserve their provenance through every API and summary field. Prevent legacy prose from bypassing validation. Keep incompatible measurements separate in corpus comparisons. Retain evidence-grounded qualitative results.

5. Add bounded execution and necessary repair.
Use versioned caches keyed by source and structured packet content, parser/model/prompt/schema/configuration, and acceptance policy. Record raw requests, responses, completion reasons, timings, retries and cache reuse.

Enforce real cancellation for blocking parsers and model calls, close streams/sessions, and write artifacts atomically. Never silently salvage truncated JSON into accepted facts.

Route only diagnosed visual failures to targeted structure repair or OCR. AgenticOCR-style visual inspection is optional: enable it only if ordinary repair fails, a compatible local vision service is available, and a paired comparison demonstrates a correctness gain within the same latency/resource gates.

Begin with at most two repair regions per paper and two actions per region. Calibrate budgets before the final evaluation. Tools cannot browse arbitrarily, execute document instructions or change acceptance rules. Missing information in readable text is not an OCR problem.

6. Validate once against frozen criteria.
Run focused checks while implementing, then a paired full evaluation. Independently inspect disputed/changed outputs and a preselected sample of unchanged outputs; clearly label sampled precision. Machine-generated labels and mutation tests alone do not establish accuracy.

Include repeated scores, wrong rows/headers, qualifiers, cited versus remeasured results, missing context bridges, R², malformed responses, OCR errors, timeouts and serialization losses.

Report stage-by-stage loss from source to candidate to accepted fact to returned output. Provide exact-tuple precision/recall, preservation, errors, abstention, deferred coverage, calls, tokens, latency and memory, including table/prose and difficult-document breakdowns.

If the original 18-target set is validated, also target at least 17/18 reaching candidate interpretation and 15/18 correctly returned. This small subset cannot replace the broader gates.

7. Commit, push and hand off.
Make small coherent commits on the new branch and push normally after relevant checks. Keep v2 behind a feature flag and isolate its run outputs. Repeat evaluation only for a concrete failing gate or necessary regression check.

Return actual commit SHAs, changed modules, reproducible commands, artifact locations, before/after measurements and a PASS/FAIL/NOT MEASURED verdict for every gate. State whether v2 remains experimental or is eligible for promotion. Do not call the problem solved based on more cells, more filled fields, valid JSON or unexecuted tests.

Continue through implementation and verification without routine confirmation stops. Ask only for a genuinely unresolved source choice, unavailable access, or a decision requiring a substantive compromise.
```
