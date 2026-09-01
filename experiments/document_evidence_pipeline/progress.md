# Document-Evidence Investigation — progress

Branch: `claude-code-verification`   Baseline git: `af6de8e` (repo dirty: pre-existing uncommitted production edits, not mine)

## COMPLETED

### Phase 0 — Recon (verified against live repo)
- Real six-stage path traced: `run_pipeline.py` → `semantic_scholar.run_collection` → `pdf_parser.run_processing`
  → `build_index.run_embedding` → `summarize.run_summarization`. Web path (`orchestration/pipeline.py`) adds
  figure extraction + corpus synthesis + gap analysis.
- Acquisition = Semantic Scholar search + PDF fallback chain **S2 `openAccessPdf` → arXiv → Unpaywall(if contact_email)**.
  No OpenAlex / Crossref / Europe PMC in production code.
- Parser = PyMuPDF `page.get_text()`, regex-strip references, 800/100 word chunks. **No page/section/table provenance.**
- Retrieval (Stage 4) = dense ChromaDB cosine over bge-m3, per-paper `where` filter, 5 target queries × top-3
  (`retrieval_aware.py`). Config names a bm25+cross-encoder `hybrid_rerank` mode that this path does not use.
- Attribution: **none** (no OWN_PAPER/CITED_PAPER). Abstention: one regex "empirical evidence" gate in `summarize.py`.
- `src/evidence/verifier.py` exists but is untracked, `evidence_grounding.enabled: false` — **not wired into production**.
  (Minor bug: `_paper_text_coverage` appends an unsupported field to both `weak` and `supported`.)

### Phase 1 — Baseline (run `runs/20260901T150245Z-0e6dd1de/`, read-only)
- 60 papers, 60 abstracts, **31/60 full-text (51.7%)**, 304 chunks, 100% chunk coverage, 1 weak extraction.
- Identifiers: DOI 55/60, ArXiv 24/60, PMID 3/60, PMCID 2/60, S2 `openAccessPdf.url` non-empty 14/60.
- **ChromaDB works** — `researchgpt_papers` opens, 304 vectors, query returns hits, no `PanicException`.
  Full `build_index` embed→index→query cycle exits 0. The historically reported panic does NOT reproduce.
- 24/24 synthetic attribution oracle re-confirmed — deterministic fixtures, **not real-paper evidence**.
- Prior `FINAL_REPORT.md` numbers (50 papers / agriculture / 26 FT / 128 chunks) are **stale** — corpus was
  re-collected on "domain-generalizable medical image segmentation".

### Phase 2 — Multi-source acquisition (run `runs/20260901T150624Z-acq-2272d1/`, live, 667s)
Harness: `acquisition/resolve_corpus.py` (committed). Per-paper × {S2, arXiv, OpenAlex, Europe PMC, Crossref},
classified FULL_TEXT / ABSTRACT_ONLY / METADATA_ONLY / FAILED with PyMuPDF + JATS validation. No credentials.

- Baseline full text: **31/60 (51.7%)**  →  any-source ceiling: **34/60 (56.7%)**  →  **delta +3 papers (+5.0pp)**.
- +3 breakdown: OpenAlex OA PDF ×1, Europe PMC PMCID→JATS ×2.
- **26/60 unrecoverable from every free source.** All 26 have a DOI, **none** have ArXiv or PMC → closed-access,
  no preprint. This is a hard ceiling for free acquisition on this corpus.
- Source yield (papers each can independently supply full text): arXiv 24, OpenAlex 17, S2 8, Crossref 5, EuropePMC 2.
  The shipped pipeline is ~77% an arXiv fetcher (24 of 31).
- Reliability: S2 `openAccessPdf` 6/60 FAILED (dead/HTML), OpenAlex 13/60 FAILED, Crossref 17/60 FAILED.
- JATS/XML available for only **2/60** papers.

### Canonical pipeline — built + validated (`pipeline/`, tests `tests/`, `benchmark_canonical.py`)
Modules: schema · acquire (canonical record + deterministic identity + content validation) ·
represent (JATS + PDF → provenance blocks) · chunker (block-bounded, char offsets) · index (isolated
Chroma + BGE-M3, **no reranker**) · extract (LLM + verbatim-span verification) · attribute (deterministic
OWN/CITED/UNKNOWN) · decide (abstention gate) · run.

- **Level 1** unit/logic tests: **28/28** (`tests/test_pipeline_units.py`).
- **Level 2** (6-paper subset): ran E2E; 2 defects found + fixed (block-id provenance mismatch;
  bare "vs."/"compared to" misfiring as CITED on ablation-table headers).
- **Level 3** (full 60, run `runs/20260901T160444Z-canon-L3-ca6e/`, 38.7 min, qwen2.5:7b, reranker OFF):
  - Acquisition **33/60 as-run → 34/60 (56.7%) after fetch-cap fix** vs baseline 31/60. Wrong-paper accepted **0**.
    Identity rejections 1, content (landing-page) rejections 2.
  - Provenance-valid rate **100% (146/146)** grounded items. Schema problems **0**.
  - **Abstention on no-full-text quantitative fields: 81/81 (100%)** — zero fabricated Dataset/Metric/Result
    for the 26 inaccessible papers (baseline emits them anyway).
  - Attribution on quantitative items: OWN 8 (all correct on inspection), CITED 2, UNKNOWN 28
    (passive-voice self-description → not guessed).
  - Extraction returned/field: dataset 22, metrics 5, results 3, method 53, limitations 33.
    metrics/results low = abstention gate (23 EXPLICIT metrics / 11 EXPLICIT results suppressed for
    unconfirmed ownership).
  - **Post-run fix:** `pipeline/acquire.py` fetch cap 8 MB → 40 MB (8 MB truncated a 22 MB PDF →
    false identity reject of `413a184de4`). One-paper re-acquisition confirmed FULL_TEXT, title_sim 1.0.

## FINAL A/B (run `runs/20260901T170346Z-canon-L3-525e/`, 51 min, git a823aac)

- Acquisition: **34/60 (56.7%)** vs baseline 31/60 — confirmed by a full 60-paper re-acquisition
  (`runs/20260901T165648Z-acqverify-3b2b`, 40 MB cap). Lost vs baseline: none. Wrong-paper: 0.
- Provenance-valid: **150/150 (100%)**. Schema problems: 0. (Task-5 regression: no provenance loss.)
- Abstention on no-full-text quantitative fields: **78/78 (100%)**.
- Attribution rework effect: quantitative OWN **8 -> 22**, UNKNOWN 28 -> 16, CITED **2 -> 2**.
  metrics RETURNED **5 -> 13**, results RETURNED **3 -> 8**. All 21 returned quantitative items
  manually reviewed: **0 false OWN**. Both CITED items correctly abstained.
- VRAM peak 2.65 GB (of 6). No new models/services/parsers/rerankers.

## DECISION — see `FINAL_REPORT.md`

**GO_WITH_CHANGES.** Beats baseline on every axis (acquisition 51.7->56.7% at the validated
ceiling, 0 wrong-paper, 100% provenance, 0 fabricated quant claims for the 26 inaccessible papers,
0 false OWN across 21 returned quantitative items) and the recall rework tripled quantitative
coverage without losing precision. Not flat GO: production integration (FINAL_REPORT §O) + a
paired in-production A/B + a value sanity check remain; no human-gold precision measurement.

## BLOCKED / NOT ATTEMPTED
- `pytest` not installed in `.venv` → prior "37 tests pass" unverifiable.
- GROBID/Docling/MinerU not installed; no Docker. Java 24 present. GPU RTX 3050 6GB. **Not needed** — no
  measured structural problem PyMuPDF can't handle at the current bottleneck.
- Human-gold Dataset/Metric/Result labels — none exist; §H/§I/§J/§K numbers are coverage-under-verification
  + full manual inspection, not precision/recall vs gold.
- Paired A/B of the recommended Stage-4 changes inside production code (needs the integration in `FINAL_REPORT.md` §O).

## PRODUCTION INTEGRATION (FINAL_REPORT.md §O) — commits f12089d..fce2328

All 5 §O changes are integrated into the six stages, behind
`config['evidence_grounding']['enabled']` (default **false** = byte-for-byte legacy).

| # | change | files |
|---|---|---|
| — | validated logic promoted to `src/evidence/` (single copy); experiment `pipeline/{schema,attribute,represent,chunker}.py` are re-export shims (−635 LOC, no duplication) | `src/evidence/{schema,attribute,represent,chunker,acquire,gate,verifier}.py` |
| 1 | Stage 1: `_candidate_pdf_urls` -> `(source,url,repr)`, legacy order preserved when flag off; `download_open_access_pdfs(validate, use_extra_sources)` — identity + content validation, 40 MB streamed cap, OpenAlex/Crossref/Europe-PMC-JATS | `src/collection/semantic_scholar.py`, `src/evidence/acquire.py` |
| 2 | per-paper `pdf_source` / `representation_type` / `acquisition_status` / `identity_validation` / `content_validation`; `NO_ACCESSIBLE_FULL_TEXT` distinct | `src/collection/semantic_scholar.py` |
| 3 | Stage 2: `process_paper_grounded()` -> provenance blocks + chunking; chunk schema is a SUPERSET (adds section / page_or_node / block_id / char span) | `src/processing/pdf_parser.py` |
| 3 | Stage 3: section / page_or_node / block_id / representation into Chroma metadata | `src/embedding/build_index.py` |
| 4 | Stage 5: `run_evidence_gate()` after Stage 4 — verbatim span + hierarchical attribution + value sanity check + abstain; no-full-text -> Dataset/Metric/Result NOT_FOUND; rewrites `paper_summaries.json`, writes `paper_evidence.json` | `src/evidence/gate.py`, `src/summarization/summarize.py` |
| 5 | Stage 6 synthesis reads the gated fields directly (no code change; documented) | `src/synthesis/gap_analysis.py` |

**Verified so far (Phases 1–8):**
- Existing `tests/test_pipeline.py`: **37/37**. Experiment suite against promoted code: **37/37**.
- Production grounded-acquisition smoke (5 frozen papers): 22.1 MB PDF ✅, Europe PMC JATS ✅, OpenAlex
  recovery ✅, baseline paper preserved ✅, inaccessible -> NO_ACCESSIBLE_FULL_TEXT ✅.
- Evidence-gate smoke (synthetic): hallucinated dataset -> ABSTAINED; own metric -> RETURNED+OWN; cited
  number -> not returned; no-full-text paper -> 3/3 abstained + fields cleared; provenance 3/3.
- `git diff --check` clean; no secrets in additions; only intended files changed.
- Pre-existing uncommitted production WIP committed unchanged as baseline checkpoint `f12089d`.

## ⏸ PAUSED — RESUME HERE (Phase 9 + 10 + reports + final decision)

Stopped by user request (laptop offline overnight). Nothing lost — all code + Phase 1–8 validation
committed through `fce2328`. Partial A/B scratch dir was deleted (fully regenerable).

**To finish, run and then report on:**
1. `python experiments/document_evidence_pipeline/production_ab.py --arm both`
   (paired production A/B on the frozen 60-paper corpus; ~100 min: both arms fresh Ollama extraction.
   Writes `runs/prodab-*/report.md` + `{baseline,canonical}_metrics.json` + `*_paper_evidence.json`.)
2. Phase 10 quantitative sanity check: for every RETURNED metrics/results item in
   `canonical_paper_evidence.json`, verify value verbatim-in-evidence, belongs to the paper, provenance
   valid, attribution OWN (not CITED), not an unsupported inference. Target: 0 false OWN.
3. Acceptance criteria check (FINAL_REPORT-integration prompt): acq ≥ 31/60 and ≈ 34/60; identity/content
   validated; provenance ≥ 95%; 0 unsupported quant claims for inaccessible papers; metrics/results recall
   up vs baseline; `tests/test_pipeline.py` 37/37; production pipeline runs end-to-end.
4. Update `FINAL_REPORT.md` (add a "Production integration" section + A/B table + sanity check),
   `progress.md`, `board.md`. Separate MEASURED / INFERRED / BLOCKED / NOT TESTED.
5. Final decision: GO / GO_WITH_CHANGES / NOT_READY based on the production A/B (not synthetic tests).

Expected (from the isolated Level-3 A/B, `runs/20260901T170346Z-canon-L3-525e`): acq 34/60, provenance
100%, no-full-text abstention 100%, metrics returned ~13 / results ~8, 0 false OWN. The production A/B
must reproduce these to earn GO; deviations are the finding to report.
