# Phase 10 package, Part 2 — Product acceptance before Phase 10

## Objective
Run the product pipeline offline (Stages 2–5) on the 12 hash-pinned gold PDFs, with the frozen 09B
configuration, and measure what it returns. Two arms:
- A: legacy, borderless off;
- B: the frozen config.

Also measure how many of the 18 gold claims reach the gate.

## Inputs
- `configs/acceptance_config.yaml`: a copy of the staging config with `data_acceptance/` paths, its own
  collection, and the frozen flags.
- The 12 gold PDFs (manifest SHA-256) and their acquisition records, as the 55-pair evaluation used them.
- Ollama `qwen2.5:7b` (digest `845dbda0ea48ed74…`), temperature 0, seed 42. BGE-M3 from the local cache.

## Work Performed
- `run_acceptance.py seed`: 12 PDFs copied, SHA-256 verified 12/12.
- `run_acceptance.py stages`, run once. It called `run_processing`, `run_embedding` and `run_summarization`.
  The Stage 4 dict had `evidence_grounding.enabled = False`, so Stage 4's own gate hook was skipped. The
  output was saved as `pre_gate_summaries.json`.
- `run_acceptance.py gate`: `run_evidence_gate` on copies of the pre-gate summaries, once per arm, then the
  measurements.

## Results
FACT:
- The acceptance chunks equal the 55-pair evaluation's L0 records on 12/12 papers.
- All 12 extractions are conformant; 0 failed.
- RETURNED with a verified bind: **0 in every field, in both arms**.
- RETURNED without a bind:
  - A: datasets 26, metrics 6, results 2;
  - B: datasets 26, metrics 6, results 1.
- 5 fields change from A to B; 1 changes its outcome:
  - P008 results[1] goes from RETURNED to ABSTAINED `table_value_unbound`, a coincidental match on prose
    typed as a table;
  - 4 change only their reason, from `ownership_unverified` to `table_value_unbound`.
- **Gold coverage: 3/18.**
  - C005 and C013: present, ABSTAINED `pdf_only` in both arms.
  - C057: present, ABSTAINED `evidence_span_not_found` in both arms.
  - The other 15 claims never reach the gate.
- Stage 4's priming call stalled once and was skipped (disclosed).

INTERPRETATION: on this product unit, extraction coverage, not binding, is the first bottleneck for 15 of
18 claims. Representation (`pdf_only`) blocks 2 of the 3 that do reach the gate.

## Evidence
`src/evaluation/acceptance_pre10/`:
- `ACCEPTANCE_REPORT.md`;
- `results.json`, with sections seed, stages, gate and gold_coverage;
- `pre_gate_summaries.json`;
- `run_acceptance.py`.

## Decisions
- Stage 5 runs on copies. Stage 4's built-in gate hook is bypassed through the config dict passed to it;
  no pipeline code changed.
- Arm B leaves the flags unset, so they resolve from `staging_config.yaml`, as the product does.

## Changes
Branch `acceptance/pre-phase10`, created from `claude-code-verification` (`2d61f3c`). New files:
- `configs/acceptance_config.yaml`;
- `src/evaluation/acceptance_pre10/*`;
- this checkpoint.

No production code changed.

## Temporary Files
`data_acceptance/` (gitignored) holds the seeded PDFs, the metadata, the processed data, Chroma, the
`gate_A` and `gate_B` copies, and the logs. It is kept: Phase 10 measures the product fields from
`pre_gate_summaries.json`.

## Current State
**Part 2 complete**, committed and pushed.

## Next Step
Part 3: Binder v2 on `exp/phase10-binder` (STEP 0 failure map, STEP 1 pre-registration, …).

## Do Not Redo
The Qwen extraction (run once) and the seed.

## Reproduction
```
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/acceptance_pre10/run_acceptance.py seed
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/acceptance_pre10/run_acceptance.py stages   # Ollama running; runs Qwen
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/acceptance_pre10/run_acceptance.py gate
```
