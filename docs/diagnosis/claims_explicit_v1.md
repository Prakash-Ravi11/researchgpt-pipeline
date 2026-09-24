# Explicit claim extraction — one bounded experiment for decision D3

One treatment, one variable. Decision D3 (NO_CLAIMS_REACH_BINDER, commit `77dd6aa`) selected
**explicit claim extraction** as the next action; this measures it. Nothing else changed.

Every number is `[measured]` from the two runs below, or `[derived]` by arithmetic from them.

| | |
|---|---|
| worktree / branch | `C:\Users\Praka\Downloads\rgpt-exp-parser` · `exp/parser-backend` |
| parent commit | `77dd6aa` (working tree clean at start — precondition PASS) |
| corpus | the same 21 PDF-path papers, `pymupdf4llm` arm, read-only by absolute path |
| control | `out/claims_legacy/` · `claim_extractor=legacy` |
| treatment | `out/claims_explicit/` · `claim_extractor=explicit` |
| LLM calls | **none** in either arm — the extractor is rule-based and the legacy arm reads a frozen cache |

---

## 1. The change made

**New module:** `experiments/document_evidence_pipeline/explicit_claims.py` — deterministic,
rule-based, no LLM. The unit is a sentence of body text.

**New flag:** `evidence_grounding.claim_extractor: legacy | explicit`, default **`legacy`**, in
`configs/staging_config.yaml`; `RGPT_CLAIM_EXTRACTOR` overrides it for one run.

**Dispatch:** at the single call site that produces claims,
`experiments/document_evidence_pipeline/parser_backend_measure.py:184-197`. The `legacy` branch
is the original expression unchanged. Nothing downstream of that line differs between arms.

**The contract, which is load-bearing.** `gate_paper` (`gate.py:601-611`) takes a **dict** whose
`results` is ONE string that it re-splits with `_SENT = re.compile(r"(?<=[.!?])\s+")`, keeping
sentences ≥ 12 chars containing a digit. `explicit_claims` therefore splits with that **same
`_SENT` object, imported not copied**, emits only sentences that pass those filters, and
guarantees each ends in `.`/`!`/`?` so joining and re-splitting is exactly the identity.
`build_record` asserts the round-trip itself. **`gate_paper` was not edited** (STOP CONDITION 6
not triggered).

**Rejection rules**, one reason code per rejected sentence: `IN_REFERENCES`,
`IN_ACKNOWLEDGMENTS`, `IN_TABLE_BLOCK`, `IN_CAPTION`, `NO_NUMBER`, `NUMBER_IS_LABEL`,
`CITATION_MARKER`, `YEAR`, `NUMBER_IN_NAME`. A claim is emitted when ≥ 1 standalone numeric
token survives; a token may carry a sign (including U+2212), a decimal, `%`, `±` or scientific
notation.

**Tests:** `experiments/document_evidence_pipeline/tests/test_explicit_claims.py` — **36 passed**,
covering the 7 NORM strings, `GPT-4-based metrics`, `F1 score`, `Table 2`, `[12]`, `(2021)`, a
references-section sentence, and the `_SENT` round-trip contract.

---

## 2. Control reproduction (STOP CONDITION 2)

`[measured]` from `out/claims_legacy/counts.json`:

| required | got | |
|---|--:|---|
| claims | 22 | PASS |
| entered the binder | 14 | PASS |
| papers holding an entered claim | 8 | PASS |
| bound | 0 | PASS |
| returned metrics | 3 | PASS |

Table side identical to the frozen baseline: 160 / 142 / 92 / 2187. The control is the same
run as before, reproduced under the new dispatch with the flag at its default.

---

## 3. Legacy vs explicit, side by side

`[measured]`

| | legacy | explicit |
|---|--:|--:|
| table blocks | 160 | 160 |
| backend grid returns | 142 | 142 |
| post-gate cell tables | 92 | 92 |
| attached cells | 2187 | 2187 |
| **claims total** | **22** | **2218** |
| **entered the binder** | **14** | **1754** |
| **bound** | **0** | **5** |
| **papers with ≥1 claim in the binder** | **8 / 21** | **21 / 21** |
| returned metrics | 3 | 0 |
| returned results | 1 | 597 |

The table half of the funnel is untouched, as intended — the treatment changes only which
sentences are offered to the gate.

Binding statuses, explicit arm `[measured]`:
`not_bindable` 1458 · `no_binding_call` 464 · `pdf_only` 189 · `wrong_cell` 69 ·
`not_a_table_claim` 33 · **`bound` 5**.

**`bound` moves 0 → 5.** That is the first time this programme has recorded a non-zero `bound`
count on real extracted claims. It is 5 of 1754, i.e. 0.29 % of claims that entered the binder.
`returned metrics` falls 3 → 0 because the explicit extractor emits no `metrics` field at all —
the 3 legacy "returned metrics" were metric *names* with no numeric anchor, which this extractor
rejects by design (`NUMBER_IN_NAME`).

---

## 4. Rejection totals

`out/claims_explicit/rejection_ledger.csv` — **10,769** rejected sentences `[measured]`:

| reason code | n |
|---|--:|
| `NO_NUMBER` | 6914 |
| `IN_REFERENCES` | 2002 |
| `NUMBER_IN_NAME` | 502 |
| `YEAR` | 386 |
| `IN_TABLE_BLOCK` | 275 |
| `CITATION_MARKER` | 255 |
| `IN_CAPTION` | 212 |
| `NUMBER_IS_LABEL` | 191 |
| `IN_ACKNOWLEDGMENTS` | 32 |
| **total** | **10,769** |

`[derived]` 10,769 rejected + 2,218 kept = 12,987 candidate sentences.

**STOP CONDITION 5 check:** 0 emitted claims come from a references section, a table block or a
caption `[measured]`. Claim block types are `paragraph` 2208 and `heading` 10; no claim carries
`section == references`, any `acknowledg*` section, `block_type == table`, a caption block type,
or a `Table N:` / `Figure N:` opener.

**STOP CONDITION 4 check:** claims passed to `gate_paper` = **2218**; evidence items `gate_paper`
iterated = **2218**; per-paper mismatches across all 21 papers = **0** `[measured]`.

---

## 5. Bucket counts

Over the **1749** claims that entered the binder and did not bind (`[derived]` 1754 − 5).
Buckets are computed with the binder's own comparator (`gate._has`).

| bucket | legacy | explicit |
|---|--:|--:|
| **B-BIND** — value is in an attached cell | 4 | **536** |
| **B-TABLE** — value only in gate-rejected / fallback table text | 0 | **207** |
| **B-UNDETECTED** — triage `TABLE_POSSIBLY_UNDETECTED` | 0 | **95** |
| **B-PROSE** — triage `PROSE_ONLY` | 10 | **858** |

B-BIND by terminal reason code, explicit arm `[measured]`:

| terminal reason | n |
|---|--:|
| `OWNERSHIP_UNVERIFIED` | 252 |
| `RETURNED` | 143 |
| `BINDING_WRONG_CELL` | 69 |
| `EVIDENCE_SPAN_NOT_FOUND_IN_PAPER_CHUNKS` | 58 |
| `ATTRIBUTED_TO_CITED_WORK` | 14 |

Also `[measured]`:

- **bound: 5**
- **bindings with `sign_match=false`: 0.** 74 binding rows were reviewed; only **5** carry a
  cell value that a sign can be compared against, and all 5 match. The other 69 are
  `wrong_cell` rows, for which the gate records no cell value at all — reported as *not
  assessable* rather than as mismatches (defect F-3 below).
- **papers with ≥1 claim entering the binder: 21/21** (legacy: 8/21).

### Largest bucket and the mapped next change

**Largest bucket: B-PROSE, n = 858** (49 % of the 1749 non-binding claims).

Pre-registered mapping → **claim classification**.

Named, **not implemented**. The `TABLE_POSSIBLY_UNDETECTED` / `PROSE_ONLY` split is **heuristic**:
a claim is called `TABLE_POSSIBLY_UNDETECTED` when its page carries more distinct `Table N`
labels in prose than the page has detected table blocks. It is a triage signal, not a
measurement of undetected tables.

---

## 6. Positive control (STOP CONDITION 3)

Re-run after the change `[measured]`:

- **L1 = 12/12 PASS**
- **L2 = 11/12 PASS**
- Only failure: **STRUCT-1**, terminal stage `B4_binding`, reason `NOT_BINDABLE`.

Unchanged from the pre-change run, as required.

---

## 7. Stop conditions

| # | condition | result |
|---|---|---|
| 1 | precondition (HEAD `77dd6aa`, clean tree) | PASS, not triggered |
| 2 | legacy reproduces 22 / 14 / 8 / 0 / 3 | PASS, not triggered |
| 3 | positive control L1 12/12, L2 11/12, STRUCT-1 only | PASS, not triggered |
| 4 | claims passed ≠ claims iterated | 2218 = 2218, not triggered |
| 5 | a claim from references / table block / caption | 0, not triggered |
| 6 | contract unmatchable without editing `gate_paper` | `gate_paper` untouched, not triggered |

No stop condition fired.

---

## 8. Found, not fixed

| id | location | defect |
|---|---|---|
| **F-1** | `src/evidence/represent.py` section labelling (pre-existing) | **155 of 2218 explicit claims (7.0 %) are bibliography lines** that escaped `IN_REFERENCES` because their block's *section label* is itself junk — 7 distinct labels such as `'2017. url http://arxiv.org/abs/1711.0510'` and `'2023. url http://arxiv.org/abs/2305.0193'`, carrying 235 claims between them. The heading regex promotes a reference-list line to a section name, so a section-name test cannot see that the block is bibliography. This does not trip STOP CONDITION 5 as written (no such block is labelled `references`), but it is a real precision leak in the explicit arm and inflates the 2218. |
| **F-2** | `diagnostics/funnel/funnel_trace.py` (this diagnostic's own trace layer) | `json.dumps` leaves U+2028 / U+2029 / U+0085 unescaped inside string values, while `str.splitlines()` treats them as line breaks — so a JSONL reader using `splitlines()` splits one record into two and the parse fails. Fixed in the trace layer (escape on write, `split("\n")` on read); recorded because any future reader of these files can hit the same thing. |
| **F-3** | `src/evidence/gate.py:476-487` | The `wrong_cell` verdict records `candidate: {row, col}` but **never the candidate cell's value**. A reviewer cannot see what number was actually at the cell the binder rejected, so `sign_match` and any value-level review are impossible for all 69 `wrong_cell` bindings. Only the 5 `bound` rows are reviewable. |
| **F-4** | `experiments/document_evidence_pipeline/explicit_claims.py` (this module) | `YEAR` rejects any bare 4-digit integer in [1900, 2099]. A legitimate measured quantity in that range (`2048` tokens, `1920` pixels, a sample count) is rejected as a year. 386 sentences were rejected on this rule; the false-positive share is unmeasured. |
| **F-5** | `experiments/document_evidence_pipeline/explicit_claims.py` (this module) | A sentence shorter than 12 characters is rejected as `NO_NUMBER` regardless of whether it contains a digit, because the allowed reason-code vocabulary has no "too short" code. The count is folded into `NO_NUMBER` 6914 and cannot be separated from genuine no-number rejections. |

Carried forward unchanged from `docs/diagnosis/funnel_142_3_0.md` §8: D-1 through D-7, none fixed.

---

## 9. Artifacts

Committed: `claim_ledger.csv`, `rejection_ledger.csv`, `binding_review.csv`, `buckets.json`,
`counts.json`, `output_hashes.json`, `run_metadata.json` in both `out/claims_legacy/` and
`out/claims_explicit/`.

Two treatment-arm artifacts exceed the 5 MB commit threshold and are gitignored; their
SHA-256 is recorded here and they regenerate deterministically with
`run_funnel.py --arm pymupdf4llm --out claims_explicit --trace --claim-extractor explicit`:

| file | bytes | sha256 |
|---|--:|---|
| `out/claims_explicit/trace.jsonl` | 13,467,284 | `4bc082f36b51037c784a4e3fac6d1b8c4dfbaad2307a82d8bc6b205177d04233` |
| `out/claims_explicit/results.json` | 8,077,594 | `dd660be193ba45703d5bf7b59a8500b50235824befaec070940a38ede526e494` |

Control-arm equivalents are under 5 MB and are committed:
`out/claims_legacy/trace.jsonl` 2,611,363 B
`f69e2ff2fab96a5ea3c390ee5860fcc0eeb2aab52c86fbb7519714115134d48e`;
`out/claims_legacy/results.json` 176,134 B
`76e2f42177effde187b6bbd423385edc1b31247e47bc77098653e0c876fb1ef8`.

---

## 10. What this experiment does and does not establish

It establishes `[measured]` that explicit extraction removes the D3 condition: claims entering
the binder go 14 → 1754, papers reaching the binder go 8/21 → 21/21, and `bound` becomes non-zero
(5) for the first time. It does **not** establish that those 5 bindings are correct — that is
what the empty `human_label` column in `binding_review.csv` is for, and it is unfilled. The
per-claim precision of the extractor is likewise unmeasured beyond F-1's 7.0 % bibliographic leak.

No next change is implemented. B-PROSE → claim classification is named for human review only.
