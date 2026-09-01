"""P4 - abstention gate. Turns a verified+attributed evidence item into a
final RETURNED / ABSTAINED verdict. Prefer abstaining over an unsupported or
mis-attributed answer.
"""
from __future__ import annotations

from .schema import (RETURNED, ABSTAINED, EXPLICIT, INFERRED, MISSING, UNSUPPORTED,
                     CITED_PAPER, UNKNOWN, OWN_PAPER, FULLTEXT_ONLY_FIELDS)

# fields where we require author-ownership before returning a number
OWNERSHIP_REQUIRED = {"results", "metrics"}


def decide(item: dict) -> dict:
    f = item["field"]
    st = item["evidence_status"]

    if st in (MISSING, UNSUPPORTED):
        item["final"] = ABSTAINED
        item["abstain_reason"] = item.get("abstain_reason") or f"evidence_status={st}"
        return item

    if not item.get("provenance_valid"):
        item["final"] = ABSTAINED
        item["abstain_reason"] = "provenance_not_established"
        return item

    if f in FULLTEXT_ONLY_FIELDS and st == INFERRED:
        item["final"] = ABSTAINED
        item["abstain_reason"] = "inferred_not_explicit_for_quantitative_field"
        return item

    if f in OWNERSHIP_REQUIRED:
        attr = item.get("attribution", UNKNOWN)
        if attr == CITED_PAPER:
            item["final"] = ABSTAINED
            item["abstain_reason"] = "result_attributed_to_cited_work"
            return item
        if attr == UNKNOWN:
            item["final"] = ABSTAINED
            item["abstain_reason"] = "ownership_unverified"
            return item

    item["final"] = RETURNED
    item["abstain_reason"] = None
    return item
