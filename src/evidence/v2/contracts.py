"""Content-addressed evidence and explicit support/processing contracts."""
from __future__ import annotations
import hashlib
import json
from enum import Enum

class Support(str, Enum):
    SUPPORTED = "supported"
    UNRESOLVED = "unresolved"
    INAPPLICABLE = "inapplicable"
    CONTRADICTED = "contradicted"

TERMINAL = {"processed", "rejected", "unresolved", "deferred"}

def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()

def support(state, refs=(), reason=""):
    return {"status": Support(state).value, "evidence_ids": list(refs), "reason": reason}

def account(candidate, state, reason, fact_ids=()):
    if state not in TERMINAL or not reason:
        raise ValueError("Every candidate needs a terminal state and a reason")
    return {"candidate_id": candidate["id"], "state": state, "reason": reason,
            "fact_ids": list(fact_ids)}

def coverage(document, decisions):
    known = {c["id"] for c in document["candidates"]}
    rows = {d["candidate_id"]: d for d in decisions}
    if len(rows) != len(decisions) or set(rows) != known:
        raise ValueError("Candidate accounting must be a bijection")
    counts = {s: sum(d["state"] == s for d in rows.values()) for s in TERMINAL}
    pages = document["pages"]
    complete = not counts["deferred"] and all(p["status"] == "inventoried" and p.get("table_status") != "unresolved" for p in pages)
    return {"pages_available": len(pages), "pages_inventoried": sum(
                p["status"] == "inventoried" for p in pages),
            "candidate_total": len(known), "accounted": len(rows), **counts,
            "processing_complete": complete,
            "semantic_complete": complete and not counts["unresolved"],
            "unavailable_supplements": "unknown unless explicitly supplied"}

def verify_document(document):
    ids = [u["id"] for u in document["units"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evidence identities")
    for unit in document["units"]:
        if unit["source_sha256"] != document["source_sha256"]:
            raise ValueError("Foreign source evidence")
    evidence={u["id"]:u for u in document["units"]}
    for candidate in document["candidates"]:
        if candidate["unit_id"] not in evidence:
            raise ValueError("Candidate references missing evidence")
        unit=evidence[candidate["unit_id"]]
        if "start" in candidate and "end" in candidate and candidate.get("raw_text") is not None:
            if unit["raw_text"][candidate["start"]:candidate["end"]]!=candidate["raw_text"]:
                raise ValueError("Candidate span does not reproduce source text")
    return evidence
