# Parser backend experiment — pre-registration amendments

Amends the pre-registration in `PARSER_BACKEND_REPORT.md` section 1. Written and
committed **before implementation**, and before any treatment-arm result exists.
The control arm (`current`) baseline from D1 is the only outcome seen so far.

Accepted without change: D1, D2, D3, D4, D5, and the section-8 key-set reading.

---

## A1 — P1 amended from a sign to a count

**Was:** `delta_returned > 0`.

**Now:** at least **3 of the 14** movable claims become RETURNED, **drawn from at
least 2 distinct papers**.

Reason. A bare `> 0` lets one claim decide a paper-level conclusion, and with 14
movable items one claim is inside the noise of a single table parsing well. A
count of 3 alone does not fix that here: `ae2768758f9928d50eebd4c945f47ff51e0e6f3b`
holds 4 of the 14 movable claims by itself, so 3 could still come from a single
paper and a single table. The 2-paper requirement is what makes the criterion
robust to a one-paper fluke.

3/14 is about 21%. It is a feasibility threshold, not a rate — see A5.

This is **stricter** than both the original `>= 0` and the amended `> 0`. No
threshold has been loosened.

## A2 — new cap on bucket 3 (`bound_to_other_table`)

**P6:** of the claims that reach `bound`, at most **one third** may be withheld
with `abstain_reason="bound_to_other_table"`.

Reason. `other` is what `classify_table` returns from its **default branch**
(gate.py:380) when it cannot see at least one metric-named column and at least
two distinct row labels. That is precisely the signature of a thin or degraded
grid produced by the new parser — it is a defect of my extraction, not a property
of the paper. Capping it stops the run passing on cells that bound but were
classified into silence.

## A3 — explicit no-cap decision on bucket 2 (`bound_to_ablation_table`)

**No cap.** An ablation caption is a property of the paper, not of the parser: a
claim bound to a genuine ablation table *should* be withheld, and capping that
would be capping correct behaviour.

But the classification is only trustworthy when it fires on the caption. Two
cases are therefore counted and reported separately, and **the split is reported
whether or not the run passes**:

- `ablation` via `_ABLATION_RE` matching the caption or a column header — treated
  as correct.
- `ablation` fired **solely** via `row_has_ablation`, with no `_ABLATION_RE` hit
  on caption or headers — treated as **parser-induced** and reported as a defect
  with the offending row labels listed.

These can only push claims toward ABSTAIN, never toward RETURNED, so they cannot
inflate P1. They are a deflation risk and a credibility risk, not a cheat.

## A4 — the row-label quality gate is NOT extended to reject punctuation labels

D6(c) is real (see V3 below): borderless extraction emits `-` for empty cells, and
two such row labels are enough to classify a whole table `ablation`. The obvious
response is to drop row labels that are pure punctuation.

**Decided against, for this run.** The brief asks for `row_has_ablation`
incidence to be *counted and flagged*. Adding the rule would suppress the very
measurement being asked for, and it is a second single-variable change that would
confound this one. The pre-registered gate from section 1.3 stands unchanged
(empty / contains newline / over 60 chars).

If the count comes back non-zero, the punctuation rule is the natural second
pre-registered run. Recorded here so the decision is visible rather than
discovered later.

## A5 — what this run may and may not be used for

Confirmed and binding: **no percentage from this run enters the paper.** 14
movable claims means one claim moves the headline figure by roughly 7 points.
This is a **feasibility study** — does attaching layout-extracted cells to
PDF-path papers move claims off `pdf_only` at all, and at what cost in
mis-binding. It is not a measured rate, and the report states so in sections 4,
5 and 11.

## A6 — tesseract

Not installed, and will not be. The native no-tesseract arm is the only one run;
it is the Windows story. The with-tesseract arm is reported **UNMEASURED**, with
the reason.

The section-10 priors are **retired**, not compared against: different
`pymupdf4llm` version, different machine, different OCR availability. They are
recorded in the report as the origin of the hypothesis and nothing more.

To be recorded as observed fact, not assumption: which path `pymupdf4llm` 1.28.2
actually takes (`pymupdf_layout` / `onnxruntime` vs tesseract), plus the
installed size and licence of everything the install pulled in. Reproducibility
is a paper claim.

---

## D6 verification — confirmed, with three corrections

### V1 — (a) confirmed exactly

gate.py:539-542:

```python
if sb.get("table_type") in ("ablation", "other"):
    item.update(evidence_status=EXPLICIT, provenance_valid=True, final=ABSTAINED,
                abstain_reason=f"bound_to_{sb['table_type']}_table")
    return item
```

A correctly bound claim is abstained on table type. Departure accounting uses the
five buckets as specified.

### V2 — (b) confirmed, with a correction that makes it sharper

`classify_table`'s default branch (gate.py:380) is
`"results" if (metric_cols >= 1 and len(rows or []) >= 2) else "other"`. The
threshold is as described.

**Correction:** `rows` is not a row count. `_table_type_for` (gate.py:383-387)
passes a **set of distinct row labels**:

```python
{c.get("row_label", "") for c in sib}
```

So `len(rows) >= 2` is *two distinct row labels among surviving cells*. This
makes the hazard worse than stated, in two ways:

- dropping rows reduces distinct labels, exactly as described; and
- a table whose surviving rows share a label collapses to 1 distinct label and
  flips to `other` **without any row being dropped at all**.

**Second correction, recorded not fixed:** the comment on gate.py:377 says
">=2 metric-named columns"; the code on gate.py:380 tests `metric_cols >= 1`.
Comment and code disagree. Not touched — gate.py is out of scope.

**Third hazard, not in the brief:** `_table_type_for` groups sibling cells by
**caption string equality across the whole paper**. Every table whose caption
extracts as `""` pools into one pseudo-table, mixing unrelated row labels and
headers before classification. PDF-path captions come from the table block's
first line, so this is a live risk for the new parser. Caption uniqueness per
paper per arm is recorded.

### V3 — (c) confirmed, with a threshold correction

gate.py:368-370:

```python
row_has_ablation = bool(rows) and sum(
    1 for r in rows if _ABLATION_RE.search(r or "") or (r or "").strip().startswith(("-", "−", "w/o"))
) >= max(2, len(rows) // 3)
```

**Corrections:** the prefix set is `("-", "−", "w/o")` — `w/o` as well as the two
dashes. And it needs **at least 2** such labels (`max(2, ...)`), not one. A single
`-` row is harmless; two are enough to classify the table `ablation` and abstain
every claim bound to it.

**Related hazard, same function:** `_ABLATION_RE` matches `\bvs\.?\b` and
`\bversus\b`, and is tested against caption + headers + row labels joined. A
plain results table captioned "Method A vs. Method B", or carrying a "vs" header,
classifies as `ablation`. Counted in the same breakdown as V3.

### V4 — (d) accepted as specified

Per table per arm: caption, column headers, row labels, resulting `table_type`.
These are the classifier's only inputs and are recorded verbatim so the
classification is auditable.

---

## Recording requirements added to `results.json`

Per table, per arm, in addition to section 9 of the brief:

| field | why |
|---|---|
| `rows_before_gate`, `rows_after_gate` | D6(b) — the drop that flips the type |
| `table_type_before`, `table_type_after` | D6(b) — computed on pre-gate and post-gate cells; a transition is recorded, never silently applied |
| `caption`, `column_headers`, `row_labels` | D6(d) — the classifier's inputs |
| `ablation_trigger` | one of `caption_or_header` / `row_has_ablation_only` / `null` — A3, V3 |
| `caption_collision` | true when another table in the same paper/arm shares this caption string — V2 |

Per claim, `claims_flipped` carries `from_status` -> `to_status` plus the final
verdict bucket of the five in D6(a), so a `bound` that ends ABSTAINED on table
type is never counted as a win.

## Unit test added for D6(b)

Beyond the ten in section 8: a table with **3 data rows before the gate and 1
after**, asserting that `rows_before_gate=3`, `rows_after_gate=1`, and that
`table_type_before` / `table_type_after` are both recorded on the block — i.e.
the `results` -> `other` transition is visible in the artifact rather than
silently applied.

## Implementation reading that needs no ruling but is written down

Section 7 lists a three-tier fallback but names two arms. The only reading where
the arms differ and the tiering is still per-table:

- arm `pymupdf_tables` — tier 1 (`page.find_tables()`) only, then `fallback_pdf`.
- arm `pymupdf4llm` — tier 1, then tier 2 (markdown pipe tables), then
  `fallback_pdf`.

Both arms reuse `blocks_from_pdf`'s block stream verbatim and only *add*
`table_cells` to table-typed blocks, so chunk text stays byte-identical across
all three arms. That is what makes P2 a valid wiring check.

---

# Amendments to the measurement design (A-F)

Committed before the measurement runs.

## A — within-paper contamination: option (ii), with enforcement

**Chosen: (ii), enforced ordering.**

Every tier-1 (`find_tables`) decision for a paper is taken and cached **before**
any tier-2 (`to_markdown`) call, and `_tier1_grids` now raises `RuntimeError` if
`pymupdf4llm_invoked()` is already true. A violation stops the run instead of
silently corrupting an arm.

Why (ii) over (i):

- The ordering (i) would buy is **already what the code does** within a paper —
  the tier-1 loop completes over all pages before `_tier2_page_markdown` is
  called even once. (i) would add process starts without changing a single
  decision.
- (i) costs 21 x 4 x 2 = 168 executions against 63 for (ii), and per amendment F
  every `pymupdf4llm` process start loads the ONNX layout model. (i) pays that
  toll to enforce an ordering that an `assert` enforces for free.
- The assert converts an incidental property into a checked invariant, which is
  the actual gap — the ordering was correct but unguarded.

Combined with **one paper per process**, the across-paper case in A is also
closed: paper 2's tier-1 calls can no longer follow paper 1's `to_markdown`,
and if they ever did, the run stops.

`_tier1_grids(..., allow_contaminated=True)` exists solely for the test that
pins the leak; nothing in the measurement path passes it.

## B — the (a)/(b)/(c) question, answered as a finding

**Before this amendment the answer was (c) within a paper and (b) across
papers.**

- Within one `blocks_from_pdf_layout` call: **(c), already ordered safely.** All
  tier-1 calls precede the single tier-2 call, by construction of the function.
- Across papers in one process: **(b), unguarded and actually wrong.** Paper 2's
  `find_tables` calls would have run after paper 1's `to_markdown`, returning
  phantom grids with corrupted values, and nothing would have complained.
- Worse, the tier-1 call site sat inside `except Exception`, so had the guard
  existed it would have been **swallowed and recorded as a per-page parse
  error** — an arm silently degraded and logged as ordinary data trouble.

After this amendment: **(a), asserted at runtime**, with `RuntimeError`
re-raised past the page-level handler. Two regression tests cover it
(`test_13`, `test_14`).

This is reported in the results write-up as a finding, not only as a fix.

## C — multiple comparisons

Recorded verbatim, and repeated in the report:

> This run SELECTS a candidate, it does not validate one. No arm may be reported
> as "the" backend on the strength of this run. Confirmation requires a second,
> separately pre-registered run on the selected arm.

Three candidate arms are evaluated against one threshold on 14 movable claims.
With that many comparisons and that little data, the arm that scores best is the
arm that got luckiest as readily as the arm that is best.

## D — P1 is evaluated per arm

Each arm passes or fails **independently**; no aggregate verdict is reported.
All four outcomes are stated:

| arm | tesseract | outcome |
|---|---|---|
| `pymupdf_tables` | off (native) | measured |
| `pymupdf4llm` | off (native) | measured |
| `pymupdf_tables` | on | UNMEASURED — not installed, per A6 |
| `pymupdf4llm` | on | UNMEASURED — not installed, per A6 |

`current` is the control and is reported alongside as the baseline, not as a
fourth candidate.

## E — retained from the original brief

Unchanged and binding: failures recorded as `null` plus the exception string and
never swallowed; no number written that was not computed; `UNMEASURED` stated
wherever it applies; the section-12 report section order; and **STOP after the
report** — no wiring into `build_document()`, no config flag, no
`requirements.txt` change, no merge.

## F — expected cost

63 subprocess executions (21 papers x 3 arms), of which the 21 `pymupdf4llm`
ones each load the ONNX layout model. The brief's estimate of 84+ assumes four
configurations; there are three, because the two with-tesseract arms are
UNMEASURED rather than run.

Total wall time is measured and reported, so the runtime figure in the report is
observed rather than estimated.

---

# Experiment 2 — header-newline normalization

Pre-registered before corpus execution. One controlled run against the same
frozen canonical corpus and the same `pymupdf4llm` configuration.

## 2.0 Correction to the section-12 interpretation, which motivates this run

The "parser-side ceiling" label from the section-12 diagnostic was **an artifact
of the pre-registered category rule**, and is withdrawn as an interpretation.

The rule summed categories 1+2+3 and called the total "parser-side". But
category 2 (`FIND_TABLES_EMPTY`) was **zero**, and category 3
(`QUALITY_GATE_DROPPED_ALL_ROWS`) was **6 of 9 claims** — tables where a
structured grid *did* exist and was discarded by the experimental quality gate.
Lumping gate suppression together with table unavailability and labelling the sum
"parser-side" obscured the dominant cause.

The three causes must be distinguished:

| cause | claims | detail |
|---|---|---|
| **parser / table availability** | 3 | 2 papers with no table block at all |
| **quality-gate suppression** | 6 | 2 papers; grids existed and were discarded — 4 claims by the newline-in-header rule, 2 by `too_few_data_rows` on genuinely single-row qualitative tables |
| **downstream binding failure** | (separate population) | the 2 `wrong_cell` + 3 `not_bindable` claims of section 4 |

The measurements in sections 3-12 stand unchanged; only the label is corrected.

**Section 9 did not demonstrate that layout-aware parsing does not help.** It
demonstrated that under *this* quality-gate configuration nothing bound. The
dominant single blocker among the untouched claims was a rule I wrote, not the
parser.

## 2.1 Hypothesis

> Legitimate intra-cell line wrapping in table headers is being incorrectly
> rejected by the quality gate. Collapsing header whitespace may allow correctly
> parsed tables to reach structural binding.

## 2.2 Prediction

> The known 3x5 table containing `Tempo\n(sem cache)`
> (`ae2768758f9928d50eebd4c945f47ff51e0e6f3b`, table block `:19`, page 3) will
> survive the quality gate, making the associated four movable claims
> measurable.

**"4 claims become measurable" is the prediction. It is NOT a prediction that
four claims will bind or return.** Success is not defined as "four claims became
measurable"; the outcomes in 2.4 are reported as they fall.

Secondary prediction, stated so the frozen rules can be seen to still bind: the
**second** affected table (`fef0393e997e`, block `:406`) will **still be
rejected**. Its header `col1` is a 150-character reference question, so once the
newline check no longer fires, the frozen `MAX_COL_HEADER_CHARS = 40` rule
rejects it as `header_too_long`.

## 2.3 The single variable

| | control (section 9, recorded) | treatment |
|---|---|---|
| header cell contains a newline | **reject the whole table** | **do not reject**; collapse intra-cell whitespace (`Tempo\n(sem cache)` -> `Tempo (sem cache)`), preserving semantic content |

Collapse is applied to header cells before the remaining header checks, so a
header that is only whitespace still fails the frozen non-empty rule, and an
over-long header still fails the frozen length rule.

**Frozen, unchanged:** row-label newline rejection; row-label length limits;
header non-empty rules; column-count checks; `MIN_DATA_ROWS` / `MIN_COLUMNS`;
colspan handling; value-field newline behaviour; `_SUBJECT_RE`; `_OWN_ROW`;
`classify_table`; structural binding; grounding; claim extraction; parser and
backend; `pymupdf4llm` configuration (`table_strategy="text"`); subprocess
isolation; corpus; every threshold; adversarial evaluation; every other
quality-gate rule.

Implemented as a new arm label `pymupdf4llm_hdrnorm` = the `pymupdf4llm` backend
plus `collapse_header_ws=True`. The section-9 code path is left intact and
reproducible; the flag defaults to the section-9 behaviour.

## 2.4 Primary outcomes

Counted over the same numeric metrics/results claim population:

1. claims reaching genuine `bound`
2. claims reaching `RETURNED`
3. claims reaching `wrong_cell`
4. claims reaching `not_bindable`
5. claims remaining `pdf_only`

Plus all transitions relative to the section-9 baseline, and all five departure
buckets of D6(a).

## 2.5 Safety, unchanged

- Invariant 14: 0 cross-row acceptances (no RETURNED claim with `wrong_cell`).
- Invariant 15 (parenthetical reading): nothing RETURNED from a `pdf_only` or
  `wrong_cell` binding.
- Any newly introduced `wrong_cell` binding or rejection is listed individually.
- The `structural_binding_measure.py` adversarial probe suite runs on LaTeX/JATS
  structured papers and is **not affected** by this change, which touches only
  PDF-path header handling. It is not re-run; that is stated rather than implied.
- No safety criterion is weakened.

## 2.6 Comparison

CONTROL = the section-9 recorded `pymupdf4llm` result, read from
`runs/parser_backend/results.json`. **Not recomputed, not redefined.**
TREATMENT = identical run with only the header-newline behaviour replaced.

## 2.7 Naming, fixed

`table_blocks = 160` — total table blocks entering the backend population.
`backend_grid_returns = 142` — grids returned by the backend before the gate.
`post_gate_cell_tables = 92` — tables surviving the gate with attached cells.

`92` is never called "backend grid output".

## 2.8 A limit of the section-9 artifact, stated in advance

`_reject_header` returns on the **first** failing rule, so the section-9 record
shows only that first reason. Whether a table was rejected *solely* because of a
header newline is therefore **not knowable from the control artifact** — it is
knowable only from whether that table survives the treatment run. The count of
"tables previously rejected solely because of header newline" is reported after
the run, from the treatment outcome, not asserted from the control.

## 2.9 Interpretation, fixed in advance

The four known claims are not assumed to bind. Any of these may occur and is
reported as it falls:

- **A.** several become `bound` and/or `RETURNED`
- **B.** they reach structural binding and become `not_bindable`
- **C.** they reach structural binding and become `wrong_cell`
- **D.** they are blocked by another unchanged quality or classification rule

If they reach structural binding and fail there, the exact downstream mechanism
is identified.

Neither F1 nor F2 is implemented in this run.
