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
| **Canonical pipeline, full 60-paper (run of record)** | `runs/20260901T160444Z-canon-L3-ca6e/` | 16:04Z |

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
| full-text acquisition | 31/60 (51.7%) | **34/60 (56.7%)** (33 as-run + fetch-cap fix) |
| wrong-paper accepted | not checked | **0** |
| landing-page/abstract as full text | possible | **0** |
| provenance on returned evidence | none | **100% (146/146)** |
| fabricated Dataset/Metric/Result for the 26 inaccessible papers | emitted anyway | **0** (81/81 abstain) |
| false OWN_PAPER attributions | n/a | **0 observed** |
| new models / services | — | **none** (BGE-M3 + qwen2.5:7b kept, no reranker, no GROBID/Docling/MinerU) |
| runtime (full corpus) | — | 38.7 min on RTX 3050 6 GB |

- **26/60 papers are closed access with no preprint** (DOI but no ArXiv/PMCID) — hard free-acquisition ceiling.
- Quantitative-field recall is deliberately low (metrics 5/33, results 3/33 returned): the abstention gate
  suppresses EXPLICIT numbers whose author-ownership can't be confirmed. Safe; a known coverage cost.
- ChromaDB: working, no panic. JATS/XML: 2/60. Decision: **GO_WITH_CHANGES** (see `FINAL_REPORT.md` §20).
