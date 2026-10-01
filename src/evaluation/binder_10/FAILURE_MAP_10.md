# Phase 10 STEP 0 — Failure map of the 14 failing gold claims (before any v2 code)

Written on branch `exp/phase10-binder`, created from `acceptance/pre-phase10` (`6ed2434`). Line numbers refer
to `src/evidence/gate.py` at that commit.

## Sources
- **Legacy stages.** These were derived mechanically by a read-only script: the legacy binder, run on each
  claim's gold sentence. The flags were `fallthrough_policy = table_value_guard` (frozen) and borderless off
  in R-prod.
  - Records: R-prod = the L0 records and R-eval = the L1 records in `runs/p09b_run`.
  - R-oracle = the 09A oracle record for C012, C057 and C058 (`borderless_09a/results.json#oracle`).
  - Product unit = the gold coverage of the acceptance run (`acceptance_pre10/results.json#gold_coverage`).
- **Gold.** The gold cells are the phase 08 evaluator's reconstructed target cells. They are
  machine-assisted and not human-validated.

## Stage definitions (legacy)
- **product**: the claim's value is not in the Qwen extraction, so it never reaches the gate.
- **representation**: no reconstructed gold cell (`postfix_evaluate.reconstruction`).
- **candidate recall**: the gold cell exists but is not among legacy's candidates. Legacy's candidates are
  the cells under a column whose header matches the claim's metric words (`gate.py:453-454`) and that hold
  one of the claim's numbers.
- **ranking**: the gold cell is a candidate, but legacy chose another one.
- **verification**: legacy chose the gold cell, and its subject test rejected it (`_row_matches_subject`,
  `gate.py:330-337`, applied at `gate.py:471-479`).
- **gate**: bound correctly, then withheld.

## Stage distribution (14 claims)

| Unit | product | representation | candidate recall | ranking | verification | gate |
|---|---|---|---|---|---|---|
| Product unit (acceptance run) | **12** | 2 (C005, C057) | — | — | — | — |
| R-prod, L0 (gold sentence) | — | **9** | 4 | 0 | 1 | 0 |
| R-eval, L1 (gold sentence) | — | 3 | **10** | 0 | 1 | 0 |
| R-oracle (C012, C057, C058; gold cell only) | — | — | 1 (C057) | 0 | 2 (C012, C058) | 0 |

## Per claim
The v2 stages:
- **A**: ClaimFrame (values, structure, comparisons, required bindings).
- **B**: paper-local aliases.
- **C**: high-recall candidates.
- **D**: dimension scoring.
- **E**: ambiguity.
- **F**: verifier.
- **G**: gate fixes.
- **H**: LLM judge.

| Claim | Paper | Product | R-prod (L0) | R-eval (L1) | Legacy code path and mechanism | v2 stage(s) |
|---|---|---|---|---|---|---|
| C005 | P001 | reaches gate | representation | candidate recall | **R-prod:** Table 4 has no cells (no ruling lines), so `structural_bind` returns `pdf_only` (`gate.py:432-434`) → `unverifiable_binding` (`gate.py:587-589`). **R-eval:** the methods sit in the columns (`Ours`, `nnU-Net`) and "Dice" appears only in the caption. The metric-column cells are other tables' Dice columns and none holds 0.926, so the value is found elsewhere → `wrong_cell` (`gate.py:480-488`). | C (quantity from the caption; subject against column headers), B ("our method" → `Ours`), A (comparison 0.926 vs 0.920: two required bindings) |
| C012 | P004 | not reached | representation | representation | The gold table (Table 1) is never reconstructed: L0 is `pdf_only`, and L1 rejects it at borderless G1. **R-eval:** the binder binds a Table 2 cell (wrong), which is then withheld as `bound_to_ablation_table`. **R-oracle:** the gold cell is a DSC-column candidate. The implicit OWN subject (`gate.py:448-449`) fails `_OWN_ROW` on the row "UM-CAM+SPL" (`gate.py:263-265`, `330-337`) → `wrong_cell` (`gate.py:474-479`). | B (declared method alias "UM-CAM+SPL" from the claim tokens), C/D (table relevance: "Table 1"). Representation blocks R-prod and R-eval. |
| C021 | P006 | not reached | candidate recall | candidate recall | TABLE V has the methods as hierarchical columns (`YOLOv5 / Box` …), and "MAP" is only in the caption. No column matches "map", so there are 0 candidates and the numbers are found in other cells → `wrong_cell` (`gate.py:480-488`). | C (subject against the column header's top level, quantity from the caption, qualifier box/mask from the sub-header; whitespace-insensitive "Mas k" and "0.94 7"), A (4 required bindings), E (0.947 appears under both Box and Mask: the qualifier separates them) |
| C025 | P007 | not reached | representation | candidate recall | "ICC" is not a recognised metric word (`gate.py:32-38`, `73-87`), so `metric_toks` is empty → `not_bindable` (`gate.py:452-457`). It then falls through and the gate gives `attributed_to_cited_work` (the "[36]" citation). The claim is a threshold ("all exceed 0.922"), not an equality. | B (quantity alias "ICC" from the header "ICC3"), A (threshold claims are not bindings) |
| C027 | P008 | not reached | verification | verification | "Dice↑" is a column. The claim's numbers in order are 2.6, 0.84 and 0.87. The first number with a column hit is 0.84, on row DSRNet. The subject is implicit OWN (`gate.py:446-449`), and the DSRNet row is not OWN, so the result is `wrong_cell` on the gold cell. **The comparison is parsed as a single subject** (`gate.py:471-479`). | A (the comparison "from X by A to Y by B": two required bindings), D (one subject per binding) |
| C034 | P011 | not reached | representation | candidate recall | No metric word ("15 healthy fetal brains") → `not_bindable` (`gate.py:452-457`). It falls through: RETURNED in 09A, and abstained `table_value_unbound` by the guard (`gate.py:606-615`). | A (descriptive attribute: count), C (a count claim matches a count header, "Number of subjects"; the qualifier "training" matches the row `TRAINING`) |
| C035 | P011 | not reached | representation | candidate recall | No metric word ("gestational age … between 21 and 38 weeks") → `not_bindable` → falls through; abstained by the guard or as cited ("[14]"). | A (range 21–38 with unit), B (quantity alias "Gestational age (weeks)"). The subject (the atlas) has no lexical link to the row "EVALUATION Quantitative", so this needs H or an abstention. |
| C041 | P014 | not reached | candidate recall | candidate recall | No metric word (hippocampal volumes, p-values) → `not_bindable` (`gate.py:452-457`) → grounding → `ownership_unverified`. The methods are in the columns (`SRI-exposed (n = 62)`, `Unexposed (n = 120)`, `Adjusted Pa`). | A (multi-value comparison with left/right qualifiers and p-values), B ("controls" → `Unexposed` via the caption's "unexposed controls"), C (subject against column headers; quantity from the row label and caption) |
| C042 | P014 | not reached | candidate recall | candidate recall | The same mechanism as C041 (cortical folding indices). | A, B, C, as for C041 |
| C045 | P014 | not reached | candidate recall | candidate recall | The same mechanism as C041 (placenta volume, ADC_D; Table 3). | A, B, C, as for C041 |
| C048 | P015 | not reached | representation | candidate recall | "Dice" appears only in the caption ("Mean Dice scores"), so no Dice column exists → `not_bindable` (`gate.py:452-457`) → `ownership_unverified`. | C (quantity from the caption; qualifier "global" matches the column `Global`), B (subject "Fetal-SynthSeg" matches the row `FetalSynthSeg` after hyphen normalisation) |
| C052 | P016 | not reached | representation | candidate recall | The metric sits inside the cell text ("DSC: 83.79%, VS: 84.84%, HD95: 35.66 mm", column `Results`). The one candidate is a non-gold DSC-column cell → `wrong_cell`. The gold sentence itself ends at "(X.", where its citation was cut. | C (cell-internal quantity; a multi-metric cell binds only its DSC part). The cited subject has no link, so this likely ends in NO_BIND. |
| C057 | P017 | reaches gate | representation | representation | Table 6 is never reconstructed (L1 rejects it at G3). **R-oracle:** "DSCs" (plural) is not recognised, so `metric_toks` is empty → `not_bindable` (`gate.py:452-457`). | B (plural normalisation), A (values with a 95% CI; "respectively": internal/external). The DSC row group is absent from the oracle cell's context, so the quantity link may fail. |
| C058 | P017 | not reached | representation | representation | Table 7 is never reconstructed (L1 rejects it as `disagree`). **R-oracle:** the comparison is parsed as a single implicit OWN subject. The first number, 0.882, sits on the row "2D Stacks" → `wrong_cell`. "R2" (a reader) is parsed as the metric r² (`gate.py:85-87`). | A (comparison "from X to Y for R1"), B ("2D stack interpretation" → `2D Stacks`), E (0.882 appears for both R1 and R2, and the qualifier group is lost in the oracle cells, so it must abstain) |

## Reading
- **Product unit.** 12 of 14 claims never reach the gate, so in the product the earliest failure is extraction
  coverage for almost all of them.
- **Gold sentence.** The binder's dominant failure is **candidate recall**: 4 in R-prod and 10 in R-eval. The
  cause is the binder's single channel, a metric word that matches a column header. It misses:
  - metrics in captions, row groups or cell text;
  - methods-as-columns;
  - descriptive attributes (counts, ranges, ages);
  - plural or abbreviated forms.
- **Verification.** Its failures (C027 in R-prod and R-eval; C012 and C058 in R-oracle) are comparisons or
  named subjects forced into one implicit OWN subject.
- **No ranking failure.** Legacy never had two accepted candidates for these claims.
