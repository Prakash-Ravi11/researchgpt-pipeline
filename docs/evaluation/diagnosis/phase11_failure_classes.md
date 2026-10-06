# Phase 11 failure-class diagnosis (read-only)

Classification before implementation. All labels are **machine-assisted, unvalidated**, and the historical evaluation is **development-contaminated**. Identifiers below are traceability keys only; none may become a code condition or synthetic fixture.

## Evidence and limits

- Sources: `src/evaluation/binder_10/results.json` (`run.vs_legacy.v2`, `criteria.v2`) and `validation_10.json`; no evaluation re-run or source edit was performed for this classification.
- The validation record confirms 180 passing pytest checks per policy/runtime, 123 regression expectations, and no real LLM run. Product changes are five internal statuses only; no product S1/S2 violation is present.
- There are 19 gold S1 occurrences across the two representations, 5 gold S2 occurrences, 22 sweep S2 associations, and 1 distinct audited S1 mismatch (two representation occurrences). Rows are not independent claims; do not pool them into an accuracy rate.
- All 17 canonical-pair S1 occurrences have an empty reconstructed target set. They are classified **other**, not silently blamed on binder normalization or removed from the frozen score.
- The two real-claim S1 occurrences have extra cells outside the reconstructed target subset. This motivates class B synthetics, but does not prove those cells are semantically wrong.
- C/D labels are candidate mechanism classes from stored context, not causal proof. Only general failing synthetic cases can justify changes. D is a safety-constrained preservation mechanism, not an excuse to recover every old binding.

## Complete violation inventory

| Representation | Violation | Unit | Class | Evidence / interpretation | JSON pointer |
| --- | --- | --- | --- | --- | --- |
| R-prod | wrong_binds | PF008 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[0] |
| R-prod | wrong_binds | PF010 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[1] |
| R-prod | wrong_binds | PF026 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[2] |
| R-prod | wrong_binds | PF027 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[3] |
| R-prod | wrong_binds | PF028 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[4] |
| R-prod | wrong_binds | PF038 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[5] |
| R-prod | wrong_binds | PF039 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[6] |
| R-prod | wrong_binds | PF040 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-prod.wrong_binds[7] |
| R-prod | wrong_binds | C021 | B / other | Extra selected cells outside reconstructed gold subset; multi-binding shape, with target-reconstruction caveat. No semantic relabeling. | run.vs_legacy.v2.R-prod.wrong_binds[8] |
| R-prod | lost_verified | C026 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-prod.lost_verified[0] |
| R-prod | lost_binds | C024 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-prod.lost_binds[0] |
| R-prod | lost_binds | C026 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-prod.lost_binds[1] |
| R-prod | lost_binds | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#0 | D / other | Implicit subject and multiple values; preserved legacy row is not proof of independent subject or complete coverage. C-style row decoration alone is insufficient. | run.vs_legacy.v2.R-prod.lost_binds[2] |
| R-prod | lost_binds | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#1 | D / other | Implicit subject and multiple values; preserved legacy row is not proof of independent subject or complete coverage. C-style row decoration alone is insufficient. | run.vs_legacy.v2.R-prod.lost_binds[3] |
| R-prod | lost_binds | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-prod.lost_binds[4] |
| R-prod | lost_binds | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-prod.lost_binds[5] |
| R-prod | lost_binds | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-prod.lost_binds[6] |
| R-prod | lost_binds | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-prod.lost_binds[7] |
| R-prod | lost_binds | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:165#0 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-prod.lost_binds[8] |
| R-eval | wrong_binds | PF004 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[0] |
| R-eval | wrong_binds | PF008 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[1] |
| R-eval | wrong_binds | PF010 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[2] |
| R-eval | wrong_binds | PF026 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[3] |
| R-eval | wrong_binds | PF027 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[4] |
| R-eval | wrong_binds | PF028 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[5] |
| R-eval | wrong_binds | PF038 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[6] |
| R-eval | wrong_binds | PF039 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[7] |
| R-eval | wrong_binds | PF040 | other | No reconstructed gold target (gold=[]); conservative scorer violation, not independently established semantic error. | run.vs_legacy.v2.R-eval.wrong_binds[8] |
| R-eval | wrong_binds | C021 | B / other | Extra selected cells outside reconstructed gold subset; multi-binding shape, with target-reconstruction caveat. No semantic relabeling. | run.vs_legacy.v2.R-eval.wrong_binds[9] |
| R-eval | lost_verified | PF005 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_verified[0] |
| R-eval | lost_verified | C013 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_verified[1] |
| R-eval | lost_verified | C026 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-eval.lost_verified[2] |
| R-eval | lost_verified | C085 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_verified[3] |
| R-eval | lost_binds | C012 | D (semantic veto) | Claim and bound cell explicitly name different tables. Legacy preservation must not override the table rejection. | run.vs_legacy.v2.R-eval.lost_binds[0] |
| R-eval | lost_binds | C013 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_binds[1] |
| R-eval | lost_binds | C024 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_binds[2] |
| R-eval | lost_binds | C026 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-eval.lost_binds[3] |
| R-eval | lost_binds | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#0 | D / other | Implicit subject and multiple values; preserved legacy row is not proof of independent subject or complete coverage. C-style row decoration alone is insufficient. | run.vs_legacy.v2.R-eval.lost_binds[4] |
| R-eval | lost_binds | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#1 | D / other | Implicit subject and multiple values; preserved legacy row is not proof of independent subject or complete coverage. C-style row decoration alone is insufficient. | run.vs_legacy.v2.R-eval.lost_binds[5] |
| R-eval | lost_binds | P004:3c9b838a0b36d032a86ffe582f55b3583fd4a815:113#0 | D (semantic veto) | Claim and bound cell explicitly name different tables. Legacy preservation must not override the table rejection. | run.vs_legacy.v2.R-eval.lost_binds[6] |
| R-eval | lost_binds | P004:3c9b838a0b36d032a86ffe582f55b3583fd4a815:116#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_binds[7] |
| R-eval | lost_binds | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_binds[8] |
| R-eval | lost_binds | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_binds[9] |
| R-eval | lost_binds | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | C / D | Decorated/cited row or hierarchical header/structured numeric value; formatting/linking loss is a hypothesis. D requires raw verification; no automatic reinstatement. | run.vs_legacy.v2.R-eval.lost_binds[10] |
| R-eval | lost_binds | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-eval.lost_binds[11] |
| R-eval | lost_binds | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:165#0 | B / D | Whole-claim completeness/subject support differs from legacy first-cell success. D only if raw verification and full required coverage can pass. | run.vs_legacy.v2.R-eval.lost_binds[12] |
| R-prod + R-eval | audit | 28be140170be | A | Both independent readers: a confidence threshold is linked to a metric cell for another model/class. Confirmed quantity and subject mismatch. | criteria.v2.S1.new_binds_wrong_or_unaudited |

## Implications for the registered classes

- **A:** one independently confirmed numeric-equality error. Reproduce with invented setting/metric values and multiple models; require local quantity type and subject agreement.
- **B:** extra-cell and partial-coverage shapes occur. Preserve whole-claim coverage; do not discard correct comparison cells simply to match an incomplete reconstructed gold subset.
- **C:** decorate synthetic labels/headers/values and test exact raw support. Some formatting cases may already pass; preserve those controls and demonstrate any newly fixed loss before coding.
- **D:** retain a legacy bind only after the same verifier and completeness checks, with semantic vetoes. A historical wrong-table result is a concrete reason a blanket fallback is unsafe.
- **Other:** target reconstruction and incomplete evidence remain visible. This task cannot repair them by changing the frozen evaluator or suppressing semantically supported cells.

## Frozen source hashes

- `src/evaluation/binder_10/results.json`: `832e47595a3039af806c91027a2b7c2ed5faf05aba5dd4c7de5c7eb079908095`.
- `src/evaluation/binder_10/validation_10.json`: `6f9bd5f6979b41840c131e8105b56b6c0160823e6d6f4dfb12968e5f496212a7`.
