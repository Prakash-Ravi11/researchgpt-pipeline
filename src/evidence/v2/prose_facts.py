"""Reuse October source ownership/qualifier validation; copy measurements by IDs."""
from decimal import Decimal
from .contracts import identity, support

def adapt_supported_prose(source, result):
    from src.evidence.prose_attribution.inventory import inventory
    source_numbers = {n["id"]: n for n in inventory(source)}
    facts = []
    for record in result.get("accepted_claims", []):
        if not record.get("published") or record.get("status") != "supported":
            continue
        ids = record["proposed"]["candidate_ids"]
        if any(i not in source_numbers for i in ids):
            raise ValueError("Unknown original numeric occurrence")
        old = record["measurement"]
        # The existing validator proves occurrence/value/qualifier/condition identity.
        values = [source_numbers[i] for i in ids]
        raw = " ; ".join(n["expression"] for n in values)
        measurement = {k: (str(Decimal(str(old[k]))) if old.get(k) is not None else None)
                       for k in ("value", "lower", "upper")}
        if old["kind"]=="scalar":
            import re
            from .measurements import NUMBER
            matching=[n for n in values if n["value"]==old["value"]]
            if len(matching)!=1:
                continue
            expression=matching[0]["expression"].replace("\u2212","-").replace(",","")
            token=re.search(NUMBER,expression)
            if not token:
                continue
            scale=next((Decimal(power) for word,power in [("billion","1e9"),("million","1e6"),("thousand","1e3")]
                        if word in expression.casefold()),Decimal(1))
            measurement["value"]=str(Decimal(token.group())*scale)
        measurement.update({"kind": old["kind"], "raw": raw, "unit": old["unit"],
            "scale": "percent" if old["unit"] == "percent" else "source_reported",
            "bound": old["qualifier"], "direction": old["direction"],
            "negated": old["negated"], "conditions": old["conditions"],
            "topic_qualifiers": old.get("topic_qualifiers", []),
            "uncertainty": None, "uncertainty_type": None, "footnote_marker": None})
        fields = {}
        for key, decision in record["field_support"].items():
            state = decision["status"]
            state = "contradicted" if state == "rejected" else state
            if state == "supported" and key in ("location", "year", "population") and record.get(key) is None:
                state = "inapplicable"
            fields[key] = support(state, decision.get("source_references", []), decision.get("reason", ""))
        spans = record["quotation"]["selected_spans"]
        native_occurrences=[]
        for number in values:
            span=number["source_span"]
            block=next(b for b in source.blocks if b["raw_start"]<=span["raw_start"]<b["raw_end"])
            native_occurrences.append({"block_id":block["id"],"start":span["raw_start"]-block["raw_start"],
                                       "end":span["raw_end"]-block["raw_start"]})
        lineage = {"original_source":source.metadata.get("original_source_sha256"),
                   "native_occurrences":native_occurrences,
                   "source": source.metadata["content_sha256"],
                   "representation": source.metadata.get("source_version", "prose-source-v1"),
                   "numeric_occurrences": ids, "spans": [s["sentence_id"] for s in spans],
                   "scope": record.get("scope_group_id")}
        facts.append({"id": identity(lineage), "paper_id": source.document_id, "kind": "numeric",
            "source_sha256":source.metadata.get("original_source_sha256",source.metadata["content_sha256"]), "category": "source_reported", "subject": record["subject"], "metric": record["outcome"],
            "metric_label": record["outcome"], "measurement": measurement,
            "experimental_scope": {"population": record.get("population"), "conditions": old["conditions"]},
            "caption": None, "reporting_source": source.metadata["content_sha256"],
            "measurement_origin": None, "method_origin": None,
            "modality": "negated" if old["negated"] else record.get("claim_role"),
            "location": record["location"], "year": record["year"], "field_support": fields,
            "evidence_ids": [s["sentence_id"] for s in spans], "source_lineage": lineage,
            "quotation": record["quotation"], "decision": "accepted"})
    return facts
