# Stage A — verification of the 44 candidate claim→cell pairs

**Status of these labels:** machine-assisted and **not validated by a human** (RESEARCH_DIRECTIVE.md, "Labelling authority"). Only pairs marked `VERIFIED_POSITIVE` are treated as verified gold pairs downstream; the candidate dataset as a whole is **not** gold.

| | |
|---|---|
| Candidate source | `src/evaluation/candidate_gold/researchgpt_candidate_gold_30_2026-09-28 (1).zip` (SHA-256 `a11900f2ea572e89…`) |
| Physical PDFs | the canonical copies pinned by Phase 2.1 (`pdf_identity_manifest_v2.csv`), re-hashed before use |
| Run | 2026-09-30T00:36:20+00:00, git `30fc85d75d9e` (`claude-code-verification`), PyMuPDF 1.28.2 |
| Method | deterministic PDF evidence (recomputed each run) + one recorded adjudication per pair (`stage_a_adjudications.json`) + an independent second pass (`stage_a_independent_verification.json`) |
| Reproduce | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py` |

## 1. Summary

- Total candidate pairs: **44**

| Status | Pairs |
|---|---|
| VERIFIED_POSITIVE | 1 |
| WRONG_CLAIM | 37 |
| WRONG_TABLE | 4 |
| WRONG_ROW | 0 |
| WRONG_COLUMN | 0 |
| WRONG_CELL | 2 |
| AMBIGUOUS | 0 |
| NOT_VERIFIABLE | 0 |

- Verified gold pairs: **1**, covering 1 cell link(s), in paper(s): P003.
- Independent second pass: 44 pairs compared; exact status agreement 43/44; positive-vs-not agreement 43/44 (first-pass statuses vs the independent pass; raw agreement only (pilot, n<50: no kappa, per RESEARCH_DIRECTIVE.md)).

## 2. Paper-level distribution

| Paper | Pairs | VERIFIED_POSITIVE | WRONG_CLAIM | WRONG_TABLE | WRONG_ROW | WRONG_COLUMN | WRONG_CELL | AMBIGUOUS | NOT_VERIFIABLE |
|---|---|---|---|---|---|---|---|---|---|
| P001 | 3 |  | 3 |  |  |  |  |  |  |
| P002 | 4 |  | 4 |  |  |  |  |  |  |
| P003 | 2 | 1 | 1 |  |  |  |  |  |  |
| P005 | 2 |  | 2 |  |  |  |  |  |  |
| P006 | 4 |  | 2 | 2 |  |  |  |  |  |
| P007 | 1 |  | 1 |  |  |  |  |  |  |
| P009 | 1 |  | 1 |  |  |  |  |  |  |
| P011 | 2 |  | 2 |  |  |  |  |  |  |
| P013 | 1 |  | 1 |  |  |  |  |  |  |
| P014 | 3 |  |  | 2 |  |  | 1 |  |  |
| P015 | 1 |  | 1 |  |  |  |  |  |  |
| P016 | 6 |  | 6 |  |  |  |  |  |  |
| P017 | 2 |  | 1 |  |  |  | 1 |  |  |
| P019 | 2 |  | 2 |  |  |  |  |  |  |
| P021 | 1 |  | 1 |  |  |  |  |  |  |
| P024 | 2 |  | 2 |  |  |  |  |  |  |
| P026 | 1 |  | 1 |  |  |  |  |  |  |
| P029 | 6 |  | 6 |  |  |  |  |  |  |

## 3. Every pair

| Pair | Status | Cells | Claim (start) | Reason | Confidence | Independent pass |
|---|---|---|---|---|---|---|
| P001/G001 | **WRONG_CLAIM** | 24 | Original architecture Contracted Architecture N cascades Dice %|Jϕ| ≤0… | rule 1(b) - the claim text is Table 1's own content (column headers, every cell value, then the caption); no natural-language sentence asserts a cell value | high | WRONG_CLAIM |
| P001/G002 | **WRONG_CLAIM** | 8 | Based on these results, we adopted a regularization parameter of λ = 1… | rule 1(e) - the only sentence is qualitative/comparative and states no cell value; every number in the candidate claim comes from Table 2's embedded text. Secondary: 6 of the 8 candidate cells (other lambda rows) are not asserted even qualitatively | medium | WRONG_CLAIM |
| P001/G003 | **WRONG_CLAIM** | 11 | Label Ours nnU-Net CSF 0.903 ± 0.006 0.878 ± 0.012 Grey Matter 0.742 ±… | rule 1(b) - the claim text is Table 5's own content plus caption; secondary: the candidate cells (0.923, 0.897, 0.877 ...) are not even the values printed in that text (0.903, 0.878, 0.742 ...) | high | WRONG_CLAIM |
| P002/G001 | **WRONG_CLAIM** | 6 | Dataset Number of subjects (Neurotypical / Pathological) Gestational a… | rule 1(b) - the claim text is Table 1's own content (dataset summary rows + caption); secondary: the candidate cells are body-text fragments such as 'et al., 2012] SR-re' | high | WRONG_CLAIM |
| P002/G002 | **WRONG_CLAIM** | 3 | Conﬁguration DSC ↑ ASSD ↓ BNE1 ↓ Ranking ↓ Baseline 0.748 ± 0.009 0.29… | rule 1(b) - the claim text is Table 3's own content plus caption; secondary: the candidate cells are whole rows merged into one cell | high | WRONG_CLAIM |
| P002/G003 | **WRONG_CLAIM** | 7 | DSC ↑ ASSD ↓ HR ↓ Baseline 0.82 ± 0.02 0.22 ± 0.05 0.093 ± 0.03 Hybrid… | rule 1(b) - the claim text is Table 4(a)/(b)'s own content plus caption; secondary: candidate cells hold three merged values each | high | WRONG_CLAIM |
| P002/G004 | **WRONG_CLAIM** | 3 | Best Medium Worst Baseline Hybrid TopoCP Baseline Hybrid TopoCP Baseli… | rule 1(b) - the claim text is Table 7's own content plus caption | high | WRONG_CLAIM |
| P003/G001 | **WRONG_CLAIM** | 5 | 2: Comparison chat for Exiting Methods Table 1: Comparison Table for E… | rule 1(b) - the claim text is Table 1's own content ('Comparison Table for Exiting Method' rows) plus caption; no sentence asserts a value | high | WRONG_CLAIM |
| P003/G002 | **VERIFIED_POSITIVE** | 1 | Method Whole Tumor Dice (%) Tumor Core Dice (%) Enhancing Tumor Dice (… | the sentence states 92.3% average Dice for 'our method' and cites Table 3; PDF Table 3 (p6, 'Comparison with state-of-the-art methods on the ISLES dataset') row 04 'Proposed Method' x column 'Dice Score (%)' = 92.3 (bold); 92.3 occurs once in Table 3 | high | VERIFIED_POSITIVE |
| P005/G001 | **WRONG_CLAIM** | 3 | Architectural detail of CSPCNN Global Pathway Layer Type Filter size S… | rule 1(b) - the claim text is Table 7's own content (CNN architecture parameters); no sentence | high | WRONG_CLAIM |
| P005/G002 | **WRONG_CLAIM** | 6 | Architectural detail of Global CNN Type Filter size Strides Filters FC… | rule 1(b)/(c) - Table 7's own content plus a sentence that only points to Table 7 and states no value | high | WRONG_CLAIM |
| P006/G001 | **WRONG_TABLE** | 1 | RECALL PERFORMANCE Table IV presents the recall performance evaluation… | the claim asserts evaluation on 827 labeled images and cites Table IV, but the candidate 'Table IV' object (p12 bbox) is the tail of the preceding table plus the body paragraph that contains the claim; the candidate cell '827 labeled b' is body text of the claim sentence itself, not a cell of TABLE IV ('RECALL PERFORMANCE OF THE YOLO MODELS') | high | WRONG_TABLE |
| P006/G002 | **WRONG_TABLE** | 1 | MEAN AVERAGE PRECISION (mAP@.5) Table V shows the mean Average Precisi… | the claim cites Table V, but the candidate 'Table V' object is on p13, anchored on the body sentence 'Table V shows the mean Average Precision (mAP)...', and its region holds the continuation of the preceding table plus body text; TABLE V ('MEAN AVERAGE PRECISION (MAP@.5)') is on p14. Even there 827 appears twice (merged Images cell and All/Labels), so the cell would be ambiguous | high | WRONG_TABLE |
| P006/G003 | **WRONG_CLAIM** | 7 | 14 TABLE V: MEAN AVERAGE PRECISION (MAP@.5) Class Image s Label s YOLO… | rule 1(b) - the claim text is the page number '14', TABLE V's own content and the unrelated sentence 'Figure 11 presents the F1-confidence curves' | high | WRONG_CLAIM |
| P006/G004 | **WRONG_CLAIM** | 2 | MEAN AVERAGE PRECISION (mAP@.5:.95) Table VI shows the mAP for the YOL… | rule 1(d) - the claim (Table VI, 827 images, IoU 0.5-0.95) shares only the digit '5' (substring of '0.5' / '.5') with the candidate cells 'mAP@.5 s' and 'mAP@.5'; secondary: the candidate 'Table VI' region is body text only, not the table | high | WRONG_CLAIM |
| P007/G001 | **WRONG_CLAIM** | 1 | 3.1 Inter-observer agreement All ICC estimates exceed 0.922, indicatin… | rule 1(d) - the claim ('All ICC estimates exceed 0.922 ... (Table 3)') shares only the section number '3.1' with the candidate cell '3.1 Inter-observer ag', which is the section heading; secondary: the candidate 'Table 3' content is body text. The real Table 3 row LCC x ICC3 = 0.922 carries the claim's value but is not the candidate cell | high | WRONG_CLAIM |
| P009/G001 | **WRONG_CLAIM** | 1 | 2.1.1 MRI datasets and rationale of data pooling for test diversificat… | rule 1(c) - the sentence only points to Table 1 ('metadata information listed in Table 1') and asserts no value; the candidate cell '(21.1-38.3)' shares no number with it | high | WRONG_CLAIM |
| P011/G001 | **WRONG_CLAIM** | 11 | Dataset Magnetic ﬁeld strength (Tesla) Vendor Image resolution (mm3) N… | rule 1(b) - the claim text is Table 1's own content plus caption and an unrelated fragment ('recently proved its good ability...') | high | WRONG_CLAIM |
| P011/G002 | **WRONG_CLAIM** | 10 | SR quality (# of slices) Baseline U-Net TopoCP Equal Acceptable (50) 1… | rule 1(b) - the claim text is Table 3's own content plus caption and a reference fragment '[8] B.' | high | WRONG_CLAIM |
| P013/G001 | **WRONG_CLAIM** | 2 | Conditional Atlas Learning in Fetal MRI 5 Table 1: Fetal MRI acquisiti… | rule 1(b) - the claim is the running header 'Conditional Atlas Learning in Fetal MRI 5' plus Table 1's own caption; the link to the '1.5T' cells is the caption describing its own table | high | WRONG_CLAIM |
| P014/G001 | **WRONG_CELL** | 1 | RESULTS Demographics Our cohort consisted of 182 participants: 62 with… | the claim (120 unexposed controls, Table 1) and the table (Table 1, p4) are right, but the only candidate cell '(n=120)' is the second line of the column header 'Unexposed (n = 120)' - a header fragment, not a table cell, which rule 3 classifies as WRONG_CELL | high | WRONG_CELL (disagrees) |
| P014/G002 | **WRONG_TABLE** | 1 | Fetal brain measures in SRI-exposed group vs controls SRI-exposed fetu… | the claim's values (left/right hippocampus 0.45 vs 0.53 and 0.48 vs 0.56, adjusted p = 0.0004) are in PDF Table 2 ('Fetal brain volume and cortical folding...', Adjusted P column). The candidate cell '0.0004 (0.000003 to 0.0008)' is the Difference (95% CI) of ADC_D in Table 3 ('Placenta measures...'); the candidate 'Table 2' object holds Table 3's content. The shared 0.0004 is a numeric coincidence | high | WRONG_TABLE |
| P014/G003 | **WRONG_TABLE** | 1 | Additionally, the SRI-exposed group showed reduced cerebral cortical l… | the claim's values (gyrification 1.24 vs 1.28 p = 0.03; curvedness 0.21 vs 0.24 p = 0.0004; surface area 143.35 vs 151.36 p = 0.02) are in PDF Table 2; the candidate cell is Table 3's ADC_D difference '0.0004 (0.000003 to 0.0008)' (same wrong candidate object as P014/G002) | high | WRONG_TABLE |
| P015/G001 | **WRONG_CLAIM** | 4 | Thomas’ Hospital, London, on a Siemens FreeMax 0.55T scanner, with sim… | rule 1(c)/(d) - the sentence refers to Table 1 only for 'similar parameters as the KCL dataset'; its numbers (0.55T, 300/397/600 ms) describe another acquisition and are not in the candidate cells; the only overlap is '0.5' as a substring of '0.55' | high | WRONG_CLAIM |
| P016/G001 | **WRONG_CLAIM** | 1 | The results, summarized in Table 4.1, demonstrate the superior perform… | rule 1(c)/(d) - the sentence only points to Table 4.1 and states no value; the candidate cell 84.13 matches only the table number '4.1' as a substring | high | WRONG_CLAIM |
| P016/G002 | **WRONG_CLAIM** | 1 | The quantitative comparison is summarized in Table 4.3.… | rule 1(c)/(d) - the sentence only points to Table 4.3; the candidate cell 84.35 matches '4.3' as a substring; secondary: the candidate 'Table 4' is Table 4.1 (collapsed label; a 'Table 4' label line occurs on 7 pages) | high | WRONG_CLAIM |
| P016/G003 | **WRONG_CLAIM** | 2 | As summarized in Table 4.4, the absence of CLAHE leads to a substantia… | rule 1(c)/(d) - qualitative sentence pointing to Table 4.4; candidate cells 84.48 / 84.49 match '4.4' as a substring; secondary: collapsed label (candidate is Table 4.1) | high | WRONG_CLAIM |
| P016/G004 | **WRONG_CLAIM** | 2 | The quantitative results are presented in Table 4.5.… | rule 1(c)/(d) - the sentence only points to Table 4.5; candidate cells 84.56 / 84.51 match '4.5' as a substring; secondary: collapsed label | high | WRONG_CLAIM |
| P016/G005 | **WRONG_CLAIM** | 2 | The resulting performance metrics are summarized in Table 4.5.… | rule 1(c)/(d) - the sentence only points to Table 4.5; same substring cells as P016/G004; secondary: collapsed label | high | WRONG_CLAIM |
| P016/G006 | **WRONG_CLAIM** | 23 | 4.4.5 Effect of Optimizers The performance of the proposed model was i… | rule 1(c)/(d) - section heading plus a sentence pointing to Table 4.6 with no value; 23 candidate cells share no whole number with it; secondary: collapsed label | high | WRONG_CLAIM |
| P017/G001 | **WRONG_CLAIM** | 50 | FreeHemoSeg) SL Model < .001 < .001 < .001 < .001 < .001 FreeHemoSeg w… | rule 1(b)/(e) - a fragment of Table 5's p-value rows plus a qualitative sentence ('achieved the best case-level and slice-level diagnostic accuracy ... (Table 4, Table 5, Figure 5G-L)') that states no value | high | WRONG_CLAIM |
| P017/G002 | **WRONG_CELL** | 5 | Lesion Segmentation Performance of FreeHemoSeg across GMH-IVH Grades. … | value claim citing Table 6 (p22) and the table matches, but only 2 of the 5 candidate cells are asserted: '0.559' and '(0.546, 0.571)' (FreeHemoSeg x Overall, internal). 'SC, (95% CI)' is a fragment of the row label 'DSC, (95% CI)'; '0.497)' is SL Model's internal Grade II interval '(0.429, 0.497)'; '0.526' is FreeHemoSeg w/o SAM x Overall (internal). The external values the claim states, 0.512 (0.497, 0.526), are not the candidate cells | high | WRONG_CELL |
| P019/G001 | **WRONG_CLAIM** | 24 | Even though FeTal-SAM has equipped with rich priors from the registere… | rule 1(b) - a truncated sentence fragment ('...without the') followed by Table 1's own content; no value asserted in natural language | high | WRONG_CLAIM |
| P019/G002 | **WRONG_CLAIM** | 21 | For tissue structures that present good contrast in the MR images, FeT… | rule 1(b)/(e) - a qualitative fragment ('FeTal-SAM achieves performance comparable to 3D segmentation models specifically') followed by Table 2's own content | high | WRONG_CLAIM |
| P021/G001 | **WRONG_CLAIM** | 1 | 3.3 Comparison with the State-of-the-arts We implemented several state… | rule 1(c) - the sentence lists the compared methods and points to Table 1 without stating any value; the candidate cell 'CAI’21 73.3 79.1 ±0.6 ±0.3' (a merged cell) shares no whole number with it | high | WRONG_CLAIM |
| P024/G001 | **WRONG_CLAIM** | 1 | 3 Results and discussion 3.1 Effect of Pathology-Informed Augmentation… | rule 1(c)/(d) - section headings plus 'Table 2 summarizes the performance of models...' with no value; the cell '3.12*±2.09' matches only the section number '3.1' as a substring | high | WRONG_CLAIM |
| P024/G002 | **WRONG_CLAIM** | 15 | Enhancing Corpus Callosum Segmentation in Fetal MRI 9 Healthy pCCA CCA… | rule 1(b) - figure axis text plus Table 3's own content and caption | high | WRONG_CLAIM |
| P026/G001 | **WRONG_CLAIM** | 14 | Structure Manual Sex Race Race × Sex γ2 Std Err P-value γ1 Std Err P-v… | rule 1(b) - the claim text is Table 9's own content plus caption | high | WRONG_CLAIM |
| P029/G001 | **WRONG_CLAIM** | 12 | Consequently, MF-Max facilitates comprehensive feature Layer GRU Pool … | rule 1(b) - a sentence fragment plus Table 1's own content (feature-map dimensions) and the page footer | high | WRONG_CLAIM |
| P029/G002 | **WRONG_CLAIM** | 6 | Experimental environment Configure Model parameter Con­ figure GPU RTX… | rule 1(b) - Table 2's own content (experimental environment) plus the page footer | high | WRONG_CLAIM |
| P029/G003 | **WRONG_CLAIM** | 6 | The first row displays the intermediate layer feature maps pro­ cessed… | rule 1(b) - a sentence about a figure plus Table 5's own content; no value asserted in natural language | high | WRONG_CLAIM |
| P029/G004 | **WRONG_CLAIM** | 10 | The efficiency of Trans Deeplab and Deeplab v3+ is moderate among the … | rule 1(b) - a truncated sentence fragment plus Table 6's own content | high | WRONG_CLAIM |
| P029/G005 | **WRONG_CLAIM** | 1 | 5.4 Ablation experiment As shown in Table 8, evaluation results for gr… | rule 1(c)/(d)/(e) - qualitative sentence ('group 1 outperforms both groups 2 and 3') pointing to Table 8 with no value; the cell '5.43' matches only the section number '5.4' as a substring | high | WRONG_CLAIM |
| P029/G006 | **WRONG_CLAIM** | 12 | Blocks Evaluation metrics Otsu-WD GRU-EB MF-Max Dice Sen MAE MIoU mAP … | rule 1(b) - Table 7's own content, a second table's content and a caption fragment | high | WRONG_CLAIM |

## 4. Why pairs were rejected

- **WRONG_CLAIM** (37): rule 1(b) - Table 2's own content (experimental environment) plus the page footer; rule 1(b) - Table 7's own content, a second table's content and a caption fragment; rule 1(b) - a sentence about a figure plus Table 5's own content; no value asserted in natural language; rule 1(b) - a sentence fragment plus Table 1's own content (feature-map dimensions) and the page footer; rule 1(b) - a truncated sentence fragment ('...without the') followed by Table 1's own content; no value asserted in natural language; rule 1(b) - a truncated sentence fragment plus Table 6's own content; rule 1(b) - figure axis text plus Table 3's own content and caption; rule 1(b) - the claim is the running header 'Conditional Atlas Learning in Fetal MRI 5' plus Table 1's own caption; the link to the '1.5T' cells is the caption describing its own table; rule 1(b) - the claim text is Table 1's own content ('Comparison Table for Exiting Method' rows) plus caption; no sentence asserts a value; rule 1(b) - the claim text is Table 1's own content (column headers, every cell value, then the caption); no natural-language sentence asserts a cell value; rule 1(b) - the claim text is Table 1's own content (dataset summa
- **WRONG_TABLE** (4): the claim asserts evaluation on 827 labeled images and cites Table IV, but the candidate 'Table IV' object (p12 bbox) is the tail of the preceding table plus the body paragraph that contains the claim; the candidate cell '827 labeled b' is body text of the claim sentence itself, not a cell of TABLE IV ('RECALL PERFORMANCE OF THE YOLO MODELS'); the claim cites Table V, but the candidate 'Table V' object is on p13, anchored on the body sentence 'Table V shows the mean Average Precision (mAP)...', and its region holds the continuation of the preceding table plus body text; TABLE V ('MEAN AVERAGE PRECISION (MAP@.5)') is on p14. Even there 827 appears twice (merged Images cell and All/Labels), so the cell would be ambiguous; the claim's values (gyrification 1.24 vs 1.28 p = 0.03; curvedness 0.21 vs 0.24 p = 0.0004; surface area 143.35 vs 151.36 p = 0.02) are in PDF Table 2; the candidate cell is Table 3's ADC_D difference '0.0004 (0.000003 to 0.0008)' (same wrong candidate object as P014/G002); the claim's values (left/right hippocampus 0.45 vs 0.53 and 0.48 vs 0.56, adjusted p = 0.0004) are in PDF Table 2 ('Fetal brain volume and cortical folding...', Adjusted P column). The candidate 
- **WRONG_CELL** (2): the claim (120 unexposed controls, Table 1) and the table (Table 1, p4) are right, but the only candidate cell '(n=120)' is the second line of the column header 'Unexposed (n = 120)' - a header fragment, not a table cell, which rule 3 classifies as WRONG_CELL; value claim citing Table 6 (p22) and the table matches, but only 2 of the 5 candidate cells are asserted: '0.559' and '(0.546, 0.571)' (FreeHemoSeg x Overall, internal). 'SC, (95% CI)' is a fragment of the row label 'DSC, (95% CI)'; '0.497)' is SL Model's internal Grade II interval '(0.429, 0.497)'; '0.526' is FreeHemoSeg w/o SAM x Overall (internal). The external values the claim states, 0.512 (0.497, 0.526), are not the candidate cells

## 5. Pairs that needed manual or ambiguous interpretation

- P001/G002 (WRONG_CLAIM): Comparative claim ('best Dice') about the lambda = 1 row; judged under rule 1(e) because no numeric cell value is stated
- P003/G002 (VERIFIED_POSITIVE): The candidate claim text also carries Table 2's embedded text before the sentence; only the natural-language sentence was judged (rule 1). The candidate row_label '04' is the S.no column of the right row. 92.3 also appears in a per-dataset table on p7 ('ISLES Ischemic Lesion 92.3 ± 2.8'); the sentence explicitly cites Table 3.
- P014/G001 (WRONG_CELL): Disagreement resolved in favour of the independent pass: the first pass accepted this pair as VERIFIED_POSITIVE (medium) because the count is printed in that column, but that contradicted the written rule 3 ('header fragments' -> WRONG_CELL), which the independent pass applied. The claim->table link itself is correct; the claim's count lives in a column header, so no table cell carries it.

## 6. Disagreements with the independent pass and how they were resolved

- P014/G001: this pass **WRONG_CELL**, independent pass **WRONG_CELL** ("Claim (p3) asserts cohort sizes incl. '120 unexposed controls', citing Table 1 (p4). Candidate is Table 1 (same table; bbox truncated to header + first ~9 rows). The only candidate cell '(n=120)' is the second line of th"). Resolution: Disagreement resolved in favour of the independent pass: the first pass accepted this pair as VERIFIED_POSITIVE (medium) because the count is printed in that column, but that contradicted the written rule 3 ('header fragments' -> WRONG_CELL), which the independent pass applied. The claim->table link itself is correct; the claim's count lives in a column header, so no table cell carries it.

## 7. Verified gold pairs

- **P003/G002** — claim p5: "On the ISLES dataset for ischemic stroke lesion segmentation, our method achieves a remarkable average Dice score of 92.3%, outperforming several state-of-the-art methods, as shown in Table 3." → Table 3 (p6): row `04 | Proposed Method` × column `Dice Score (%)` = `92.3`.
