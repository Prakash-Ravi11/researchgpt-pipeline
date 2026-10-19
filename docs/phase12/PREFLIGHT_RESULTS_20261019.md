# Phase 12 continuation: preflight containment, 19 October 2026

The continuation removes model work that the current host rules cannot accept.
It preserves all checked facts and candidate denominators. It adds no scientific
extraction capability and remains experimental and disabled by default.

## Demonstrated cause and change

The original frozen run contains 139 prepared prose packets, of which 123 had
actual request artifacts. Only one of those 123 requests had any non-excluded
numeric occurrence with a supported host ownership witness. The 12 executed table
requests had zero measurement relationships admissible under the current host rules.
The completed prose results contain 39 unpublished proposals and zero accepted claims.
These findings come from actual saved sources, requests and decisions, not reconstructed
missing execution. The deterministic preflight diagnostic constructs in-memory inputs
from authoritative saved source packets solely to check current policy compatibility.

`src/evidence/v2/preflight.py` tests these necessary acceptance conditions before
calling the model. A blocked packet is recorded as deferred with its policy limitation;
its candidates stay in the denominator. A model's IDs or labels cannot establish a
host ownership witness or repair unavailable table structure. This is not evidence
that the source has no outcome. The original validators and acceptance thresholds
remain unchanged. A future scientific relationship validator or structure repair can
make additional packets admissible; this change does not supply either capability.

`semantic.py` loads the tokenizer only when a request is admissible, and forwards the
actual row_span/col_span fields. `runner.py` retains specific preflight reasons in the
candidate ledger. The existing API checkpoint reader and host facts remain unchanged.

Implementation commit: `bcee259fb094be8c8b0c86320fcc45c134120285`.
Prior reference commit: `e6ecdcce3fc5f76131040ab89cf433afa12fddc2`.

## Bounded before/after controls

Before editing code, P002, P003 and P010 were selected respectively for a prior
partial quotation record, a timeout with native numeric facts, and a timeout without
native numeric facts. The prior code was frozen as 528 hash-checked archive members.
One before and one after run per paper used alternating order, the same PDFs, model
digest and settings, fresh application outputs, and unchanged 120-second document,
30-second request and six-request limits. No timing trial was discarded or repeated.
No tests or bulk preservation audit ran concurrently with these timed controls.

The model was initially not resident for both P002 arms and both P003 arms, and
resident for both P010 arms. These strata are retained separately in the reconciliation.
OS and model prefix caches were not flushed. Cold model loading itself has no usable
token/timing counters in these attempts; these are initial-residency observations.
The same existing local qwen2.5:7b digest and 8192 context / 2048 output settings were
verified. Temperature 0, seed 42, top_k 40, top_p 0.9 and repeat_penalty 1.1 matched every
recorded request. No model call occurred in an after arm.

| Paper | Before seconds / attempts | After seconds / attempts | Numeric records before / after | Quotations before / after |
| --- | ---: | ---: | ---: | ---: |
| P002 | 121.547 / 4 | 14.468 / 0 | 0 / 0 | 32 / 32 |
| P003 | 121.172 / 4 | 7.344 / 0 | 24 / 24 | 0 / 0 |
| P010 | 121.047 / 4 | 4.516 / 0 | 0 / 0 | 14 / 14 |

Control p50/p95/max were 121.172/121.5095/121.547 seconds before and
7.344/13.7556/14.468 seconds after. Document timeouts were 3 to 0. Both arms include the
strict API sidecar reader after worker completion or interruption, so actual saved
host facts are available in the before results as well. Time includes timeout teardown
and API projection. It excludes acquisition, index construction, dense retrieval and UI.
It differs from the original 30-paper direct-worker timing scope and must not replace it.

**No raw response stream was recorded for any of the 12 before attempts.** Nine have
host hard-timeout records; three lack a host result after document interruption.
Prompt and generated token counts are unknown for all 12, not zero. A request artifact
records an attempted call; it does not demonstrate completed inference. The service-side
cause of the absent streams is unresolved. This is measured avoidance of failed calls,
not a benchmark of faster successful model generation. The previous 30-paper run did
contain completed streams and remains separate, unchanged evidence.

All 70 API-visible facts were identical: 24 numeric facts and 46 source quotations.
Both arms retain 3,416 candidates, with 74 processed and 3,342 deferred. All three
outputs remain partial. New numeric fact recovery is **0**. Complete exact tuples
remain **0 to 0** because measurement origin is unresolved. Independently correct tuple
recovery and accuracy remain **NOT MEASURED**. Successful controls establish behavior
on these examples only; they do not establish equal correct coverage across the corpus.

## Checks and gates

The combined regression run passed **233 tests in 193.60 seconds**: the existing
184-check scope plus all 49 current Phase 12 checks. A preceding focused run passed
49 tests in 22.84 seconds. New regressions cover no-call deferral, preservation of a
supported prose owner, admissible table proposals still reaching validation, and
row/column span metadata. All 21 saved accepted October prose records pass preflight
and produce unchanged adapter outputs, using zero inference.

The preservation audit passed all 6,606 input/code hash checks; it also rechecked
all 2,617 original controlled-run files with zero changes. Dependencies had no drift,
the original checkout's tracked files and index stayed clean, and production remains
disabled. The 528 reference-code members and 232 new control artifacts are hash checked.
Raw requests, private sources, detailed records, caches and local settings stay ignored.

| Gate | Verdict |
| --- | --- |
| Control fact and candidate-denominator preservation | PASS for the three controls |
| Control return deadlines | PASS for the three controls |
| Existing and current regression checks | PASS |
| Production/input/dependency preservation | PASS |
| Processing and semantic completeness | FAIL; all controls partial |
| Independent precision / exact-tuple recall | NOT MEASURED |
| Full-stack p50/p95 at equal independently correct coverage | NOT MEASURED |
| Revised performance across all 30 papers | NOT MEASURED |
| Complete-tuple correctness/recovery | NOT MEASURED independently; structural count unchanged at zero |
| Production promotion | NOT ELIGIBLE |

The original promotion gates were not changed. Typed scientific context, measurement
origin, broader scientific prose validation, visual/structured-source repair and
independent labels remain gaps. Requests that would require those missing capabilities
are now explicitly deferred earlier, rather than sent to an unusable proposal path.
The separate finalization-deadline risk is also unresolved: an admissible model call
can still consume the document deadline, with the strict checkpoint reader preserving
host facts. The control does not validate that boundary for future admissible workloads.

## Local evidence and reproduction

Run in `C:\Users\Praka\Downloads\researchgpt-evidence-v2` on `phase-12-new-implementation`.
The continuation artifacts are under `.run/evidence_v2/phase12/resume-20261019/`:
selection.json, before-code-hashes.json, request-diagnosis.json, paired-controls/
(launches, attempts, decisions, before/after API records and comparison.json),
reconciled-controls.json, preflight-tests.xml, regression.xml, regression-command.json,
accepted-record-compatibility.json and preservation.json.

The following inspect existing evidence without inference. Choose a fresh output name:

```powershell
. 'C:\Users\Praka\Downloads\researchgpt-evidence-v2-handoff-20261016\enter-evidence-v2.ps1'
& $EvidenceV2Python -B scripts/diagnose_scientific_requests_v2.py --run .run/evidence_v2/phase12/paired-controlled-model --output .run/evidence_v2/phase12/resume-20261019/diagnosis-review.json
& $EvidenceV2Python -B scripts/report_scientific_preflight_v2.py --run .run/evidence_v2/phase12/resume-20261019/paired-controls --output .run/evidence_v2/phase12/resume-20261019/controls-review.json
```

The exact executed model-control command and selected inputs are in selection.json,
paired-controls/manifest.json and each arm's launch.json. No repeat is needed to read
or verify these results.
