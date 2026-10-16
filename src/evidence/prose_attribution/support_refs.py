"""Exact field witnesses from source spans already selected by the model.

This module adds no source units, guesses no omitted value and reads no fixture.
Context rebinding additionally requires the existing explicit deployment path.
"""
import re

from .inventory import NUMBER, UNIT_ALIASES, numeric_value


def literal(value, text):
    return isinstance(value, (str, int)) and not isinstance(value, bool) and bool(
        re.search(r"(?<!\w)" + re.escape(str(value)) + r"(?!\w)", text, re.I))


def unique_refs(pairs):
    refs = []
    for reference, _ in pairs:
        if reference not in refs:
            refs.append(reference)
    return refs


def context_witnesses(source, frame, pairs, anchor_function):
    selected = {span["sentence_id"] for _, span in pairs}
    context = set(frame["context_ids"])
    if (frame["status"] != "supported" or frame["global_scope"] or not context
            or not context <= selected or not frame["required_refs"] <= selected):
        return []
    units = [source.sentence(identifier) for identifier in context]
    # Reclassification is conservative when a selected context unit contains
    # another owner or repeated occurrences of this platform. A shared name
    # does not identify which deployment supplies its location/date.
    if any(item["subject"] != frame["subject"] for unit in units for item in anchor_function(unit["text"])):
        return []
    mentions = sum(len(re.findall(r"(?<!\w)" + re.escape(frame["subject"]) + r"(?!\w)", unit["text"])) for unit in units)
    if mentions != 1:
        return []
    return [(reference, span) for reference, span in pairs if span["sentence_id"] in context]


def field_witnesses(field, value, pairs, candidates):
    if field == "year":
        if type(value) is not int:
            return []
        ids = {span["sentence_id"] for _, span in pairs}
        years = {candidate["value"] for candidate in candidates
                 if candidate["sentence_id"] in ids and candidate["kind"] == "context_year"}
        if years != {value}:
            return []
        return [(reference, span) for reference, span in pairs if literal(value, span["normalized_text"])]
    if not isinstance(value, str):
        return []
    # A location witness includes the preposition, not merely the same words.
    pattern = r"\b(?:in|at|near)\s+(?:the\s+)?" + re.escape(value) + r"(?!\w)"
    return [(reference, span) for reference, span in pairs if re.search(pattern, span["normalized_text"], re.I)]


def normalize_area_location(value, pairs, candidates):
    if not isinstance(value, str):
        return value, None
    match = re.fullmatch(r"(?P<number>" + NUMBER + r")\s+(?P<unit>acres?|hectares?)\s+"
                         r"(?:in|at|near)\s+(?P<place>[A-Z][A-Za-z .,'’\-]+)", value)
    if not match:
        return value, None
    amount, unit, place = numeric_value(match["number"]), UNIT_ALIASES[match["unit"]], match["place"]
    area = [candidate for candidate in candidates if candidate["kind"] == "deployment_scale"
            and candidate["value"] == amount and candidate["unit"] == unit
            and any(span["sentence_id"] == candidate["sentence_id"]
                    and span["normalized_start"] <= candidate["reference"]["start"]
                    and candidate["reference"]["end"] <= span["normalized_end"] for _, span in pairs)]
    geographic = field_witnesses("location", place, pairs, candidates)
    if not area or not geographic:
        return value, None
    return place, {"field": "location", "operation": "normalization", "before": value, "after": place,
                   "assessment_rule": "verified_area_modifier_removed_from_location",
                   "area_candidate_ids": [candidate["id"] for candidate in area],
                   "source_references": unique_refs(geographic)}
