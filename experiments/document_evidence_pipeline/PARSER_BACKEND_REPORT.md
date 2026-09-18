# Layout-aware PDF table backend — experiment report

**Both candidate arms FAIL their pre-registered criteria. This is a negative
result, reported as one.**

The decisive number is not in the pre-registration, because neither of us
anticipated it: across 21 papers, 2187 attached table cells and 92 successfully
gridded tables, **zero claims reached binding status `bound` in any arm.** Not
one. The hypothesis — that attaching real table cells moves numeric claims into
*genuinely bound* — is false on this corpus, for both backends.

The single claim that moved from ABSTAINED to RETURNED did so by becoming
`not_bindable` and falling through to grounding, not by binding to a cell.

Two further findings outrank the headline for a paper:

- The two claims that did reach `wrong_cell` are **false rejections**. In both,
  the extracted cell is the *correct* cell, with a clean row label. The gate
  rejected them on subject matching. The ceiling on this approach is not the
  parser.
- `pymupdf4llm` calls poison `page.find_tables()` for the rest of the process.
  Discovered while testing, before the measurement; it would otherwise have
  silently corrupted the tier-1 arms.

Worktree `../rgpt-exp-parser`, branch `exp/parser-backend`, forked from `09fbc95`.
The original working directory was never checked out, moved, or modified.

---

## 1. What was run, on which papers, with which versions

**Corpus (census, n = 21).** Every PDF-path paper in the frozen canonical run
`experiments/document_evidence_pipeline/runs/prodab-20260902T004416Z/canonical/`
— that is, every paper whose `runs/latex_ingestion/reps.json` representation is
`pdf` or `pdf(fallback)`. Read **read-only by absolute path from the original
working tree**, because `runs/` and `data/` are gitignored and absent from this
worktree. Nothing was copied into or out of the original tree.

Not `data/pdfs/`: those 130 PDFs have **zero paper-id overlap** with the
extraction cache, so no claim would have existed to gate (appendix D2).

**Three arms**, one process per paper per arm, 63 processes:

| arm | table grids from |
|---|---|
| `current` | `blocks_from_pdf` — control, no cells |
| `pymupdf_tables` | tier 1 only: `page.find_tables()` |
| `pymupdf4llm` | tier 1, then tier 2: markdown pipe tables (`table_strategy="text"`) |

All three reuse `blocks_from_pdf`'s block stream verbatim and only *add*
`table_cells`, so prose text, block ids, char spans and section labels are
byte-identical across arms. Claims and the extraction cache are the same ones
`structural_binding_measure.py` uses; `gate_paper` is the real gate.

**Versions.** Python 3.10.18, Windows-10-10.0.26200. `pymupdf==1.28.2`,
`pymupdf4llm==1.28.2`, `pymupdf_layout==1.28.2`, `onnxruntime==1.23.2`,
`psutil==7.2.2`, `pytest==9.1.1`. Installed into a venv inside the worktree;
`requirements.txt` was not modified.

**Tesseract: not installed, not on PATH.** With-tesseract arms are UNMEASURED
(section 7).

**Harness validation.** Three checks, all passed, all in `results.json`:

- **Control cross-check.** The rebuilt `current` arm and the frozen cached
  chunks give identical results: 3 RETURNED, `{pdf_only: 14, no_binding_call: 8}`
  in both. Rebuilding blocks from the PDF reproduces the frozen pipeline exactly.
- **Contamination canary.** 0 cells with a newline in their value in every arm.
  Under the leak, values appear as `'0 811\n.'`. Process isolation held.
- **Parse errors.** 0 in all 63 processes.

Total wall time **886.2 s** (14.8 min), measured.

## 2. Pre-registered criteria, restated verbatim

From `PARSER_BACKEND_REPORT.md` section 1 (commit `6a27b6c`) as amended by
`PARSER_BACKEND_PLAN.md` (commits `2f9a5b1`, `b441885`). Nothing below was
changed after any treatment-arm result was seen.

**Quality gate thresholds.** `MAX_ROW_LABEL_CHARS = 60`,
`MAX_COL_HEADER_CHARS = 40`, `MIN_DATA_ROWS = 2`, `MIN_COLUMNS = 2`.

**Whole-table rejection** if: fewer than 2 header cells; any header cell *other
than the first* empty; any header cell containing a newline; any header cell over
40 chars; fewer than 2 data rows in the raw grid.

**Row drops** if the row label is empty, contains a newline, or exceeds 60 chars.

**PASS criterion** — all five must hold, per arm:

> - **P1 (PRIMARY).** At least **3 of the 14** movable claims become RETURNED,
>   **drawn from at least 2 distinct papers**.
> - **P2.** `delta_returned >= 0` on metrics+results across the census —
>   verification that the harness is wired correctly, not a finding.
> - **P3.** At least **4 of the 8** papers holding `pdf_only` claims have every
>   one of their `pdf_only` claims leave that status.
> - **P4.** Adversarial rejection unchanged: 0 cross-row acceptances
>   (invariant 14) and no RETURNED numeric quant claim with binding status other
>   than `bound` (invariant 15), in every arm.
> - **P5 (backfire guard).** Of the claims that leave `pdf_only`, at most **one
>   third** land in `wrong_cell`.

**FAIL criterion.** Any of the above not met.

**Selection, not validation** (amendment C, verbatim):

> This run SELECTS a candidate, it does not validate one. No arm may be reported
> as "the" backend on the strength of this run. Confirmation requires a second,
> separately pre-registered run on the selected arm.

**Scope** (amendment A5): 14 movable claims, roughly 7 percentage points per
claim. A feasibility study, not a measured rate. **No percentage from this run
enters the paper.**

## 3. Results

| | `current` | `pymupdf_tables` | `pymupdf4llm` |
|---|---|---|---|
| papers parsed ok | 21/21 | 21/21 | 21/21 |
| table blocks | 160 | 160 | 160 |
| tables with a grid | 0 | **0** | **92** |
| tables `fallback_pdf` | 0 | 160 | 68 |
| **cells** | **0** | **0** | **2187** |
| cells with row+col ok | 0 | 0 | 2187 |
| rows dropped by the gate | 0 | 0 | 45 |
| RETURNED metrics | 3 | 3 | 3 |
| RETURNED results | 0 | 0 | 1 |

Binding status counts, all numeric metrics/results evidence items (22 per arm):

| status | `current` | `pymupdf_tables` | `pymupdf4llm` |
|---|---|---|---|
| `pdf_only` | 14 | 14 | 9 |
| `no_binding_call` (no numeric anchor) | 8 | 8 | 8 |
| `not_bindable` | 0 | 0 | 3 |
| `wrong_cell` | 0 | 0 | 2 |
| **`bound`** | **0** | **0** | **0** |

`current` produced 0 cells on all 21 papers, matching the brief's prior.

## 4. PRIMARY — delta_returned, and every claim that moved

| arm | RETURNED | delta | newly-returned claims | from papers |
|---|---|---|---|---|
| `current` (control) | 3 | — | — | — |
| `pymupdf_tables` | 3 | **+0** | 0 | 0 |
| `pymupdf4llm` | 4 | **+1** | 1 | 1 |

**RETURNED → ABSTAINED transitions: 0.** The backfire in its original form did
not occur, and could not have (appendix D1).

### The complete `claims_flipped` list — all 5 transitions

`pymupdf_tables`: **none**. Not one claim changed status.

`pymupdf4llm`:

1. `6437463b4b13` results · `pdf_only` → `not_bindable` · ABSTAINED → ABSTAINED
   *"The repeated test showed a 10.6 percentage point improvement in
   project-family standardized decision accuracy…"* — now `ownership_unverified`.
2. `6437463b4b13` results · `pdf_only` → `not_bindable` · ABSTAINED → ABSTAINED
   *"However, this advantage did not persist in the larger breadth extension
   test, where the accuracy change w…"* — now `ownership_unverified`.
3. `be7c4dc39030` results · `pdf_only` → `wrong_cell` · ABSTAINED → ABSTAINED
   *"The best configuration using GPT-5.2 with full schema, RAG, and a
   second-pass auditing achieved an 80.36% F1 score."* — `binding_wrong_cell`.
4. `c093b845f68e` results · `pdf_only` → `not_bindable` · **ABSTAINED →
   RETURNED** *"The system achieved an Exact Match accuracy of 0.72 on the
   official test set."*
5. `e6f1d66c34b5` results · `pdf_only` → `wrong_cell` · ABSTAINED → ABSTAINED
   *"The system achieved an nDCG@5 score of 0.4502, which was competitive with
   the organizer baseline…"* — `binding_wrong_cell`.

### What the one win actually is

Transition 4 is the entire `delta_returned = +1`. It is **not** a binding
success. `not_bindable` means the claimed metric matched no column in any table
in the paper; the claim escaped the binding gate and was returned by grounding
and attribution. Attaching cells changed `pdf_only` (terminal abstain) into
`not_bindable` (fall-through). The claim is no better evidenced than before — it
is merely no longer blocked.

**Zero claims bound to a cell in any arm.** That is the result.

### The two `wrong_cell` rejections are false rejections

Re-derived per claim, each in a clean process:

**`e6f1d66c34b5`** — claim: *"The system achieved an nDCG@5 score of 0.4502…"*

```
cell found : row='NLP-CEIA-UFG (ours)'  col='**nDCG@5**'  value='0.4502'
             caption='Table 1: Subtask A results (rank 17/38).'
gate reason: value is under column '**nDCG@5**' but for row
             'NLP-CEIA-UFG (ours)', not the claim's subject 'The system'
```

That is the right cell. Right value, right column, and the row is the authors'
own entry. `_SUBJECT_RE` extracted the subject as *"The system"*, `_OWN_ROW` does
not recognise *"the system"* as an own-reference, so the subject stayed literal
and failed to token-match `NLP-CEIA-UFG (ours)` — whose `(ours)` `_OWN_ROW`
would have matched had the subject resolved to OWN.

**`be7c4dc39030`** — claim: *"The best configuration using GPT-5.2 … achieved an
80.36% F1 score."*

```
cell found : row='GPT-5.2'  col='_F_1 **score**'  value='**80.36**'
             caption='Table 2: Performance (%) across Llama 4 and G…'
gate reason: value is under column '_F_1 **score**' but for row 'GPT-5.2',
             not the claim's subject OWN
```

Also the right cell. Here the subject resolved to implicit OWN, and `_OWN_ROW`
does not match a model-name row label `GPT-5.2`.

So P5's failure is **not** the failure P5 was designed to catch. P5 guards
against garbage row labels causing mis-binds. These row labels are clean and
correct. The rejections come from the gate's subject resolution
(`_SUBJECT_RE` / `_OWN_ROW` / `_row_matches_subject`), which was previously
unreachable on PDF-path papers because they never had cells to bind to.

**Attaching correct cells exposed a pre-existing weakness that PDF-only
abstention had been hiding.** For the paper this is the most useful thing the
run produced, and it is a claim about the gate, not about parsers.

## 5. Criteria met / not met

### `pymupdf_tables` — **FAIL**

| | criterion | result | |
|---|---|---|---|
| P1 | >= 3 claims RETURNED from >= 2 papers | 0 claims, 0 papers | **FAIL** |
| P2 | `delta_returned >= 0` (wiring) | +0 | PASS |
| P3 | >= 4 of 8 papers fully leave `pdf_only` | 0 of 8 | **FAIL** |
| P4 | adversarial rejection unchanged | identical to control | PASS |
| P5 | <= 1/3 of departures in `wrong_cell` | 0 departures — undefined | N/A |

### `pymupdf4llm` — **FAIL**

| | criterion | result | |
|---|---|---|---|
| P1 | >= 3 claims RETURNED from >= 2 papers | 1 claim, 1 paper | **FAIL** |
| P2 | `delta_returned >= 0` (wiring) | +1 | PASS |
| P3 | >= 4 of 8 papers fully leave `pdf_only` | 4 of 8 | PASS |
| P4 | adversarial rejection unchanged | see below | PASS / mis-specified |
| P5 | <= 1/3 of departures in `wrong_cell` | 2 of 5 = **40%** | **FAIL** |

Neither arm may be recommended. Per amendment C, this run selects rather than
validates, and it has selected nothing.

### P4 was mis-specified by me, and the honest reading matters

P4 as I wrote it says *"no RETURNED numeric quant claim with binding status other
than `bound`"*. Applied literally it fails **the control arm**, which returns 3
claims with status `no_binding_call` — claims with no numeric anchor that never
call `structural_bind` at all. A criterion that fails the baseline is not a
criterion.

The underlying invariant 15 in `STRUCTURAL_BINDING_REPORT.md` is narrower in its
own parenthetical: *"none returned from a PDF-only / `no_cell` / `wrong_cell`
binding"*. Under that reading:

- No arm returns a claim from `pdf_only` or `wrong_cell`. **Holds everywhere.**
- Invariant 14, 0 cross-row acceptances: `wrong_cell` claims RETURNED = 0 in
  every arm. **Holds everywhere.**

`pymupdf4llm` does newly return one claim with status `not_bindable`, which
`gate.py`'s own case-2 docstring explicitly routes to "fall through to grounding
+ attribution". That is documented behaviour, not an adversarial acceptance.

Recorded as a defect in my pre-registration. It does not change either verdict:
both arms already fail on P1.

## 6. Per-paper outcomes and root causes

### `pymupdf_tables`: 0 cells on the entire corpus

160 table blocks, 0 grids. Root cause, from `table_fallback`:

| count | reason |
|---|---|
| 127 | `no_grid_from_backend` — `find_tables()` returned nothing for that page |
| 21 | `quality_gate:too_few_data_rows` |
| 6 | `quality_gate:empty_header_cell` |
| 4 | `quality_gate:header_too_long` |
| 2 | `quality_gate:newline_in_header` |

`find_tables()` found nothing at all on **127 of 160** tables. Of the 33 grids it
did return, the pre-registered gate rejected **all 33** — 21 of them for having
fewer than 2 data rows, which is the collapse mode the brief's own prior
describes. On real scientific PDFs the ruling-line strategy is not a viable
source of table cells.

### `pymupdf4llm`: 92 grids, 2187 cells, still no bindings

| count | outcome |
|---|---|
| 92 | parsed via tier 2 |
| 21 | `quality_gate:too_few_data_rows` |
| 18 | `no_grid_from_backend` |
| 17 | `quality_gate:empty_header_cell` |
| 6 | `quality_gate:header_too_long` |
| 4 | `too_few_rows:1` (post-gate, inside the cell parser) |
| 2 | `quality_gate:newline_in_header` |

Rows dropped: 45 — `empty_row_label` 34, `row_label_too_long` 11.

Per paper (tables / with grid / cells / rows dropped):

```
101625072120  0/ 0     0  0     96285d75a525 12/ 8   115 13
141276ba659d  8/ 7   111  0     a6ecdf69703d  3/ 2    20  0
2009dbb5f290  2/ 1     8  0     ac8fffa1a4ae  0/ 0     0  0
413a184de4b1 25/24   444 16     ae2768758f99  1/ 0     0  0
4f3fca4c4fa8  4/ 3    32  1     be7c4dc39030  5/ 3    46  2
6437463b4b13  5/ 4    69  0     c093b845f68e  1/ 1     9  0
68f93a5921c1  3/ 0     0  0     d3b5f3c050b4  5/ 3    25  0
78797b71788b  0/ 0     0  0     e6f1d66c34b5  8/ 6    64  0
81e060664f24  2/ 1    15  0     ef1e4a167191  0/ 0     0  0
                                f1f07a37d4cd 31/ 1    18  0
                                f3b06a914702 22/14   985  2
                                fef0393e997e 23/14   226 11
```

Four of the eight informative papers never produced a single cell
(`68f93a5921c1`, `78797b71788b`, `ae2768758f99`, `101625072120`), which is
exactly why P3 stopped at 4 of 8. `ae2768758f99` alone holds 4 of the 14 movable
claims and yielded 0 cells from its 1 table.

### Cell-quality defect in my tier-2 implementation

**Markdown emphasis leaks into cells**: `308 of 627` column headers (49%) and
`59 of 493` row labels (12%) contain `*` or `_` — `'**Accuracy (%)**'`,
`'_F_1 **score**'`, `'**80.36**'`. I do not strip emphasis from pipe-table cells.

It did **not** cause the two false rejections: `_metric_tokens` tokenises
alphanumerics so `**nDCG@5**` still matches, and `_has()` strips non-numerics
from values. But it is real debt and the most obvious single fix before any
second run.

### D6(b) and D6(c), as asked

- **Table-type transitions.** Only **1** genuine post-gate flip
  (`ablation -> other`). The other 29 "changes" are tables rejected outright
  (`results -> REJECTED` 12, `other -> REJECTED` 13, `ablation -> REJECTED` 4),
  which emit no cells and so cannot mis-bind anything. 35 were never classified
  (no grid); 95 were classified and unchanged. The D6(b) mechanism is real but
  rare on this corpus.
- **Ablation triggers.** 30 tables classified `ablation` via
  `_ABLATION_RE` on caption or header; **1** via `row_has_ablation` alone. The
  borderless `-`-row hazard exists and fired exactly once.
- Per amendment A4, the row-label gate was **not** extended to reject punctuation
  labels, so this count measures the hazard rather than suppressing it.

## 7. Tesseract on / off

**UNMEASURED.** Tesseract is not installed on this machine and, per your
instruction, was not installed. Only the native no-tesseract arm was run. That is
the Windows story: the numbers in sections 3-6 are all no-tesseract numbers.

The section-10 priors are **retired**, not compared against — different
`pymupdf4llm` version, different machine, different OCR availability.

Observed instead, as fact: `pymupdf4llm` 1.28.2 takes the **ONNX layout path,
not tesseract**. The `pymupdf_layout` distribution installs into the `pymupdf`
namespace (`pymupdf/layout/resources/onnx/layout_rf2.4.1.onnx` and four more
models); `pymupdf4llm.ocr` contains no tesseract reference; `onnxruntime` reports
providers `['AzureExecutionProvider', 'CPUExecutionProvider']`. Whether an
installed tesseract would add anything on this corpus is **UNKNOWN**.

## 8. Stale section labels (recorded, not fixed)

**2051 blocks** across the 21 papers carry a stale section label — identical in
all three arms, as expected, since the block stream is shared.

**12 of 21** papers are affected. Worst: `f1f07a37d4cd` **641** blocks,
`fef0393e997e` 341, `d3b5f3c050b4` 272, `96285d75a525` 193, `be7c4dc39030` 139.

Definition used: a block is stale if it follows a **missed numbered heading** —
a non-heading block that `_NUM_HEADING_RE` *would* have matched had its first
newline been a space (`"1\nIntroduction"`) — and precedes the next successfully
detected heading.

A first version of this detector matched on the first line alone. That counts
maths like `"1\n|Pf|"` as a missed heading; it inflated two papers before being
tightened to the counterfactual above. The reported figure is the tightened one.

Not fixed here: a separate single-variable change, and fixing it would confound
this experiment.

## 9. Install and runtime cost on Windows, per backend

**Runtime**, 21 papers, measured:

| arm | total wall | per paper | peak RSS (max / median) |
|---|---|---|---|
| `current` | 3.8 s | 0.2 s | 102 MB / 56 MB |
| `pymupdf_tables` | 57.9 s | 2.8 s | 115 MB / 70 MB |
| `pymupdf4llm` | **798.6 s** | **38.0 s** | **637 MB / 355 MB** |

`pymupdf4llm` is **210x** the control's wall time and about 6x its peak memory.
Total run including process startup: 886.2 s for 63 processes.

**Install.** `pip install pymupdf4llm` into a bare venv pulls **221.6 MB**.
Deducting what the project already pins (`pymupdf` 54.1, `numpy` 51.3,
`pyyaml` 0.6) the genuinely incremental cost is **≈ 116 MB**, dominated by
`sympy` 51.2, `onnxruntime` 41.6 and `networkx` 12.0 — `sympy` and `networkx`
arrive only as `onnxruntime` dependencies.

**Licences.** `onnxruntime`, `tabulate`, `pyyaml`, `coloredlogs`,
`humanfriendly` MIT; `numpy`, `sympy`, `protobuf`, `networkx`, `psutil`,
`pyreadline3` BSD; `flatbuffers`, `packaging` Apache-2.0. `pymupdf4llm` and
`pymupdf` are **dual AGPL-3.0 / Artifex commercial**. No new licence exposure —
`pymupdf>=1.24.0` is already in `requirements.txt` — but AGPL is worth stating
plainly in a paper rather than leaving implicit.

`requirements.txt` was **not** modified.

## 10. What this does NOT measure

- **Anchor delivery is untouched.** No anchor logic ran differently in any arm.
- **Text extraction fidelity is untouched.** Every arm reuses
  `blocks_from_pdf`'s block stream verbatim; prose text is byte-identical. This
  experiment changes only whether `table_cells` are attached.
- **Retrieval is untouched.** No embedding, no chunk selection, no Chroma
  collection was involved. `chunk_document` ran, but only to carry cells.
- Nothing downstream of the gate: Stage-6 synthesis, corpus analysis and concern
  questions were not exercised.
- Precision was not measured and could not be: no claim bound, so there were no
  bound-claim acceptances to be right or wrong about.
- **No rate, ratio or percentage from this run belongs in the paper.** 14 movable
  claims; one claim is ~7 points. The `40%` in P5 is 2 of 5.

## 11. UNMEASURED / UNKNOWN

- **With-tesseract arms:** UNMEASURED, both backends. Tesseract not installed by
  instruction.
- **Whether a second pre-registered run with emphasis-stripping would bind
  anything:** UNKNOWN. 49% of headers carry markdown emphasis; the two cases
  inspected did not fail because of it, but the other 90 gridded tables were not
  individually audited.
- **Whether the two false rejections generalise:** UNKNOWN. Two cases, read by
  hand. The judgement that each cell is "correct" is mine, from the claim text
  and the cell — both are quoted above so it can be checked.
- **Why `find_tables()` returned nothing on 127 of 160 tables:** not diagnosed
  per table. Vector-ruling detection was not inspected page by page.
- **Whether a different `table_strategy` would change tier 1:** UNKNOWN. Tier 1
  ran at the library default; only tier 2 used `"text"`.
- **Whether any of this holds outside these 21 papers:** UNKNOWN. Single corpus,
  one domain mix, n = 21.
- **Cell-level correctness of the 2187 cells:** UNMEASURED. They were counted and
  gate-filtered, not verified against the source PDFs.
- **`current` arm on non-PDF papers:** out of scope; LaTeX and JATS papers were
  excluded by design.

---

# 12. Diagnostic — why 9 claims stayed `pdf_only` under `pymupdf4llm`

Artifact-only analysis of `runs/parser_backend/results.json`. No corpus rerun, no
production code changed, no new pre-registration.

`pymupdf_tables: 0 cells corpus-wide; all 14 movable claims remained pdf_only.`

Everything below concerns the `pymupdf4llm` arm only.

## 12.1 Decision rule, stated before the result

Fixed, applied mechanically, not modified after observation:

> `parser-side ceiling : categories 1+2+3 >= 7 of 9`
> `gate-side ceiling   : categories 1+2+3 <= 3 of 9`
> `mixed / inconclusive: otherwise`

This is a feasibility / corpus-ceiling diagnosis, **not** a general scientific
accuracy rate.

## 12.2 Two corrections to the diagnostic's framing

**The population is 9 claims across 4 papers, not 9 papers.** The brief refers
throughout to "the 9 papers" and sets the rule "of 9". The artifact gives:

| paper | `pdf_only` claims under `pymupdf4llm` |
|---|---|
| `1016250721201821285c39eba5ab77eddf80812e` | 1 |
| `68f93a5921c1c6bbc5e0032f87366e46a06fded0` | 2 |
| `78797b71788ba1c852407d6010e8454f7b95f0b5` | 2 |
| `ae2768758f9928d50eebd4c945f47ff51e0e6f3b` | 4 |
| **total** | **9 claims / 4 papers** |

Categories are paper-level (rule C), so the two denominators differ. The rule is
applied below at **both** unit levels rather than my picking one. They agree.

**There is no claim ID in the artifact schema.** Claims are keyed by
`(field, value)`; that pair is used as the identifier throughout.

## 12.3 Per-paper records

### `1016250721201821285c39eba5ab77eddf80812e` — **CATEGORY 1: NO_TABLES_DETECTED**

- movable claim (1): `[results]` *"RAG-Fuse achieved the best Macro-F1 scores
  across all datasets, with up to 37% improveme…"* — ABSTAINED,
  `unverifiable_binding`
- table blocks: **0**; detected grids: 0; cells: 0
- tables: none — no block typed `table` in the shared block stream
- `control_caption_only_table_block: false`
- anomaly: none

### `68f93a5921c1c6bbc5e0032f87366e46a06fded0` — **CATEGORY 3: QUALITY_GATE_DROPPED_ALL_ROWS**

Tie-break applied: one table reached `FIND_TABLES_EMPTY`, two reached the quality
gate; the paper takes the furthest stage.

- movable claims (2):
  - `[results]` *"RAG outperformed the baseline in all models tested, with an
    average improvement of 22% i…"* — ABSTAINED, `unverifiable_binding`
  - `[results]` *"The largest model (Llama-3-70b) showed a 37% increase in
    F1-score when using RAG."* — ABSTAINED, `unverifiable_binding`
- table blocks: 3; detected grids: 0; cells: 0; rows dropped: 0
- `control_caption_only_table_block: true` (3 blocks)

| table id | page | furthest stage | rows before → after | cells | artifact evidence |
|---|---|---|---|---|---|
| `:95` | p4 | `FIND_TABLES_EMPTY` | 0 → 0 | 0 | `fallback='no_grid_from_backend'`; caption `'Table 1 and Table 2 illustrate two example tasks, show-'` |
| `:118` | p6 | `QUALITY_GATE_DROPPED_ALL_ROWS` | 1 → 0 | 0 | `fallback='quality_gate:too_few_data_rows:1'` |
| `:126` | p6 | `QUALITY_GATE_DROPPED_ALL_ROWS` | 1 → 0 | 0 | `fallback='quality_gate:too_few_data_rows:1'` |

Block `:95` is a **false table block**: its text is a prose sentence beginning
"Table 1 and Table 2 illustrate…", which `blocks_from_pdf` types as a table
because the first line starts with `"table "`. There is no grid to find. Tables
`:118` and `:126` are qualitative RAG-vs-non-RAG example tables with a single
data row; `MIN_DATA_ROWS = 2` rejected them as designed.

- anomaly: none

### `78797b71788ba1c852407d6010e8454f7b95f0b5` — **CATEGORY 1: NO_TABLES_DETECTED**

- movable claims (2):
  - `[results]` *"The system achieved 72.69% accuracy on emotion recognition
    with 216 test samples."* — ABSTAINED, `unverifiable_binding`
  - `[results]` *"It demonstrated practical low-latency inference behavior and
    passed 20 focused privacy t…"* — ABSTAINED, `unverifiable_binding`
- table blocks: **0**; detected grids: 0; cells: 0
- tables: none
- `control_caption_only_table_block: false`
- anomaly: none

### `ae2768758f9928d50eebd4c945f47ff51e0e6f3b` — **CATEGORY 3: QUALITY_GATE_DROPPED_ALL_ROWS**

This paper holds **4 of the 9** claims — the largest single block in the
population.

- movable claims (4), all ABSTAINED `unverifiable_binding`:
  - *"A etapa de geração de embeddings apresentou redução de aproximadamente 75%
    na latência c…"*
  - *"A busca vetorial teve redução de cerca de 23%."*
  - *"A geração de respostas teve redução de 10%."*
  - *"A etapa de geração de texto representa mais de 85% da latência total da
    requisição, enqu…"*
- table blocks: 1; detected grids: 0; cells: 0; rows dropped: 0
- `control_caption_only_table_block: true` (1 block)

| table id | page | furthest stage | rows before → after | cells | artifact evidence |
|---|---|---|---|---|---|
| `:19` | p3 | `QUALITY_GATE_DROPPED_ALL_ROWS` | **3 → 0** | 0 | `fallback='quality_gate:newline_in_header:col3'` |

Caption: `'Table 1. Métricas de performance e custo por componente da arq…'`
Headers: `['Componente', 'Volume', 'Custo', 'Tempo\n(sem cache)', 'Tempo\n(com cache)']`

**The backend extracted this table correctly and my own pre-registered gate
destroyed it.** Three data rows, five columns, clean row labels. Rejected because
columns 3 and 4 are legitimate two-line headers — *"Tempo (sem cache)"* / *"Tempo
(com cache)"*, wrapped across lines by the PDF layout — and rule 1.2(3) rejects
any header cell containing a newline.

The rule's rationale was that an embedded newline signals a merged or wrapped
cell. That diagnosis was right; the remedy was wrong. Collapsing intra-cell
whitespace to a space would have preserved the table intact.

Per amendment A4 the threshold is **not** changed now. Recorded as a finding and
as the single highest-value candidate for a second pre-registered run: it alone
governs 4 of the 9 remaining claims.

- anomaly: none

## 12.4 Category counts

By **claim** (n = 9, the rule's stated denominator):

| category | claims |
|---|---|
| 1 `NO_TABLES_DETECTED` | **3** |
| 2 `FIND_TABLES_EMPTY` | **0** |
| 3 `QUALITY_GATE_DROPPED_ALL_ROWS` | **6** |
| `UNRESOLVED` | **0** |
| total | 9 ✓ |

By **paper** (n = 4, the level at which categories are assigned):

| category | papers |
|---|---|
| 1 `NO_TABLES_DETECTED` | 2 |
| 2 `FIND_TABLES_EMPTY` | 0 |
| 3 `QUALITY_GATE_DROPPED_ALL_ROWS` | 2 |
| `UNRESOLVED` | 0 |
| total | 4 ✓ |

`CATEGORY_1 + CATEGORY_2 + CATEGORY_3 + UNRESOLVED = 9` holds.

`UNRESOLVED = 0`, so the rule-G budget is not engaged and the artifact schema was
sufficient for this diagnostic: `table_fallback`, `rows_before_gate`,
`rows_after_gate` and `n_cells` distinguish all three stages per table.

## 12.5 `NO_METRIC_COLUMN` consistency check

**Count: 0 — as predicted.**

All four papers record `n_cells = 0` and `n_tables_with_grid = 0`, consistent
with `pdf_only` firing at gate.py:434 only when `paper_table_cells(chunks)` is
empty. No paper shows surviving cells while recorded `pdf_only`.

## 12.6 Anomalies

**None.** No paper was excluded from the categories or the 9-claim total.

## 12.7 Corpus reconciliation

| check | result |
|---|---|
| `sum(per-paper gridded tables) == 92` | **True** (92) |
| `sum(per-paper attached cells) == 2187` | **True** (2187) |
| summed at table level instead | 92 and 2187 — identical |

Both reconcile exactly, and at the same artifact level: `n_tables_with_grid` is
defined per paper as `count(tables where n_cells > 0)`, and the per-table sum
gives the same figure.

**Definitional caveat, since "gridded" can mislead.** The 92 counts tables that
*ended with surviving cells*, not tables for which the backend returned a grid.
Of the 160 table blocks in this arm:

- 18 — backend returned nothing (`no_grid_from_backend`)
- **142 — backend returned a grid**
- of those 142, **50 were killed by the quality gate**, leaving **92**

So the backend's own extraction rate is 142/160 (89%), and the reported 92 is
after my gate removed 50. Both numbers are correct; they answer different
questions, and section 3's "tables with a grid" row means the post-gate one.

## 12.8 Rule applied

Categories 1+2+3 = **9 of 9** claims (and **4 of 4** papers). Threshold for a
parser-side ceiling is `>= 7 of 9`.

**Conclusion: `parser-side ceiling`.**

Both unit levels give the same verdict, so the 9-claims/4-papers discrepancy in
12.2 does not affect it.

Every one of the 9 remaining `pdf_only` claims is blocked before the gate's
metric-column logic is ever consulted: 3 because no table block exists at all, 6
because every candidate table lost all of its cells — 2 to a genuine single-row
qualitative table, 4 to my own newline-in-header rule rejecting a correctly
extracted table.

This concerns only the 9 claims that stayed `pdf_only`. It does **not** overturn
section 4: the 2 claims that did reach `wrong_cell` failed on the gate's subject
matching with correct cells in hand. The corpus ceiling is parser-side; the
ceiling on claims that get past the parser is gate-side. Both are real, and they
bind on different claims.

---

# 13. Experiment 2 — header-newline normalization

Pre-registered in `PARSER_BACKEND_PLAN.md` (commit `d808b05`) before corpus
execution. One controlled run, one variable.

## 13.0 Correction to the section-12 interpretation, before the new result

The **"parser-side ceiling" label is withdrawn.** It was an artifact of my own
pre-registered category rule, which summed categories 1+2+3 and called the total
"parser-side". But category 2 (`FIND_TABLES_EMPTY`) was **zero**, and category 3
(`QUALITY_GATE_DROPPED_ALL_ROWS`) was **6 of 9 claims** — tables where a
structured grid existed and the experimental quality gate discarded it.

The three causes, separated:

| cause | claims |
|---|---|
| parser / table availability | 3 (2 papers with no table block at all) |
| **quality-gate suppression** | **6** (4 by the newline-in-header rule, 2 by `too_few_data_rows` on genuine single-row qualitative tables) |
| downstream binding failure | separate population: the 2 `wrong_cell` + 3 `not_bindable` of section 4 |

Every measurement in sections 3–12 stands. Only the label changes.

**Section 9 did not demonstrate that layout-aware parsing does not help.** It
demonstrated that under *that* quality-gate configuration nothing bound, and the
dominant single blocker among the untouched claims was a rule I wrote.

## 13.1 Design

CONTROL = the section-9 recorded `pymupdf4llm` result, read from
`runs/parser_backend/results.json`. Not recomputed, not redefined.
TREATMENT = arm `pymupdf4llm_hdrnorm`: identical corpus, backend and
configuration, with **only** header-newline rejection replaced by intra-cell
whitespace collapse.

Single-variable property verified before the run: `ae2768758f99` re-run through
the new code with the flag **off** reproduced the frozen artifact exactly —
every recorded field and every per-table record identical, including
`binding_status_counts` and `n_stale_section_blocks`.

Fixed naming: `table_blocks = 160`, `backend_grid_returns = 142`,
`post_gate_cell_tables = 92` (control) / **93** (treatment).

## 13.2 Corpus-wide effect

| | control | treatment | delta |
|---|---|---|---|
| `table_blocks` | 160 | 160 | +0 |
| `backend_grid_returns` | 142 | 142 | +0 |
| `post_gate_cell_tables` | 92 | **93** | **+1** |
| attached cells | 2187 | **2199** | **+12** |
| rows dropped | 45 | 45 | +0 |
| RETURNED metrics | 3 | 3 | **+0** |
| RETURNED results | 1 | 1 | **+0** |

As requested, itemised:

- tables previously rejected **solely** because of a header newline: **1**
- tables surviving after normalization: **1**
- additional cells: **+12**
- additional claims reaching `structural_bind`: **+4**
- newly `bound`: **0**
- newly `RETURNED`: **0**
- newly `wrong_cell`: **0**
- newly `not_bindable`: **+4**
- remaining `pdf_only`: **5**

The section-2.8 caveat paid off. Two tables were *recorded* as
`newline_in_header`, but only one was rejected **solely** for that reason. The
other also violated the frozen length rule — invisible in the control, because
`_reject_header` returns on the first failing rule, and revealed only by the
treatment.

## 13.3 Primary outcomes

| binding status | control | treatment | delta |
|---|---|---|---|
| **`bound`** | **0** | **0** | **+0** |
| `RETURNED` (total) | 4 | 4 | +0 |
| `wrong_cell` | 2 | 2 | +0 |
| `not_bindable` | 3 | **7** | **+4** |
| `pdf_only` | 9 | **5** | **−4** |
| `no_binding_call` | 8 | 8 | +0 |

Departure buckets (D6a):

```
control    {pdf_only 9, no_binding_call 5, not_bindable 2,
            no_binding_call_returned 3, wrong_cell 2, not_bindable_returned 1}
treatment  {pdf_only 5, no_binding_call 5, not_bindable 6,
            no_binding_call_returned 3, wrong_cell 2, not_bindable_returned 1}
```

All four transitions, and there are no others:

| paper | from | to | verdict | final reason |
|---|---|---|---|---|
| `ae2768758f99` | `pdf_only` | `not_bindable` | ABSTAINED → ABSTAINED | `ownership_unverified` |
| `ae2768758f99` | `pdf_only` | `not_bindable` | ABSTAINED → ABSTAINED | `ownership_unverified` |
| `ae2768758f99` | `pdf_only` | `not_bindable` | ABSTAINED → ABSTAINED | `ownership_unverified` |
| `ae2768758f99` | `pdf_only` | `not_bindable` | ABSTAINED → ABSTAINED | `ownership_unverified` |

**The prediction held: the four claims became measurable.** They did not bind.
The outcome is **case B** — they reached structural binding and became
`not_bindable`.

## 13.4 Before/after table audit

### `ae2768758f99` block `:19` — the predicted table

| | control | treatment |
|---|---|---|
| original header values | `['Componente', 'Volume', 'Custo', 'Tempo\n(sem cache)', 'Tempo\n(com cache)']` | same |
| normalized header values | — (rejected) | `['Componente', 'Volume', 'Custo', 'Tempo (sem cache)', 'Tempo (com cache)']` |
| gate outcome | `quality_gate:newline_in_header:col3` | `tier:find_tables` (survives) |
| `rows_before_gate` | 3 | 3 |
| `rows_after_gate` | **0** | **3** |
| surviving cell count | **0** | **12** |
| `table_type_before` | `other` | `other` |
| `table_type_after` | `None` (rejected) | `other` |
| metric columns detected | not recorded | **0** |
| claims entering `structural_bind` | 0 | **4** |
| binding outcome | `pdf_only` | `not_bindable` |
| final gate outcome | ABSTAINED `unverifiable_binding` | ABSTAINED `ownership_unverified` |

Semantics preserved: `Tempo\n(sem cache)` → `Tempo (sem cache)`. All three data
rows kept, no row dropped.

### `fef0393e997e` block `:406` — the secondary prediction

| | control | treatment |
|---|---|---|
| original header `col1` | 160-char reference question containing a newline | same |
| normalized header `col1` | — | same text, newline collapsed, **160 chars** |
| gate outcome | `quality_gate:newline_in_header:col1` | `quality_gate:header_too_long:col1:160` |
| `rows_before_gate` / `after` | 10 / 0 | 10 / 0 |
| surviving cell count | 0 | 0 |
| `table_type_before` / `after` | `results` / `None` | `results` / `None` |
| claims entering `structural_bind` | 0 | 0 |

**The frozen 40-char rule still binds.** This table is not a table — `col1` is a
question, not a column header — and the frozen rule rejects it correctly once
the newline check stops firing first.

No other table in the corpus changed outcome: exactly 2 tables differ, both
above.

## 13.5 The exact downstream mechanism (case B)

`not_bindable` is `structural_bind` case 2, gate.py:455 — *"claimed metric
matches no table column in this paper"*. The cause is measured, not inferred:

```
header                tokens   matches _METRIC_TOKENS
'Componente'          []       False
'Volume'              []       False
'Custo'               []       False
'Tempo (sem cache)'   []       False
'Tempo (com cache)'   []       False

claim                                                    tokens
'...redução de aproximadamente 75% na latência...'       []
'A busca vetorial teve redução de cerca de 23%.'         []
'A geração de respostas teve redução de 10%.'            []
'...mais de 85% da latência total da requisição...'      []
```

**`_METRIC_TOKENS` is an English-only vocabulary and this paper is in
Portuguese.** `latency` is in the vocabulary; `tempo` and `latência` are not. The
claims say *latência*, the headers say *Tempo*.

Both sides yield zero metric tokens, and in `structural_bind`:

```python
metric_columns = [c for c in cells if metric_toks and _col_matches_metric(...)]
```

With `metric_toks` empty this list is empty **regardless of how many cells
exist**. The 12 newly attached cells are never compared against anything. The
claim exits at case 2 before any cell is examined.

This is precisely the **RESIDUAL GAP** that `structural_bind`'s own docstring
already declares — *"a claim whose metric phrase contains no recognised metric
word AT ALL … still evades binding via case 2"*. What is new is that it is a
**language** gap, not merely a vocabulary-coverage gap: no claim in a
non-English paper can bind, whatever the parser does.

**A second, independent language blocker follows it.** Having fallen through to
grounding and attribution, all four abstained `ownership_unverified`.
`attribute.py`'s own-reference cues are English-only regexes —
`\b(we|our|us|ours)\b`, `\bthis (paper|work|study|…)\b`, `\bthe proposed\b` — and
a Portuguese sentence matches none of them.

**And a third sits behind both.** The table classifies as `table_type = "other"`
(0 metric columns, so `classify_table`'s default branch cannot return
`results`). Had a claim bound, gate.py:539 would have withheld it as
`bound_to_other_table`.

Three sequential blockers, none of them a parser problem, and none fixable by
better table extraction.

## 13.6 Safety — unchanged

| | control | treatment |
|---|---|---|
| RETURNED by binding status | `{no_binding_call: 3, not_bindable: 1}` | `{no_binding_call: 3, not_bindable: 1}` |
| invariant 14, cross-row acceptances | **0** | **0** |
| RETURNED from a `pdf_only` binding | **0** | **0** |
| newly introduced `wrong_cell` bindings or rejections | — | **0** |

No safety criterion was weakened, and no new wrong-cell outcome was created.

Adversarial false rejects: the two identified in section 4 are unchanged, and no
new ones appeared. The `structural_binding_measure.py` adversarial probe suite
runs on LaTeX/JATS structured papers and is untouched by this change, which
affects only PDF-path header handling; it was **not** re-run, and that is stated
rather than implied.

## 13.7 A runtime anomaly, reported not repaired

The driver recorded **35,244.3 s** total wall. That figure is not usable as a
runtime measurement: one worker, `fef0393e997e`, recorded **34,755 s** (9.7 h)
against 122.5 s for the same paper in section 9 — a 284x outlier, while every
other paper ran *faster* than in section 9 (ratios 0.4-0.9, on an otherwise idle
machine).

**It does not reproduce.** Re-running that single paper on the treatment arm:
**147.3 s**, peak RSS 369 MB, and outcomes byte-identical to the recorded run.
The stall was environmental — the run spanned an overnight period — and affected
timing only, not any measured outcome.

Representative treatment-arm runtime: **477.4 s** for the other 20 papers, or
**~625 s** substituting the reproduced 147.3 s, against 798.6 s for the same arm
in section 9. The recorded 35,244.3 s is left in the artifact unaltered.

## 13.8 Conclusion

The pre-registered hypothesis was **confirmed at the level it predicted and no
further**. Legitimate intra-cell header wrapping *was* causing a correctly
parsed table to be discarded; normalizing the header recovered it exactly as
predicted — one table, 12 cells, three rows, semantics intact — and made four
movable claims measurable.

It produced **no additional binding, no additional returned evidence, and no
additional risk**. `bound` remains 0 across the whole corpus.

The quality-gate rule was a real defect and is now demonstrated to be one. It was
not, however, what was standing between this corpus and genuine evidence binding.
For these four claims, three further blockers sit behind it, and all three are
the gate's English-only vocabulary meeting a Portuguese paper.

Neither F1 nor F2 was implemented. `gate.py`, `_SUBJECT_RE`, `_OWN_ROW`,
`classify_table` and `build_document()` are unmodified.

---

## Appendix — discrepancies found against the brief, before any code

Preserved from the pre-registration commit `6a27b6c`. These changed the design.

**D1 — the stated backfire cannot happen.** `pdf_only` is a terminal ABSTAIN in
`_gate_value` (gate.py:528-531), not a fall-through. Measured control: 22 numeric
metrics/results items, 14 abstained at `pdf_only`, 3 RETURNED, and those 3 never
reach `structural_bind` (no numeric anchor under `_NUMVAL` =
`\d+\.\d+|\b\d{2,}\b`). `delta_returned >= 0` was therefore an identity, not a
criterion — hence P1 as a count, and P5 as the real backfire guard.

**D2 — `data/pdfs/` is the wrong corpus.** 130 live PDFs, zero paper-id overlap
with the extraction cache. Corpus switched to the frozen canonical run.

**D3 — the worktree has no corpus.** `runs/` and `data/` are gitignored; read
read-only by absolute path from the original tree.

**D4 — `n = 10` discards most of the signal.** All 14 movable claims sit in 8 of
the 21 papers. Switched to a census of 21. Vindicated: 4 of those 8 papers
produced no cells at all, and a 10-paper sample could easily have missed the
`pdf_only` departures entirely.

**D5 — "any empty header rejects the table"** would reject the conventional blank
top-left corner. Narrowed to any header cell *other than the first*. Confirmed
inert for binding: `_jats_table_cells` requires a truthy `head` and skips cells
where `val == row_label`, so `header[0]` never binds anything.

**D6 — table-type abstention** (yours, verified). Five-bucket accounting adopted.
Three corrections recorded: `classify_table` receives a *set* of distinct row
labels, not a row count; `row_has_ablation` needs >= 2 matching labels and its
prefix set includes `w/o`; `_table_type_for` groups siblings by caption equality
across the whole paper. Also recorded, not fixed: gate.py:377's comment says
">= 2 metric-named columns" while gate.py:380 tests `>= 1`.

**Methodological finding — `pymupdf4llm` poisons `find_tables()`.** After
`to_markdown` runs, `page.find_tables()` in the same process returns phantom
text-clustered grids with corrupted values (`'0 811\n.'` for `'0.811'`). Found
while testing, before the measurement. Within a paper the tier order was already
safe; **across papers in one process it was not**, and the tier-1 call site sat
inside `except Exception`, so the corruption would have been logged as an
ordinary per-page parse error. Now a `RuntimeError` re-raised past that handler,
with one process per paper. It fired for real during post-run analysis when a
script tried a second paper in one process — it stopped rather than reported a
corrupted number.
