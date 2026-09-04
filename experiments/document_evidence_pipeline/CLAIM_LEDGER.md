# CLAIM LEDGER

Branch `claude-code-verification` · 2026-09-04
One row per paper claim, with the exact wording it will carry, the number and report
that back it, and its status. **Nothing enters the paper that is not a row here.**

**Rules applied.** Every row cites a specific report and a specific number; "the
results show" is not accepted. Any claim that cannot be cited that way is listed
anyway as UNSUPPORTED so the decision to drop it is visible. Any claim with n below
10 carries its denominator inside the claim wording, not in a footnote. Where a
claim changed after a later experiment, both the superseded and the current wording
are recorded — this project has three documented cases of a wrong number
propagating, and the ledger is the last guard against a fourth.

**Source-set note.** Twelve of the thirteen nominated reports were read.
`PHASE6_REGRESSION_REPORT.md` **does not exist** in the tree; no claim in this
ledger rests on it, and any future claim that would have cited it must be treated as
UNSUPPORTED until the report is written.

---

## Empirical findings

| # | Claim (exact wording as it will appear) | Evidence (number + report) | Experiment | Corpus | Status | Section |
|---|---|---|---|---|---|---|
| 1 | **Value preservation is not evidence preservation.** Through the PDF path, 98.6 % of ground-truth numeric values survive verbatim and 100 % carry provenance, but only 16.8 % remain context-bindable — 8.9 % for table-resident values. 86 % of table values that survive strict verbatim matching have lost the local context needed to tie them to a metric or dataset. | pooled 6,530 meaningful values / 23 paired papers: verbatim-lax 98.6 %, provenance 100 %, context-bindable 16.8 %; table split 98.7 % verbatim vs 8.9 % bindable; 3,476 strict table survivors → 481 bindable. `EXTRACTION_FIDELITY_REPORT.md` §STEP 3 POOLED + §"How many surviving values became unbindable" | Test 1 extraction fidelity (`extraction_fidelity.py`) | canonical 60 — 23 arXiv PDF↔LaTeX pairs | **SUPPORTED** | results (headline) |
| 2 | **A metric can improve while its denominator collapses.** Table bindability rose 0.089 → 0.120 on the LaTeX path at a point when only 38.8 % of table numeric values were present in that representation at all (verbatim-lax 0.388 vs PDF 0.987). The improvement was real and worthless; survival and binding must always be reported together. | vb-lax before 0.388 / 0.987; bindability 0.089 → 0.120. `LATEX_ACQUISITION_REPORT.md` §MEASURE 1 table + §AMENDMENT D finding 2 ("literally true and worthless") | Phase-4b MEASURE 1 bindability re-run | canonical 60 | **SUPPORTED** | discussion |
| 3 | **Content parity does not imply extraction parity.** With LaTeX table verbatim survival restored to parity (0.983 vs PDF 0.987) and nothing lost, the 11 LaTeX-retained papers still extracted at mean 5.82 non-empty fields against the PDF baseline's 9.91, at the production 768-token output reservation. | vb-lax after 0.983 / 0.987; RETAINED-11 mean fields 4.73 → 5.82 (Task-2 routing) vs 9.91 frozen PDF baseline. `LATEX_ACQUISITION_REPORT.md` §MEASURE 1, §MEASURE 2 on RETAINED-11, §AMENDMENT D finding 3 | Phase-4b MEASURE 1 + MEASURE 2 | canonical 60 — 11 LaTeX-retained | **SUPPORTED** | results |
| 4 | **Configuration constants tuned on one input distribution fail silently on another.** The 768-token output reservation, set on PDF prose in §3.2b, never fired on PDF input; on structured LaTeX table text it capped generation — the retained-11 subset reaches mean 5.82 fields at 768 versus 9.09 at 4096, with `done_reason == "length"` on 2 papers at 768 and 0 at 4096. | 5.82 @768 vs 9.09 @4096; `done_reason=="length"` 2 → 0; "its first firing anywhere". `LATEX_ACQUISITION_REPORT.md` §TASK 1 (capped 768 vs uncapped 4096) | Phase-4b Task 1 uncapped diagnostic | canonical 60 — 11 LaTeX-retained | **SUPPORTED** | discussion / limitations |
| 5 | **Retrieval delivery and extraction coverage are not proportional.** On the canonical corpus, content-aware selection delivers 16.7 % of anchor mentions to the extractor yet reaches 94 % `results` coverage; on the medical corpus it delivers 13.1 % and reaches 68 % `results` coverage. Most anchor mentions never reach the extractor, and coverage does not track delivery. | canonical delivery 0.167 → `results` 94 %; medical delivery 13.06 % → `results` 13/19 = 68 %. `SELECTION_POLICY_REPORT.md` §MEASURE 1 + §MEASURE 2; `MEDICAL_RECHUNK_REPORT.md` §3.3b; `MEDICAL_SELECTOR_CONTROL_REPORT.md` §Result arm 3 | selection delivery sweep + coverage runs | canonical 60 (34 full-text) and medical 50 (19 full-text), reported separately, never pooled | **SUPPORTED** | results |
| 6 | **Failure modes differ across scientific domains.** Comparing LaTeX-derived structure on CS/NLP papers with JATS-derived structure on biomedical papers: cell binding fired on 0 of 5 returned structured claims (canonical) and 0 of 2 (medical); wrong-cell rejection caught 2 of 6 cross-row probes on canonical and 12 of 13 probes on medical; the case-2 fall-through carried 4 items in each. | canonical vs medical side by side, not pooled. `BINDING_VALIDATION_REPORT.md` §TASK 5 comparison table | Phase-5 binding validation, post-F1 | canonical 60 (13 structured) and medical 50 (11 JATS), side by side | **SUPPORTED** (denominators carried in the wording — every n is below 10) | discussion |

---

## Methodology claims

| # | Claim (exact wording as it will appear) | Evidence (number + report) | Experiment | Corpus | Status | Section |
|---|---|---|---|---|---|---|
| 7 | **Safety invariants can pass on a materially broken system.** Two documented instances: 12 of 12 staging invariants returned `STAGING_PASS` with 0 errors on an ingestion path that had discarded roughly 60 % of table numerics (table verbatim survival 0.388); and invariants 14 and 15, written specifically to catch structural-binding failures, both reported PASS while 3 adversarial probes were being accepted, because both key on `wrong_cell`/`pdf_only` and the acceptances routed through `not_bindable`. | (a) 12/12, `STAGING_PASS`, 0 errors at table vb-lax 0.388 — `LATEX_ACQUISITION_REPORT.md` §Invariant-blindness observation + §AMENDMENT D finding 1. (b) invariants 14/15 PASS with 3 pre-F1 acceptances — `BINDING_VALIDATION_REPORT.md` §"The historical blind spot (F2 — invariant 16)" | Phase-4b parity measurement; Phase-5 binding validation | canonical 60 (a); medical 50 + canonical 60 (b) | **SUPPORTED** on two cited instances | discussion |
| 7b | *Instance not carried:* "15/15 invariants passed on the pre-5b binding gap." | No number for this instance appears in any of the twelve available nominated reports; it is documented in `STRUCTURAL_BINDING_REPORT.md`, which is not in the source set. | — | — | **UNSUPPORTED** within the nominated sources — do not cite until `STRUCTURAL_BINDING_REPORT.md` is added to the source set | — |
| 7c | *Instance not carried:* "a suite reported as 37/37 tests that was actually 6." | The corrected figure is citable (`tests/test_pipeline.py` 6/6 — `SELECTION_POLICY_REPORT.md` §Tests, `CONTEXT_BUDGET_REPORT.md` §Tests), but the superseded "37/37" claim appears only in `FINAL_REPORT.md` / `STAGING_VALIDATION_REPORT.md` / `progress.md`, none of which is in the source set. | — | — | **UNSUPPORTED** within the nominated sources — the miscount cannot be evidenced from a nominated report | — |
| 8 | **Evaluation coverage is not evaluation completeness.** The invariant suite had a route-specific blind spot: invariants 14 and 15 test which internal binding route produced a verdict, so three adversarial acceptances that reached RETURNED via `not_bindable` were invisible to them. Controlled adversarial testing found this, not the suite. Invariant 16 was added on that evidence and tests the final acceptance outcome regardless of route; it now evaluates 37 probes across both domains with 0 acceptances. | 3 acceptances invisible to 14/15; invariant 16 over 37 probes (medical JATS 13, canonical LaTeX 16, cross-row 8), 30 adversarial, 0 accepted; 16/16 PASS. `BINDING_VALIDATION_REPORT.md` §"The historical blind spot (F2 — invariant 16)" + §Tests table | Phase-5 binding validation + invariant-16 re-run | canonical 60 + medical 50, both domains | **SUPPORTED** | discussion |
| 9 | **Mean-over-claims aggregation dilutes single-value errors.** Under a detection criterion fixed before results were inspected, an established automated RAG evaluation framework registered 18 of 19 numeric perturbations at the strict marker but only 6 of 19 crossed the 0.5 majority threshold, where a number-anchored structural check flagged 19 of 19. Across all should-reject mutants the framework detected 31 of 67 against the structural check's 54 of 67, with the gap concentrated in numeric perturbation and support deletion. | 18/19 strict vs 6/19 at threshold vs 19/19 structural; 31/67 vs 54/67; 106 cases, 0 unscored. `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` §Result table + §Outcome item 2 | evaluation-method comparison (`eval_framework_sensitivity.py`; RAGAS 0.2.15 Faithfulness, qwen2.5:7b judge, one fixed configuration) | canonical 60 + data_test 8 + medical 50 — 106 cases, corpus label carried per case, never pooled into a per-corpus rate | **NARROWED** | results |
| 9s | **SUPERSEDED — do not restore:** ~~"conventional aggregate evaluation misses structural evidence failures."~~ | Withdrawn on its own evidence: the cross-row arm did not survive its positive control — only 2 of 8 controls were accepted, so the arm is n = 2, not n = 8, and on those 2 the framework detected 2 of 2. The structural diagnostic fails the same control (1 of 5 canonical, 0 of 2 medical). `EVAL_FRAMEWORK_SENSITIVITY_REPORT.md` §Positive control + §What may not be claimed | same | same | **WITHDRAWN** | — |
| 10 | **Structural binding is sound against crafted attacks and inert on real claims.** After removing an asymmetric-matching confound, cell binding fired on 0 of 5 returned structured claims on the canonical corpus and 0 of 2 on the medical corpus, while 0 of 30 adversarial probes in a 37-probe suite were accepted across both domains. | bound = 0 both domains; 0/30 adversarial acceptances across 37 probes. `BINDING_VALIDATION_REPORT.md` §Headline, §TASK 2 case distribution, §F2 probe table | Phase-5 binding validation, post-F1 | canonical 60 (13 structured) + medical 50 (11 JATS), separate | **SUPPORTED** (denominators carried — every n is below 10) | results / limitations |

---

## Algorithmic contribution

| # | Claim (exact wording as it will appear) | Evidence (number + report) | Experiment | Corpus | Status | Section |
|---|---|---|---|---|---|---|
| 11 | **The parity gate fires on real evidence loss, and it is conservative.** All 12 fallbacks were justified under a criterion pre-registered and committed before measurement (precision 1.00, n = 12): in each, the PDF representation preserved ground-truth numeric-anchor occurrences that the LaTeX representation lost. Precision states why the gate fired, not that discarding the whole representation was proportionate — 4 of 12 fired on an aggregate deficit below 2 %, and one paper preserved 1522 of 1522 table anchors, lost 3 prose occurrences of 71, and was discarded entirely. Prose drove 12 of 12 fallbacks and tables only 4 of 12: the LaTeX loss is in running text (math mode, macros), not in the structured content the path was adopted for. | 12/12 justified, 0 over-triggered, precision 1.00; 4/12 below 2 % aggregate deficit; `f3b06a914702` 1522/1522 table anchors, 3 prose occurrences of 71 lost; splits fired prose 12, table 4, caption 1. Criterion committed at `eeab489` before computation. `PARITY_GATE_PRECISION_REPORT.md` §Result, §Reading | parity-gate precision re-slice (`parity_gate_precision.py`) over the frozen measurement | canonical 60 — 12 arXiv fallbacks | **NARROWED** | results |
| 11s | **SUPERSEDED — do not restore:** ~~"the parity gate accurately identifies inferior representations."~~ | "Accurate" is not measured. Precision 1.00 is measured under one pre-registered criterion; the conservatism profile above constrains it, and 8 of 12 fallbacks discarded a representation whose table survival matched or beat the PDF's. `PARITY_GATE_PRECISION_REPORT.md` §What may not be claimed | same | same | **WITHDRAWN** | — |
| 12 | **We operationalise content retention as an enforced ingestion-time gate with per-document fallback, at numeric-anchor and table-cell granularity.** | The mechanism and its measurement are cited: per-split verbatim survival with zero tolerance and whole-paper fallback, 12/12 justified. `PARITY_GATE_PRECISION_REPORT.md` §DEFINITION + §Result; `LATEX_ACQUISITION_REPORT.md` §MEASURE 1 | parity gate | canonical 60 | **NARROWED** (mechanism supported) | intro / discussion |
| 12s | **SUPERSEDED — do not restore:** ~~"we introduce content-preservation checking for representation substitution."~~ arXiv 2605.30790 measures answer retention as an analytic control. | The narrowing is applied as instructed, but **the prior-art attribution itself is not citable from any nominated report** — no literature survey is in the source set. | — | — | **WITHDRAWN**; the replacement's novelty delta is **UNSUPPORTED** within the nominated sources until the survey is added | — |
| 13 | **We contribute a mutation class for quantitative binding that existing metamorphic relations cannot express.** | The mutation class is cited: cross-row / correct-row-wrong-column / correct-metric-wrong-condition / cross-table substitution, with 0 of 30 adversarial acceptances post-F1. `GATE_SENSITIVITY_REPORT.md` §"Two-significant-token binding rule — cross-row / cross-baseline probe"; `BINDING_VALIDATION_REPORT.md` §TASK 3 | mutation suite + Phase-5 adversarial probes | canonical 60 + medical 50 | **NARROWED** (mutation class supported) | intro / discussion |
| 13s | **SUPERSEDED — do not restore:** ~~"we introduce mutation testing to RAG evaluation."~~ MetaRAG holds that. | The narrowing is applied as instructed, but **the prior-art attribution itself is not citable from any nominated report** — no literature survey is in the source set. | — | — | **WITHDRAWN**; the replacement's novelty delta is **UNSUPPORTED** within the nominated sources until the survey is added | — |

---

## Selection result

| # | Claim (exact wording as it will appear) | Evidence (number + report) | Experiment | Corpus | Status | Section |
|---|---|---|---|---|---|---|
| 14 | **Content-aware selection's isolated contribution on the medical corpus is +16 pp on `metrics` (58 % → 74 %, 11/19 → 14/19) and +26 pp on `results` (42 % → 68 %, 8/19 → 13/19)**, measured against a control arm that holds selection at legacy while pinning the Stage-4 domain prompt variant to the routing content-aware would have produced. The routing component is +11 pp on `metrics` and +5 pp on `results` and is reported separately. | three arms, 19 papers, seeded, clean cache: arm 1 legacy/natural 9/19, 7/19; arm 2 legacy/pinned 11/19, 8/19; arm 3 content_aware/natural 14/19, 13/19. `MEDICAL_SELECTOR_CONTROL_REPORT.md` §Result + §Decomposition | 3-arm routing control (`medical_selector_control.py`) | medical 50 (19 full-text) — never pooled with canonical or data_test | **SUPPORTED** | results |
| 14s | **SUPERSEDED — do not restore as a selection result:** ~~"content-aware selection lifts `metrics` +27 pp and `results` +31 pp on the medical corpus"~~ (and its re-run form, +26 pp / +32 pp). | Confounded: content-aware selection also flipped the Stage-4 domain prompt variant on 5 papers (routing cs_ml 16 / biomed 3 → biomed 8 / cs_ml 11), and the biomed variant is itself a measured gain on clinical papers. The confounded figure is the sum of two components. `MEDICAL_RECHUNK_REPORT.md` §3.3c + caveat 3; `MEDICAL_SELECTOR_CONTROL_REPORT.md` §Defect + §Decomposition | same | same | **WITHDRAWN** — diagnostic history only | — |

---

## Wording adjustments made while building this ledger

- **Claim 3** was specified as *"98 % preserved extracted worse than 39 % preserved."* No nominated
  report states that comparison. The 38 % figure is the **pre-fix denominator collapse** (claim 2),
  not a second extraction arm; the extraction numbers (4.73 / 5.82 vs 9.91) were all measured on
  the **post-fix** 0.983-survival representation. The row above carries the citable form. Writing
  the "98 vs 39" version would fabricate a comparison the data does not contain.
- **Claim 7** was specified with four instances; two are citable from the nominated sources and are
  in the claim wording, two are not and are listed as rows 7b and 7c rather than dropped silently.
- **Claims 12 and 13**: the narrowed wordings are adopted as instructed, but the prior-art
  attributions that justify the narrowing (arXiv 2605.30790, MetaRAG) cannot be cited to any
  nominated report. The narrowing stands — it can only make a claim weaker — but the novelty
  delta must not be asserted until a literature-survey source is added to this ledger.

---

## Abstract-eligible list

The abstract may contain **nothing that is not on this list.** All five are SUPPORTED,
carry a denominator, and survive their own controls. NARROWED claims (9, 11, 12, 13) are
results- and discussion-section material and must not be compressed into the abstract, where
the qualification that narrowed them would be lost.

| # | Abstract-eligible claim | Headline number |
|---|---|---|
| 1 | Value preservation is not evidence preservation. | 98.6 % of 6,530 values survive verbatim, 16.8 % stay context-bindable, 8.9 % in tables |
| 3 | Content parity does not imply extraction parity. | survival restored to 0.983 vs 0.987, extraction still 5.82 vs 9.91 fields |
| 7 | Safety invariants can pass on a materially broken system. | 12/12 invariants PASS at 0.388 table survival; invariants 14 and 15 PASS during 3 adversarial acceptances |
| 8 | Evaluation coverage is not evaluation completeness. | a route-specific blind spot found by adversarial testing, not by the suite; invariant 16 now 0 acceptances over 37 probes |
| 14 | Content-aware selection's isolated contribution, post-control. | `metrics` +16 pp (11/19 → 14/19), `results` +26 pp (8/19 → 13/19) |

**Explicitly not abstract-eligible**, despite being SUPPORTED: claims 2, 4, 5 (discussion-grade
cautions rather than headline results) and claims 6 and 10, whose every denominator is below 10
(0 of 5, 0 of 2, 2 of 6, 12 of 13) — they belong in results/discussion where the denominators
can be shown, not in an abstract where they would read as rates.
