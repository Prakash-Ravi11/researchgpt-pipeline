# PHASE 10 — Binder v2: pre-registration (committed before any v2 measurement)

**Starting commit: `afe1488`** (`exp/phase10-binder`).
- Its code equals `acceptance/pre-phase10` (`6ed2434`) and `claude-code-verification` (`2d61f3c`).
- The defaults are `fallthrough_policy = table_value_guard` and `borderless_policy = off`.
- At this commit no v2 code exists. The failure map (`FAILURE_MAP_10.md`, STEP 0) is committed.

## A. Criteria and decision (verbatim from the brief)

> CRITERIA (per arm)
>   S1 zero wrong binds:
>      - on the 55 pairs/18 claims: bound to a cell other than the gold cell;
>      - on Sweep A, Sweep B and product fields: every NEW bind vs legacy is audited against the PDF
>        (crop + text layer, two independent agent checks; any disagreement counts as WRONG).
>   S2 zero verified binds lost vs legacy, in any unit or representation setting.
>   S3 legacy byte-identical to the starting commit: 30/30 PDFs, 55-pair evaluation, newline canary 0.
>   Reported, NOT criteria:
>   - correct gains;
>   - gold-cell candidate recall WITH the median and max candidate-set size;
>   - abstention codes;
>   - per-claim earliest-failure-stage transitions;
>   - the ablation table;
>   - RETURNED-with-verified-bind counts at gate level;
>   - the product-field changes.
>
> STEP 4 — DECISION (mechanical)
> - v2 passes S1–S3 with at least one correct gain -> commit binder_policy: v2 in staging_config.yaml and
>   acceptance_config.yaml.
> - v2_llm is enabled instead only if it ALSO passes S1–S3, adds correct gains beyond v2, and its cache
>   replay and fresh run agree on every decision.
> - Any S1 or S2 failure -> no enable; list every failing item.
> - Zero correct gains -> no enable; the report gives the earliest-failure-stage distribution and names the
>   stage that blocks.
> - Never enable borderless. If gains appear only under R-eval, report them as binder capability that is
>   blocked in the product by representation.

Global rules from the brief also apply:
- no claim- or paper-specific logic;
- no gold, evaluator-scoring or 09A/09B artifact change;
- Python 3.10 and 3.13;
- no new dependency;
- STOP if the LLM returns a cell, value or span that is not in its input;
- STOP if a diagnosed failure is "fixed" twice without the measured outcome changing.

## B. Arms
All arms pin `RGPT_FALLTHROUGH_POLICY=table_value_guard` (the frozen product default) and
`RGPT_BORDERLESS_POLICY=off`. Representation never changes inside an arm: arms only gate cached records.
- **legacy**: `binder_policy = legacy`, i.e. the starting commit's binder.
- **v2**: `binder_policy = v2`, i.e. the deterministic Binder v2 (§D).
- **v2_llm**: `binder_policy = v2_llm`, i.e. v2 plus the LLM judge (§E). It runs three times:
  - fresh run 1, which fills the cache;
  - a replay from the cache;
  - fresh run 2.
- **Ablations**: v2 with one mechanism disabled at a time, through `RGPT_BINDER_V2_DISABLE`. The mechanisms
  are:

  | Mechanism | What it does |
  |---|---|
  | `caption_quantity` | quantity linked through the caption, row label or cell text, not only the column header |
  | `column_subject` | subject matched against column headers (methods as columns) |
  | `own_alias` | "ours", "our method", "proposed" and declared own-method names |
  | `synonyms` | plural forms, R²/R2, and the one synonym table |
  | `count_attribute` | a count claim links to a count header |
  | `multi_binding` | comparison and multi-value required bindings; disabled, only the claim's first table-relevant value is bound |
  | `table_mention` | relevance from a "Table N" mention (the R4 port) |
  | `gate_fixes` | the two gate fixes of §D11 |

## C. Representations and units
- **R-prod**: the L0 records in `runs/p09b_run` (legacy representation, borderless off).
- **R-eval**: the L1 records in `runs/p09b_run` (borderless consensus records; evaluation only).
- **R-oracle**: for C012, C057 and C058 only, labelled an **upper bound**. This is the 09A O12 construction:
  the R-prod records of the paper, where the target table's caption-block chunks carry only the claim's gold
  target cells.
- **Units**:
  - the 55 CANONICAL pairs and the 18 REAL claims, through the unchanged phase 08 evaluator
    (`postfix_evaluate.evaluate`, with before = after = the setting's records);
  - Sweep A (the 48 harvested claims in the 16 papers);
  - Sweep B (every chunk's text of the 16 papers);
  - the **product fields**: `acceptance_pre10/pre_gate_summaries.json`, gated on the acceptance chunks (equal
    to R-prod for the 12 gold papers).

  The evaluator routes through `gate.structural_bind` and `gate.gate_paper`, so it measures each arm.

## D. Binder v2 — operational definitions (deterministic)
- **D1 Router (`gate.py`, additions only).**
  - `_binder_policy()` resolves `RGPT_BINDER_POLICY`, then the `binder_policy:` line of
    `configs/staging_config.yaml`, then `legacy` (the code shape of the other flags).
  - With anything other than `legacy`:
    - `structural_bind` returns `binder_v2.structural_bind_v2`;
    - `gate_paper` returns `binder_v2.gate_paper_v2`;
    - `_gate_value` abstains with `structural_binding["abstain_code"]` when v2 sets it.
  - With `legacy` the old code runs unchanged.
- **D2 Values (ClaimFrame A).**
  - Numbers are read with the guard's token rule (PREREG_09B D3), with positions kept.
  - A value mention has the anchor shape: a decimal, or an integer with at least 2 digits.
  - These are not value mentions:
    - years (19xx/20xx);
    - numbers in square brackets;
    - numbers after Table, Fig., Figure, Section or Eq.;
    - a CI level ("95% CI").
  - Structure is parsed and kept:
    - ± uncertainty;
    - an interval in brackets (CI);
    - a range ("a–b", "between a and b");
    - a unit (%, mm, cm, cm2, cm3, mm3, s, ms, min, weeks, days, years, kg, ml, T);
    - a threshold cue (exceed, above, over, at least, more/greater/less than, below, under, up to). A
      threshold mention is never a binding.
- **D3 Cells (C).**
  - Every attached cell of the paper is considered.
  - The cell text is read with `borderless.norm`, so whitespace wraps and markup do not split numbers.
  - The parsed cell keeps: central value, ±, interval, range, unit, the non-numeric "cell text" (e.g.
    "DSC: 83.79%"), and the numbers per "label: value" part of a multi-metric cell.
  - Context per cell:
    - table (caption, page, "Table N" label);
    - row label;
    - the column header levels (split at " / ");
    - caption.
- **D4 Label matching.**
  - A label's core is the label without bracketed parts, e.g. "SRI-exposed (n = 62)" → "SRI-exposed".
  - A label matches the claim when the concatenation of its alphanumeric tokens (lower case) equals the
    concatenation of a contiguous run of claim tokens. So "Mas k" matches "mask" and "Fetal-SynthSeg" matches
    "FetalSynthSeg".
  - A match inside a longer matched label is dropped (maximal match).
  - Labels shorter than 2 characters never match.
- **D5 Paper-local aliases (B)**, each with a verbatim evidence span from the paper:
  - Own-method:
    - claim references: "our method/model/approach/network/framework/system/pipeline/module", "ours",
      "the proposed …";
    - own labels: cell labels containing "ours" or "proposed";
    - declared names: X in "we propose/present/introduce/develop X", "called/named/termed X". Two or more
      distinct declared names make the own-method ambiguous, which gives `ambiguous_subject` whenever a
      binding needs it.
  - Group aliases: a label word followed by a noun in the paper text (e.g. "unexposed controls") makes that
    noun an alias of the label. The evidence is that span.
  - Quantity synonyms (one documented table): {dice, dsc, dice score, dice coefficient, dice similarity
    coefficient}. Plural "-s" is stripped. R² ≡ R2. No global metric list acts as the gate.
- **D6 Links of a claim value to a candidate cell.**
  - **value**: the value is equal to the cell's central value or one of its numbers, by token equality. If
    both sides carry ± or an interval, those must also be equal. A unit must not conflict; % never matches
    a fraction unless the cell context states %.
  - **quantity**: a claim term (D4, D5 synonyms) matches the cell's column header, row label, caption or cell
    text. A count claim (an integer followed by a plural noun) also links to a count header ("Number of …",
    "No. of …", "n", "#").
  - **subject**: a claim label match (D4) to the cell's row label or a column header level, or an
    own-method/alias link (D5). It must be different evidence from the quantity link.
  - **qualifier conflict**: the value's local context names another label on the same axis and level of the
    same table, and not the cell's own label.
  - **table mention**: the claim names exactly one "Table N" and the cell's table is another one.
  - Local context: the clause of the value (split at `;`, "while", "whereas"), plus the phrase the value
    governs ("for …", "by …", the parenthetical it sits in).
- **D7 Eligibility.** Value, quantity and subject all linked, with no qualifier conflict and no table-mention
  conflict.
- **D8 Choice (D/E).**
  - Among the eligible cells for one value, a cell wins if it is not dominated in every dimension: subject
    (local over global, label over alias), quantity (header, then row/cell text, then caption, then count
    type), qualifier matches, and table mention.
  - There is no sum, no order tie-break and no proximity tie-break.
  - Two or more non-dominated cells give an abstention:
    - `ambiguous_subject`: they differ in subject;
    - `ambiguous_quantity`: they differ in quantity;
    - `duplicate_quantity_context`: different tables, same subject and quantity;
    - `insufficient_qualifier`: same table, they differ only on a qualifier axis;
    - `duplicate_value`: otherwise.
- **D9 Required bindings.**
  - A value mention is required when one of its value-matching cells has any quantity or subject link.
  - **SINGLE_CELL**: 1 required binding.
  - **MULTI_CELL**: more than 1, one subject.
  - **COMPARISON**: more than 1, two or more subjects.
  - **PARTIAL_COMPARISON**: some, but not all, required bindings bound. It is never counted as bound and
    abstains with `partial_binding`; ambiguity codes take precedence.
  - Statuses:
    - no required binding and no value-matching cell → `not_a_table_claim`;
    - value-matching cells but none required → `not_bindable` (the guard applies);
    - a required value whose only value+quantity cells name a different entity on the subject axis → legacy
      `wrong_cell`.
- **D10 Verifier (F).** It is re-run from the raw cell and claim for every binding, and checks that:
  - the cell is an attached table cell, not prose or caption;
  - the value is in the cell;
  - the subject is linked by text or alias span;
  - the quantity is linked;
  - units and qualifiers agree;
  - every required binding passed.

  Any failure → `deterministic_verification_failed`.
- **D11 Gate fixes, only under v2/v2_llm.**
  - The ablation cue must be a standalone word: a hyphen-joined method name like "X-CAM" is not a cue.
  - Sentence splitting does not split after "et al.".
  - Table type and splitting are otherwise unchanged.

## E. v2_llm (H)
- **When.** The judge is called only when D8 leaves 2–5 eligible cells, or when a value has value and quantity
  links but no subject link (an unresolved alias).
- **Model.** Ollama `qwen2.5:7b`, temperature 0, seed 42, through `summarize.call_ollama_json`. The cache is
  primed once (`prime_ollama_cache`) and calls are serial.
- **Input.** The ClaimFrame and the candidate list (ids and context).
- **Output.** JSON only: `{"choice": "<id>|none", "span": "<verbatim text from the paper>"}`.
- **Checks.** The verifier rejects an id that is not in the list and a span that is not verbatim in the paper's
  chunks. Either event is also a phase **STOP** (global rule). An accepted choice must then pass D10, with the
  span as its alias evidence.
- **Cache.** `src/evaluation/binder_10/llm_cache.jsonl`, one line per request/response, keyed by the SHA-256 of
  the request.
- **Agreement.** The replay and fresh run 2 must agree with fresh run 1 on every decision. Disagreements are
  listed.

## F. Measurements
- **bind.**
  - For pairs and claims: the whole-claim `structural_bind` (as routed) has status `bound`.
  - For sweep items and product fields: the gate item's binding status is `bound`.
- **correct gain.** A pair or claim that is `bound_correct` (phase 08 evaluator) under v2 or v2_llm and not
  under legacy, per representation.
- **wrong bind (S1, gold units).** Status `bound` with a cell that is not among the unit's reconstructed gold
  target cells.
- **new bind (S1, sweeps and product).**
  - The item is bound under the arm and not bound under legacy, or bound to a different cell.
  - Every new bind is audited against the PDF: the item text and the bound cell's table crop, plus the text
    layer.
  - Two independent agent checks answer one question: does the item's value refer to the same quantity, for
    the same subject, as the bound cell?
  - Any disagreement, or any "no", is WRONG. All audits are machine-assisted and not human-validated.
- **lost verified bind (S2).**
  - Pairs and claims: `bound_correct` under legacy and not under the arm.
  - Sweeps and product: bound under legacy and not under the arm.
  - Every representation and unit counts.
- **S3.**
  - `legacy` gate records (every harvested claim plus every chunk text, `gate_paper` output) are identical to
    the starting commit's on 30/30 PDFs.
  - The 55-pair evaluation shows 0 differences.
  - The newline canary is 0: no attached cell value contains "\n" in the R-prod and R-eval records.
- **Reported:**
  - correct gains;
  - gold-cell candidate recall, i.e. whether a gold cell is among the value-matching candidates, with the
    median and max candidate-set size;
  - abstention codes;
  - per-claim earliest-failure stage, legacy → v2;
  - the ablation table;
  - gate-level RETURNED-with-verified-bind;
  - product-field changes vs legacy.

## G. Disclosure
- The mechanisms were chosen after STEP 0, which read the 14 failing gold claims. The 55 pairs remain the
  evaluation set:
  - the code holds no claim id, paper id or string from them;
  - the one synonym table (D5) and the unit and cue lists (D2) are general vocabulary, written down here.
- Correct gains on the gold units are therefore an optimistic estimate. The sweeps and product fields, with
  their PDF audits, are the out-of-sample check.
