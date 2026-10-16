"""Conservative saved-quotation mapping; no ownership/context repairs."""
from copy import deepcopy
import re

from .source import SourceDocument, normalize_with_map

QUOTE_VERSION = "quote-reconstruction-v1"


def map_saved_quotation(source: SourceDocument, quotation):
    if not isinstance(quotation, str) or not quotation:
        return {"status": "alignment_failure", "reason": "missing_quotation"}
    exact = [match.start() for match in re.finditer(re.escape(quotation), source.raw_text)]
    if len(exact) == 1:
        start, end = exact[0], exact[0] + len(quotation)
        return {"status": "supported", "rule": "exact_original", "raw_start": start, "raw_end": end,
                "evidence_text": source.raw_text[start:end], "regions": source.regions(start, end),
                "ownership_established": False}
    if len(exact) > 1:
        return {"status": "alignment_failure", "reason": "repeated_original_text_ambiguous"}
    normalized, _ = normalize_with_map(quotation)
    alternatives = [(normalized, "normalized_whitespace_or_unicode")]
    if normalized.endswith((".", "!", "?")):
        alternatives.append((normalized[:-1], "terminal_punctuation_prefix"))
    possibilities = []
    for needle, rule in alternatives:
        if len(needle.split()) < 8:
            continue
        for match in re.finditer(re.escape(needle), source.normalized_text):
            begin, end = match.start(), match.end()
            # Require word boundaries; no matching a convenient suffix/prefix
            # inside a different word or accepting broad fuzzy paragraph matches.
            if begin and source.normalized_text[begin - 1].isalnum() and needle[0].isalnum():
                continue
            raw_begin = source.character_map[begin]["raw_start"]
            raw_end = source.character_map[end - 1]["raw_end"]
            possibilities.append((raw_begin, raw_end, rule))
    unique = {(start, end): rule for start, end, rule in possibilities}
    if len(unique) != 1:
        return {"status": "alignment_failure", "reason": "unmapped_or_ambiguous_under_frozen_rules",
                "candidate_interval_count": len(unique)}
    (start, end), rule = next(iter(unique.items()))
    return {"status": "supported", "rule": rule, "raw_start": start, "raw_end": end,
            "evidence_text": source.raw_text[start:end], "regions": source.regions(start, end),
            "ownership_established": False}


def repair_saved_claim(source, claim):
    result = deepcopy(claim)
    alignment = map_saved_quotation(source, claim.get("evidence_text"))
    if alignment["status"] == "supported":
        result["evidence_text"] = alignment["evidence_text"]
    decision = {"version": QUOTE_VERSION, "original_evidence_text": claim.get("evidence_text"),
                "alignment": alignment, "claim_fields_changed": [],
                "semantic_assessment": "unchanged; quotation mapping cannot establish ownership"}
    return result, decision
