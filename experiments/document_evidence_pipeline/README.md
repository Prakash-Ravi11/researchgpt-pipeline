# document_evidence_pipeline — isolated investigation

Read-only against production data; every run writes only to `runs/<run_id>/`.
No production module is imported for measurement; no `data/` path is mutated; no credentials are used.

## Authoritative results (latest)

| Phase | Artifact | Run |
|---|---|---|
| 0 Recon | `../../progress.md` (COMPLETED section) | — |
| 1 Baseline | `runs/20260901T150245Z-0e6dd1de/{baseline,source_results,parser_results}.json` | 2026-09-01T15:02Z |
| 2 Acquisition | `runs/20260901T150624Z-acq-2272d1/{acquisition_results,acquisition_summary,report}.json/md` | 2026-09-01T15:06Z |
| 2/3 Decision | `acquisition/DECISION_phase2.md` | — |

Do not cite `FINAL_REPORT.md` — its corpus (50 papers, agriculture) no longer matches the repo
(now 60 papers, medical image segmentation). It is kept only as a historical record.

## Harnesses

- `benchmark.py --run` — read-only P0 baseline + source/parser/chroma feasibility probes.
- `acquisition/resolve_corpus.py --run [--limit N] [--skip SRC]` — P1 per-paper multi-source full-text
  resolver (S2 / arXiv / OpenAlex / Europe PMC / Crossref), PyMuPDF+JATS validated.
- `runner.py` — deterministic 24-case synthetic attribution/abstention oracle (no production imports).
- `real_benchmark.py`, `baseline_inventory.py` — earlier-session harnesses; results under `runs/*-real-*`
  are STALE (old corpus) and must be re-run before use.

## Headline numbers (2026-09-01)

- Baseline full-text acquisition: **31/60 (51.7%)**.
- Multi-source ceiling: **34/60 (56.7%)** — delta **+3 papers**, all reachable via OpenAlex (1) + Europe PMC JATS (2).
- **26/60 papers are closed access with no preprint** — hard ceiling for free acquisition.
- ChromaDB: working, no panic. JATS/XML: available for 2/60. GROBID/Docling/MinerU: not installed.
