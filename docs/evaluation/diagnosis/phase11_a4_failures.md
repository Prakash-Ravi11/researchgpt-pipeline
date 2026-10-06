# Phase 11 A4: read-only failure classification

Diagnosed at checkpoint `731ef69`, implementation `7f0cef3`, before new tests or fixes.
Machine-assisted, unvalidated. This is mechanism classification, not held-out evidence.
The six original experiment assertions and all frozen artifacts remain unchanged.

## Baseline

The unchanged experiment command (`python -B -m tests.test_pipeline_units`, from
`experiments/document_evidence_pipeline`) ran with `RGPT_BINDER_POLICY=v2` in a detached
temporary worktree at `phase10-binder-final` (`050f8de`). Python 3.10.18 and 3.13.6 each
reported **56 passed, 7 failed**. All six authorized assertions already failed there;
none is new in Phase 11. The extra baseline failure was the real-metric cross-row
probe (adv 4c), which passes at the Phase 11 checkpoint. The worktree was removed.
The process-wide offline audit guard blocked network/Ollama access and self-tested
before each run. Commands, original STOP log hashes, baseline log hashes and exact
per-assertion observations are in `../evidence/phase11_a4_baseline.json`.

## Mechanisms

| Original assertion line | Baseline classification (both runtimes) | Mechanism and observed consequence |
| --- | --- | --- |
| 262 | Already failing in Phase 10 | E1: `_form` joins the tokens of a decorated metric header, but `_match_forms` only permits `_SEP` separators, which exclude `@`. The same claim/header cannot match. `_frame` consequently treats the mixed-case metric stem as an unexplained name. `links` rejects the own cell; the gate maps `wrong_cell` to `binding_wrong_cell`, losing a supported return. |
| 266 | Already failing in Phase 10 | E1: the same compound-metric mismatch loses the quantity link. A different row supplies no subject link either. `_bind_v2` drops the candidate as `not_required` before its own-reference conflict can establish a wrong-cell result. It returns `not_bindable`; the gate correctly applies its table-value guard and produces `table_value_unbound`. |
| 277 | Already failing in Phase 10 | E2: when no value candidate exists, `_bind_v2` chooses `not_a_table_claim` solely from `any_cand=False`. It never establishes that the claimed quantity is represented in the attached table. A missing metric column is incorrectly classified as a prose aggregate. |
| 356 | Already failing in Phase 10 | E3: `_build` indexes every leaf header as a quantity and `_qnames` offers that header as quantity evidence, including a generic group heading. This creates a purported metric link to a number in another model's row. `links` emits name/subject conflicts, and `_bind_v2` reports `wrong_cell` even though no measurable metric has been named. |
| 358 | Already failing in Phase 10 | E3: identical generic-heading quantity promotion, for another numeric candidate. The status error precedes the gate's independent table-value guard. |
| 368 | Already failing in Phase 10 | E2: the generic measurement phrase has neither a supported quantity nor a numeric candidate. The absent-value branch nevertheless returns `not_a_table_claim` instead of `not_bindable`. This assertion is not evidence for a valid count binding. |

## Existing semantic contract

`gate.structural_bind` documents quantity-scope checking before value-location
classification: a quantity not represented in the table is `not_bindable`; a
represented quantity with a value absent from every cell is `not_a_table_claim`;
a represented quantity whose value belongs to a conflicting row/column is
`wrong_cell`, mapped to `binding_wrong_cell` by `_gate_value`. Generic group
headings are documented residuals, not recognised performance metrics.

Binder v2 additionally supports explicit row/caption quantities, count attributes,
hierarchical headers and local multi-value scope. Those extensions and Classes A-D
remain binding constraints. A missing text-only second value must not invalidate
an otherwise verified bind; a matching conflicting second value still must.
The six baseline failures establish that the divergence predates Phase 11, within
v2 itself. No gate semantics, source implementation or pre-existing expectation
has been changed during this diagnosis.
