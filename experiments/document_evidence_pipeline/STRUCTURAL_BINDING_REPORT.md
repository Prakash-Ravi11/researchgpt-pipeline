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

---

# Phase 5a (cont.) — table-type classification fed into the gate

AxCell classifies each table (leaderboard / ablation / irrelevant) before
extracting cells; our gate had no notion that some tables are not results tables.
An ablation table's numbers are real but must not surface as the paper's headline
result (cf. the earlier "vs." ablation-table attribution bug; `0549e2e9` is
ablation-heavy).

## The check — `classify_table(caption, headers, rows)` → `results | ablation | other`

Deterministic, **no LLM**. Caption + header + row-label vocabulary only:

- **ablation** (cues win over results cues): `ablat*`, `w/o`, `without`, `vs.`,
  `versus`, `with and without`, `contribution/effect/impact/role/influence of`,
  `sensitivity analysis`, `leave-one-out`, `varying/removing/replacing …`, or ≥ ⅓
  of the row labels are ablation-style (`w/o …`, `− retrieval`).
- **results**: `(main/overall/final/test-set) results`, `comparison with/to`,
  `state-of-the-art` / `SOTA`, `leaderboard`, `performance on`, `held-out`,
  `official test`.
- **other**: `statistics`, `dataset … size/split/counts`, `hyper-parameters`,
  `notation`, `prompt template`, `inference/training time`, `#params`,
  `complexity`, `related work`, `citation commands` (LaTeX template artefacts).
- default: ≥ 1 metric-named column + ≥ 2 rows → `results`, else `other`.

Fed into `structural_bind`: a `bound` verdict carries `table_type`. In
`_gate_value`, `status == "bound"` **and** `table_type ∈ {ablation, other}` →
`ABSTAINED`, `abstain_reason = "bound_to_ablation_table"` / `"bound_to_other_table"`
(`evidence_status = EXPLICIT`, `provenance_valid = True` — the value *is* at its
cell; it just isn't a headline result). Only `results`-table bindings fall through
to grounding + attribution + RETURNED.

## MEASURE

### Classification distribution (13 structured papers, 53 distinct tables)

| class | tables | cells |
|---|--:|--:|
| other | 25 | 1033 |
| results | 21 | 864 |
| ablation | **7** | 89 |

### Currently-returned quantitative items grounded in an ablation table: **0**

On structured papers the gate returns **0** numeric quant items with binding ON
(all withheld as `no_cell` / `wrong_cell` — prose-stated, not cell values). With
binding OFF (pre-5a) it returned 6, and **0 of those bind to an ablation table**
either (all `no_cell` / `wrong_cell`). So the ablation hazard is currently
**latent** — 7 ablation tables exist but no returned claim touches one. The
classification is a guard for when structured ingestion (Phase 4, blocked) is
re-enabled and cell-bindings start being returned.

### Test 2 confusion matrix — no new false negatives

`gate_sensitivity.py --pass det`: **TP 1 / FN 22 / FP 3 / TN 41** — byte-identical
to the Phase-5a (structural-binding) matrix. Test 2's corpora are PDF-only, so
`structural_bind` returns `pdf_only` and never reaches the `bound` + `table_type`
path; the classification cannot introduce a false negative there. **0**
`bound_to_*_table` abstentions in Test 2.

### 10-table manual spot-check (deterministic sample)

| paper | class | cells | caption |
|---|---|--:|---|
| `0549e2e9e6` | **ablation** | 30 | "Ablation study performance metrics. The (–) symbol denotes the reference proposed system, and Failed indicates instances where the algorithm reached n…" |
| `0549e2e9e6` | results | 40 | "YOLOv11n transverse and longitudinal lumen localization results." |
| `69b02cfebf` | results | 45 | "Optimized retrieval configurations and summary metrics across the SentenceTransformer backbone models. The best-performing model is all-MiniLM-L6-v2." |
| `93db4f9a32` | other | 16 | "Embedding backbones evaluated." |
| `93db4f9a32` | other | 14 | "Validator failure reasons for Group B (1,399 pairs). \\Venv is involved in 83.5% of all failures." |
| `a9b2a3fd60` | other | 8 | "Citation commands supported by the style file. The style is based on the natbib package…" (LaTeX template artefact — correctly not results) |
| `db78acdc12` | **ablation** | 14 | "Comparison of RAG performance **with and without** the bge-reranker-v2-m3 reranker. Values represent overall mean scores across RAGAS metrics." |
| `ddb170b2ee` | **ablation** | 6 | "**Ablation study** on varying the number of top k retrieved content." |
| `e0efa866a1` | other | 201 | "Pearson correlation coefficients calculated for the BioASQ dataset." (correlation matrix, not a headline result) |
| `eaec7401af` | results | 8 | "Conversational retrieval quality in the large multicore run." |

All 10 correct/defensible. The three ablation tables and the LaTeX-template
`other` are the notable catches.

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