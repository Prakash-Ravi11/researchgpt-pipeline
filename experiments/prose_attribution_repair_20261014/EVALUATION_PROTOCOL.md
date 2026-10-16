# Frozen comparison protocol

The unchanged baseline and its normalizer, seven regression inputs/reference answers, and eight synthetic inputs/reference answers were frozen before repair evaluation. The model sees only inputs, occurrence IDs and source units. It does not read `evaluation_only/`.

The v1 protocol pilot was stopped after three documents and one in-flight request because the model misused the JSON field contract. Its raw attempts remain separate. The v2 prompt adds a complete, unrelated fictional JSON example. The v2 extraction code is frozen before its run. No post-processing will change its accepted/rejected verdicts or fill missing fields for this comparison.

`evaluation_only/compare_final.py` is written while v2 inference is running, before its outputs are finalized or comparative scores are computed. It refuses to run without the finalized-output hash manifest and a separate per-record source review. It does not import the attribution rules or invoke inference. It uses the unchanged fixture evaluator for an additional strict regression score.

The primary common tuple comprises subject, location, year, outcome, value (both bounds for ranges), unit and qualifier. Measurement direction, negation and explicit conditions must also preserve source meaning. A quotation is checked separately: tuple agreement alone is not grounded correctness. The extended implementation also records population, role, conditions and evidence for each field; missing structured legacy fields are disclosed rather than retroactively added to the old output.

Supported-outcome recall requires a correct owner/outcome/amount or range/unit/qualifier, preserved direction/negation/conditions, an exact quotation, and an ownership relationship supported by that quotation. Missing optional location/year is not a missing outcome. Incorrect asserted context is counted independently. Fully grounded tuples additionally require the complete tuple and support for every asserted optional field.

The source review is by the implementing assistant, not an independent assessor. For regression baseline and quotation-only results, it reuses the original saved relationship review; quotation-only cannot improve the ownership verdict. New records receive explicit review notes. Semantic label equivalences are evaluation-only decisions, saved with their reasons; outputs and references remain unchanged. The prior benchmark's existing label equivalences are carried forward. No numeric value is repaired by the evaluator.

Report precision and recall together, missing quantities, invalid quotations, unsupported context, unresolved/ambiguous occurrence states, native ledger completeness and explicit model-accounting completeness separately. A ledger full of unresolved entries is complete accounting, not complete extraction. Baseline has no native ledger; its omissions are a post-hoc reference audit.

For the adjacent/reversed regression pair, compare complete tuple and core-quantity multisets. These passages reuse source facts and do not constitute independent accuracy samples. The unseen set is synthetic and assistant-authored, unseen to the original experiment/model runs, and not a blind generalization estimate.

Record actual per-document requests, retries, elapsed time and model token counters. The regression baseline uses the saved previous-day run; its latency is historical. Unseen baseline and complete-repair inference alternate order locally. Quotation-only inherits baseline inference plus host conversion time and makes zero additional model requests. Pilot and warmup costs are disclosed outside final-candidate totals. Missing completion counters on aborted requests stay unknown.

Compatibility checks run after timed inference, including existing table association regressions. Frozen repository/production hashes and the model digest are checked again at completion. No production corpus extraction, production configuration edit, model replacement, or reference correction is part of this experiment.
