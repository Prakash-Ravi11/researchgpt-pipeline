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
