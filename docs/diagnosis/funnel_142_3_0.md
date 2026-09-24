# Diagnosis — the 142 → 3 → 0 funnel

Every number is `[measured]` from the instrumented run, or `[derived]` by arithmetic from
measured numbers. No pipeline logic was changed; defects are recorded, not fixed.

| | |
|---|---|
| worktree | `C:\Users\Praka\Downloads\rgpt-exp-parser` |
| branch / HEAD at pre-flight | `exp/parser-backend` · `92a745520290de8415da063315c5808714272ada` |
| harness wrapped | `experiments/document_evidence_pipeline/parser_backend_measure.py::run_one` |
| arm measured | `pymupdf4llm` (the brief's "Control") |
| corpus | the 21 PDF-path papers of `runs/prodab-20260902T004416Z/canonical/`, read read-only by absolute path |
| claims | read verbatim from the frozen Stage-4 extraction cache; **no LLM call occurs anywhere in this path**, so temperature is not a parameter of this run |
| pre-flight tests | 41 passed / 0 failed |
| artifacts | `out/trace_on/{trace.jsonl, counts.json, results.json, run_metadata.json, output_hashes.json}`, `table_ledger.csv`, `claim_ledger.csv`, `ledger_assertions.json` |
| stage definitions | `diagnostics/funnel/STAGE_DEFINITIONS.md` |

> **The framing correction that governs this whole report.** "142 → 3" is not one funnel.
> **142 counts tables. 3 counts claims.** No item travels between them and no conservation law
> connects them, so there is no set of "139 removed grid returns". There are two funnels that
> touch at exactly one point — the cells produced by the table funnel are the candidate pool the
> binder searches. Both are reported below, and the join between them is measured in the 2×2.

---

## 1. No-op check

Three full 21-paper runs of the same arm: `baseline` (no trace layer loaded), `trace_off`
(trace layer loaded, flag off), `trace_on` (flag on, all three probes installed).

All 14 count fields are identical across all three runs `[measured]`:

| field | baseline | trace_off | trace_on |
|---|--:|--:|--:|
| papers / parse_ok | 21 / 21 | 21 / 21 | 21 / 21 |
| table_blocks | 160 | 160 | 160 |
| backend_grid_returns | 142 | 142 | 142 |
| post_gate_cell_tables | 92 | 92 | 92 |
| fallback_pdf_tables | 68 | 68 | 68 |
| attached_cells | 2187 | 2187 | 2187 |
| rows_dropped | 45 | 45 | 45 |
| returned_metrics | 3 | 3 | 3 |
| returned_results | 1 | 1 | 1 |
| successful_bindings | 0 | 0 | 0 |
| claims_total | 22 | 22 | 22 |
| claims_entering_binder | 14 | 14 | 14 |
| binding_status_counts | `pdf_only 9, no_binding_call 8, not_bindable 3, wrong_cell 2` | identical | identical |

Canonical `results.json` digest, volatile fields (`wall_seconds`, `peak_rss_mb`) excluded,
identical in all three `[measured]`:

```
df9de82f3eee02eac6c05c62123cfafef167c87b75684ed8e1c0c628777b943d
```

`trace.jsonl` is 2,106 rows / 1,331,965 bytes
(sha256 `414e36e766a6ea64fa4e51244d95feb7ce1350a0d43cdff2b22cd9b7c2dde446`) — under the 5 MB
threshold, so it is committed rather than ignored. Unit proof of the same property:
`tests/diagnostics/test_funnel_trace_noop.py`, **13 passed**, including that `emit()` with the
flag off creates neither the file nor its parent directory, and that nothing in `src/` imports
the diagnostic module.

Post-flight test suite: **54 passed / 0 failed** — the 41 pre-flight tests unchanged
(`test_anchors` 9, `test_pipeline` 6, `test_represent_layout` 26) plus the 13 new no-op tests.
No pipeline file was modified: the only tracked non-diagnostic change in the working tree is the
`funnel_trace_enabled: false` flag added to `configs/staging_config.yaml`.

**PASS.** The instrumentation did not perturb the pipeline.

### Conservation

`out/trace_on/funnel.csv`. Within-stage conservation (`in = out + dropped`) holds at **every**
stage: **0 violations**. Cross-stage, chain A (table blocks → grid returns → cell tables):
**0 violations**. **`UNATTRIBUTED` drops across the whole trace: 0.**

Chain B reports two cross-stage deltas, both by construction rather than data loss, and named
here so they are not mistaken for leaks: the `B4_binding` and `B5_result` stages emit one row per
claim for all 22 claims, including the 8 that never entered the binder, so `B4_binding` receives
22 where `B2_enters_binder` kept 14 (+8), and `B5_result` receives 22 where `B4_binding` kept 0
(+22). Both deltas are exactly the populations named in section 3.

One defect in this diagnostic's own trace layer was found and fixed before the final run:
`_emit_tables` skipped row emission for tables that passed the quality gate but then produced no
cell, undercounting row drops as 37. Corrected, the row stage reports **37 on the cell-table path
+ 8 on the fallback path = 45**, reconciling with `rows_dropped = 45`.

---

## 2. Table ledger summary

`out/trace_on/table_ledger.csv`, one row per table block (160 rows).

`grid_returned` is taken from the `no_grid_from_backend` fallback string, **not** from
`n_tables_with_grid` — see defect D-1.

```
160 table blocks
 −18  NO_GRID_FROM_BACKEND          the backend returned no grid at all
=142  backend grid returns                                        [measured]
 −46  whole-table quality-gate rejections
 − 4  passed the gate, then produced no cell in _layout_table_cells
= 92  cell tables                                                 [measured]
      68 fallback = 18 + 46 + 4                                   [derived]
```

All reconciliation assertions pass `[measured]`:

| assertion | got | expected |
|---|--:|--:|
| rows | 160 | 160 |
| grid_returned | 142 | 142 |
| no-grid | 18 | 18 |
| grid returns producing no cell table | 50 | 50 |
| … of which whole-table gate rejections | 46 | 46 |
| … of which post-gate parse losses | 4 | 4 |
| fallback | 68 | 68 |
| no-grid + no-cell-table grids = fallback | 68 | 68 |
| cell tables | 92 | 92 |
| attached cells | 2187 | 2187 |

**One clarification to the brief's arithmetic.** The brief expected "gate-rejected grids = 50".
50 is correct as *grid returns that produced no cell table*, but only **46** of those are
whole-table gate rejections; the other **4** passed the gate and died later, inside
`_layout_table_cells` (`represent_layout.py:76-79`, `PARSE_TOO_FEW_ROWS`). The aggregate is
asserted and the split is reported rather than merged.

### Why the 50 died, by reason code `[measured]`

| reason code | n | condition | line |
|---|--:|---|---|
| `GATE_TOO_FEW_DATA_ROWS` | 21 | raw grid has < 3 rows | `represent_layout.py:183-186` |
| `GATE_EMPTY_HEADER_CELL` | 17 | a header cell other than the first is blank | `:146-148` |
| `GATE_HEADER_TOO_LONG` | 6 | a header cell exceeds 40 chars | `:155-156` |
| `PARSE_TOO_FEW_ROWS` | 4 | header + 0 data rows survive | `:76-79` |
| `GATE_HEADER_NEWLINE` | 2 | a header cell contains a newline | `:149-154` |

`GATE_HEADER_NEWLINE` = 2 is the entire surface that Experiment 2 (header-newline
normalisation) could act on, and it is why that experiment moved 92 → 93 cell tables and
2187 → 2199 cells and still produced `bound = 0`.

### Rows and cells `[measured]`

- **45 rows dropped** by `_row_drop_reason`: `empty_row_label` 34, `row_label_too_long` 11,
  `newline_in_row_label` 0.
- **62 cells discarded at attach time** (`represent_layout.py:110`), now attributed for the
  first time: `empty_value` **55**, `value_equals_row_label` **7**, `empty_header` **0**.
  A further 539 positions are row-label corner cells, skipped by design.
  The pipeline counts none of these — see defect D-2.
- **0 UNATTRIBUTED** drops anywhere in the trace.

### Tables contributing to a returned metric: 0

**This assertion from the brief is falsified by measurement, and the falsification is the
finding.** Not one RETURNED metric grounds to a table block. All 6 ground to prose blocks
(`discussion` ×2, `abstract` ×2, `references` ×2). No table accounts for any returned metric,
so the expected correspondence cannot exist. Recorded, not reconciled.

---

## 3. Claim ledger summary

`out/trace_on/claim_ledger.csv`, 22 rows. Existence checks use the binder's own comparison
(`gate._has`, `gate.py:459-465`) and its own claim-number regex
(`anchors.NUMERIC_ANCHOR_RE = \d+\.\d+|\b\d{2,}\b`).

| assertion | got | expected |
|---|--:|--:|
| claim rows | 22 | 22 |
| entered the binder | 14 | 14 |
| papers holding an entered claim | 8 | 8 |
| `bound` | 0 | 0 |
| entered claims with an unnamed terminal reason | 0 | 0 |

### The 8 that never entered the binder `[measured]`

Reason code `NO_NUMERIC_ANCHOR` (`gate.py:525`): the value contains no decimal number and no
2+-digit integer, so the binding branch is skipped entirely. Three of these are RETURNED —
see section 5.

### The 14 that entered, by terminal state `[measured]`

| binding status | n | terminal reason | meaning |
|---|--:|---|---|
| `pdf_only` | 9 | `UNVERIFIABLE_BINDING` | the paper has **no cells at all**; the binder returns at `gate.py:434` before comparing anything. Terminal abstain (`gate.py:528-531`) |
| `not_bindable` | 3 | `OWNERSHIP_UNVERIFIED` ×2, `RETURNED` ×1 | the claimed metric matches no column in the paper |
| `wrong_cell` | 2 | `BINDING_WRONG_CELL` | the value is in the metric's column but at another row |
| **`bound`** | **0** | — | **has never fired** |

**Only 5 of the 14 are on a paper that has any post-gate cell table at all.** The other 9 call
the binder on a paper with zero cells. So the binder performs a real comparison on **5** of 22
extracted claims.

---

## 4. Positive control

`diagnostics/funnel/positive_control/` — 13 fixtures, 12 scored (AMBIG-1 is RECORD_ONLY).

- **L1 = 12/12 PASS.** `structural_bind` called directly with cells built by
  `schema.table_cell` (its real input type), quality gate bypassed. CORE-1 binds to
  (`Ours`, `Accuracy (%)`); CORE-2 correctly refuses; all 7 NORM cases bind; REF-0/REF-1 bind.
- **L2 = 11/12 PASS.** The same tables injected as raw grids through the real `_attach`
  (real pre-registered quality gate), real `chunk_document`, real `gate_paper`.
  **CORE-1 reaches `BOUND_AND_RETURNED` through the full production path.**

**The single L2 failure:**

| case | terminal stage | reason code |
|---|---|---|
| **STRUCT-1** | `B4_binding` | **`NOT_BINDABLE`** |

STRUCT-1 is the two-header-row table. `_layout_table_cells` treats row 0 as the only header
(`represent_layout.py:96`), so `["", "CIFAR-10", "CIFAR-10"]` becomes the header and
`["Model", "Acc", "F1"]` becomes a *data row*. The composed path `CIFAR-10/F1` is therefore
never constructed, the claim's metric token `f1` matches no column, and the claim exits at
case 2. At L1, handed the ideal cell, the binder binds it correctly — so this is a
representation limit, not a binder defect.

`AMBIG-1` (RECORD_ONLY) returned `wrong_cell` at both levels, as designed.

---

## 5. The 3 returned metrics

The headline "3" is `n_returned_metrics` from the harness, which counts only metrics values
containing a digit (`parser_backend_measure.py:225-227`). The gate actually returns **6**
metrics; the other 3 are digit-free (`precision`, `search recall`, `ANN search accuracy`).
See defect D-3.

The 3 `[measured]`:

| paper | value | grounded block | section | is a table block? | binding |
|---|---|---|---|---|---|
| `68f93a5921c1` | `'F1-scores'` | `:106` | discussion | **no** | never called |
| `be7c4dc39030` | `'F1 score'` | `:6` | abstract | **no** | never called |
| `fef0393e997e` | `'GPT-4-based metrics'` | `:44` | abstract | **no** | never called |

**Table: none. Cell: none. Value: none.**

**Why each was returned without a binding.** All three are metric *names*, not quantitative
claims. Their only digits are single digits inside a name — the `1` of "F1", the `4` of
"GPT-4". `NUMERIC_ANCHOR_RE` requires a decimal or a 2+-digit integer, so
`_NUMVAL.search(value)` is False, the binding branch at `gate.py:525` is skipped in its
entirety, and the item falls straight through to grounding and attribution, both of which it
passes. **They are returned precisely because they are not numeric claims.** No binding was
attempted, missed or failed — none was ever possible.

The one RETURNED `results` item is different and worth naming: `c093b845f68e`,
`'The system achieved an Exact Match accuracy of 0.72 on the official test set.'` It *did*
enter the binder, came back `not_bindable` (case 2), and was then returned through the
case-2 fall-through at `gate.py:544-546`. Its value `0.72` appears in **no** attached cell.
So the only quantitative claim the system returns on this corpus is returned on prose
grounding, with binding explicitly not established.

---

## 6. Decision

Rules evaluated in order; the first match is the decision.

| rule | condition | result |
|---|---|---|
| **D1** BINDER_CONTRACT_BUG | CORE-1 or CORE-2 fails at L1 | **no** — both PASS (L1 12/12) |
| **D2** STAGE_KILLS_VALID_DATA | CORE passes L1 but CORE-1 dies at L2 at a named stage | **no** — CORE-1 reaches `BOUND_AND_RETURNED` at L2 |
| **D3** NO_CLAIMS_REACH_BINDER | CORE passes, and fewer than 21 claims (< 1 per paper) enter the binder | **MATCH** — **14** entered, over 8 of 21 papers |
| D4 NORMALIZATION_GAP | ≥1 NORM case fails at L1 | not reached; also could not fire — 7/7 NORM pass at L1 |
| D5 NO_DOWNSTREAM_DEFECT_FOUND | none of the above | not reached |

## DECISION: **D3 — NO_CLAIMS_REACH_BINDER**

**The rule that fired:** CORE passes at L1 (12/12), and 14 claims enter the binder across the
21 papers — fewer than one per paper.

**Evidence rows:** `claims_entering_binder = 14` of `claims_total = 22`, identical in
`baseline`, `trace_off` and `trace_on`; 8 papers hold all 14; 13 of 21 papers contribute no
claim to the binder at all; 8 claims are excluded by `NO_NUMERIC_ANCHOR` at `gate.py:525`;
and of the 14 that do enter, **9 are on papers with zero cells**, leaving **5** claims on
which the binder performs a real comparison.

**Next action (the selected decision's, and nothing beyond it): explicit claim extraction.**

---

## 7. The 2×2

Over the 14 claims that entered the binder. Membership tested with `gate._has` `[measured]`.

| | value in gate-rejected / fallback table text | not | total |
|---|--:|--:|--:|
| **value IS in an attached cell** | 1 | 3 | **4** |
| **value NOT in an attached cell** | 0 | 10 | **10** |
| total | **1** | **13** | **14** |

Also `[measured]`: the value appears in a **discarded** cell for exactly **1** of the 14.

**What this decides about the first fix.** For **10 of the 14**, the number is in no cell
anywhere — not in an attached cell, not in a discarded cell, not in the text of a rejected or
fallback table. Those claims are prose aggregates; no parser change and no normaliser could
bind them, because there is no cell to bind to. Only **4** have a cell holding their value, and
exactly **1** of those is recoverable by improving table extraction (its value sits in text
that the gate rejected). This is why the decision is D3 and not a parser or normalisation fix:
the binding surface on this corpus is 4 claims wide, and the extraction-side recoverable
surface is 1.

This does not change the decision.

---

## 8. Found, not fixed

| id | location | defect |
|---|---|---|
| **D-1** | `experiments/document_evidence_pipeline/parser_backend_measure.py:208` | `n_tables_with_grid` is computed as `sum(1 for t in tables if t["n_cells"] > 0)` — it counts tables with **≥ 1 cell**, not tables for which the backend returned a grid. The true grid-return count (142) appears in no artifact and is recoverable only by counting the `no_grid_from_backend` fallback string. Every report that read this field as "grids" understated the backend and overstated the gate. |
| **D-2** | `src/evidence/represent_layout.py:110` | Cells discarded at attach time carry no counter and no reason code. The condition `if val and head and val != row_label` silently drops a position for any of three different causes. Measured here for the first time: **62** cells (55 `empty_value`, 7 `value_equals_row_label`, 0 `empty_header`), plus 539 row-label corner positions. Invisible in every existing artifact. |
| **D-3** | `experiments/document_evidence_pipeline/parser_backend_measure.py:225-227` | `if not _NUM.search(value): continue` silently excludes digit-free values from every claim and returned-metric count. The headline "3 returned metrics" is a filtered subset of the **6** the gate actually returns, and is nowhere labelled as such. |
| **D-4** | `src/evidence/gate.py:603-610` | `gate_paper` accepts `results` **only** as a `str`; a `list` fails `isinstance(results_text, str)` and is discarded with no error, no warning and no log line, producing zero evidence items. A caller passing a list sees total silent abstention indistinguishable from a paper with no claims. `datasets` and `metrics` on the adjacent lines take lists, so the asymmetry is easy to hit. |
| **D-5** | `src/evidence/gate.py:459-465` + `src/evidence/anchors.py:27` | The value comparison is sign-blind on **both** sides. `NUMERIC_ANCHOR_RE` has no sign, so claims of `-0.4` and `0.4` both yield the anchor `0.4`; and the cell side strips with `[^\d.\-]`, which deletes U+2212 MINUS rather than folding it, so cells `−0.4`, `+0.4` and `0.4` are indistinguishable. Verified: `has("0.4", …)` is True for all four surface forms. Fixture NORM-1 passes for this reason, not because signs are handled. (The `exp/stage-a` branch adds signed anchors; that work is not on this branch.) |
| **D-6** | `src/evidence/gate.py` grounding / `attribute.py` | Two RETURNED metrics on `f3b06a91470232d1587b194e2bc82fa9a50f3c9f` are grounded in `section=references` (blocks `:178`, `:179`): `'search recall'` and `'ANN search accuracy'`. A metric returned from a bibliography entry passed both grounding and own-work attribution. |
| **D-7** | `src/evidence/represent_layout.py:96` | `_layout_table_cells` treats row 0 as the sole header row, so a multi-level header cannot be represented and its sub-columns become a data row. This is the whole of the STRUCT-1 L2 failure. |

Previously recorded and unchanged: `_METRIC` matching the Portuguese preposition "em"
(`/FINDINGS.md`), 2051 stale section-label blocks, `pymupdf4llm` poisoning `find_tables`
within a process.
