"""Source-derived numeric occurrence inventory, independent of expected answers."""
from __future__ import annotations

import re

NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
EXPRESSION = re.compile(r"(?<![\w.])(?P<currency>\$)?(?P<sign>[+-])?(?P<number>" + NUMBER + r")"
                        r"(?P<scale>\s*(?:thousand|million|billion))?"
                        r"(?P<unit>\s*(?:%|percentage points?|percent(?:age)?|gallons?|days?|acres?|hectares?|liters?|litres?))?", re.I)
UNIT_ALIASES = {"%": "percent", "percentage": "percent", "percent": "percent",
                "percentage point": "percentage_points", "percentage points": "percentage_points",
                "gallon": "gallons", "gallons": "gallons", "day": "days", "days": "days",
                "acre": "acres", "acres": "acres", "hectare": "hectares", "hectares": "hectares",
                "liter": "liters", "liters": "liters", "litre": "liters", "litres": "liters"}


def numeric_value(text):
    value = float(text.replace(",", ""))
    return int(value) if value.is_integer() else value


def inventory(source):
    candidates = []
    for sentence in source.sentences:
        matches = list(EXPRESSION.finditer(sentence["text"]))
        for occurrence, match in enumerate(matches):
            amount = numeric_value(match.group("number"))
            if match.group("sign") == "-":
                amount = -amount
            scale = (match.group("scale") or "").strip().lower()
            if scale:
                amount *= {"thousand": 1000, "million": 1000000, "billion": 1000000000}[scale]
            unit = UNIT_ALIASES.get((match.group("unit") or "").strip().lower())
            if unit == "percent" and re.match(r"\s*points?\b", sentence["text"][match.end():], re.I):
                unit = "percentage_points"
            if unit is None and re.match(r"-\s*acre\b", sentence["text"][match.end():], re.I):
                unit = "acres"
            if match.group("currency"):
                unit = "USD_per_acre" if re.match(r"\s*(?:per\s+acre|/\s*acre)", sentence["text"][match.end():], re.I) else "USD"
            ref = {"document_id": source.document_id, "sentence_id": sentence["id"],
                   "start": match.start(), "end": match.end()}
            span = source.span(ref)
            nearby = sentence["text"][max(0, match.start() - 50):min(len(sentence["text"]), match.end() + 60)]
            citation = sentence["text"][:match.start()].rstrip().endswith("[") and re.match(r"\s*[,\]]", sentence["text"][match.end():])
            kind, scope_reason = "measurement", None
            if citation:
                kind, scope_reason = "citation_marker", "Citation number is not an outcome; repeated citations do not identify one study."
            elif unit in ("acres", "hectares"):
                kind, scope_reason = "deployment_scale", "Area/deployment scale excluded by task."
            elif unit is None and 1800 <= amount <= 2200 and (re.search(r"\b(?:in|of|during|our)\s*$", sentence["text"][:match.start()], re.I)
                    or re.match(r"\s*(?:deployment|trial|study|survey)\b", sentence["text"][match.end():], re.I)):
                kind, scope_reason = "context_year", "Year is contextual evidence, not a standalone measured outcome."
            elif re.search(r"download", nearby, re.I):
                kind, scope_reason = "background_statistic", "Downloads excluded by task."
            elif re.search(r"images?\s+annually|images?\s+per\s+year", nearby, re.I):
                kind, scope_reason = "background_statistic", "Annual image-processing volume excluded by task."
            elif re.search(r"market.*(?:grow|reach)|(?:projects?|forecast).*market", sentence["text"], re.I):
                kind, scope_reason = "projection", "Market size/growth projection excluded by task; preserved as projection in accounting."
            candidate = {"id": f"n{len(candidates) + 1:03d}", "document_id": source.document_id,
                         "source_sha256": source.metadata["content_sha256"], "sentence_id": sentence["id"],
                         "expression": match.group(), "value": amount, "unit": unit, "kind": kind,
                         "scope_reason": scope_reason, "reference": ref, "source_span": span,
                         "previous_expression_end": matches[occurrence - 1].end() if occurrence else 0,
                         "next_expression_start": matches[occurrence + 1].start() if occurrence + 1 < len(matches) else len(sentence["text"]),
                         "range_group": None}
            candidates.append(candidate)
        local = [candidate for candidate in candidates if candidate["sentence_id"] == sentence["id"]]
        for left, right in zip(local, local[1:]):
            between = sentence["text"][left["reference"]["end"]:right["reference"]["start"]]
            prefix = sentence["text"][:left["reference"]["start"]]
            if left["unit"] is None and right["unit"] and re.fullmatch(r"\s*(?:-|–|—|to)\s*", between):
                left["unit"] = right["unit"]
                left["unit_source_reference"] = right["reference"]
            if left["unit"] == right["unit"] and left["unit"] and (re.fullmatch(r"\s*(?:-|–|—|to)\s*", between)
                    or (re.search(r"\bbetween\s*$", prefix, re.I) and re.fullmatch(r"\s*and\s*", between, re.I))):
                group = "r:" + left["id"] + ":" + right["id"]
                left["range_group"] = right["range_group"] = group
    return candidates


def model_inventory(candidates):
    return [{"id": candidate["id"], "sentence_id": candidate["sentence_id"],
             "expression": candidate["expression"], "value": candidate["value"],
             "unit": candidate["unit"], "range_group": candidate["range_group"]} for candidate in candidates]


def initial_ledger(candidates):
    return [{"candidate_id": candidate["id"], "document_id": candidate["document_id"],
             "source": candidate["source_span"], "expression": candidate["expression"],
             "value": candidate["value"], "unit": candidate["unit"],
             "state": "outside_scope" if candidate["scope_reason"] else "unresolved",
             "reason": candidate["scope_reason"] or "No supported association yet.",
             "claim_ids": [], "role": candidate["kind"], "explicit_model_accounting": False}
            for candidate in candidates]
