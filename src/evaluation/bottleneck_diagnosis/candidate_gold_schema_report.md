# Candidate-gold schema and integrity report (Phase 1)

**Dataset status: CANDIDATE, not verified gold.** Nothing in this report verifies a claim, table,
cell or pair against a physical PDF. That is Phase 3. "Gold" appears below only as part of field
or file names the dataset itself uses (`gold_claim_cell_pairs`, `TABLE_GROUND_TRUTH`).

| | |
|---|---|
| ZIP (read in place, never extracted, moved or written) | `src/evaluation/candidate_gold/researchgpt_candidate_gold_30_2026-09-28 (1).zip` |
| ZIP SHA-256, identical before and after the run | `a11900f2ea572e89e9a4dd9424bf9279c256799f6cdbaca44ed0f60e0ee745ce` (528,329 bytes) |
| Measurement script | `src/evaluation/bottleneck_diagnosis/phase1_candidate_gold_inventory.py` |
| Machine-readable output (every number below comes from it) | `src/evaluation/bottleneck_diagnosis/candidate_gold_inventory.json` |
| Run | 2026-09-29T09:42:25Z, git HEAD `30fc85d75d9e` (`claude-code-verification`), Python 3.10.18 |
| Reproduce | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase1_candidate_gold_inventory.py` |

**What went into model context.** `README.txt` (1.1 KB) and `INDEX.json` (7 KB) were read in full.
Two sample records were read as samples: P004 table `T001` with its first 12 cells, and P007 pair
`G001`. Everything else was measured by the script and never loaded whole.

Labels used below:
- **Measured:** a count computed by the script.
- **Heuristic:** a flag meant for Phase 3 planning, not a verdict.
- **Interpretation:** my reading of the measurements.

---

## 1. ZIP integrity (measured)

| Check | Result |
|---|---|
| CRC test (`ZipFile.testzip`) | pass, no bad member |
| Members | 32: `INDEX.json`, `README.txt`, `P001.json` … `P030.json`. Numbering is contiguous and there are no unexpected members |
| Uncompressed size | 5,981,046 bytes |
| UTF-8 validity | 32 of 32 members are valid UTF-8 with no BOM |
| JSON syntax | 31 of 31 JSON members parse, with 0 syntax errors |
| `paper_id` matches the file name | 30 of 30 |

Per-member CRC32 and SHA-256 values are in `candidate_gold_inventory.json` → `zip.members`.

Encoding note: `±` is stored correctly as U+00B1 (bytes `C2 B1`). It occurs 676 times in `cells.raw_text`,
and there are 0 U+FFFD replacement characters. An earlier terminal print showed `�`. That was the
Windows console code page, not the data.

## 2. Declared versus measured counts (measured)

| Quantity | INDEX.json | Measured | Per-paper `extraction_audit` |
|---|---|---|---|
| papers | 30 | 30 | — |
| tables | 128 | 128 (`table_inventory` is also 128) | matches in 30/30 |
| cells | 8,322 | 8,322 (2,490 have a `numeric_value`) | matches in 30/30 |
| claims | 661 | 661 unique `claim_id`s (see §5.1) | matches in 30/30 |
| cross-references | — | 97 (23 papers) | matches in 30/30 |
| claim–table relationships | — | 87 (21 papers), covering 86 claims | matches in 30/30 |
| candidate claim–cell pairs | 44 | 44 (18 papers), holding 329 cell references to 318 unique cells | matches in 30/30 |
| numeric-normalization cases | 873 | 873 (21 papers) | matches in 30/30 |

The dataset is **internally consistent**. That shows only that the generator counted its own output
correctly. It says nothing about whether the output is correct.

## 3. Schema (`candidate-gold-2026-09-28-v1`, 30 of 30 papers)

Every paper has the same key set at every path (0 key-set variants across 194 key paths). The full path
and type table is in `candidate_gold_inventory.json` → `schema.paths`. One type variant exists:
`tables[].header_hierarchy` is a list in 114 tables and the string `"NOT_REPORTED"` in 14.

**Top level:** `paper_id`, `source_filename`, `schema_version`, `extraction_status` (`"candidate"` × 30),
`source_of_truth` (`"physical PDF only"` × 30), `source_pdf_unchanged`, `human_verification_required` (true × 30),
sections `01_metadata` … `13_limitations`, `TABLE_GROUND_TRUTH`, `CLAIM_TABLE_LINKING`,
`numeric_normalization_cases`, `extraction_audit`.

| Entity | Fields that exist | Fields that do NOT exist (absence is a finding) |
|---|---|---|
| Metadata (`01_metadata`) | title, authors, year, venue, doi, arxiv_id, pages, status, evidence{page, source_text} | `doi` = `NOT_REPORTED` in 30/30; `arxiv_id` = `NOT_REPORTED` in 11/30; `year` = `NOT_REPORTED` in 8/30 |
| Sections 02–13 | status (`REPORTED`/`NOT_REPORTED`), evidence[]{page, source_text}; sections 10 and 12 also have `claim_id` | offsets, bboxes |
| Table (`tables[]`) | table_id (`T###`, unique only within a paper), printed_label, caption, page, bbox (4 numbers, units not stated), rows, cols, header_hierarchy, original_contents (row-major grid of strings), source_evidence{page, caption_text, orientation} | spans (rowspan/colspan), footnotes, continuation links, a multi-level header tree |
| Table inventory (`table_inventory[]`) | table_id, printed_label, caption, page, bbox. Identical to `tables[]` for all 128 | — |
| Cell (`cells[]`) | cell_id (`T###_R#_C#`), table_id, row_index, column_index (1-based), raw_text, normalized_text, row_label, column_label, header_path, numeric_value, uncertainty, unit, significance_markers, cell_type, page | **cell bbox**, character offsets, span, multi-level header path (`header_path` has length ≤ 1 everywhere) |
| Claim (sections 10 and 12) | claim_id (`C###`), page, source_text | metric, reported value, subject/row entity, condition, claim type, offsets |
| Cross-reference | cross_reference_id, page, raw_reference, normalized_table_label, resolved, resolution | a resolved table_id |
| Claim–table relationship | relationship_id, claim_id, **table_id (null in 87/87)**, table_label, relationship_type (`explicit_reference` × 87), evidence_page, supporting_text, status (`CANDIDATE_UNVERIFIED` × 87) | — |
| Candidate pair (`gold_claim_cell_pairs[]`) | pair_id (`G###`), claim_id, table_id, cell_ids (1–50), binding_basis, confidence, human_verification_required (true × 44) | **metric, target row, target column, target value, the role of each cell, condition** |
| Numeric-normalization case | case_id, page, table_id, cell_id, raw_text, case_type, normalized_value, uncertainty, unit, human_verification_required | — (every field copies the referenced cell: 0 mismatches) |
| `extraction_audit` | the 7 counts above, self_audit_completed (true × 30), warnings (the same single warning × 30) | — |

## 4. Structural integrity checks (measured)

| Check | Result |
|---|---|
| Duplicate IDs within a paper (table, inventory table, cell, cell position, claim in section 10, claim in section 12, pair, relationship, cross-reference, case) | 0 |
| Distinct claim_ids with identical text | 0 |
| `cell_id` agrees with its (table_id, row_index, column_index) | 8,322 of 8,322 |
| Cell refers to an existing table | 8,322 of 8,322 |
| Cell `raw_text` equals `original_contents[row][col]` | 8,322 of 8,322; 0 cells fall outside the grid |
| Grid coverage | 11,033 grid positions. The 8,322 non-empty ones each have exactly one cell, and the 2,711 without a cell are all empty strings |
| `rows`/`cols` match `original_contents`; no ragged rows | 128 of 128 |
| `tables[]` agrees with `table_inventory[]` (label, caption, page, bbox); page and caption agree with `source_evidence` | 128 of 128 |
| Cell page equals table page | 8,322 of 8,322 |
| Numeric case agrees with its cell (table, page, raw_text, value, uncertainty, unit) | 873 of 873 |
| Pair → claim, pair → table, pair → cells, pair cells lie in the pair's table | 44 of 44, 329 of 329 |
| Every pair's claim has a relationship to the same table label | 44 of 44 |
| Relationship → existing claim | 87 of 87 |
| Page references within 1..`01_metadata.pages` (tables, cells, claims, all section evidence, cross-references, relationships, cases) | 0 out of range |
| bbox: 4 numbers, x0<x1, y0<y1, non-negative, ≤ 2000 | 128 of 128 pass. A check against each PDF's real page size needs the PDF and is deferred to Phase 2 |

**Reference-integrity findings (measured):**
- `claim_table_relationships[].table_id` is null in **87 of 87**. Relationships link a claim to a
  *label string* only.
- Relationship labels that resolve to **more than one table**: **20 of 87** (6 papers: P002, P006, P009,
  P015, P016, P026).
- Cross-references marked `resolved: false`: **97 of 97**. Cross-references whose label matches **no
  table** in the paper's inventory: **10** (6 papers), for example P004 "Table 1", P009 "Table 4"–"Table 7",
  and P025 "Table XX". These may be tables missing from the inventory; Phase 2/3 must check the PDF.
- Duplicate printed labels within a paper: **12** (9 papers). P016 has **7 tables all labelled
  "Table 4"**, while its claims cite "Table 4.1" … "Table 4.6". Interpretation: sub-numbered labels
  were collapsed when the dataset was generated.

## 5. Content findings (measured unless marked heuristic)

### 5.1 Claims
- Sections `10_quantitative_results.evidence` and `12_claims_and_conclusions.evidence` are **identical
  lists in 30 of 30 papers**. There is one claim list of 661, stored twice, not 1,322 claims.
- All 661 claims contain a digit. *Heuristic:* 131 (21 papers) begin with a section number
  (e.g. "2 Related works 2.1 Registratiom In the past…"), and 22 (14 papers) contain arXiv stamps or
  reference-list text (e.g. "Yolov3: An incremental improvement. arXiv preprint arXiv:1804.02767. [55]…").
- Only **86 of 661** claims have any claim–table relationship.
- *Interpretation:* the claim list looks like digit-bearing sentences, not curated quantitative claims.
  Phase 9 should compare against verified claims, not against these 661.

### 5.2 Cells and numeric representation
- `cell_type`: text 4,077, numeric 2,016, mixed_numeric_text 1,755, numeric_with_uncertainty 474.
  `unit`: `%` 24, `s` 4, otherwise null.
- **`normalized_text` equals `raw_text` in 8,322 of 8,322 cells.** No text normalization was applied.
  Normalized values exist only in `numeric_value` and `uncertainty`.
- `±` without a parsed uncertainty: **155 cells** (11 papers), mostly mixed_numeric_text fragments such as
  `'weeks, 28.2±3.6)'` and `'Baseline 0.748 ± 0.009 0.292 ± 0.02 29'`. `numeric_normalization_cases`
  has 629 `value_with_uncertainty` cases but only 474 non-null uncertainties.
- *Heuristic (merged cells):* **41 cells** (5 papers) contain two or more `±` values, e.g. P002 `T004_R2_C3`
  `'0.82±0.02 0.22±0.05 0.093±0.03'`. `numeric_value` keeps only the first value (0.82).
- `significance_markers`: 197 items, of which only 5 are `*`. **24 cells** (4 papers) carry "marker"
  lists that are the leftover characters of merged values split one per character (`'0'`, `'.'`, `'2'`,
  `'±'`, `' '`, …). The field is malformed in those cells.
- The 3 cells flagged as "`numeric_value` not found in text" are values written without a leading zero
  (`'.03365'` → 0.03365, `'.99 ± 0.1'`, `'.057'`). The values are correct; my tokenizer needs a leading
  digit, so these are **checker false positives, not data defects**.

### 5.3 Tables, headers and labels
- **Headers are single-level everywhere.** `header_path` has length 1 in 7,691 cells and 0 in 631.
  `header_hierarchy` is exactly grid row 1 in 114 tables and `"NOT_REPORTED"` in 14 (no header
  captured).
- `column_label`: value 5,890, **empty string 1,801**, `NOT_REPORTED` 631 (the cells of the 14
  header-less tables). `row_label`: value 4,757, **empty string 2,629**, `NOT_REPORTED` 936 (exactly the
  936 column-1 cells, which are the row labels themselves).
- *Heuristic (possible non-table text regions):* **36 of 128 tables** (15 papers) have a numeric-cell
  fraction below 0.1, and 23 of those have **zero** numeric cells. The P007 sample showed why: its
  "Table 3" `original_contents` is body text split into columns (`'As the two segmentati'`, `'on met'`, …).
- Captions: 10 end in a hyphen (truncated at a line break). In P030, 5 captions read "Table1" instead of
  the printed label "Table 1".

## 6. Candidate claim–cell pairs (characterisation only, not verification)

- **44 pairs** in 18 papers, with 329 cell references to 318 unique cells.
  - **13 pairs have one cell. 31 have 2–50 cells**; the distribution is in `distributions.pair.n_cells`.
  - A "pair" is therefore claim → cell set. The atomic candidate links number 329, which is the natural
    unit for Phase 3 verification and for any recall denominator.
- All 44 share one `binding_basis`: *"Explicit table reference plus exact numeric token overlap; not
  verified"*. All have `confidence` = `CANDIDATE_HIGH_IF_VISUALLY_CONFIRMED`.
- The table reference holds for all 44: every claim mentions the pair table's printed label. For
  8 pairs (P006 ×2, P016 ×6), that label is shared by more than one table in the paper (§4).
- The numeric basis does not hold uniformly:
  - **11 of 44 pairs share no whole numeric token with any of their cells.** In all 11, the claim's
    numbers appear in the cells only as **substrings**. Examples: "Table 4.1" → cell `84.13`,
    "Table 4.3" → `84.35` (P016); section "5.4" → `5.43` (P029); "3.3" → `73.3` (P021); "0.55T" →
    `0.5×0.5×0.5` (P015).
  - **1 more pair** (P007 G001) shares only the claim's leading section number "3.1". Its "cell" is the
    fragment `'3.1 Inter-observer ag'` inside a text region labelled "Table 3".
  - *Heuristic, and so combined:* **12 of 44 pairs** rest on a substring or structural-number
    coincidence (7 single-cell, 5 multi-cell). The other 32 share value-like numbers, but 26 of those
    32 are multi-cell sets, leaving 6 single-cell pairs.
- Numeric-coincidence exposure (measured):
  - 204 of 329 pair cells have a `numeric_value`.
  - **43 pair cells** have that value repeated elsewhere in the same table, and **77** in another table
    of the same paper.
  - 8 of 44 pairs point into tables with a numeric fraction below 0.1.
  - P014 G002 and G003 reference the same single cell.
- Per-pair detail (claim text, table, cells, labels, shared tokens, repetition counts) is in
  `candidate_gold_inventory.json` → `candidate_pairs`.

## 7. Ambiguities (enumerated)

No field in the dataset encodes ambiguity. The substring "ambig" occurs 9 times, all inside quoted paper
`source_text`. The measured ambiguity sources are:
- 31 multi-cell pairs;
- 12 duplicate printed labels in 9 papers;
- 20 relationship labels that resolve to more than one table;
- 97 of 97 cross-references unresolved, 10 of them to no table at all;
- 87 of 87 relationships with no `table_id`;
- the merged-cell and header-less tables described in §5.

## 8. Physical PDFs (preliminary presence only; identity checks are Phase 2)

- All **30 of 30** `source_filename`s exist on disk by exact filename, but **not in this worktree's data**.
  - They are in the sibling git worktree `C:\Users\Praka\Downloads\rgpt-exp-parser\data\medical30_eval\pdfs\`
    (branch `exp/r4-disambiguation`, untracked data).
  - A second copy of each is in `...\medical30_eval\_staging\`.
  - `67d7236f…` (P007) also has two copies inside this repository (`data/pdfs/` and
    `experiments/document_evidence_pipeline/runs/medical_reacquire/pdfs/`).
- Copies of the same file have equal byte sizes. They have **not** been hashed, page-counted or
  title-checked; that is Phase 2.
- A one-off filename search over `C:\Users\Praka\{Downloads, Documents, OneDrive}` (Desktop does not
  exist) found no other copies.

## 9. Is the candidate dataset usable? (interpretation)

- **As a candidate evidence source and a table/cell index to verify against the PDFs: yes.** It is
  structurally clean (§4), has stable IDs, and records a page and table bbox for every table.
- **As gold: no, not without Phase 3.** The measured reasons:
  - the pair basis is numeric-token overlap, and in 12 of 44 pairs that overlap is a substring or
    structural-number coincidence;
  - 31 of 44 pairs are cell sets rather than single targets;
  - relationships carry no table_id, and 20 of their labels are ambiguous;
  - the claim list is unfiltered digit-bearing sentences;
  - table reconstruction merges columns (41 cells) and includes text regions (36 tables with a numeric
    fraction below 0.1).
- **What a Phase 6 oracle needs that the dataset does not carry:** metric, target row, target column,
  target value per link, and condition. These fields do not exist (§3). They would have to be recorded
  during Phase 3 verification, marked "machine-assisted, unvalidated" unless Prakash labels them
  (RESEARCH_DIRECTIVE.md "Labelling authority").
