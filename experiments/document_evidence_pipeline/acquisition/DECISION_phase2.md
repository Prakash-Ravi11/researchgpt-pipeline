# Phase 2 / Phase 3 decision — acquisition & document representation

Run: `experiments/document_evidence_pipeline/runs/20260901T150624Z-acq-2272d1/`
Corpus: live `data/raw_metadata/collected_papers.json`, 60 papers, sha256 `cf3bf90addf1…`
Method: `acquisition/resolve_corpus.py` — per-paper resolution across 5 external sources, each artifact
validated as real full text with PyMuPDF (`>=2000` chars, `>=2` non-empty pages) or JATS XML (`>=4000` chars,
`<article>`+`<body>`). No credentials, polite `mailto` only.

## Measured

| | papers | rate |
|---|---|---|
| Baseline — shipped pipeline (S2→arXiv→Unpaywall) full text | 31/60 | 51.7% |
| Any-source ceiling (S2 ∪ arXiv ∪ OpenAlex ∪ EuropePMC ∪ Crossref) | 34/60 | 56.7% |
| **Delta** | **+3** | **+5.0pp** |
| Unrecoverable from every free source | 26/60 | 43.3% |
| JATS/XML full text available | 2/60 | 3.3% |

Newly recoverable: `ef1e4a16…` (OpenAlex OA PDF), `0549e2e9…` and `f42ad6e2…` (Europe PMC PMCID → JATS XML).

Per-source independent full-text yield: arXiv 24, OpenAlex 17, S2 `openAccessPdf` 8, Crossref 5, Europe PMC 2.
Per-source failed fetches (dead link / HTML landing / 403): S2 6, OpenAlex 13, Crossref 17.
Median metadata+fetch latency: OpenAlex ~1.4s, Crossref ~1.5s, arXiv ~1.5s, Europe PMC ~1.7s, S2 link ~2.3s.

All 26 unrecoverable papers have a DOI but **no** ArXiv ID and **no** PMCID — published-only, closed access,
no preprint deposit. No free-source resolver reaches them.

## Decision

**MODIFY — smallest slice.** The multi-source hypothesis is only marginally supported on this corpus.

ACCEPT (cheap, low-risk, ~30 LOC in `src/collection/semantic_scholar.py::_candidate_pdf_urls`):
- Add OpenAlex `best_oa_location.pdf_url` / `open_access.oa_url` as a fallback link after arXiv.
- Add Europe PMC: if `externalIds.PubMedCentral` present, try `…/{PMCID}/fullTextXML` (JATS) before giving up.
- Persist `pdf_source` per paper in `collected_papers.json` so recovery rate is logged, not reconstructed.

REJECT for this corpus:
- **XML/JATS-first document strategy (Phase 3)** — 2/60 availability. Cannot evaluate "XML vs PDF quality"
  at n=2, and it cannot be the primary representation when 58/60 papers have no XML. Keep PDF/PyMuPDF primary;
  use JATS opportunistically only when a PMCID exists.
- **Full Crossref integration** — 5 independent full texts, all also reachable via arXiv/OpenAlex; 17 failed
  fetches. Net new recovery ≈ 0. Not worth the dependency.
- **Aggressive "query every source" resolver** — +3 papers does not justify 5 network round-trips per paper
  (~11s/paper here) in the production path.

## What this does NOT resolve

The real ceiling is corpus composition: 43% of these papers are closed access with no preprint. Acquisition
improvements top out near 57%. The higher-leverage work is making the **abstract-only path safe** — i.e. Stage 4
must mark Dataset/Metric/Result as `NOT_FOUND`/`ABSTAIN` for the 26 (soon 43%→ ~43%) papers where full text is
genuinely unavailable, instead of emitting plausible values. That is Phases 7–10 and is still unproven.

## Rejected-alternative log

| Alternative | Measured benefit | Cost | Verdict |
|---|---|---|---|
| OpenAlex fallback link | +1 unique paper | 1 API call/paper, no dep | ACCEPT |
| Europe PMC by PMCID (JATS) | +2 unique papers | 1–2 calls when PMCID exists (2/60) | ACCEPT (guarded) |
| Crossref PDF links | +0 unique | 1 API call/paper, 27% fail | REJECT |
| Unpaywall | not tested (needs real contact email) | dep + email config | DEFER |
| XML/JATS-first representation | n=2 | large rewrite of Stage 2 | REJECT (corpus) |
| Query-all-sources resolver in prod | +3 total | ~11s/paper, 5 deps | REJECT |
