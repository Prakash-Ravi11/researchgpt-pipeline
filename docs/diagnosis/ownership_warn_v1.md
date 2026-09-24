# ownership_policy: block vs warn — one bounded experiment

One treatment, one variable. The human overrode the pre-registered mapping
(B-PROSE → claim classification) on the ground that B-PROSE claims have no table value, and
selected the top recoverable reason instead: **OWNERSHIP_UNVERIFIED (252 of 536 B-BIND claims)**.
This measures it.

Every number is `[measured]` from the two runs below, or `[derived]` from them.

| | |
|---|---|
| worktree / branch | `C:\Users\Praka\Downloads\rgpt-exp-parser` · `exp/parser-backend` |
| parent commit | `bd2121a` (working tree clean at start — precondition PASS) |
| corpus | the same 21 PDF-path papers, `pymupdf4llm` arm, `claim_extractor=explicit` in both arms |
| control | `out/ownership_block/` · `ownership_policy=block` |
| treatment | `out/ownership_warn/` · `ownership_policy=warn` |
| LLM calls | none |

> ## The headline, stated first
>
> **Warn produced zero new bindings.** `bound` is **5 in both arms**. The ownership check runs
> at `gate.py:571`, *after* binding has already been decided at `gate.py:525-546`, so relaxing it
> cannot turn an unbound claim into a bound one — it can only change what happens to a claim
> whose binding verdict is already fixed.
>
> The 252 claims the human targeted are **all `not_bindable`** `[measured]`: their claimed metric
> matches no column in the paper. Warn returns them, but returns them **without a binding**.
> Returned items rise 597 → 1534 (+937); bindings do not move.

---

## 1. The change made

**Emitters of `OWNERSHIP_UNVERIFIED`, located before editing:**

| file:line | in the measured path? | edited? |
|---|---|---|
| `src/evidence/gate.py:572` | **yes** — reached via `gate_paper` → `_gate_value` | **yes, this one only** |
| `experiments/document_evidence_pipeline/results_gate_sweep.py:169` | no — separate harness, not imported by `parser_backend_measure.py` | no |
| `experiments/document_evidence_pipeline/pipeline/decide.py:41` | no — vendored experiment copy, not in the measured path | no |

**The change**, `src/evidence/gate.py:571-582` (was 571-573):

```python
if attr["attribution"] == UNKNOWN:
    if _ownership_policy() == "warn":
        item["ownership_flag"] = "OWNERSHIP_UNVERIFIED"
    else:
        item.update(final=ABSTAINED, abstain_reason="ownership_unverified")
        return item
```

Plus `_ownership_policy()` at `src/evidence/gate.py:507-527` and `import os` at
`src/evidence/gate.py:18`. **That is the entire diff under `src/`** — 36 insertions, 2 deletions,
in one file. `anchors.py` is untouched and `reproducibility/verify_deterministic.py` reports
**36 passed, 0 failed, 0 skipped**.

**Flag:** `evidence_grounding.ownership_policy: block | warn`, default **`block`**, in
`configs/staging_config.yaml`; `RGPT_OWNERSHIP_POLICY` overrides it per run.

Warn was implementable without changing any other decision (STOP CONDITION 3 not triggered) —
see the isolation check in §6.

---

## 2. Control reproduction (STOP CONDITION 2)

`out/ownership_block/` against `bd2121a` `[measured]`:

| required | got | |
|---|--:|---|
| claims | 2218 | PASS |
| entered the binder | 1754 | PASS |
| bound | 5 | PASS |
| B-PROSE | 858 | PASS |
| B-BIND | 536 | PASS |
| B-TABLE | 207 | PASS |
| B-UNDETECTED | 95 | PASS |
| B-NONE | 53 | PASS |
| B-BIND reasons | 252 / 143 / 69 / 58 / 14 | PASS |

B-BIND by terminal reason, control: `OWNERSHIP_UNVERIFIED` 252, `RETURNED` 143,
`BINDING_WRONG_CELL` 69, `EVIDENCE_SPAN_NOT_FOUND_IN_PAPER_CHUNKS` 58,
`ATTRIBUTED_TO_CITED_WORK` 14.

Block-mode positive control: **L1 12/12, L2 11/12, STRUCT-1 the only failure** — unchanged.

---

## 3. Block vs warn, side by side

`[measured]`

| | block | warn |
|---|--:|--:|
| claims total | 2218 | 2218 |
| entered the binder | 1754 | 1754 |
| **bound** | **5** | **5** |
| returned (metrics + results) | 597 | **1534** |
| ownership-flagged claims | 0 | **937** |
| papers with ≥1 claim in the binder | 21/21 | 21/21 |
| bindings in `binding_review.csv` | 74 | 74 |
| … of them ownership-flagged | 0 | **2** |
| sign mismatches | 0 | 0 |

Terminal reason codes `[measured]`:

| reason | block | warn |
|---|--:|--:|
| `RETURNED` | 596 | **1528** |
| `OWNERSHIP_UNVERIFIED` | 932 | **0** |
| `EVIDENCE_SPAN_NOT_FOUND_IN_PAPER_CHUNKS` | 254 | 254 |
| `UNVERIFIABLE_BINDING` | 161 | 161 |
| `ATTRIBUTED_TO_CITED_WORK` | 151 | 151 |
| `BINDING_WRONG_CELL` | 69 | 69 |
| `METRIC_VALUE_OUT_OF_RANGE` | 2 | 2 |

Exactly one reason code moves, and it moves to zero.

### What the 937 newly-returned claims are

`[measured]`, by binding status: `not_bindable` **720**, `no_binding_call` **205**,
`not_a_table_claim` **10**, `bound` **2**.

By bucket: B-BIND 252, B-PROSE 296, B-TABLE 115, B-UNDETECTED 40, B-NONE 27, and 207 that are
outside the bucket scheme because they bound or never failed to bind.

**254 of 937** have their value in an attached cell; **2** have an actual binding.
**236 of 937 (25.2 %) carry the F-1 bibliographic pattern.**

The 252 the human targeted: **all 252 are `not_bindable`** `[measured]`. Warn moves them from
ABSTAINED to RETURNED without producing a binding for any of them.

---

## 4. Buckets and reconciliation

Buckets are **identical in both arms** `[measured]` — as they must be, since bucket membership is
a property of where the value sits, not of the ownership verdict.

| bucket | block | warn |
|---|--:|--:|
| B-PROSE | 858 | 858 |
| B-BIND | 536 | 536 |
| B-TABLE | 207 | 207 |
| B-UNDETECTED | 95 | 95 |
| **B-NONE** | **53** | **53** |
| **sum** | **1749** | **1749** |
| expected (entered − bound) = 1754 − 5 | **1749** | **1749** |
| **reconciles** | **PASS** | **PASS** |

The 53 previously-unbucketed claims are now B-NONE, all with one reason code:
**`VALUE_ONLY_IN_DISCARDED_CELLS` 53** `[measured]` — the value appears only in a cell discarded
at attach time (`represent_layout.py:110`), so it is in no attached cell, no fallback table text,
and the triage never fires. Every entered-and-unbound claim now has exactly one bucket.

---

## 5. New bindings

**New binding count: 0.** `bound` = 5 in both arms `[measured]`.

Two existing bindings change terminal state (bound-and-abstained → bound-and-returned). Both are
on the same cell of the same paper, from two different sentences:

| | |
|---|---|
| bound cell value | `92.69%` |
| row header | `ColNomic-3B (Ours, adopted)` |
| `value_occurrences_in_paper` | **3** |
| `mention_matches_bound_table` | **no_mention** |
| `sign_match` | true |
| F-1 flag | false |

Distributions over these 2 `[measured]`:

- `mention_matches_bound_table`: `{no_mention: 2}` — neither claim names a table, so the mention
  cannot corroborate or contradict the chosen table.
- `value_occurrences_in_paper`: `{3: 2}` — the value `92.69` occurs in **3** attached cells in
  that paper, so the binder chose one of three candidates. n = 2 and both are the same cell; no
  distribution can be read off this.

---

## 6. Isolation check

Row-wise over all 2218 claim rows, both arms aligned by (paper_id, claim_text) at every index
`[measured]`:

| check | result |
|---|---|
| control `OWNERSHIP_UNVERIFIED` rows that changed | **937 of 937** |
| rows with any **other** control reason that changed | **0** |
| `binding_status` identical row-wise | **true** |
| bucket identical row-wise | **true** |
| `value_found_in_attached_cells` identical row-wise | **true** |

**Isolation exceptions: none.** The treatment is confined to the ownership check.

**STOP CONDITION 4:** claims passed to `gate_paper` = claims iterated = **2218** in both arms,
0 per-paper mismatches across all 21 papers `[measured]`.

---

## 7. Positive control, both modes

`[measured]`

| | block | warn |
|---|---|---|
| L1 | **12/12** | **12/12** |
| L2 | **11/12** | **11/12** |
| only failure | STRUCT-1 (`B4_binding` / `NOT_BINDABLE`) | STRUCT-1 (`B4_binding` / `NOT_BINDABLE`) |
| cases differing between modes | — | **0** |

**CORE-2 under warn: does NOT bind.** Its binding status stays `not_a_table_claim` in both modes,
identical to block. The negative control is not broken by warn.

Note for the record: CORE-2's *final* is `RETURNED` in both modes — it always was. The fixture's
expectation is NO_BIND (no binding), which it satisfies in both modes; it is returned on prose
grounding, not on a binding.

---

## 8. F-1 count

- Among the **2** new bindings: **0** carry the F-1 bibliographic pattern.
- Among the **937** newly-returned claims: **236 (25.2 %)** carry it `[measured]`.
- Among all 2218 claims: 253.

F-1 is not fixed here, per the scope lock. It is reported because a quarter of what warn admits
matches the bibliography pattern.

---

## 9. Labeling artifacts

Per STEP 4, over `binding_review.csv`:

- `out/ownership_warn/labeling_sample.csv` — **74 rows**: all 72 bindings without an ownership
  flag, plus all **2** with one (fewer than 60, so all are included), in seeded random order
  (seed **20260924**), with an empty `human_label`.
- `out/ownership_warn/labeling_reserve.csv` — **0 rows**; there is no third flagged binding.

**The pre-registered rule cannot discriminate on this population.** It counts CORRECT among
*flagged bindings*, and there are **2**. A Wilson 95 % interval on n = 2 spans essentially the
whole unit interval, so neither `KEEP_WARN` nor `REVERT_TO_BLOCK` can fire, and both are the same
binding on the same cell.

So that the next step is not blocked, the claim-level population is also emitted, **clearly
separate and not a substitute for the pre-registered denominator**:

- `out/ownership_warn/labeling_sample_claims.csv` — 60 of the 937 ownership-flagged **claims**,
  same seed, empty `human_label`.
- `out/ownership_warn/labeling_reserve_claims.csv` — the next 40 in the same seeded order.

Choosing between the two denominators is the human's call. This report does not make it.

---

## 10. Pre-registered decision rule, reproduced verbatim, NOT applied

> p = CORRECT / labeled, among flagged bindings, with Wilson 95% CI.
> KEEP_WARN if the lower bound > 0.5.
> REVERT_TO_BLOCK if the upper bound < 0.5.
> Otherwise, label labeling_reserve.csv and re-apply.
> After either outcome, the next change is the largest remaining recoverable count among B-TABLE
> and the B-BIND reasons. B-PROSE, B-UNDETECTED and B-NONE are excluded.

Not applied. No labels exist.

---

## 11. Stop conditions

| # | condition | result |
|---|---|---|
| 1 | precondition (HEAD `bd2121a`, clean tree) | PASS, not triggered |
| 2 | control does not reproduce, or block positive control changes | reproduced; PC unchanged; not triggered |
| 3 | warn cannot be isolated to the ownership check | 0 exceptions; not triggered |
| 4 | claims passed ≠ claims iterated | 2218 = 2218 both arms; not triggered |

No stop condition fired.

---

## 12. Found, not fixed

| id | location | defect |
|---|---|---|
| **G-1** | `src/evidence/gate.py:571` vs `gate.py:525-546` | **The ownership check is downstream of binding.** No ownership policy can create, remove or redirect a binding; it can only change the terminal state of a claim whose binding verdict is already fixed. This is why the treatment produced 0 new bindings, and it means "recover the 252 OWNERSHIP_UNVERIFIED B-BIND claims" is not reachable from this lever — all 252 are `not_bindable`, i.e. their metric matches no column. |
| **G-2** | `diagnostics/funnel/build_ownership_ledgers.py` (this diagnostic) | `claim_id` is not unique per gate item: the ledger joins explicit-claim records to gate items by **sentence text**, so identical sentences at different char spans in one paper share an id. 21 ids cover 53 duplicate rows of 2218. Row counts are correct; any keyed join on `claim_id` alone silently loses those 53. |
| **G-3** | `src/evidence/attribute.py` / `gate.py:558-570` | 236 of the 937 claims warn admits (25.2 %) match the F-1 bibliographic pattern, i.e. attribution returned UNKNOWN on text that reads as a reference-list entry. Warn converts those into returned results. |
| **G-4** | `src/evidence/gate.py:476-487` (restated, now quantified) | The `wrong_cell` verdict still records only `(row, col)`. This diagnostic works around it by resolving the pair against the paper's attached-cell inventory, but the gate's own output remains unreviewable: 69 of 74 binding rows carry no cell value from the gate. |

Carried forward unchanged: F-1 … F-5 (`docs/diagnosis/claims_explicit_v1.md` §8) and
D-1 … D-7 (`docs/diagnosis/funnel_142_3_0.md` §8). None fixed.

---

## 13. Artifacts

Committed in both `out/ownership_block/` and `out/ownership_warn/`: `claim_ledger.csv`,
`rejection_ledger.csv`, `binding_review.csv`, `buckets.json`, `counts.json`,
`output_hashes.json`, `run_metadata.json`, and in the warn arm the four labeling files.

Over the 5 MB threshold, gitignored, SHA-256 recorded per the standing rule; both regenerate
deterministically from `run_funnel.py`:

| file | bytes | sha256 |
|---|--:|---|
| `out/ownership_block/trace.jsonl` | 13,932,683 | `6ce51e89b95537c63f8087a8741f8fabc92e535327b73d775c4b2a5d9ec0a63b` |
| `out/ownership_block/results.json` | 8,077,592 | `3d89a3b8e95bd041a5f21ff4721e7b1ba6d77ec1b1525c02a5f7d825ce1cac92` |
| `out/ownership_warn/trace.jsonl` | 13,895,059 | `4bf86125f2b33ba1e12945164f054ddb45cf72b0df81c27f7ee57bc2e811f57c` |
| `out/ownership_warn/results.json` | 8,068,154 | `c473c57a102a1bb7b90ad5a5f5df82406710c473cdd32a9eab071852e8d6eae0` |
