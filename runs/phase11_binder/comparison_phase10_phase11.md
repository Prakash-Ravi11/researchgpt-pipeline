# Phase 10 vs Phase 11 deterministic binder comparison

Current disposition (2026-10-08): STOP at Stage B of the change-role repair. Review found a new general counterexample: "The Dice scores of 0.37 increase after tuning." The candidate incorrectly marked the absolute score as a change amount. Stage B was reverted byte-for-byte to the retained binder (S1=19, S2=25); Stage A's S3 PASS is the last measured identity result. Stage C, held-out evaluation and end-to-end replay were not started. The new reproduction tests remain uncommitted. The completed audit and STOP evidence are the only publication changes. See the final Stage B STOP section for the exact conflict and verification limits.

Follow-up disposition (2026-10-07): the single numeric-metric fix attempt was REJECTED and REVERTED after it reintroduced an improvement-to-p-value binding. Retained binder behavior remains phase11-binder-final: S1=19 and S2=25. The new synthetic reproductions remain uncommitted (4 expected recovery failures, 6 passing controls). See the final STOP section below. No second fix attempt was made.

development-contaminated, machine-assisted, unvalidated

S1 is unchanged: 19 -> 19 wrong-binding flags. S2 improves by two occurrences: 27 -> 25 (four fixed, two new). Both zero-failure criteria remain FAIL.

Python 3.10.18; explicit v2 with the identical legacy reference. The unchanged frozen evaluator functions and arguments from R5 were called on the same cached representations and product inputs. Only cached input roots were redirected in memory for the temporary worktree; code imports came from the corresponding checkout. The stdin driver is preserved in the JSON artifact.

Offline guard: blocked; external and localhost:11434 canaries raised in both runs. No LLM or network requests. No source/test/config/frozen artifact changes; no commits. Temporary Phase 10 worktree removed.

Phase 10 commit: 050f8de76b8eabf04bb46fd863beee152a760975. Phase 11 commit: a113581c070b573c789eab4bb5b0666e9adb5d99. Local final tag object: f7146a26442beb75df35998d2676af1193af6d70.

Frozen source: C:\Users\Praka\Downloads\researchgpt-pipeline\src\evaluation\binder_10\results.json (criteria.v2.S1.gold_wrong_binds: 19; criteria.v2.S2.lost_verified_binds: 27). Corroborating report: C:\Users\Praka\Downloads\researchgpt-pipeline\src\evaluation\binder_10\PHASE10_REPORT.md.

Every frozen Phase 10 per-representation comparison list reproduced exactly. Both Phase 11 arms exactly match R5. Input hashes match and legacy reference outputs are identical.

| Representation | Phase 10 S1 | Phase 11 S1 | Phase 10 S2 | Phase 11 S2 |
|---|---:|---:|---:|---:|
| R-prod | 9 | 9 | 10 | 11 |
| R-eval | 10 | 10 | 17 | 14 |
| R-oracle | 0 | 0 | 0 | 0 |
| Total | 19 | 19 | 27 | 25 |

S2 gold-unit losses: 5 -> 3; sweep association losses: 22 -> 22. Occurrences repeat claims across units/representations.

## a. Wrong-binding flags fixed

None.

## b. Wrong-binding flags new

None.

## c. Lost bindings fixed

- **R-eval / claims / C013**

  Claim: Our proposed method achieves an average DSC of 90.22% and an average HD95 of 4.04 pixels, which is at least 3.02 pixels lower than other weakly-supervised methods on the testing set.

  Gold: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; Table 2; UM-CAM+SPL (ours) / Test set / HD95 (pixels) = 4.04±4.26*.

  phase10: wrong_cell; cells: none; gate: ['ABSTAINED'].

  phase11: bound; cells: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; Table 2; UM-CAM+SPL (ours) / Test set / HD95 (pixels) = 4.04±4.26*; gate: ['ABSTAINED'].

- **R-eval / pairs / PF005**

  Claim: The UM-CAM+SPL (ours) achieves a Test set DSC (%) of 90.22.

  Gold: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*.

  phase10: wrong_cell; cells: none; gate: ['ABSTAINED'].

  phase11: bound; cells: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; gate: ['ABSTAINED'].

- **R-eval / sweep_A / C013**

  Claim: Our proposed method achieves an average DSC of 90.22% and an average HD95 of 4.04 pixels, which is at least 3.02 pixels lower than other weakly-supervised methods on the testing set.

  Gold: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; Table 2; UM-CAM+SPL (ours) / Test set / HD95 (pixels) = 4.04±4.26*.

  Counted legacy association: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*.

  phase10: wrong_cell; cells: none; gate: ABSTAINED.

  phase11: bound; cells: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; Table 2; UM-CAM+SPL (ours) / Test set / HD95 (pixels) = 4.04±4.26*; gate: ABSTAINED.

- **R-eval / sweep_B / P004:3c9b838a0b36d032a86ffe582f55b3583fd4a815:116#0**

  Claim: Our proposed method achieves an average DSC of 90.22% and an average HD95 of 4.04 pixels, which is at least 3.02 pixels lower than other weakly-supervised methods on the testing set.

  Gold: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; Table 2; UM-CAM+SPL (ours) / Test set / HD95 (pixels) = 4.04±4.26*.

  Counted legacy association: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*.

  phase10: wrong_cell; cells: none; gate: ABSTAINED.

  phase11: bound; cells: Table 2; UM-CAM+SPL (ours) / Test set / DSC (%) = 90.22±3.75*; Table 2; UM-CAM+SPL (ours) / Test set / HD95 (pixels) = 4.04±4.26*; gate: ABSTAINED.

## c. Lost bindings new

- **R-eval / sweep_B / P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0**

  Claim: Our method showed an average of 5% and 0.12 mm improvement in Dice and 95HD over PAUNet, respectively.

  Gold: none. No reconstructed gold target for this unit; no new gold label assigned

  Counted legacy association: TABLE II; Attention UNet vs. Ours / Dice = 0.12.

  phase10: bound; cells: TABLE II; Attention UNet vs. Ours / Dice = 0.12; gate: ABSTAINED.

  phase11: wrong_cell; cells: none; gate: ABSTAINED.

- **R-prod / sweep_B / P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0**

  Claim: Our method showed an average of 5% and 0.12 mm improvement in Dice and 95HD over PAUNet, respectively.

  Gold: none. No reconstructed gold target for this unit; no new gold label assigned

  Counted legacy association: TABLE II; Attention UNet vs. Ours / Dice = 0.12.

  phase10: bound; cells: TABLE II; Attention UNet vs. Ours / Dice = 0.12; gate: ABSTAINED.

  phase11: wrong_cell; cells: none; gate: ABSTAINED.

## Remaining Phase 11 failure mechanisms

These groups describe frozen scoring outcomes and deterministic traces; they are not independently validated semantic error labels.

| S1 mechanism | Occurrences |
|---|---:|
| extra_bound_cells_outside_reconstructed_gold | 2 |
| representation:table_not_reconstructed | 1 |
| representation:target_cell_column_wrong | 2 |
| representation:target_cell_column_whitespace_artifact | 2 |
| representation:target_cell_row_wrong | 12 |

Seventeen flags arise because the cached representation fails the frozen target reconstruction (12 row mismatches, 2 column mismatches, 2 column whitespace mismatches, 1 missing table). C021 adds mask-column bindings outside its two reconstructed Box gold cells in both representations (2 flags).

| S2 status/mechanism | Occurrences |
|---|---:|
| partial_binding | 10 |
| wrong_cell | 9 |
| duplicate_quantity_context | 4 |
| not_bindable | 2 |

- partial_binding (10): C026 has a quantity-axis conflict for 95HD=0.96 (6 repeated occurrences); YOLOv7 recall has a quantity-term conflict (2); YOLOv5 mAP values have quantity/name/qualifier conflicts (2).
- wrong_cell (9): RCNN/95% has quantity/name conflicts (4); the 0.12-mm improvement hits a Dice p-value and is rejected for quantity-axis conflict (2); C012 has name/table-mention conflicts (2); C085 has a quantity-term conflict (1).
- duplicate_quantity_context (4): the 88.7/92.3 Dice prose binds 88.7 but finds duplicate quantity context for 92.3, causing the whole claim to abstain.
- not_bindable (2): the unlabelled Dice/95HD/ASD fragment has unresolved subject/quantity links.

Full per-occurrence states, gold targets, captions and Phase 11 traces are in the JSON artifact.

## Qualifications

- Development-contaminated, machine-assisted, unvalidated; no validation claim.
- S1 totals count frozen gold-unit wrong-binding flags, not unique claims or independent audit failures.
- The separate Phase 10 PDF audit recorded one distinct wrong new binding among 22 audited; that audit was not rerun and is not added to the gold-flag total.
- 17 of 19 remaining S1 flags have no reconstructed gold cell. Two C021 flags include extra mask cells outside the reconstructed gold list.
- S2 includes repeated gold-unit and sweep claim/cell occurrences across representations; it does not count unique claims.
- The two new S2 losses remove a legacy association between a 95HD improvement in mm and a Dice p-value (0.12); no verified gold cell exists for this sweep sentence. Thus the count is not proof of semantic harm.
- The four recovered bindings are still ABSTAINED by the gate (bound_to_other_table), so this is not an end-to-end return gain.

## Files created

- C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase10_measurement.json
- C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase10_console.txt
- C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase11_measurement.json
- C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase11_console.txt
- C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase10_phase11.json
- C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase10_phase11.md

## Follow-up: one bounded numeric-metric fix (2026-10-07)

development-contaminated, machine-assisted, unvalidated

This section records a single uncommitted candidate after phase11-binder-final, subsequently rejected and reverted. The tag comparison above remains unchanged. This Markdown file is the sole updated report; no duplicate report format is being created.

S1 triage found no established semantic error that justifies suppressing the selected Mask cells. Frozen verified gold includes all four C021 Box/Mask targets (postfix_claim_cell_gold.json, PF007-PF010), but reconstruction retains only the two Box targets because the cached Mask header is split as 'Mas k'. Six PF026-PF028 occurrences are excluded by a ligature difference in 'Local gyrification index'; six PF038-PF040 occurrences by 'ADC_D' versus 'ADC D _'; four PF008/PF010 occurrences by the split Mask header. PF004 (R-eval) selects Table 2's validation cell instead of the absent Table 1 target; the canonical probe omits table identity. These remain frozen scoring failures, not newly validated semantic errors. No frozen gold or scoring changes are proposed.

Sources: src/evaluation/binder_10/validate_10.py:144 and :172; src/evaluation/bottleneck_diagnosis/postfix_evaluate.py:240 and :244; src/evaluation/bottleneck_diagnosis/postfix_claim_cell_gold.json:494, :638, :686, :734, :782; src/evaluation/binder_10/PHASE10_REPORT.md:66. Read-only local PDF text inspection corroborates the Box/Mask values but is not an independent blind audit.

C026 mechanism: _frame treated the '95' in the recognized metric '95HD' as a numeric mention. That moved the next value's local start into the metric token, excluding the full '95HD' label. For 0.96, links then chose the earlier Dice caption quantity and reported quantity_axis. This caused partial_binding and six repeated S2 losses across claims/sweep_A/sweep_B and R-prod/R-eval.

Failing-first synthetic evidence (Python 3.10.18): the new tests/test_binder_v2_numeric_metric_labels.py produced 4 failures and 5 passes. Invented 73Rho and 61Luma multi-metric claims returned partial_binding instead of bound; real values equal to the metric prefix produced duplicate bindings. No experiment claim, metric or value was copied into the synthetic cases.

The one fix removes value mentions wholly inside a recognized alphabetic quantity-label span before constructing local contexts. Values outside the label remain required; cross-metric conflicts and threshold/delta semantics are preserved. The new tests now pass 9/9. Existing tests, the frozen regression harness and Phase 10 artifacts are unchanged. The external and localhost:11434 connection canaries raised with the existing offline guard in blocked mode.

### Sequential A4 checks for the working-tree change

Full pytest includes Classes A-E, the Class B boundaries, and the nine new tests. Each child inherits the blocked guard. The frozen regress.py sets v2 internally even when its invocation environment is legacy. Stop on the first failure; no repeated fix attempts.

The initial runner was interrupted by WinError 5 while cleaning its temporary directory (numeric_metric_a4_39rzx2i_). Its child output was not saved, so that attempt supplies no matrix verdict. After the user's resume instruction, the unchanged fix is being checked with workspace filesystem access outside the restrictive sandbox; the Python offline guard remains active.

| Python | Invocation policy | Suite | Result | Guard |
|---|---|---|---|---|
| 3.10.18 | legacy | full pytest | PASS: 252 passed in 22.67s | active |
| 3.10.18 | legacy | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.10.18 | legacy | experiment units | PASS: 63 passed, 0 failed | active |
| 3.10.18 | legacy | frozen regress | PASS: 0 failing: []; :105/:198 PASS (not_a_table_claim) | active |
| 3.10.18 | v2 | full pytest | PASS: 252 passed in 18.36s | active |
| 3.10.18 | v2 | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.10.18 | v2 | experiment units | PASS: 63 passed, 0 failed | active |
| 3.10.18 | v2 | frozen regress | PASS: 0 failing: []; :105/:198 PASS (not_a_table_claim) | active |
| 3.13.6 | legacy | full pytest | PASS: 252 passed in 20.37s | active |
| 3.13.6 | legacy | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.13.6 | legacy | experiment units | PASS: 63 passed, 0 failed | active |
| 3.13.6 | legacy | frozen regress | PASS: 0 failing: []; :105/:198 PASS (not_a_table_claim) | active |
| 3.13.6 | v2 | full pytest | PASS: 252 passed in 17.94s | active |
| 3.13.6 | v2 | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.13.6 | v2 | experiment units | PASS: 63 passed, 0 failed | active |
| 3.13.6 | v2 | frozen regress | PASS: 0 failing: []; :105/:198 PASS (not_a_table_claim) | active |

All 16 sequential combinations passed. Frozen regress.py:105 and :198 remain not_a_table_claim in all four regression invocations.

### S3 and development regression after the bounded fix

S3 PASS: legacy gate records identical for 30/30 PDFs; no differences across 55 pairs / 18 claims; newline canary 0. Frozen validate_10.identity was called unchanged, with its merge_results sink redirected to memory. No frozen file was written.

Binder source SHA-256: bf44ac87bb3dda4f1ded40b802ec89c5f3e5f81a9d6e72db72a97d24e116f31c.

Python 3.10.18; same cached inputs and unchanged V.run_arm / V.compare calls as R5. Legacy output is exactly identical to the pre-fix reference. No held-out evaluation or production run was performed.

| Representation | Before S1 | After S1 | Before S2 | After S2 |
|---|---:|---:|---:|---:|
| R-prod | 9 | 9 | 11 | 7 |
| R-eval | 10 | 10 | 14 | 10 |
| R-oracle | 0 | 0 | 0 | 0 |
| Total | 19 | 19 | 25 | 17 |

S1 flags fixed: 0; new: 0. S2 occurrences fixed: 8; new: 0.

| Change | Representation | Kind | ID | Claim | Before status/cells | After status/cells |
|---|---|---|---|---|---|---|
| fixed | R-eval | claims | C026 | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. | partial_binding: none | bound: Ours / Dice↑ = 0.87±0.06; Ours / 95HD(mm)↓ = 0.96±0.38; Ours / ASD(mm)↓ = 0.28±0.14 |
| fixed | R-eval | sweep_A | C026 | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. | partial_binding: none | bound: Ours / Dice↑ = 0.87±0.06; Ours / 95HD(mm)↓ = 0.96±0.38; Ours / ASD(mm)↓ = 0.28±0.14 |
| fixed | R-eval | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. | partial_binding: none | bound: Ours / Dice↑ = 0.87±0.06; Ours / 95HD(mm)↓ = 0.96±0.38; Ours / ASD(mm)↓ = 0.28±0.14 |
| fixed | R-eval | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | Our method showed an average of 5% and 0.12 mm improvement in Dice and 95HD over PAUNet, respectively. | wrong_cell: none | bound: Attention UNet vs. Ours / Dice = 0.12 |
| fixed | R-prod | claims | C026 | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. | partial_binding: none | bound: Ours / Dice↑ = 0.87±0.06; Ours / 95HD(mm)↓ = 0.96±0.38; Ours / ASD(mm)↓ = 0.28±0.14 |
| fixed | R-prod | sweep_A | C026 | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. | partial_binding: none | bound: Ours / Dice↑ = 0.87±0.06; Ours / 95HD(mm)↓ = 0.96±0.38; Ours / ASD(mm)↓ = 0.28±0.14 |
| fixed | R-prod | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. | partial_binding: none | bound: Ours / Dice↑ = 0.87±0.06; Ours / 95HD(mm)↓ = 0.96±0.38; Ours / ASD(mm)↓ = 0.28±0.14 |
| fixed | R-prod | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | Our method showed an average of 5% and 0.12 mm improvement in Dice and 95HD over PAUNet, respectively. | wrong_cell: none | bound: Attention UNet vs. Ours / Dice = 0.12 |

C026 gate outcomes after binding recovery:

- R-prod: bound; returned=True; gate=['RETURNED']; reasons=[None].
- R-eval: bound; returned=True; gate=['RETURNED']; reasons=[None].

Rejected candidate scoring: S1 FAIL; S2 FAIL; S3 PASS. Development-contaminated, machine-assisted, unvalidated. No validation or enablement claim.

### STOP: recovery exposes an unsafe improvement binding

The apparent S2 change from 25 to 17 consists of six supported C026 recoveries and two restored associations that must not be accepted as semantic gains. In both R-prod and R-eval, the claim 'Our method showed an average of 5% and 0.12 mm improvement in Dice and 95HD over PAUNet, respectively.' changed from wrong_cell/no cell to bound/Attention UNet vs. Ours, Dice=0.12 in a p-value table. The retained frozen S1 gold-unit flags do not cover this sweep sentence; a clean S1 delta therefore did not detect this unsafe behavior.

Conflicting requirements exposed by this one candidate:

- Supported multi-metric equality: 'Our method reports Prism of 0.713, 73Rho of 1.624, and Zeta of 0.283.' must bind all three matching quantity cells. Baseline: partial_binding; candidate: bound.
- Improvement safety: 'Our method showed an average of 6% and 0.37 mm improvement in Prism and 83Rho over BirchNet, respectively.' must not bind to CedarNet vs. Ours / Prism=0.37 in a paired p-value table. Baseline: not bound; candidate: bound. The added synthetic safety test failed on the candidate and passes after its reversion.

The latter wording places 'improvement' after its values. The existing delta recognizer looks before a number, so the context repair exposes an unrecognized delta as an equality. This is a concrete separate prerequisite, not evidence that the two requirements are inherently impossible to satisfy together. No delta-parser fix or second numeric-label attempt was made in this session.

The binder change was reverted. The final new-test result on the restored implementation is 4 failed / 6 passed: two multi-metric recovery cases and two duplicate-prefix-binding cases intentionally preserve the unresolved behavior; the improvement safety control passes. All original tests and expectations remain untouched. The 16/16 matrix and S3 PASS above apply to the rejected candidate and do not override this STOP.

Retained result: S1=19 / FAIL, S2=25 / FAIL, legacy remains default. No commit, push, tag, held-out evaluation or end-to-end run was made. The interrupted test temporary directory was removed after verifying its absolute path remained inside runs/phase11_binder.

Persistent changes from this follow-up:

- New: C:\Users\Praka\Downloads\researchgpt-pipeline\tests\test_binder_v2_numeric_metric_labels.py
- Updated existing report only: C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase10_phase11.md
- Temporarily changed and reverted: C:\Users\Praka\Downloads\researchgpt-pipeline\src\evidence\binder_v2.py

## 2026-10-08 Part 0: legacy inventory

Development-contaminated, machine-assisted, unvalidated. This read-only inventory describes the retained implementation and existing reports before the new implementation stages. No source, test, configuration, frozen evidence, or scoring file was changed for this inventory.

Case-insensitive substring search found **711 occurrences on 622 lines in 98 readable first-party code/configuration/Markdown files** at inspection time. A broader scan that also included ignored machine receipts and imported corpus text found **11,585 occurrences in 166 files**. These are literal occurrence counts, not counts of distinct behaviors. They exclude the inventory text being appended here and any later report additions. **No occurrence uses "legacy" to mean Python 3.10 or Python 3.13.** Named `test_legacy_*` functions test compatibility with older behavior; they are not separate interpreter versions.

### Semantic categories

1. **Binder policy:** `binder_policy=legacy`, `RGPT_BINDER_POLICY=legacy`, `_structural_bind_legacy`, baseline comparison arms, Class D preservation, and S3 identity refer to the older deterministic binder. It remains the default binder. Class D rechecks a legacy-selected cell; it does not blindly accept its old status.
2. **Fallthrough policy:** `fallthrough_policy=legacy` names gate behavior before `table_value_guard`. It is independent of binder policy. The code falls back to legacy when no recognized environment/configuration value exists; the active configured value can differ.
3. **Retrieval selection:** `selection.mode=legacy` and `_select_legacy` mean five fixed generic queries, top-three results per query, union, and assembly. `legacy_fallback` records fallback from content-aware selection because of old chunk schema. A circuit breaker also retries this selector.
4. **Older representation/acquisition/product paths:** flat chunks and compatible old chunk fields, older PDF processing or acquisition order, and behavior with `evidence_grounding.enabled=false`.
5. **Historical proposal:** `src/evaluation/bottleneck_diagnosis/repository_inventory.md:96` describes a proposed `disambiguation_policy=legacy` switch. This is a proposal in a report, not a current implemented configuration.
6. **Authentication compatibility:** `backend/.env:11` is a comment about older HS256 JWT signing. It is unrelated to binder policy or interpreters. No secret value is reproduced here.
7. **Imported data and tooling:** research text uses the ordinary English term "legacy". Machine receipts repeat policy names, `legacy_cells`, and `in_legacy_pdf`. Vendored browser tooling uses the term for old storage formats and was excluded from the first-party counts.

### Complete readable code/configuration/Markdown inventory

The following 98 paths are relative to `C:/Users/Praka/Downloads/researchgpt-pipeline`. Comma-separated numbers identify matching lines; ranges identify consecutive matching lines. All numbers refer to the pre-append inspection state. A single line can contain multiple occurrences.

**Binder implementation and tests**

```text
src/evidence/binder_v2.py:1264-1265,1283,1296,1306
src/evidence/gate.py:432,435,438,504,506-507,511,532,536,538,542,560,696
tests/test_binder_v2.py:1,216,222,234,238-239
tests/test_binder_v2_phase11_d.py:1,23,26,33,42,44,52,55,62
```

In `gate.py`, lines 504, 506-507, 511, and 532 concern the separate fallthrough policy. The other listed occurrences concern binder policy.

**Fallthrough behavior and acceptance experiments**

```text
tests/test_fallthrough_guard.py:1,57,75,108-109,115,132,137-138,142
src/evaluation/fallthrough_09b/validate_09b.py:3,40-41,99,109,114,124,207,401
src/evaluation/fallthrough_09b/PHASE09B_REPORT.md:50,85,94,96,114,116,315
src/evaluation/fallthrough_09b/PREREG_09B.md:15,17,32,36,75,78,124,129,144-145,192
src/evaluation/acceptance_pre10/run_acceptance.py:16,47
src/evaluation/acceptance_pre10/ACCEPTANCE_REPORT.md:7,46
docs/evaluation/checkpoints/phase_09b_fallthrough.md:5,170
docs/evaluation/checkpoints/phase_acceptance_pre10.md:6
```

`test_fallthrough_guard.py:109` explicitly pins the binder to legacy while testing fallthrough compatibility; its other occurrences concern fallthrough.

**Binder reports, historical comparisons, helpers, and receipts described in Markdown**

```text
BLOCKED.md:244,253-254,276
docs/evaluation/PROGRESS.md:31,43,54,85,92,134,159
docs/evaluation/checkpoints/phase_10_binder.md:8,30,40,86
docs/evaluation/checkpoints/phase_11_binder.md:12,22,28
docs/evaluation/diagnosis/phase11_failure_classes.md:7,18-63,71
docs/evaluation/phase_11_binder.md:4,80-83,88-91,99,108,112,125-126,129-130,133-134,138,165,168,187,196,241-242
docs/evaluation/preregistration/phase_11_scope.md:16,68,70-71,76-79,85-86,126
src/evaluation/binder_10/FAILURE_MAP_10.md:7,16,19,22-23,47,75
src/evaluation/binder_10/PHASE10_REPORT.md:5,25,29,35,53,70,139,142,190,277,298
src/evaluation/binder_10/PREREG_10.md:13,15-16,48,69,87-88,92,174,210,214,221-222,225,234,237
src/evaluation/binder_10/RECOVERY_10.md:43,50,60,73
src/evaluation/binder_10/SYNTHETIC_REVIEW_10.md:19,35,43,47,49
src/evaluation/binder_10/review/precision/repro.py:1,106,108
src/evaluation/binder_10/validate_10.py:3,5,66,151,215,223,226,236,278,291-293,327-328,347,352,363,382,397,401,403,405-406,420-421,433,442,482,492,538
runs/phase10_recovery/historical_review/precision/p3.py:37
runs/phase10_recovery/historical_review/precision/p5.py:28
runs/phase10_recovery/historical_review/precision/p6.py:25
runs/phase10_recovery/historical_review/precision/p8.py:17
runs/phase10_recovery/historical_review/precision/p9.py:21
runs/phase10_recovery/historical_review/precision/repro.py:1,106,108
runs/phase10_recovery/historical_review/robustness/probe_misc.py:41
runs/phase10_recovery/historical_review/robustness/probe_unicode.py:34,37
runs/phase10_recovery/historical_review/spec_conformance/p2.py:35,37-38
runs/phase10_recovery/reviews/lost_legacy/REPORT.md:1,21,38-39,42,44
runs/phase10_recovery/reviews/lost_legacy/focused_repro.py:1,24-26,58,69,72,79
runs/phase10_recovery/reviews/lost_legacy/synthetic_probe.py:1,28-30,101,106,109-112
runs/phase10_recovery/reviews/wrongbind_structure/REVIEW.md:75
runs/phase10_recovery/working/build_report.py:27,29,47,64,84,88,94,112,117-118,130,144-145,172-174,179,207,209,225
runs/phase10_recovery/working/dev_run.py:12
runs/phase10_recovery/working/review/precision/p3.py:37
runs/phase10_recovery/working/review/precision/p5.py:28
runs/phase10_recovery/working/review/precision/p6.py:25
runs/phase10_recovery/working/review/precision/p8.py:17
runs/phase10_recovery/working/review/precision/p9.py:21
runs/phase10_recovery/working/review/precision/repro.py:1,106,108
runs/phase10_recovery/working/review/robustness/probe_misc.py:41
runs/phase10_recovery/working/review/robustness/probe_unicode.py:34,37
runs/phase10_recovery/working/review/spec_conformance/p2.py:35,37-38
runs/phase10_recovery/working/test_binder_v2.py:1,216,222,234,238-239
runs/phase10_recovery/working/test_recovery_defects.py:29
runs/phase10_recovery/working/validate_10.py:3,5,66,197,205,208,218,260,273-275,309-310,327,332,341,354,369,373,375,377-378,392-393,405,414,450,460,496
runs/phase10_recovery/working/validate_10_modes.py:17-18,35,40,49,62,77,81,83,85-86,104-105,117,126,162,172,208
runs/phase11_binder/a4_matrix.py:16
runs/phase11_binder/a4_report.py:143-146,150,176,190,247,249,266,324
runs/phase11_binder/comparison_phase10_phase11.md:9,17,64,76,90,102,143,173,179-182,187-190,200,204,246
runs/phase11_binder/write_report.py:21,36,38,61,85,87,91,98,113,125,131
```

These occurrences mean a binder arm or baseline, a saved baseline association, S3 compatibility, or the name of a historical binder review/reproduction. `PROGRESS.md:43,159` instead concern fallthrough. Matrix rows labelled legacy name the invocation environment, not Python; frozen `regress.py` selects v2 internally.

**Retrieval selector, schema fallback, and selector experiments**

```text
src/summarization/retrieval_aware.py:11,35,47,172,251,260,299-300,304,320,323-324,326-327
src/summarization/summarize.py:305,1232-1234,1239,1244,1249,1257-1258,1260-1261,1275,1301,1305-1306
configs/acceptance_config.yaml:43
configs/staging_config.yaml:39
PHASE1_DELIVERY_GAP.md:76,94,165,180,192
PHASE5_INTERVENTION.md:57,111,168
PHASE7_PORTABILITY.md:59
PROJECT_STATE.md:109-110,181
experiments/document_evidence_pipeline/CLAIM_LEDGER.md:70
experiments/document_evidence_pipeline/CONTEXT_BUDGET_REPORT.md:35,83,96,98-99,101,109,113,119-120,122,127,139-141,269,276
experiments/document_evidence_pipeline/DIAG_0549E2E9_REPORT.md:14,23,35
experiments/document_evidence_pipeline/EXPERIMENT_MATRIX.md:291,294,317
experiments/document_evidence_pipeline/LATEX_ACQUISITION_REPORT.md:298
experiments/document_evidence_pipeline/MEDICAL_RECHUNK_REPORT.md:14-16,101-102,104,110,126,129,131,137,139-140,146,159,161,187,212,222-223,228
experiments/document_evidence_pipeline/MEDICAL_SELECTOR_CONTROL_REPORT.md:24-25,30,36,41,75,115,119
experiments/document_evidence_pipeline/SELECTION_POLICY_REPORT.md:15-16,20,37,43,53,57,80,95,98,100,108,128
experiments/document_evidence_pipeline/context_budget_measure.py:4,60,99,147,150-151
experiments/document_evidence_pipeline/diag_0549e2e9.py:3,139-140,148,180,222
experiments/document_evidence_pipeline/medical_rechunk.py:95,104
experiments/document_evidence_pipeline/medical_rechunk_measure.py:60,135,138,147-148,178,188,205,221-222,224,232
experiments/document_evidence_pipeline/medical_selector_control.py:13-14,78,130,154-155,157-158,162,169
experiments/document_evidence_pipeline/phase5_intervention.py:96
experiments/document_evidence_pipeline/phase7_stepA.py:4,24,64
experiments/document_evidence_pipeline/runs/phase5_intervention/PREREGISTRATION.md:12,66
experiments/document_evidence_pipeline/selection_coverage_run.py:1,65,119-120,128,132
experiments/document_evidence_pipeline/selection_delivery_sweep.py:2,9,75-76,98
experiments/document_evidence_pipeline/verify_deadline.py:27
```

Within this group, legacy schema/chunks means missing grounded structure such as `block_type`; legacy selection/mode means the fixed-query selector. `retrieval_aware.py:172` specifically names the older table-like-text heuristic used when block-type metadata is unavailable.

**Older acquisition/representation and disabled-grounding product behavior**

```text
.github/modernize/rearchitecture/board.md:51
configs/config.example.yaml:68
configs/config.yaml:64
src/collection/semantic_scholar.py:190,253
src/processing/pdf_parser.py:127,171,182
experiments/document_evidence_pipeline/extraction_fidelity.py:4,355,380,428,435
experiments/document_evidence_pipeline/EXTRACTION_FIDELITY_REPORT.md:48,88,159
experiments/document_evidence_pipeline/EXTRACTION_TRIAGE_REPORT.md:17
experiments/document_evidence_pipeline/FINAL_REPORT.md:16,28,205,211,213,280
experiments/document_evidence_pipeline/production_ab.py:5
experiments/document_evidence_pipeline/progress.md:97,102
```

`in_legacy_pdf` and `verbatim_legacy` compare extracted claim text with the older flat-chunk PDF processing path. They do not describe binder policy or Python.

**Mixed historical inventory and unrelated authentication**

```text
src/evaluation/bottleneck_diagnosis/repository_inventory.md:96,120,136,250,253,336
backend/.env:11
```

Inventory line 96 is the proposed disambiguation policy; 120 is older PDF representation; 136 is retrieval selection; 250 is older acquisition; 253 is old chunk schema; and 336 describes claims from an older production funnel. The `.env` occurrence is only the HS256 compatibility comment; no values are included.

### Machine receipts, imported text, and search limits

The broader 68 machine-data/text files add 10,874 occurrences, primarily:

- 8,816 in `experiments/document_evidence_pipeline/runs/extraction_fidelity/fidelity.json`, chiefly repeated `in_legacy_pdf` fields.
- Frozen binder outputs, comparison receipts, matrix receipts, and review JSON: baseline binder arms, saved `legacy_cells`, compatibility test names, and policy-labelled filenames.
- `reproducibility/config/frozen_config.json:22-23`: four occurrences describing retrieval selection and old schema fallback.
- Retrieval-selection traces: selector mode or schema fallback.
- Imported paper text/XML/TeX and copied extracted text: ordinary research content, not implementation switches.

The search used `rg` with case-insensitive matching and included `src`, `tests`, `configs`, `experiments`, `docs`, `runs`, `scripts`, `backend`, `frontend`, `web`, `reproducibility`, `.github`, and top-level files, bypassing ignore rules for relevant receipts. First-party code/configuration/Markdown counts used source/configuration extensions and Markdown, including ignored helpers. Exclusions were `.git`, virtual environments, vendored `.claude`/`.impeccable` browser tooling, dependency/build/cache directories, binary PDFs and bibliographies, and raw root corpus/output trees. These are scoped repository counts, not a claim to have searched inaccessible or vendored files.

Historical temporary directories were inaccessible and excluded after the initial diagnostic:

```text
runs/phase11_binder/a4_tmp_czxnthwg
runs/phase11_binder/a4_tmp_eq2t469d
.run/onboarding-pytest-20261004211703061
```

Every Python inspection used `PYTHONIOENCODING=utf-8`, disabled bytecode writes, and loaded the existing offline guard. The guard reported its blocked startup canary PASS. No LLM or network call was made.

## 2026-10-08 Part 0: interpreter findings

The environment audit was completed before any implementation edits. No interpreter, environment, requirement, configuration or frozen artifact was changed.

- where.exe python (the executable lookup, avoiding PowerShell's where alias): C:\Users\Praka\miniconda3\python.exe; C:\Users\Praka\AppData\Local\Programs\Python\Python313\python.exe; C:\Users\Praka\AppData\Local\Microsoft\WindowsApps\python.exe.
- py -0p: default -V:3.13t points to Python313\python3.13t.exe; -V:3.13 points to Python313\python.exe.
- python --version: Python 3.10.18.
- .python-version:1 pins 3.10.18. .venv/pyvenv.cfg identifies 3.10.18 (Miniconda base); .venv-09a/pyvenv.cfg identifies regular CPython 3.13.6, not the launcher's free-threaded default.
- Canonical interpreter: C:\Users\Praka\Downloads\researchgpt-pipeline\.venv\Scripts\python.exe (3.10.18). Orchestration will assert the exact version and invoke this executable explicitly, including -m pytest. Keep .venv-09a for compatibility; retain both installed environments. A .python-version file does not override PATH or the Windows launcher.

| Evidence | Actual interpreter selection |
|---|---|
| a4_guard_resume_matrix.json | Explicit .venv and .venv-09a executable paths, 8 combinations each |
| a4_run.py:21 | Runtime directory chooses the executable |
| a4_matrix.py:9,15-18 | Both runtimes/policies; stale expected full count 239, not the retained final runner |
| run_checks.py:17 | sys.executable; runtime label alone is not provenance |
| test_portability.py:44; validate_09a.py:283; validate_09b.py:148 | Children use the parent's sys.executable |
| validate_10.py:4-11; regress.py:3 | Document .venv explicitly |
| tests/test_pipeline.py:9; experiment unit-test instructions | Unqualified python in documentation; matrix uses explicit paths |
| README.md:13,25; scripts/doctor.py:42-44 | Python >=3.10, not an exact execution pin |
| requirements.lock; requirements-dev.txt:3 | Direct dependency lock only; pytest>=8.0.0; no interpreter pin |
| CI/shebang/config inventory | No CI workflow, root pyproject/tox/pytest.ini/setup.cfg/Pipfile/runtime.txt or interpreter-selecting Python shebang found |

| Runtime/package | .venv | .venv-09a |
|---|---|---|
| Python | 3.10.18 | 3.13.6 |
| Py_GIL_DISABLED | absent | 0 |
| pytest | 9.1.1 | 9.1.1 |
| requests | 2.34.2 | 2.34.2 |
| PyYAML | 6.0.3 | 6.0.3 |
| PyMuPDF | 1.28.2 | 1.28.2 |
| NumPy | 2.2.6 | 2.5.3 |
| scikit-learn | 1.7.2 | 1.7.2 |

NumPy differs despite requirements.lock:13 specifying 2.2.6. These are compatibility comparisons across environments, not an isolated causal test of interpreter version. A future complete dependency lock should include transitive/test dependencies; no package is being changed silently here.

The eight paired historical suite outputs match after removing timings and ordering regression lines: 243 full-pytest, 37 standalone, 63 experiment and 123 regression checks per policy/runtime. Frozen regress.py:20 selects v2 internally even under a legacy-labelled invocation. S1/S2/S3 receipts themselves use 3.10.18; their 3.13 equivalence was not previously established. The rejected candidate's 252-pass matrix is not the retained source state.

Fresh read-only baseline check of all ten numeric-metric tests: both 3.10.18 and 3.13.6 produce exactly the same four known recovery failures and six passing controls. Failed nodes: test_numeric_metric_name_preserves_each_local_quantity[73Rho], [61Luma], test_real_measurement_equal_to_metric_prefix_is_retained[73], [73 mm]. No other difference was observed.

## 2026-10-08 Part 1: design decision before implementation

development-contaminated, machine-assisted, unvalidated

Retained state: S1=19, S2=25, S3 previously PASS. S3 is not a current failure. S1's 17 missing reconstructed targets and C021's two extra-mask flags are frozen reconstruction/scoring limitations; C021's mask cells are in verified gold. PF004 additionally has a target-table ambiguity because the canonical text omits table identity. No score or gold alteration is authorized. S2 includes both genuine missed equalities (C026) and desirable rejection of two improvement-to-p-value associations; a smaller S2 count alone is insufficient.

| Candidate | Root cause | Expected effects | Side-effect risk and test plan |
|---|---|---|---|
| 1. Per-mention change-role recognizer | Change nouns after a value/unit are absent from the prefix-only delta recognizer | Guard alone S1=19/S2=25; later numeric-label repair S1=19/S2=19; S3 unchanged | Lowest scope. Test pre/postposed changes, bare p-value/Dice negatives, units/uncertainty, punctuation, mixed absolute/change statements and colliding p-value cells |
| 2. Typed claim/cell compatibility | Equal numbers can denote absolute scores, changes, p-values or effect sizes | May suppress wrong associations but can add abstentions; S1/S2 effect uncertain; legacy S3 unchanged | Larger semantic surface, mixed tables and missing captions. Test a cross-product of claim/cell roles, unknown types, explicit delta columns and unit incompatibility |
| 3. Comparative expression frame | Heuristics incompletely represent endpoints, change magnitudes and coordinated quantities | Broader potential; S1/S2 changes not narrowly predictable; legacy S3 unchanged | Largest rewrite. Metamorphic tests for from/to, by, postposed changes, respectively, mixed clauses, and no unsupported arithmetic |

Choose design 1. Preserve the existing prefix cue and delta boolean contract; add an immediate post-value/unit change-noun cue with lexical and punctuation boundaries. Do not treat an entire sentence as an improvement merely because the word occurs somewhere. The gate's status semantics, candidate choice, legacy policy and default configuration remain unchanged.

Falsifiable expectations, declared before implementation:
- Stage A adds general failing-first tests only. Production decisions must equal the retained baseline exactly.
- Stage B guard: S1=19, S2=25; both improvement sweep occurrences remain unbound (their rejection status may become not_a_table_claim); no new wrong or lost associations, no added absolute bindings; four numeric-metric recovery failures remain. Bare p-values/Dice scores stay non-delta. Legacy output identical; S3 30/30, zero pair/claim differences, newline canary 0.
- Stage C numeric-label repair: recover exactly the six C026 loss occurrences, with all three correct cells; zero improvement-to-p-value associations restored; S1=19, S2=19; no other new/lost associations and no legacy change. All existing and new tests must pass.
- Any newly conflicting expectation or unexpected metric/association movement causes reversion of that stage and STOP. No speculative second patch.

Stage sequencing: Stage A is intentionally red; Stages A/B also carry the four explicitly measured baseline recovery failures until Stage C. Those exact expected failures are recorded, not skipped, xfailed or weakened. Every requested suite is run after each stage; any additional failure stops the stage. Passing guard work may be committed only with this baseline-red qualification; Stage C requires a fully green matrix. No existing test is edited.

Untouched held-out data: filename/provenance inspection found no held-out manifest and did not inspect candidate records. phase_11_scope.md:101-131 says the planned held-out set was not built. Honest construction requires an independent custodian, 12 new deduplicated papers/60 claims (40 positives,20 near misses), fixed hashes/strata/gold before predictions, hidden labels and two blinded readings. Development examples cannot be relabelled held-out.

Later end-to-end evaluation is limited to deterministic cached replay, labelled CACHED REPLAY - NOT A FRESH PRODUCTION RUN. Fresh acquisition/extraction stages are not measurable from cache. No production or real LLM calls will run.

## Stage A: bounded verification

development-contaminated, machine-assisted, unvalidated

Guard blocked; external and localhost:11434 canaries raised. Explicit interpreter paths; PYTHONIOENCODING=utf-8; no bytecode or pytest cache. Temporary files stay under runs/phase11_binder and are removed.

Source SHA-256: 31b6dbd94fc43861cd2128d5da8927e7ec11c2fa50af0477fd11423398b84da0.

Expected red checks: 4 retained numeric recovery cases and 7 failing-first change-role cases. No expectation is skipped, xfailed or changed.

| Python | Policy | Check | Result | Guard |
|---|---|---|---|---|
| 3.10.18 | v2 | Classes A-E and B boundaries | PASS: 63 passed in 0.35s | active |
| 3.10.18 | v2 | 10 retained numeric tests | EXPECTED RED: 4 failed, 6 passed in 0.23s | active |
| 3.10.18 | v2 | 18 change-role tests | EXPECTED RED: 7 failed, 11 passed in 0.24s | active |
| 3.10.18 | legacy | full pytest | EXPECTED RED: 11 failed, 260 passed in 6.58s | active |
| 3.10.18 | legacy | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.10.18 | legacy | experiment units | PASS: 63 passed, 0 failed | active |
| 3.10.18 | legacy | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |
| 3.10.18 | v2 | full pytest | EXPECTED RED: 11 failed, 260 passed in 6.07s | active |
| 3.10.18 | v2 | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.10.18 | v2 | experiment units | PASS: 63 passed, 0 failed | active |
| 3.10.18 | v2 | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |
| 3.13.6 | v2 | Classes A-E and B boundaries | PASS: 63 passed in 0.31s | active |
| 3.13.6 | v2 | 10 retained numeric tests | EXPECTED RED: 4 failed, 6 passed in 0.22s | active |
| 3.13.6 | v2 | 18 change-role tests | EXPECTED RED: 7 failed, 11 passed in 0.22s | active |
| 3.13.6 | legacy | full pytest | EXPECTED RED: 11 failed, 260 passed in 5.27s | active |
| 3.13.6 | legacy | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.13.6 | legacy | experiment units | PASS: 63 passed, 0 failed | active |
| 3.13.6 | legacy | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |
| 3.13.6 | v2 | full pytest | EXPECTED RED: 11 failed, 260 passed in 5.07s | active |
| 3.13.6 | v2 | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.13.6 | v2 | experiment units | PASS: 63 passed, 0 failed | active |
| 3.13.6 | v2 | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |

Stage A: all 16 matrix combinations and six focused checks completed with only the declared expected failures. The frozen regression selects v2 internally even for legacy-labelled invocations.

### Stage A: S3 and frozen development measurement

S3 PASS: 30/30 PDF gate records identical; 55 pairs and 18 claims with zero differences; newline canary 0. Python 3.10.18. Frozen identity function unchanged, result sink held in memory and written only here.

| Representation | Baseline S1 | Current S1 | Baseline S2 | Current S2 |
|---|---:|---:|---:|---:|
| R-prod | 9 | 9 | 11 | 11 |
| R-eval | 10 | 10 | 14 | 14 |
| R-oracle | 0 | 0 | 0 | 0 |
| Total | 19 | 19 | 25 | 25 |

Lost occurrences recovered: 0; new losses: 0; new wrong flags: 0. Cached input hashes unchanged; legacy arm exactly identical to baseline.

| Affected unit | Claim | Baseline status/cells/final | Current status/cells/final |
|---|---|---|---|
| none | identical decisions | unchanged | unchanged |

Improvement-to-p-value guard checks:

- R-prod / sweep_B / P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0: wrong_cell; none; ABSTAINED.
- R-eval / sweep_B / P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0: wrong_cell; none; ABSTAINED.

Stage A measurement PASS against the preregistered expectations. Development-contaminated, machine-assisted, unvalidated. Frozen S1 remains FAIL; S2 remains FAIL; S3 PASS.

Stage B implementation note: the 18 Stage A cases were preserved, and three general predicate/count controls were added and passed before the source change. The candidate rule used singular change nouns immediately after the parsed quantity/unit, preserved counts, and did not cross punctuation. The rejected candidate passed all 21 change-role tests before the review counterexample was added. No numeric-label change was reapplied.

## Stage B: bounded verification

development-contaminated, machine-assisted, unvalidated

Guard blocked; external and localhost:11434 canaries raised. Explicit interpreter paths; PYTHONIOENCODING=utf-8; no bytecode or pytest cache. Temporary files stay under runs/phase11_binder and are removed.

Source SHA-256: 6e0720524ae11a84fcc56dcca36e77b41eec95be1021369050362366e56c95c6.

Expected red checks: 4 retained numeric recovery cases and 0 failing-first change-role cases. No expectation is skipped, xfailed or changed.

| Python | Policy | Check | Result | Guard |
|---|---|---|---|---|
| 3.10.18 | v2 | Classes A-E and B boundaries | PASS: 63 passed in 0.52s | active |
| 3.10.18 | v2 | 10 retained numeric tests | EXPECTED RED: 4 failed, 6 passed in 0.25s | active |
| 3.10.18 | v2 | 21 change-role tests | PASS: 21 passed in 0.15s | active |
| 3.10.18 | legacy | full pytest | EXPECTED RED: 4 failed, 270 passed in 8.86s | active |
| 3.10.18 | legacy | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.10.18 | legacy | experiment units | PASS: 63 passed, 0 failed | active |
| 3.10.18 | legacy | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |
| 3.10.18 | v2 | full pytest | EXPECTED RED: 4 failed, 270 passed in 6.13s | active |
| 3.10.18 | v2 | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.10.18 | v2 | experiment units | PASS: 63 passed, 0 failed | active |
| 3.10.18 | v2 | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |
| 3.13.6 | v2 | Classes A-E and B boundaries | PASS: 63 passed in 0.51s | active |
| 3.13.6 | v2 | 10 retained numeric tests | EXPECTED RED: 4 failed, 6 passed in 0.20s | active |
| 3.13.6 | v2 | 21 change-role tests | PASS: 21 passed in 0.14s | active |
| 3.13.6 | legacy | full pytest | EXPECTED RED: 4 failed, 270 passed in 7.80s | active |
| 3.13.6 | legacy | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.13.6 | legacy | experiment units | PASS: 63 passed, 0 failed | active |
| 3.13.6 | legacy | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |
| 3.13.6 | v2 | full pytest | EXPECTED RED: 4 failed, 270 passed in 5.05s | active |
| 3.13.6 | v2 | standalone pipeline | PASS: 37 passed, 0 failed | active |
| 3.13.6 | v2 | experiment units | PASS: 63 passed, 0 failed | active |
| 3.13.6 | v2 | frozen regress | PASS: 0 failing: []; :105/:198 not_a_table_claim | active |

Stage B: all 16 matrix combinations and six focused checks completed with only the declared expected failures. The frozen regression selects v2 internally even for legacy-labelled invocations.

## Stage B STOP: absolute score misclassified as a change amount

development-contaminated, machine-assisted, unvalidated

The matrix above describes the rejected candidate, before the additional review counterexample was added. It is not a fully green result: each full-pytest invocation still had the four known numeric-metric recovery failures. A separate read-only review then exposed a new quantity-role error outside that matrix's test cases.

Exact counterexample: `The Dice scores of 0.37 increase after tuning.`

- Required absolute-score expectation (new review reproduction): `assert mention['delta'] is False, mention`.
- Candidate actual: `mention['delta'] == True`; the focused test failed with `assert True is False`.
- Mechanism: the immediate post-value pattern treated the singular spelling `increase` as a change noun. Here it is a verb with the plural subject `scores`; 0.37 is an absolute measurement, not a change magnitude. Lexical adjacency and singular spelling do not establish the grammatical relation.
- This conflicts with the preregistered requirement that absolute Dice/metric quantities remain non-delta. The confirmed error is role classification; no end-to-end lost answer or frozen metric movement is claimed for this synthetic sentence.

The counterexample was appended to the new task-owned test file as `test_predicates_and_event_counts_are_not_change_amounts[plural_score_predicate]`. All earlier expectations were preserved. The candidate failed this test on Python 3.10.18, with the offline guard active. The six-line Stage B source change was then removed. No second implementation was attempted and the numeric-label fix was not reapplied.

Reversion evidence: `git diff -- src/evidence/binder_v2.py` is empty, and its SHA-256 is again `31b6dbd94fc43861cd2128d5da8927e7ec11c2fa50af0477fd11423398b84da0`, exactly the Stage A retained source. No pre-existing test, gate semantics, policy default, frozen evaluator, frozen evidence or scoring file was changed.

| Post-reversion check | Python 3.10.18 | Python 3.13.6 |
|---|---|---|
| New change-role file, now 22 tests | 7 expected failures, 15 passes | 7 expected failures, 15 passes |
| Existing numeric-metric file, unchanged, 10 tests | 4 known failures, 6 passes | 4 known failures, 6 passes |
| Combined focused run | 11 failed, 21 passed | 11 failed, 21 passed |
| New plural-score predicate counterexample | PASS | PASS |
| Offline guard startup canary | PASS, blocked | PASS, blocked |

The seven change-role failures are the same four postposed-role cases, two absolute-cell collision cases and mixed-quantity role assertion demonstrated in Stage A. The four numeric-metric failures are the same retained baseline cases listed in Part 0. Thus the reversion restores the known behavior, including its unresolved bugs. These tests are intentionally red reproductions, not a passing implementation stage.

| Criterion | Retained baseline | Last measured result (Stage A) | Disposition after Stage B reversion |
|---|---|---|---|
| S1 wrong-binding flags | 19 | 19 | Unchanged retained source; zero-failure criterion FAIL |
| S2 lost-binding occurrences | 25 | 25 | Unchanged retained source; zero-failure criterion FAIL |
| S3 PDF identity | PASS | 30/30 identical; 55 pair and 18 claim outputs unchanged; newline canary 0 | Last measured PASS applies to identical retained source |

Stage B S3 and development measurement were not run after the new counterexample triggered STOP. No S1/S2 improvement is claimed for that candidate. Stage C, current held-out evaluation and current end-to-end replay were not run. The matrix and S3 were not repeated after reverting because the source hash matches the already measured Stage A source; the focused runs above verify the reversion. Frozen `regress.py:105` and `:198` returned the expected `not_a_table_claim` in all four Stage A and all four Stage B regression invocations.

No untouched held-out set has been established by the provenance inspection. Candidate records were not opened. The honest construction plan is recorded in Part 1. This session therefore cannot establish generalization, a current end-to-end funnel, or a largest end-to-end bottleneck. The six repeated C026 quantity-conflict occurrences are a demonstrated development-set binding mechanism, not evidence about the largest production loss stage. Binding recovery alone would still not guarantee a returned answer (the earlier C013 recovery remained abstained by the final gate).

Proposed next step, not implemented: revise the change-role design to require a grammatical amount relation while distinguishing absolute scores used as subjects of change predicates. Preserve this counterexample and the bare p-value, absolute-score, event-count, punctuation and mixed-quantity controls. Only a separately authorized bounded stage that passes these controls should precede another numeric-label repair attempt. No claim-specific exception or scoring change is proposed.

Persistent files created or changed in this task:

- Updated existing report: `C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\comparison_phase10_phase11.md`. This remains the only report; no duplicate JSON/Markdown report was created.
- New failing-first test file, retained uncommitted: `C:\Users\Praka\Downloads\researchgpt-pipeline\tests\test_binder_v2_change_roles.py`.
- Temporarily changed and fully reverted: `C:\Users\Praka\Downloads\researchgpt-pipeline\src\evidence\binder_v2.py`.

The pre-existing untracked numeric-metric test file was not edited or staged. Test temporary directories were confined to `C:\Users\Praka\Downloads\researchgpt-pipeline\runs\phase11_binder\` and removed by the test orchestration. Existing unrelated untracked files were left alone. Audit/preregistration commit: `a5563e026c67b53a1ce58960d02bfe90e3d31b26`. The completed verification and STOP report will be committed separately; no implementation-stage commit is warranted. A single user-authorized GitHub push of the report commits follows, with the actual result reported to the user. No production run or LLM call occurred.
