# Opt-in source-referenced Prototype A

The implementation is in `src/evidence/prose_attribution/`. Importing it does not activate extraction. `RepairConfig.enabled` defaults to false; disabled calls make no request and write no artifacts. This experiment's separate YAML opts in. The production configuration, parser, catalog and existing table invocation are unchanged.

`SourceDocument` retains original input text and a normalized Unicode/whitespace view, character-to-original-word maps, source hash, available parser/layout metadata and explicit missing/inferred statuses. Parser blocks do not become semantic paragraphs. Whole-sentence selections are bounded references; the source API also validates narrower start/end spans. Word geometry requires matching original character offsets. Regions stay separate by block/page/line, and geometry never enters `model_units()`.

The numeric inventory identifies each occurrence independently, including contextual years, citations, area/volume statistics, scalar amounts and range components. IDs are stable within the content-hashed document/version. All candidates receive a ledger state; unaccounted model entries remain unresolved rather than disappearing. Ledger completeness, explicit model-accounting completeness and unresolved counts are distinct measures.

Core publication requires all of: valid source/document references, exact value/unit/range occurrence checks, a coupled outcome predicate, source-scoped qualifier/direction/negation, required conditions, and an explicit named/unique anaphoric/ordered-pair relationship. Literal text presence alone does not establish ownership. The semantic rules are automated and conservative, not a guarantee of human correctness. A larger reconstructed quote never changes the relationship verdict. Selected ownership bridge IDs must include the supporting source path. Deployment context and general-platform scope are assessed separately; unsupported optional location/year/population/role stays null. Entire core-unresolved/rejected claims stay unpublished.

The source rule set supports explicit platform-use/outcome predicates, compatible unique anaphora, explicit same-trial continuation, original-author trial reporting scopes, and equal-length respectively lists. Missing reading order blocks unlicensed cross-block links. Explicitly unspecified ownership stays unresolved. Predicate/qualifier checks are tied to the chosen numeric occurrence, not arbitrary keywords in a paragraph. Units and verified named-entity labels use value-independent aliases, recorded per claim. Neither source rules nor prompts read reference answers or case-specific expected quantities.

One document pass is followed by at most one context request for each unresolved evidence unit, batching its fields. The document cap is three model requests and 240 seconds; each request is at most 180 seconds. The smallest known ownership/context path is retrieved. Explicit absence of identifying evidence is not retried blindly. Every attempt, actual request, streamed response, semantic verdict and ledger state is retained. A single transport worker uses the existing ResearchIQ invocation/parser/trace; a host deadline kills its process/socket before any next request. Workers are timeout boundaries, not agents or parallel inference.

Prompts, schemas, source representations, quotation rules and cache fingerprints are versioned. The experiment bypasses caches; server prompt/KV reuse is recorded. Comparisons use the same local model, temperature/seed/context/output budget, while source-ID wrappers, schema constraints and bounded context requests differ and are measured.

Summaries are generated in code exclusively from published supported records. They retain scalar/range meaning, qualifier, direction, negation, population, threshold/baseline conditions and reporting role. Compound forecast records share a source group and preserve the threshold dependency. Cited results are reported as the review's reports, not its author's experiments.

`unified_table_views` produces the same claim shape from the existing validated method/configuration/dataset/metric/cell associations. It does not alter payloads, scales, source geometry or table extraction. Unsupported table context/role stays null; existing automated assessment limitations remain explicit. It runs only when explicitly enabled. There is no table recovery/fallback path in prose extraction.

The frozen synthetic set was requested by the user. It is unseen to the original A/B/model runs but authored by this assistant before repair evaluation, with no independent human review. It is not a blind corpus-accuracy estimate.

## Explicit invocation

The reusable entry point is `scripts/extract_prose_claims.py`. A source JSON contains `document_id`, authoritative `text`, optional `blocks` (whose texts join with two newlines to the authoritative text), and optional `metadata`. Existing parser chunks can instead use `SourceDocument.from_chunks()` through the Python API. Metadata should include `source_kind` when known; the CLI does not infer document genre.

Provide the existing model YAML and a separate repair YAML. Omitting the repair YAML leaves the CLI disabled and performs no source read, request, or output write. To enable, the separate YAML must contain `prose_attribution_repair: {enabled: true}`; the dataclass supplies bounded defaults. The output must be a new directory. For example, after preparing a source JSON:

```powershell
.\experiments\prose_attribution_ab_20261013\.venv\Scripts\python.exe -B .\scripts\extract_prose_claims.py --source-json .\source.json --repair-config .\experiments\prose_attribution_repair_20261014\experiment_config.yaml --output .\out\prose_trial_1
```

This command is a usage example, not an additional measured inference run. The source-ID extractor remains an opt-in experimental path; final measured quality is reported separately. The CLI uses the same frozen core as the comparison and does not write production paper summaries, evidence or caches.

The CLI additionally uses `deadline_guard.extract_bounded_document`, added after an execution interruption exposed a late worker-return race. It preserves the pre-guard result, rejects a completion whose recorded host elapsed time exceeds its allowed request time, and versions the transport in the cache fingerprint. This guard was not imported by the frozen v2 comparison, and its synthetic transport tests are not model-performance evidence. It cannot enforce elapsed time while the host itself is suspended; on resumption it fails closed and records the overrun. The primary measured run retains the incomplete interrupted case and its actual elapsed time.
