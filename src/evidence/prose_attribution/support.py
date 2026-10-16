"""Conservative, explicit source-relationship assessment, separate from spans.

These are automated semantic rules, not independently human-verified truth.
An exact quotation, nearby name or broad paragraph does not pass these rules by
itself. Unlicensed/ambiguous references remain unresolved.
"""
from __future__ import annotations

import re
import math

from .schema import claim_record
from .source import ReferenceError
from . import SUPPORT_VERSION
from .support_refs import literal, unique_refs, context_witnesses, field_witnesses, normalize_area_location

NAME = r"[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,2}"
STOP_NAMES = {"The", "A", "An", "In", "Its", "This", "Case Study", "Another", "One"}
TOPIC_ALIASES = {"usage": "use", "saved": "saving", "savings": "saving", "losses": "loss", "loss": "loss",
                 "costs": "cost", "fields": "field", "plots": "plot", "harvest": "harvesting",
                 "pesticide-use": "pesticide", "pesticides": "pesticide", "chemicals": "chemical"}


def anchors(text):
    found = []
    patterns = [
        r"(?P<name>" + NAME + r")[’']s\s+[^.;]{0,100}?(?:system|app|platform|recommendations)",
        r"(?P<name>" + NAME + r")\s+(?:app|system|platform)\b",
        r"(?P<name>" + NAME + r")\s+(?:implemented|reduced|increased|raised|lowered|provided)\b",
        r"(?:survey\s+of|using|used)\s+(?:the\s+)?(?P<name>" + NAME + r")\s+(?:users|app|system)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = match.group("name")
            # A location embedded in the grammatical subject (a farm in Iowa
            # implemented ...) is not the named platform doing the implementing.
            if re.search(r"\b(?:in|at|near)\s*$", text[:match.start("name")], re.I) and re.search(r"implemented", match.group(), re.I):
                continue
            if name not in STOP_NAMES and name not in [item["subject"] for item in found]:
                found.append({"subject": name, "start": match.start("name"), "end": match.end("name"),
                              "witness": match.group(), "rule": "named_platform_in_use_or_outcome_predicate"})
    return sorted(found, key=lambda item: item["start"])


def nouns(text):
    return set(re.findall(r"\b(?:system|app|platform|farm|vineyard|trial|deployment|predictions?|forecasts?)\b", text.lower()))


def general_scope(text):
    return bool(re.search(r"among (?:its|the) users|users worldwide|worldwide|global|survey of .*users|download|images? annually", text, re.I))


def ambiguous_source(text):
    return bool(re.search(r"does not identify|not identify which|reading order is uncertain|unclear which|cannot determine", text, re.I))


def clause_for(text, position):
    boundaries = [0, len(text)]
    for match in re.finditer(r";|\bwhile\b|\bwhereas\b", text, re.I):
        boundaries += [match.start(), match.end()]
    ordered = sorted(set(boundaries))
    return next((text[a:b], a) for a, b in zip(ordered, ordered[1:]) if a <= position < b)


def discourse(source, candidates):
    """Build explicit named/anaphoric links and independent context scopes."""
    frames, active, pending_context, last_measurement = {}, [], None, None
    for unit in source.sentences:
        text = unit["text"]
        named = anchors(text)
        if re.search(r"\bCase Study:|\bExample:|\banother cited deployment\b|\ba later survey\b", text, re.I):
            active = []
            last_measurement = None
        if re.search(r"case involved|a\s+(?:[\w,-]+\s+){0,5}(?:farm|vineyard)\s+in\b", text, re.I) and not named:
            pending_context = unit["id"]
        local = [candidate for candidate in candidates if candidate["sentence_id"] == unit["id"]]
        for candidate in local:
            clause, clause_start = clause_for(text, candidate["reference"]["start"])
            clause_named = anchors(clause)
            required = {unit["id"]}
            frame = {"status": "unresolved", "subject": None, "context_ids": [], "required_refs": required,
                     "rule": None, "reason": "No explicit ownership predicate/reference was established.",
                     "global_scope": general_scope(clause), "unit_id": unit["id"]}
            coordinated = re.search(r"(?P<names>" + NAME + r"\s+and\s+" + NAME + r")\s+(?:reduced|increased|raised|lowered)", clause)
            if "respectively" in clause.lower() and coordinated:
                names = coordinated.group("names").split(" and ")
                quantities = [item for item in local if item["kind"] == "measurement" and item["unit"] == candidate["unit"]]
                if len(names) == len(quantities) and candidate in quantities:
                    frame.update(status="supported", subject=names[quantities.index(candidate)],
                                 rule="explicit_respectively_ordered_pair", reason="Ordered entity/value lists have equal length and respectively licenses pairing.")
            elif len(clause_named) == 1:
                owner = clause_named[0]["subject"]
                context_ids = [unit["id"]]
                if pending_context and re.search(r"\bthe farm\b|\bthe vineyard\b", clause, re.I):
                    context_ids.append(pending_context)
                    required.add(pending_context)
                frame.update(status="supported", subject=owner, context_ids=context_ids,
                             rule="named_platform_predicate", reason=clause_named[0]["witness"])
            elif len(clause_named) > 1 or (coordinated and "respectively" not in clause.lower()):
                frame["reason"] = "Several named platforms are present without an explicit value pairing."
            else:
                # A reference must name its noun/continuation; a name merely
                # appearing in a nearby paragraph is never enough.
                reference = re.search(r"\b(?:the (system|app|platform|farm|vineyard|predictions?|forecasts?)|the same (trial|deployment)|its (predictions?|forecasts?)|this (?:translated|advance knowledge))\b", clause, re.I)
                if reference:
                    noun = next((group.lower() for group in reference.groups() if group), None)
                    if noun in ("prediction", "predictions", "forecast", "forecasts"):
                        noun = "system"
                    compatible = [item for item in active if noun is None or noun in item["nouns"]
                                  or (noun in ("trial", "deployment") and "deployment" in item["nouns"])]
                    distinct = {item["subject"] for item in compatible}
                    if len(distinct) == 1:
                        parent = compatible[-1]
                        crosses = source.sentence(parent["anchor_id"])["block_id"] != unit["block_id"]
                        missing_order = any(block["reading_order_status"] == "missing" for block in source.blocks)
                        if crosses and missing_order and "same" not in reference.group().lower():
                            frame["reason"] = "Cross-block anaphora has missing reading-order metadata and no explicit continuation."
                        else:
                            required.add(parent["anchor_id"])
                            if reference.group().lower().startswith("this"):
                                if last_measurement is None:
                                    frame["reason"] = "This has no identified measurement antecedent."
                                    frames[candidate["id"]] = frame
                                    continue
                                required.update(last_measurement["required_refs"])
                            frame.update(status="supported", subject=parent["subject"],
                                         context_ids=parent["context_ids"], rule="explicit_unique_anaphoric_link",
                                         reason=reference.group() + " has one compatible named source antecedent.")
                    else:
                        frame["reason"] = "Anaphoric reference has zero or multiple compatible antecedents."
                elif len({item["subject"] for item in active}) == 1:
                    parent = active[-1]
                    trial_text = source.sentence(parent["anchor_id"])["text"]
                    if re.search(r"\bour .*trial\b|\bwe (?:used|conducted|tested)\b", trial_text, re.I):
                        required.add(parent["anchor_id"])
                        frame.update(status="supported", subject=parent["subject"], context_ids=parent["context_ids"],
                                     rule="explicit_single_original_trial_reporting_scope",
                                     reason="One explicitly declared original-author trial supplies the reporting scope, with no competing platform or topic reset.")
            if ambiguous_source(text):
                frame.update(status="unresolved", subject=None, reason="Source explicitly leaves ownership/reading order ambiguous.")
            if frame["global_scope"]:
                frame["context_ids"] = []
            frames[candidate["id"]] = frame
            if candidate["kind"] == "measurement" and frame["status"] == "supported":
                last_measurement = frame
        if named:
            for item in named:
                context_ids = [unit["id"]]
                if pending_context and re.search(r"\bthe farm\b|\bthe vineyard\b", text, re.I):
                    context_ids.append(pending_context)
                entry = {"subject": item["subject"], "anchor_id": unit["id"],
                         "nouns": nouns(text) | {"deployment"},
                         "context_ids": [] if general_scope(text) else context_ids}
                active = [old for old in active if old["subject"] != item["subject"]] + [entry]
    return frames


def canonical_topic(word):
    return TOPIC_ALIASES.get(word.lower(), word.lower().rstrip("s"))


def measurement_features(source, candidate, candidates):
    unit = source.sentence(candidate["sentence_id"])
    text, ref = unit["text"], candidate["reference"]
    grouped = [item for item in candidates if candidate["range_group"] and item["range_group"] == candidate["range_group"]]
    first = grouped[0] if grouped else candidate
    last = grouped[-1] if grouped else candidate
    begin = first["previous_expression_end"]
    end = last["next_expression_start"]
    left, right = text[begin:first["reference"]["start"]], text[last["reference"]["end"]:end]
    if "respectively" in text.lower() and not grouped:
        ordered = [item for item in candidates if item["sentence_id"] == candidate["sentence_id"]
                   and item["kind"] == "measurement" and item["unit"] == candidate["unit"]]
        if ordered:
            left = text[ordered[0]["previous_expression_end"]:ordered[0]["reference"]["start"]]
    # Direction/outcome predicates are coupled to this occurrence, not to any
    # number or keyword elsewhere in a broad source paragraph.
    left = re.split(r"[,;]|\b(?:and|while|whereas)\b", left, flags=re.I)[-1]
    right = re.split(r"\b(?:and|while|whereas|resulting)\b", right, flags=re.I)[0]
    phrase = left + " <VALUE> " + right
    prefix = left[-60:]
    qualifier = "exact"
    for regex, label in ((r"as early as", "as_early_as"), (r"up to", "up_to"), (r"estimated", "estimated"),
                         (r"approximately|approximate|about", "approximate"), (r"within", "within"),
                         (r"more than", "more_than"), (r"less than", "less_than")):
        if re.search(regex, prefix, re.I):
            qualifier = label
            break
    negated = bool(re.search(r"not observed|did not|was not|were not|no .*reduction", phrase, re.I))
    direction = "not_observed" if negated else "none"
    if direction == "none":
        if re.search(r"increas|rose|raised", phrase, re.I):
            direction = "increase"
        elif re.search(r"reduc|decreas|lower|fell", phrase, re.I):
            direction = "decrease"
        elif re.search(r"saving|saved", phrase, re.I):
            direction = "savings"
    special = None
    if candidate["unit"] == "days" and re.search(r"forecast|before harvest", text, re.I):
        special, direction = "forecast_lead_time", "lead_time"
    elif re.search(r"error|margin", text, re.I) and re.search(r"within\s+(?:a\s+)?$", prefix, re.I):
        special, direction = "prediction_error_threshold", "threshold"
    elif re.search(r"error|margin", text, re.I) and re.search(r"for\s*$", prefix, re.I) and re.search(r"of (?:the )?(fields|plots)", right, re.I):
        special, direction = "fields_within_prediction_error_threshold", "proportion"
    return {"phrase": phrase, "qualifier": qualifier, "direction": direction, "negated": negated,
            "special_outcome": special, "range_candidates": [item["id"] for item in grouped]}


def outcome_supported(outcome, feature):
    aliases = {"forecast_accuracy": "fields_within_prediction_error_threshold", "forecast_error": "prediction_error_threshold",
               "water_saved": "water_savings", "pumping_energy_cost_reduction": "energy_cost_reduction_for_pumping"}
    label = aliases.get(outcome, outcome)
    if feature["special_outcome"]:
        if label == feature["special_outcome"]:
            return True
        if feature["special_outcome"] == "forecast_lead_time":
            return "lead" in label and ("forecast" in label or "prediction" in label)
        if feature["special_outcome"] == "prediction_error_threshold":
            return "error" in label and not any(token in label for token in ("fields", "plots", "proportion", "accuracy"))
        return any(token in label for token in ("fields", "plots", "proportion", "accuracy"))
    if label in ("forecast_lead_time", "prediction_error_threshold", "fields_within_prediction_error_threshold"):
        return False
    ignored = {"reduction", "increase", "decrease", "saving", "savings", "saved", "for", "per", "in", "of", "use", "usage"}
    topics = [canonical_topic(word) for word in label.split("_") if word not in ignored]
    source_topics = {canonical_topic(word) for word in re.findall(r"[A-Za-z-]+", feature["phrase"])}
    if not topics or not all(topic in source_topics for topic in topics):
        return False
    if "reduction" in label and feature["direction"] not in ("decrease", "not_observed"):
        return False
    if "increase" in label and feature["direction"] != "increase":
        return False
    if any(token in label for token in ("saved", "saving")) and feature["direction"] not in ("savings", "decrease"):
        return False
    return True


def status(value, reason, refs=None, rule=None):
    return {"status": value, "reason": reason, "source_references": refs or [], "assessment_rule": rule}


def assess_claim(source, candidates, frames, proposed, claim_id):
    record = claim_record(source.document_id, claim_id, proposed)
    record["support_version"] = SUPPORT_VERSION
    adjustments = []
    references = proposed.get("references") or {}
    selected, spans, errors = set(), {}, []
    for field, refs in references.items():
        try:
            spans[field] = [source.span(ref) for ref in refs]
            selected.update(span["sentence_id"] for span in spans[field])
        except (ReferenceError, TypeError) as error:
            errors.append({"field": field, "error": str(error)})
    record["structural_validation"] = {"status": "rejected" if errors else "supported", "errors": errors,
                                       "document_id_verified": not errors,
                                       "does_not_establish_semantic_ownership": True}
    if errors:
        record.update(status="rejected", semantic_assessment=status("rejected", "Invalid source reference."))
        return record
    selected_pairs = [(ref, span) for field, refs in references.items() for ref, span in zip(refs, spans[field])]
    by_id = {candidate["id"]: candidate for candidate in candidates}
    identifiers = proposed.get("candidate_ids") or []
    chosen = [by_id[identifier] for identifier in identifiers if identifier in by_id]
    if not chosen or len(chosen) != len(identifiers):
        record["semantic_assessment"] = status("rejected", "Unknown or empty numeric occurrence selection.")
        record["status"] = "rejected"
        return record
    if any(candidate["scope_reason"] for candidate in chosen):
        record["semantic_assessment"] = status("rejected", "Selected expression is outside the requested outcome scope.")
        record["status"] = "rejected"
        return record
    measurement = proposed.get("measurement") or {}
    candidate = chosen[0]
    frame, feature = frames[candidate["id"]], measurement_features(source, candidate, candidates)
    missing_links = sorted(frame["required_refs"] - selected)
    subject = proposed.get("subject")
    subject_matches = [(ref, span) for ref, span in selected_pairs if literal(subject, span["normalized_text"])]
    subject_named = bool(subject_matches)
    subject_refs = references.get("subject", [])
    if subject_named and not any(literal(subject, span["normalized_text"]) for span in spans.get("subject", [])):
        subject_refs = unique_refs(subject_matches)
        adjustments.append({"field": "subject", "operation": "source_reference_reclassification",
                            "before": references.get("subject", []), "after": subject_refs,
                            "assessment_rule": "exact_subject_in_already_selected_source",
                            "ownership_path": sorted(frame["required_refs"])})
    owner_status = frame["status"]
    same_named_entity = (isinstance(subject, str) and (subject == frame["subject"] or
                         (subject_named and isinstance(frame["subject"], str) and subject.startswith(frame["subject"] + "'s "))))
    platform_type_alias = bool(subject_named and isinstance(frame["subject"], str)
        and re.fullmatch(re.escape(frame["subject"]) + r"\s+(?:app|system|platform)", subject)
        and any(item["subject"] == frame["subject"] for _, span in subject_matches for item in anchors(span["normalized_text"])))
    if platform_type_alias:
        same_named_entity = True
        adjustments.append({"field": "subject", "operation": "normalization", "before": subject,
                            "after": frame["subject"], "assessment_rule": "source_literal_platform_type_suffix",
                            "source_references": unique_refs(subject_matches)})
    if not same_named_entity and subject_named and isinstance(subject, str) and isinstance(frame["subject"], str):
        possible_names = {item["subject"] for unit in source.sentences for item in anchors(unit["text"])
                          if item["subject"].startswith(subject + " ")}
        same_named_entity = possible_names == {frame["subject"]}
    if owner_status == "supported" and not same_named_entity:
        owner_status = "rejected"
    elif owner_status == "supported" and (missing_links or not subject_named):
        owner_status = "unresolved"
    record["field_support"]["subject"] = status(owner_status,
        "Explicit owner disagrees with proposed subject." if owner_status == "rejected" else
        "Missing selected ownership bridge/subject reference: " + ",".join(missing_links) if owner_status == "unresolved" else frame["reason"],
        subject_refs + references.get("ownership_bridge", []), frame["rule"])
    numeric_status, numeric_reason = "supported", "Values/units match selected original numeric occurrences."
    if any(item["sentence_id"] not in {span["sentence_id"] for span in spans.get("measurement", [])} for item in chosen):
        numeric_status, numeric_reason = "unresolved", "Selected numeric occurrence has no measurement reference."
    elif feature["range_candidates"]:
        expected = [by_id[identifier]["value"] for identifier in feature["range_candidates"]]
        if (set(identifiers) != set(feature["range_candidates"]) or measurement.get("kind") != "range"
                or measurement.get("lower") != min(expected) or measurement.get("upper") != max(expected)):
            numeric_status, numeric_reason = "unresolved", "Range components cannot be published as an exact scalar."
    elif (len(chosen) != 1 or measurement.get("kind") != "scalar" or type(measurement.get("value")) not in (int, float)
          or not math.isfinite(measurement["value"]) or measurement.get("value") != candidate["value"]):
        numeric_status, numeric_reason = "rejected", "Proposed scalar differs from selected source value."
    unit_aliases = {"%": "percent", "percentage": "percent", "percentage points": "percentage_points",
                    "USD/acre": "USD_per_acre", "$/acre": "USD_per_acre", "dollars per acre": "USD_per_acre"}
    normalized_unit = unit_aliases.get(measurement.get("unit"), measurement.get("unit"))
    if normalized_unit != candidate["unit"]:
        numeric_status, numeric_reason = "rejected", "Proposed unit/denominator differs from source notation."
    record["field_support"]["value"] = status(numeric_status, numeric_reason, references.get("measurement", []), "numeric_occurrence_identity_and_notation")
    record["field_support"]["unit"] = status("supported" if normalized_unit == candidate["unit"] else "rejected",
        "Unit and denominator come from source notation or a recorded value-independent alias.", references.get("measurement", []), "source_unit_notation")
    if feature["range_candidates"]:
        record["field_support"]["range_bounds"] = status(numeric_status, "Both original range occurrences and their ordered bounds are required.", references.get("measurement", []), "explicit_range_relationship")
    record["field_support"]["outcome"] = status("supported" if outcome_supported(proposed.get("outcome", ""), feature) else "unresolved",
        "Outcome must be coupled to this numeric occurrence's predicate, not a shared paragraph keyword.", references.get("measurement", []), "occurrence_coupled_outcome_predicate")
    if "loss" in proposed.get("outcome", "").split("_") and re.search(r"\blosses\b", feature["phrase"], re.I):
        adjustments.append({"field": "outcome", "operation": "topic_normalization", "source_form": "losses",
                            "canonical_form": "loss", "assessment_rule": "loss_losses_topic_identity"})
    qualifier_ok = measurement.get("qualifier") == feature["qualifier"]
    direction_ok = measurement.get("direction") == feature["direction"] and measurement.get("negated") == feature["negated"]
    record["field_support"]["qualifier"] = status("supported" if qualifier_ok and direction_ok else "rejected",
        "Qualifier, comparison direction and negation must match this expression's source scope.", references.get("measurement", []), "local_qualifier_direction_and_negation")
    record["field_support"]["direction"] = status("supported" if direction_ok else "rejected", "Comparison direction and negation follow the coupled source predicate.", references.get("measurement", []))
    conditions = []
    condition_status = "supported"
    if feature["special_outcome"] == "fields_within_prediction_error_threshold":
        thresholds = [item for item in candidates if item["sentence_id"] == candidate["sentence_id"]
                      and measurement_features(source, item, candidates)["special_outcome"] == "prediction_error_threshold"]
        proposed_conditions = measurement.get("conditions") or []
        population_text = " ".join(span["normalized_text"] for span in spans.get("population", []) + spans.get("condition", [])
                                   if span["sentence_id"] == candidate["sentence_id"])
        if (len(thresholds) != 1 or not proposed.get("population") or str(proposed["population"]).lower() not in population_text.lower()
                or not any(item.get("candidate_id") == thresholds[0]["id"] and item.get("operator") == "within" for item in proposed_conditions)):
            condition_status = "unresolved"
        else:
            threshold = thresholds[0]
            if threshold["sentence_id"] not in {span["sentence_id"] for span in spans.get("condition", [])}:
                condition_status = "unresolved"
            conditions = [{"kind": "error_threshold", "candidate_id": threshold["id"], "operator": "within",
                           "value": threshold["value"], "unit": threshold["unit"], "source_references": references.get("condition", [])}]
    elif measurement.get("conditions"):
        condition_units = {span["sentence_id"] for span in spans.get("condition", [])}
        for condition in measurement["conditions"]:
            baseline = by_id.get(condition.get("candidate_id"))
            sentence = source.sentence(candidate["sentence_id"])["text"]
            comparison = re.search(r"\b(?:compared (?:with|to)|relative to|versus|against)\b", sentence, re.I)
            if (condition.get("kind") != "baseline" or condition.get("operator") != "compared_with"
                    or baseline is None or baseline["sentence_id"] != candidate["sentence_id"]
                    or candidate["sentence_id"] not in condition_units or comparison is None
                    or baseline["reference"]["start"] < comparison.end()):
                condition_status = "unresolved"
            else:
                conditions.append({"kind": "baseline", "candidate_id": baseline["id"], "operator": "compared_with",
                                   "value": baseline["value"], "unit": baseline["unit"],
                                   "population": condition.get("population"), "source_references": references.get("condition", [])})
    record["field_support"]["condition"] = status(condition_status,
        "Conditional proportions require the source-linked threshold and population; arbitrary conditions remain unresolved.", references.get("condition", []), "explicit_threshold_proportion_relationship")
    core = [record["field_support"][field]["status"] for field in ("subject", "value", "outcome", "qualifier", "condition")]
    final_status = "rejected" if "rejected" in core else "unresolved" if "unresolved" in core else "supported"
    context_text = " ".join(source.sentence(identifier)["text"] for identifier in frame["context_ids"])
    context_refs = {span["sentence_id"] for span in spans.get("context", [])}
    selected_context = context_witnesses(source, frame, selected_pairs, anchors) if final_status == "supported" else []
    for field in ("location", "year"):
        value = proposed.get(field)
        field_refs = references.get("context", [])
        field_rule = "deployment_context_connection"
        if field == "location" and selected_context:
            value, normalization = normalize_area_location(value, selected_context, candidates)
            if normalization:
                adjustments.append(normalization)
        context_valid = bool(value is not None and frame["context_ids"] and set(frame["context_ids"]) <= context_refs
                             and re.search(r"(?<!\w)" + re.escape(str(value)) + r"(?!\w)", context_text, re.I))
        if value is not None and not context_valid and selected_context:
            witnesses = field_witnesses(field, value, selected_context, candidates)
            if witnesses:
                context_valid = True
                field_refs = unique_refs(witnesses)
                field_rule = "selected_deployment_context_reclassification"
                adjustments.append({"field": field, "operation": "source_reference_reclassification",
                                    "before": references.get("context", []), "after": field_refs,
                                    "assessment_rule": field_rule, "ownership_path": sorted(frame["required_refs"])})
        if value is None:
            available = (bool(re.search(r"\b(?:18|19|20|21)\d{2}\b", context_text)) if field == "year"
                         else bool(re.search(r"\b(?:in|at|near)\s+(?:the\s+)?[A-Z](?:[A-Za-z]+|\.[A-Z]\.)", context_text)))
            field_status = "unresolved" if available else "supported"
            reason = "Optional supported context not supplied; retain null." if available else "No deployment-specific context is established for this field."
        elif context_valid:
            field_status, reason = "supported", "Context is explicitly tied to the same deployment/antecedent."
        else:
            field_status, reason = "rejected", "Context is not tied to this claim; local context cannot propagate to general users."
        record["field_support"][field] = status(field_status, reason, field_refs, field_rule)
        if value is None and field == "location" and re.search(r"\b(?:in|at|near)\s+the\s+[A-Z]", context_text):
            adjustments.append({"field": field, "operation": "availability_diagnostic", "value_retained": None,
                                "assessment_rule": "article_before_named_location_detected"})
        if context_valid:
            record[field] = value
    population = proposed.get("population")
    population_ids = {candidate["sentence_id"]} | (set(frame["context_ids"]) if not frame["global_scope"] else set())
    population_text = " ".join(span["normalized_text"] for span in spans.get("population", []) + spans.get("condition", [])
                               if span["sentence_id"] in population_ids)
    population_ok = population is None or str(population).lower() in population_text.lower()
    record["population"] = population if population_ok else None
    record["field_support"]["population"] = status("supported" if population_ok else "unresolved", "Population must be explicit in the referenced statement.", references.get("population", []))
    role_text = " ".join(span["normalized_text"] for field in ("role", "subject", "ownership_bridge") for span in spans.get(field, []))
    explicitly_cited = bool(re.search(r"review quotes|prior study|another cited|cited deployment", role_text, re.I))
    expected_role = ("cited_result" if explicitly_cited else "original_result" if re.search(r"\bwe (?:used|conducted|tested)|\bour .*trial\b", role_text, re.I)
                     else "cited_result" if source.metadata.get("source_kind") == "narrative_overview" or re.search(r"cited|review|prior study|\[\d+\]", role_text, re.I) else None)
    role_ok = proposed.get("claim_role") == expected_role and expected_role is not None
    record["claim_role"] = expected_role if role_ok else None
    record["field_support"]["claim_role"] = status("supported" if role_ok else "unresolved",
        "Role comes from explicit first-person/cited reporting or provided document genre, not number presence.", references.get("role", []), "source_reporting_role")
    record.update(status=final_status, published=final_status == "supported",
                  semantic_assessment={"status": final_status, "method": "automated explicit predicate/anaphora assessment; not independent human review",
                                       "ownership_rule": frame["rule"], "required_refs": sorted(frame["required_refs"]),
                                       "missing_links": missing_links, "context_scope": "general_platform" if frame["global_scope"] else "deployment",
                                       "core_field_statuses": {field: record["field_support"][field]["status"] for field in ("subject", "value", "outcome", "qualifier", "condition")}})
    if adjustments:
        record["validation_adjustments"] = adjustments
    if final_status == "supported":
        record.update(subject=frame["subject"], outcome=feature["special_outcome"] or proposed["outcome"],
                      measurement={**measurement, "unit": normalized_unit, "conditions": conditions})
        record["normalization_decisions"] = [{"field": "subject", "before": subject, "after": frame["subject"], "rule": "verified_named_entity_label"}] if subject != frame["subject"] else []
        if normalized_unit != measurement.get("unit"):
            record["normalization_decisions"].append({"field": "unit", "before": measurement.get("unit"), "after": normalized_unit, "rule": "value_independent_unit_alias"})
        record["measurement"]["topic_qualifiers"] = ["for pumping"] if "pumping" in feature["phrase"].lower() and "energy" in feature["phrase"].lower() else []
        record["scope_group_id"] = source.document_id + ":" + min(frame["required_refs"]) + ":" + ("general_platform" if frame["global_scope"] else "deployment")
        record["compound_group_id"] = source.document_id + ":" + candidate["sentence_id"] if feature["special_outcome"] in ("prediction_error_threshold", "fields_within_prediction_error_threshold") else None
        selected_refs = list(dict.fromkeys(ref for values in references.values() for ref in values if isinstance(ref, str)))
        quotation = source.reconstruct(selected_refs)
        record.update(evidence_text=quotation["evidence_text"], source_regions=quotation["regions"], quotation=quotation)
    return record
