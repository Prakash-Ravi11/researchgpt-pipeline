# Phase 12 implementation and measured limits

Phase 12 remains experimental and disabled by default. Implementation and the
controlled evaluation are recorded; reliable scientific extraction is not established.
No promotion, merge, deployment, global package upgrade, model replacement or paid API was used.
Independent accuracy gates remain **NOT MEASURED**, as authorized after the recovered
30-paper labels were confirmed machine-assisted and unvalidated.

## Code and baseline

- October baseline: `18af9febca88e122b05f6baef7ecbca0068eca4d`.
- Documentation-only implementation start: `ac1202d52fa9db53f1b7abfa621a70d32d808514`.
- Controlled model run: `97da982afc3ba9c44398ea4e83d3f082739c239e`.
- Subsequent checkpoint-reader correction: `1aa3e80524cdcc0d154a06384d25dd108ecd0f61`.
- Branch/upstream: `phase-12-new-implementation` / `origin/phase-12-new-implementation`.

`src/evidence/v2/` adds all-page native inventories, table/header relationships,
measurements, per-field support, candidate accounting, bounded local proposals,
raw execution records, versioned caches, deterministic output and opt-in sidecars.
The existing October prose-attribution validator is reused. Missing optional
location/year already preserves supported core results; no redundant change was made there.
`src/api/data.py` selects the new output only with `paths.scientific_results_dir`.
`Config.enabled` and local model use are false by default. Existing acquisition,
search, UI and default API behavior remain in place.

Host code copies measurements from source evidence and checks subject/metric/header
relationships. Valid evidence IDs alone do not confer support. Unknown origin,
location, year and uncertainty type stay null. Raw experimental scope is preserved;
its complete conversion into typed dataset/split/comparator fields remains unfinished.

## Frozen controlled comparison

All 30 hash-verified PDFs were retained in both arms, in alternating order, with fresh
application outputs and no acceptance-cache reuse. Windows, the same RTX 3050 Laptop,
existing Python environment and local `qwen2.5:7b` Q4_K_M were used.
The model digest is `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`.
Every recorded request matched temperature 0, seed 42, context 8192, prediction limit
2048, top_k 40, top_p 0.9 and repeat_penalty 1.1. The baseline benchmark fixes its
context estimator in memory to that same window; frozen baseline files, prompts,
schemas and acceptance code were unchanged.

| PDF to returned record | Baseline | v2 before checkpoint-reader correction |
| --- | ---: | ---: |
| Papers | 30 | 30 |
| p50 seconds | 33.4455 | 120.6570 |
| p95 seconds | 34.61735 | 120.75985 |
| Maximum seconds | 36.5160 | 120.8430 |
| Document timeouts | 0 | 29 |
| Partial papers | 26 | 30 |
| Actual request artifacts | 30 | 135 |
| Raw successful stop events | 4 | 48 |
| Requests without final done event | 26 | 87 |
| Known prompt / generated tokens | 8,047 / 1,497 | 95,594 / 14,113 |
| Requests with unknown token counters | 26 | 87 |

Known token counters are partial totals, not estimates of total consumption.
The v2 host records show 59 request hard timeouts, 48 responses and 28 requests
without a host-result artifact. A raw stop event is not host acceptance. Baseline's
four completed extractions indicate schema/execution completion, not scientific correctness.
All 30 baseline returned records contained zero gated result text and zero structured
numeric rows; v2 returned only P002 (32 qualitative source quotations, zero numeric rows).

All 60 arms began with the model resident. Cold model loading and cache-hit speed
were not measured. OS/model prefix caches were not flushed. Timing includes parser,
selection, local inference, host validation and record serialization, but excludes
acquisition, embedding/index creation, dense retrieval and browser work. Therefore
full-stack promotion p50/p95 at equal independently correct coverage are NOT MEASURED.
The measured scope is substantially slower and cap-limited; it is a failure, not a speed gain.
Teardown overhead beyond the 120-second document cap is retained in the numbers.
The small variation around that cap does not justify selective timing repeats.

Worker peak working set was recorded for 30 baseline workers (maximum 206,585,856 bytes)
and one v2 worker (182,468,608 bytes). Killed-worker, model-service and GPU peaks are
unknown, so these are not comparable full-resource maxima. No OOM is demonstrated in
these artifacts; this does not establish a complete no-OOM resource gate.

Preparatory runs are preserved separately. Their actual_request.json counts are
2 calibration-model, 1 paired-model-final, 1 failed-relative-output-artifacts,
5 paired-model-verified and 12 paired-corpus-model. These 21 artifacts are excluded
from the final 165-request comparison. Path failures, old tokenizer startup and
unequal context settings are documented in local evaluation-selection.json.
No missing execution is reconstructed or counted as a successful run.

## Stage losses and the demonstrated publication correction

The actual source-v2 inventories cover 570 pages, 133 table structures (122 inventoried,
11 unresolved), and 41,380 candidates: 26,436 non-table numeric, 2,463 table numeric,
11,233 qualitative and 1,248 visual. All enumerated candidates have exactly one
recorded decision. This is accounting coverage, not exhaustive semantic interpretation.
Graphical outcomes and unresolved table structures remain incomplete.

Before model work, host checkpoints contain 56 numeric facts plus 236 verbatim
qualitative quotations. Model requests comprise 12 table and 123 prose requests.
The interrupted evaluation retained checkpoint facts but did not publish final
returned records for 29 papers. This was an actual serialization/publication loss.

The subsequent opt-in sidecar reader recovers a missing final result only after
checking the run, paper, source hash, policy, candidate/fact counts, and exact
reproduction of saved host facts and decisions from the saved source inventory.
A present but invalid final result still fails closed. Partial model responses are
never interpreted by recovery. The reader writes nothing to the old run and always
marks recovered results partial with incomplete model work.

A separate zero-inference replay used those actual checkpoints, rather than
reconstructing missing model execution:

| Paper | Originally returned numeric records | Replayed host-supported numeric records | Complete exact tuples after replay |
| --- | ---: | ---: | ---: |
| P003 | 0 (no returned record) | 24 | 0 |
| P005 | 0 (no returned record) | 13 | 0 |
| P006 | 0 (no returned record) | 7 | 0 |
| P008 | 0 (no returned record) | 12 | 0 |
| Other 26 papers | 0 | 0 | 0 |
| Total | 0 | 56 | 0 |

All 56 recovered numeric facts have unresolved measurement origin. The pre-existing
exact-tuple fields are source_sha256, subject, metric, measurement, experimental_scope,
measurement_origin and modality. Structurally complete records remain **0 to 0**;
independently correct complete-tuple recovery remains **NOT MEASURED**. Core-record
recovery is **0 to 56**, not 56 proven correct scientific tuples. Qualitative source
quotations are **32 to 236**; they retain unresolved ownership and are not counted as
numeric outcomes. The existing P002 final facts were preserved exactly.

After replay, all 41,380 enumerated candidates remain accounted for: 308 processed,
41,072 deferred, zero rejected and zero unresolved. Processed context settings explain
why 308 processed candidates do not equal the 292 facts. No paper is semantically complete.
Reader-only replay p50/p95/max were 0.188/0.4489/0.500 seconds. These exclude all model
work and cannot replace the frozen end-to-end timings above. All 2,617 controlled-run
files were hash-identical before/after replay. Per-paper before.json (null for a missing
original returned record), after.json, fact IDs and source paths remain local.

A preselected implementing-assistant visual check of four native numeric cell/subject/
metric relationships agreed in 4/4 examples. It is a small non-independent sample,
not a corpus precision estimate. It exposed missing Roman numeral captions, repaired
and tested before the frozen controlled run. It does not validate study ownership.

## Preservation and regression evidence

The recorded combined regression run passed 220 tests, comprising 184 existing and
36 interim new checks. The latest focused run passed all 45 tests in 21.01 seconds,
including wrong cell/metric/study safeguards, optional null context, repeated scores,
merged/transposed/continued tables, negative R-squared, uncertainty, malformed output,
real process cancellation, cache integrity, API serialization, interrupted checkpoint
recovery and tampered checkpoint rejection. These counts describe different recorded
runs and must not be added as unique tests. No failures occurred in the recorded baseline test scope.

An adapter/serialization replay preserved all 21 accepted October prose records,
including core values, qualifiers, conditions, direction, negation, context and original
evidence. It made zero inference calls and did not establish new extraction gains.
The historical 18-target diagnostic retains 55 reference cells; its provisional 3/18
native-cell matches are not interpreted recall or independent correctness. The 17/18
and 15/18 promotion gates remain NOT MEASURED. The earlier three-request enrichment
pilot remains unverified and contributes no gains. Corrected replay case 06 still
has zero accepted claims; Corteva and FieldView are not silently promoted or conflated.

Final preservation passed 6,606 hash checks over 3,023 source/copy records, 30 source/copy PDFs
and 500 frozen code files, plus rechecks of 2,617 controlled-run files. Dependencies had no drift;
the original checkout stayed clean in its tracked worktree and index. Results are recorded
in VALIDATION.json and the local verified-final-preservation.json.
The initial final-preservation.json audit compared CRLF archive files with LF Git blob hashes
and falsely flagged 439 code files. Exact comparison against canonical Git archive member
bytes found no change. The failed comparator report is retained alongside the corrected audit.
PDFs, labels, raw outputs, model files, caches and the historical handoff stay local.
They are excluded from Git and must not be described as Git-backed backups.

## Promotion verdicts

| Gate | Verdict | Scope or remaining gap |
| --- | --- | --- |
| Precision >= max(95%, baseline) | NOT MEASURED | No independently reviewed labels |
| Exact recall >= max(80%, baseline) | NOT MEASURED | Difficult/deferred targets retained |
| Preserve all independently correct baseline facts | NOT MEASURED | Saved-record preservation alone is insufficient |
| Zero accepted wrong cell/metric/study in executed regression fixtures | PASS | Fixture behavior only |
| Enumerated candidate accounting | PASS | 41,380 unique terminal decisions |
| Processing and semantic completeness | FAIL | All 30 partial; 41,072 deferred after replay |
| Full-stack uncached p50 and p95 at equal correct coverage | NOT MEASURED | Scope and correctness evidence unavailable |
| No slowdown in measured PDF-to-output scope | FAIL | Cap-dominated v2 latency is worse |
| Independently validated 18-target 17/18 and 15/18 | NOT MEASURED | Recovered labels unvalidated |
| Default disabled, local processing, bounded cancellation | PASS | Explicit opt-in; local service and regression checks |
| Visual repair correctness gain | NOT MEASURED | No compatible vision service or active repair backend |
| Cold-load/cache-hit benchmark and full-resource/no-OOM gate | NOT MEASURED | No cold/cache-hit trials; resource counters incomplete |
| Production records, dependencies and frozen input preservation | PASS | 6,606 input/code hash checks, 2,617 controlled files unchanged; no dependency drift |

The raw reconciliation report leaves fixture accuracy unmeasured because it reads only the
controlled run. The scoped fixture PASS above comes from the separately executed JUnit checks.
No gate was lowered or given a 20% latency allowance. Remaining implementation gaps
include typed scientific dataset/split/comparator/origin relationships, broader scientific
prose measurement schemas, ambiguous and graphical evidence, and measured OCR/visual or
structured-source integration. Existing adapters remain available; no new repair backend
or vision capability is claimed. V2 is not eligible for production promotion.

## Reproduce and inspect locally

Open `C:\Users\Praka\Downloads\researchgpt-evidence-v2` on `phase-12-new-implementation`.
Use the existing interpreter through the preserved launcher; do not install or upgrade packages.
Choose fresh output paths for every replay/report. The following commands make no model requests:

```powershell
. 'C:\Users\Praka\Downloads\researchgpt-evidence-v2-handoff-20261016\enter-evidence-v2.ps1'
& $EvidenceV2Python -B -m pytest tests/test_evidence_v2.py -q -p no:cacheprovider
& $EvidenceV2Python -B scripts/report_scientific_v2.py --run .run/evidence_v2/phase12/paired-controlled-model --output .run/evidence_v2/phase12/reconciled-review.json
& $EvidenceV2Python -B scripts/replay_scientific_checkpoints_v2.py --run .run/evidence_v2/phase12/paired-controlled-model --corpus .run/evidence_v2/phase12/baseline/corpus.json --output .run/evidence_v2/phase12/api-checkpoint-review
```

Local artifact root: `.run/evidence_v2/phase12/`.
Key evidence: baseline/{manifest,corpus,gates}.json, paired-controlled-model/{manifest,comparison}.json and timing.jsonl, reconciled-delivery.json, source-breakdown.json,
api-checkpoint-replay/{summary,frozen_run_hashes}.json and Pxxx/{before,after}.json,
tests/{final-regression,source-caption,checkpoint-reader}.xml,
preservation/{prose-adapter,legacy-18-diagnostic,final-preservation}.json,
source-audit/{selection,review}.json, evaluation-selection.json and PHASE12_HANDOFF.json.
Requests/raw responses/host decisions remain under each controlled run's per-paper arm.
