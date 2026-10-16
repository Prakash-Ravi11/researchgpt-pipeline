# Review rubric fixed before gold/scoring

Review each finalized claim against its unchanged full source passage and its own evidence span. Review is an assistant assessment, not an independent human correctness label. Compare strict fixture results separately.

- Ownership/deployment: the named technology must own the outcome; no merged or joint deployment may be inferred from adjacency.
- Context: location/year must be explicitly supported for this claim. A prior local deployment does not establish context for a later general statement about an app's users.
- Numeric meaning: preserve the numerical amount, unit/scale, direction and quantity type. Area/download/volume statistics excluded by instructions do not count as target outcomes.
- Qualification: preserve approximation/estimate, bounds, forecasting lead-time wording, and conditional proportions. A forecast success proportion's evidence must retain its error criterion.
- Evidence completeness: an exact substring can still omit the owner, local context or comparison condition. Record lexical alignment and relationship support separately; do not treat lexical match as semantic proof.
- Missing facts: an expected occurrence without a source-supported semantic counterpart is missing. Equivalent labels are assessed from source meaning without changing outputs, normalization or gold.
- Extra records: review source support and scope; strict unmatched output is not automatically hallucination. Report duplicate/conflicting tuples separately.
- Order: compare normalized and source-reviewed claim multisets in adjacent versus reversed cases, including qualifiers/context. Do not count changed claim ordering alone as sensitivity.
- Control: any quantitative output in the non-quantitative control is unsupported.

The headline reviewed attribution-error count covers wrong owner/deployment and unsupported propagated context, counting affected output records. Missing/altered qualifiers, incomplete evidence, duplicated records and numeric mistakes are separate counters. A claim can have several defect categories; aggregate error-record counts must not double-count it.

Reference changes require a documented source-supported error and the same corrected evaluation for A and B. Label preferences alone do not justify a fixture edit. The 30 expected occurrences repeat 15 source facts and are not independent studies.
