"""Prove when the current host policy cannot accept any proposal in a packet.

This is a computation guard, not evidence that a source contains no outcomes.
Blocked candidates remain deferred and retain their original recall denominator.
"""
from .contracts import verify_document
from .table_facts import relation_for_cell, validate_relation


def table_preflight(document, packet):
    evidence=verify_document(document)
    table=next(t for t in document["tables"] if t["id"]==packet["table_id"])
    cells=[evidence[i] for i in table["cell_ids"]]
    possible=[];blocked=[]
    for identifier in packet["measurement_ids"]:
        expected,reason=relation_for_cell(table,cells,evidence[identifier])
        fact,issues=validate_relation(document,table,expected,evidence) if expected else (None,[reason])
        if fact:possible.append(identifier)
        else:blocked.append({"unit_id":identifier,"reason":issues[0]})
    return {"can_propose":bool(possible),"admissible_measurement_ids":possible,
            "blocked":blocked,"reason":"current_host_table_rules_require_source_or_structure_repair"}


def prose_preflight(source):
    from src.evidence.prose_attribution.inventory import inventory
    from src.evidence.prose_attribution.support import discourse
    candidates=inventory(source);frames=discourse(source,candidates)
    possible=[c["id"] for c in candidates if not c["scope_reason"]
              and frames[c["id"]]["status"]=="supported"]
    # assess_claim requires a supported ownership frame before publishing a core
    # claim. Model-selected IDs and labels cannot supply a missing host witness.
    return {"can_propose":bool(possible),"candidate_ids":possible,
            "candidate_count":len(candidates),
            "reason":"current_prose_validator_has_no_supported_ownership_witness"}
