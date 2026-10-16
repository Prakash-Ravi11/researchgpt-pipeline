"""Deterministic quantitative summaries of accepted records only."""


def _number(value):
    return str(int(value)) if isinstance(value, (int, float)) and float(value).is_integer() else str(value)


def quantitative_summary(records):
    lines = []
    for record in records:
        if not record.get("published") or record.get("status") != "supported":
            continue
        measurement = record["measurement"]
        value = (f"{_number(measurement['lower'])}–{_number(measurement['upper'])}" if measurement["kind"] == "range"
                 else _number(measurement["value"]))
        qualifier = measurement["qualifier"]
        qualifier_text = {"exact": "", "approximate": "approximately ", "estimated": "an estimated ",
                          "up_to": "up to ", "within": "within ", "as_early_as": "as early as ",
                          "more_than": "more than ", "less_than": "less than "}[qualifier]
        role = record.get("claim_role")
        lead = ("The source's authors report their trial of" if role == "original_result"
                else "The source projects" if role == "projection" else "The review reports" if role == "cited_result"
                else "The source reports")
        outcome = record["outcome"].replace("_", " ")
        text = f"{lead} {record['subject']}: {qualifier_text}{value} {measurement['unit']} for {outcome}"
        if measurement.get("negated"):
            text += "; this reduction was not observed"
        else:
            text += f" ({measurement['direction'].replace('_', ' ')})"
        if record.get("population"):
            text += " among " + record["population"]
        for condition in measurement.get("conditions", []):
            text += (f", within {_number(condition['value'])} {condition['unit']} error" if condition["kind"] == "error_threshold"
                     else f", compared with {_number(condition['value'])} {condition['unit']} baseline")
        for topic in measurement.get("topic_qualifiers", []):
            if topic not in outcome:
                text += ", " + topic
        context = [str(record[field]) for field in ("location", "year") if record.get(field) is not None]
        if context:
            text += " [" + ", ".join(context) + "]"
        lines.append({"claim_id": record["claim_id"], "text": text + ".", "source_regions": record["source_regions"],
                      "claim_role": role, "population": record.get("population"),
                      "qualifier": qualifier, "direction": measurement["direction"],
                      "conditions": measurement.get("conditions", [])})
    return lines
