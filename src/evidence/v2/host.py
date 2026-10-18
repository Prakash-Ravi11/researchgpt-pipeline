"""Deterministic pre-model facts and accounting, shared by extraction and recovery."""
from .contracts import account, identity, verify_document
from .table_facts import build_table_facts


def build_host_checkpoint(document):
    verify_document(document)
    facts, cell_decisions, packets = build_table_facts(document)
    evidence = {u["id"]: u for u in document["units"]}
    decisions = []
    for candidate in document["candidates"]:
        state, reason, ids = cell_decisions.get(candidate["unit_id"],
            ("unresolved", "relationship_requires_supported_event_packet", []))
        if candidate["table_id"] and candidate["unit_id"] not in cell_decisions:
            state, reason = "unresolved", "table_expression_or_header_role_unresolved"
        decisions.append(account(candidate, state, reason, ids))
    # Exact source quotations preserve nonnumeric outcomes; they are never rewritten as own-paper findings.
    for candidate in document["candidates"]:
        if candidate["kind"] != "qualitative" or not candidate.get("outcome_signal"):
            continue
        unit = evidence[candidate["unit_id"]]
        if any(c["unit_id"] == unit["id"] and c["kind"] == "numeric" for c in document["candidates"]):
            continue
        lineage = {"source": document["source_sha256"], "representation": document["representation_id"],
                   "unit": unit["id"]}
        fact = {"id": identity(lineage), "paper_id": document["paper_id"], "kind": "qualitative",
            "source_sha256":document["source_sha256"], "category": "source_quotation", "quotation": unit["raw_text"],
            "subject": None, "metric": None, "metric_label": None, "measurement": None,
            "measurement_origin": None, "method_origin": None, "modality": "source_quotation",
            "experimental_scope": {}, "reporting_source": document["source_sha256"],
            "field_support": {"quotation": {"status": "supported", "evidence_ids": [unit["id"]],
                                               "reason": "Verbatim source quotation; no inferred ownership"}},
            "evidence_ids": [unit["id"]], "source_lineage": lineage, "decision": "accepted"}
        facts.append(fact)
        for decision in decisions:
            if decision["candidate_id"] == candidate["id"]:
                decision.update(state="processed", reason="verbatim_qualitative_source_quotation", fact_ids=[fact["id"]])
    return facts, decisions, packets
