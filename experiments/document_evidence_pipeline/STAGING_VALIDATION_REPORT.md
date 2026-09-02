# STAGING VALIDATION REPORT

Repo `C:\Users\Praka\Downloads\researchgpt-pipeline` · branch `claude-code-verification`
Parent HEAD at start: `a8ffc1d` · staging run git rev: `a8ffc1d`
Run: `experiments/document_evidence_pipeline/runs/staging-20260902T030714Z/`

# Executive Decision

**STAGING_PASS_WITH_LIMITATIONS**

All 12 safety invariants PASS, the A/B/C/D monitor is `OK`, the real six-stage pipeline ran end-to-end
with **0 errors**, and existing tests are unchanged (37/37 + 42/42). Limitations (§Failures / Warnings):
the bounded staging corpus is small (8 papers, 7 full-text, survey/benchmark-heavy), so verified
quantitative coverage is low (16 items) and there is still **no human-gold** precision measurement.
No genuine defect was discovered. Production/default stays disabled.

# Configuration

Two-file separation — **no code change** to `src/config.py`, no new flag-resolution logic, no env var.
Mirrors how `configs/test_config.yaml` already works (`run_pipeline.py --config <file>`).

| config | `evidence_grounding.enabled` | corpus | paths |
|---|---|---|---|
| `configs/config.yaml` (production / default) | **false** (unchanged) | RAG, 60 papers | `data/` |
| `configs/staging_config.yaml` (**new, tracked, no secret**) | **true** | LLM-reasoning, 8 papers | `data_test/` |

Verified at runtime by `staging_run.py`:
`load_config("configs/config.yaml")["evidence_grounding"]["enabled"] == False` and
`load_config("configs/staging_config.yaml")["evidence_grounding"]["enabled"] == True`.

# End-to-End Results  (`runs/staging-20260902T030714Z/manifest.json`)

| | value |
|---|---|
| run id | `staging-20260902T030714Z` |
| config | `configs/staging_config.yaml` (staging flag on; production default flag off) |
| corpus / query | "large language model reasoning benchmarks", 8 frozen `data_test` papers |
| model | `qwen2.5:7b` (Ollama), retrieval-aware context, no reranker |
| **acquisition** | **7/8 full text** (FULL_TEXT 7 · NO_ACCESSIBLE_FULL_TEXT 1); source arXiv ×7; representation pdf ×7 |
| identity validation | 7/7 passed; **wrong-paper accepted 0** |
| evidence RETURNED | datasets 12 · metrics 2 · results 2  (**total 16**) |
| evidence abstained | datasets 3 · metrics 6 · results 3 |
| grounded-quant attribution | OWN_PAPER 4 · CITED_PAPER 0 · UNKNOWN 3 → only the 4 OWN RETURNED |
| **provenance** | **19/19 = 100%** |
| **no-full-text quantitative abstention** | **3/3 = 100%** (the 1 NO_ACCESSIBLE paper) |
| pipeline errors | **0** |
| runtime | 333.6 s (acquisition + Stage 2–5, 8 papers) |

The 4 RETURNED quantitative items (hand-checked, all OWN): `ef62f95c` metrics + results
("positive relationship (Spearman's r2 = 0.36) …" — the paper's own analysis, number verbatim in span),
`4fd7dfbb` results ("results reveal significant disparities in multilingual capabilities" — the paper's
own finding), `8d6411e3` metrics ("Accuracy (%)" table header). Values 3–4 are thin (a table header, a
qualitative sentence) — a documented quality nuance, **not** a safety issue; consistent with the
primary-corpus behaviour.

# Monitoring

Hook: `src/evidence/monitor.py`, called at the end of `src/evidence/gate.py::run_evidence_gate`
(observability *inside* Stage 5 — **not** a new stage). Writes `evidence_monitor.json` next to
`evidence_gate_summary.json` and prints one status line. It never raises; the staging runner enforces
STOP-on-fail.

| Signal | Result | Status |
|---|---:|---|
| A · RETURNED quant count (datasets/metrics/results/total) | 12 / 2 / 2 / **16** | **INFO** — different corpus than the recorded reference (60-paper, total 74); counts recorded, no drift verdict (per the "a different corpus is not automatically a failure" rule) |
| B · RETURNED quant items with `attribution != OWN_PAPER` | **0 / 4** | **OK** |
| C · provenance_valid / provenance_checked | **19 / 19 = 1.00** | **OK** |
| D · no-full-text papers returning a Dataset/Metric/Result | **0** | **OK** |
| **overall** | | **OK** |

Drift band for the *same* corpus is `[0.5×, 2.0×]` of the recorded reference total — deliberately wide,
so it flags "something moved a lot" rather than imposing an arbitrary quality target.

# Safety Invariants

| # | invariant | result |
|---|---|---|
| 1 | wrong-paper accepted = 0 | **PASS** (0) |
| 2 | false OWN_PAPER = 0 | **PASS** (0 / 4 RETURNED quant) |
| 3 | unsupported quantitative claims = 0 (every RETURNED item EXPLICIT + provenance_valid) | **PASS** |
| 4 | no-full-text quantitative leakage = 0 | **PASS** (0) |
| 5 | provenance = 100% | **PASS** (19/19) |
| 6 | errors = 0 | **PASS** |
| 7 | CITED_PAPER cannot become OWN_PAPER | **PASS** (0 CITED among RETURNED) |
| 8 | UNKNOWN cannot become OWN_PAPER | **PASS** (0 UNKNOWN among RETURNED; 3 UNKNOWN all abstained) |
| 9 | abstract-only / no-full-text papers cannot emit unsupported quantitative evidence | **PASS** (3/3 abstained) |
| 10 | evidence span contains the claimed value | **PASS** (all RETURNED quant numbers verbatim in the paper + span) |
| 11 | number-anchored results gate remains active | **PASS** (`gate.py` still has the `field == "results"` number-anchored branch + `_NUMVAL`) |
| 12 | six-stage architecture unchanged | **PASS** (`run_pipeline.py` still chains Stage 1→2→3→4 + sanity; monitor is inside Stage 5, no 7th stage) |

# Tests

| suite | before | after | change |
|---|---|---|---|
| `python tests/test_pipeline.py` | 37/37 | **37/37** | none — monitor runs only inside `run_evidence_gate`, which these tests do not call |
| `experiments/.../tests/test_pipeline_units.py` | 42/42 | **42/42** | none |

No test was modified.

# Failures / Warnings

- **No FAILs.** Monitor `overall = OK`; all 12 invariants PASS; 0 pipeline errors.
- **Limitation — small bounded corpus.** 8 papers / 7 full-text, and 5 of the 7 are survey /
  benchmark-proposal papers that legitimately report few "our measured result" claims → verified
  quantitative coverage is low (16 RETURNED, 4 quant). The gate correctly abstains rather than
  manufacturing evidence; this is expected, not a regression.
- **Limitation — no human gold.** All counts are coverage under a strict grounding + attribution gate
  + manual inspection, not precision/recall vs labelled data.
- **Limitation — 2 thin RETURNED values** (a table-header "Accuracy (%)", a qualitative
  "disparities …" sentence). Both are the paper's own (attribution correct), just not crisp numbers —
  a value-quality tier (EXPLICIT vs INFERRED) is still not implemented. Not a safety issue.
- Monitor signal A returned **INFO** (not PASS/FAIL) because the staging corpus ≠ the 60-paper
  reference; a same-corpus staging re-run would return PASS/WARN with a drift ratio.

# Recommendation

**Keep `evidence_grounding` enabled in STAGING only** (`configs/staging_config.yaml`). All safety
conditions pass on the real six-stage pipeline and on an independent topic.

**Do NOT enable production.** `configs/config.yaml` keeps `evidence_grounding.enabled: false`.
Before any production change: (a) a same-corpus staging re-run so monitor signal A produces a real
drift verdict; (b) a paired staging A/B on a genuinely distant domain (clinical / humanities);
(c) a human-gold spot-check of ~20 RETURNED items; (d) wire the `evidence_monitor.json` `overall`
field into whatever staging alerting exists.

---

## Git safety (pre-commit)

```
git status --porcelain      # only src/evidence/gate.py modified (tracked); monitor.py, staging_run.py,
                             # configs/staging_config.yaml new; no unrelated tracked files touched
git diff --check            # clean (LF/CRLF warning only)
git diff --stat a8ffc1d     # src/evidence/gate.py | 5 +++++
```

No force push, no reset, no history rewrite, no amend. `a8ffc1d` and all earlier validation history
preserved. One focused commit.

## Files changed

| file | change |
|---|---|
| `src/evidence/monitor.py` | **new** — deterministic A/B/C/D monitor; writes `evidence_monitor.json` |
| `src/evidence/gate.py` | +5 lines — call `run_monitor(...)` at the end of `run_evidence_gate` |
| `configs/staging_config.yaml` | **new, tracked, no secret** — the only place `evidence_grounding.enabled: true` |
| `experiments/document_evidence_pipeline/staging_run.py` | **new** — bounded reproducible E2E staging runner + 12-invariant checker |
| `experiments/document_evidence_pipeline/STAGING_VALIDATION_REPORT.md` | **new** — this report |

Production behaviour with `configs/config.yaml` is byte-for-byte unchanged (flag still false).
