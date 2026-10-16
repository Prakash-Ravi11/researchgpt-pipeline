# Frozen normalization policy

`normalize.py` is shared by both candidates. Its SHA-256 will be stored before inference and checked before scoring. The benchmark gold and evaluator have not been loaded when this policy is written.

The adapter trims label whitespace, converts numeric strings/years, standardizes snake_case, maps ordinary synonyms for outcome labels, standardizes common units and qualifiers, and expands thousand/million/billion unit prefixes arithmetically. Named subject aliases derive only from names visible in source prose. No rule looks at a numeric expected answer, evidence text, case ID, location/year association or evaluator result. Location labels receive whitespace normalization only. Evidence text is never rewritten. Null/missing fields stay null; no default qualifier, deduplication, relationship correction or inferred location/year is added.

Canonical labels are design choices made from the task/source vocabulary. The strict fixture may use different labels; semantic review will document equivalence separately without editing this policy or the finalized outputs. All applied changes are saved per claim. Unsupported or malformed fields are preserved and flagged during conversion.

A uses the ResearchIQ `call_ollama_json` and `ExtractionTrace` directly, one call per case, with caching bypassed by calling the invocation layer rather than the paper extraction/cache layer. It retains each deployment paragraph as one context boundary, without splitting sentences or flattening across blank lines. Separate study-level records are prompted; no table recovery or fallback path is invoked.

B uses the installed LangExtract Ollama provider and extractor. Each quantitative claim is a `claim` extraction whose verbatim `extraction_text` becomes `evidence_text`; the seven other contract fields come directly from attributes. SDK source intervals/alignment statuses are preserved separately, shifted only by the common input-ID prefix to refer to the original passage. Repeated evidence spans and unresolved SDK matches remain visible. Conversion never repairs the claim's ownership.

Both candidates receive the same instruction text, input-ID prefix, unchanged source text, and one unrelated fictional example. Formatting wrappers differ to meet each API's contract. All rendered requests are retained for comparison.
