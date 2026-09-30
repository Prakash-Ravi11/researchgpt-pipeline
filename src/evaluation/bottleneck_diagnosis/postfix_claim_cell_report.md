# Post-fix claim → cell gold (mined from the 30 physical PDFs)

Labels are **machine-assisted, unvalidated**: two blind machine readers, not a human. Generated 2026-09-30T05:46:03+00:00 at git `30fc85d75d9e` (`claude-code-verification`).

## 1. How the set was built

1. **Harvest** (`postfix_mine_claims.py`, deterministic; never calls find_tables, the binder or the gate): every sentence that names a table, or directly follows a sentence naming exactly one table ("contextual"), carries a meaningful number, and has that number printed on the table's page outside the sentence itself.
2. **Two blind readings** of every candidate against the page renders + PDF text layer: reader A claim-first, reader B cell-first; neither saw the other, the candidate ZIP, Stage A or any pipeline output.
3. **Agreement** (rules fixed before evaluation, see `postfix_evaluate.py`): a pair is VERIFIED_POSITIVE only when both readers say so, their claim sentences coincide, and they agree on table, page, row, leaf column and value. The claim is an exact substring of the PDF text layer (checked); nothing is paraphrased or generated.

## 2. Counts

- Harvested candidates: **85**; final status: AMBIGUOUS 5, VERIFIED_POSITIVE 18, WRONG_CLAIM 60, WRONG_ROW 1, WRONG_TABLE 1.
- Reader status agreement: 84/85 — raw agreement between two machine readers (not a human-labelled kappa category).
- Reader status distributions: A_claim_first: AMBIGUOUS 5, VERIFIED_POSITIVE 18, WRONG_CLAIM 60, WRONG_ROW 1, WRONG_TABLE 1; B_cell_first: AMBIGUOUS 4, VERIFIED_POSITIVE 19, WRONG_CLAIM 60, WRONG_ROW 1, WRONG_TABLE 1.
- **Verified claims: 18; verified pairs: 55** from 12 papers (P001, P003, P004, P006, P007, P008, P011, P014, P015, P016, P017, P030).
- By reference (pairs): {'contextual': 26, 'explicit': 29}; claim subject (claims): {'own_method': 12, 'dataset_or_cohort': 4, 'baseline_or_cited': 2}; claim subject (pairs): {'own_method': 42, 'dataset_or_cohort': 10, 'baseline_or_cited': 3}; table orientation (pairs): {'columns_are_entities': 27, 'rows_are_entities': 28}.
- The subject kind belongs to the claim sentence: a multi-value own-method claim can include a baseline's cell (e.g. 'ours 0.926 versus 0.920 for nnU-Net').
- Same sentence as one of the 44 candidate-ZIP pairs (the cell may differ): P003/G002:VERIFIED_POSITIVE, P007/G001:WRONG_CLAIM, P014/G002:WRONG_TABLE, P014/G003:WRONG_TABLE, P017/G002:WRONG_CELL.

## 3. Verified pairs

| Pair | Claim | Paper | Claim p. | Table (p.) | Row | Column | Cell | Subject | Claim text |
|---|---|---|---|---|---|---|---|---|---|
| PF001 | C005 | P001 | 12 | Table 4 (p13) | Average | Ours | `0.926 ± 0.012` | own_method | It shows that our method obtains similar results than nnU-Net for all anatomical labels, achieving an average Dice score of 0.926 ± 0.012 versus 0.920 ± 0.014 f… |
| PF002 | C005 | P001 | 12 | Table 4 (p13) | Average | nnU-Net | `0.920 ± 0.014` | own_method | It shows that our method obtains similar results than nnU-Net for all anatomical labels, achieving an average Dice score of 0.926 ± 0.012 versus 0.920 ± 0.014 f… |
| PF003 | C010 | P003 | 5 | Table 3 (p6) | Proposed Method | Dice Score (%) | `92.3` | own_method | On the ISLES dataset for ischemic stroke lesion segmentation, our method achieves a remarkable average Dice score of 92.3%, outperforming several state-of-the-a… |
| PF004 | C012 | P004 | 8 | Table 1 (p7) | Segmentation > UM-CAM+SPL | DSC (%) | `89.76±5.09*` | own_method | Quantitative evaluation results in the second section of Table 1 show that the network trained with UM-CAM and SPL supervision achieves an average DSC score of … |
| PF005 | C013 | P004 | 8 | Table 2 (p8) | UM-CAM+SPL (ours) | Test set / DSC (%) | `90.22±3.75*` | own_method | Our proposed method achieves an average DSC of 90.22% and an average HD95 of 4.04 pixels, which is at least 3.02 pixels lower than other weakly-supervised metho… |
| PF006 | C013 | P004 | 8 | Table 2 (p8) | UM-CAM+SPL (ours) | Test set / HD95 (pixels) | `4.04±4.26*` | own_method | Our proposed method achieves an average DSC of 90.22% and an average HD95 of 4.04 pixels, which is at least 3.02 pixels lower than other weakly-supervised metho… |
| PF007 | C021 | P006 | 13 | TABLE V (p14) | All | YOLOv5 / Box | `0.947` | own_method | For all the classes combined, YOLOv5 has a mAP score of 0.947 for box detection and 0.947 for mask detection, while YOLOv7 has a mAP score of 0.94 for box detec… |
| PF008 | C021 | P006 | 13 | TABLE V (p14) | All | YOLOv5 / Mask | `0.947` | own_method | For all the classes combined, YOLOv5 has a mAP score of 0.947 for box detection and 0.947 for mask detection, while YOLOv7 has a mAP score of 0.94 for box detec… |
| PF009 | C021 | P006 | 13 | TABLE V (p14) | All | YOLOv7 / Box | `0.94` | own_method | For all the classes combined, YOLOv5 has a mAP score of 0.947 for box detection and 0.947 for mask detection, while YOLOv7 has a mAP score of 0.94 for box detec… |
| PF010 | C021 | P006 | 13 | TABLE V (p14) | All | YOLOv7 / Mask | `0.941` | own_method | For all the classes combined, YOLOv5 has a mAP score of 0.947 for box detection and 0.947 for mask detection, while YOLOv7 has a mAP score of 0.94 for box detec… |
| PF011 | C025 | P007 | 10 | Table 3 (p10) | LCC | ICC3 | `0.922` | dataset_or_cohort | All ICC estimates exceed 0.922, indicating an excellent inter-rater agreement [36] (Table 3). |
| PF012 | C026 | P008 | 6 | TABLE I (p7) | Ours | Dice↑ | `0.87±0.06` | own_method | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. |
| PF013 | C026 | P008 | 6 | TABLE I (p7) | Ours | 95HD(mm)↓ | `0.96±0.38` | own_method | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. |
| PF014 | C026 | P008 | 6 | TABLE I (p7) | Ours | ASD(mm)↓ | `0.28±0.14` | own_method | Our method achieved mean Dice of 0.87, 95HD of 0.96, and ASD of 0.28. |
| PF015 | C027 | P008 | 6 | TABLE I (p7) | DSRNet | Dice↑ | `0.84±0.06` | own_method | We observe that by adding 2.6% extra parameters, our attention module could improve the performance by 3% (from 0.84 by DSRNet to 0.87 by Ours) in terms of Dice… |
| PF016 | C027 | P008 | 6 | TABLE I (p7) | Ours | Dice↑ | `0.87±0.06` | own_method | We observe that by adding 2.6% extra parameters, our attention module could improve the performance by 3% (from 0.84 by DSRNet to 0.87 by Ours) in terms of Dice… |
| PF017 | C034 | P011 | 2 | Table 1 (p2) | TRAINING | Number of subjects | `15` | dataset_or_cohort | Dis-carding pathological and non-annotated brains, our training dataset results in 15 healthy fetal brains (see details summarized in Table 1). |
| PF018 | C035 | P011 | 2 | Table 1 (p2) | EVALUATION Quantitative | Gestational age (weeks) | `21-38` | dataset_or_cohort | The normative spatiotemporal MRI atlas of the fetal brain [14] provides 3D high-quality isotropic smooth volumes along with tissue label maps for all gestationa… |
| PF019 | C035 | P011 | 2 | Table 1 (p2) | EVALUATION Quantitative | Gestational age (weeks) | `21-38` | dataset_or_cohort | The normative spatiotemporal MRI atlas of the fetal brain [14] provides 3D high-quality isotropic smooth volumes along with tissue label maps for all gestationa… |
| PF020 | C041 | P014 | 4 | Table 2 (p5) | Brain volume (cm3) > Left hippocampus | SRI-exposed (n = 62) | `0.45` | own_method | SRI-exposed fetuses showed signiﬁcantly smaller left (0.45 vs 0.53 cm3, adjusted p = 0.0004) and right (0.48 vs 0.56 cm3, adjusted p = 0.0004) hippocampal volum… |
| PF021 | C041 | P014 | 4 | Table 2 (p5) | Brain volume (cm3) > Left hippocampus | Unexposed (n = 120) | `0.53` | own_method | SRI-exposed fetuses showed signiﬁcantly smaller left (0.45 vs 0.53 cm3, adjusted p = 0.0004) and right (0.48 vs 0.56 cm3, adjusted p = 0.0004) hippocampal volum… |
| PF022 | C041 | P014 | 4 | Table 2 (p5) | Brain volume (cm3) > Left hippocampus | Adjusted Pa | `0.0004` | own_method | SRI-exposed fetuses showed signiﬁcantly smaller left (0.45 vs 0.53 cm3, adjusted p = 0.0004) and right (0.48 vs 0.56 cm3, adjusted p = 0.0004) hippocampal volum… |
| PF023 | C041 | P014 | 4 | Table 2 (p5) | Brain volume (cm3) > Right hippocampus | SRI-exposed (n = 62) | `0.48` | own_method | SRI-exposed fetuses showed signiﬁcantly smaller left (0.45 vs 0.53 cm3, adjusted p = 0.0004) and right (0.48 vs 0.56 cm3, adjusted p = 0.0004) hippocampal volum… |
| PF024 | C041 | P014 | 4 | Table 2 (p5) | Brain volume (cm3) > Right hippocampus | Unexposed (n = 120) | `0.56` | own_method | SRI-exposed fetuses showed signiﬁcantly smaller left (0.45 vs 0.53 cm3, adjusted p = 0.0004) and right (0.48 vs 0.56 cm3, adjusted p = 0.0004) hippocampal volum… |
| PF025 | C041 | P014 | 4 | Table 2 (p5) | Brain volume (cm3) > Right hippocampus | Adjusted Pa | `0.0004` | own_method | SRI-exposed fetuses showed signiﬁcantly smaller left (0.45 vs 0.53 cm3, adjusted p = 0.0004) and right (0.48 vs 0.56 cm3, adjusted p = 0.0004) hippocampal volum… |
| PF026 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Local gyriﬁcation index | SRI-exposed (n = 62) | `1.24` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF027 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Local gyriﬁcation index | Unexposed (n = 120) | `1.28` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF028 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Local gyriﬁcation index | Adjusted Pa | `0.03` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF029 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Curvedness (mm-1) | SRI-exposed (n = 62) | `0.21` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF030 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Curvedness (mm-1) | Unexposed (n = 120) | `0.24` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF031 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Curvedness (mm-1) | Adjusted Pa | `0.0004` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF032 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Surface area (cm2) | SRI-exposed (n = 62) | `143.35` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF033 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Surface area (cm2) | Unexposed (n = 120) | `151.36` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF034 | C042 | P014 | 4 | Table 2 (p5) | Cerebral cortical folding > Surface area (cm2) | Adjusted Pa | `0.02` | own_method | Additionally, the SRI-exposed group showed reduced cerebral cortical local gyriﬁcation index (1.24 vs 1.28, adjusted p = 0.03), curvedness (0.21 vs 0.24 mm–1, a… |
| PF035 | C045 | P014 | 5 | Table 3 (p5) | Volume | SRI-exposed | `753.11` | dataset_or_cohort | Placenta volumes (753.11 cm3 vs 656.00 cm3, adjusted p = 0.004) and ADC_D (0.004 vs 0.003, adjusted p = 0.048) were higher in SRI-exposed group vs unexposed con… |
| PF036 | C045 | P014 | 5 | Table 3 (p5) | Volume | Unexposed | `656.00` | dataset_or_cohort | Placenta volumes (753.11 cm3 vs 656.00 cm3, adjusted p = 0.004) and ADC_D (0.004 vs 0.003, adjusted p = 0.048) were higher in SRI-exposed group vs unexposed con… |
| PF037 | C045 | P014 | 5 | Table 3 (p5) | Volume | Adjusted Pa | `0.004` | dataset_or_cohort | Placenta volumes (753.11 cm3 vs 656.00 cm3, adjusted p = 0.004) and ADC_D (0.004 vs 0.003, adjusted p = 0.048) were higher in SRI-exposed group vs unexposed con… |
| PF038 | C045 | P014 | 5 | Table 3 (p5) | ADC_D | SRI-exposed | `0.004` | dataset_or_cohort | Placenta volumes (753.11 cm3 vs 656.00 cm3, adjusted p = 0.004) and ADC_D (0.004 vs 0.003, adjusted p = 0.048) were higher in SRI-exposed group vs unexposed con… |
| PF039 | C045 | P014 | 5 | Table 3 (p5) | ADC_D | Unexposed | `0.003` | dataset_or_cohort | Placenta volumes (753.11 cm3 vs 656.00 cm3, adjusted p = 0.004) and ADC_D (0.004 vs 0.003, adjusted p = 0.048) were higher in SRI-exposed group vs unexposed con… |
| PF040 | C045 | P014 | 5 | Table 3 (p5) | ADC_D | Adjusted Pa | `0.048` | dataset_or_cohort | Placenta volumes (753.11 cm3 vs 656.00 cm3, adjusted p = 0.004) and ADC_D (0.004 vs 0.003, adjusted p = 0.048) were higher in SRI-exposed group vs unexposed con… |
| PF041 | C048 | P015 | 9 | Table 2 (p9) | FetalSynthSeg | Global | `74.9±11.5∗` | own_method | Across all cross-validation splits, Fetal-SynthSeg achieves the highest global average Dice score of 74.9, consistently outperforming all other simulation-based… |
| PF042 | C052 | P016 | 22 | Table 4.2 (p22) | (X. Huang et al., 2023a) | Results | `DSC: 83.79%, VS: 84.84%, HD95: 35.66 mm` | baseline_or_cited | A contextual transformer block integrated into an encoder-decoder architecture with hybrid dilated convolutions achieved a DSC of 83.79% on a private dataset of… |
| PF043 | C052 | P016 | 22 | Table 4.2 (p22) | (X. Huang et al., 2023a) | Dataset | `80 fetuses (private)` | baseline_or_cited | A contextual transformer block integrated into an encoder-decoder architecture with hybrid dilated convolutions achieved a DSC of 83.79% on a private dataset of… |
| PF044 | C057 | P017 | 23 | Table 6 (p22) | Internal Validation > DSC, (95% CI) > FreeHemoSeg | Overall (n = 1456 slices) | `0.559 (0.546, 0.571)` | own_method | FreeHemoSeg achieved the best lesion segmentation performance (Table 6, Figure 6), achieving DSCs of 0.559 (95% CI, 0.546–0.571) and 0.512 (95% CI, 0.497–0.526)… |
| PF045 | C057 | P017 | 23 | Table 6 (p22) | External Validation > FreeHemoSeg | Overall (n = 1410 slices) | `0.512 (0.497, 0.526)` | own_method | FreeHemoSeg achieved the best lesion segmentation performance (Table 6, Figure 6), achieving DSCs of 0.559 (95% CI, 0.546–0.571) and 0.512 (95% CI, 0.497–0.526)… |
| PF046 | C058 | P017 | 28 | Table 7 (p28) | R1 > 2D Stacks | Sensitivity | `0.882` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF047 | C058 | P017 | 28 | Table 7 (p28) | R1 > FreeHemoSeg | Sensitivity | `1.000` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF048 | C058 | P017 | 28 | Table 7 (p28) | R2 > 2D Stacks | Sensitivity | `0.882` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF049 | C058 | P017 | 28 | Table 7 (p28) | R2 > FreeHemoSeg | Sensitivity | `0.941` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF050 | C058 | P017 | 28 | Table 7 (p28) | R1 > 2D Stacks | Time (s) | `43.1±28.1` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF051 | C058 | P017 | 28 | Table 7 (p28) | R1 > FreeHemoSeg | Time (s) | `36.2±17.4` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF052 | C058 | P017 | 28 | Table 7 (p28) | R2 > 2D Stacks | Time (s) | `63.9±21.9` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF053 | C058 | P017 | 28 | Table 7 (p28) | R2 > FreeHemoSeg | Time (s) | `30.2±7.5` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF054 | C058 | P017 | 28 | Table 7 (p28) | R2 > 3D Volume | Specificity | `0.943` | own_method | Compared with standard 2D stack interpretation, FreeHemoSeg’s assistance increased sensitivity from 0.882 to 1.000 for R1 and from 0.882 to 0.941 for R2, while … |
| PF055 | C085 | P030 | 11 | Table 2 (p5) | Wen et al.[43] | Mean DSC | `0.9010` | baseline_or_cited | Wen et al. achieved a mean DSC of 0.9010 using the FeTA 2021 dataset, which is higher than that reported in other stud-ies [45]. |

## 4. Candidates not verified

| Candidate | Paper | Final | Why |
|---|---|---|---|
| C001 | P001 | WRONG_CLAIM | both readings agree; A: claim_text is only the fused body of Table 1 (Dice, %/J/<=0, GPU per number of cascades for the original and c |
| C002 | P001 | WRONG_CLAIM | both readings agree; A: The only number in the sentence is the adopted setting λ = 1, which is a row key (λ column) of Table 2, not a  |
| C003 | P001 | WRONG_CLAIM | both readings agree; A: claim_text is the fused body and caption of Table 3 followed by a sentence fragment ('registration, which can  |
| C004 | P001 | WRONG_CLAIM | both readings agree; A: Table-description sentence whose only number is the test-set size (20 scans); 20 is not printed in any cell of |
| C006 | P001 | WRONG_CLAIM | both readings agree; A: claim_text is only the fused Table 4 body (labels x Ours/nnU-Net/PP/dHCP, plus the Time row) and its caption;  |
| C007 | P002 | WRONG_CLAIM | both readings agree; A: claim_text is the running header ('22 P. de Dumast et al.'), the fused body of the dataset-summary Table 1 and |
| C008 | P002 | WRONG_CLAIM | both readings agree; A: claim_text is the fused body of Table 4 (sub-tables (a) FeTA and (b) STA: Baseline/Hybrid/TopoCP x DSC/ASSD/HR |
| C009 | P003 | WRONG_CLAIM | both readings agree; A: claim_text is the Figure 2 caption, the Table 1 caption and body, and the section number '3.'; there is no nat |
| C011 | P003 | WRONG_CLAIM | both readings agree; A: The natural-language sentence carries no number and points to figures 4 and 5; every number in claim_text come |
| C014 | P005 | WRONG_CLAIM | both readings agree; A: claim_text is the Table 3 caption tail and the CSPCNN local-pathway architecture body (layers, filter sizes, s |
| C015 | P005 | WRONG_CLAIM | both readings agree; A: claim_text is the Table 4 caption tail and the CSPCNN global-pathway architecture body followed by 'Table 5.'; |
| C016 | P005 | WRONG_CLAIM | both readings agree; A: claim_text is the Table 5 caption tail and the MRIPCNN local-pathway architecture body; there is no natural-la |
| C017 | P005 | WRONG_CLAIM | both readings agree; A: claim_text is the Table 6 caption tail and body (p13) followed by 'Table 7.'; there is no natural-language sen |
| C018 | P005 | WRONG_CLAIM | both readings agree; A: The sentence is a method description with no number; the numbers in claim_text (256, 21, 14,450,688, 128, 5) c |
| C019 | P006 | AMBIGUOUS | both readings agree; A: Table-introduction sentence whose only value is the evaluation-set size 827; Table IV prints 827 both in the m |
| C020 | P006 | AMBIGUOUS | both readings agree; A: Table-introduction sentence; 827 is printed in Table V (p14) both in the merged Images cell and in the Labels  |
| C022 | P006 | AMBIGUOUS | both readings agree; A: Table-introduction sentence; 827 appears in Table VI (p15) both in the merged Images cell and in the Labels ce |
| C023 | P006 | WRONG_CLAIM | both readings agree; A: Qualitative conclusion; its only numbers (0.5-0.95) are the IoU range inside the metric name mAP@0.5-0.95, not |
| C024 | P006 | AMBIGUOUS | both readings agree; A: 'The RCNN models ... recall rate with 95%': Table VII (p17) prints 95.0% recall for both RCNN [55] and Mask RC |
| C028 | P009 | WRONG_CLAIM | both readings agree; A: 0.02, 0.04, 0.04 and 0.03 are derived differences between similar-domain cells of Table 3 (p15) (e.g. Exp 3 0. |
| C029 | P009 | WRONG_CLAIM | both readings agree; A: 0.02 is the derived out-of-domain difference between Experiment 7 (0.76±0.13) and Experiment 5 (0.74±0.10) in  |
| C030 | P009 | WRONG_CLAIM | both readings agree; A: 0.07 is the derived most-pathological difference between Experiment 2 (0.67±0.15) and Experiment 1 (0.60±0.21) |
| C031 | P009 | WRONG_CLAIM | both readings agree; A: 0.03 (Exp 4 0.55 - Exp 3 0.52) and 0.02 (Exp 6 0.66 - Exp 5 0.64) are derived most-pathological differences in |
| C032 | P010 | WRONG_CLAIM | both readings agree; A: 17 is the number of cases, printed in Table 1 only as the case index of the last row, and 318 s is a batch tot |
| C033 | P011 | WRONG_CLAIM | both readings agree; A: claim_text is the fused Table 1 header/body and caption plus a sentence fragment continuing from p1; no result |
| C036 | P011 | WRONG_CLAIM | both readings agree; A: claim_text is the fused Table 2 body (Baseline U-Net/TopoCP with p-value columns) and its caption; there is no |
| C037 | P013 | WRONG_CLAIM | both readings agree; A: claim_text is the running header plus the Table 1 caption; a caption, not a claim. |
| C038 | P013 | WRONG_CLAIM | both readings agree; A: claim_text is the fused Table 1 body followed by a sentence fragment ('templates while preserving accurate ind |
| C039 | P013 | WRONG_CLAIM | both readings agree; A: The sentence is a method description without numbers; all numbers in claim_text come from the fused Table 2 bo |
| C040 | P014 | AMBIGUOUS | reader disagreement: A=AMBIGUOUS, B=VERIFIED_POSITIVE; A: 62 and 120 are printed only in Table 1's column headers 'SRI-exposed (n = 62)' and 'Unexposed (n = 120)', not  |
| C043 | P014 | WRONG_TABLE | both readings agree; A: The values (9.15 vs 9.67 cm³; 95% CI −1.03 to −0.004) come from the sensitivity analysis the sentence attribut |
| C044 | P014 | WRONG_CLAIM | both readings agree; A: The adjusted p = 0.10 is the cerebellar-volume result of the sensitivity analysis (supplementary Table S1, nam |
| C046 | P014 | WRONG_CLAIM | both readings agree; A: The β/p values (0.002, 0.02, 0.05, 0.005, 0.03) come from supplementary Tables S7/S8, which the sentence itsel |
| C047 | P015 | WRONG_CLAIM | both readings agree; A: Data-acquisition (setup) description of a separate prospective multi-echo dataset that is not a row of Table 1 |
| C049 | P015 | WRONG_CLAIM | both readings agree; A: The sentence naming Table 3 only describes what the table compares; it asserts no value. '4.3' is a section nu |
| C050 | P015 | WRONG_CLAIM | both readings agree; A: The 0.1–2.5 Dice-point figures are derived differences between FetalRealSeg/RealSynthHybrid and FetalSynthSeg  |
| C051 | P016 | WRONG_CLAIM | both readings agree; A: Pointer sentence ('...as summarized in Table 4.2') with no asserted value; '4.2' is the section/table number. |
| C053 | P016 | WRONG_CLAIM | both readings agree; A: Pointer sentence ('the results are summarized in Table 4.6') with no asserted value; '4.4' comes from the sect |
| C054 | P017 | WRONG_CLAIM | both readings agree; A: Acquisition-protocol (setup) description, not a result sentence. |
| C055 | P017 | WRONG_CLAIM | both readings agree; A: Only a page number ('16') and the start of the Table 3 caption; no sentence. |
| C056 | P017 | WRONG_CLAIM | both readings agree; A: The only real sentence (best case/slice-level accuracy, Tables 4 and 5) contains no numeric value; all numbers |
| C059 | P018 | WRONG_CLAIM | both readings agree; A: Training-setup statement (ensemble of 10 3D U-Nets), not a result; '10' is not a Table 2 value (only inside SD |
| C060 | P018 | WRONG_CLAIM | both readings agree; A: Part of the Table 2 caption (what is reported); '95' belongs to the metric name HD95. |
| C061 | P021 | WRONG_CLAIM | both readings agree; A: The only number is the hyper-parameter setting γ = 200, printed as a column header of the 'γ value' row, not a |
| C062 | P022 | WRONG_CLAIM | both readings agree; A: Pointer sentence describing what Table 1 shows; '95' is part of the metric name (95% percentile), no result va |
| C063 | P024 | WRONG_CLAIM | both readings agree; A: Pre-processing (method/setup) description, not a result; 0.5 and 256 are processing settings. |
| C064 | P026 | WRONG_ROW | both readings agree; A: p = 0.057 is printed in Table 8 as the Sex P-value of Left NAc / Manual (Test set); the Right NAc / Manual (Te |
| C065 | P026 | WRONG_CLAIM | both readings agree; A: Qualitative claim with no result value; '120' is part of the row label 'Baseline120' and '799' is the page num |
| C066 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 4 cell content (DSC/ESSP/Δ for nnU-Net, CoTr, ANTs, UNesT) followed by the |
| C067 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 5 cell content (NSD/ESSP/Δ) followed by the Table 6 caption. |
| C068 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 7 cell content (β, Std Err, P-value) followed by the Table 8 caption. |
| C069 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 8 cell content (γ, Std Err, P-value for manual volumes) followed by the Ta |
| C070 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 10 cell content followed by the Table 11 caption. |
| C071 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 11 caption fragment and cell content followed by the Table 12 caption. |
| C072 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 12 cell content followed by the Table 13 caption. |
| C073 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: page header, Table 14 caption and cell content, then the Table 15 caption. |
| C074 | P026 | WRONG_CLAIM | both readings agree; A: No natural-language sentence: Table 15 cell content followed by the Table 16 caption. |
| C075 | P028 | WRONG_CLAIM | both readings agree; A: 177, 139 and 38 are sums of Table 1 training rows (18+5+116+28+10, 18+5+116, 28+10), not printed in any cell. |
| C076 | P029 | WRONG_CLAIM | both readings agree; A: Equation (20) followed by a pointer sentence to Table 1 (layer dimensions) with no asserted value; '20' is the |
| C077 | P029 | WRONG_CLAIM | both readings agree; A: Equation (24), its variable definitions, a section heading and a pointer to Table 2; no result value. |
| C078 | P029 | WRONG_CLAIM | both readings agree; A: Computing-environment (setup) description, not a result. |
| C079 | P029 | WRONG_CLAIM | both readings agree; A: Table 2 cell content, its caption and the page footer; no sentence. |
| C080 | P029 | WRONG_CLAIM | both readings agree; A: 1.33, 1.01 and 0.27 are derived improvements of AS-WEC over other models (e.g., Dice 92.48-91.15 = 1.33, Acc 9 |
| C081 | P029 | WRONG_CLAIM | both readings agree; A: An unfinished sentence fragment without values fused with Tables 3 and 4 cell content, captions and page foote |
| C082 | P030 | WRONG_CLAIM | both readings agree; A: Running header, Table 2 caption and cell content, then a sentence fragment without values. |
| C083 | P030 | WRONG_CLAIM | both readings agree; A: Sentence fragment ('Yan et al. proposed a new') fused with the Table 4 caption and cell content; no claim valu |
| C084 | P030 | WRONG_CLAIM | both readings agree; A: Running header plus the start of the Table 4 (continued) content; no sentence. |

## 5. Limits

- The readers are machine readers; the labels are suggestions until a human confirms them (RESEARCH_DIRECTIVE.md, Labelling authority).
- The harvest only sees sentences that name a table (or directly follow one that does) and whose number is printed verbatim on the table page: claims stating a value in another format (0.91 vs 91%) or pointing to a table from further away are not in the set.
- Harvest totals per paper are in `postfix_claim_cell_gold.json` (`harvest_stats`).
