# Phase 5a — structural cell binding in the evidence gate

Branch `claude-code-verification` · HEAD `b6e6fa3` (+ this change) · 2026-09-04
Inside Stage 5 (the evidence gate) + the Stage-2 chunker (prerequisite only).
Production `configs/` not modified. Selector, acquisition, extraction prompt,
model settings, corpus membership untouched. Seeded path.

## ATTRIBUTION ≠ BINDING (stated in `src/evidence/gate.py`)

**ATTRIBUTION** answers *whose* result this is. **BINDING** answers *which* result
this is — is the claimed number the value at the (row = subject, column = metric)
cell it implies. Grounding ("number + ≥ 2 topical tokens co-occur in one chunk")
checks neither. Phase 4a produces structured `table_cells` (value, column_header,
row_label, caption, section) for LaTeX e-print and JATS papers; nothing consumed
them. This wires them into the gate.

## Prerequisite — the chunker carries `table_cells` forward

`chunk_document` and `process_paper_grounded` now copy `table_cells` +
`table_caption` from a table block onto **every** chunk of that block (the cells
describe the whole table; any sub-chunk that grounds a claim can reach them).

Verified: cell counts survive Stage 2 **unchanged** —

| representation | cells at block level | cells reachable via chunks |
|---|--:|--:|
| LaTeX (6-paper sample) | 1423 | **1423** |
| JATS (`0549e2e9`) | 256 | **256** |

## The check — `structural_bind(value, chunks)` → `_gate_value`

For a quantitative claim (`metrics` / `results` with a meaningful numeric anchor):

| paper | outcome |
|---|---|
| **PDF-only** (no `table_cells` anywhere) | `structured=False` → **`unverifiable_binding`** → NOT returned as an OWN quantitative result |
| **structured**, value at the (subject-row, metric-column) cell | `bound` → proceeds to grounding + attribution (binding ≠ ownership) |
| **structured**, value under the metric column but a **different row** | `wrong_cell` → **`binding_wrong_cell`** (cross-row) |
| **structured**, value at the subject's row but a **different column** (a real metric column for the claimed metric exists) | `wrong_cell` |
| **structured**, value in **no** cell | `no_cell` → `unverifiable_binding` |
| **structured**, non-standard column headers, value at subject's row | falls back to value+row → `bound` |

Subject is parsed from `"<subject> reports/achieves/… <metric> of <value>"`; an
`our/proposed/…` subject or an absent subject → the OWN-method row (`_OWN_ROW`).

## MEASURE

### 1. Returned numeric metrics/results — binding OFF vs ON

Canonical 34, re-ingested through the LaTeX path (parity gate ON so structured
cells exist): 11 LaTeX-retained + 2 JATS = **13 structured**, 21 PDF-only.
Stage-4 output from the frozen extraction cache; the real `gate_paper`.

| subset | OFF | ON | Δ |
|---|--:|--:|--:|
| structured (LaTeX + JATS) | 6 | **0** | −6 |
| PDF-only | 10 | **3** | −7  (**correction**, not regression) |
| total | 16 | **3** | −13 |

- **PDF-only −7**: exactly the predicted correction — on a collapsed PDF a
  quantitative OWN claim cannot be bound to a cell, so it is not returned as a
  verified own result. Same class of correction as §14 (abstract-vs-body).
- **structured −6**: all 6 were **prose / abstract-stated** numbers with **no
  matching table cell** — e.g. `f3d7e0165d`'s abstract "faithfulness score of
  0.621 … 0.797" (the paper has a *Faithfulness* column, but neither value is in
  any of its 69 cells). Under "must be verified against the CELL … do not guess"
  → `unverifiable_binding`. This is the strict contract, reported not tuned.
- The **3 survivors** are single-digit values (`"improves by 8 points"`) that fall
  below the meaningful-numeric-anchor rule and never reach the binding check —
  the pre-existing single-digit-exclusion gap (this report's §C), unchanged.

### 2. Binding probes on structured papers

Auto-constructed from parsed cells: a claim `"<row> reports a <metric-col> of
<value> on the benchmark."`, value sanitised to a plausible metric range.

| class | wants | n | RETURNED | ABSTAINED | wrong |
|---|---|--:|--:|--:|--:|
| `correct_cell` | RETURNED | 9 | 1 | 8 | 8\* |
| `correct_row_wrong_col` | ABSTAINED | 4 | **0** | 4 | 0 |
| `correct_col_wrong_row` (**cross-row**) | ABSTAINED | 6 | **0** | 6 | 0 |
| `cross_table_substitution` | ABSTAINED | 10 | **0** | 10 | 0 |

- **Cross-row acceptances on structured papers: 0** — the hard requirement, met.
- **Adversarial probes accepted (FOOLED): 0** across all three wrong-* classes.
- \* The 8 `correct_cell` "misses" are **not binding failures**: 7 are claims
  about a **baseline row** (`all-MiniLM-L6-v2`, `Nearest Neighbor`, `ARCD`, …) —
  binding *succeeds* (`bound`) and **attribution** then correctly abstains them
  as not-own (`ownership_unverified`); 1 has a single-digit value that does not
  ground. Where a probe used a clean **own-method** row, it bound and returned.
  (Auto-probe construction on Phase-4a cells is limited by cell-quality debt —
  `\cmidrule(lr){3-4}` leaking into headers, un-stripped `\pm` in values like
  `8466.7`; noted, not fixed here — Stage 2 is out of scope.)

### 3. Test 2 mutation suite — confusion matrix vs the 5a result

Test 2's corpora (`canonical60` + `data_test` `paper_evidence.json`) are **all
PDF-only** — their chunks carry no `table_cells`. So structural binding marks
**every numeric OWN paraphrase `unverifiable_binding`**:

| | 5a (post-range-check) | 5a + structural binding |
|---|---|---|
| should-ACCEPT (paraphrase) | TP 36 / FN 1 | **TP 1 / FN 22** |
| should-REJECT (pert/fab/del) | FP 7 / TN 65 | **FP 3 / TN 41** |
| precision / sensitivity / specificity | .837 / .973 / .903 | **.25 / .04 / .93** |

The FN surge is the **correction**: Test 2's synthetic ground truth ("this
numeric paraphrase should be accepted") assumes the pre-5a contract. Under the
new contract a numeric OWN claim on a PDF-only paper is *unverifiable*, so it is
correctly withheld — the harness's `expected=RETURNED` for those mutants is now
wrong, not the gate. FP fell 7 → 3 (recurrence-based support-deletion escapes
also now abstain). On **structured** papers (§2) cross-row acceptances are 0.

## Invariants (added)

- **14 `cross_row_binding_acceptances_zero`** — no RETURNED numeric quant claim
  has `structural_binding.status == "wrong_cell"`.
- **15 `no_own_quantitative_from_unverifiable_binding`** — every RETURNED numeric
  quant claim has `structural_binding.status == "bound"` (none returned from a
  PDF-only / `no_cell` / `wrong_cell` binding).

## Tests

- `tests/test_pipeline.py` + `tests/test_anchors.py`: **15/15**.
- experiment suite `tests/test_pipeline_units.py`: **44/44** (+2 structural
  binding: own-cell → RETURNED, cross-row → `binding_wrong_cell`; 1 rewritten:
  PDF-only quant → `unverifiable_binding`).
- **15/15 staging invariants PASS** (`staging_run.py`, structural binding active).

## Honest limits

- The gate can now only return a quantitative OWN result when a structured
  representation exists **and** the value binds to its cell. On the current
  default corpus (LaTeX ingestion disabled from Phase 4b, ~2 JATS papers) that is
  a very small set — most quantitative results are withheld as unverifiable. That
  is the correct posture given the measured cross-row / count-misread defects, but
  it makes the structured-ingestion path (Phase 4, blocked on the `num_predict`
  cap) the gating dependency for quantitative coverage.
- Prose / abstract-stated numbers on structured papers do not bind (no cell) and
  are withheld. Binding does not attempt prose-level row inference.
- Single-digit quantitative claims bypass binding entirely (pre-existing §C gap).