# Parity-gate precision — are the 12 fallbacks justified?

Branch `claude-code-verification` · 2026-09-04
Six stages unchanged. `configs/` not modified. `latex_ingestion_enabled` stays `false`.
No re-run of acquisition or extraction: this re-slices the **frozen** parity
measurement already recorded on every fallback paper's chunks
(`latex_parity_fallback`, written by `process_paper_grounded` from
`src/evidence/latex_parity.py::check_parity`). Canonical corpus only; not pooled.

Harness: `parity_gate_precision.py`. Detail in `runs/parity_gate_precision/`.

## Why this measurement exists

The parity gate is an algorithmic contribution, and so far it has only been shown
to *fire* (12 of 23 arXiv papers fell back to PDF). That does not answer the
question a reviewer will ask: **does it reject bad representations, or does it
reject aggressively?** This report re-slices those 12 against a criterion fixed in
advance.

---

## DEFINITION — fixed before any number in this report was computed

The implementation states its own rule in `latex_parity.py`:

> *"Every numeric value the PDF path preserves must also survive the LaTeX path."*

The frozen measurement operationalises that as `verbatim_survival`: the fraction of
ground-truth numeric-anchor **occurrences** (taken from the LaTeX body, split into
`table` / `prose` / `caption`, and their union `all`) that appear verbatim in a
representation's block text. The gate falls back when, for **any one split**,
`latex_survival + tolerance < pdf_survival`, with `tolerance = 0.0` (strict).

Applying the required form — *a fallback is justified when representation B fails to
preserve evidence demonstrably recoverable from representation A under the frozen
parity measurement* — with **B = LaTeX** (the candidate) and **A = PDF** (the
baseline):

> ### Criterion J
> A fallback is **JUSTIFIED** iff, under the frozen parity measurement, the PDF
> representation preserves strictly more of the ground-truth numeric-anchor
> occurrences than the LaTeX representation **on the aggregate (`all`) split**:
>
> ```
> justified  ⟺  pdf_survival(all) > latex_survival(all)
> ```
>
> A fallback is **OVER-TRIGGERED** otherwise — that is, when
> `latex_survival(all) >= pdf_survival(all)` and the gate fired on a sub-split
> (`table`, `prose`, or `caption`) alone.

**Why the `all` split is the right test of justification.** The rule's stated
guarantee is about evidence the PDF preserves. Evidence *demonstrably recoverable
from A but not preserved by B* is exactly a document-level deficit: across the whole
paper, PDF recovered occurrences that LaTeX lost. If the aggregate is a tie or
LaTeX-favourable, then taken over the document LaTeX preserved at least as much
recoverable evidence as PDF, and the fallback was caused by a **redistribution
between splits** rather than by net evidence loss. Discarding the representation in
that case is the gate being conservative, not the gate catching a bad
representation.

Both splits are computed over the **same ground-truth occurrence multiset**, so
`pdf > latex` on a split means at least one occurrence is present in PDF and absent
in LaTeX. Criterion J therefore requires real, countable lost evidence — not a
threshold artefact — and it can come out either way on this data.

**Reported alongside, as description, NOT as a second criterion:** the absolute
occurrence deficit on the `all` split,
`lost ≈ round(n_all × (pdf_survival − latex_survival))`. A fallback can satisfy
Criterion J on a single lost occurrence out of several hundred; that is still
justified under the rule, but it is evidence about the gate's *conservatism*, and
suppressing it would overstate the result. No case is reclassified on this number.

**Pre-registered outcome mapping** (fixed before computing, per the task):

| justified / 12 | reading |
|---|---|
| high precision | support for the gate as a practical safety mechanism |
| moderate precision | useful, but the gate must be described as conservative |
| low precision | report it — the gate prevents silent loss but is not yet selective enough for automatic deployment; a legitimate limitation |

The gate will not be described as "accurate" or "optimal" in any case; only the
measured safety and conservatism properties are claimed.

---

## Result

**JUSTIFIED 12/12 · OVER-TRIGGERED 0/12 · precision 1.00** under Criterion J.

Every one of the 12 fallbacks fired on the aggregate (`all`) split. None was
triggered by a sub-split redistribution alone, so in every case the PDF
representation demonstrably preserved ground-truth numeric-anchor occurrences that
the LaTeX representation lost.

| paper | verdict | n GT | `all` latex | `all` pdf | occurrences lost | splits fired |
|---|---|--:|--:|--:|--:|---|
| 141276ba659d | JUSTIFIED | 191 | 0.712 | 0.990 | 53 | all, prose |
| 2009dbb5f290 | JUSTIFIED | 162 | 0.593 | 0.951 | 58 | all, prose |
| 413a184de4b1 | JUSTIFIED | 1817 | 0.928 | 0.943 | 27 | all, prose, caption |
| 4f3fca4c4fa8 | JUSTIFIED | 131 | 0.565 | 0.939 | 49 | all, table, prose |
| 6437463b4b13 | JUSTIFIED | 223 | 0.834 | 0.852 | 4 | all, prose |
| 68f93a5921c1 | JUSTIFIED | 31 | 0.548 | 0.935 | 12 | all, table, prose |
| 81e060664f24 | JUSTIFIED | 71 | 0.606 | 0.775 | 12 | all, table, prose |
| 96285d75a525 | JUSTIFIED | 408 | 0.983 | 0.985 | 1 | all, prose |
| be7c4dc39030 | JUSTIFIED | 151 | 0.960 | 1.000 | 6 | all, prose |
| d3b5f3c050b4 | JUSTIFIED | 63 | 0.682 | 0.841 | 10 | all, prose |
| f3b06a914702 | JUSTIFIED | 1603 | 0.998 | 1.000 | 3 | all, prose |
| fef0393e997e | JUSTIFIED | 322 | 0.839 | 0.894 | 18 | all, table, prose |

### Per-split deficits that triggered each fallback

`latex / pdf` verbatim survival; **bold** marks a split that fired.

| paper | table | prose | caption |
|---|---|---|---|
| 141276ba659d | 1.000/1.000 (n=102) | **0.375/0.977** (n=88) | 1.000/1.000 (n=1) |
| 2009dbb5f290 | 1.000/1.000 (n=35) | **0.472/0.936** (n=125) | 1.000/1.000 (n=2) |
| 413a184de4b1 | 0.994/0.994 (n=681) | **0.880/0.905** (n=1046) | **0.989/1.000** (n=90) |
| 4f3fca4c4fa8 | **0.939/0.970** (n=33) | **0.409/0.925** (n=93) | 1.000/1.000 (n=5) |
| 6437463b4b13 | 1.000/1.000 (n=65) | **0.764/0.790** (n=157) | 1.000/1.000 (n=1) |
| 68f93a5921c1 | **0.474/1.000** (n=19) | **0.667/0.833** (n=12) | — |
| 81e060664f24 | **0.909/1.000** (n=11) | **0.534/0.724** (n=58) | 1.000/1.000 (n=2) |
| 96285d75a525 | 0.983/0.983 (n=348) | **0.982/1.000** (n=55) | 1.000/1.000 (n=5) |
| be7c4dc39030 | 1.000/1.000 (n=79) | **0.915/1.000** (n=71) | 1.000/1.000 (n=1) |
| d3b5f3c050b4 | 0.941/0.941 (n=17) | **0.587/0.804** (n=46) | — |
| f3b06a914702 | 1.000/1.000 (n=1522) | **0.958/1.000** (n=71) | 1.000/1.000 (n=10) |
| fef0393e997e | **0.939/0.944** (n=197) | **0.677/0.815** (n=124) | 1.000/1.000 (n=1) |

**Splits that fired across the 12: `prose` 12, `table` 4, `caption` 1** (plus `all`
12 by construction). **Prose is the sole universal driver.** The LaTeX path's loss
is concentrated in running text — numbers inside math mode and macros in prose —
not in the structured content the path was adopted for.

### Over-triggered cases

**None.** Criterion J had real teeth on this data rather than being satisfied by
construction: `413a184de4b1` fired on `caption` with a deficit of 0.011 over n=90
and on `all` by only 0.015, so a slightly different aggregate would have made it a
sub-split-only trigger and classified it OVER-TRIGGERED.

## Reading — high precision, and a strict, all-or-nothing decision rule

Against the pre-registered mapping, 12/12 is **high precision**: this is
**support for the gate as a practical safety mechanism**. On this corpus it did not
fire once without real, countable evidence loss behind it.

That is a statement about *why* it fired. It is not a statement that each fallback
was the best available action, and the same data constrains that separately:

- **The aggregate deficit is small in a third of cases.** 4/12 discarded the LaTeX
  representation over an aggregate loss below **2 %** of ground-truth occurrences
  (`413a184de4b1`, `6437463b4b13`, `96285d75a525`, `f3b06a914702`); 5/12 below 5 %.
  At the other end, 4/12 lost **≥ 20 %** — the distribution is bimodal, not uniform.
  Occurrences lost on `all`: min 1, median 12, max 58.
- **In 8/12 the structured content was not degraded at all.** LaTeX table survival
  was greater than or equal to PDF table survival in 8 of the 12 papers, and exactly
  equal at 1.000/1.000 in four of them. Those fallbacks discarded a representation
  whose tables were intact, on a prose deficit.
- **The sharpest case is `f3b06a914702`:** LaTeX preserved **1522 of 1522** table
  numeric anchors verbatim (1.000/1.000) and lost **3 prose occurrences out of 71**
  — an aggregate deficit of 0.2 % (3 of 1603) — and the whole representation was
  discarded.

The decision rule that produces this is strict by construction: **any** split,
**zero** tolerance, **whole-paper** granularity. So the measured properties are:

- **Safety:** on this corpus, precision 1.00 — the gate never discarded a
  representation that had not actually lost recoverable evidence. It does what it
  was built to prevent, which is silent loss.
- **Conservatism:** it is a document-level minimum with no tolerance and no
  per-split or per-block granularity, so it also discards representations that are
  intact on the structured content and deficient only in prose. 8 of 12 fallbacks
  are of that shape.

Both properties are measured on **12 fallbacks from one corpus** (canonical 60,
arXiv subset). They are not extrapolated to other corpora, and no claim is made that
the gate is accurate or optimal.

## Threats to validity

- **n = 12, single corpus.** Canonical-60 arXiv papers only. Medical and data_test
  contribute no LaTeX fallbacks and are not pooled in.
- **Criterion J is one defensible operationalisation.** It follows the rule the
  implementation states, but a reviewer could instead define justification per-split
  (in which case all 12 are justified trivially, since a split fired by definition)
  or by a minimum deficit magnitude (which would reclassify the four <2 % cases).
  The criterion was fixed and committed before computation (`eeab489`) precisely so
  the choice could not be made to fit the answer; the deficit magnitudes are
  reported in full so a reader can apply a different one.
- **Ground truth is LaTeX-derived.** The anchor set comes from the LaTeX body, so a
  numeric value present only in the PDF is outside the measurement entirely. The
  measurement bounds LaTeX-vs-PDF loss, not absolute document coverage.
- **`verbatim_survival` is presence-anywhere ("verbatim-lax").** A number counted as
  surviving may be present in the wrong block. This measurement says nothing about
  whether the surviving occurrence is correctly located.

## What may be claimed

- On the canonical corpus, **all 12 parity-gate fallbacks were justified** under a
  pre-registered criterion: in each, PDF preserved ground-truth numeric-anchor
  occurrences that LaTeX lost (precision 1.00, n=12).
- **`prose` drove every fallback** (12/12); `table` 4/12, `caption` 1/12. The LaTeX
  path's weakness on this corpus is running text, not tables.
- The gate is **conservative as well as safe**: 4/12 fired on an aggregate deficit
  below 2 %, and 8/12 discarded representations whose table survival matched or beat
  the PDF's.

## What may not be claimed

- That the gate is "accurate" or "optimal" — neither is measured here.
- That precision 1.00 generalises beyond these 12 fallbacks on this corpus.
- That every fallback was the best available action; Criterion J tests whether real
  evidence was lost, not whether discarding the whole representation was the
  proportionate response.
- Any recommendation to change `DEFAULT_PARITY_TOLERANCE`. The tolerance stays 0.0;
  no alternative threshold was evaluated, and this report proposes none.
