# document_evidence_pipeline — isolated investigation

Read-only against production data; every run writes only to `runs/<run_id>/` (gitignored).
No production module is imported for measurement; no `data/` path is mutated; no credentials are used.

## Read this first

**`FINAL_REPORT.md`** — the decision (GO_WITH_CHANGES), full metrics, accepted/rejected components,
and the exact 5 production changes recommended (§18). Answers questions A–Q.
**`progress.md`** — chronological log with per-phase evidence.
**`acquisition/DECISION_phase2.md`** — the narrower Phase-2 acquisition decision.

## Authoritative runs

| What | Run dir | When |
|---|---|---|
| P0 baseline (read-only) | `runs/20260901T150245Z-0e6dd1de/` | 15:02Z |
| P1 multi-source acquisition probe | `runs/20260901T150624Z-acq-2272d1/` | 15:06Z |
| Canonical pipeline, first full run | `runs/20260901T160444Z-canon-L3-ca6e/` | 16:04Z |
| 40 MB-cap re-acquisition (60 papers) | `runs/20260901T165648Z-acqverify-3b2b/` | 16:56Z |
| **Canonical pipeline, final 60-paper A/B (run of record)** | `runs/20260901T170346Z-canon-L3-525e/` | 17:03Z |

(`runs/` is gitignored — regenerate with the harnesses below. Headline numbers are frozen here and in `FINAL_REPORT.md`.)

## Harnesses

- `benchmark.py --run` — read-only P0 baseline + source/parser/chroma feasibility probes.
- `acquisition/resolve_corpus.py --run [--limit N] [--skip SRC]` — P1 per-paper multi-source resolver.
- `pipeline/` — the canonical pipeline (schema → acquire → represent → chunker → index → extract → attribute → decide → run).
- `python -m tests.test_pipeline_units` — Level-1 deterministic logic tests (28/28).
- `python benchmark_canonical.py --level2` — 6-paper representative smoke.
- `python benchmark_canonical.py --level3` — full 60-paper run (the final benchmark).
- `runner.py` — deterministic 24-case synthetic attribution/abstention oracle. `real_benchmark.py`,
  `baseline_inventory.py` — earlier-session harnesses; `runs/*-real-*` results are STALE (old corpus).

## Headline numbers (2026-09-01)

| | baseline six-stage | canonical pipeline |
|---|---|---|
| full-text acquisition | 31/60 (51.7%) | **34/60 (56.7%)** (full re-acquisition, 40 MB cap) |
| wrong-paper accepted | not checked | **0** |
| landing-page/abstract as full text | possible | **0** |
| provenance on returned evidence | none | **100% (150/150)** — weaker sense: span resolves to a chunk and contains the number; NOT support-identity (see `FINAL_REPORT.md` §N.10) |
| fabricated Dataset/Metric/Result for the 26 inaccessible papers | emitted anyway | **0** (78/78 abstain) |
| false OWN_PAPER attributions | n/a | **0 observed** |
| new models / services | — | **none** (BGE-M3 + qwen2.5:7b kept, no reranker, no GROBID/Docling/MinerU) |
| runtime (full corpus) | — | 51 min extraction on RTX 3050 6 GB, 2.65 GB VRAM |

- **26/60 papers are closed access with no preprint** (DOI but no ArXiv/PMCID) — hard free-acquisition ceiling.
  Consequence: **all synthesis / gap analysis is built only on the OA-reachable 34** — open-access selection
  bias, uncorrected and previously unstated (see `FINAL_REPORT.md` §N.11).
- Quantitative recall after the hierarchical-attribution rework: metrics 13 returned, results 8 (was 5 / 3);
  quantitative OWN attribution 8 -> 22, **0 false OWN** across all 21 returned items, CITED unchanged at 2.
- ChromaDB: working, no panic. JATS/XML: 2/60. Decision: **GO_WITH_CHANGES** (see `FINAL_REPORT.md` §P).
