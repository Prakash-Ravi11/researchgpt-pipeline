# Layout-aware PDF table backend — experiment report

**Status: STOP POINT 1 (pre-registration). No implementation code written yet.**

Worktree `../rgpt-exp-parser`, branch `exp/parser-backend`, forked from `09fbc95`.
The original working directory has not been checked out, moved, or modified.

---

## 0. Discrepancies found while confirming section 4 — read before approving

Everything in section 4 of the brief was confirmed correct except where noted.
Five findings, in descending order of impact on the experiment's design.

### D1 — the stated backfire cannot happen; the primary PASS criterion is a tautology

The brief (section 5) says:

> today a PDF claim gets `pdf_only`, falls through grounding + attribution, and
> can still be RETURNED.

It cannot. `gate.py` `_gate_value` (line 528-531) returns immediately on the
PDF-only branch:

```python
sb = structural_bind(value, chunks)
item["structural_binding"] = sb
if not sb["structured"]:                       # case 1 — PDF-only
    item.update(evidence_status=UNSUPPORTED, final=ABSTAINED,
                abstain_reason="unverifiable_binding")
    return item
```

`pdf_only` is a terminal ABSTAIN, not a fall-through. This is deliberate and
enforced: `STRUCTURAL_BINDING_REPORT.md` invariant 15,
`no_own_quantitative_from_unverifiable_binding`, states that *every* RETURNED
numeric quant claim must have `structural_binding.status == "bound"`.

Measured on the 21 PDF-path canonical papers (read-only probe, real
`gate_paper`, current `blocks_from_pdf`):

| | count |
|---|---|
| numeric metrics/results evidence items | 22 |
| reach `structural_bind`, get `pdf_only` -> **ABSTAINED** (`unverifiable_binding`) | **14** |
| never reach `structural_bind` (no numeric anchor) | 8 |
| **currently RETURNED** | **3** |

The 8 that skip binding do so because `_gate_value` guards the call with
`_NUMVAL.search(value)`, and `_NUMVAL` is `NUMERIC_ANCHOR_RE` =
`\d+\.\d+|\b\d{2,}\b` (anchors.py:27) — a claim whose only digits are single
digits has no anchor. Those 8 go straight to grounding + attribution: 3 RETURNED,
2 `evidence_span_not_found_in_paper_chunks`, 3 `ownership_unverified`.

Consequence for the experiment:

- The 3 currently-RETURNED items never touch `structural_bind`, and whether
  `_NUMVAL` matches depends only on the claim string (from the frozen extraction
  cache, identical in every arm). Under the section-7 design — reuse
  `blocks_from_pdf`'s block stream verbatim and only *add* `table_cells` — chunk
  text is byte-identical across arms, so grounding and attribution are identical
  too. **These 3 cannot flip.**
- The 14 movable items are **already abstained**. They can only stay abstained or
  become returned.

Therefore `delta_returned >= 0` is **guaranteed by construction and cannot
fail**. It is not a criterion; it is an identity. Pre-registering it as the PASS
gate would be pre-registering a result.

The real risk in this codebase is the inverse of the one described, and it is
harder to see: attaching cells moves `pdf_only` -> `wrong_cell`, the cell count
and the "structurally bound" coverage figure both rise, **and RETURNED stays at
3**. The paper could then report improved binding coverage from a change that
returned nothing new and merely relabelled one abstention as another. Section 4
of this report must therefore lead with `delta_returned`, and the PASS criterion
must require it to be *strictly positive*.

### D2 — `data/pdfs/` is the wrong corpus and has zero overlap with the claims

Section 9 says input is `data/pdfs/`, and also says to run `gate_paper` on "the
same extraction cache and claims that `structural_binding_measure.py` uses".
These are incompatible.

`structural_binding_measure.py:34-36` reads from the frozen canonical run:

```python
CANON = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CACHE = CANON / "processed" / "extraction_cache.json"
META  = CANON / "raw_metadata" / "collected_papers.json"
```

- `data/pdfs/` holds 130 PDFs (the live app store).
- `canonical/pdfs/` holds 34 (32 PDF + 2 JATS XML).
- **Overlap: 0 paper ids.**

None of the 130 live PDFs has an extraction-cache entry, so none has any claim
for `gate_paper` to gate. Measuring on `data/pdfs/` would produce zero evidence
items in every arm. The corpus must be the canonical one.

### D3 — the worktree does not contain the corpus

`experiments/document_evidence_pipeline/.gitignore` ignores `runs/`, and the root
`.gitignore` ignores `data/pdfs/`, `data/processed/`, `data/raw_metadata/`. The
frozen canonical corpus, the extraction cache and the chunk cache are therefore
untracked and **absent from the worktree**.

The measurement will read them read-only, by absolute path, from the original
working directory, and write only into the worktree's `runs/parser_backend/`.
Nothing is copied into or out of the original tree. The report records the
absolute source path so the run is reproducible.

### D4 — section 6's `n = 10` discards most of the informative corpus

The movable population is 14 claims, held by exactly **8** of the 21 PDF-path
papers:

| paper | `pdf_only` claims |
|---|---|
| `1016250721201821285c39eba5ab77eddf80812e` | 1 |
| `6437463b4b13b7cc1cc75f3a9bfce4e2281ed79d` | 2 |
| `68f93a5921c1c6bbc5e0032f87366e46a06fded0` | 2 |
| `78797b71788ba1c852407d6010e8454f7b95f0b5` | 2 |
| `ae2768758f9928d50eebd4c945f47ff51e0e6f3b` | 4 |
| `be7c4dc39030508deb495c9f689526ca1b4289cf` | 1 |
| `c093b845f68ee02f440f80ec911220395ba5f904` | 1 |
| `e6f1d66c34b525dc480ced9902cf46419b6a37fa` | 1 |

The other 13 PDF-path papers contribute nothing to the primary metric. A random
10-of-21 sample would capture ~3.8 of the 8 informative papers in expectation.
There is no cost argument for sampling: 21 papers x 3 arms is a cheap run.
**Pre-registered below as a census of all 21**, which eliminates sampling error
entirely.

Even at n=21 the experiment is underpowered: 14 movable claims means the
resolution of `delta_returned` is one claim, roughly 7 percentage points. The
report states this rather than dressing 14 up as a sample.

### D5 — "any empty header rejects the whole table" would reject almost every real table

Scientific tables conventionally leave the **top-left corner cell blank** — it
sits above the row-label column. In `_jats_table_cells` that cell is harmless by
construction: column 0 holds the row label, and the `val != row_label` test
(represent.py:237) already skips it, so `header[0]` is never used to bind
anything.

Applied literally, section 7's "any empty header -> reject" discards every table
with a blank corner, which is the normal case. Pre-registered below as: **the
first header cell may be empty; every other header cell must be non-empty.** An
empty header over a *data* column is the dangerous one and still rejects the
whole table.

### Confirmed exactly as stated in section 4

- `build_document` at represent.py:424, dispatching to
  `blocks_from_jats` / `blocks_from_latex` / `blocks_from_pdf`. OK
- `blocks_from_pdf` at represent.py:144; types a block `table` iff
  `first_line.lower().startswith("table ")`; attaches no `table_cells`. OK
  (Measured on this corpus: 0 cells on all 21 PDF-path papers.)
- `structured_table()` / `table_cell()` in schema.py:122 / :156. OK
- `_jats_table_cells` at represent.py:185 — `<tr>/<th>/<td>` with
  colspan/rowspan; `header = expand(rows[0])`; `row_label` is the first spanning
  cell in each row; `len(rows) < 2` -> `fallback_pdf`; skips cells whose value
  equals the row label. OK. Hardcodes `representation="jats_xml"` in exactly
  three places: lines 194, 200, 240. OK
- `paper_table_cells` at gate.py:273. OK
- `structural_bind`: no cells -> `{"structured": False, "status": "pdf_only"}` at
  gate.py:434-435. OK. Status `wrong_cell` -> ABSTAIN `binding_wrong_cell` at
  gate.py:532-535. OK
- Experiment conventions (`<name>_measure.py`, `runs/<name>/`,
  `<NAME>_REPORT.md`, sys.path bootstrap). OK

Two cosmetic line-number drifts, noted only for accuracy: the chunker's copy of
`table_cells` is at chunker.py:50-51 (line 49 is the comment above it), and
`structural_bind`'s `def` is at gate.py:391 (390 is blank).

### One spec conflict in section 8 that needs a ruling

Test 8 asks that blocks from `blocks_from_pdf_layout` have **the same key set**
as `blocks_from_pdf` (set equality), but section 7 requires recording
`layout_backend`, `table_parse_status`, `table_fallback`, `table_caption` and
drop counters **on every table block**. Both cannot hold for table blocks.

Pre-registered reading: **exact set equality for every non-table block**, and for
table blocks, the `blocks_from_pdf` key set plus exactly the documented extras
and nothing else. This keeps the arms comparable where it matters (the prose
stream) while still carrying the cells. Flagged rather than silently loosened.

---

## 1. Pre-registration

Fixed before any implementation code and before any treatment-arm result. The
control arm (`current`) was measured first and is reported in D1 — a baseline is
what a delta is measured against, and without it the criterion below could not be
stated. **No `pymupdf_tables` or `pymupdf4llm` output has been produced or
inspected at the time of writing.**

### 1.1 Row-label quality gate thresholds

| constant | value | rationale |
|---|---|---|
| `MAX_ROW_LABEL_CHARS` | **60** | `_SUBJECT_RE` (gate.py:266) caps a claim subject at 34 chars. A row label past 60 is a wrapped paragraph fragment, not a label, and `_row_matches_subject` would token-match it by accident. |
| `MAX_COL_HEADER_CHARS` | **40** | Column headers are short metric names. Past 40 chars the cell is a merged or wrapped header, and `_col_matches_metric` would match a metric token belonging to a different column. |
| `MIN_DATA_ROWS` | **2** | `_jats_table_cells` requires only `len(rows) >= 2` (1 header + 1 data). 2 data rows is stricter and is the **detector for the known `find_tables` borderless failure** in section 10, where all 5 data rows collapse into 1. A 1-data-row grid is exactly what that bug produces. |
| `MIN_COLUMNS` | **2** | Header must have >= 2 columns (a row-label column + >= 1 data column). Below that there is nothing to bind against. |

### 1.2 Whole-table rejection (-> `parse_status="fallback_pdf"`, `cells=[]`)

Reject the entire table if **any** holds:

1. header has fewer than `MIN_COLUMNS` (2) cells;
2. **any header cell other than the first** is empty or whitespace-only
   (see D5 — the first cell is the row-label corner and may be blank);
3. any header cell contains a newline;
4. any header cell exceeds `MAX_COL_HEADER_CHARS` (40);
5. fewer than `MIN_DATA_ROWS` (2) data rows after the header.

A bad header mis-binds every row beneath it, so the whole table goes.

### 1.3 Individual row drops (table kept, row emitted in no cell)

Drop a data row if its `row_label` is empty, contains a newline, or exceeds
`MAX_ROW_LABEL_CHARS` (60). A dropped row is safe: its values then appear in no
cell, and `structural_bind` case 5a falls through to grounding rather than
mis-binding.

No degraded cell is ever emitted to raise the count.

### 1.4 PASS criterion

All five must hold, for at least one of the two treatment arms, on the census:

- **P1 (PRIMARY).** `delta_returned > 0` — strictly. At least one of the 14
  currently-`pdf_only` claims becomes RETURNED. Stated strictly because
  `delta_returned >= 0` is an identity under this design (D1) and cannot fail.
- **P2.** `delta_returned >= 0` on metrics+results across the census — retained
  verbatim from the brief, and recorded as **verification that the harness is
  wired correctly**. A negative value here means the arms differ in chunk text,
  i.e. the implementation violated section 7's "same block dicts" rule. It is a
  correctness check on the experiment, not a finding about the hypothesis.
- **P3.** At least **4 of the 8** papers holding `pdf_only` claims have every one
  of their `pdf_only` claims leave that status (to any other status).
- **P4.** Adversarial rejection unchanged: 0 cross-row acceptances (invariant 14)
  and no RETURNED numeric quant claim with binding status other than `bound`
  (invariant 15), in every arm.
- **P5 (backfire guard).** Of the 14 claims that leave `pdf_only`, **at most one
  third land in `wrong_cell`**. A majority landing in `wrong_cell` means the row
  labels are garbage and the gate is rejecting on bad evidence — cells up,
  returns flat.

### 1.5 FAIL criterion

Any of: `delta_returned <= 0` in both treatment arms (P1); or `delta_returned <
0` in either arm (P2 — implementation bug, run is void); or fewer than 4 of the 8
papers fully leaving `pdf_only` (P3); or any adversarial acceptance (P4); or more
than one third of departures landing in `wrong_cell` (P5).

A FAIL is reported as a FAIL. No threshold is moved afterwards. If a threshold
turns out to have been wrong, that is written up as a finding and a second
pre-registered run is proposed.

### 1.6 The sample

**Census, not a sample: all 21 PDF-path papers** in the frozen canonical corpus
`experiments/document_evidence_pipeline/runs/prodab-20260902T004416Z/canonical/`,
i.e. every paper whose `runs/latex_ingestion/reps.json` representation is `pdf`
or `pdf(fallback)`. Deviates from section 6's `n = 10` for the reason in D4;
n = 21 is a superset of any n = 10, so a 10-paper subset can be recomputed from
the same results if required.

Of the 21, **8 are informative** for the primary metric (they hold all 14 movable
claims); the other 13 can move cell counts and binding coverage but not
`delta_returned`. Both figures are reported separately.

### 1.7 Arms

`current` (`blocks_from_pdf`), `pymupdf_tables` (`page.find_tables()` first),
`pymupdf4llm` (markdown pipe tables first). Each arm runs twice, with and without
tesseract on PATH.

---

## Sections 2-11

To be written after the measurement. Report structure follows section 12 of the
brief.
