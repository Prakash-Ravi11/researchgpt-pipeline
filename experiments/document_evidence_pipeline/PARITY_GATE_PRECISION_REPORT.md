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

<!-- RESULTS APPENDED BELOW AFTER COMPUTATION -->
