# Why B-BIND and B-TABLE claims do not bind — read-only breakdown

Read-only diagnosis. No pipeline decision changed: `src/` was not touched, and the run
reproduces `2aa50c2` block mode row for row.

Human decisions carried in: the ownership experiment is **REVERT_TO_BLOCK** (`ownership_policy`
stays in code with default `block`, no code change), and the `2aa50c2` labeling samples are unused.

| | |
|---|---|
| worktree / branch | `C:\Users\Praka\Downloads\rgpt-exp-parser` · `exp/parser-backend` |
| parent commit | `2aa50c2` (working tree clean at start — precondition PASS) |
| run | `out/binding_breakdown/` · `claim_extractor=explicit`, `ownership_policy=block` |
| corpus | the same 21 PDF-path papers, `pymupdf4llm` arm |
| LLM calls | none |

> ## The headline
>
> **R1–R5 total 74 of 536 B-BIND claims (13.8 %).** The dominant sub-reason is
> `NO_METRIC_IN_CLAIM` at **414 of 536 (77.2 %)** — the binder extracts no metric from the claim
> at all, so no table-side change can make it bind. The pre-registered mapping excludes that
> category, so it is not the named next change, but it is the fact that governs the population.
>
> **R1 is 0 on this corpus**, and the classifier that would detect it is validated: STRUCT-1
> classifies as `METRIC_IN_DROPPED_HEADER_ROW` exactly as pre-registered. Multi-level headers are
> a real representation gap (STRUCT-1 proves it) but they are not what is blocking these 536.
>
> **Named next change: R4 — candidate disambiguation, n = 59.**

---

## 1. Control reproduction (STOP CONDITION 2)

`out/binding_breakdown/` against `2aa50c2` block mode `[measured]`:

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

Row-wise identity against `2aa50c2` block mode, all 2218 rows aligned by (paper_id, claim_text):

| field | identical |
|---|---|
| `terminal_state` + `terminal_reason_code` | **2218 / 2218** |
| `binding_status` | 2218 / 2218 |
| `bucket` | 2218 / 2218 |
| `value_found_in_attached_cells` | 2218 / 2218 |
| `triage` | 2218 / 2218 |

B-BIND by terminal reason is identical to `2aa50c2`: 252 / 143 / 69 / 58 / 14.
Table side unchanged: 160 / 142 / 92 / 2187.

**Positive control: L1 12/12, L2 11/12, STRUCT-1 the only failure** — unchanged.
No pipeline decision differs (STOP CONDITION 3 not triggered).

---

## 2. B-BIND at the binding stage (3a)

Binding-stage outcome, taken from `structural_bind`'s verdict at `gate.py:525-546`, **not** the
terminal return-stage code `[measured]`:

| binding-stage outcome | n |
|---|--:|
| `not_bindable` — the claimed metric matches no column in the paper (`gate.py:452-457`) | **467** |
| `wrong_cell` — a cell was chosen and verification rejected it (`gate.py:474-487`) | **69** |
| `skipped` (binding branch not entered) | 0 |
| other | 0 |
| **SUM** | **536** — reconciles, **PASS** |

No B-BIND claim skipped the binding branch: every one has a numeric anchor, so `gate.py:525` was
always entered. `pdf_only` cannot appear here by construction — a B-BIND claim's value is in an
attached cell, so its paper has cells.

---

## 3. Sub-reason for every non-binding B-BIND claim (3b)

Candidate cells are attached cells in the same paper whose value matches a claim value under the
binder's own comparator (`gate._has`). Metric extraction is the binder's own
(`gate._metric_tokens`); the matcher is the binder's own (`gate._col_matches_metric`). Rules are
applied in the fixed order, first match wins, so the counts partition the 536 exactly once.

| # | sub-reason | n | share |
|---|---|--:|--:|
| 1 | `NO_METRIC_IN_CLAIM` | **414** | 77.2 % |
| 2 | `METRIC_IN_DROPPED_HEADER_ROW` | **0** | 0 % |
| 3 | `METRIC_IN_ROW_HEADER` | **6** | 1.1 % |
| 4 | `METRIC_NEAR_MATCH` | **9** | 1.7 % |
| 5 | `WRONG_CELL` | **59** | 11.0 % |
| 6 | `METRIC_ABSENT` | **18** | 3.4 % |
| 7 | `OTHER` | **30** | 5.6 % |
| | **SUM** | **536** | reconciles, **PASS** |

Cross-tab against the binding-stage outcome `[measured]`:

- `not_bindable` (467) → `NO_METRIC_IN_CLAIM` 414, `OTHER` 30, `METRIC_ABSENT` 18,
  `METRIC_NEAR_MATCH` 4, `METRIC_IN_ROW_HEADER` 1.
- `wrong_cell` (69) → `WRONG_CELL` 59, `METRIC_IN_ROW_HEADER` 5, `METRIC_NEAR_MATCH` 5.
  The 10 that are not `WRONG_CELL` matched an earlier rule, which is the fixed ordering working as
  specified, not a discrepancy.

### Examples, three per sub-reason

Each shows the claim sentence, the metric the binder extracted, a candidate cell value, and the
full raw header stack at that cell (kept column header first, then every discarded row above it).

**`NO_METRIC_IN_CLAIM` (414)** — `gate._metric_tokens(claim)` is empty.

| # | claim (truncated) | metric | occ |
|---|---|---|--:|
| 1 | `'Multi-HyDE\n34.4\n37.91\nFinal Pipeline\n45.6\n52.91.'` | *(none)* | 4 |
| 2 | `'Multi-HyDE\n0.6269\n0.3547\n0.3849\n0.8404\n0.0594\nHyDE\n0.7660\n…'` | *(none)* | 22 |
| 3 | `'Multi-HyDE\n0.8976\n0.8170\n0.5205\n0.9352\n0.4871\nHyDE\n0.8883\n…'` | *(none)* | 32 |

These are **table rows flattened into prose**: PyMuPDF emitted the table body as a paragraph
block, so `explicit_claims` saw a "sentence" of stacked numbers. There is no metric phrase because
there is no sentence. See defect H-1.

**`METRIC_IN_DROPPED_HEADER_ROW` (0)** — none on this corpus. The classifier's positive control
(STRUCT-1) does fire, so this is an empty category, not an untested one. See §6.

**`METRIC_IN_ROW_HEADER` (6)** — the metric names the row stub, not a column.

| # | claim (truncated) | metric | candidate cell | header stack | hit row label |
|---|---|---|---|---|---|
| 1 | `'Cosine Similarity\n0.5981\n0.5765\nRecall\n0.2462\n…'` | `faithfulness\|recall\|rouge\|score` | `**0.5981**` | `['**Method 1**']` | `Recall` |
| 2 | `'…the system attains 91.03% Recall@5 (95% bootstrap CI …'` | `accuracy` | `**91.03 [84.6, 96.2]**<br>**80.77 **` | `['Recall@5 (%)<br>Ju', '100.00 [100.0, 100.0]<br>79.31', …]` | `Dimensional Accuracy` |
| 3 | `'Hallucination Rate\n484\n88.84\nDimensional Accuracy\n1,015\n95.37\n…'` | `accuracy\|rate` | `1,400` | `['Total']` | `Dimensional Accuracy` |

These are transposed tables: the metric is the row axis and the method is the column axis.

**`METRIC_NEAR_MATCH` (9)** — every (claim metric, header text) pair is in
`out/binding_breakdown/bbind_subreasons.csv`. **Quality is poor and the count should be discounted:**

| # | claim metric | matched header text | comment |
|---|---|---|---|
| 1 | `recall` | `Real plans` | edit distance ≤ 2 on unrelated words |
| 2 | `mrr\|ndcg\|recall` | `7_._3 min (one-time)` | `mrr` ↔ `min` is distance 2 |
| 3 | `ter` | `Recall@5 (%)<br>Ju` | 3-character metric token |

The brief fixes rule 4 as token-set equality **or edit distance ≤ 2**. On 3-character metric
tokens (`mrr`, `mae`, `map`, `ter`, `em`) that threshold matches unrelated words. R3 = 9 is
therefore an **upper bound**, and most of it looks spurious on inspection.

**`WRONG_CELL` (59)** — the binding stage chose a cell and verification rejected it.
The metric matched the **chosen** cell's header in **19 of 59**; it did not in **40 of 59**
`[measured]`.

| # | claim (truncated) | metric | chosen row | chosen col | metric matched chosen header | occ |
|---|---|---|---|---|---|--:|
| 1 | `'• ColNomic-3B reaches 91.47% Recall@5 on a new 4,056-pair …'` | `recall` | `**Overall**` | `Zero-shot Recall@5 (%)` | **true** | 5 |
| 2 | `'PlanSightRAG achieves 91.47%\nRecall@5 on zero-shot retrieval…'` | `recall` | `**Overall**` | `Zero-shot Recall@5 (%)` | **true** | 3 |
| 3 | `'…our Qwen2.5-VL-72B pipeline reaches 100% verdict accuracy…'` | `accuracy` | `CLIP ViT-B/32` | `FDOT` | false | 36 |

**`METRIC_ABSENT` (18)** — the metric matches no header level, row label or raw grid cell
anywhere in the paper's tables.

**`OTHER` (30)** — the metric appears somewhere in the paper's tables but not at or above any
candidate cell. Up to 10 examples are in `bbind_subreasons.csv` (filter `sub_reason == OTHER`).

---

## 4. B-TABLE check (STEP 4)

For each of the 207 B-TABLE claims, the binder's matcher plus checks 2–4 were run against the raw
header cells and row labels of the gate-rejected or fallback table where its value was found. For
`no_grid_from_backend` tables only the raw block text is available, and that is what was used.

**B-TABLE-MATCHABLE = 0 of 207** `[measured]`.

The reason is on the claim side, not the table side: **189 of the 207** B-TABLE claims have **no
extracted metric at all**, so there is nothing to match against any header. Of the 18 that do
carry a metric, none matches a header or row label of the table holding its value.

---

## 5. R1–R5 and the excluded counts

`[measured]`

| rule | category | n |
|---|---|--:|
| **R1** | `METRIC_IN_DROPPED_HEADER_ROW` | **0** |
| **R2** | `METRIC_IN_ROW_HEADER` | **6** |
| **R3** | `METRIC_NEAR_MATCH` | **9** (upper bound; see §3) |
| **R4** | `WRONG_CELL` | **59** |
| **R5** | `B-TABLE-MATCHABLE` | **0** |
| | **R1–R5 total** | **74** |

Excluded by the pre-registered mapping:

| category | n |
|---|--:|
| `NO_METRIC_IN_CLAIM` | **414** |
| `METRIC_ABSENT` | **18** |
| `OTHER` | **30** |
| **excluded total** | **462** |

`[derived]` 74 + 462 = 536.

---

## 6. STRUCT-1's classification (3c)

The classifier was run on all 13 positive-control fixtures.

**STRUCT-1 → `METRIC_IN_DROPPED_HEADER_ROW`**, which is exactly the pre-registered expectation.
**The classifier is validated**: it can detect R1, and R1 = 0 on the corpus is an empty category
rather than a blind spot.

AMBIG-1 → `WRONG_CELL`, as designed. The 11 fixtures that bind (CORE-1, REF-0/1, NORM-1…7)
classify as `OTHER`; that is expected and carries no meaning, because `classify()` is only applied
to claims that did **not** bind, and those 11 did.

Full output: `out/binding_breakdown/classifier_validation.json`.

> **Correction made during this run, recorded rather than hidden.** A first version of rule 2 used
> the near-matcher as well as the binder's matcher. With edit distance ≤ 2 that made the metric
> `mrr` match the word `min`, and rule 2 fired on a data row reading `7.3 min (one-time)`,
> reporting **R1 = 6**. Rules 2 and 3 now use the binder's own matcher only, which is what the
> brief specifies; near-matching belongs to rule 4 alone. The corrected count is **R1 = 0**.
> STRUCT-1 still classifies correctly, because its hit is an exact match (`F1` header vs metric
> `f1`).

---

## 7. `value_occurrences_in_paper` per category

Number of attached cells in the same paper carrying the same value under `gate._has` `[measured]`:

| sub-reason | n | occ = 1 | occ > 1 | median | max |
|---|--:|--:|--:|--:|--:|
| `NO_METRIC_IN_CLAIM` | 414 | 98 | 316 | 3 | 94 |
| `METRIC_IN_DROPPED_HEADER_ROW` | 0 | — | — | — | — |
| `METRIC_IN_ROW_HEADER` | 6 | 0 | 6 | 10 | 30 |
| `METRIC_NEAR_MATCH` | 9 | 1 | 8 | 9 | 60 |
| **`WRONG_CELL`** | **59** | **7** | **52** | **6** | **63** |
| `METRIC_ABSENT` | 18 | 5 | 13 | 6 | 35 |
| `OTHER` | 30 | 13 | 17 | 3 | 23 |

**52 of the 59 `WRONG_CELL` claims have their value in more than one attached cell** (median 6).
That is the direct evidence for R4: the binder is choosing among several same-value cells and
picking one the verifier then rejects.

---

## 8. Pre-registered mapping, reproduced verbatim

> R1 METRIC_IN_DROPPED_HEADER_ROW → multi-level header representation (represent_layout.py:96; STRUCT-1 is its positive control)
> R2 METRIC_IN_ROW_HEADER → binder uses row labels as a metric axis
> R3 METRIC_NEAR_MATCH → metric alias normalization in the binder's matcher
> R4 WRONG_CELL → candidate disambiguation when a value occurs in more than one cell
> R5 B-TABLE-MATCHABLE → table gates to flag-only
> Excluded: NO_METRIC_IN_CLAIM, METRIC_ABSENT, OTHER.
> Next change = the largest of R1–R5.
> If R1–R5 are all zero, binding-side fixes are exhausted, and the next step is roadmap action 2 (corpus audit).

**Named next change: R4 — candidate disambiguation when a value occurs in more than one cell
(n = 59).** Not implemented.

R1–R5 are not all zero, so the corpus-audit branch does not apply.

---

## 9. Found, not fixed

| id | location | defect |
|---|---|---|
| **H-1** | `src/evidence/represent.py` block typing → `explicit_claims.py` | **414 of 536 B-BIND claims (77.2 %) have no extractable metric because they are table rows flattened into prose.** PyMuPDF emits a table body as a `paragraph` block, so `explicit_claims`'s `IN_TABLE_BLOCK` rule never fires and a "sentence" like `'Multi-HyDE\n34.4\n37.91\nFinal Pipeline\n45.6\n52.91.'` becomes a claim. This is the single largest fact about the 536 and it is a claim-population defect, not a binding defect. Distinct from F-1 (bibliography leakage): here the leak is table content, not references. |
| **H-2** | brief's rule 4 / `classify_bindings.py:near` | Edit distance ≤ 2 is too loose for the 3-character metric tokens in `_METRIC_TOKENS` (`mrr`, `mae`, `map`, `ter`, `em`): `mrr` matches `min`, `ter` matches arbitrary text. R3 = 9 is an upper bound and most of it is spurious on inspection. A length-aware threshold would be needed before R3 is actionable. |
| **H-3** | `src/evidence/gate.py:474-487` | In 40 of 59 `WRONG_CELL` cases the metric did **not** match the chosen cell's header, yet the binder still chose that cell and reported `wrong_cell` rather than `not_bindable`. The chosen cell is reached by value match first, so a value collision can select a cell in a column that does not name the claimed metric at all. |
| **H-4** | `src/evidence/represent_layout.py:96` (restated, now quantified) | Multi-level headers remain unrepresentable, and STRUCT-1 still fails at L2. On this corpus the gap costs **0** of the 536 B-BIND claims, so it is real but not currently load-bearing. |
| **H-5** | `diagnostics/funnel/classify_bindings.py` (this diagnostic) | `value_occurrences_in_paper` counts attached cells whose value matches **any** of the claim's numeric anchors, not the one specific anchor that produced the candidate. For a claim carrying several numbers the count is an upper bound. |

Carried forward unchanged: G-1 … G-4 (`ownership_warn_v1.md` §12), F-1 … F-5
(`claims_explicit_v1.md` §8), D-1 … D-7 (`funnel_142_3_0.md` §8). None fixed.

---

## 10. Artifacts

Committed in `out/binding_breakdown/`: `bbind_subreasons.csv` (536 rows, one per B-BIND claim,
with sub-reason, binding-stage outcome, extracted metric, `value_occurrences_in_paper` and full
evidence JSON), `btable_check.csv` (207 rows), `binding_breakdown.json`,
`classifier_validation.json`, `claim_ledger.csv`, `rejection_ledger.csv`, `binding_review.csv`,
`buckets.json`, `counts.json`, `output_hashes.json`, `run_metadata.json`.

Over the 5 MB threshold, gitignored, SHA-256 recorded per the standing rule; both regenerate
deterministically from `run_funnel.py`:

| file | bytes | sha256 |
|---|--:|---|
| `out/binding_breakdown/trace.jsonl` | 14,103,621 | `f1f757c5772ac2075688396982731ad8447b9236b3aa54866647426006ae1134` |
| `out/binding_breakdown/results.json` | 8,077,591 | `0de9d5f7750c9b37f60725511dc334f8edf6110f56d26aad0ea42cf0bdd59bc8` |
