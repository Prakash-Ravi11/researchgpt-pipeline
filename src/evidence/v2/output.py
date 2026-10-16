"""Deterministic API-compatible scientific output; no legacy result fallback."""
from copy import deepcopy
from .contracts import identity

def render_fact(fact):
    if fact["kind"] == "qualitative":
        return "Source quotation (measurement ownership unresolved): " + fact["quotation"]
    m = fact["measurement"]
    # Preserve the actual reported expression, including uncertainty and bounds.
    unit = "" if not m["unit"] or m["unit"] in m["raw"] else " " + m["unit"]
    scope = fact.get("experimental_scope")
    context = " / ".join(x["text"] for x in scope) if isinstance(scope, list) else str(scope or "")
    qualifier = m.get("bound")
    prefix = {"up_to":"up to ", "approximate":"approximately ", "at_least":"at least "}.get(qualifier, "")
    negation = "Not observed: " if m.get("negated") else ""
    conditions = m.get("conditions", [])
    qualifiers = m.get("topic_qualifiers", [])
    extra = "; ".join(str(x) for x in qualifiers + conditions)
    tail = "; ".join(x for x in (context, extra) if x)
    suffix = f" ({tail})" if tail else ""
    if m["unit"] == "percent" and "%" in m["raw"]:
        unit = ""
    return f'{negation}{fact["subject"]}: {fact["metric_label"]} {prefix}{m["raw"]}{unit}{suffix}.'

def project_record(record, extraction):
    if extraction.get("enabled") is not True:
        return record
    result = deepcopy(record)
    facts = [deepcopy(f) for f in extraction["facts"] if f.get("decision") == "accepted"]
    rendered = " ".join(render_fact(f) for f in facts)
    # These legacy scientific prose fields cannot bypass the fact store.
    for field in ("results", "key_findings", "inferences", "summary"):
        result[field] = rendered
    result["quantitative_results"] = [{"method": f["subject"], "configuration": {"llm": None, "retriever": None},
        "dataset": None, "metric": f["metric_label"], "value": f["measurement"]["value"],
        "unit": f["measurement"]["unit"], "measurement": f["measurement"],
        "source": f.get("source", {}), "fact_id": f["id"],
        "source_lineage": f["source_lineage"], "evidence_ids": f["evidence_ids"]}
        for f in facts if f["kind"] == "numeric"]
    result["qualitative_results"] = [f for f in facts if f["kind"] == "qualitative"]
    result["scientific_facts"] = facts
    result["scientific_extraction"] = {"enabled": True, "policy_version": extraction["policy_version"],
        "coverage": extraction["coverage"], "run_id": extraction["run_id"],
        "source_sha256": extraction.get("source_sha256"),
        "state": extraction.get("state"), "reason": extraction.get("reason")}
    result["comparisons"] = []
    result["evidence"] = {field: [{"fact_id": f["id"], "source_lineage": f["source_lineage"],
        "evidence_ids": f["evidence_ids"], "value": render_fact(f)} for f in facts]
        for field in ("results", "key_findings", "summary", "inferences")}
    return result

def compatible_groups(facts):
    groups = {}
    for fact in facts:
        if fact["kind"] != "numeric":
            continue
        # Unknown study origin is never pooled across reporting sources.
        key = identity({"metric": fact["metric"], "unit": fact["measurement"]["unit"],
            "scale": fact["measurement"]["scale"], "scope": fact["experimental_scope"],
            "modality": fact["modality"], "measurement_origin": fact["measurement_origin"],
            "reporting_source": fact["reporting_source"],
            "table_or_event": fact["source_lineage"].get("scope",fact["source_lineage"].get("value"))})
        groups.setdefault(key, []).append(fact)
    return groups
