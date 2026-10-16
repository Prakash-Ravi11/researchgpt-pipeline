from copy import deepcopy

from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.inventory import inventory
from src.evidence.prose_attribution.support import assess_claim, discourse


def make(text, blocks=None):
    source = SourceDocument.from_text("doc", text, blocks=blocks, metadata={"source_kind": "narrative_overview"})
    candidates = inventory(source)
    return source, candidates, discourse(source, candidates)


def proposal(candidate, subject, outcome, refs, **changes):
    result = {"candidate_ids": [candidate["id"]], "subject": subject, "outcome": outcome,
              "location": None, "year": None, "population": None, "claim_role": "cited_result",
              "measurement": {"kind": "scalar", "value": candidate["value"], "lower": None, "upper": None,
                              "unit": candidate["unit"], "qualifier": "exact", "direction": "decrease",
                              "negated": False, "conditions": []},
              "references": {field: list(refs) for field in ("subject", "measurement", "ownership_bridge", "context", "population", "condition", "role")}}
    result.update(changes)
    return result


def test_correct_span_and_broad_paragraph_do_not_validate_wrong_owner():
    source, candidates, frames = make("DeltaDrip reduced water use by 17%. OtherTool reduced crop losses by 23%.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = proposal(candidate, "OtherTool", "water_use_reduction", ["s001", "s002"])
    result = assess_claim(source, candidates, frames, p, "c1")
    assert result["structural_validation"]["status"] == "supported"
    assert result["status"] == "rejected" and not result["published"]
    assert result["subject"] is None and result["measurement"] is None


def test_general_users_keep_supported_owner_but_drop_false_local_context():
    source, candidates, frames = make("In 2020, farmers in River Vale using the DeltaDrip app reduced crop losses by 23%. The app reduced pesticide use by an estimated 17% among its users.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = proposal(candidate, "DeltaDrip", "pesticide_use_reduction", ["s001", "s002"], location="River Vale", year=2020)
    p["measurement"]["qualifier"] = "estimated"
    result = assess_claim(source, candidates, frames, p, "c1")
    assert result["status"] == "supported"
    assert result["subject"] == "DeltaDrip" and result["location"] is None and result["year"] is None
    assert result["field_support"]["year"]["status"] == "rejected"
    p["population"] = "farmers in River Vale"
    p["references"]["population"] = ["s001"]
    assert assess_claim(source, candidates, frames, p, "bad_population")["population"] is None


def test_explicit_cross_page_continuation_has_multiple_regions_and_required_bridge():
    blocks = [{"id": "b1", "text": "In 2020, a farm in River Vale used DeltaDrip's irrigation system.", "page": 1, "reading_order": 0},
              {"id": "b2", "text": "The same trial reduced water use by 17%.", "page": 2, "reading_order": 1}]
    source, candidates, frames = make("\n\n".join(b["text"] for b in blocks), blocks)
    candidate = next(c for c in candidates if c["value"] == 17)
    p = proposal(candidate, "DeltaDrip", "water_use_reduction", ["s001", "s002"], location="River Vale", year=2020)
    result = assess_claim(source, candidates, frames, p, "c1")
    assert result["published"] and result["year"] == 2020
    assert {r["page"] for r in result["source_regions"]} == {1, 2}
    p["references"] = {field: ["s002"] for field in p["references"]}
    assert assess_claim(source, candidates, frames, p, "c2")["status"] == "unresolved"


def test_respectively_enforces_order_not_same_number_or_keyword_proximity():
    source, candidates, frames = make("DeltaDrip and OtherTool reduced water use by 17% and 23%, respectively.")
    for candidate, owner in zip(candidates, ("DeltaDrip", "OtherTool")):
        p = proposal(candidate, owner, "water_use_reduction", ["s001"])
        assert assess_claim(source, candidates, frames, p, "c")["published"]
        p["subject"] = "OtherTool" if owner == "DeltaDrip" else "DeltaDrip"
        assert assess_claim(source, candidates, frames, p, "bad")["status"] == "rejected"


def test_explicit_ambiguous_source_stays_unresolved_despite_proposed_relationship():
    source, candidates, frames = make("DeltaDrip and OtherTool are irrigation platforms. Water use fell by 17%, but the source does not identify which platform produced it.")
    p = proposal(candidates[0], "DeltaDrip", "water_use_reduction", ["s001", "s002"])
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["status"] == "unresolved" and not result["published"]


def test_range_negation_and_percent_points_keep_numeric_meaning():
    source, candidates, frames = make("DeltaDrip reduced water use by 10-14%. DeltaDrip's system improved precision by 3 percentage points.")
    assert candidates[0]["unit"] == candidates[1]["unit"] == "percent"
    assert candidates[0]["range_group"] == candidates[1]["range_group"]
    assert candidates[2]["unit"] == "percentage_points"
    p = proposal(candidates[0], "DeltaDrip", "water_use_reduction", ["s001"])
    assert assess_claim(source, candidates, frames, p, "scalar")["status"] == "unresolved"
    p["candidate_ids"] = [candidates[0]["id"], candidates[1]["id"]]
    p["measurement"].update(kind="range", value=None, lower=10, upper=14)
    assert assess_claim(source, candidates, frames, p, "range")["published"]


def test_repeated_numeric_occurrences_and_citations_have_distinct_ids():
    source, candidates, frames = make("DeltaDrip reduced water use by 17% [2]. OtherTool reduced crop losses by 17% [2].")
    assert len({c["id"] for c in candidates}) == 4
    assert [c["kind"] for c in candidates] == ["measurement", "citation_marker", "measurement", "citation_marker"]
    assert candidates[0]["source_span"]["raw_start"] != candidates[2]["source_span"]["raw_start"]


def test_location_next_to_implemented_is_not_misread_as_a_platform():
    source, candidates, frames = make("In 2020, a 2,000-acre farm in River Vale implemented DeltaDrip's irrigation system. The farm reduced water use by 17%.")
    area = next(c for c in candidates if c["value"] == 2000)
    assert area["kind"] == "deployment_scale"
    measured = next(c for c in candidates if c["value"] == 17)
    assert frames[measured["id"]]["subject"] == "DeltaDrip"


def test_absolute_saving_does_not_inherit_the_next_outcomes_reduction_direction():
    from src.evidence.prose_attribution.support import measurement_features
    source, candidates, frames = make("DeltaDrip's system saved approximately 60 million gallons and reduced energy costs by 17%.")
    feature = measurement_features(source, candidates[0], candidates)
    assert feature["direction"] == "savings" and feature["qualifier"] == "approximate"
