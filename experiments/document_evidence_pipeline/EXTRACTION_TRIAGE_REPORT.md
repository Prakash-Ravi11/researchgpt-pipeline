# EXTRACTION TRIAGE REPORT — UI-observed corpus

Branch `claude-code-verification` · HEAD `b0d86b3` · 2026-09-02
**Measurement only. No fix implemented.** Any fix below is a recommendation for a later phase.

Scripts: `scripts/triage_extraction.py` (STEP 1–3), `scripts/triage_trace.py` (STEP 4–6).
Full rows: `experiments/document_evidence_pipeline/runs/extraction_triage/{per_doc.csv, per_page.csv, per_doc.json, trace_detail.json, field_presence.json, qwen_raw_*.txt}`.
All generation used the Phase-1 seeded path (`temperature 0`, `seed 42`), not production defaults.

## Corpus (third corpus — never merged with the frozen 60 or `data_test/`)

`data/raw_metadata/collected_papers.json` as of this run: **50 papers, medical-imaging / clinical / biomed domain**.
- **19 full-text** (12 Semantic-Scholar PDF, 7 arXiv PDF), all `representation_type: pdf`, all PDFs present.
- **31 abstract-only** (`has_full_text: false`, closed access, no PDF). 1 chunk each (the abstract); these
  are not full-text failures and are excluded from the buckets. Note: they extract **7–10 fields from the
  abstract alone** — so the LLM path is not globally broken.
- Chunk store: legacy schema (`evidence_grounding.enabled: false` was used) — 182 chunks / 50 papers.

## STEP 2 — representation distribution (full-text only, n=19)

| class | n | notes |
|---|--:|---|
| STRUCTURED (JATS / arXiv LaTeX) | **0** | no JATS; arXiv LaTeX available for 7 but not fetched (later phase) |
| BORN_DIGITAL_TEXT | 17 | real text layer on every page, `chars_per_page` 1257–5997 |
| MIXED (geometry) | 2 | `f82c2090…`, `330377da…` — pages with a large embedded image + little adjacent text |
| IMAGE_ONLY | **0** | — |
| UNKNOWN | 0 | — |

`chars_per_page` never drops into scanned territory (min 1257). No PDF has an empty text layer on any page.

## STEP 3 — buckets (full-text only, n=19)

| bucket | n | verdict |
|---|--:|---|
| **A1** NO_TEXT_LAYER | **0** | no scanned / textless PDF in this corpus |
| **A2** LOW_TEXT_DENSITY (text layer present) | **0** | lowest `chars_per_page` is 1257; no paper pairs low density with image dominance |
| **M** MIXED / image-region | 2 by geometry → **0 confirmed** | both flagged pages are **micrograph / figure images, not results tables rendered as images** (see STEP 4). One paper (`330377da…`) extracted all 10 fields anyway; the other (`f82c2090…`) had its results **table in the text layer** — it was extracted then destroyed by a JSON bug, not lost to an image. No results table exists only-as-image anywhere in this corpus. |
| **B** text present, chunk_count ~0 | 1 candidate → **0 confirmed** | `f09cd609…`: 4 326 chars → 1 chunk is **correct** (< `chunk_size` 800 words). Threshold false positive; `CUTOFF_HEADINGS` did not fire. Reclassified C. |
| **C** text + chunks + embeddings all present; loss is downstream | **17** | includes all 3 zero-field papers by structure (text/chunks/embeddings intact). Per task rule, not investigated as an infrastructure problem — but STEP 4 identifies the downstream cause. |
| **D** | 0 | — |

## STEP 4 — trace (B/M/D + the 3 zero-field papers), seeded re-run

| paper | bucket | raw→clean chars | cutoff@ | chunks | seeded re-run result |
|---|---|---|---|---|---|
| `330377dabc3f` | M(geom) | 80 064 → 60 854 | 0.76 | 13/13 | **all 10 fields** — image page p14 is a figure, not load-bearing |
| `f09cd60900e0` | B→C | 4 327 → 4 326 | none | 1/1 | 7 fields — 1-chunk paper, working as designed |
| `f82c20907921` | M(geom)+zero | 80 274 → 51 164 | 0.64 | 11/11 | **0 fields, reproduces.** Qwen emitted a leading-colon key `": Hypothesis and Objectives"` and (in the cached run) a nested enzyme-activity **table object** at top level → `normalize_extraction` kept nothing. The flagged image pages (29, 31–33) are **immunohistochemistry micrographs** ("Figure 4", "Figure 6"), not tables. |
| `9879e1cce991` | C+zero | 31 192 → 23 836 | 0.76 | 5/5 | **1 field (`method`), reproduces.** Qwen returned a **nested object** with keys `improvement` / `reasons` / `impact_on_other_metrics` (an ablation-style structure) instead of flat strings. |
| `d1f8a7f02d6c` | C+zero | 2 384 → 2 382 | none | 1/1 | **0 fields.** The "paper" is **1 page / 2 382 chars** (extended abstract). Nothing to extract; not a defect. |

### Root cause of the observed symptom

For the born-digital papers that return empty text fields, acquisition, the text layer, reference cutting,
chunking, and embedding are all **intact** (Bucket C). The loss is in **Stage 4 extraction**: on
clinical case-reports and wet-lab / biochem papers, `qwen2.5:7b` + the CS/ML-tuned `EXTRACTION_SYSTEM_PROMPT`
emits **non-conforming JSON** — nested objects, leading-colon keys, markdown, per-metric sub-structures —
and `_parse_json_response` / `normalize_extraction` salvage only the flat fields that happen to match,
leaving the rest empty while junk keys ride into `extraction_cache.json`. Observed junk keys across the
low/zero-field papers: `:1 :2 :3`, `**Summary of the Case:**`, `system` / `patient` / `diagnosis`,
`improvement` / `reasons` / `impact_on_other_metrics`, `": Hypothesis and Objectives"`, a nested results table.
This reproduces under the seeded path. **`metrics` is the single most-missing field (9 / 19 full-text papers)**,
consistent with numeric results living in tables that PyMuPDF flattens into unstructured text.

## STEP 5 — UI handoff

`paper_summaries.json` for `9879e1cce991` (UI shows "Not extracted"): **all fields empty**. `get_paper`
(`src/api/main.py`) returns the merged metadata + `paper_summaries.json` record verbatim. The backend
genuinely produced nothing — **this is not a rendering bug.** Ruled out.

## STEP 6 — field-presence determinability (full-text papers, n=19)

| field | determinable-present | determinable-absent | undeterminable | (heuristic heading found) |
|---|--:|--:|--:|--:|
| method | 0 | 0 | **19** | 14/19 |
| datasets | 0 | 0 | **19** | 17/19 |
| metrics | 0 | 0 | **19** | 15/19 |
| results | 0 | 0 | **19** | 15/19 |
| limitations | 0 | 0 | **19** | 15/19 |

No paper has a structured representation (0 JATS; arXiv LaTeX available for 7, not fetched). Without
section structure, whether a field is *present in the paper* cannot be mechanically determined — only
guessed from heading regexes on flattened PDF text (shown as a lower bound, not a denominator).
**Extraction coverage cannot be computed against a real denominator on any PDF-only paper in this corpus.**

## Three answers

1. **Is OCR needed?** — **NO.** Bucket A1 is empty; every full-text PDF has a real text layer
   (`chars_per_page` ≥ 1257). No scanned document in this corpus.

2. **Is image-region table work needed?** — **NO for this corpus.** Bucket M is non-empty by geometry
   (2 papers) but every flagged page is a micrograph / figure image, not a results table rendered as an
   image; no results table exists only-as-image. The geometric detector (`per_page.csv`
   `image_area_fraction` + `chars_near_image_regions`) should be kept for future corpora, but it has no
   work to do here.

3. **Is GROBID needed?** — **YES, qualified.** Not because Bucket B is non-empty (it is empty), but
   because **field-presence is undeterminable for 19/19 (100%) of PDF-only papers**: there is no
   structured section representation, so coverage has no real denominator and section-targeted
   extraction/retrieval cannot be grounded in true document structure. arXiv LaTeX (7/19) is the cheaper
   partial route; GROBID (or equivalent TEI section parsing) is what covers the Semantic-Scholar-PDF
   remainder.

## Recommendations (for later phases — not implemented here)

- **R1 (primary).** Harden Stage-4 JSON handling: reject / repair non-conforming responses (nested
  objects, markdown, stray keys) and retry with a schema-repair prompt, instead of silently keeping the
  flat subset. This is the direct cause of the zero-field symptom on non-CS papers and is domain-general.
- **R2.** The `EXTRACTION_SYSTEM_PROMPT` is CS/ML-shaped ("dataset", "metric", "SOTA"); clinical /
  wet-lab papers need field definitions that fit (e.g. "study population", "outcome measures",
  "statistical results"). Consider a domain-detect + prompt-variant step inside Stage 4 (no new stage).
- **R3.** Add structured section parsing so STEP 6 has a denominator: fetch arXiv e-print LaTeX where
  available (7/19), GROBID/TEI for the rest. Enables real extraction-coverage measurement and
  section-scoped retrieval.
- **R4.** Table extraction from the born-digital text layer (not images): `metrics` is missing on 9/19
  papers because PyMuPDF flattens tables. A PDF table parser (e.g. `pdfplumber` / Camelot on the text
  layer) would recover these; image-region OCR is **not** the lever here.
- **R5.** Drop the `chars > 3000 and chunk_count <= 1` Bucket-B rule or raise the char floor to one
  `chunk_size` worth of characters — it false-flagged a correctly-chunked 1-chunk paper.
