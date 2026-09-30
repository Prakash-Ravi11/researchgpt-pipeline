# Phase 2.1 — corrected PDF identity evaluation

**These are Phase 2.1 corrected outputs** (evaluator-only fix of T5, T6, T7). The Phase 2 outputs are
preserved unchanged and remain the record of the original rule:

| Phase 2 artifact (unchanged) | SHA-256 |
|---|---|
| `pdf_identity_manifest.csv` | `909119d41c523e67f95494da5175b56d5da0e8eb1e20ac1faa1ab227cb004880` |
| `pdf_identity_details.json` | `888f775186ee9728880270f9367489fc96bbee31e884ad1e3a49e33bc08d9b73` |
| `phase2_pdf_identity.py` | `063c1b815625144b14e28c3c1ed52328968566f1ea0d3bd88ef7b4d23a3defa4` |

Phase 2 artifacts byte-identical after this run: **True**.

| | |
|---|---|
| Evaluator | `src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py` (imports every unchanged helper and threshold from `phase2_pdf_identity.py`) |
| Outputs | `pdf_identity_manifest_v2.csv`, `pdf_identity_details_v2.json`, this report |
| Run | 2026-09-29T23:58:53+00:00, git `30fc85d75d9e` (`claude-code-verification`), Python 3.10.18, PyMuPDF 1.28.2 |
| Command | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py` |
| Tests | `.venv/Scripts/python.exe -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_phase2_1_pdf_identity.py -q` |

## 1. What changed (and what did not)

| Check | Phase 2 rule | Phase 2.1 rule |
|---|---|---|
| T5 title | A candidate title of `NOT_REPORTED` was compared as if it were a title (a false FAIL) | `NOT_REPORTED` or empty gives **N/A**. Reported titles use the unchanged rule |
| T6 authors | Page tokens kept affiliation superscripts glued to surnames (`comte1`), causing false FAILs | Whole-word surname match on the PyMuPDF span stream. A trailing marker is accepted only if the PDF marks it as superscript (MuPDF flag, or smaller and raised span, or Unicode superscript). Normalization stages are recorded per surname |
| T7 arXiv | The candidate id found **anywhere** passed, including reference lists (false PASSes) | The candidate id passes **only** if it equals the page-1 arXiv stamp `arXiv:<id>[vN] [cat]`; other occurrences are kept for audit |
| decide | An N/A title counted as a title failure in the confidence clause | N/A title is neutral; otherwise unchanged |

Unchanged and re-verified for all 30 papers: T1–T4, T8, T9, all thresholds, and the candidate-consistency
checks C1/C2. The run aborts unless these reproduce the Phase 2 values exactly; they did (30/30).

## 2. Pre-run verification (no substitution)

- 62 PDF copies recorded in Phase 2 across 30 papers. 62 exist, and 62 hash to the Phase 2 SHA-256. They were re-hashed after the run: stable = **True**.
- No PDF was downloaded, searched for or substituted. Candidate ZIP SHA-256 is unchanged: **True** (`a11900f2ea572e89…`).

## 3. Summary

- Papers: **30**. **MATCH_VERIFIED 25**, **MATCH_WITH_DISCREPANCY 5**. MISMATCH 0, AMBIGUOUS 0, MISSING 0.

| Test | PASS | FAIL | N/A |
|---|---|---|---|
| T1 | 30 | 0 | 0 |
| T2 | 30 | 0 | 0 |
| T3 | 30 | 0 | 0 |
| T4 | 30 | 0 | 0 |
| T5 | 29 | 0 | 1 |
| T6 | 29 | 0 | 1 |
| T7 | 14 | 5 | 11 |
| T8 | 30 | 0 | 0 |
| T9 | 30 | 0 | 0 |

Status transitions, Phase 2 → Phase 2.1:

| Phase 2 | Phase 2.1 | Papers |
|---|---|---|
| MATCH_VERIFIED | MATCH_VERIFIED | 11 |
| MATCH_VERIFIED | MATCH_WITH_DISCREPANCY | 1 |
| MATCH_WITH_DISCREPANCY | MATCH_VERIFIED | 14 |
| MATCH_WITH_DISCREPANCY | MATCH_WITH_DISCREPANCY | 4 |

## 4. Every remaining discrepancy

| paper_id | test | candidate value | PDF-observed value | page | reason | normalization / rule |
|---|---|---|---|---|---|---|
| P006 | T7 | `1804.02767` | page-1 stamp: none on page 1; observed: 1804.02767 (later_page, p19) | 19 | no arXiv stamp on page 1; candidate 1804.02767 occurs on pages [19] | page-1 arXiv stamp only |
| P012 | T7 | `1809.07786` | page-1 stamp: none on page 1; observed: 1809.07786 (later_page, p9) | 9 | no arXiv stamp on page 1; candidate 1809.07786 occurs on pages [9] | page-1 arXiv stamp only |
| P017 | T7 | `2509.17925` | page-1 stamp: none on page 1; observed: 2509.17925 (later_page, p39) | 39 | no arXiv stamp on page 1; candidate 2509.17925 occurs on pages [39] | page-1 arXiv stamp only |
| P020 | T7 | `2006.01632` | page-1 stamp: none on page 1; observed: 1409.1556 (later_page, p18); 1411.1784 (later_page, p19); 1412.7062 (later_page, p19); 1511.06434 (later_page, p19); 1701.03056 (later_page, p21); 1705.02894 (later_page, p19); 1706.05587 (later_page, p19); 1710.10196 (later_page, p19); 1804.03999 (later_page, p19); 2006.01632 (later_page, p17); 2105.09511 (later_page, p21) | 17 | no arXiv stamp on page 1; candidate 2006.01632 occurs on pages [17] | page-1 arXiv stamp only |
| P030 | T7 | `2209.15076` | page-1 stamp: none on page 1; observed: 1806.04224 (later_page, p15); 1808.00457 (later_page, p16); 2209.15076 (later_page, p13); 2302.09516 (later_page, p16) | 13 | no arXiv stamp on page 1; candidate 2209.15076 occurs on pages [13] | page-1 arXiv stamp only |

## 5. Surname-level non-matches inside papers where T6 passes

These do not fail T6 at the unchanged 0.5 threshold. They are listed so that no candidate author error is hidden.

| paper_id | candidate surname | class | PDF-observed (audit) | page |
|---|---|---|---|---|
| P007 | Agarwala | mismatch_candidate_includes_marker | Agarwal[sup:a] | 1 |
| P027 | Erdoğan | mismatch_not_found | nearest word: Erdo˘gmu¸s1 | 1 |

## 6. T6 detail (all candidate surnames)

- Surnames checked: 252. By class: match_trailing_marker 137, match_exact 109, match_normalized 4, mismatch_candidate_includes_marker 1, mismatch_not_found 1.
- Normalization stage that made each match: exact 244, case_folded 4, compatibility_decomposed 2.
- Evidence for trailing affiliation markers: mupdf_superscript_flag 137.
- The per-surname record (class, stage, raw PDF text with `[sup:…]` markers, page) is in `pdf_identity_details_v2.json` → `papers[].t6`.

## 7. T7 detail (papers that report an arXiv id)

| paper_id | candidate | page-1 stamp | outcome |
|---|---|---|---|
| P001 | `2307.03579v1` | 2307.03579v1 | pass_page1_stamp |
| P002 | `2208.07566v1` | 2208.07566v1 | pass_page1_stamp |
| P004 | `2306.11490v1` | 2306.11490v1 | pass_page1_stamp |
| P006 | `1804.02767` | none | fail_no_page1_stamp |
| P011 | `2010.12391v2` | 2010.12391v2 | pass_page1_stamp |
| P012 | `1809.07786` | none | fail_no_page1_stamp |
| P013 | `2508.04522v1` | 2508.04522v1 | pass_page1_stamp |
| P015 | `2411.06842v4` | 2411.06842v4 | pass_page1_stamp |
| P017 | `2509.17925` | none | fail_no_page1_stamp |
| P018 | `2107.03846` | 2107.03846v2 | pass_page1_stamp |
| P019 | `2601.15759v1` | 2601.15759v1 | pass_page1_stamp |
| P020 | `2006.01632` | none | fail_no_page1_stamp |
| P021 | `2310.14172` | 2310.14172v1 | pass_page1_stamp |
| P022 | `2204.02779v4` | 2204.02779v4 | pass_page1_stamp |
| P024 | `2508.20475v2` | 2508.20475v2 | pass_page1_stamp |
| P026 | `2510.17999v2` | 2510.17999v2 | pass_page1_stamp |
| P027 | `2205.01675v1` | 2205.01675v1 | pass_page1_stamp |
| P028 | `2108.04175v1` | 2108.04175v1 | pass_page1_stamp |
| P030 | `2209.15076` | none | fail_no_page1_stamp |

Papers whose candidate reports no arXiv id but whose page 1 carries a stamp (T7 is N/A; informational): P008.

