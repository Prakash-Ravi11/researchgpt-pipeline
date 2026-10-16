"""Source-only contracts for verified representation/reference corrections."""
from copy import deepcopy

import pytest

from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.inventory import inventory
from src.evidence.prose_attribution.support import assess_claim, discourse


def setup(text, blocks=None):
    source = SourceDocument.from_text("doc", text, blocks=blocks, metadata={"source_kind": "narrative_overview"})
    candidates = inventory(source)
    return source, candidates, discourse(source, candidates)


def propose(candidate, subject, outcome, refs, **fields):
    value = {"candidate_ids": [candidate["id"]], "subject": subject, "outcome": outcome,
             "location": None, "year": None, "population": None, "claim_role": "cited_result",
             "measurement": {"kind": "scalar", "value": candidate["value"], "lower": None, "upper": None,
                             "unit": candidate["unit"], "qualifier": "exact", "direction": "decrease",
                             "negated": False, "conditions": []},
             "references": {name: list(refs) for name in ("subject", "measurement", "ownership_bridge", "context", "population", "condition", "role")}}
    value.update(fields)
    return value


@pytest.mark.parametrize("platform", ["DeltaDrip", "NoraEcho"])
def test_exact_source_platform_type_and_loss_plural_identity(platform):
    source, candidates, frames = setup(f"Farmers using the {platform} app reported a 23% reduction in crop losses.")
    p = propose(candidates[0], platform + " app", "crop_loss_reduction", ["s001"])
    before = deepcopy(p)
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["subject"] == platform
    assert result["outcome"] == "crop_loss_reduction" and p == before
    assert {item["assessment_rule"] for item in result["validation_adjustments"]} >= {
        "source_literal_platform_type_suffix", "loss_losses_topic_identity"}


def test_supported_core_retains_nulls_for_missing_or_unsupported_optional_fields():
    source, candidates, frames = setup("In 2026, a farm in River Vale used DeltaDrip's irrigation system. The farm reduced water use by 17%.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip", "water_use_reduction", ["s001", "s002"])
    missing = assess_claim(source, candidates, frames, p, "missing")
    assert missing["published"] and missing["location"] is None and missing["year"] is None
    p.update(location="Other Valley", year=1999, population="different farmers")
    unsupported = assess_claim(source, candidates, frames, p, "unsupported")
    assert unsupported["published"]
    assert all(unsupported[field] is None for field in ("location", "year", "population"))
    assert unsupported["field_support"]["year"]["status"] == "rejected"


def test_subject_witness_can_be_reclassified_without_adding_source_or_quote():
    source, candidates, frames = setup("In 2026, a farm used DeltaDrip's irrigation system. The farm reported cost savings of $13 per acre.")
    candidate = next(c for c in candidates if c["value"] == 13)
    p = propose(candidate, "DeltaDrip's irrigation system", "cost_savings_per_acre", ["s002"])
    p["references"]["population"] = ["s001"]
    p["measurement"]["direction"] = "savings"
    before = deepcopy(p)
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["field_support"]["subject"]["source_references"] == ["s001", "s002"]
    assert result["quotation"] == source.reconstruct(["s002", "s001"])
    assert p == before and result["year"] is None
    p["references"]["population"] = []
    assert not assess_claim(source, candidates, frames, p, "no_name")["published"]


def test_cross_block_context_reclassification_requires_same_trial_path():
    blocks = [{"id": "p1", "text": "In 2026, a farm in River Vale used DeltaDrip's irrigation system.", "page": 1, "reading_order": 0},
              {"id": "p2", "text": "The same trial reduced water use by 17%.", "page": 2, "reading_order": 1}]
    source, candidates, frames = setup("\n\n".join(b["text"] for b in blocks), blocks)
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip", "water_use_reduction", ["s002"], year=2026, location="River Vale")
    p["references"]["subject"] = ["s001"]
    before = deepcopy(p)
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["year"] == 2026 and result["location"] == "River Vale"
    assert result["field_support"]["year"]["source_references"] == ["s001"]
    assert {region["page"] for region in result["source_regions"]} == {1, 2}
    assert p == before and result["quotation"] == source.reconstruct(["s001", "s002"])
    p["references"]["subject"] = ["s002"]
    result = assess_claim(source, candidates, frames, p, "missing_path")
    assert not result["published"] and result["year"] is None and result["location"] is None


def test_shared_platform_name_does_not_inherit_either_prior_deployment_context():
    source, candidates, frames = setup("In 2024, a farm in North Vale used the DeltaDrip app. In 2025, a farm in South Vale used the DeltaDrip app. DeltaDrip reduced water use by 17%.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip", "water_use_reduction", ["s001", "s002", "s003"], year=2024, location="North Vale")
    p["references"]["context"] = ["s001", "s002"]
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["location"] is None and result["year"] is None


def test_local_then_general_users_does_not_reclassify_local_context():
    source, candidates, frames = setup("In 2026, a farm in River Vale used the DeltaDrip app. A later survey of DeltaDrip users worldwide reported water use reductions of up to 17%.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip", "water_use_reduction", ["s001", "s002"], location="River Vale", year=2026)
    p["measurement"]["qualifier"] = "up_to"
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["location"] is None and result["year"] is None


@pytest.mark.parametrize("area,expected", [(500, "River Vale"), (501, None)])
def test_area_location_modifier_requires_both_source_area_and_geography(area, expected):
    source, candidates, frames = setup("In 2026, a farm in River Vale implemented DeltaDrip's irrigation system across 500 acres. The farm reduced water use by 17%.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip", "water_use_reduction", ["s001", "s002"], location=f"{area} acres in River Vale")
    before = deepcopy(p)
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["location"] == expected and p == before
    assert result["quotation"] == source.reconstruct(["s001", "s002"])


def test_wrong_number_and_missing_qualifier_still_prevent_publication():
    source, candidates, frames = setup("DeltaDrip app reduced crop losses by an estimated 23%.")
    p = propose(candidates[0], "DeltaDrip app", "crop_loss_reduction", ["s001"])
    assert not assess_claim(source, candidates, frames, p, "lost_qualifier")["published"]
    p["measurement"]["qualifier"] = "estimated"
    p["measurement"]["value"] = 17
    assert not assess_claim(source, candidates, frames, p, "wrong_number")["published"]


def test_compound_population_threshold_remains_mandatory():
    source, candidates, frames = setup("DeltaYield's forecast system made predictions. The predictions were within a 4% error for 79% of the plots.")
    threshold, proportion = candidates
    p = propose(proportion, "DeltaYield", "fields_within_prediction_error_threshold", ["s001", "s002"], population="plots")
    p["measurement"]["direction"] = "proportion"
    assert not assess_claim(source, candidates, frames, p, "missing_condition")["published"]
    p["measurement"]["conditions"] = [{"kind": "error_threshold", "candidate_id": threshold["id"], "operator": "within", "population": "plots"}]
    result = assess_claim(source, candidates, frames, p, "condition")
    assert result["published"] and result["measurement"]["conditions"][0]["value"] == 4


def test_repeated_entity_and_citation_do_not_resolve_ambiguous_deployment():
    source, candidates, frames = setup("In 2024, a farm in North Vale used the DeltaDrip app [2]. In 2025, a farm in South Vale used the DeltaDrip app [2]. The app reduced water use by 17%, but the source does not identify which deployment produced it.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip app", "water_use_reduction", ["s001", "s002", "s003"], location="North Vale", year=2024)
    result = assess_claim(source, candidates, frames, p, "c")
    assert not result["published"] and result["location"] is None and result["year"] is None


def test_article_before_region_marks_model_null_as_unresolved_without_filling_it():
    source, candidates, frames = setup("In 2026, a farm in the U.S. Midwest used DeltaDrip's irrigation system. The farm reduced water use by 17%.")
    candidate = next(c for c in candidates if c["value"] == 17)
    p = propose(candidate, "DeltaDrip", "water_use_reduction", ["s001", "s002"])
    result = assess_claim(source, candidates, frames, p, "c")
    assert result["published"] and result["location"] is None
    assert result["field_support"]["location"]["status"] == "unresolved"


def test_invalid_source_identifier_does_not_become_optional_field_removal():
    source, candidates, frames = setup("DeltaDrip reduced water use by 17%.")
    p = propose(candidates[0], "DeltaDrip", "water_use_reduction", ["s001"])
    p["references"]["context"] = ["s999"]
    result = assess_claim(source, candidates, frames, p, "c")
    assert not result["published"] and result["structural_validation"]["status"] == "rejected"
