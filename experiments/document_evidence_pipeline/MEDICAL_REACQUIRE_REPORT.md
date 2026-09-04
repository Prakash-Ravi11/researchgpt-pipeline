# Stage 1 — canonical five-source resolver integrated + medical corpus re-acquired

Branch `claude-code-verification` · 2026-09-04
Inside Stage 1 only. Six stages unchanged. `configs/config.yaml` not modified.
Phase 4's `latex_ingestion_enabled` stays `false`. Seeded path. Acquisition only —
no extraction re-run.

## Integration

The validated §O resolver (Semantic Scholar + arXiv + OpenAlex + Europe PMC +
Crossref) already lived in `download_open_access_pdfs(validate=True,
use_extra_sources=True)` but was reachable only via a **fresh search**
(`run_collection`) with `evidence_grounding.enabled`. A corpus collected before
§O — like the medical corpus — could never be upgraded without re-searching.

**Added `src/collection/semantic_scholar.py::re_acquire_corpus(config)`** — a
Stage 1 entry that re-runs the same validated path against an **existing**
`collected_papers.json` (no new search). It preserves every frozen-60 guarantee,
because it calls the same functions:

- four acquisition states (`FULL_TEXT` / `NO_ACCESSIBLE_FULL_TEXT` / `METADATA_ONLY` / …)
- identity validation (title / DOI / author) and content validation (real body,
  not a landing/error/abstract page) — both required before `has_full_text`
- provenance (`pdf_source` / `representation_type` / `acquisition_status` /
  `identity_validation` / `content_validation` / `acquisition_candidates`)
- structured-preferred ordering: **JATS/XML > validated PDF > abstract**
- `NO_ACCESSIBLE_FULL_TEXT` abstention

Wired into `run_pipeline.py` behind `collection.reacquire_existing` (default
absent → normal fresh-search Stage 1) and exposed as
`python -m src.collection.semantic_scholar --reacquire`.

## MEASURE — 50-paper medical corpus, re-acquired (isolated `runs/medical_reacquire/`)

Identifiers present: **17 PubMedCentral · 8 arXiv · 47 DOI** (of 50).
Before: 19/50 full text, all `pdf` representation, **0 JATS**.

| | before | after |
|---|--:|--:|
| full-text coverage | 19/50 (38 %) | **23/50 (46 %)** |
| `acquisition_status` | — | 23 FULL_TEXT / 27 NO_ACCESSIBLE_FULL_TEXT |

### Representation distribution (full-text only)

| | count |
|---|--:|
| **JATS (`jats_xml`)** | **11** |
| PDF (`pdf`) | 12 |
| abstract-only | 27 |

### Per-source contribution (accepted full text)

| source | accepted |
|---|--:|
| **europepmc** (JATS) | **11** |
| arxiv (PDF) | 8 |
| semantic_scholar (PDF) | 4 |
| openalex | 0 |
| crossref | 0 |
| unpaywall | 0 (no contact email configured) |

Europe PMC is the entire structured gain. OpenAlex and Crossref contributed 0
accepted here — every OpenAlex link that resolved returned an
`html_or_error_page` (publisher landing / paywall), consistent with the frozen-60
finding that Crossref added 0 unique.

### Identity validation

- **Wrong-paper accepted: 0.** Every one of the 23 accepted papers has
  `identity_validation.passed == True`.
- `title_similarity` of accepted papers: **min 0.94 / median 1.00 / max 1.00**.

### Content rejections — 18 candidate fetches rejected

| reason | count |
|---|--:|
| `html_or_error_page` | 15 (S2 + OpenAlex links → publisher landing/paywall HTML) |
| `thin_text_2384chars_1pages` | 3 (paper `d1f8a7f02d` — every PDF candidate was a 1-page abstract stub; correctly stays `NO_ACCESSIBLE_FULL_TEXT`) |

## THE NUMBER THAT MATTERS

**Medical papers now with JATS: 11.**

Phase 5's structural cell binding can be validated on **11 biomedical JATS
papers** — up from **2** in the canonical corpus, and in the exact domain
(biomedical) that Europe PMC serves. With LaTeX ingestion off for measured
reasons (Phase 5x), Europe PMC JATS on the medical corpus is now the only
non-trivial structured set the binding contract can be exercised against.

The 11 (all `identity title_similarity 1.00`):

| paper | PMCID | title (abbrev.) |
|---|---|---|
| `3aeeb4d31b0d` | PMC11575827 | Trajectories of human brain functional connectome maturation… |
| `33fea4124ef0` | PMC11522281 | Exploring fetal brain tumor glioblastoma symptom verification… |
| `913b6b3cb4c4` | PMC12611563 | Biallelic variants in the UTRN gene cause a novel form of… |
| `819f9eacf36c` | PMC8064052 | Second-Trimester Placental and Thyroid Hormones… |
| `7cc53dfe80d5` | PMC10722247 | Large vestibular schwannomas presenting in late pregnancy |
| `506958c71c4b` | PMC8204808 | Exposure to Perfluoroalkyl Substances During Pregnancy… |
| `dd7cacac10d3` | PMC8882309 | Congenital Dislocation of the Knee: Idiopathic or Arthrogryposis? |
| `ec45017959a4` | PMC12668676 | Joint profiling of cell morphology and gene expression… |
| `20f7c8717108` | PMC7686807 | Paradoxical Effects of a Cytokine and an Anticonvulsant… |
| `eef59dba1650` | PMC10431487 | Mixtures of Metals and Micronutrients in Early Pregnancy… |
| `4e8aa13b4455` | PMC10444676 | Interaction of the pre- and postnatal environment… |

(6 of the 17 PMCID papers did not yield JATS — no OA full text in Europe PMC, or
the JATS failed content validation; those stay PDF or abstract-only.)

## Tests

- `tests/test_pipeline.py` + `tests/test_anchors.py`: **15/15**.
- experiment suite `tests/test_pipeline_units.py`: **46/46**.
- Staging invariants unaffected — `staging_run.py` calls `download_open_access_pdfs`
  directly, not `re_acquire_corpus`; no gate/selector/Stage-2 change.

## Not in this commit

- The isolated re-acquisition wrote `runs/medical_reacquire/` only.
  `data/raw_metadata/` and `data/pdfs/` (the live medical corpus) are untouched —
  promoting the re-acquired corpus (and the PDF→JATS representation switch for 7
  papers that already had full text) is a separate step.
- No extraction re-run.
