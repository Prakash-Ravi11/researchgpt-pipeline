# arXiv LaTeX e-print as a structured representation — BUILD

Branch `claude-code-verification` · HEAD `dc7ee24` (+ this change) · 2026-09-03
Inside Stage 1 (acquisition) and Stage 2 (processing). No new top-level stage. Production
`configs/` not modified — the LaTeX candidate lives only on the `use_extra_sources` (§O /
staging) path. Selector, evidence gate, scoring weights and prompt untouched. No new heavy
dependency: HTTP GET + stdlib `tarfile`/`gzip` only (no Docling / Marker / GROBID / Java /
Ghostscript). arXiv e-print requests throttled to **1 per 3 s**.

**This commit adds parsing only. No downstream measurement beyond parse success** (Phase 5
consumes the structured cells).

## Motivation (Test 1 — 23 paired papers, 6530 values)

PyMuPDF preserves digits (98.6 % verbatim) and page provenance (100 %) but **destroys table
structure**: only 8.9 % of table-resident values stay context-bindable, versus no collapse
on Europe PMC JATS. 23 of 24 arXiv papers ship compilable LaTeX with real
`tabular`/`\caption`/`\multicolumn`. arXiv is ~68 % of the canonical full-text corpus
(24 / 34).

## What was built

| # | change | where |
|---|--------|-------|
| 1 | arXiv **e-print LaTeX** as a preferred structured representation, ranked **above arXiv PDF, below JATS/XML** (`STRUCTURED_REPR_RANK = {jats:0, latex:1, pdf:2}`) | `schema.py`, `collection/semantic_scholar.py::_candidate_pdf_urls` |
| 1 | e-print retrieval: throttled HTTP GET → stdlib `tarfile`/`gzip` → main `.tex` detection → `\input`/`\include` resolution (cycle + depth 12 guarded) | `evidence/latex_source.py` (new) |
| 2 | **content / identity split, enforced.** LaTeX supplies content / tables / section structure ONLY. Identity + metadata come from the paired **arXiv PDF** and Semantic Scholar — never the `.tex`. `identity_validate` refuses `rep_type="latex"` outright; `validate_acquisition_record` rejects a `REPR_LATEX` record whose `identity_source` is not `arxiv_pdf`/`semantic_scholar`. Both files are kept (`.tex` for tables, `.pdf` for identity + per-table fallback). | `evidence/acquire.py`, `evidence/schema.py`, `collection/semantic_scholar.py::download_open_access_pdfs` |
| 3 | **structural cell model.** Every data cell retains: value, column header, row label, caption, section. `\multicolumn` expanded, `\multirow` recorded; `\input`/`\include` resolved upstream. One canonical shape (`structured_table()` / `table_cell()`). NOT a flat text dump. | `evidence/latex_tables.py` (new), `evidence/schema.py` |
| 4 | **per-table failure handling.** A table whose `tabular` env will not parse is marked `parse_status="fallback_pdf"` with a reason, and its PyMuPDF table text is attached as the fallback **for that table** (caption-token matched), recorded in `table_fallback`. Partial success per paper is accepted; silent failure is not. | `evidence/latex_tables.py`, `evidence/represent.py::blocks_from_latex` |
| 5 | **same cell model extended to Europe PMC JATS** (`<table>` grid → identical `structured_table` shape) so both structured sources produce ONE downstream shape. | `evidence/represent.py::_jats_table_cells` |
| 6 | four acquisition states, identity validation, content validation, provenance — all still apply. `FULL_TEXT` still requires passed identity + content; a `REPR_LATEX` `FULL_TEXT` additionally requires a non-LaTeX `identity_source`. | `evidence/schema.py::validate_acquisition_record` |

`build_document` / `process_paper_grounded` dispatch `representation_type == "latex"` →
`blocks_from_latex(tex_bytes, pdf_data=<paired arXiv PDF>)`. LaTeX chunks count as
`full_text` downstream, same as PDF/JATS.

## Parse-success report — 24 canonical arXiv full-text papers

Real acquisition split run per paper: e-print LaTeX for content, paired arXiv PDF for
identity + per-table fallback. `experiments/document_evidence_pipeline/latex_acquisition_report.py`;
raw JSON at `runs/latex_acquisition/latex_acquisition_report.json`.

| arXiv id | representation obtained | tables | parsed | PDF-fallback | structured cells | fallback reason(s) |
|---|---|--:|--:|--:|--:|---|
| 2503.18174 | latex | 2 | 2 | 0 | 44 | — |
| 2506.22210 | latex | 4 | 4 | 0 | 78 | — |
| 2411.07396 | latex | 22 | 22 | 0 | 1066 | — |
| 2401.08406 | latex | 23 | 23 | 0 | 278 | — |
| 2608.08340 | latex | 5 | 5 | 0 | 163 | — |
| 2608.26091 | latex | 25 | 25 | 0 | 501 | — |
| 2507.06956 | latex | 6 | 5 | 1 | 624 | no_data_cells_after_parse |
| 2506.06339 | latex | 4 | 4 | 0 | 98 | — |
| 2608.04137 | latex | 8 | 8 | 0 | 127 | — |
| 2605.15467 | latex | 4 | 4 | 0 | 128 | — |
| 2506.04838 | latex | 10 | 0 | 10 | 0 | no_data_cells_after_parse |
| 2512.12938 | latex | 9 | 5 | 4 | 29 | no_data_cells_after_parse |
| 2601.15457 | latex | 3 | 3 | 0 | 86 | — |
| 2509.16369 | latex | 8 | 8 | 0 | 104 | — |
| 2510.00261 | latex | 5 | 5 | 0 | 64 | — |
| 2504.07738 | latex | 4 | 3 | 1 | 35 | too_few_rows:1 |
| 2603.12396 | latex | 2 | 2 | 0 | 12 | — |
| 2605.03344 | latex | 10 | 5 | 5 | 65 | no_data_cells_after_parse, no_tabular_env_in_float |
| 2508.02872 | latex | 10 | 10 | 0 | 422 | — |
| 2604.22661 | latex | 3 | 3 | 0 | 633 | — |
| 2507.07695 | latex | 4 | 4 | 0 | 31 | — |
| 2504.00698 | **pdf fallback** | — | — | — | — | no_latex_source_in_eprint (identity OK; whole-paper falls back to PDF) |
| 2509.20707 | latex | 3 | 3 | 0 | 75 | — |
| 2607.29058 | latex | 4 | 4 | 0 | 68 | — |

### Summary

- **LaTeX representation obtained: 23 / 24** (matches Test 1's "23 of 24 ship compilable
  LaTeX"). The 1 miss (`2504.00698`) has no `.tex` in its e-print bundle — its LaTeX
  candidate is rejected and the whole paper falls back to the arXiv PDF; identity still
  passed, so `acquisition_status` is unchanged.
- **Tables: 157 parsed + 0 partial + 21 PDF-fallback** = 178 across the 23 LaTeX papers.
- **4731 structured cells** retained, each carrying value + column_header + row_label +
  caption + section.
- **Per-table fallback reasons:** `no_data_cells_after_parse` 16 (the `tabular` env parsed
  but no data cell survived — text-only tables, exotic cell layouts, or a header-only grid);
  `no_tabular_env_in_float` 4 (image/`\includegraphics` "tables"); `too_few_rows:1` 1.
- Fallbacks concentrate on 3 papers (`2506.04838` 10/10, `2605.03344` 5/5, `2512.12938`
  4/9); 18 of 23 papers parse **every** table. `\multicolumn`/`\multirow` produced **0
  "partial"** rows on this corpus — the span handling held.
- No LaTeX metadata was read for identity on any paper — `identity_source = "arxiv_pdf"`
  for all 23.

## Tests

- `tests/test_pipeline.py` + `tests/test_anchors.py`: **15/15**.
- experiment suite `tests/test_pipeline_units.py`: **42/42**.
- 12 staging invariants: **<pending — staging_run.py>**. No new invariants.

## Not in this commit (deliberate)

- No downstream measurement — no bindability re-measure, no coverage delta. Phase 5 wires
  the structured cells into the gate; the chunker does not yet carry `table_cells` forward
  to `chunks.json`.
- `no_data_cells_after_parse` (16 tables) is the honest macro long-tail. Each fell back to
  the PDF with provenance; tightening the cell heuristic is a follow-up, not this commit.

---

# Phase 4a — Bug 3: numeric-value loss in the LaTeX path, and the parity gate

Phase-4b MEASURE 1 (Test-1 bindability re-run, 23 paired papers, 6,530 meaningful values)
showed the LaTeX ingestion path was **losing ~60 % of table-resident numeric values** the
PDF path preserves (table verbatim-lax LaTeX **0.388** vs PDF 0.987). This section is the
fix + an enforced parity gate so the representation entering 4b can never be worse than the
PDF baseline.

## Mechanism

Two causes, both "the structured parser was treated as a replacement for the text, not a
layer on top of it":

1. **`blocks_from_latex` linearised only the cells the structural parser captured** and
   dropped everything else: the 16 `no_data_cells` fallback tables whose PDF-fallback
   caption didn't match contributed *nothing*; `_clean()` emptied cells containing
   `$…$` / `\num{}` / `88.5\pm0.3` / `\multicolumn`; whole columns were dropped on header
   misalignment.
2. **`_tex_prose` used the lossy cell cleaner** (`_clean`), so inline-math and `\num{}`
   numeric bodies in prose were also lost (prose verbatim-lax LaTeX 0.688 vs 0.982).

A third, harness-only cause surfaced during the fix: the MEASURE-1 script assembled the
LaTeX by crudely concatenating every `.tex` member (`extraction_fidelity._extract_tex`),
**not** through `latex_source`'s `\input`/`\include` resolution that production uses — so it
was scoring the parser against a worse input than the real path ever sees. Fixed in the
harness (`_assembled_tex` now routes through `latex_source.fetch_eprint_latex`).

## The fix (Stage-2 representation only)

- **`schema.structured_table` gains `raw_text`** — the FULL verbatim cell content of the
  table, every value, including cells whose structural parsing failed. Structured `cells`
  are now explicitly *metadata layered on top of `raw_text`*, never a replacement.
- **`latex_tables._numeric_verbatim` / `_tabular_raw_text`** — a numeric-preserving
  lineariser: unwraps `\num{}` / `\SI{}` / `\textbf{}` keeping the inner token, keeps `$…$`
  contents, turns `\pm` / `\times` / sub-/superscripts into spaces (numbers on both sides
  survive), `&`→` | `, `\\`→space. Every `structured_table(...)` call — including the
  `too_few_rows` / `row_split_error` / `no_tabular_env_in_float` early returns — now carries
  `raw_text`.
- **Per-table, not all-or-nothing.** A table with 5 of 20 cells failing keeps all 20 values
  in `raw_text` and structure for the 15; `parse_status="fallback_pdf"` now means "no
  structured cells" — the value text still ships. The 16 `no_data_cells` tables contribute
  their content.
- **`blocks_from_latex` table block `text` = `caption || linearised cells || raw_text`** —
  raw_text always present, so no numeric value is dropped. PDF-fallback text is appended
  only when raw_text *and* cells are both empty.
- **`_tex_prose` routed through `_numeric_verbatim`** — prose numerics preserved.
- Structured-cell shape (value, column_header, row_label, caption, section) **unchanged** —
  it is metadata alongside the lossless text, consumed by Phase 5 from there.

## The parity gate (`src/evidence/latex_parity.py` + `process_paper_grounded`)

Enforced in ingestion, not a report line. For each paper acquired as LaTeX:

1. ground truth = every numeric-anchor **occurrence** (`NUMERIC_ANCHOR_RE`, the gate's own
   rule) in the `\begin{document}`…`\end{document}` body, split **table / caption / prose**
   from the LaTeX source (`_numbers_by_location`, no experiment-harness import).
2. compute verbatim-lax survival of each split under the LaTeX blocks and under the paired
   arXiv-PDF blocks.
3. **if LaTeX survival + `latex_parity_tolerance` < PDF survival on *any* split → the paper
   FALLS BACK to the PDF representation**, and `{latex_survival, pdf_survival, per_location,
   n_ground_truth}` is recorded on every chunk's `latex_parity_fallback`.

`latex_parity_tolerance` is a config value (`evidence_grounding.latex_parity_tolerance` in
`configs/staging_config.yaml`; **production `configs/config.yaml` untouched**), **default
strict = 0.0** (LaTeX must not lose a single value the PDF keeps). `schema.validate_
acquisition_record` already refuses a `REPR_LATEX` record without a non-LaTeX
`identity_source`; this adds the content-parity half.

## MEASURE 1 — before / after (same 23 paired papers, 6,530 values)

verbatim-lax = "is the value present anywhere in the ingested chunks". L = LaTeX path,
P = PDF path.

| split | n | vb-lax **before** L/P | vb-lax **after** L/P | vb-strict after L/P | bindable after L/P |
|-------|--:|--:|--:|--:|--:|
| all | 6530 | 0.441 / 0.986 | **0.981 / 0.986** | 0.752 / 0.699 | 0.184 / 0.168 |
| table | 5405 | **0.388** / 0.987 | **0.983 / 0.987** | 0.708 / 0.643 | 0.110 / 0.089 |
| prose | 965 | 0.688 / 0.982 | **0.971 / 0.982** | 0.959 / 0.966 | 0.542 / 0.555 |
| caption | 160 | 0.744 / 1.000 | **0.981 / 1.000** | 0.981 / 1.000 | 0.525 / 0.531 |

- **Numeric survival is at parity** — within ≤ 1.9 pp of the PDF path on every split, up
  from a 60 pp table gap. The residual sub-2 pp is **location-classification skew** between
  two independent numeric extractors (the gate's `_numbers_by_location` vs the harness's
  `numbers_from_latex`) on the *kept* papers — the per-paper, per-location parity check
  passed for every kept paper; it is not lost content. Not tuned away.
- **Parity-gate fallbacks: 12 of 23 papers.** Genuine LaTeX deficits — LaTeX survival
  ranged 0.55–0.998 vs PDF, all strictly below PDF on at least one split, all fell back to
  PDF. Examples: `68f93a5921c1` 0.548 vs 0.936, `4f3fca4c4fa8` 0.565 vs 0.939,
  `2009dbb5f290` 0.593 vs 0.951; near-parity ones (`f3b06a914702` 0.998 vs 1.000) fall back
  too under strict tolerance. 11 papers kept LaTeX.

## Honest interpretation — bindability

**Once survival is at parity, LaTeX structure barely improves context-binding.** Table
bindable rises only **0.089 → 0.110** (+2.1 pp); prose (0.542 vs 0.555) and caption
(0.525 vs 0.531) are flat-to-slightly-*below* the PDF path. This is **not** the lift Test
1's JATS control implied, and it is reported as the genuine finding, not adjusted: the
bindability definition, metric hints, and context window are unchanged. The structural cell
model is correct and is still worth carrying for Phase 5 (which consumes `cells` directly
rather than via a ±90-char text window), but on this corpus, via chunk text, LaTeX ≈ PDF
for binding.

## Invariant-blindness observation

The 12 staging invariants **passed under the broken ingestion too** (the 0.388-table-survival
version: `STAGING_PASS`, 12/12, 0 errors). They check wrong-paper / provenance / no-leakage
/ gate-active / architecture-unchanged — **none of them measures numeric fidelity**. A green
invariant run is therefore *not* evidence that the representation preserves content; only the
MEASURE-1 parity comparison is.

## Tests (re-run after the fix)

- `tests/test_pipeline.py` + `tests/test_anchors.py`: **15/15**.
- experiment suite `tests/test_pipeline_units.py`: **42/42**.
- **12 staging invariants PASS** (`staging-20260903T154909Z`, parity gate active), monitor
  `overall: OK`, `DECISION: STAGING_PASS`, 0 errors, runtime 541 s. No new invariants. (This
  run's `data_test` chunk count rose 1,790 → 3,505 as parity-failed papers fell back to the
  fuller PDF representation.)
- MEASURE 2/3/4 remain **not run** — deferred until this parity gate is accepted.

## MEASURE 1 re-sliced — RETAINED vs FALLBACK

The pooled M1 above mixes the 12 parity-fallback papers (now on the PDF representation, so
L == P for them) into the LaTeX column, halving the visible effect. Re-slice of the SAME
`runs/latex_ingestion/m1_per_paper.json` (no new run):

- **RETAINED** — 11 papers that stayed on LaTeX (`4d6e977f0e5c 69b02cfebf3c 93db4f9a329d
  a6d08e12d2ef a9b2a3fd6070 cf099b7cd7e8 db78acdc12fd ddb170b2eeb8 e0efa866a1e4 eaec7401af70
  f3d7e0165df8`)
- **FALLBACK** — 12 papers that hit the parity gate

> The per-paper artifact stored `verbatim` **strict** only (not lax) and no per-split n, so
> this re-slice reports vb-strict / bindable / provenance as **macro** (mean of per-paper
> rates) and **gt-wt** (per-paper rates weighted by that paper's ground-truth count). The
> exact occurrence-pooled vb-lax for the subset cannot be rebuilt from this artifact without
> re-running; pooled vb-lax was ≈ 0.98 L / ≈ 0.99 P for both.

### RETAINED only (n = 11)

| split | vb-strict L/P (macro) | vb-strict L/P (gt-wt) | bindable L/P (macro) | bindable L/P (gt-wt) | prov L/P (macro) |
|-------|--:|--:|--:|--:|--:|
| all | 0.837 / 0.840 | **0.877 / 0.786** | 0.311 / 0.249 | **0.210 / 0.174** | 0.837 / 0.840 |
| table | 0.825 / 0.817 | **0.866 / 0.768** | **0.241 / 0.134** | **0.142 / 0.085** | 0.825 / 0.817 |
| prose | 0.896 / 0.955 | 0.964 / 0.961 | 0.528 / 0.587 | 0.597 / 0.559 | 0.896 / 0.955 |
| caption | 0.857 / 1.000 | 0.963 / 1.000 | 0.359 / 0.243 | 0.500 / 0.272 | 0.857 / 1.000 |

### FALLBACK control (n = 12)

| split | vb-strict L/P (macro) | bindable L/P (macro) | prov L/P (macro) |
|-------|--:|--:|--:|
| all | 0.817 / 0.817 | 0.249 / 0.249 | 0.817 / 0.817 |
| table | 0.791 / 0.791 | 0.154 / 0.154 | 0.791 / 0.791 |
| prose | 0.965 / 0.965 | 0.567 / 0.567 | 0.965 / 0.965 |
| caption | 1.000 / 1.000 | 0.317 / 0.317 | 1.000 / 1.000 |

FALLBACK L == P **exactly** on every metric and both aggregations — the 12 are fully on the
PDF representation, as intended. Clean control.

### Two cheap checks (same data)

- **`no_data_cells` tables concentrate in FALLBACK**: 16 total → **14 in FALLBACK papers**
  (`2506.04838` 10, `2512.12938` 4), **2 in RETAINED** (`2507.06956` 1, `2605.03344` 1).
- **The 12 fallbacks do NOT simply cluster on the 3 heavy-table-failure papers.** Of
  `2506.04838` / `2605.03344` / `2512.12938`: two (`2506.04838`, `2512.12938`) fell back;
  the third (`2605.03344`, 5 fallback tables but only 1 `no_data_cells`) reached numeric
  parity via the new `raw_text` lineariser and was **RETAINED**. The other 10 fallbacks are
  papers with modest per-location deficits under strict tolerance (LaTeX survival
  0.55–0.998, each below PDF on ≥ 1 split).

### Verdict

**CONDITIONAL** — on the 11 RETAINED papers, table bindable is **0.142 vs 0.085 (gt-wt,
+5.7 pp) / 0.241 vs 0.134 (macro, +10.7 pp)**, roughly **2–3× the pooled +2.1 pp**; "all"
bindable +3.6 pp gt-wt / +6.2 pp macro. Prose bindable stays flat (macro slightly negative,
0.528 vs 0.587); caption rises (+11–23 pp) but n is small. So the structural benefit is real
on the ~48 % of papers where the parser achieves numeric parity — it roughly doubles the
(still low, ~0.14) table bindable rate there — and is correctly suppressed to the PDF
baseline on the rest by the gate. It is **not** a corpus-wide lift, and prose binding does
not improve at all.

---

# Phase 4b — MEASURE 2 / 3 / 4 (canonical 34, parity-gated LaTeX ingestion)

Canonical 34 full-text re-ingested through the parity-gated LaTeX path (`_assembled_tex` =
production `\input` resolution), then `content_aware@10`, seeded, clean cache. Split
**11 LaTeX-retained / 12 PDF-fallback (parity gate) / 9 PDF non-arXiv / 2 JATS**.

## MEASURE 2 — downstream extraction

| metric | post-3.2b baseline | 4b (all 34) |
|---|--:|--:|
| mean non-empty fields / paper | 9.65 | **8.00** |
| conformance | 32 conf / 2 salv / 0 nonconf | **25 conf / 5 salv / 1 repaired / 1 repaired_salvaged / 2 no_response** |
| circuit-breaker fallbacks | 0 | 1 (`e0efa866a1`, recovered under legacy) |
| `_extraction_failed` | 0 | **2** (`69b02cfebf`, `eaec7401af` — both `no_response`) |
| `done_reason == "length"` | 0 | **2** (`69b02cfebf`, `eaec7401af`) |
| method / datasets / metrics / results / limitations | 100 / 97 / 91 / 94 / 94 % | 85 / 82 / 74 / 88 / 74 % |

### AMENDMENT A — by representation subset (this is the finding)

| subset | n | mean fields | method | datasets | metrics | results | limitations |
|---|--:|--:|--:|--:|--:|--:|--:|
| **RETAINED (LaTeX)** | 11 | **4.73** | 55 % | 55 % | 36 % | 73 % | 36 % |
| ARXIV_FALLBACK (→PDF) | 12 | **10.00** | 100 % | 100 % | 100 % | 100 % | 100 % |
| OTHER (non-arXiv) | 11 | 9.09 | 100 % | 91 % | 82 % | 91 % | 82 % |

**RETAINED vs its own post-3.2b frozen baseline: mean 9.91 → 4.73. 0 better, 8 worse,
3 unchanged.** Per paper:

| paper | frozen → 4b | conformance (4b) | done_reason |
|---|--:|---|---|
| `69b02cfebf3c` | 10 → **0** | no_response | **length** (truncated) |
| `eaec7401af70` | 10 → **0** | no_response | **length** (truncated) |
| `a9b2a3fd6070` | 10 → **0** | conformant (empty JSON) | stop |
| `4d6e977f0e5c` | 10 → 2 | salvaged | stop |
| `ddb170b2eeb8` | 9 → 2 | salvaged | stop |
| `cf099b7cd7e8` | 10 → 4 | repaired_salvaged | stop |
| `db78acdc12fd` | 10 → 6 | repaired | stop |
| `93db4f9a329d` | 10 → 8 | salvaged | stop |
| `a6d08e12d2ef` / `e0efa866a1e4` / `f3d7e0165df8` | 10 → 10 | conformant | stop |

**The structural gain did not survive to extraction — it inverted.** Only 3 of 11 retained
papers extract cleanly; 8 regressed, 3 to *zero* fields. The `done_reason == "length"`
watch item fired exactly where the task anticipated ("LaTeX gives denser structured tables,
so if the cap starts firing this is where it shows") — 2 papers, both LaTeX-retained, both
truncated, both failed.

**Mechanism.** The M1 parity fix restored numeric survival by putting the full verbatim
table content (`raw_text`) into the block `text` — a wall of pipe-separated cell tokens
(`Method | Dice | HD95 | AUC nnU-Net | 82.1 | 4.8 | 0.913 …`). Stage 4 sees only block
`text`, not the structured `cells` (Phase 5's job). Feeding qwen2.5:7b that dense,
low-prose token soup as extraction context produces unparseable JSON, hits the
`num_predict` cap, or returns nothing. **The representation that preserves the most numbers
is the worst for the model.** The PDF path's collapsed-but-prose-like table text extracts
better than the LaTeX path's lossless-but-unreadable one.

## MEASURE 3 — 0549e2e9 (JATS, not arXiv)

`rep = jats_xml`. 4a's JATS change attaches structured `cells` but leaves the table block
**text unchanged**, so there is no LaTeX effect and none expected. Result: `conformance =
salvaged`, `done_reason = stop`, `response_truncated = False`, **7 fields**, circuit breaker
did **not** fire; salvage recovered 0 additional / discarded 0. **Identical to its 3.2d
state.** 3.2b's `num_ctx` budget fix survives structured JATS input — the regression risk
flagged for 0549e2e9 did not materialise (and could not: its input is unchanged).

## MEASURE 4 — field-presence determinability (first real denominator)

Structured representation exists for **13 / 34 papers = 11 LaTeX-retained + 2 JATS** — the
first point in the project with a real presence denominator. Over those 13:

| field | determinable-present | determinable-absent | undeterminable | coverage-when-present |
|---|--:|--:|--:|--:|
| method | 8 | 5 | 21 | 62 % |
| datasets | 8 | 5 | 21 | 62 % |
| metrics | 5 | 8 | 21 | 38 % |
| results | 10 | 3 | 21 | 77 % |
| limitations | 5 | 8 | 21 | 38 % |

`undeterminable` (21) is reported separately, never folded into either bucket.
**Caveat: the numerator is poisoned by MEASURE 2.** 8 of the 13 determinable papers are the
LaTeX-retained subset whose extraction collapsed, so `determinable-present` is undercounting
because *extraction* failed, not because the field is absent. The denominator (13/34) is
real; the coverage-when-present rates are a floor, not a clean measurement, until the
representation is fixed. "determinable-absent" for the LaTeX subset still leans on heuristic
section labels — a lower bound on presence.

## AMENDMENT D — paper-facing findings

1. **12/12 staging invariants passed on the pre-fix ingestion that had discarded 60 % of
   table numerics** (`STAGING_PASS`, 0 errors). They check wrong-paper / provenance /
   attribution / no-leakage / gate-active / architecture — **never fidelity**. A green
   invariant run is not evidence that a representation preserves content.
2. **The pre-fix "bindability 0.089 → 0.120" was true and worthless** — the denominator had
   collapsed (only 38 % of table values were present at all). Survival and binding must
   always be reported together; either alone is misleading.
3. **Even with survival restored to parity, the representation that preserves the most
   numbers extracted the worst.** RETAINED mean fields 9.91 → 4.73. "Preserves more
   content" ≠ "better for the pipeline": Stage 4 consumes block text, and lossless verbatim
   table text is less model-legible than collapsed PDF text. A representation change must be
   validated end-to-end (M2), not just on survival (M1).

## Status

**Phase 4a remains BLOCKED** — now for a demonstrated downstream reason, not only M1. The
parity gate correctly protects the 12 fallback papers and the non-arXiv corpus (both at
baseline), so the *acquisition* + *identity split* + *parity gate* machinery is sound. What
is not usable is the **table-block text representation** for the retained papers. See the
two follow-up tasks below, then the final decision.

---

# Phase 4b — TASK 1 (isolate the cap) + TASK 2 (field routing)

The 9.91 → 4.73 M2 collapse on the 11 RETAINED papers had two confounded causes: unusable
input, and the 768 `num_predict` cap (untouched since 3.2b; **its first firing anywhere in
this project** — 3 of 11 retained papers hit `done_reason == "length"` + truncation +
`no_response`).

## TASK 1 — uncapped diagnostic (`extraction_output_reservation = 4096`, retained-11 only)

| | capped **768** | **uncapped 4096** | post-3.2b frozen |
|---|--:|--:|--:|
| mean non-empty fields / paper | 4.73 | **9.09** | 9.91 |
| conformance | 5 salv / 1 rep / 1 rep_salv / 2 no_response / 2 conf | **11 / 11 conformant** | — |
| `done_reason == "length"` | 3 | **0** | 0 |
| method / datasets / metrics / results / limitations | 55 / 55 / 36 / 73 / 36 % | **91 / 91 / 91 / 91 / 91 %** | — |

Per paper: 10 of 11 recover to a full 10 fields (`ddb170b2ee` 9 → 10, above its baseline);
the lone hold-out is `a9b2a3fd60` (0 fields, `conformant` — the model returned valid *empty*
JSON, a pre-existing failure mode unrelated to truncation or LaTeX).

**Verdict: SUBSTANTIAL RECOVERY.** The 4.73 collapse was **mostly the 768 cap masking**, not
unusable input. With output headroom the retained-LaTeX subset extracts at ~parity (9.09 vs
9.91, the gap entirely one empty-JSON paper). *The raised reservation was a diagnostic only
and is NOT left in place — `EXTRACTION_OUTPUT_RESERVATION = 768` is unchanged.*

## TASK 2 — field routing: separate what the gate reads from what the extractor sees

Change (routing, not parser): a table block's `text` (what Stage 4 sees) is now **caption +
linearised cells** only. The verbatim pipe-separated cell dump moves to `table_raw_text`, a
separate block field read by the **parity gate** (`check_parity` now scans
`text + table_raw_text` on the LaTeX side) and later by Phase 5. Structured `cells`
unchanged. PDF-fallback text / `raw_text` are used in `text` only when the structural parse
yields **no** cells.

### Parity gate — unchanged (verified, not assumed)

Re-ran M1: **the same 12 papers fall back, with byte-identical survival figures** (`2009dbb5f2`
0.593 vs 0.951 … `6437463b4b` 0.834 vs 0.852). The gate reads `table_raw_text`, so moving
the dump out of `text` does not affect it. On the now-cleaner **extractor-visible** chunk
text, LaTeX table verbatim-lax is **0.918 / 0.987** (linearised cells cover ~92 % of table
numbers; the last ~7 % live only in `table_raw_text` + `cells`), vb-strict **0.642 / 0.643**
(dead level), bindable **0.113 / 0.089**.

### MEASURE 2 on RETAINED-11, normal 768 reservation

| | capped 768 (pre-Task-2) | **768 + Task-2 routing** | uncapped 4096 | frozen |
|---|--:|--:|--:|--:|
| mean non-empty fields / paper | 4.73 | **5.82** | 9.09 | 9.91 |
| `done_reason == "length"` | 3 | **2** (`4d6e977f0e`, `eaec7401af`) | 0 | 0 |
| conformance | … | 4 conf / 5 salv / 2 no_response | 11 conf | — |
| method / datasets / metrics / results / limitations | 55/55/36/73/36 % | 73 / 73 / 27 / 73 / 55 % | 91 % all | — |

Cleaner routing lifts 4.73 → 5.82, but **still far below 9.91 and still truncating on 2
papers.** The linearised-cell text (`row / col = value ; …`, repeated per cell) is itself
dense enough to drive the model past 768.

## ACCEPTANCE — FAILS

Required: *M1 parity holds AND M2 on RETAINED ≥ its 9.91 baseline.* Parity holds (gate
decisions identical). **M2 on RETAINED = 5.82 at the normal reservation — below baseline,
with truncation still present.**

### The real finding

Structured LaTeX table text — even routed cleanly, even with every numeric value preserved
(parity) — is **worse extractor input than flattened PDF text**, and specifically along the
axis of *output-length pressure*: the structured/tabular rendering makes qwen2.5:7b generate
more, overrunning the 768 `num_predict` cap that PDF prose never approached. It is viable
only at a larger `extraction_output_reservation` (9.09 at 4096) — a 3.2b constant this task
forbids tuning. Parity of *content* does not imply parity of *extraction*.

Not tuned away: the bindability definition, metric hints, context window, and
`EXTRACTION_OUTPUT_RESERVATION` are all unchanged.

## DECISION — LaTeX ingestion disabled by default; measurement work committed

Per the task: acceptance failed → the arXiv-LaTeX-e-print candidate is **disabled by
default** (`evidence_grounding.latex_ingestion_enabled: false`, `configs/staging_config.yaml`;
production `configs/config.yaml` never carried it). The code path, the parity-gate module
(`src/evidence/latex_parity.py`), the harnesses, and this report are committed — **the
negative result is Phase 4's deliverable.** Flipping the flag on requires first raising
`EXTRACTION_OUTPUT_RESERVATION` (out of scope here) and re-running MEASURE 2.

### AMENDMENT D — paper-facing findings (final)

1. **Staging invariants are fidelity-blind.** 12/12 passed on the pre-fix ingestion that
   discarded 60 % of table numerics, and again on every intermediate broken state. They
   check wrong-paper / provenance / attribution / leakage / gate-active / architecture —
   never numeric fidelity or extraction quality.
2. **Survival and binding must be reported together.** Pre-fix "bindability 0.089 → 0.120"
   was literally true and worthless: only 38 % of table values were present at all.
3. **Content parity ≠ pipeline parity.** With survival restored to parity and nothing lost,
   the retained-LaTeX subset still extracted at 5.82 vs 9.91 — the structured table text
   drives the model past the output cap. A representation change must be validated
   end-to-end (MEASURE 2), never on survival (M1) alone; and "preserves more" is not a
   virtue if the consumer can't read it.
