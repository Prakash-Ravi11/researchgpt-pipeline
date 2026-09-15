# EXP-LATEX-01 — reproducibility package

**Status: SCAFFOLDED — NO ARM EXECUTED.** Implementation, tests, harness,
statistics and gates are complete and verified. Neither the control nor the
treatment arm has been run, so **no EXP-LATEX-01 metric exists**. See §6.

Audit: `docs/experiments/EXP-LATEX-01-AUDIT.md`
Report: `docs/RESEARCHGPT_NOVELTY_EVIDENCE_REPORT.md`

---

## 1. Question

> Does LaTeX-aware structural ingestion improve scientific evidence extraction
> compared with the existing PDF-only pipeline, without degrading correctness,
> provenance, attribution, abstention, reproducibility or runtime?

**Read the audit's Finding A before running this.** The primary question has
already been measured twice on this corpus (Phase 4b, Phase 5x) and answered
negatively. The Part-15 primary gate is 60 % table binding on the LaTeX-eligible
subset; the best existing measurement is 24 %. The arm with genuine information
value is `atomic`, which has never been run.

## 2. Arms

| Arm | `RQ_LATEX_CHUNKING` | `RQ_TABLE_ATOMIC` | Role |
|---|:--:|:--:|---|
| `control` | 0 | 0 | protocol control — PDF-only |
| `latex` | 1 | 1 | protocol treatment |
| `atomic` | 0 | 1 | **the untested cell** — atomic tables alone |
| `latex_only` | 1 | 0 | reproduces the already-negative configuration |

Held constant: corpus, retrieval questions, evaluation queries, BGE-M3,
retrieval parameters, `CHUNK_WORDS=220`, `CHUNK_OVERLAP=40`,
`EXTRACTION_OUTPUT_RESERVATION=768`, qwen2.5:7b at temperature 0 / seed 42,
`content_aware` selection at `max_passages=10`, evaluation code, metric
definitions.

## 3. Layout

```
experiments/EXP-LATEX-01/
  experiment_manifest.json      machine-readable: arms, metrics, family, environment
  config/{control,latex,atomic,latex_only}.json
  guard.py                      output isolation (18/18)
  environment.py                Part-7 capture
  metrics_registry.py           33 metrics, 6 confirmatory — pre-registered
  paired_stats.py               stdlib paired statistics (82/82)
  analyze.py                    -> metrics_summary.csv, paper_level_results.csv, plots
  gates.py                      Part-15 acceptance gates
  run_arm.py                    one arm, guarded, preflighted
  kaggle/kaggle_exp_latex_01.py Parts 7-10 on T4 x2
  kaggle/EXP-LATEX-01.ipynb     the notebook
  tests/test_paired_stats.py    82/82
  tests/test_analyze_selftest.py 26/26 (synthetic)

runs/exp-latex-01/              ALL experimental output (gitignored)
  control/ latex/ evaluation/ logs/ metrics/ manifests/
  statistical_analysis/ failure_analysis/ plots/
```

## 4. Running it

```bash
# 0. preflight — reports exactly what is missing, writes nothing else
python experiments/EXP-LATEX-01/run_arm.py --arm control --preflight-only

# 1. arms (needs GPU, torch, chromadb, pymupdf, Ollama, and the corpus)
python experiments/EXP-LATEX-01/run_arm.py --arm control --corpus <collected_papers.json>
python experiments/EXP-LATEX-01/run_arm.py --arm atomic  --corpus <collected_papers.json>
python experiments/EXP-LATEX-01/run_arm.py --arm latex   --corpus <collected_papers.json>

# 2. paired analysis
python experiments/EXP-LATEX-01/analyze.py --control control --treatment atomic
python experiments/EXP-LATEX-01/analyze.py --control control --treatment latex

# 3. gates
python experiments/EXP-LATEX-01/gates.py --summary runs/exp-latex-01/metrics_summary.csv
```

On Kaggle (T4 x2), use `kaggle/EXP-LATEX-01.ipynb`.

## 5. Integrity properties, and how each is enforced

| Property | Enforcement | Verified |
|---|---|---|
| Canonical output never written | `guard.assert_experiment_output` on every path | 18/18; runner exits 1 |
| Control arm is the real control | flag-off chunking byte-identical to pre-change code | 4,295 chunks / 400 docs, 0 mismatches |
| Missing values never imputed | analyser drops the pair and counts it in `n_missing` | self-test |
| Unmeasured metrics never blank-pass | row written with `NOT MEASURED` | self-test |
| Gates never pass without data | `gates.py` emits `NOT MEASURED`, verdict `INCOMPLETE` | verified |
| Partial arms never look like results | preflight failure writes no `per_paper.json` | verified, exit 2 |
| Test choice not made after seeing data | `metrics_registry.py` pre-registers kind -> test | committed before any arm |
| Multiple comparisons addressed | Holm over a 6-metric confirmatory family; rest labelled exploratory | self-test |

## 6. Why no arm ran

```
python 3.11.15 · linux x86_64 · 4 cpu · 15 GB RAM
GPU        : none (nvidia-smi absent)
torch      : unavailable      sentence_transformers : unavailable
chromadb   : unavailable      pymupdf               : unavailable
numpy/scipy: unavailable      Ollama                : absent
corpus     : absent (data/ is gitignored)
```

`pip install numpy scipy` failed against PyPI (read timeout through the proxy).
The statistics module is stdlib-only as a consequence.

`runs/exp-latex-01/control/preflight.json` records this. No `per_paper.json` was
written for any arm.

## 7. Decision

Neither a merge recommendation nor a rejection can be made on experimental
grounds, because there is no experiment result.

**What can be recommended on the evidence that does exist:**

* The chunker, flags, config override and nested-tabular fix are **safe to
  merge** — default behaviour is byte-identical, and the nested fix repairs a
  demonstrated silent numeric loss on a code path that is off by default.
* `RQ_LATEX_CHUNKING=1` should **remain off by default** after any merge, per
  the Phase-4/5x negative result, until re-measured.
* Run `atomic` vs `control` first. It is the cheapest arm, needs no arXiv
  e-print fetching, and is the only comparison whose outcome is unknown.

Do not merge to a default-on state, do not tag a freeze, and do not treat the
Phase-4 numbers as this experiment's control — the nested-tabular fix means the
LaTeX arm is no longer byte-identical to the one that produced them.
