# runs/exp-latex-01 — EXP-LATEX-01 output root

Every experimental artefact from EXP-LATEX-01 lives here and nowhere else.
`experiments/EXP-LATEX-01/guard.py` refuses any write outside this directory and
refuses the canonical directories (`runs/`, `data/`, `data_test/`,
`experiments/document_evidence_pipeline/runs/`) explicitly.

Contents are gitignored and regenerable — see `docs/experiments/EXP-LATEX-01.md`.

```
control/  latex/  atomic/  latex_only/   per-arm per_paper.json, manifest.json, preflight.json
evaluation/  logs/  metrics/  manifests/  statistical_analysis/  failure_analysis/  plots/
_selftest/                                SYNTHETIC analyser self-test — never a result
```

**As of the scaffolding commit, no arm has been run.** Any `per_paper.json`
found here was produced after that commit; check its `manifest.json` for the
environment and commit it came from.
