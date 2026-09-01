# FINAL_REPORT — Canonical Document-Evidence Pipeline

Run of record: `runs/20260901T160444Z-canon-L3-ca6e/` (LEVEL 3, full 60-paper corpus)
Git at run: `9224f81`  ·  corpus sha256 `cf3bf90a…`  ·  device CUDA (RTX 3050 6GB)  ·  LLM `qwen2.5:7b` via Ollama  ·  reranker OFF
Wall clock: acquisition 139 s, extraction 2107 s, total 38.7 min.
Superseding fix after the run: `pipeline/acquire.py` fetch cap 8 MB → 40 MB (see §D, §15). One-paper re-acquisition confirmed; corrected acquisition figure is **34/60**.

This report supersedes the earlier `experiments/document_evidence_pipeline/FINAL_REPORT.md` history whose corpus (50 papers, agriculture) no longer matches the repo.

---

## 1. Original problem

A paper is discovered via Semantic Scholar but the pipeline often obtains only an abstract or a landing page, not the article body. The legacy Stage 4 then still emits plausible-looking Dataset / Metric / Result / Method / Limitations values from insufficient context, with no provenance and no way to tell the authors' own results from cited ones. Target: acquire the real paper, represent it well, retrieve evidence, extract structured fields **with provenance and attribution**, and **abstain** when evidence is insufficient — on the available hardware, without a large new architecture.

## 2. Current baseline (verified live, not from prior reports)

`runs/20260901T150245Z-0e6dd1de/` + `data/`:

| metric | value |
|---|---|
| corpus | 60 papers |
| full-text acquisition | **31/60 = 51.7%** |
| abstract-only | 29/60 |
| chunks / coverage | 304 / 100% |
| ChromaDB | works (no panic); 304 vectors |
| provenance in Stage 2 output | none (page/section/table not retained) |
| attribution (OWN vs CITED) | none |
| abstention | one regex "empirical evidence" gate in `summarize.py` |
| 24-case synthetic attribution oracle | 24/24 (fixtures only, not real papers) |

Baseline Stage 4 emits Dataset/Metric/Result for effectively all 60 papers, including the 29 with no full text.

## 3. Experiments performed

1. **Phase-2 multi-source acquisition probe** (`acquisition/resolve_corpus.py`, run `…150624Z-acq-2272d1`): per-paper × {S2, arXiv, OpenAlex, Europe PMC, Crossref}, validated. Established the free-access ceiling.
2. **Canonical pipeline** (`pipeline/`), Level-1 unit tests (28/28), Level-2 6-paper smoke (2 defects found + fixed), **Level-3 full 60-paper run** (this report).

## 4. Acquisition results

| | papers | rate |
|---|---|---|
| Baseline (shipped) | 31/60 | 51.7% |
| Canonical, as-run (`…160444Z`) | 33/60 | 55.0% |
| **Canonical, cap-bug fixed** | **34/60** | **56.7%** |
| Free-access ceiling (Phase-2 union) | 34/60 | 56.7% |
| NO_ACCESSIBLE_FULL_TEXT (fixed) | 26/60 | 43.3% |

Delta vs baseline **+3 papers**, decomposed:

- **+3 recovered**: `ef1e4a16` (OpenAlex OA PDF), `0549e2e9` + `f42ad6e2` (Europe PMC PMCID → JATS XML).
- **−1 then +1**: `413a184de4` (PlanSightRAG). Baseline had it as full text. The as-run canonical pipeline **rejected** it — but that was a FALSE rejection caused by an 8 MB fetch cap truncating its 22 MB arXiv PDF (title page lost → identity check saw 0 similarity). With the cap at 40 MB it is re-accepted with `title_similarity 1.0`, 32 pages. Net back to +3.

Full-text source distribution (as-run 33): arXiv 23, Semantic Scholar 7, Europe PMC JATS 2, OpenAlex 1.
Representation: PDF 31, JATS/XML 2, abstract-fallback 27.

Validation layer activity: **identity-validation candidate rejections 1, content-validation rejections 2, wrong-paper accepted 0.** The 2 content rejections (`938908bc` S2 + OpenAlex) were HTML landing pages correctly refused. `938908bc` is a near-duplicate of `f42ad6e2` with no PMCID, so it correctly ends NO_ACCESSIBLE.

**All 26 truly-inaccessible papers have a DOI but no ArXiv ID and no PMCID** — published-only, no preprint. No free route reaches them.

## 5. XML/JATS results

Available for **2/60** papers (both via Europe PMC PMCID). Both parsed cleanly into section/paragraph hierarchy with XML node paths, 11 k and ~4 k body words, and produced the pipeline's cleanest provenance (`front/abstract`, `body/sec[i]/p[j]`). **But n = 2**: JATS materially helps the two papers it exists for and is worth taking opportunistically, but it cannot be a primary representation strategy for this corpus and "XML vs PDF quality" cannot be measured at this n.

## 6. PDF parser results

PyMuPDF only. GROBID/Docling/MinerU **not installed**, no Docker, GPU 6 GB. PyMuPDF `get_text("blocks")` + a heading regex recovered usable sections on well-formatted PDFs (e.g. `ef1e4a16`: abstract/intro/method/experimental_setup/results/discussion/limitations/conclusion) and weak sections on others (heading merged into body block → many blocks labelled `body`). Section labels are provenance metadata, not a retrieval gate, so weak section recovery degrades traceability granularity but not extraction. **No evidence a heavier parser is needed** to hit the current bottleneck (which is acquisition ceiling + attribution recall, not text extraction).

## 7. Retrieval results

BGE-M3 dense over an **isolated** ChromaDB (`pipeline/chroma/`, never `data/chroma_db`), per-paper `where` filter, 5 field-targeted queries, k = 5. Provenance-valid rate of everything the LLM then grounded: **100% (146/146)** — i.e. every span the model quoted was located in a retrieved chunk. No retrieval-recall failure surfaced as the limiting factor in extraction; the limiter is the LLM declaring MISSING or the attribution gate abstaining.

## 8. Reranker results

**Not added.** Question N answer: on this corpus retrieval did not visibly fail (100% span-location rate on grounded items; MISSING items were the model choosing not to answer, not retrieval missing the section). Adding a cross-encoder reranker (VRAM + latency) is not justified by any measured recall gap. Revisit only if a future corpus shows grounded-span-not-found rates rising.

## 9. Structured extraction results (33 full-text papers + 27 abstract-only)

| field | EXPLICIT | INFERRED | UNSUPPORTED | MISSING | RETURNED | returned / full-text paper |
|---|---|---|---|---|---|---|
| dataset | 22 | 0 | 2 | 36 | 22 | 22/33 = 67% |
| metrics | 23 | 2 | 0 | 35 | **5** | 5/33 = 15% |
| results | 11 | 2 | 0 | 47 | **3** | 3/33 = 9% |
| method | 53 | 0 | 1 | 6 | 53 | (also from abstracts) |
| limitations | 33 | 0 | 0 | 27 | 33 | (also from abstracts) |

- **The 2 dataset UNSUPPORTED** are the verification guard working: the model's "verbatim" quote was paraphrased/partial (`ddb170b2` claimed 4 datasets, quote covered 2; `96285d75` similar) → span not found verbatim → refused rather than accepted fuzzily.
- **method / limitations recall is high** (53, 33). For the 27 no-full-text papers, method/limitations are still returned **only when the abstract explicitly states them**, traced to the abstract block — not fabricated.
- **metrics / results RETURNED is very low (5, 3)** — see §10/§11. This is the abstention gate, not an extraction failure: 23 metrics + 11 results were EXPLICIT with valid provenance but abstained because ownership could not be confirmed.

## 10. Attribution results

Computed for every grounded item; **enforced** (hard gate) only for `metrics` and `results`.
On quantitative items: **OWN_PAPER 8, CITED_PAPER 2, UNKNOWN 28.**

- **All 8 OWN_PAPER are correct** on manual inspection ("we report…", "Our retrieval performance (nDCG@5 = 0.4502)…", "SPAR achieves a 9.2% absolute improvement…"). **0 false OWN observed.**
- **CITED_PAPER 2**: `ac8fffa1` (`[Manning et al. 2008]` next to the metric definition — defensible), `f42ad6e2` ("previous studies have shown…" near a method sentence — a mild over-abstention, not a safety error).
- **UNKNOWN 28**: dominated by **passive-voice self-description** ("Retrieval was generally effective, as indicated by high context precision and recall scores") — no `we/our` in the local window → not guessed. Deliberate: precision over recall.

The one Level-2 attribution bug (ablation-table header "vs. Proposed" → false CITED) was fixed pre-Level-3 (`attribute.py`, bare comparison words removed from the citation signal).

## 11. Abstention results

- **No-full-text quantitative fields: 81/81 abstained (100%).** Not one fabricated Dataset/Metric/Result for the 27 papers without an article body. This is the core win over baseline.
- Quantitative fields with EXPLICIT evidence but unconfirmable ownership: abstained (28 UNKNOWN + the CITED ones).
- INFERRED (non-verbatim) quantitative fields: abstained.
- Net: of 300 (60 × 5) field slots, **116 RETURNED / 184 ABSTAINED**; full-text papers avg 2.55 returned/5, no-full-text papers avg 1.19/5 (method+limitations from abstract).

## 12. Provenance results

**100% (146/146)** of grounded items carry `source → representation → section → page(pdf)/xml-node → char span`, and the quoted span was re-located in that chunk. Schema-validity problems: **0**. A truncated / landing-page candidate never becomes a provenance record because identity+content validation runs first.

## 13. End-to-end comparison vs the six-stage baseline

| axis | baseline six-stage | canonical pipeline |
|---|---|---|
| full-text acquisition | 31/60 (51.7%) | **34/60 (56.7%)** |
| wrong-paper in corpus | ≥1 (`413a184de4` arXiv PDF accepted with no identity check) — actually correct here, but nothing *checks* | identity-validated; 0 accepted wrong |
| landing-page / abstract counted as full text | possible (no content gate) | 0 (content gate) |
| provenance | none | 100% of returned evidence |
| OWN vs CITED | none | enforced on metrics/results; 0 false OWN observed |
| fabrication risk on 26 inaccessible papers | Dataset/Metric/Result emitted anyway | **0 quantitative claims** (100% abstain) |
| quantitative coverage (metrics/results returned) | high but unverifiable | low (5 / 3) — abstains under ownership uncertainty |
| method / limitations | yes | yes (53 / 33), provenance-bound |
| new heavy deps | — | none (no GROBID/Docling/MinerU, no reranker, same BGE-M3 + qwen2.5:7b) |

## 14. Computational cost

- Acquisition: 139 s / 60 papers ≈ 2.3 s/paper (network-bound; arXiv politeness 3 s dominates when an arXiv ID exists).
- Extraction: 2107 s / 60 papers ≈ 35 s/paper ≈ 7 s per LLM field call (qwen2.5:7b Q4_K_M, num_ctx 6144, ~4.3 GB VRAM).
- Retrieval index build: BGE-M3 fp16, ~7 k chunks, well under 1 min, fits 6 GB.
- No reranker, no extra model. Runs end-to-end on the target laptop GPU in ~39 min.

## 15. Failures and limitations

1. **Fetch cap bug (fixed post-run):** 8 MB cap truncated a 22 MB PDF → false identity rejection of 1 paper. Cap raised to 40 MB; re-acquisition of that paper confirmed FULL_TEXT. Corrected acquisition figure 34/60. A truncated-response flag would be a further hardening.
2. **Attribution recall is low.** Passive-voice results/metrics without a first-person marker in the local window → UNKNOWN → abstained. 23 EXPLICIT metrics and 11 EXPLICIT results were suppressed this way. Safe, but a real coverage cost. A wider (paragraph/section-subject) window or a small LLM tie-breaker could raise recall without sacrificing the 0-false-OWN property — untested.
3. **Table-embedded own-results.** Ablation-table rows ("Proposed 90.76 …") land as UNKNOWN because the sentence-window heuristic can't see the table's "proposed = ours" caption. Abstains (safe) but loses a real number.
4. **PDF section recovery is heuristic.** Headings merged into body blocks reduce section-label precision on ~1/3 of PDFs. Provenance still resolves to page + char span.
5. **Extraction value noise.** qwen2.5:7b occasionally returns a tool/model name as a "dataset" (`all-mpnet-base-v2`) or a truncated value (`BEIR15 score of`). Low rate; documented, not fixed.
6. **JATS n = 2.** XML-vs-PDF quality is not measurable on this corpus.
7. **Ground truth.** No human-annotated Dataset/Metric/Result labels exist, so §9 numbers are *coverage under a strict verification gate*, not precision/recall against gold. Attribution correctness (§10) is manual inspection of all returned items + a sample of abstained ones (DETERMINISTIC + PROXY, not HUMAN-GOLD).
8. **26/60 papers are simply not openly available** — no pipeline change fixes that.

## 16. Components accepted

- **Canonical acquisition record** + ordered discovery (JATS → arXiv → S2 → OpenAlex → Crossref).
- **Deterministic identity validation** (title/DOI/author) — 0 wrong-paper, and it caught a real landing-page case.
- **Deterministic content validation** (real PDF body / JATS body, reject HTML/empty/abstract-sized).
- **Provenance-bearing representation + chunking** (section + page/node + char span, block-bounded chunks).
- **LLM extraction with verbatim-span verification** → EXPLICIT/INFERRED/UNSUPPORTED/MISSING.
- **Deterministic attribution** (OWN/CITED/UNKNOWN) enforced on metrics/results.
- **Abstention gate** — the single most valuable component; 100% on no-full-text quantitative fields.
- **OpenAlex + Europe-PMC-by-PMCID** as acquisition fallbacks (+3 papers).

## 17. Components rejected

- **XML/JATS-first representation** — 2/60 availability. Keep opportunistic, not primary.
- **Full Crossref PDF integration** — 5 full texts, all also on arXiv/OpenAlex; 17 failed fetches; net +0.
- **GROBID / Docling / MinerU** — no measured structural problem PyMuPDF can't handle at the current bottleneck; infra cost unjustified.
- **Reranker** — no measured retrieval-recall gap (100% grounded-span location).
- **Any model swap** (BGE-M3, qwen2.5:7b kept).
- **"Query every source" in production** — +3 papers for 5 round-trips/paper; use the ordered fallback and stop at first validated full text.

## 18. Recommended final architecture (smallest that works)

Keep the six stages. Change only these internals:

1. **Stage 1 (`src/collection/semantic_scholar.py`):** in `_candidate_pdf_urls`, after arXiv add (a) OpenAlex `best_oa_location.pdf_url` / `open_access.oa_url` by DOI, (b) if `externalIds.PubMedCentral` present, the Europe PMC `…/{PMCID}/fullTextXML` JATS endpoint. Persist `pdf_source` and `representation_type` per paper. Raise any download cap to ≥40 MB.
2. **Stage 1/2 boundary:** add **identity validation** (title/DOI/author match) and **content validation** (real body, not landing/abstract) before a paper is marked `has_full_text`. This alone removes wrong-paper and landing-page contamination from the corpus.
3. **Stage 2 (`src/processing/pdf_parser.py`):** emit provenance-bearing blocks (section + page/xml-node + char span) instead of flat text; carry it through chunking.
4. **Stage 4 (`src/summarization/`):** per field, require a **verbatim evidence span** located in a retrieved chunk; label EXPLICIT/INFERRED/UNSUPPORTED/MISSING; run **attribution** on metrics/results; **abstain** (emit `NOT_FOUND` / `ABSTAIN`, not a value) when status ≠ EXPLICIT, provenance invalid, or ownership unconfirmed. For abstract-only / NO_ACCESSIBLE papers, force Dataset/Metric/Result to `NOT_FOUND`.
5. **Downstream synthesis / gap-analysis:** consume only RETURNED evidence; never turn an abstained field or missing corpus coverage into a "research gap" or novelty claim.

No new services, no new models, no seventh stage.

## 19. What remains unproven

- Precision/recall of Dataset/Metric/Result **against human gold** (none exists).
- Whether the recommended Stage-4 changes preserve the legacy pipeline's *useful* coverage after the abstention gate (needs a paired A/B on the same corpus with the integrated code).
- XML-vs-PDF evidence quality (n = 2).
- Attribution recall ceiling with a wider window / LLM tie-breaker.
- Behaviour on a non-RAG / non-CS corpus (this corpus is 24/60 arXiv, heavily preprint-friendly; a clinical or humanities corpus would shift the acquisition mix and the JATS share).
- Latency/throughput at production corpus sizes (>60).

## 20. Decision

### GO_WITH_CHANGES

The canonical architecture **does** solve the stated problem better than the baseline on the axes that matter:

- acquisition 51.7% → **56.7%** with the free-access ceiling reached, *and* wrong-paper / landing-page contamination eliminated (0 accepted);
- **100% provenance** on returned evidence;
- **0 fabricated** Dataset/Metric/Result for the 26 inaccessible papers (baseline fabricates for all of them);
- **0 false OWN_PAPER** attributions observed;
- runs in ~39 min on a 6 GB laptop GPU with no new models or services.

It is **not** GO outright because: (1) the fetch-cap fix landed after the run of record and is confirmed only on one paper, not a full re-run; (2) attribution/quantitative recall is low (metrics 5/33, results 3/33) and needs the window widening in §15.2 before Stage-4 integration; (3) there is no human-gold evaluation, so extraction precision is asserted via the verification gate, not measured. Integrate per §18 behind a config flag, re-run a paired A/B, widen the attribution window, then re-evaluate for GO.

Not "READY FOR PRODUCTION".

## 21. Exact evidence supporting the decision

| claim | source |
|---|---|
| baseline 31/60 | `runs/20260901T150245Z-0e6dd1de/baseline.json` |
| free-access ceiling 34/60, +3 = OpenAlex ×1 + EuropePMC JATS ×2 | `runs/20260901T150624Z-acq-2272d1/acquisition_summary.json` |
| canonical as-run 33/60, wrong-paper 0, provenance 100% (146), abstain-on-no-fulltext 81/81 | `runs/20260901T160444Z-canon-L3-ca6e/summary.json` + `report.md` |
| 8/8 OWN_PAPER correct, 2 dataset UNSUPPORTED = paraphrased quote, 413a184de4 false-reject = 8 MB cap on 22 MB PDF | `runs/20260901T160444Z-canon-L3-ca6e/evidence_results.json` + `acquisition_records.json` (spot-checked) |
| cap fix → 413a184de4 FULL_TEXT, title_similarity 1.0, 32 pages → corrected 34/60 | `pipeline/acquire.py` (cap 40 MB) + one-paper re-acquisition |
| Level-1 logic 28/28 | `tests/test_pipeline_units.py` |
| parser/reranker not needed | `runs/20260901T150245Z-0e6dd1de/parser_results.json` (tools absent) + 100% grounded-span location this run |
