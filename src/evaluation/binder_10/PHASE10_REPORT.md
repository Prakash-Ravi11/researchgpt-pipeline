# Phase 10 Binder v2 recovery and measurement report

**Decision: keep Binder v2 experimental. Do not enable v2 or v2_llm.** S1 and S2 fail; S3 passes. The implementation, recovery, synthetic validation, measurement and independent PDF audit are complete. This is a completed experiment with a failed release decision, not a production-ready binder.

The measured code is frozen at `c805cf4` on `exp/phase10-binder`. `binder_policy` still resolves to `legacy`; `fallthrough_policy=table_value_guard` and `borderless_policy=off` remain unchanged. No real LLM was run, because the brief forbids using it to rescue a failing deterministic binder. No merge into the default branch is authorized by this report.

All gold labels and new PDF audit verdicts are **machine-assisted, unvalidated**. Pair and real-claim units overlap and are reported separately; representation arms are not independent samples. Correct coverage is not accuracy.

## Recovery and provenance (requested items 1-7)

- Starting branch: `exp/phase10-binder`; starting HEAD: `408137e`.
- Already committed: failure map `afe1488`, preregistration `408137e`. Acceptance reference `6ed2434`; default verification and 09B reference `2d61f3c`.
- Uncommitted before recovery: the +37/-0 binder router in `src/evidence/gate.py`. Unrelated untracked `docs/diagnosis/`, `out/`, and `src/evaluation/candidate_gold/` were preserved.
- Recovered exact scratch files: the 62,827-byte precision-first rewrite, original tests, regression and validation harnesses, development/performance probes, first-review reproductions, and the review2 snapshot. No reconstruction from partial text was needed.
- The 76-file byte-for-byte backup is outside Git at `C:/Users/Praka/Downloads/recovery_phase10/20261004_exact/`. [recovery_manifest.json](recovery_manifest.json) records paths, original timestamps and SHA-256 values; [RECOVERY_10.md](RECOVERY_10.md) records the initial inventory.
- Workflow/session records recovered: both workflow records, second-review transcripts/metadata/journal, and workflow scripts. Transcript source reads matched the surviving snapshot. All four second-review agents started and failed at the weekly usage limit; none executed probes or produced completed findings. The wrapper's completed status was not accepted as a clean review.
- Original Binder v2 SHA-256: `52702fb251905f1a0edf7a499c499fb521a6e80f3fcd0d47ee150a5489c37677`. It matched `review2/binder_v2_under_review.py` exactly.
- Final integrated Binder v2 SHA-256: `4b04a848c5e8ce57f8d1fa42e26487f5362be3456549eceab0405442df881d3c`.
- The subsequently mentioned `New Text Document.txt` was empty (0 bytes); it supplied no additional command details.

## Confirmed defects and fixes (items 8-9)

The fresh four-lens synthetic review confirmed uncertainty/CI detachment; truncated Unicode or spelled-out units; negated equality; caption quantity overriding a conflicting cell axis; ignored lowercase cohort qualifiers; percent contamination across unrelated quantities; literal own-method label rejection; a verifier trusting precomputed links; and judge spans accepted despite being absent from the supplied prompt or not verbatim in source. General fixes and runnable before/after evidence are listed individually in [SYNTHETIC_REVIEW_10.md](SYNTHETIC_REVIEW_10.md:7).

Full-suite integration also exposed numeric row identifiers treated as values/compound names, incomplete caption context, and weak generic quantity/subject precedence. Eight additional synthetic checks cover the fixes and negative controls. Caption continuation requires the same page, exact adjacent character offsets, and a short qualifying continuation. The historical legacy test now explicitly selects legacy without changing its identity assertions. Correct `respectively` coordination may still safely abstain.

Before measurement, the recovered driver was corrected to count uncapped candidates, compare claim/cell associations, retain full text, generate crop plus text evidence, reject missing or insufficient audits, and enforce S3 cardinalities. The gold, frozen evaluator, preregistration, 09A/09B artifacts and configs were not changed. No binder or evaluator changes were made after measurement.

Implementation evidence: `src/evidence/binder_v2.py:284` (cell parsing), `:408` (context), `:590` (claim framing), `:756` (links), `:885` (raw verifier), `:1042` (judge), `:1087` (binding), `:1217` (gate); `src/evidence/gate.py:541` (legacy fallback). Driver definitions: `validate_10.py:223`, `:253`, `:326`, `:430`, `:480`.

## Validation before measurement (items 10-16)

| Check | Python 3.10.18 | Python 3.13.6 |
| --- | --- | --- |
| Full pytest, legacy | 180 passed, 0 failed | 180 passed, 0 failed |
| Full pytest, v2 | 180 passed, 0 failed | 180 passed, 0 failed |
| Standalone pipeline script | 37 passed, 0 failed | 37 passed, 0 failed |
| Experiment unit script | 63 passed, 0 failed | 63 passed, 0 failed |
| Recovered regression expectations | 123 passed, 0 failed | 123 passed, 0 failed |
| Original Binder v2 tests (included in pytest) | 19 passed | 19 passed |
| Recovery tests (included in pytest) | 60 passed | 60 passed |

The 60 recovery checks include 51 preserved cases, one verifier/judge contract test with six safety checks, and eight integration checks. No synthetic wrong bindings remained in the covered cases; this is not a proof over unseen inputs. Invalid mocked LLM responses raise the required STOP exception. Complete decisions on 51 fixtures match across both runtimes and hash seeds 0/7: `f21dd02bd4add11e1e78e814c0bff96da0b9f3b6d58a005bd764368fbaed75b7`.

The 135-value/1,200-cell stress case produces about 98 KB of trace and takes about 0.66 s on 3.10 / 0.50 s on 3.13. The 3.13 environment initially lacked scikit-learn; installing its existing project pin `scikit-learn==1.7.2` resolved the standalone pipeline's six import failures. No project dependency was added.

S3: **30/30 PDF gate records identical**, zero differences on all 55 pairs and 18 claims, newline canary **0**, against preregistered start `afe1488`. Both full suites and S3 passed before measurement. Logs and immutable raw-output hashes are indexed in [validation_10.json](validation_10.json).

Commands used: `python -B -m pytest -p no:cacheprovider tests/ src/evaluation/bottleneck_diagnosis/ --ignore=tests/test_pipeline.py -q --tb=short` under each policy/runtime; standalone `tests/test_pipeline.py`; `python -B -m tests.test_pipeline_units` from `experiments/document_evidence_pipeline`; `python -B src/evaluation/binder_10/regress.py`; then `validate_10.py identity`, `run`, `audit`, and `finalize`. Python bytecode and pytest plugin autoload were disabled for pytest.

## Frozen measurement (items 19-20)

The 55-pair/18-real-claim measurement ran on 2026-10-05 after the prerequisites. All ten deterministic arms (legacy, v2, eight ablations) completed. The report and audit were finalized on 2026-10-06. R-prod uses cached production extraction; R-eval uses the preregistered borderless records only for evaluation; R-oracle contains gold cells for three claims and is an upper bound, not product performance.


| Representation | Unit | N | Bound correct L -> v2 | Wrong L -> v2 | Correct gains | Correct losses | Returned correct L -> v2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-prod | pairs | 55 | 4 -> 23 | 0 -> 8 | 19 | 0 | 4 -> 5 |
| R-prod | claims | 18 | 2 -> 3 | 0 -> 1 | 2 | 1 | 2 -> 2 |
| R-eval | pairs | 55 | 6 -> 28 | 1 -> 9 | 23 | 1 | 4 -> 5 |
| R-eval | claims | 18 | 4 -> 4 | 1 -> 1 | 3 | 3 | 2 -> 2 |
| R-oracle | pairs | 12 | 6 -> 12 | 0 -> 0 | 6 | 0 | 0 -> 0 |
| R-oracle | claims | 3 | 0 -> 1 | 0 -> 0 | 1 | 0 | 0 -> 0 |


**Scoring qualification:** all eight R-prod wrong canonical units, and all nine R-eval wrong canonical units, have no reconstructed gold target in the cached representation (`gold=[]`). The driver conservatively counts their bindings as wrong. C021 can be both `bound_correct` under the unchanged evaluator's first-cell check and `wrong_bind` under S1's any-extra-cell check. These are frozen scoring outcomes, not a claim that every reported wrong unit was independently proven to select the wrong semantic cell. Known wrapping/ligature/subscript reconstruction issues remain disclosed; no post-result scoring adjustment was made. The independent sweep audit below supplies a separate semantic safety check.

### Candidate recall

Recall is conditional on an available reconstructed gold cell. The numerator uses any gold target in a claim's value-matching candidate sets, not all gold targets recovered. Candidate-set median/max count candidates per parsed mention, including zero-size sets. Legacy has no equivalent candidate trace; its stored zero is **not a measured 0% recall**.


| Representation | Unit | Gold in candidates / represented | Represented / all units | Median | Max |
| --- | --- | --- | --- | --- | --- |
| R-prod | pairs | 23/23 | 23/55 | 0.0 | 3 |
| R-prod | claims | 7/7 | 7/18 | 1.0 | 3 |
| R-eval | pairs | 32/35 | 35/55 | 1.0 | 3 |
| R-eval | claims | 13/15 | 15/18 | 1.0 | 3 |
| R-oracle | pairs | 12/12 | 12/12 | 1.0 | 1 |
| R-oracle | claims | 3/3 | 3/3 | 1 | 1 |


### Gate-level returns and product changes


| Representation | Unit | Gate items L -> v2 | Bound L -> v2 | Returned with bind L -> v2 | New associations | Lost associations |
| --- | --- | --- | --- | --- | --- | --- |
| R-prod | sweep_A | 96 -> 55 | 2 -> 2 | 1 -> 1 | 6 | 2 |
| R-prod | sweep_B | 5285 -> 5274 | 9 -> 7 | 5 -> 2 | 15 | 7 |
| R-prod | product | 75 -> 75 | 0 -> 0 | 0 -> 0 | 0 | 0 |
| R-eval | sweep_A | 96 -> 55 | 4 -> 3 | 1 -> 1 | 8 | 4 |
| R-eval | sweep_B | 5285 -> 5274 | 11 -> 13 | 5 -> 2 | 22 | 9 |


Sweep A starts from the same 48 claims; gate item counts differ because v2 preserves `et al.` sentence context. Sweep B uses every chunk in the same 16 papers. These are gate-level verified-binding counts, not independently audited accuracy. The 75 product items have **zero verified binds under both arms**, with no binding gains or losses. Five item statuses change from `not_bindable` to `not_a_table_claim`; all product final decisions, abstention reasons, text and cells are unchanged. The five exact items and transitions are retained in `validation_10.json.product_item_changes`. Product coverage of the 18 gold claims remains 3/18 at the gate; 15/18 are absent earlier in the product path (pre-Phase-10 acceptance evidence).

### Independent PDF audit


All 22 distinct new claim/cell bindings (51 occurrences across arms/units) have PDF crops and text layers, and two independent reviewer verdicts. 21 receive two yes votes; 1 fail the prescribed check; 0 have reviewer disagreement. Any no or disagreement counts as wrong. Missing audits: 0. See [audit/packets.json](audit/packets.json) and the two `audit/verdicts_reviewer_*.json` files. Labels are machine-assisted, unvalidated.


| Packet | Paper | Page | Bound row | Bound column | Independent verdicts |
| --- | --- | --- | --- | --- | --- |
| 12e5fadea630 | P008 | 7 | Ours | Dice↑ | yes / yes |
| 180698941f64 | P001 | 13 | Average | Ours | yes / yes |
| 1eefc5cd27ca | P006 | 15 | Pituitary | YOLOv7 / Box | yes / yes |
| 28be140170be | P006 | 15 | Glioma | YOLOv5 / Mas k | NO / NO |
| 3872c6f1b76f | P006 | 15 | Glioma | YOLOv7 / Box | yes / yes |
| 387bb2d51882 | P006 | 14 | All | YOLOv5 / Box | yes / yes |
| 398c84f99e10 | P015 | 11 | FetalSynthSeg | DSC / dHCPT1w | yes / yes |
| 44c1ebe1dba4 | P006 | 14 | All | YOLOv5 / Mas k | yes / yes |
| 4dd0b712e2bd | P006 | 15 | Pituitary | YOLOv7 / Mas k | yes / yes |
| 550d8078b328 | P006 | 15 | Glioma | YOLOv7 / Mas k | yes / yes |
| 7028128071ef | P006 | 15 | Pituitary | YOLOv5 / Box | yes / yes |
| 79c0d2eacd58 | P015 | 9 | SynthSeg | Global | yes / yes |
| 8166968c5fcb | P006 | 15 | Pituitary | YOLOv5 / Mas k | yes / yes |
| 90e37f4dc19e | P008 | 7 | DSRNet | Dice↑ | yes / yes |
| 94dfd9110c54 | P001 | 13 | Average | nnU-Net | yes / yes |
| a2f67993ec09 | P001 | 13 | Average | Ours | yes / yes |
| a9d2d454a148 | P015 | 9 | FaBiAN | Global | yes / yes |
| c964b994cb83 | P006 | 15 | Glioma | YOLOv5 / Box | yes / yes |
| dd7a91e9e681 | P006 | 14 | All | YOLOv7 / Mas k | yes / yes |
| e71ef722f7a1 | P006 | 14 | All | YOLOv7 / Box | yes / yes |
| f06ffa1cc376 | P006 | 15 | Glioma | YOLOv5 / Mas k | yes / yes |
| fde30147edcf | P015 | 9 | FetalRealSeg | Global | yes / yes |


- **28be140170be**: The claim concerns confidence thresholds selected to achieve F1=0.92, and assigns the 0.53 thresholds to YOLOv7. The bound Table VI cell instead reports mAP@0.5:0.95=0.53 for YOLOv5 mask detection on Glioma. Both the quantity and model/class subject differ; equal numeric text does not establish this binding. | The claim's 0.53 is an ideal confidence threshold for YOLOv7 box/mask predictions at an F1 score of 0.92 (canonical PDF page 14). The bound Table VI cell is YOLOv5 mask mAP@0.5:0.95 for glioma. Both the quantity and the model/class context differ; equal numeric text does not establish this binding.


### S1/S2/S3 and every failing item


| Criterion | Result | Evidence |
| --- | --- | --- |
| S1 zero wrong binds | FAIL | 9 R-prod / 10 R-eval gold-unit violations; 1 distinct new-bind audit failures |
| S2 zero verified binds lost | FAIL | R-prod: 1 gold claim + 9 sweep associations; R-eval: 1 gold pair + 3 gold claims + 13 sweep associations |
| S3 legacy identity | PASS | 30/30 PDF records; 55 pairs and 18 claims identical; newline canary 0 |


These failures block enablement despite the correct gains. All exact claim texts, cells and occurrence identities are preserved in `results.json` -> `criteria.v2` and `run.vs_legacy.v2`; no item is removed based on a post-result interpretation.


- **R-prod, S1 gold units:** pairs `PF008`, pairs `PF010`, pairs `PF026`, pairs `PF027`, pairs `PF028`, pairs `PF038`, pairs `PF039`, pairs `PF040`, claims `C021`.

- **R-prod, S2 gold units:** claims `C026`.

- **R-eval, S1 gold units:** pairs `PF004`, pairs `PF008`, pairs `PF010`, pairs `PF026`, pairs `PF027`, pairs `PF028`, pairs `PF038`, pairs `PF039`, pairs `PF040`, claims `C021`.

- **R-eval, S2 gold units:** pairs `PF005`, claims `C013`, claims `C026`, claims `C085`.


Every lost sweep association (product has none):


| Rep | Kind | Unit | Row | Column | Value |
| --- | --- | --- | --- | --- | --- |
| R-prod | sweep_A | C024 | RCNN [55] | Recall | 95.0% |
| R-prod | sweep_A | C026 | Ours | Dice↑ | 0.87±0.06 |
| R-prod | sweep_B | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#0 | Proposed Method | Whole Tumor Dice (%) | 88.7 |
| R-prod | sweep_B | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#1 | Proposed Method | Whole Tumor Dice (%) | 88.7 |
| R-prod | sweep_B | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | YOLOv7 (Proposed) | Precision | 93.5% |
| R-prod | sweep_B | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | YOLOv5 (Proposed) | Precision | 93.6% |
| R-prod | sweep_B | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | RCNN [55] | Recall | 95.0% |
| R-prod | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | Ours | Dice↑ | 0.87±0.06 |
| R-prod | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:165#0 | Ours | Dice↑ | 0.87±0.06 |
| R-eval | sweep_A | C012 | UM-CAM+SPL (ours) | Validation set / DSC (%) | 89.76±5.09* |
| R-eval | sweep_A | C013 | UM-CAM+SPL (ours) | Test set / DSC (%) | 90.22±3.75* |
| R-eval | sweep_A | C024 | RCNN [55] | Recall | 95.0% |
| R-eval | sweep_A | C026 | Ours | Dice↑ | 0.87±0.06 |
| R-eval | sweep_B | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#0 | Proposed Method | Whole Tumor Dice (%) | 88.7 |
| R-eval | sweep_B | P003:380729d6b9650ea4b8cb7e4325606e30cdd3b727:157#1 | Proposed Method | Whole Tumor Dice (%) | 88.7 |
| R-eval | sweep_B | P004:3c9b838a0b36d032a86ffe582f55b3583fd4a815:113#0 | UM-CAM+SPL (ours) | Validation set / DSC (%) | 89.76±5.09* |
| R-eval | sweep_B | P004:3c9b838a0b36d032a86ffe582f55b3583fd4a815:116#0 | UM-CAM+SPL (ours) | Test set / DSC (%) | 90.22±3.75* |
| R-eval | sweep_B | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | YOLOv7 (Proposed) | Precision | 93.5% |
| R-eval | sweep_B | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | YOLOv5 (Proposed) | Precision | 93.6% |
| R-eval | sweep_B | P006:562fa0fc542863477a8d86985bf4ac02654fb4f8:315#0 | RCNN [55] | Recall | 95.0% |
| R-eval | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:107#0 | Ours | Dice↑ | 0.87±0.06 |
| R-eval | sweep_B | P008:6890f2eb4b55bfadce53bd82f0ed2b39cb0f2709:165#0 | Ours | Dice↑ | 0.87±0.06 |


### Ablations

Each entry is bound-correct pairs / real claims. Wrong counts are S1 gold pairs / claims. The ablations are diagnostics, not alternate enablement candidates. Full return, abstention and comparison records for every arm are in `results.json.run`.


| Arm | R-prod correct | R-eval correct | Oracle correct | R-prod wrong | R-eval wrong |
| --- | --- | --- | --- | --- | --- |
| legacy | 4 / 2 | 6 / 4 | 6 / 0 | 0 / 0 | 1 / 1 |
| v2 | 23 / 3 | 28 / 4 | 12 / 1 | 8 / 1 | 9 / 1 |
| v2-caption_quantity | 23 / 3 | 28 / 3 | 12 / 0 | 8 / 1 | 9 / 1 |
| v2-column_subject | 23 / 2 | 28 / 2 | 12 / 1 | 8 / 0 | 9 / 0 |
| v2-own_alias | 23 / 2 | 28 / 2 | 12 / 1 | 8 / 1 | 9 / 1 |
| v2-synonyms | 23 / 3 | 28 / 4 | 12 / 0 | 8 / 1 | 9 / 1 |
| v2-count_attribute | 23 / 3 | 28 / 4 | 12 / 1 | 8 / 1 | 9 / 1 |
| v2-multi_binding | 23 / 4 | 28 / 5 | 12 / 1 | 8 / 1 | 9 / 1 |
| v2-table_mention | 23 / 3 | 28 / 4 | 12 / 1 | 8 / 1 | 9 / 1 |
| v2-gate_fixes | 23 / 3 | 28 / 4 | 12 / 1 | 8 / 1 | 9 / 1 |


Disabling multi-binding increases single-cell claim coverage while preserving wrong-bind violations; it does not satisfy the required complete-comparison contract. Caption quantity and synonyms contribute to oracle capability; own-alias contributes to returned verified claims. No ablation eliminates S1 failures. No ablation was promoted into a post-result code change.

### Abstention codes and per-claim failure stages

Complete counters for both policies, all representations and all units are in `results.json.run.summary`. The following v2 sweep counters retain even rare failure reasons:


| Representation | Unit | Abstention reason | Count |
| --- | --- | --- | --- |
| R-prod | sweep_A | binding_wrong_cell | 4 |
| R-prod | sweep_A | bound_to_other_table | 1 |
| R-prod | sweep_A | deterministic_verification_failed | 1 |
| R-prod | sweep_A | evidence_span_not_found_in_paper_chunks | 4 |
| R-prod | sweep_A | ownership_unverified | 3 |
| R-prod | sweep_A | partial_binding | 4 |
| R-prod | sweep_A | table_value_unbound | 6 |
| R-prod | sweep_A | unverifiable_binding | 28 |
| R-prod | sweep_B | attributed_to_cited_work | 704 |
| R-prod | sweep_B | binding_wrong_cell | 33 |
| R-prod | sweep_B | bound_to_ablation_table | 1 |
| R-prod | sweep_B | bound_to_other_table | 4 |
| R-prod | sweep_B | deterministic_verification_failed | 1 |
| R-prod | sweep_B | duplicate_quantity_context | 2 |
| R-prod | sweep_B | metric_value_out_of_range | 2 |
| R-prod | sweep_B | ownership_unverified | 1087 |
| R-prod | sweep_B | partial_binding | 12 |
| R-prod | sweep_B | table_value_unbound | 196 |
| R-prod | sweep_B | unverifiable_binding | 2732 |
| R-eval | sweep_A | attributed_to_cited_work | 1 |
| R-eval | sweep_A | binding_wrong_cell | 16 |
| R-eval | sweep_A | bound_to_other_table | 2 |
| R-eval | sweep_A | deterministic_verification_failed | 1 |
| R-eval | sweep_A | evidence_span_not_found_in_paper_chunks | 3 |
| R-eval | sweep_A | ownership_unverified | 2 |
| R-eval | sweep_A | partial_binding | 6 |
| R-eval | sweep_A | table_value_unbound | 17 |
| R-eval | sweep_A | unverifiable_binding | 1 |
| R-eval | sweep_B | attributed_to_cited_work | 1684 |
| R-eval | sweep_B | binding_wrong_cell | 50 |
| R-eval | sweep_B | bound_to_ablation_table | 1 |
| R-eval | sweep_B | bound_to_other_table | 10 |
| R-eval | sweep_B | deterministic_verification_failed | 1 |
| R-eval | sweep_B | duplicate_quantity_context | 2 |
| R-eval | sweep_B | metric_value_out_of_range | 2 |
| R-eval | sweep_B | ownership_unverified | 1568 |
| R-eval | sweep_B | partial_binding | 17 |
| R-eval | sweep_B | table_value_unbound | 574 |
| R-eval | sweep_B | unverifiable_binding | 676 |


Per-claim transitions, using the preregistered failure-map definitions:


| Claim | Product coverage | R-prod | R-eval | R-oracle |
| --- | --- | --- | --- | --- |
| C005 | reaches gate | representation -> representation | candidate_recall -> gate | - |
| C010 | product | gate -> none | gate -> none | - |
| C012 | product | representation -> representation | representation -> representation | verification -> linking |
| C013 | reaches gate | representation -> representation | gate -> linking | - |
| C021 | product | candidate_recall -> gate | candidate_recall -> gate | - |
| C025 | product | representation -> representation | candidate_recall -> candidate_recall | - |
| C026 | product | gate -> ranking | gate -> ranking | - |
| C027 | product | verification -> none | verification -> none | - |
| C034 | product | representation -> representation | candidate_recall -> linking | - |
| C035 | product | representation -> representation | candidate_recall -> linking | - |
| C041 | product | candidate_recall -> linking | candidate_recall -> linking | - |
| C042 | product | candidate_recall -> linking | candidate_recall -> linking | - |
| C045 | product | candidate_recall -> linking | candidate_recall -> linking | - |
| C048 | product | representation -> representation | candidate_recall -> candidate_recall | - |
| C052 | product | representation -> representation | candidate_recall -> linking | - |
| C057 | reaches gate | representation -> representation | representation -> representation | candidate_recall -> gate |
| C058 | product | representation -> representation | representation -> representation | verification -> linking |
| C085 | product | representation -> representation | gate -> linking | - |


The legacy stage function labels successful structural binds `gate` without distinguishing a successful gate return; v2 uses `none` for returned-correct claims. Thus `gate -> none` alone is not a new gain. The stage classifier also uses the evaluator's bound-correct field, so S1 extra-cell violations must be read separately. Definitions are frozen at `validate_10.py:276` and `:293`.


- **R-prod v2 stages:** representation 11, none 2, gate 1, ranking 1, linking 3.

- **R-eval v2 stages:** gate 2, none 2, representation 3, linking 8, candidate_recall 2, ranking 1.

- **R-oracle v2 stages:** linking 2, gate 1.


## Remaining bottleneck and next boundary (items 21-22)

Binder v2 remains experimental. The immediate release blockers are semantic linking precision and loss of previously verified bindings. Independent sweep evidence distinguishes those from conservative failures caused by absent reconstructed gold targets. Candidate recall has improved to 7/7 represented real claims in R-prod; it is no longer the only binder bottleneck. Required multi-value completeness and subject/quantity linking still block real claims, even in the three-claim oracle upper bound.

For product impact, the earliest visible constraints are the missing product claims (15/18 do not reach the gate) and production representation (11/18 real claims lack reconstructed gold cells). R-eval reduces representation failures to 3/18, but leaves eight linking failures and two candidate-recall failures. Borderless remains off; oracle/evaluation gains do not establish product gains. The product result is unchanged at zero verified bindings.

Any next implementation phase needs a new recorded scope and general synthetic reproductions for these failure classes, preserving this measurement. Do not tune against the evaluated claim IDs, rewrite the frozen scoring, or use v2_llm to hide these deterministic failures. Phase 10 ends with the no-enable decision.

## Commits and files (items 17-18)

- `7f55789` — recovered/fixed `src/evidence/binder_v2.py`, preserved router in `src/evidence/gate.py`, recovery inventory and manifest.
- `1cfea2c` — original and recovery binder tests, 51-case fixture, 123-expectation regression harness, original precision reproductions, synthetic review, explicit legacy-policy identity test.
- `c805cf4` — recovered and corrected `src/evaluation/binder_10/validate_10.py`; final pre-measurement code.
- `ad92c87` — measurement: `results.json`, `results.csv`, `validation_10.json`, `audit/packets.json`, 22 crops, 22 text layers and two independent verdict files. Raw PDF text whitespace is preserved unchanged.
- Report/checkpoint commit — this report, updated recovery/review status, `docs/evaluation/checkpoints/phase_10_binder.md`, and `docs/evaluation/PROGRESS.md`.

Raw arm results and logs remain under ignored `runs/binder_10/` and `runs/phase10_recovery/logs/`, indexed with hashes in `validation_10.json`. The exact original recovery archive remains outside the repository. Unrelated untracked directories are not included. The branch is pushed separately after the report commit; it is not merged into the default branch.
