# PHASE 4 — DENOMINATOR RECONCILIATION

Ground truth: Prakash's 85 binary labels in `runs/phase3_label_assist/human_audit.md`.
They supersede every provisional label, judge output and Phase 3 suggestion in the repo. No
machine label is used as a substitute for a human label anywhere in this phase.

## Header

| | |
|---|---|
| commit | `56ea5038f50937dcdc3a88fe8b9c905225b3c07e`, branch `claude-code-verification` |
| seed | 42 (Phase 3 sampling seed; carried, not re-drawn) |
| corpus | canonical 60 → 34 full-text papers, **31 long** (3,900 long-paper anchors). Paper ids in `PHASE2_LADDER.md` header. |
| harnesses | `phase4_step0.py` (parse/verify), `phase4_denominator.py` (A/B/C). `phase2_ladder.py` **imported** — delivery flags consumed, measurement not reimplemented. |
| input files read | `runs/phase3_label_assist/human_audit.md` · `.../routing.json` · `.../judgments.json` · `runs/phase3_composition/sample_unnamed.json` · `.../sample_named.json` · `runs/retrieval_recall/anchors.json` · `runs/phase2_ladder/per_anchor.json` · `runs/phase2_ladder/ladder.json` · `runs/prodab-20260902T004416Z/canonical/processed/chunks.json` |
| output | `runs/phase4_denominator/{human_labels.json, step0_report.json, detector_scoring.json, phase4_results.json}` |
| labels | binary. **N is the malformed signal.** Four-way Phase 3 buckets remain deferred. |

---

## STEP 0 — PARSE AND VERIFY

**0.1 — ids present in the audit sheet: 85, no duplicates.**
`U01–U19, U21–U26, U28–U35, U38–U60` (55 Task A) and `N01–N30` (30 Task B).

**0.2 — answered: 85. Blank: 0. Ambiguous: 0. Duplicated: 0. Unparseable: 0.**
No problem ids; nothing to quote.

**0.3 — Y / N / UNCERTAIN counts**

| | Y | N | UNCERTAIN |
|---|--:|--:|--:|
| Task A (is this a real extracted fact) | 30 | 25 | 0 |
| Task B (does this name belong to this value) | 9 | 21 | 0 |

**0.4 — exact n, established from the artifacts**

| | on sheet | parsed |
|---|--:|--:|
| Task A | 55 | **55** |
| Task B | 30 | **30** |

**Task A is n=55, not 60.** It is reported as 55 everywhere below and never as 60.

**0.5 — the 5 ids absent from the sheet**

`U20, U27, U31, U36, U37`. Provenance established from `routing.json`: all five were routed
`PROVISIONAL_N` by the label-assist harness, so by design they never reached the sheet.

| id | rules fired | provisional |
|---|---|---|
| U20 | `R4_BARE_SECTION_NUMBER` | N |
| U27 | `R2_CITATION_MARKER`, `R3_EMPTY_OR_SUBTOKEN` | N |
| U31 | `R2_CITATION_MARKER` | N |
| U36 | `R1_DOI_URL_SUBSTRING` | N |
| U37 | `R4_BARE_SECTION_NUMBER` | N |

All five are recorded **UNAUDITED**, assigned no label, and excluded from every human-label
denominator in this phase.

**STEP 0 GATE: PASS** (85 ≥ 85, zero problems, zero duplicates).

---

## A. AGREEMENT — process diagnostics only

No kappa. Every category is under 50, per the directive. Raw agreement only.

### A1 — human vs the two judge framings

| source | comparable n | agreements | disagreements | of which source UNCERTAIN | raw agreement | excluded (no source label) |
|---|--:|--:|--:|--:|--:|--:|
| `framing_1` | 85 | 50 | 35 | 0 | **58.8 %** | 0 |
| `framing_2` | 85 | 42 | 43 | 0 | **49.4 %** | 0 |

Every sheet item has a judge record for both framings, so nothing was excluded. The judge
never returned UNCERTAIN on these 85.

Framing 2 is at 49.4 % — indistinguishable from a coin flip on a binary task. The two framings
agreed with each other 71.1 % of the time (Phase 3 harness), but that agreement was not
agreement with the human.

### A2 — human vs the 6 provisional-N items

| | |
|---|---|
| provisional-N ids | `U20, U27, U31, U36, U37, U52` |
| labelled by the human | `U52` only |
| **overlap n** | **1** |

**The overlap is n=1. No rate is computed and none should be read into this.** The single
observation: `U52` — human **N**, provisional **N**, rule `R4_BARE_SECTION_NUMBER`. Five of the
six provisional-N items were never audited, which is exactly the blind spot the 20 % re-audit
was meant to probe and could not, at that sample size.

### A3 — how the human labelled the existing framing groups

Groups taken from the harness as recorded, not recomputed.

| group | n total | n human-labelled | human Y | human N |
|---|--:|--:|--:|--:|
| framings **disagreed** | 26 | 26 | **16** | 10 |
| framings **agreed** | 64 | 59 | 23 | **36** |

Where the two framings disagreed, the human called 16 of 26 **Y** — real facts. Where they
agreed, the human called 36 of 59 **N**. The 5 unlabelled items in the agreement group are the
provisional-N five.

### A4 — U52, the blind re-audit item

| field | value |
|---|---|
| human label | **N** |
| deterministic status | `OBVIOUS_MALFORMED`, rule `R4_BARE_SECTION_NUMBER` |
| framing_1 / framing_2 | N / N |
| route | `PROVISIONAL_N`, `in_blind_audit_sample: true` |
| framing_1 reason (verbatim) | "The text does not contain a fact but rather a section title." |
| framing_2 reason (verbatim) | "The text includes additional context that makes it unsuitable as a standalone claim." |

**Single observation, n=1. This is explicitly NOT an audit and is not generalised.** One
provisional-N item was checked and it held. Nothing follows about the other five.

---

## B. THE DENOMINATOR

### B1 — the MALFORMED detector, derived from the human Task A labels

Rules only. No model, no LLM, no learned or tuned threshold. Scored once; no rule was adjusted
after the score was seen.

| rule | fires when |
|---|---|
| `M1_CITATION_NUMERAL` | the window carries a bibliography marker (`pp.`/`pages` + range, `vol(issue):page`, `In: Proceedings`, `(eds.)`, `arXiv:NNNN.NNNNN`, `URL http…`) **and** the value is one of the numerals harvested from those citation patterns |
| `M2_SECTION_NUMBER` | the collapsed window opens with `<value>. Capital`; or opens with any section number and `<value> Capitalword` appears; or the value is `d.d` and `in <value>` appears (cross-reference) |
| `M3_PSEUDOCODE_LINE` | `<value>: Capital` appears — a numbered algorithm line label |
| `M4_SUBTOKEN_OF_LONGER_NUMBER` | **every** occurrence of the value in the window is adjacent to a digit or a digit-borne `,`/`.` — i.e. it is only ever a fragment of a longer number |
| `M5_VALUE_NOT_IN_TARGET_CHUNK` | the value does not occur in its own target chunk at all |
| `M6_LICENCE_VERSION` | the window says "licensed under" / "Creative Commons" and the value is `d.d` |

**Convergence with the label-assist rules — reported as a finding, not acted on.** `M2` ≈
`R4_BARE_SECTION_NUMBER` and `M4` ≈ `R3_EMPTY_OR_SUBTOKEN` converged independently on the same
structure. `M1` is broader than `R2_CITATION_MARKER`: the human labels show the mass is in
bibliography *numerals* (volumes, page ranges, article numbers), not only bracketed markers.
`M5` and `M6` are new — `M5` is the rule I deliberately withheld in Phase 3 as outside that
brief's four-rule list, and the human labels support it (5 of the 6 unlocatable items are N).
**`R1_DOI_URL_SUBSTRING` has no counterpart here**, because its only sample instance is `U36`,
one of the 5 UNAUDITED items. No human label existed to derive it from, so it was not derived.

### B2 — scored against the human Task A labels

**n = 55** (not 60).

| | predicted N | predicted Y |
|---|--:|--:|
| **human N** | TP 20 | FN 5 |
| **human Y** | FP 1 | TN 29 |

**Precision 0.9524 · Recall 0.8000 · n = 55.**

- False positive (1): `U43` — the only unlocatable item the human called **Y**. `M5` fires on it.
- False negatives (5): `U01`, `U04`, `U21`, `U28`, `U58`.

### B3 — GATE

Precision **0.9524 ≥ 0.80. GATE PASSES.** The detector is applied corpus-wide.

### B4 — applied to all 3,900 long-paper anchors

No classification was inspected or overridden; no model was used.

| | |
|---|--:|
| total long-paper anchors | **3,900** |
| MALFORMED | **1,167** |
| non-MALFORMED | **2,733** |
| fraction | **1,167 / 3,900 = 0.2992 (29.9 %)** |

### B5 — restated on the cleaned denominator

Old n = 3,900 · cleaned n = 2,733. Delivery flags are `phase2_ladder.py`'s measured output.

| quantity | OLD | CLEANED | CHANGE | status |
|---|--:|--:|--:|---|
| production delivery (= cell A, long) | 0.0713 | 0.0677 | −0.0036 | moved by cleaning (negligibly) |
| R@10 | 0.9382 | 0.9480 | +0.0098 | moved by cleaning (negligibly) |
| cell A delivery | 0.0713 | 0.0677 | −0.0036 | moved by cleaning |
| cell B delivery | 0.6118 | 0.5917 | −0.0201 | moved by cleaning |
| cell C delivery | 0.0174 | 0.0223 | +0.0049 | moved by cleaning |
| cell D delivery | 0.3059 | 0.3004 | −0.0055 | moved by cleaning |
| cell E delivery | 0.9385 | 0.9484 | +0.0099 | moved by cleaning |
| cell A ratio-to-random | 1.26× | — | — | **not recomputable from available artifacts** |
| cell B ratio-to-random | 1.23× | — | — | **not recomputable from available artifacts** |
| cell C ratio-to-random | 1.279 | **1.574** | **+0.295** | moved by cleaning |
| cell D ratio-to-random | 1.347 | 1.271 | −0.075 | moved by cleaning |
| cell E ratio-to-random | 20.658 | 20.068 | −0.590 | moved by cleaning |
| B4 §results ratio | 0.317× | 0.388× | +0.071 | moved by cleaning (n 310 → 211) |
| B4 §references ratio | 0.000× | 0.000× | 0.000 | unchanged (n 489 → 258) |
| B4 §conclusion ratio | 0.000× | 0.000× | 0.000 | unchanged (n 157 → 102) |
| B4 §discussion ratio | 0.000× | 0.000× | 0.000 | unchanged (n 118 → 64) |
| B4 prose ratio | 0.887× | **1.268×** | **+0.381** | moved by cleaning — **crosses the random line** (n 2,127 → 1,260) |
| B4 table ratio | 0.332× | 0.383× | +0.051 | moved by cleaning (n 1,129 → 974) |

**Why cells A and B ratios are not recomputable.** Those two cells' budget is the per-paper
*union* of 5 generic queries × top-k. `phase2_ladder.py` did not persist the per-paper union
size — only its mean survives in `ladder.json` (13.2 and 127.4). The uniform-random null needs
the per-paper value, so the ratio cannot be recomputed on a subset without re-running the
retrieval. Stated rather than estimated.

### B6 — which conclusions survive, which move

**Survive unchanged:**

- **Phase 1's verdict.** The delivery gap is real and the drop is at the 5-query × top-3 union.
  Production delivery moves 0.0713 → 0.0677; R@10 moves 0.9382 → 0.9480. The gap is if anything
  marginally wider on clean anchors.
- **Phase 2's verdict — budget dominates.** Cell A → cell B still jumps 0.068 → 0.592 on the
  cleaned denominator. The budget effect is untouched by cleaning.
- **The oracle ceiling.** Cell E stays ~20× random (20.66 → 20.07).
- **Phase 3's zero-delivery finding.** References, conclusion and discussion remain at **exactly
  0.000×** after removing 40–47 % of their anchors as malformed. Not an artifact of junk anchors.
- **Phase 3's results/table finding.** Both remain far below random (0.388×, 0.383×).

**Move:**

- **Phase 3's "prose 0.89× — below random" becomes 1.27×, above random.** This is the one
  conclusion that changes sign. Roughly 41 % of prose anchors were malformed — reference-list
  numerals and section numbers living in prose — and they were dragging the prose figure under
  the random line. On clean anchors the title-only query beats random in prose and still loses
  badly in tables. `PHASE3_ANCHOR_COMPOSITION.md` is left unmodified; the contradiction is
  recorded here.
- **Cell C ratio 1.279 → 1.574.** The per-anchor field query looks meaningfully better than
  production once malformed anchors are out, rather than indistinguishable from it.
- **Phase 3's headline "83.4 % of anchors have no metric name" is not contradicted, but ~30 % of
  that denominator is now known to be malformed.** Reported, not restated — recomputing the
  named/unnamed split on clean anchors was not asked for in this phase.

---

## C. BINDING

### C1 — how often the extractor is wrong when it fires

From the 30 human Task B labels.

| | n | rate |
|---|--:|--:|
| fires and **correct** (Y) | 9 | |
| fires and **wrong** (N) | 21 | **0.7000 on n = 30** |
| of which unlocatable | 7 | |
| wrong, excluding unlocatable | 14 | **0.6087 on n = 23** |

**The 7 unlocatable cases are shown separately and are not counted as wrong by inference.** They
are counted as wrong because *the human labelled all seven N* (`N05, N09, N20, N25, N26, N27,
N30` — every one N in `human_labels.json`). That is the human's call, not a methodological
assumption, so no citation to prior methodology is needed or offered.

### C2 — does EVIDENCE_BINDING have real mass?

**Yes on these labels, but the n does not support a corpus-wide rate, and I am not claiming one.**

From the human labels and existing artifacts only:

- 14 of 23 locatable fires are wrong (60.9 %). These are not window artifacts — in each the name
  and the value are both genuinely present in the text and genuinely unrelated: a test-set size
  labelled `accuracy`, cents-per-query labelled `accuracy`, a confidence level labelled `F1`, an
  R² column labelled `Pearson`. The binding is wrong, not the retrieval and not the parse. That
  is `EVIDENCE_BINDING` by the directive's definition — the value is right, the attached
  identity is wrong.
- The 440-char window is a **contributing mechanism, not an explanation that dissolves the
  finding**. A narrower window would fix the distant-name cases; it would not fix the
  right-table-wrong-column cases, where the correct and incorrect names are both inside any
  plausible window.
- **What these labels cannot support:** a rate for the 644-item NAMED partition, let alone the
  corpus. n=30, one sample, every category under the directive's 50-item threshold. The honest
  statement is that binding failure is *present and frequent in this sample*, with a point
  estimate of 60.9 % on n=23 that should not be propagated.

---

## Data-quality note

- **5 unaudited ids** — `U20, U27, U31, U36, U37`. All routed `PROVISIONAL_N` by the label-assist
  harness, so they never reached the sheet. No label assigned; excluded from every human-label
  denominator. Task A is therefore **n=55**, and the B2 detector is built and scored on 55.
- **Blank / ambiguous / duplicate / uncertain labels: none.** All 85 parsed cleanly; zero
  UNCERTAIN in either task.
- **A2 is n=1.** Only `U52` overlaps the provisional-N set. Five of six provisional-N items
  remain unchecked, so the rules that produced them are supported by one observation.
- **Two ratio rows are not recomputable** (cells A and B), for the reason given in B5. They are
  marked as such rather than estimated.
- **Selection effect on the detector's score.** The 55 scored items exclude the 5 that the
  harness had already flagged as obviously malformed. The scoring set is therefore harder than a
  random draw from the sample, which if anything understates precision — but it also means the
  detector was never scored against the DOI/URL class, which is absent from the labelled set.
- Nothing in Phases 0–3 was modified. `labels.json`, `suggested_labels.json`, the audit sheet and
  all label-assist artifacts are intact.

---

## VERDICT

DENOMINATOR MATERIAL — 29.9% malformed, headline rates move by up to 0.38x (prose ratio-to-random 0.887 -> 1.268, crossing the random baseline) while every delivery rate moves by <= 0.02
