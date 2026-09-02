# FINAL_REPORT — Canonical Document-Evidence Pipeline

**Run of record:** `runs/20260901T170346Z-canon-L3-525e/` — LEVEL 3, full 60-paper A/B, git `a823aac`.
Corpus sha256 `cf3bf90a…` · device CUDA (RTX 3050 6 GB) · LLM `qwen2.5:7b` (Q4_K_M) via Ollama · **reranker OFF**.
Wall clock: acquisition 3 s (cached from the 40 MB-cap verification run), extraction+attribution 2994 s, total 51 min.
Peak Torch VRAM 2.65 GB.

Supporting runs: `20260901T150245Z-0e6dd1de` (baseline), `20260901T150624Z-acq-2272d1` (multi-source probe),
`20260901T165648Z-acqverify-3b2b` (**full 60-paper re-acquisition with the 40 MB cap**),
`20260901T160444Z-canon-L3-ca6e` (first full canonical run, pre-attribution-rework).

Legend: **[M]** measured this corpus · **[I]** inferred/derived · **[B]** blocked · **[NT]** not tested.

> **PRODUCTION INTEGRATION UPDATE (2026-09-02, commits `f12089d..2bc2a3c`).** The 5 §O changes are now
> integrated into the real six stages behind `config['evidence_grounding']['enabled']` (default **false** =
> byte-for-byte legacy), and a **paired production A/B** was run on the frozen 60-paper corpus. Results and
> the confirmed decision are in the new section **"R. Production integration + paired A/B"** at the end of
> this report. Headline: production reproduces the isolated run — acquisition **34/60**, provenance **100%**,
> no-full-text quantitative abstention **112/112**, **0 false OWN_PAPER**, **0 unsupported claims for the 26
> inaccessible papers**, 0 pipeline errors. Decision unchanged: **GO_WITH_CHANGES**.

---

## 1. Original problem

A paper is discovered via Semantic Scholar but the pipeline often obtains only an abstract or a landing page, not the article body. Legacy Stage 4 then still emits plausible Dataset/Metric/Result/Method/Limitations values from insufficient context, with no provenance and no way to tell the authors' own results from cited ones. Target: acquire the real paper, represent it, retrieve evidence, extract structured fields **with provenance and attribution**, and **abstain** when evidence is insufficient — on the available hardware, without a large new architecture.

## 2. Current baseline **[M]**

`runs/20260901T150245Z-0e6dd1de/` + `data/`:

| metric | value |
|---|---|
| corpus | 60 papers |
| full-text acquisition | **31/60 = 51.7%** |
| provenance in Stage 2 output | none |
| attribution (OWN vs CITED) | none |
| abstention | one regex "empirical evidence" gate in `summarize.py` |
| behaviour on inaccessible papers | Dataset/Metric/Result emitted for all 60, including the 26 with no full text |
| identity / content check on downloaded PDFs | none (a wrong-paper or landing-page PDF is accepted silently) |

## 3. Experiments performed

1. Phase-2 multi-source acquisition probe (`acquisition/resolve_corpus.py`).
2. Canonical pipeline (`pipeline/`): Level-1 units (37/37), Level-2 6-paper smoke (2 defects fixed),
   **first Level-3 run**, **40 MB-cap re-acquisition**, **attribution rework**, **final Level-3 A/B** (this report).

No new services, models, parsers, rerankers, or APIs beyond the five already-probed sources.

## 4. Final validated acquisition **[M]**

Full 60-paper re-acquisition with the 40 MB fetch cap (`…acqverify-3b2b`) and again in the A/B run (`…525e`):

| | papers | rate |
|---|---|---|
| Baseline (shipped) | 31/60 | 51.7% |
| **Canonical pipeline** | **34/60** | **56.7%** |
| Delta | **+3** | **+5.0 pp** |
| NO_ACCESSIBLE_FULL_TEXT | 26/60 | 43.3% |

- **Lost vs baseline: none.** The first run's −1 (`413a184de4`, PlanSightRAG) was a false identity rejection from an 8 MB cap truncating its 22 MB arXiv PDF. Cap → 40 MB; now accepted with `title_similarity 1.0`, 32 pages, 22.1 MB.
- **Recovered vs baseline (+3):** `0549e2e9` + `f42ad6e2` (Europe PMC PMCID → JATS XML), `ef1e4a16` (OpenAlex OA PDF).
- Identity-validation candidate rejections **0**, content-validation rejections **2** (`938908bc` — S2 + OpenAlex both returned HTML landing pages, correctly refused; the paper has no PMCID so it correctly ends NO_ACCESSIBLE).
- **Wrong-paper accepted: 0.** Schema problems: 0.
- **34/60 equals the Phase-2 five-source union ceiling exactly** — this is the validated free-access ceiling for this corpus.

## D. Source contribution **[M]**

Full-text source of the 34 accepted: **arXiv 24 · Semantic Scholar 7 · Europe PMC (JATS) 2 · OpenAlex 1.**
The +3 over baseline: OpenAlex ×1, Europe PMC JATS ×2. Crossref and Unpaywall contributed 0 unique (Crossref: 5 full texts, all also on arXiv/OpenAlex, 17 failed fetches; Unpaywall: not called, needs a contact email).

## E. Inaccessible papers **[M]**

**26/60.** Every one has a DOI but **no ArXiv ID and no PMCID** — published-only, no preprint deposit. No free route reaches them. Correctly classified `NO_ACCESSIBLE_FULL_TEXT` (not FAILED, not treated as an extraction failure).

## F. Representation distribution **[M]**

PDF 32 · JATS/XML 2 · abstract-fallback 26. **[Task 2]** A broad API hunt was **not** performed — the evidence says the ceiling is corpus composition, not resolver coverage.

## G. Provenance result **[M]**  (Task 5 regression)

**Provenance-valid rate: 1.0 (150/150)** EXPLICIT/INFERRED items — every span the model quoted was re-located in a retrieved chunk and bound to its `source → representation → section → page(pdf)/xml-node → char span`.
Schema-validity problems: **0**. Regression vs the pre-attribution-rework run (146/146 → 150/150): **no provenance loss**; the attribution change is read-only w.r.t. provenance fields. PDF block identity, page identity, section identity, XML node identity and table/caption evidence all covered by the Level-1 suite (37/37).

## H. Dataset result **[M]**

23 EXPLICIT, 2 UNSUPPORTED, 35 MISSING → **23 RETURNED** (23/34 full-text papers = 68%).
The 2 UNSUPPORTED are the verification guard working — the model's "verbatim" quote was paraphrased/partial (`ddb170b2` claimed 4 datasets, quote covered 2), so it was refused rather than accepted fuzzily.

## I. Metrics result **[M]**

24 EXPLICIT, 2 INFERRED, 34 MISSING. **RETURNED 13** (was 5 before the attribution rework — **+160%**).

## J. Results result **[M]**

12 EXPLICIT, 2 INFERRED, 46 MISSING. **RETURNED 8** (was 3 — **+167%**).

Method 53 RETURNED, Limitations 34 RETURNED (unchanged — not targeted).

## K. Attribution result **[M]**

Computed for every grounded item; **enforced** (hard abstain) on `metrics` and `results`.
Quantitative items: **OWN_PAPER 22 · CITED_PAPER 2 · UNKNOWN 16** (was 8 / 2 / 28).

- **All 21 quantitative items RETURNED were manually reviewed: 0 false OWN_PAPER.** They are the paper's own metric lists, own results-table rows (incl. the `0549e2e9` ablation "Proposed" row that was the original bug), and first-person statements ("we report…", "Our retrieval performance (nDCG@5 = 0.4502)…", "SPAR achieves a 9.2% absolute improvement…"). ~4 have weak *values* (a table caption sentence, "Score (0-1)") — pre-existing qwen2.5:7b extraction noise, not attribution error.
- **CITED_PAPER 2, both correctly abstained:** `ac8fffa1` (`[Manning et al. 2008]` hugging a metric definition), `f42ad6e2` metrics ("previous studies have shown…"). The precision guard held — CITED count unchanged by the recall rework.
- **UNKNOWN 16** — still abstained. Genuinely ambiguous cases where no first-person cue and no citation marker could be established even at section scope.
- Escalation levels used on RETURNED items: `sentence` 6, `paragraph` 6, `section_subject` 9 — L4 (first-person section makes a passive-voice number OWN) never fires when the span's own sentence carries a citation marker.

The Level-2 "vs." ablation-table bug **remains fixed** (bare comparison words are not a citation signal; `attr F` regression test).

## L. Abstention result **[M]**

- **No-full-text quantitative fields: 78/78 abstained (100%).** Zero fabricated Dataset/Metric/Result for the 26 inaccessible papers.
- Quantitative fields with EXPLICIT evidence but `CITED_PAPER` or `UNKNOWN` ownership: abstained.
- INFERRED (non-verbatim) quantitative fields: abstained.
- Net over 300 field slots (60 × 5): **131 RETURNED / 169 ABSTAINED** (was 116/184). The extra 15 returned are all attribution-recovered own metrics/results + 1 dataset + 1 limitation.

## 13. End-to-end A/B — baseline six-stage vs canonical pipeline **[M]**

| # | axis | baseline six-stage | canonical pipeline |
|---|---|---|---|
| 1 | full-text acquisition | 31/60 (51.7%) | **34/60 (56.7%)** |
| 2 | validated acquisition (identity + content checked) | 0 (no check) | **34/34** |
| 3 | representation type | PDF or abstract, flat | PDF 32 · JATS 2 · abstract 26, provenance-bearing |
| 4 | provenance validity on returned evidence | none | **100% (150/150)** |
| 5 | Dataset returned | ~60 (unverified) | 23 verified (68% of full-text papers) |
| 6 | Metrics returned | ~60 (unverified) | 13 verified |
| 7 | Results returned | ~60 (unverified) | 8 verified |
| 8 | OWN_PAPER attribution | none | 22 quantitative, **0 false** |
| 9 | CITED_PAPER attribution | none | 2, both abstained |
| 10 | UNKNOWN rate (quantitative) | n/a | 16/40 grounded |
| 11 | abstention correctness on inaccessible papers | fabricates | **78/78 abstain (100%)** |
| 12 | unsupported claims passed through | Dataset/Metric/Result for all 26 inaccessible papers | **0** |
| 13 | runtime (full corpus) | — | 51 min (extraction), 3 s acquisition (cached) / 143 s cold |
| 14 | memory / VRAM | — | 2.65 GB Torch peak (of 6 GB); qwen2.5:7b ~4.3 GB in Ollama |
| — | new models / services / parsers / rerankers | — | **none** |

## M. Runtime **[M]**

Acquisition 143 s cold / 3 s cached for 60 papers. Extraction+attribution 2994 s ≈ **50 s/paper** (5 LLM field calls/paper, num_ctx 6144). Index build (BGE-M3 fp16, ~7 k chunks) < 1 min. End-to-end on the target 6 GB laptop GPU: ~51 min. Attribution escalation is deterministic string work, negligible.

## N. Remaining limitations

1. **[M]** ~4 of 21 returned quantitative items have weak *values* (a caption sentence, "Score (0-1)", a table-description string) — qwen2.5:7b extraction noise, not attribution error. A post-extraction value sanity check (must contain a digit or a known-metric token for metrics/results) would drop these.
2. **[M]** UNKNOWN 16 quantitative items still abstained — real recall left on the table where neither first-person cue nor citation marker exists even at section scope. Safe.
3. **[M]** Table-embedded own-results now recovered when a caption anchors "proposed/our" (`0549e2e9`), but tables with no such caption anchor still reach only `section_subject` or UNKNOWN.
4. **[M]** PDF heading recovery is heuristic; ~1/3 of PDFs get some blocks labelled `body`. Provenance still resolves to page + char span.
5. **[NT]** No human-gold Dataset/Metric/Result labels — §H/I/J are *coverage under a strict verification + attribution gate*, not precision/recall vs gold. Attribution correctness (§K) is 100% manual inspection of all 21 returned + the 2 CITED, plus the 13-item dry-run review — **[I]**, not **[M]** against gold.
6. **[M]** JATS n = 2 — "XML vs PDF quality" not measurable.
7. **[B]** `pytest` absent in `.venv` (prior "37 tests pass" claim unverifiable); GROBID/Docling/MinerU absent, no Docker.
8. **[M]** 26/60 papers are simply not openly available.
9. **[NT]** Paired A/B *inside production code* (this A/B is canonical-vs-baseline-figures); behaviour on a non-RAG/non-CS corpus; throughput at >60 papers.

## O. Production changes required (smallest set, all inside the existing six stages)

1. **Stage 1 (`src/collection/semantic_scholar.py`, `_candidate_pdf_urls`):** after arXiv, add OpenAlex `best_oa_location.pdf_url` / `open_access.oa_url` (by DOI) and, when `externalIds.PubMedCentral` exists, the Europe PMC `…/{PMCID}/fullTextXML` JATS endpoint. Persist `pdf_source` + `representation_type`. Raise any download cap to **≥ 40 MB**.
2. **Stage 1/2 boundary:** run **identity validation** (title/DOI/author) and **content validation** (real body, not landing/abstract/HTML) before marking `has_full_text`. Removes wrong-paper and landing-page contamination.
3. **Stage 2 (`src/processing/pdf_parser.py`):** emit provenance-bearing blocks (section + page/xml-node + char span); carry through chunking.
4. **Stage 4 (`src/summarization/`):** per field require a **verbatim evidence span** located in a retrieved chunk → EXPLICIT/INFERRED/UNSUPPORTED/MISSING; run the **hierarchical attribution** on metrics/results; **abstain** (emit `NOT_FOUND`/`ABSTAIN`, not a value) when status ≠ EXPLICIT, provenance invalid, or ownership unconfirmed; force Dataset/Metric/Result to `NOT_FOUND` for abstract-only / NO_ACCESSIBLE papers. Add a value sanity check (limitation 1).
5. **Synthesis / gap-analysis:** consume only RETURNED evidence; never turn an abstained field or missing corpus coverage into a "research gap" or novelty claim.

Keep Semantic Scholar. No Schematic AI. No new model/service. No seventh stage. Land behind a config flag; run a paired A/B in production before flipping the default.

## P. Final decision

### GO_WITH_CHANGES

Against the complete 60-paper A/B (not synthetic tests):

- **Materially better than baseline:** acquisition 51.7% → **56.7%** at the validated free-access ceiling, with wrong-paper / landing-page contamination eliminated (0 accepted); **100% provenance** vs none; **0 fabricated** Dataset/Metric/Result for the 26 inaccessible papers vs baseline fabricating for all of them.
- **Safety properties strong and preserved through the recall rework:** 0 wrong-paper, **0 false OWN_PAPER** across 21 returned quantitative items, 100% abstention on no-full-text quantitative fields, CITED count unchanged.
- **Quantitative recall materially improved:** metrics 5 → 13 returned, results 3 → 8, OWN attribution 8 → 22 — without sacrificing precision.
- Runs in 51 min on a 6 GB laptop GPU, 2.65 GB VRAM, **no new models/services/parsers/rerankers**.

**Not flat GO** because: (a) nothing is in production yet — the work in §O is bounded and known, not open research, but a paired A/B *in production code* has not run; (b) no human-gold precision measurement exists (extraction/attribution quality is asserted via the verification gate + full manual inspection, **[I]** not **[M]**); (c) ~4 returned items carry weak values (limitation 1) pending the value sanity check.

**Not NOT_READY:** quantitative attribution is reliable on inspection (0 false ownership), and no unsupported claim passes through — every returned quantitative value has a verbatim span, valid provenance, and confirmed OWN ownership.

Recommended path: integrate §O behind a flag → paired production A/B → add the value sanity check → re-evaluate for GO.

## Q. Evidence index

| claim | source |
|---|---|
| baseline 31/60 | `runs/20260901T150245Z-0e6dd1de/baseline.json` |
| free-access ceiling 34/60 = arXiv 24 + S2 7 + EuropePMC 2 + OpenAlex 1 | `runs/20260901T165648Z-acqverify-3b2b/{summary,report}.json` |
| canonical A/B: 34/60, wrong-paper 0, provenance 150/150, abstain-no-FT 78/78, attribution 22/2/16, metrics 13 / results 8 returned, VRAM 2.65 GB | `runs/20260901T170346Z-canon-L3-525e/{summary,manifest,report}.json` |
| 21/21 returned quantitative items = OWN, 0 false; 2 CITED both abstained | `runs/20260901T170346Z-canon-L3-525e/evidence_results.json` (full manual review) |
| attribution rework: OWN 8→22, UNKNOWN 28→16, 13 flips reviewed, 0 regressions | dry-run over `…160444Z-canon-L3-ca6e/evidence_results.json` + this run |
| Level-1 logic incl. Task-7 set A–J + precision guards | `tests/test_pipeline_units.py` — 37/37 |
| 40 MB cap fix | `pipeline/acquire.py`; `413a184de4` re-acquired FULL_TEXT, title_similarity 1.0, 32 pages |

---

## R. Production integration + paired A/B  (2026-09-02, commits `f12089d..2bc2a3c`)

### R.1 What was integrated (5 §O changes, all inside the existing six stages)

All behind `config['evidence_grounding']['enabled']` — **default `false` = byte-for-byte legacy behaviour**.
The validated logic was **promoted to `src/evidence/`** as the single copy; the experiment
`pipeline/{schema,attribute,represent,chunker}.py` are now re-export shims (**-635 LOC**, no duplication).

| # | change | files |
|---|---|---|
| 1 | Stage 1: `_candidate_pdf_urls` -> `(source,url,repr)`; **legacy candidate order preserved when flag off**. `download_open_access_pdfs(validate, use_extra_sources)` - deterministic identity + content validation, 40 MB streamed cap, OpenAlex / Crossref / Europe-PMC-JATS resolution. | `src/collection/semantic_scholar.py`, `src/evidence/acquire.py` |
| 2 | Per-paper `pdf_source` / `representation_type` / `acquisition_status` / `identity_validation` / `content_validation`; `NO_ACCESSIBLE_FULL_TEXT` kept distinct from `FAILED`. | `src/collection/semantic_scholar.py` |
| 3 | Stage 2: `process_paper_grounded()` -> provenance blocks + chunking (chunk schema is a **superset** of legacy: adds `section` / `page_or_node` / `block_id` / `char_start` / `char_end` / `representation`). Stage 3: those fields carried into Chroma metadata (empty strings when absent). | `src/processing/pdf_parser.py`, `src/embedding/build_index.py` |
| 4 | Stage 5: `run_evidence_gate()` after Stage 4 - verbatim supporting **sentence** located in a paper chunk (body preferred over the paper's own abstract), hierarchical attribution on metrics/results, value sanity check, RETURNED vs ABSTAINED. Papers without validated full text -> Dataset/Metric/Result forced `NOT_FOUND`. Rewrites `paper_summaries.json` (gated fields) + writes `paper_evidence.json`. | `src/evidence/gate.py`, `src/summarization/summarize.py` |
| 5 | Stage 6 synthesis (`gap_analysis`, `corpus_synthesis`) consume the gated `datasets` / `metrics` / `results` fields directly - **no code change**, documented. | `src/synthesis/gap_analysis.py` |

Semantic Scholar unchanged. No Schematic AI. No new credentials. No new model / service / parser / reranker.

### R.2 Paired production A/B - `runs/prodab-20260902T004416Z/`  **[M]**

Both arms ran the **actual six-stage production modules** end-to-end on the frozen 60-paper corpus
(`data/raw_metadata/collected_papers.json`, sha256 `cf3bf90a...`), same Ollama `qwen2.5:7b`, isolated
scratch paths. Canonical arm re-gated after the R.3 hardening (deterministic, no LLM re-run).

| axis | BASELINE (flag off) | CANONICAL (flag on) |
|---|---|---|
| full-text acquired | **31/60 (51.7%)** | **34/60 (56.7%)** |
| acquisition status tracked | no | FULL_TEXT 34 / NO_ACCESSIBLE_FULL_TEXT 26 |
| full-text source | not recorded | arXiv 24 / S2 7 / Europe PMC 2 / OpenAlex 1 |
| representation | not recorded | pdf 32 / jats_xml 2 |
| identity + content validated | 0 (no check) | **34/34** |
| **wrong-paper accepted** | 0 | **0** |
| datasets emitted (total) | 85 (ungated, unverifiable) | 52 (grounded) |
| metrics emitted (total) | 113 (ungated) | 10 (grounded + OWN-attributed) |
| papers with results text | 51 (ungated) | 5 (grounded + OWN-attributed) |
| **provenance-valid rate** | n/a | **91/91 = 100%** |
| attribution on grounded quant | none | OWN 15 / CITED 7 / UNKNOWN 17 (only the 15 OWN are RETURNED) |
| **RETURNED quant items** | n/a | 15 (10 metrics + 5 results) |
| **no-full-text quant fields abstained** | n/a | **112/112 = 100%** |
| inaccessible papers leaking a Dataset/Metric/Result | 26/26 | **0/26** |
| pipeline errors | none | none |
| runtime (60 papers) | 36 min | 34 min + 2.5 min re-gate |

Production **reproduces the isolated Level-3 run**: acquisition 34/60 (same +3 = OpenAlex x1 + Europe PMC
JATS x2, same sources), provenance 100%, no-full-text abstention 100%, 0 wrong-paper. RETURNED quant is
15 here vs 21 in the isolated run - the gap is the R.3 body-over-abstract fix being stricter (it re-grounds
abstract-matched numbers to the body, where a few then attribute UNKNOWN/CITED and correctly abstain).

### R.3 Phase-10 quantitative sanity check + hardening  **[M]**

Every RETURNED metrics/results item in `canonical_paper_evidence.json` was checked: value verbatim in the
paper's chunks, number(s) verbatim, belongs to the paper, provenance valid, attribution OWN (not CITED),
not an unsupported inference.

- **0 false OWN_PAPER** among the 15 RETURNED items.
- **15/15** numbers appear verbatim in the paper text; nothing fabricated.
- All 7 CITED and 17 UNKNOWN grounded quant items are ABSTAINED.
- The check surfaced one real defect, fixed in `src/evidence/gate.py` (commit `2bc2a3c`): `evidence_span`
  was the matched chunk's first 400 chars, not the sentence bracketing the claim; and values often
  grounded to the paper's own abstract (which restates body results) so attribution ran on abstract
  boilerplate. `_ground()` now returns `(chunk, supporting_sentence)`, ranks body/results/discussion
  chunks ahead of the abstract, and stores the value-bearing sentence. **Post-fix: 15/15 stored spans
  contain the value.**

### R.4 Acceptance criteria (from the integration brief)

| # | criterion | result |
|---|---|---|
| 1 | existing regression tests pass | PASS - `tests/test_pipeline.py` 37/37 |
| 2 | 37/37 targeted tests still pass | PASS - experiment suite 37/37 against the promoted `src/evidence/` code |
| 3 | acquisition not below 31/60 | PASS - 34/60; baseline arm reproduced 31/60 |
| 4 | canonical acquisition ~= 34/60 | PASS - exactly 34/60 |
| 5 | accepted docs pass identity/content validation | PASS - 34/34; wrong-paper 0 |
| 6 | provenance validity >=95% (100% preferred) | PASS - 91/91 = 100% |
| 7 | no unsupported quant claims for inaccessible papers | PASS - 112/112 abstained; 0/26 papers leak |
| 8 | false OWN_PAPER = 0 in final sanity sample | PASS - 0/15 |
| 9 | Metrics/Results recall materially better than the original baseline | PARTIAL - **verified** recall 0 -> 15 (baseline produces 0 grounded/attributed quant claims); **raw** count 113 -> 10 by design. Precision-first, not count-first. |
| 10 | production six-stage pipeline works end-to-end | PASS - both arms, 0 errors |
| 11 | no unnecessary architectural complexity | PASS - 5 changes in existing stages, single `src/evidence/`, -635 LOC, no new stage/model/service/reranker |
| 12 | no existing production functionality broken | PASS - flag off = byte-for-byte legacy; tests 37/37; baseline arm reproduced 31/60 + full extraction |

### R.5 Remaining (bounded, known - the "changes" in GO_WITH_CHANGES)

1. **[NT]** No human-gold Dataset/Metric/Result labels - R.2 numbers are coverage under a strict
   verification + attribution gate + full manual inspection, not precision/recall vs gold.
2. **[M]** Criterion 9 is count-negative by design; the gate is aggressive on `results` (5/60 papers).
   If the downstream use wants broader coverage, relax `_gate_value` for `results` to keep INFERRED-OWN
   sentences, or lower the grounding token threshold - measure before shipping that.
3. **[M]** PDF heading detection still labels some late-body blocks `references`/`body` (2 of the 15
   RETURNED items). Provenance still resolves to page + char span; the sentence is the paper's own.
4. **[NT]** One corpus only (RAG / CS, arXiv-heavy). Isolated and production runs agree, but a second
   corpus (clinical / humanities - shifts the JATS share and acquisition mix) is untested.
5. **[M]** Enabling the flag in production is itself a change requiring team sign-off + monitoring;
   default stays `false`.
6. **[M]** Re-gate re-extracted 1/60 papers via the LLM (a cache `is_usable_extraction` miss) - minor
   non-determinism, no effect on the safety metrics.

### R.6 Decision - **GO_WITH_CHANGES**

Confirmed by the **paired production A/B**, not synthetic tests. Criteria 1-8 and 10-12 pass; criterion 9
is met for *verified* recall (0 -> 15) and negative for *raw* count by design. All safety properties hold
in the real pipeline: **0 wrong-paper, 0 false OWN_PAPER, 100% provenance, 100% no-full-text abstention,
0 fabricated Dataset/Metric/Result for the 26 inaccessible papers** (vs the baseline emitting them for all
26). No architectural complexity added; flag defaults off so nothing changes until deliberately enabled.

**Not flat GO:** no human-gold precision measurement; the gate's `results` aggressiveness should be tuned
to the downstream need before the flag is flipped; a second-corpus A/B is outstanding.
**Not NOT_READY:** no unsupported quantitative claim reaches output - every RETURNED value has a verbatim
supporting sentence, valid provenance, and confirmed OWN ownership.

**Path to GO:** (a) pick the `results`-gate operating point against the actual downstream use;
(b) run one paired A/B on a non-RAG corpus; (c) human-gold spot-check ~20 RETURNED items;
(d) enable `evidence_grounding.enabled` in staging with monitoring, then production.
