# Phase 07 — Claim → cell verification on the 30 PDFs (new mining, not the 44 candidates)

## Objective
Mine the 30 physical PDFs for genuine natural-language claims that report a table value, point to a
table, and have a verifiable target cell. Verify them independently against the PDF: exact wording, no
paraphrase, no generated claims.

## Inputs
- The 30 canonical PDFs (Phase 01).
- `src/evaluation/bottleneck_diagnosis/postfix_mine_claims.py`: deterministic harvest; never calls
  `find_tables`, the binder or the gate.
- `src/evaluation/bottleneck_diagnosis/postfix_labelling_workflow.js`: the blind-reader protocol, with the
  prompts verbatim.
- `src/evaluation/bottleneck_diagnosis/postfix_evaluate.py` (`assemble`): the agreement rules, fixed before
  any evaluation.

## Work Performed
1. **Harvest** (rules in the `postfix_mine_claims.py` docstring). A candidate is a sentence that either
   names a table ("explicit") or directly follows a sentence naming exactly one table ("contextual"). It
   must carry a meaningful number that is printed on the table page outside the sentence itself.
2. **Blind double reading** of every candidate against 170-dpi page renders plus the PDF text layer:
   - reader A reads claim-first; reader B reads cell-first;
   - 4 agents in total: group G1 = C001–C043 and G2 = C044–C085, each group read by A and B;
   - the claim must be an exact substring of the harvested text (checked in code).
3. **Assembly:** a pair is VERIFIED_POSITIVE only if both readers say so, their claims coincide, and they
   agree on table, page, innermost row, leaf column and value. Any disagreement becomes AMBIGUOUS and is
   never a pair.
4. **Blindness audit** of all 4 reader transcripts (283 tool calls in total).

## Results
FACT, harvest: **85 candidates** (62 explicit, 23 contextual) from 24 papers. 303 table-reference
sentences were considered and 46 caption sentences skipped.

| Dropped | Explicit | Contextual |
|---|---|---|
| no meaningful number | 143 | 131 |
| number not on the table page | 52 | 21 |

Candidates per paper:

| P001–P010 | P011–P020 | P021–P030 |
|---|---|---|
| P001 6 | P011 4 | P021 1 |
| P002 2 | P012 0 | P022 1 |
| P003 3 | P013 3 | P023 0 |
| P004 2 | P014 7 | P024 1 |
| P005 5 | P015 4 | P025 0 |
| P006 6 | P016 3 | P026 11 |
| P007 1 | P017 5 | P027 0 |
| P008 2 | P018 2 | P028 1 |
| P009 4 | P019 0 | P029 6 |
| P010 1 | P020 0 | P030 4 |

FACT, labelling: labels completed **85/85 by both readers**; labels remaining **0**. Status agreement
between readers: 84/85 (raw; machine readers, not a human-labelled kappa category).

| Status | Reader A | Reader B | Final |
|---|---|---|---|
| VERIFIED_POSITIVE | 18 | 19 | **18** |
| WRONG_CLAIM | 60 | 60 | **60** |
| AMBIGUOUS | 5 | 4 | **5** |
| WRONG_ROW | 1 | 1 | **1** |
| WRONG_TABLE | 1 | 1 | **1** |

FACT, verified set: **18 claims, 55 pairs, 12 papers**: P001, P003, P004, P006, P007, P008, P011, P014,
P015, P016, P017, P030.
- Verified claims: C005, C010, C012, C013, C021, C025, C026, C027, C034, C035, C041, C042, C045, C048, C052,
  C057, C058, C085.
- Pairs by reference: explicit 29, contextual 26.
- Claim subject, by claims: own_method 12, dataset_or_cohort 4, baseline_or_cited 2. By pairs: own_method
  42, dataset_or_cohort 10, baseline_or_cited 3. (The subject belongs to the sentence; a multi-value
  own-method claim can include a baseline's cell.)
- Table orientation, by pairs: rows_are_entities 28, columns_are_entities 27.
- Same sentence as a candidate-ZIP pair (cells re-verified independently): P003/G002 (Stage A VP),
  P007/G001 (Stage A WRONG_CLAIM), P014/G002 and P014/G003 (Stage A WRONG_TABLE), P017/G002 (Stage A
  WRONG_CELL). The other 13 claims are new.

FACT, rejections (the reason for every candidate is in the gold JSON):
- WRONG_CLAIM: table/caption text fused into the "sentence" with no natural-language claim; pointer
  sentences without values; derived differences not printed in any cell (P009 C028–C031, P015 C050,
  P029 C080; P028 C075 is a sum); setup descriptions.
- AMBIGUOUS: C019, C020, C022, C024 (P006: the value is printed in two cells); C040 (P014: readers
  disagree).
- WRONG_ROW: C064 (P026). WRONG_TABLE: C043 (P014).

FACT, blindness audit: each reader accessed only `candidates.json`, the page renders and text layers, and
its own working files. No tool call referenced another reader's files, and no listing output shown to a
reader contained another reader's files.

FACT, verified claims by reference: explicit 9, contextual 9.

FACT, harvest recall limit. The harvest finds a table's page only when a text block *starts* with its
caption.
- 17 of 129 referenced table labels had no such caption: P001:5; P002:2,3,5,6,7; P005:6; P006:II;
  P009:4,5,6,7; P020:1,2; P025:XX; P030:1,6. Some of these may be supplementary or non-existent tables.
- 17 explicit numeric sentences reference only such tables, so they were dropped as "number not on a
  table page".
- Example: P001 Table 5's caption is merged below the table into its text block. The P001 p13 claim "…a
  higher average Dice score of 0.866 ± 0.013 compared to 0.847 ± 0.008 for our method" was therefore
  never a candidate.

INTERPRETATION:
- 18 genuine claims / 55 pairs exceed the user's approximate 30–50-pair aim (by 5), without forcing a quota.
- The recall limit means the set under-represents tables whose caption sits below them.
Labels are **machine-assisted, unvalidated**: only Prakash can validate them.

## Evidence
All in `src/evaluation/bottleneck_diagnosis/`:

| Artifact | SHA-256 prefix |
|---|---|
| `postfix_candidates.json` (harvest output, evaluator input) | `df94a0071f3892cf` |
| `postfix_blind_readings.json` (both readers' raw labels, evaluator input) | `450a327af10e03ae` |
| `postfix_labelling_workflow.js` (reader protocol) | `e8eed1c5d8588a2b` |
| `postfix_claim_cell_gold.json` (all 85 candidates with both readings and final status; 55 verified pairs with claim text, page, table, row/column levels, cell text, value, evidence excerpt, verification method and confidence) | `29ac3c4bd250b61e` |
| `postfix_claim_cell_gold.csv` | `6020ef8e480c16d5` |
| `postfix_claim_cell_report.md` | `221b17e0b275e4a4` |

## Decisions
DECISION:
- The contextual harvest tier was added before labelling. The trigger: a genuine claim on P001 p13 names
  its table (Table 5) only in the preceding sentence. The tier added 23 candidates, 9 of which became
  verified claims (e.g. C005, P001 p12 → Table 4). The P001 p13 claim itself was still missed, because of
  the caption-page recall limit above. Corrected 2026-09-30 after the checkpoint audit.
- Claims are verbatim substrings, never transcribed.
- Disagreements are never pairs.
- The 44 candidates are not reused as the primary set.

## Changes
New untracked files: `postfix_mine_claims.py`, `postfix_evaluate.py`, `postfix_labelling_workflow.js`,
`postfix_candidates.json`, `postfix_blind_readings.json`, and the three gold artifacts. No tracked file
changed.

## Temporary Files
- Scratchpad `postfix_mine/`: `candidates.json`, 77 PNG renders, 58 TXT text layers.
- Scratchpad `postfix_labels.json`.
- Readers' working files: `annot_c044/`, `assigned_c044_c085.txt`, `exact_C001_C043.json`,
  `label_c001_c043/`, `labeler/`, `my_cands_44_85.txt`, `my_labels_44_85.json`, `my_labels_44_85.py`.
- `regen_check/`: the harvest-regeneration check.

## Cleanup
- Preserved: `candidates.json` → `postfix_candidates.json`; `postfix_labels.json` →
  `postfix_blind_readings.json`. Both SHA-256 match the hashes recorded in the gold JSON's run metadata.
- Verified: the harvest regenerates a byte-identical `candidates.json`, so the renders are regenerable.
- Then all the scratch items above were deleted, on 2026-09-30.
- Harness-managed files under `~/.claude` and `%TEMP%/claude/.../tasks` were left alone.

## Current State
**Complete**; resumable from repository files alone. Nothing remains to label.

## Next Step
None within this phase. Human validation of the 55 pairs is Prakash's decision.

## Do Not Redo
- The harvest and the machine labelling. Never relabel with machine readers to change the gold.
- Never edit `postfix_blind_readings.json` or `postfix_candidates.json`.

## Reproduction
- Harvest: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/postfix_mine_claims.py <out_dir>`
  (regenerates `candidates.json` byte-identical, plus renders).
- Gold + evaluation: see Phase 08.
