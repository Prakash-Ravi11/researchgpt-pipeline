from copy import deepcopy

from src.evidence.prose_attribution.selection import choose_record


def assessed(ident, *, year=None, location=None, published=True, subject="DeltaDrip", scope="doc:s001:deployment"):
    return {"claim_id": ident, "published": published, "subject": subject, "outcome": "water_use_reduction",
            "scope_group_id": scope, "location": location, "year": year, "population": None,
            "claim_role": "cited_result", "measurement": {"kind": "scalar", "value": 17, "lower": None,
            "upper": None, "unit": "percent", "qualifier": "exact", "direction": "decrease", "negated": False,
            "conditions": []}, "field_support": {field: {"status": "supported"} for field in
                                                   ("year", "location", "population", "claim_role")},
            "evidence_text": ident, "proposed": {"raw": ident}}


def test_supported_context_loss_retains_atomic_earlier_record_and_raw_evidence():
    current, incoming = assessed("a0:c0", year=2026), assessed("a1:c0")
    before = deepcopy((current, incoming))
    chosen, decision = choose_record(current, incoming)
    assert chosen is current and chosen["year"] == 2026 and chosen["evidence_text"] == "a0:c0"
    assert decision["dropped_supported_fields"] == ["year"]
    assert decision["fields_or_evidence_merged"] is False
    assert (current, incoming) == before


def test_more_complete_supported_retry_can_replace_previous_record():
    current, incoming = assessed("a0:c0"), assessed("a1:c0", year=2026)
    chosen, decision = choose_record(current, incoming)
    assert chosen is incoming and decision is None


def test_different_core_or_scope_is_not_a_context_retention_match():
    current = assessed("a0:c0", year=2026)
    for incoming in (assessed("a1:c0", subject="OtherTool"), assessed("a1:c0", scope="doc:s003:deployment")):
        chosen, decision = choose_record(current, incoming)
        assert chosen is incoming and decision is None


def test_rejected_retry_never_replaces_supported_record():
    current, incoming = assessed("a0:c0", year=2026), assessed("a1:c0", published=False)
    chosen, decision = choose_record(current, incoming)
    assert chosen is current and decision is None
