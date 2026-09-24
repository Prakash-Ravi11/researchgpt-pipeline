# R4 — scored cell disambiguation

## STOP STATUS: **STOPPED at STEP 9 — ISOLATION EXCEPTION (8 claims)**

Control reproduced, both corpus arms ran, both positive controls passed. The isolation
check then failed with **8 exceptions**, which STEP 9 defines as a STOP condition and
explicitly forbids patching around. The pre-registered decision rule is **not applied**.

| | |
|---|---|
| repository | `C:\Users\Praka\Downloads\rgpt-exp-parser` |
| **starting SHA** | **`8f2140eaa8a76e9a3d1c08a59c837b70a133ad5e`** (`8f2140e`) |
| branch created | `exp/r4-disambiguation`, from `8f2140e` |
| working tree at start | clean; branch was `exp/parser-backend` |
| corpus | the same 21 PDF-path papers, `pymupdf4llm` arm |
| LLM calls | none |
| `C:\Users\Praka\Downloads\researchgpt-pipeline` | untouched |
| `main` | untouched, not pushed |

---

## 1. Actual legacy selection — file:line

Discovered by searching the repository, not taken from the experiment description.
All three selection points are inside `structural_bind` in **`src/evidence/gate.py`**:

| file:line | code | role |
|---|---|---|
| **`src/evidence/gate.py:474`** | `return _bound(n, on_row[0])` | binds to the first subject-matching candidate |
| **`src/evidence/gate.py:476`** | `c = col_hits[0]` | reports `wrong_cell` against the first metric-column candidate |
| **`src/evidence/gate.py:485`** | `c = elsewhere[0]` | reports `wrong_cell` against the first any-column candidate |

Candidate construction: `col_hits` at `src/evidence/gate.py:469`,
`elsewhere` at `src/evidence/gate.py:483`.

## 2. How legacy chooses among multiple value-matching cells — three lines

1. Candidates are built by list comprehension in document order — `col_hits`
   (`gate.py:469`) is every cell whose column header matches the claim's metric tokens
   *and* whose value matches the claim number under `_has`; `elsewhere` (`gate.py:483`)
   is every cell in the paper whose value matches, regardless of column.
2. It then filters `col_hits` to rows whose `row_label` matches the claim's grammatical
   subject (`on_row`, `gate.py:472`) and, if any survive, binds to **`on_row[0]`** —
   purely the first in document order (`gate.py:474`).
3. If no row matches the subject it does **not** bind: it returns `wrong_cell` against
   **`col_hits[0]`** (`gate.py:476`) or **`elsewhere[0]`** (`gate.py:485`), again purely
   the first in document order. There is no scoring, no tie detection, and no use of
   table mentions anywhere in the selection.

---

## 3. The R4 change

**A. `disambiguation_policy: legacy | scored`, default `legacy`**
(`configs/staging_config.yaml`, `evidence_grounding` block; `RGPT_DISAMBIGUATION_POLICY`
overrides per run). Reader: `src/evidence/gate.py::_disambiguation_policy`.

In `scored` mode, at each of the two candidate sites, the same candidate list legacy
would have taken index 0 of is scored instead:

- **+1** if the claim metric matches the cell's column header under the binder's
  **existing exact matcher** `_col_matches_metric`;
- **+1** if any row-label token of ≥ 3 characters, not a stopword, occurs in the claim
  sentence;
- **table-mention restriction**: applied only when the claim names exactly one label
  *and* exactly one table in the paper carries that label, and never when it would empty
  the pool;
- unique highest scorer with score ≥ 1 → bind via the **same `_bound` constructor**, so
  verification downstream is the identical path; otherwise **`ABSTAIN_AMBIGUOUS`** and no
  binding.

`src/` diff: **`src/evidence/gate.py` only, 122 insertions, 0 deletions.** `represent_layout.py`,
`anchors.py`, `chunker.py`, `attribute.py` and `explicit_claims.py` verified untouched.
`ABSTAIN_AMBIGUOUS` deliberately gets **no branch in `_gate_value`** — adding one would be a
gate change — so it falls through to grounding exactly as `not_bindable` does.

**B. `h1_flattened_table_text`** — computed **entirely in the read-only analysis layer**
(`diagnostics/funnel/analyze_disambiguation.py::h1_flag`), never in pipeline code, so it
cannot filter, bind, admit or gate. Set when the source block is typed `paragraph` **and**
either ≥ 50 % of whitespace-separated tokens are numeric, or ≥ 3 numeric tokens equal
attached-cell values of one single table. Explicitly a heuristic.

---

## 4. Control reproduction — PASS

`out/disambig_legacy/`, settings `claim_extractor=explicit`, `ownership_policy=block`,
`disambiguation_policy=legacy` `[measured]`:

| required | got | |
|---|--:|---|
| claims | 2218 | PASS |
| entered binder | 1754 | PASS |
| bound | 5 | PASS |
| B-PROSE | 858 | PASS |
| B-BIND | 536 | PASS |
| B-TABLE | 207 | PASS |
| B-UNDETECTED | 95 | PASS |
| B-NONE | 53 | PASS |
| `not_bindable` | 467 | PASS |
| `wrong_cell` | 69 | PASS |
| sub-reasons | 414 / 0 / 6 / 9 / 59 / 18 / 30 | PASS |

Positive control, legacy mode: **L1 12/12, L2 11/12, STRUCT-1 the only failure** — PASS.

Because the control reproduced, proceeding to the treatment was correct under STEP 7.

---

## 5. Legacy funnel

`[measured]` `pdf_only` 189 · `no_binding_call` 464 · `not_bindable` 1458 ·
`not_a_table_claim` 33 · `wrong_cell` 69 · **`bound` 5**. Returned results 597.
Table side 160 / 142 / 92 / 2187.

## 6. Scored funnel

`[measured]` `pdf_only` 189 · `no_binding_call` 464 · `not_bindable` 1458 ·
`not_a_table_claim` 33 · `wrong_cell` **0** · **`bound` 31** · `ABSTAIN_AMBIGUOUS` **43**.
Returned results 627. Table side identical: 160 / 142 / 92 / 2187.

`[derived]` The 69 legacy `wrong_cell` claims split exactly: **26 new bindings + 43
abstentions = 69**. `bound` goes 5 → 31 (+26). Claims, entered-binder, `not_bindable`,
`pdf_only`, `no_binding_call` and `not_a_table_claim` are all unchanged.

---

## 7. Transition table — multi-candidate claims only (65)

`[measured]`

| legacy outcome | scored outcome | n |
|---|---|--:|
| `WRONG_CELL` | `ABSTAIN_AMBIGUOUS` | 41 |
| `WRONG_CELL` | `BOUND` | 20 |
| `BOUND` | `BOUND same cell` | 4 |
| | **total** | **65** |

`BOUND → BOUND different cell` = **0**: no pre-existing binding moved cell.
`BOUND → ABSTAIN_AMBIGUOUS` = 0. `BOUND → WRONG_CELL` = 0.

### 8. Split by H-1 and F-1 (labels only, never filters)

| legacy → scored | h1=False | h1=True |
|---|--:|--:|
| `WRONG_CELL` → `ABSTAIN_AMBIGUOUS` | 28 | 13 |
| `WRONG_CELL` → `BOUND` | 15 | 5 |
| `BOUND` → `BOUND same cell` | 3 | 1 |

| legacy → scored | f1=False | f1=True |
|---|--:|--:|
| `WRONG_CELL` → `ABSTAIN_AMBIGUOUS` | 41 | 0 |
| `WRONG_CELL` → `BOUND` | 20 | 0 |
| `BOUND` → `BOUND same cell` | 4 | 0 |

No multi-candidate claim carries the F-1 bibliography label.

---

## 9. Isolation result — **STOP**

STEP 9 requires that every claim with **≤ 1 value-matching candidate**, or that never
reaches cell selection, be identical between arms.

**Result: 8 ISOLATION EXCEPTIONS.** All 8 have exactly **one** value-matching candidate,
so there was no choice for R4 to make, yet the outcome changed in every one.

| claim_id | paper | n_value_matching | legacy | scored |
|---|---|--:|---|---|
| `799f403556eba6c7` | `413a184de4b1` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `ABSTAIN_AMBIGUOUS` / ABSTAINED / `ATTRIBUTED_TO_CITED_WORK` |
| `aea97bc5af7a089f` | `413a184de4b1` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `bound` / ABSTAINED / `OWNERSHIP_UNVERIFIED` |
| `228ddf3d9fbec8a1` | `413a184de4b1` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `bound` / ABSTAINED / `BOUND_TO_OTHER_TABLE` |
| `368749712a0df1de` | `413a184de4b1` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `bound` / ABSTAINED / `BOUND_TO_OTHER_TABLE` |
| `8362518e00c27611` | `be7c4dc39030` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `bound` / **RETURNED** / `RETURNED` |
| `fbd39790b1162795` | `f1f07a37d4cd` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `ABSTAIN_AMBIGUOUS` / **RETURNED** / `RETURNED` |
| `c7ee6d368165ccc0` | `fef0393e997e` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `bound` / ABSTAINED / `BOUND_TO_ABLATION_TABLE` |
| `a206213b3379585d` | `fef0393e997e` | 1 | `wrong_cell` / ABSTAINED / `BINDING_WRONG_CELL` | `bound` / ABSTAINED / `BOUND_TO_ABLATION_TABLE` |

Fields that differ: `binding_status` in all 8; `terminal_state` in 2
(`8362518e00c27611`, `fbd39790b1162795`, ABSTAINED → RETURNED); `terminal_reason` in all 8.

### Root cause, reduced to one candidate

The pre-registered R4 rule replaces **two** things, not one: the *choice* among candidates
**and** the *accept/reject* test.

- legacy accept test: `_row_matches_subject(row_label, subject)` — `gate.py:472`
- scored accept test: `score >= 1` — `_r4_select`

With exactly one candidate there is no choice to make, but the accept test still differs,
so the outcome changes. Minimal reproduction, one cell carrying the value under a
metric-matching header whose row label is not the claim's grammatical subject:

```
legacy  status=wrong_cell   cell=None
scored  status=bound        cell=GPT-5.2   r4={'n_candidates': 1, 'top_score': 2, 'n_winners': 1}
```

This is also visible in the unit tests: `test_zero_score_abstains_via_cross_column_candidates`
is a one-candidate case where legacy says `wrong_cell` and scored says `ABSTAIN_AMBIGUOUS`.

So the scope condition *"in `scored` mode, ONLY the selection of a cell among already-existing
value-matching candidates changes"* is **violated for single-candidate claims**, by the
pre-registered rule itself rather than by the implementation. Not patched, per STEP 9.

---

## 10. Positive controls — PASS in both modes

`[measured]`

| | legacy | scored |
|---|---|---|
| L1 | 12/12 | 12/12 |
| L2 | 11/12 | 11/12 |
| only failure | STRUCT-1 (`NOT_BINDABLE`) | STRUCT-1 (`NOT_BINDABLE`) |

**CORE-1 binds to the SAME cell** in both modes: row `Ours`, column `Accuracy (%)`,
value `92.3`, caption `Table 1: Accuracy on the benchmark.` — PASS.
**CORE-2 does not bind** in either mode (`not_a_table_claim`) — PASS.
STEP 11 did not trigger.

AMBIG-1 changes from `wrong_cell` to `ABSTAIN_AMBIGUOUS` under scored, which is the
designed behaviour for a value present in two cells with no disambiguating context.

---

## 11. H-1 counts across all buckets

`h1_flattened_table_text` = **358 of 2218 claims (16.1 %)** `[measured]`.

| binding status | H-1 flagged |
|---|--:|
| `not_bindable` | 308 |
| `no_binding_call` | 26 |
| `ABSTAIN_AMBIGUOUS` | 13 |
| `bound` | **6** |
| `pdf_only` | 5 |
| **total** | **358** |

6 of the 31 scored bindings are on claims the H-1 heuristic flags as flattened table text.

---

## 12. Labeling file

**Path:** `C:\Users\Praka\Downloads\rgpt-exp-parser\out\disambig_scored\labeling_disambig.csv`

**Row count: 31** `[measured]` — 26 `new_scored_binding` + 5 `legacy_binding`.
`changed_scored_binding` = 0, because no pre-existing binding moved cell.

Row order randomized with seed **20260924**. `human_label` is empty in every row; allowed
values `CORRECT` / `WRONG_CELL` / `WRONG_SIGN` / `NOT_A_CLAIM`. Columns include claim
sentence, metric, bound cell value, row label, column header path, table caption, page,
score, `h1_flag`, `f1_flag`, plus `legacy_status` / `scored_status` / `kind` for context.

Of the 31 rows: **6 carry the H-1 flag, 0 carry the F-1 flag, 25 carry neither.**

---

## 13. Pre-registered decision rule — reproduced verbatim, **NOT APPLIED**

```
Labeled set = bindings new or changed under scored, excluding rows with the h1 or f1 flag set.
p = CORRECT / labeled, with Wilson 95% CI; n = labeled count.
KEEP_SCORED if n ≥ 10 and the lower bound > 0.5.
REVERT if n ≥ 10 and the upper bound < 0.5.
Otherwise, keep legacy as the default and record the result as inconclusive.
After any outcome, binding-side changes are closed on this corpus (remaining R2 = 6, R3 ≤ 9). The next change is claim-admission precision in explicit_claims.py (H-1 flattened table text and F-1 bibliography lines), followed by roadmap action 2 (corpus audit).
```

Not applied. No labels exist. The human labels the CSV first.

For sizing only, not a decision: the eligible denominator would be the new-or-changed
bindings excluding H-1/F-1 flagged rows = **26 new − 6 H-1 flagged = 20**.

---

## 14. Found, not fixed

| id | location | defect |
|---|---|---|
| **J-1** | the pre-registered R4 rule itself, against `src/evidence/gate.py:472` | **The rule is not isolable as specified.** It replaces legacy's accept test (`_row_matches_subject`) as well as the choice among candidates, so single-candidate claims change outcome even though no disambiguation occurred. 8 of 1754 claims are affected. A rule that kept legacy's accept test and changed only the *index* chosen when ≥ 2 candidates survive would be isolable; that is a redesign and was not attempted. |
| **J-2** | `src/evidence/gate.py` scored branch | `ABSTAIN_AMBIGUOUS` has no branch in `_gate_value`, so it falls through to grounding and attribution exactly like `not_bindable`. Consequence: 2 claims that legacy ABSTAINED (`BINDING_WRONG_CELL`) are RETURNED under scored without a binding. Adding a branch would be a gate change, which is forbidden, so this was left as is. |
| **J-3** | `src/evidence/gate.py:474` (legacy, pre-existing) | Legacy's `on_row[0]` also takes document order when several subject-matching candidates exist, so legacy has an undisambiguated choice of its own. The 4 `BOUND → BOUND same cell` transitions show scored happened to agree on all of them here, but that is not guaranteed. |
| **J-4** | `diagnostics/funnel/analyze_disambiguation.py` | `n_value_matching` counts value-matching cells across the whole paper (the `elsewhere` population), which is an upper bound on the `col_hits` candidate count. It is therefore conservative for the isolation check: a claim counted as multi-candidate may have had one `col_hits` candidate. The 8 exceptions all have n = 1, so none of them is affected. |
| **J-5** | `src/evidence/gate.py::_r4_row_token_hit` | The stopword list is hand-written and English-only. On the Portuguese paper in this corpus a row token may match a claim for lexical reasons unrelated to identity. Not measured. |

Carried forward unchanged: H-1 … H-5 (`binding_breakdown_v1.md` §9), G-1 … G-4, F-1 … F-5,
D-1 … D-7. None fixed.

---

## 15. Tests

`experiments/document_evidence_pipeline/tests/test_r4_disambiguation.py` — **19 tests**,
covering the unique scored winner (both the agree-with-legacy and the divergence case), tie
→ `ABSTAIN_AMBIGUOUS`, zero score → `ABSTAIN_AMBIGUOUS`, the table-mention restriction and
its three non-restriction guards, single candidate unchanged, no candidate unchanged,
`pdf_only` unchanged, `not_bindable` unchanged, the default policy being `legacy`, and the
scoring helpers.

Full suite: **109 passed** (90 pre-existing + 19 new), run before the corpus execution.
`reproducibility/verify_deterministic.py`: **36 passed, 0 failed, 0 skipped**.

---

## 16. Artifacts

Committed under `out/disambig_legacy/` and `out/disambig_scored/`: `counts.json`,
`buckets.json`, `output_hashes.json`, `run_metadata.json`, `claim_ledger.csv`,
`rejection_ledger.csv`, `binding_review.csv`, plus in the legacy arm
`bbind_subreasons.csv` / `btable_check.csv` / `binding_breakdown.json`, and in the scored arm
`labeling_disambig.csv` / `disambiguation_summary.json`.

Over 5 MB, gitignored, SHA-256 recorded; both regenerate deterministically from
`run_funnel.py` with the settings in `run_metadata.json`:

| file | bytes | sha256 |
|---|--:|---|
| `out/disambig_legacy/trace.jsonl` | 14,172,163 | `d528d370b8b0478f22b1f419d09152a3d27cff1ed827136bae3ed86ff50fc212` |
| `out/disambig_legacy/results.json` | 8,077,596 | `cdd9e73f9a9c2b480645724b35ceb185beed0a05cbc5ee1f999c6bef887270b0` |
| `out/disambig_scored/trace.jsonl` | 14,198,790 | `7f633231f7ad2010b37f254c31ffcca510bd1278809b40ca730ccd46fb731303` |
| `out/disambig_scored/results.json` | 8,078,516 | `7a216e2a8c3c2200188e560b5967a80f5097f541afd1f62e9acdb835758e63b3` |

The same table, generated directly from `sha256sum` output, is in
`docs/diagnosis/ARTIFACT_HASHES.md`.
