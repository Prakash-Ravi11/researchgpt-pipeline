"""Prefer an existing complete source record over a strictly weaker retry.

This selects whole assessed records; it never combines fields or evidence.
"""
SELECTION_VERSION = "supported-context-retention-v1"


def core(record):
    measurement = record.get("measurement") or {}
    return (record.get("subject"), record.get("outcome"), record.get("scope_group_id"),
            tuple(measurement.get(field) for field in ("kind", "value", "lower", "upper", "unit", "qualifier", "direction", "negated")),
            [{key: value for key, value in condition.items() if key != "source_references"}
             for condition in measurement.get("conditions", [])])


def supported_optional_fields(record):
    return {field for field in ("location", "year", "population", "claim_role")
            if record.get(field) is not None and record.get("field_support", {}).get(field, {}).get("status") == "supported"}


def choose_record(current, incoming):
    if current is None:
        return incoming, None
    if current["published"] and not incoming["published"]:
        return current, None
    if current["published"] and incoming["published"] and core(current) == core(incoming):
        previous, proposed = supported_optional_fields(current), supported_optional_fields(incoming)
        if proposed < previous:
            return current, {"assessment_rule": "retain_atomic_record_on_strict_supported_context_loss",
                             "kept_claim_id": current["claim_id"], "incoming_claim_id": incoming["claim_id"],
                             "dropped_supported_fields": sorted(previous - proposed),
                             "same_supported_core_and_scope": True, "fields_or_evidence_merged": False}
    return incoming, None
