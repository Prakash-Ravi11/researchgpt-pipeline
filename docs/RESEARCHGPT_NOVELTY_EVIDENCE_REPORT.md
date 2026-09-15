# ResearchGPT: Novelty, Evidence, Quantitative Evaluation, Statistical Validation and Research Direction Report

Branch `claude/busy-rubin-q2j212` · base commit `acb89d8` · 2026-09-15
Companion: `docs/experiments/EXP-LATEX-01-AUDIT.md`

> **Status of this report.** Every number below is either (a) a value already
> measured and recorded in `experiments/document_evidence_pipeline/`, cited to
> its report, or (b) explicitly marked **NOT MEASURED**. **No arm of
> EXP-LATEX-01 was executed.** The audit environment has no GPU, no
> torch/sentence-transformers/chromadb/pymupdf, no Ollama, and the canonical
> corpus is gitignored and absent. Nothing here reports a new experimental
> result, because none was produced.

---

## 1. Executive summary

ResearchGPT is a reproducible, evidence-grounded RAG pipeline for scientific
literature. Its strongest asset is **not** the pipeline. It is the
**measurement apparatus around the pipeline**, and specifically a set of
*negative and methodological* findings that are unusually well controlled:

1. **Value preservation is not evidence preservation.** 98.6 % of 6,530
   ground-truth numeric values survive verbatim through PDF parsing and 100 %
   carry provenance, but only 16.8 % remain context-bindable — **8.9 %** for
   table-resident values. (`EXTRACTION_FIDELITY_REPORT.md`)
2. **Content parity does not imply extraction parity.** Restoring LaTeX numeric
   survival to parity with PDF (0.983 vs 0.987) still left the 11 LaTeX-retained
   papers extracting **5.82 vs 9.91** non-empty fields. The representation that
   preserved the most numbers was the worst input for the model.
   (`LATEX_ACQUISITION_REPORT.md`)
3. **Safety invariants can pass on a materially broken system.** 12/12 staging
   invariants returned `STAGING_PASS` with 0 errors on an ingestion path that had
   discarded ~60 % of table numerics; invariants 14 and 15 passed while three
   adversarial probes were being accepted. (`LATEX_ACQUISITION_REPORT.md`,
   `BINDING_VALIDATION_REPORT.md`)
4. **Evaluation coverage is not evaluation completeness.** A route-specific
   blind spot was found by controlled adversarial testing, not by the invariant
   suite that was written to catch it. (`BINDING_VALIDATION_REPORT.md`)

These are publishable *because they are negative and controlled*, not despite
it. The system contribution (BGE-M3 + Chroma + qwen2.5:7b + a parity gate) is
**not** a defensible novelty claim on its own.

**Readiness: PARTIALLY READY.** There is enough evidence for a strong
methods/negative-results paper on scientific-RAG reliability measurement. There
is **not** enough for a "our system is better" paper, and the current
EXP-LATEX-01 framing is pointed at a question this project has already answered
negatively.

---

### 1.1 Executive decision table

| Area | Current result | Target | Status | Evidence |
|---|---|---|---|---|
| Full-text acquisition | 34/60 = 56.7 % (from 31/60) | higher | **SUPPORTED** | `README.md`, run `…170346Z-canon-L3-525e` |
| Numeric survival | 98.6 % verbatim-lax (PDF), 98.1 % (LaTeX) | ≥ 98 % | **SUPPORTED** | `EXTRACTION_FIDELITY_REPORT.md`, `LATEX_ACQUISITION_REPORT.md` M1 |
| Table binding | 8.9 % (PDF) → 11.0 % pooled / 14.2 % gt-wt retained | ≥ 60 % on LaTeX-eligible | **NOT YET SUPPORTED** | `LATEX_ACQUISITION_REPORT.md` M1 re-slice |
| Anchor delivery | 16.7 % (`content_aware@10`) | ≥ 16.7 % | **SUPPORTED** (as baseline) | `SELECTION_POLICY_REPORT.md` |
| Provenance | 100 % (150/150) — *value-presence sense, not support identity* | 100 % | **PARTIALLY SUPPORTED** | `FINAL_REPORT.md` §84, §N.10 |
| Attribution | 0 wrong-paper, 0 false OWN_PAPER | 0 | **SUPPORTED** | `FINAL_REPORT.md` §129 |
| Abstention | 78/78 on inaccessible papers | 100 % | **SUPPORTED** | `FINAL_REPORT.md` §117 |
| Test suite | 15/15 + 42/42 | "91/91" — **not a test count** | **PARTIALLY SUPPORTED** | audit §3 reconciliation |
| Runtime | +47 % with LaTeX at reservation 4096 | ≤ +50 % | **SUPPORTED** (measured cost) | `LATEX_ACQUISITION_REPORT.md` Phase 5x |
| Peak VRAM | 5909/6144 MiB = 96 % | ≤ 5.5 GB | **NOT YET SUPPORTED** | `LATEX_ACQUISITION_REPORT.md` Phase 5x |
| Statistical significance | **none computed** — no paired statistics exist for any claim | paired tests with effect sizes | **NOT YET SUPPORTED** | see §10 |
| Cross-paper robustness | canonical 60 + medical 50, reported separately | multi-domain | **PARTIALLY SUPPORTED** | `MEDICAL_*_REPORT.md`, `CLAIM_LEDGER.md` row 6 |

---

## 2. Research problem

Scientific RAG systems are evaluated as if retrieving the right document and
producing fluent text were the hard parts. For evidence-grounded scientific
claims they are not. The hard part is that a number can survive the whole
pipeline — be extracted, be quoted, carry a valid provenance span — and still be
**unbound from the metric, dataset, and condition that give it meaning**. A
pipeline can be simultaneously 98.6 % faithful at the character level and 8.9 %
useful at the evidence level.

## 3. Research gap

Existing RAG evaluation reports answer-level faithfulness and retrieval-level
relevance. Neither measures whether a returned quantitative claim is bound to
its supporting *structure*. The gap this project sits in: **reliability
measurement for the structural layer of scientific evidence**, with
ingestion-time enforcement rather than post-hoc judging.

## 4. ResearchGPT architecture

See audit §1. Six stages; evidence grounding inside stages 1–2; measurement
isolated in `experiments/document_evidence_pipeline/`.

## 5. Current system capabilities

Five-source acquisition resolver with four acquisition states and identity/content
validation; structured representation from JATS and LaTeX into one
`structured_table` cell model; an ingestion-time content-parity gate with
per-document fallback; numeric-anchor provenance; hierarchical OWN_PAPER/CITED
attribution; abstention on inaccessible papers; a 16-invariant staging suite; a
mutation/adversarial probe suite; a claim ledger that refuses uncited claims.

## 6. Existing frozen baseline

As tabulated in audit §3. Note three properties of the freeze itself:

* **There is no git tag.** `git tag -l` is empty; there is no `paper-freeze-v1`
  object and no `main` branch. The freeze is documentary (the reports and
  `CLAIM_LEDGER.md`), not cryptographic.
* The corpus (`data/`) is gitignored and not distributed, so the baseline is not
  independently re-runnable from the repository alone.
* Three figures in the project brief (146/146, 81/81, 91/91) are superseded or
  miscategorised values (audit §3).

Recommendation: create an annotated tag over the commit whose reports define the
freeze, and record the corpus manifest hash. This is cheap and removes a real
reviewer objection.

## 7. Quantitative results (measured, pre-existing)

| # | Finding | Number | Corpus |
|---|---|---|---|
| 1 | Verbatim survival vs bindability | 98.6 % / 16.8 % / 8.9 % table | 6,530 values, 23 paired papers |
| 2 | Denominator collapse | bindability 0.089→0.120 while survival was 0.388 | canonical 60 |
| 3 | Content ≠ extraction parity | 0.983 survival, 5.82 vs 9.91 fields | 11 LaTeX-retained |
| 4 | Constants fail on new distributions | 5.82 @768 vs 9.09 @4096 | 11 LaTeX-retained |
| 5 | Delivery ≠ coverage | 16.7 % delivery → 94 % results | canonical 60 / medical 50 |
| 6 | Domain-dependent failure modes | 2/6 vs 12/13 cross-row rejections | canonical + medical |
| 9 | Framework sensitivity | 18/19 strict, 6/19 at threshold, 19/19 structural | 106 cases |
| 11 | Parity-gate precision | 12/12 justified, precision 1.00 | 12 fallbacks |
| 14 | Selection isolated effect | metrics +16 pp, results +26 pp | medical 19 |

## 8. EXP-LATEX-01 methodology

Pre-registered in `experiments/EXP-LATEX-01/metrics_registry.py` and
`experiment_manifest.json`. Control `(0,0)`, treatment `(1,1)`, plus factorial
`atomic (0,1)` and `latex_only (1,0)`. Everything else held constant (audit §7).
Output isolated to `runs/exp-latex-01/`, enforced by `guard.py`.

## 9. Control vs treatment results

**NOT MEASURED.** No arm was executed. `runs/exp-latex-01/control/preflight.json`
records the blockers: torch, sentence-transformers, chromadb, pymupdf and Ollama
absent; no CUDA device; corpus absent.

What *is* delivered and verified:

| Component | Verification |
|---|---|
| `RQ_TABLE_ATOMIC` flag-off parity | byte-identical to the pre-change chunker over **4,295 chunks / 400 randomised documents, 0 mismatches** |
| Atomic chunking effect | a 160-row table: **22 chunks → 1** |
| Nested-tabular fix | **226 identical / 74 differ (all nested) / 0 unexpected** over 300 generated tables |
| Table unit tests | **54/54** (`tests/test_table_atomic.py`) |
| Paired statistics | **82/82** against t-tables, Cauchy and df=2 closed forms, brute-forced Wilcoxon nulls, independent binomial McNemar, Newcombe Wilson intervals |
| Analyser end-to-end | **26/26** on synthetic data, including "missing values are dropped, never imputed" |
| Output guard | **18/18**; runner exits 1 on a canonical `--out`, 2 on failed preflight |

## 10. Statistical analysis

**No statistical test has ever been run in this project.** Every existing
finding is a point estimate or a ratio; there is no confidence interval, no
paired test, and no effect size anywhere in the 23 reports. This is the single
largest methodological weakness, and it is fixable without new data for several
claims — the per-paper artefacts already exist for the LaTeX M1/M2 measurements.

Delivered: `paired_stats.py` (paired t, Wilcoxon exact + tie-corrected normal,
McNemar exact + continuity-corrected, Wilson, seeded bootstrap, Cohen's *dz*,
rank-biserial *r*, Holm–Bonferroni), validated 82/82. Applied to nothing yet.

## 11. Failure analysis

Pre-existing, classified per Part 16 categories:

| Category | Instance | Evidence |
|---|---|---|
| acquisition | 26/60 closed access, no preprint — hard free-acquisition ceiling | `README.md` |
| LaTeX | 1/24 papers ship no `.tex` (`2504.00698`) | `LATEX_ACQUISITION_REPORT.md` |
| table | 21/178 tables fall back to PDF; `no_data_cells_after_parse` ×16 | same |
| table | **nested tabular silently truncated the outer table** — found in this audit, fixed | audit §6 |
| chunking | table blocks split at 220 words — **unmeasured on the corpus** | audit §0 |
| extraction | 2 papers `done_reason == "length"` at reservation 768 | same |
| extraction | `a9b2a3fd6070` returns valid **empty** JSON at both 768 and 4096 | Phase 5x |
| reproducibility | no git tag; corpus not distributed | §7 |
| evaluation | invariants fidelity-blind; route-specific blind spot | `CLAIM_LEDGER.md` rows 7, 8 |

## 12. Poison-RAG case study

The case study named in the protocol (Nazary, Deldjoo, di Noia — *Poison-RAG:
Adversarial Data Poisoning Attacks on Retrieval-Augmented Generation in
Recommender Systems*, ECIR 2025) **could not be re-run**: the corpus is absent
and no extraction engine is available.

What the audit contributes to it is mechanism, not measurement. Three of the
weaknesses listed in the protocol map onto defects with identified causes:

* *"detailed quantitative tables were not fully represented"* — consistent with
  table blocks being split at `CHUNK_WORDS=220`, which strands rows from their
  headers. `RQ_TABLE_ATOMIC` addresses exactly this; the effect is **unmeasured**.
* *"mathematical formulation incompletely represented"* — `_clean()` mangles
  row labels containing math (`$\mathcal{L}_{\text{adv}}$` → `\mathcalL_adv`)
  while preserving the numerics. Verified on a fixture in
  `tests/test_table_atomic.py` case 6; **prevalence on the paper is unmeasured**.
* *"Figure 1 incorrectly segmented into multiple image objects"* — see §18.

The BERT / OpenAI / GPT-3.5 embedding distinction the protocol flags is a
**claim-typing** requirement (§19), not an extraction requirement, and nothing in
the current schema enforces it.

### 12.1 Figure extraction: semantic figures vs image objects

The protocol's observation is correct and generalises: **PDF image-object count
is not semantic figure count.** A single semantic figure is routinely composed of
several embedded images (panels, insets, vector fragments).

Current state: `src/processing/figure_extractor.py` extracts image objects.
Nothing groups them. `metrics_registry.py` now carries `semantic_figures` and
`image_objects` as **separate** metrics, with `image_objects` explicitly marked
"reported for contrast, not as a quality metric", so the two can never be
conflated in a results table.

Proposed grouping strategy (not implemented, not measured): cluster image
objects on a page by (a) bounding-box adjacency below a gap threshold, (b)
proximity to a single `Figure N` caption block, (c) absence of an intervening
text block; then bind the cluster to the caption. Validate against
hand-labelled semantic figure counts on a subset. **This is a proposal; no
number is claimed.**

### 12.2 Author claim vs system inference (claim typing)

The protocol requires every extracted claim to carry one of
`AUTHOR_STATED` / `EXPERIMENTALLY_REPORTED` / `TABLE_DERIVED` / `FIGURE_DERIVED` /
`SYSTEM_INFERENCE` / `SYSTEM_SUMMARY`, with
`AUTHOR_STATED_LIMITATION` distinct from `SYSTEM_INFERRED_LIMITATION`.

**This is not implemented.** `src/evidence/schema.py` has no claim-type field;
`attribute.py` classifies *which paper* a claim belongs to (OWN_PAPER / CITED),
not *what kind of claim* it is. The Poison-RAG audit finding — "an inferred
limitation may have been represented as an author-stated limitation" — is
therefore a structural gap, not a one-off error: the schema has no way to
express the distinction, so it cannot be violated *or* enforced.

This is, in my assessment, **the most valuable unbuilt thing in the project**,
and more defensible as a contribution than LaTeX ingestion. See §17.

## 13. Evidence and provenance validation

Provenance is 150/150 in the **value-presence** sense: the span resolves to a
real chunk and contains the number. `FINAL_REPORT.md` §N.10 is explicit that
this is **not support identity** — Test 2's `support_deletion_primary` re-grounded
7/26 items on a different chunk when the value recurred elsewhere. Any paper
claiming "100 % provenance" must carry that qualification in the same sentence.

## 14. Mutation testing

A mutation class for quantitative binding (cross-row, correct-row-wrong-column,
correct-metric-wrong-condition, cross-table substitution) with **0 of 30
adversarial acceptances across 37 probes** post-F1. `CLAIM_LEDGER.md` row 13
narrows the claim from "we introduce mutation testing to RAG evaluation"
(MetaRAG holds that) to the mutation class itself — correctly, and the ledger
also flags that the prior-art attribution is itself uncited. See §19.

## 15. Abstention evaluation

78/78 abstentions on the 26 inaccessible papers, 0 fabricated Dataset/Metric/
Result. Strong, and the denominator is honest. Note it measures abstention when
*no text exists*, which is the easy case; abstention under *retrieved-but-
insufficient* evidence is not separately measured.

## 16. Reproducibility evaluation

| Property | State |
|---|---|
| Seeded generation | yes — temperature 0, seed 42 |
| Deterministic chunking | yes |
| Pinned freeze | **no git tag** |
| Corpus distributed | **no** (gitignored) |
| Environment captured per run | not before this work; `environment.py` adds it |
| Statistical reproducibility | bootstrap seeded; nothing else applicable yet |

## 17. Prior-art comparison

**Caveat stated first: no literature survey exists in this repository, and I
could not perform one here** (no network access to scholarly sources from this
environment). `CLAIM_LEDGER.md` rows 12s and 13s already record that the
project's two prior-art attributions (arXiv 2605.30790 for content-retention
checking; MetaRAG for mutation testing) **cannot be cited to any nominated
report** and that the novelty delta is UNSUPPORTED until a survey is added.

I will not fabricate citations to fill this table. What follows is the
*structure* the survey must fill, with the project's own position stated and the
prior-art column left explicitly empty.

| Category | What ResearchGPT does | Prior art | Delta measurable? |
|---|---|---|---|
| RAG evaluation frameworks | ingestion-time enforced content-parity gate with per-document fallback | **SURVEY REQUIRED** | yes — precision 1.00, n=12 |
| Hallucination / faithfulness eval | number-anchored structural check vs mean-over-claims aggregation | **SURVEY REQUIRED** (RAGAS 0.2.15 measured as a comparator) | yes — 31/67 vs 54/67 |
| Table extraction | structural cell model (value + column header + row label + caption + section) | **SURVEY REQUIRED** | yes — bindability |
| Scientific PDF/LaTeX parsing | stdlib-only LaTeX e-print path, no GROBID/Docling/Marker | **SURVEY REQUIRED** | partly — deliberately avoids the standard tools |
| RAG poisoning/security | adversarial binding probes | **SURVEY REQUIRED** | yes — 0/30 acceptances |
| Provenance/citation eval | span-resolves-and-contains-value | **SURVEY REQUIRED** | weak — not support identity |

The one comparator actually measured is RAGAS 0.2.15 Faithfulness with a
qwen2.5:7b judge, under a pre-registered criterion
(`EVAL_FRAMEWORK_SENSITIVITY_REPORT.md`). That is a real, controlled prior-art
comparison and it is the strongest such asset the project has.

## 18. Novelty assessment

**Level 1 — existing technologies used.** BGE-M3, ChromaDB, qwen2.5:7b, PyMuPDF,
Semantic Scholar / Europe PMC / arXiv APIs. **Zero novelty.** Using them is not
a claim.

**Level 2 — engineering/system contribution.** The five-source resolver with
identity/content validation; the content/identity split enforced at schema level
(identity may never come from the `.tex`); the parity gate; one `structured_table`
shape shared by JATS and LaTeX. **Real but modest** — this is competent systems
work, publishable as a system description, not as a scientific contribution.

**Level 3 — scientific/methodological contribution.** The candidate claim is:

> *A reproducible evidence-grounded evaluation framework for measuring
> reliability of scientific RAG pipelines across acquisition, structural
> extraction, retrieval, provenance, attribution, abstention and synthesis.*

**Do the experiments support this claim? Partially — and not as stated.**

Supported: the project demonstrably measures acquisition, structural extraction,
provenance, attribution and abstention, and it has found real failures with
those measurements that a conventional framework missed.

Not supported: "framework" implies generality. Everything is measured on one
60-paper CS corpus and one 50-paper medical corpus, with one embedding model,
one 7B extractor, and one judge. There is no ablation showing the framework
transfers, no statistical validation of any claim, and the retrieval and
synthesis arms are barely measured. As written, the claim overreaches.

**The defensible restatement**, which the evidence does support:

> *Four controlled negative results showing that standard reliability signals
> for scientific RAG — verbatim fidelity, safety invariants, aggregate
> faithfulness scores, and content-preservation parity — each pass while the
> evidence layer is materially broken; with the measurement apparatus that
> exposes them.*

That is a narrower claim and a much stronger one.

### 18.1 Novelty scorecard

Scored 0–5 with rationale. **No composite score is given** — a single number
would imply a precision this evidence does not have, and would be the same
rhetorical move the project's own claim ledger exists to prevent.

| Dimension | Score | Rationale |
|---|:--:|---|
| Problem significance | **4** | Evidence unbinding is real, measured, and under-studied. Not 5: it affects a subset of scientific RAG use, not all RAG. |
| Research gap clarity | **4** | The 98.6 % / 8.9 % gap states the problem in one line. Not 5: the gap is argued from this system's own measurements, not against a surveyed literature. |
| Technical novelty | **2** | Every component is off-the-shelf. The parity gate and the shared cell model are sound engineering, not new technique. |
| Methodological novelty | **4** | Pre-registered detection criteria, positive controls that withdrew the project's own claims, a claim ledger, invariant-blindness findings. This is genuinely above the norm. |
| Experimental novelty | **3** | Good controls (12-paper PDF-fallback control is clean; 3-arm routing control). Offset by a 2-arm design where a factorial was needed, and by n=2 and n=5 denominators. |
| Evaluation rigor | **4** | Withdrew claims 9s, 11s, 14s on their own controls. Denominators carried in claim wording. Rare discipline. |
| Reproducibility | **3** | Seeded, deterministic, environment-captured. But no git tag, no distributed corpus, and the baseline cannot be re-run from the repo alone. |
| Generalizability | **2** | Two corpora, one model stack, one judge. No transfer evidence. |
| Quantitative evidence | **4** | Large, well-sourced measurement base across 23 reports. |
| Statistical evidence | **1** | Zero statistical tests, zero confidence intervals, zero effect sizes in the entire project. The apparatus now exists; nothing has used it. |
| Prior-art differentiation | **1** | No literature survey exists. Two prior-art attributions are recorded in the ledger as uncitable. One measured comparator (RAGAS). |

**Optimistic reading.** A methods paper built on findings 1, 3, 7 and 8, with the
RAGAS comparison as the external anchor, is a credible workshop-to-mid-conference
submission. The negative results are clean and the measurement discipline is
visible.

**Conservative reading.** Without a literature survey and without a single
p-value, a reviewer sees a well-instrumented single-system engineering report.
Findings are compelling but every one is n=1 system, n≤2 corpora.

**Reviewer-risk reading.** The three sharpest objections, in order of danger:
(1) *"Everything is measured on your own system; how do I know this generalises?"*
— currently unanswerable. (2) *"No statistics."* — fatal at a venue that expects
them, and cheap to fix. (3) *"The 100 % provenance claim is value-presence, not
support identity, and you say so yourself."* — survivable only if the
qualification is in the abstract, not a footnote.

## 19. Current limitations

Open-access selection bias (synthesis built only on the 34 reachable papers,
uncorrected); provenance in the weak sense; binding measured on denominators
below 10; no claim typing; no figure grouping; no statistics; no survey; no
pinned freeze; retrieval metrics (Recall@k, MRR, nDCG) essentially unmeasured;
one extractor model.

## 20. Strongest defensible contribution

The §18 restatement: **four controlled negative results about the failure of
standard reliability signals in scientific RAG, plus the apparatus that found
them.** Its strength is that each finding is a *falsified assumption* rather than
a performance number, which makes it robust to the "your system is small" objection.

## 21. Alternative research tracks

| | Novelty potential | Experimental burden | Current evidence | Remaining work | Publication potential | Risk | Effort |
|---|---|---|---|---|---|---|---|
| **A. Scientific RAG reliability/evaluation** | high (methodological) | medium | **strongest** — findings 1,3,7,8,9 + RAGAS comparator | survey, statistics, one transfer corpus | mid-tier conference / strong workshop | prior-art overlap unknown | **~4–6 weeks** |
| **B. Research assistant / synthesis** | low | high | weakest — synthesis barely measured, OA bias uncorrected | human eval, baselines, larger corpus | low without human study | crowded field | ~3 months |
| **C. Document intelligence / structural extraction** | low–medium | high | LaTeX arm measured **negative**; no GROBID/Docling/Marker/Nougat comparison | full comparator study, bigger corpus | hard — mature field with strong baselines | **high** — likely loses to existing tools | ~2–3 months |
| **D. Hybrid reliability + structural** | medium | high | inherits C's negative result | all of A plus all of C | dilutes A's sharpest claims | high | ~3 months |

## 22. Recommended research track

**TRACK A**, on evidence, not preference.

A is the only track whose central claims are *already measured and already
survived their own controls*. C is the track EXP-LATEX-01 currently serves, and
C's core experiment has been run twice and came back negative — a table-binding
gate of 60 % against a best measured 24 %, at +47 % runtime and 96 % VRAM. D
inherits that. B has the least evidence.

The decisive argument: Track A's remaining work (a survey, statistics on
artefacts that already exist, one transfer corpus) is weeks. Track C's remaining
work is a comparator study against mature tools that ResearchGPT would probably
lose.

**This recommendation implies re-scoping EXP-LATEX-01.** Its value under Track A
is not "does LaTeX help" — that is answered — but the `atomic` arm as a *fifth
negative-or-positive result* about chunk-boundary effects on structural
evidence, which is a Track A finding.

## 23. Research paper readiness and required experiments

**PARTIALLY READY.**

Ready: the problem statement, four controlled findings, the measurement
apparatus, one external comparator, and a claim ledger that already enforces
citation discipline.

Not ready: no statistics, no literature survey, no transfer evidence, no pinned
freeze.

**Minimum experiments before drafting**

1. Run `paired_stats` over the **existing** per-paper artefacts (`m1_per_paper.json`,
   the M2 field counts) — CIs and effect sizes for findings 1 and 3. *No new data.*
2. Literature survey for §20, with the ledger's two uncitable attributions resolved.
3. Pin the freeze: annotated tag + corpus manifest hash.
4. Run the `atomic` vs `control` arm on Kaggle — the cheapest unanswered question.

**Minimum experiments before submission**

5. One transfer corpus in a third domain, to answer "does this generalise".
6. A second extractor model, to show findings 3 and 4 are not qwen2.5:7b artefacts.
7. Support-identity provenance measurement, or an abstract that states the weak sense.
8. Retrieval metrics (Recall@k, MRR, nDCG) actually measured, or dropped from the claims.

## 24. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Prior art already covers the four findings | **unknown — unsurveyed** | fatal | do the survey first, before any more experiments |
| Reviewers reject n=1-system evidence | high | major | transfer corpus (#5) |
| "No statistics" desk-reject | high | fatal | #1 — cheapest fix available |
| Findings are model-specific | medium | major | #6 |
| EXP-LATEX-01 consumes the remaining time for a negative answer | **high** | major | re-scope to the `atomic` arm only |

## 25. Final faculty decision summary

The project has a real contribution and it is **not** the one the current
experiment is chasing. The strongest asset is a set of controlled demonstrations
that standard reliability signals pass while scientific evidence is broken. The
weakest links are statistical (zero tests) and bibliographic (zero survey) —
both cheap to fix and both currently blocking.

Recommended sequence: **survey → statistics on existing artefacts → pin the
freeze → `atomic` arm → transfer corpus.** Do not run the full four-arm
EXP-LATEX-01 before the survey; if prior art already owns these findings, the
arms do not matter.

---

## 26. Appendix: raw metrics

`experiments/document_evidence_pipeline/` (23 reports). Run of record:
`runs/20260901T170346Z-canon-L3-525e/`. The `runs/` trees are gitignored and
regenerable via the documented harnesses.

## 27. Appendix: statistical tables

**Empty — no statistical test has been run.** `experiments/EXP-LATEX-01/paired_stats.py`
is validated 82/82 and applied to nothing.

## 28. Appendix: experiment configuration

`experiments/EXP-LATEX-01/experiment_manifest.json`, `config/{control,latex,atomic,latex_only}.json`,
`metrics_registry.py` (33 metrics, 6 confirmatory).

## 29. Appendix: git commit and environment information

```
branch  claude/busy-rubin-q2j212
commit  acb89d8 (base)
tags    none in repository
python  3.11.15 · linux x86_64 · 4 cpu · 15 GB RAM
GPU     none — nvidia-smi absent
absent  torch, sentence_transformers, chromadb, pymupdf, numpy, scipy, Ollama, data/
```

Full capture: `runs/exp-latex-01/manifests/kaggle_environment.json` and
`experiments/EXP-LATEX-01/experiment_manifest.json`.
