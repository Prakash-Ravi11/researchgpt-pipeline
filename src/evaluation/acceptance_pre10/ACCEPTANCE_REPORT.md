# Product acceptance before Phase 10 (phase 10 package, Part 2)

**Result: the product returns 0 table-verified values on the 12 gold papers in either arm. Only 3 of the 18
gold claims reach the gate at all.**

The two arms:
- arm A: `fallthrough_policy = legacy`, `borderless_policy = off`;
- arm B: the frozen config (`table_value_guard`, `off`).

Between them, 5 fields change. Only one changes its outcome: an unverified return that arm B abstains on.

Everything is counted over the 12 gold papers and their 18 gold claims. Gold labels are machine-assisted and not
human-validated.

Branch `acceptance/pre-phase10`, created from `claude-code-verification` (`2d61f3c`, the merged 09B freeze).

## 1. Setup (no network)
- **Config.** `configs/acceptance_config.yaml` is a copy of `configs/staging_config.yaml` with these changes:
  - paths under `data_acceptance/` (gitignored, `6d53d4b`);
  - collection `researchgpt_acceptance_pre10`;
  - `fallthrough_policy: table_value_guard` and `borderless_policy: off` written out.
- **Seed** (`run_acceptance.py seed`):
  - the 12 gold PDFs were copied from their hash-pinned paths in `pdf_identity_manifest_v2.csv`, with
    SHA-256 verified 12/12;
  - their acquisition records are the ones the 55-pair evaluation used (all `representation_type: pdf`,
    `FULL_TEXT`), with `pdf_path` pointing to the copies.
- **Stage functions that ran** (`run_acceptance.py stages`, once):

  | Stage | Function | Seconds |
  |---|---|---|
  | 2 | `src.processing.pdf_parser.run_processing` | 20.9 |
  | 3 | `src.embedding.build_index.run_embedding` (BGE-M3, cached, `HF_HUB_OFFLINE=1`) | 102.3 |
  | 4 | `src.summarization.summarize.run_summarization` | 586.6 |

  Stage 1 (collection) did not run. Stage 4 ran with `evidence_grounding.enabled = False` in the dict passed
  to it. Its own Stage 5 hook (`summarize.py:1344-1346`) therefore did not run, and the pre-gate summaries
  could be saved. Extraction never reads that flag: `retrieval_aware.py:301` keys on the chunk schema.
- **Qwen.** `qwen2.5:7b`, digest `845dbda0ea48ed74…`, temperature 0, seed 42, local Ollama. All 12 papers
  were extracted (`_conformance: conformant`), 0 were `_extraction_failed`, and all used content-aware
  selection.
- **Representation.** The acceptance `chunks.json` equals the 55-pair evaluation's L0 records
  (`runs/p09b_run`) on **12/12 papers**. This holds although they came from Python 3.10 and 3.13
  respectively.
- **Stage 5** (`run_acceptance.py gate`): `run_evidence_gate` ran on copies of
  `pre_gate_summaries.json`, once per arm.
  - Arm A set `RGPT_FALLTHROUGH_POLICY=legacy` and `RGPT_BORDERLESS_POLICY=off`.
  - Arm B left both unset; they resolved to `table_value_guard` and `off`.

## 2. Per arm and field type

| Field | Arm | Items | RETURNED, verified bind | RETURNED, no bind | ABSTAINED: by reason |
|---|---|---|---|---|---|
| datasets | A | 32 | 0 | 26 | 6: `evidence_span_not_found_in_paper_chunks` 6 |
| datasets | B | 32 | 0 | 26 | 6: same |
| metrics | A | 29 | 0 | 6 | 23: `value_failed_sanity_check` 9, `ownership_unverified` 7, `attributed_to_cited_work` 4, `evidence_span_not_found` 3 |
| metrics | B | 29 | 0 | 6 | 23: `value_failed_sanity_check` 9, `ownership_unverified` 4, `attributed_to_cited_work` 4, `evidence_span_not_found` 3, **`table_value_unbound` 3** |
| results | A | 14 | 0 | 2 | 12: `unverifiable_binding` 6, `ownership_unverified` 3, `evidence_span_not_found` 3 |
| results | B | 14 | 0 | 1 | 13: `unverifiable_binding` 6, `ownership_unverified` 2, `evidence_span_not_found` 3, **`table_value_unbound` 2** |

Binder status of the gated items, the same in both arms:

| Field | No binder run (no numeric anchor) | `pdf_only` | `not_bindable` | `not_a_table_claim` |
|---|---|---|---|---|
| datasets | 32 | — | — | — |
| metrics | 26 | — | 1 | 2 |
| results | 3 | 6 | 4 | 1 |

**No gated item is `bound`** in either arm.

## 3. Every field that changes from A to B (5)

| Paper | Field | Value (start) | A | B | Matched (guard) |
|---|---|---|---|---|---|
| P006 | metrics[2] | "Mean Average Precision (mAP) at IoU threshold of 0.5" | ABSTAINED `ownership_unverified` | ABSTAINED `table_value_unbound` | 0.5 in prose typed as a table ("Table V shows the mean Average Precision …") |
| P006 | metrics[3] | "… at IoU threshold of 0.5-0.95" | ABSTAINED `ownership_unverified` | ABSTAINED `table_value_unbound` | same block |
| P006 | results[1] | "The mAP scores were also higher at both IoU thresholds of 0.5 and 0.5-0.95 …" | ABSTAINED `ownership_unverified` | ABSTAINED `table_value_unbound` | same block |
| P008 | metrics[1] | "95 percent Hausdorff Distance" | ABSTAINED `ownership_unverified` | ABSTAINED `table_value_unbound` | 95 in the TABLE I caption block ("95HD") |
| P008 | results[1] | "… MAS, which took about 20 minutes …" | **RETURNED** (no bind) | **ABSTAINED** `table_value_unbound` | 20 in prose typed as a table ("Table IV shows …") |

Only the P008 results item changes its outcome. Its match is the same coincidental class the 09B guard
recall check found (prose typed as a table; 09B report §14, item 16).

## 4. Gold coverage (the guard's token rule: `gate.numeric_tokens`, PREREG_09B D3)
**3 of 18** gold claims have a gold value token in the pre-gate extraction:

| Claim | Paper | Gold value tokens | Pre-gate field with it | A | B |
|---|---|---|---|---|---|
| C005 | P001 | 0.926, 0.920 | results (0.926) | ABSTAINED `unverifiable_binding` (`pdf_only`) | same |
| C013 | P004 | 4.04, 90.22 | results (4.04, 90.22) | ABSTAINED `unverifiable_binding` (`pdf_only`) | same |
| C057 | P017 | 0.559, 0.512 | results (0.559) | ABSTAINED `evidence_span_not_found_in_paper_chunks` (`not_bindable`) | same |

**Not covered (15):** C010, C012, C021, C025, C026, C027, C034, C035, C041, C042, C045, C048, C052, C058, C085.
For these, the claim's value never reaches the gate. The product's first failure stage for them is the
extraction itself.

## 5. Findings
- **No verified product returns.** In the product run, the binder binds no extracted value on these 12
  papers. Every RETURNED item is ungrounded by any table cell: 34 in A and 33 in B.
- **Product coverage is the first bottleneck.** 15 of 18 gold claims are absent from the Qwen extraction. Of
  the 3 that are present, 2 are blocked by representation: `pdf_only`, because their tables have no cells
  with borderless off.
- **The guard's effect on the product unit** is 1 unverified return removed. That removal is a coincidental
  match (prose typed as a table).
- **Config finding.** The fall-through and borderless flags resolve only from `configs/staging_config.yaml`
  (`gate.py:515`, `represent.py:419`). So their lines in `acceptance_config.yaml` record intent only. Also,
  YAML 1.1 reads the unquoted `borderless_policy: off` as the boolean `False`. This is harmless here, because
  the resolvers parse the raw line.

## 6. Disclosures
- **The priming call stalled.** With a configured seed, Stage 4 makes one priming call before extraction
  (`prime_ollama_cache`, `summarize.py:944-949`). It hit the read-gap timeout on its single attempt and was
  skipped; the log line reads "Still stalled after 1 attempts — skipping this paper". All 12 papers then
  extracted normally.
- **Run once.** The extraction ran once; the extraction cache now holds 12 entries. Stage 5 can be re-run from
  `pre_gate_summaries.json` without re-extraction.
- **UNMEASURED: none.**

## 7. Files
- `src/evaluation/acceptance_pre10/`:
  - `run_acceptance.py`;
  - `pre_gate_summaries.json`;
  - `results.json`, with sections seed, stages, gate and gold_coverage;
  - this report.
- `configs/acceptance_config.yaml`.
- Data in `data_acceptance/` (gitignored): PDFs, metadata, chunks, Chroma, both gate arms.
