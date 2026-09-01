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

## BLOCKED / NOT ATTEMPTED
- `pytest` not installed in `.venv` → prior "37 tests pass" unverifiable.
- GROBID/Docling/MinerU not installed; no Docker. Java 24 present. GPU RTX 3050 6GB.
- Phases 3–13 not started (gated behind P1–P3 per brief).

## NEXT (single step)
Decision on Phase 2/3 (see `acquisition/DECISION_phase2.md`): **MODIFY — small**. Add OpenAlex `best_oa_location.pdf_url`
and Europe-PMC-by-PMCID as two extra links in the existing `_candidate_pdf_urls` fallback chain (+3 papers, ~30 LOC,
no new heavy deps). Do NOT pursue XML/JATS-first (2/60 availability) or full Crossref integration (~0 gain here).
Then re-run Stage 1 to get a *logged* per-source recovery rate and confirm +3 in production.
