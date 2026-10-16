"""Create frozen synthetic evaluation data before repair implementation/evaluation.

This reference-authoring file is outside model input assembly and is never
imported by extraction. No independent human review is claimed.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def fact(subject, outcome, value, unit="percent", qualifier="exact", *, location=None,
         year=None, direction="decrease", role="cited_result", lower=None, upper=None,
         negated=False, population=None, conditions=None):
    return {"subject": subject, "location": location, "year": year, "outcome": outcome,
            "measurement": {"kind": "range" if lower is not None else "scalar", "value": value,
                            "lower": lower, "upper": upper, "unit": unit, "qualifier": qualifier,
                            "direction": direction, "negated": negated, "conditions": conditions or []},
            "population": population, "claim_role": role}


def main():
    inputs, gold = [], []
    def add(ident, blocks, facts, **evaluation_notes):
        source = "\n\n".join(block["text"] for block in blocks)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        inputs.append({"id": ident, "text": source, "sha256": digest, "blocks": blocks,
                       "provenance": "frozen synthetic material", "source_kind": "narrative_overview"})
        gold.append({"id": ident, "claims": facts, **evaluation_notes})
    add("u01_shared_paragraph", [{"id": "b1", "text":
        "In 2022, a farm in Amber Vale implemented AuroraDrip's irrigation system and reduced water use by 20% [9]. In 2023, a farm in Silver Plain using the NoraLens app reported a 20% reduction in crop losses [9].",
        "semantic_paragraph_boundary": "not_established", "reading_order": 0}], [
            fact("AuroraDrip", "water_use_reduction", 20, location="Amber Vale", year=2022),
            fact("NoraLens", "crop_loss_reduction", 20, location="Silver Plain", year=2023)])
    add("u02_page_continuation", [
        {"id": "b1", "text": "A review describes a 2021 deployment of CedarSpray's pesticide system on a farm in Northern Vale.",
         "page": 1, "column": "left", "reading_order": 0, "section": "Case study", "metadata_origin": "synthetic"},
        {"id": "b2", "text": "The same trial reduced pesticide use by an estimated 18% and lowered input costs by 12%. A later survey of CedarSpray users worldwide reported pesticide-use reductions of up to 22%.",
         "page": 2, "column": "left", "reading_order": 1, "section": "Case study continued", "metadata_origin": "synthetic"}], [
            fact("CedarSpray", "pesticide_use_reduction", 18, qualifier="estimated", location="Northern Vale", year=2021),
            fact("CedarSpray", "input_cost_reduction", 12, location="Northern Vale", year=2021),
            fact("CedarSpray", "pesticide_use_reduction", 22, qualifier="up_to", population="users worldwide")])
    add("u03_respectively", [{"id": "b1", "text":
        "A cited comparison tested FallowFlow and MeadowMind for irrigation. FallowFlow and MeadowMind reduced water use by 13% and 21%, respectively [3].",
        "reading_order": 0}], [fact("FallowFlow", "water_use_reduction", 13), fact("MeadowMind", "water_use_reduction", 21)])
    add("u04_compound_forecast", [{"id": "b1", "text":
        "In 2024, a farm in Orbit Prairie used SkyYield's forecast system. The system provided yield forecasts as early as 45 days before harvest. Its predictions were within a 4% relative error for 79% of the plots [4].",
        "reading_order": 0}], [
            fact("SkyYield", "forecast_lead_time", 45, unit="days", qualifier="as_early_as", location="Orbit Prairie", year=2024, direction="lead_time"),
            fact("SkyYield", "prediction_error_threshold", 4, qualifier="within", location="Orbit Prairie", year=2024, direction="threshold"),
            fact("SkyYield", "fields_within_prediction_error_threshold", 79, location="Orbit Prairie", year=2024,
                 direction="proportion", population="plots", conditions=[{"kind": "error_threshold", "operator": "within", "value": 4, "unit": "percent"}])])
    add("u05_ranges_and_negation", [{"id": "b1", "text":
        "In our 2025 trial in Reed Valley, we used ReedScan's crop-management system. The system reduced pesticide use by between 10% and 14%. Input costs fell by up to 9%. Crop losses increased by approximately 3%, rather than decreasing. A 5% reduction in water use was not observed.",
        "reading_order": 0}], [
            fact("ReedScan", "pesticide_use_reduction", None, lower=10, upper=14, location="Reed Valley", year=2025, role="original_result"),
            fact("ReedScan", "input_cost_reduction", 9, qualifier="up_to", location="Reed Valley", year=2025, role="original_result"),
            fact("ReedScan", "crop_loss_increase", 3, qualifier="approximate", direction="increase", location="Reed Valley", year=2025, role="original_result"),
            fact("ReedScan", "water_use_reduction", 5, direction="not_observed", negated=True, location="Reed Valley", year=2025, role="original_result")])
    add("u06_projection_scope", [{"id": "b1", "text":
        "A cited field deployment of CropSense increased crop market value by 7% [6]. A market report projects that the agricultural AI market will grow by 18% next year and reach $2 billion. The platform has 900,000 downloads.",
        "reading_order": 0}], [fact("CropSense", "market_value_increase", 7, direction="increase")],
        excluded_roles=["projection", "background_statistic"], excluded_values=[18, 2000000000, 900000])
    add("u07_ambiguous_order", [
        {"id": "left", "text": "PinePilot and RainLens are both described as irrigation platforms.",
         "column": "left", "reading_order": None, "metadata_origin": "synthetic", "reading_order_status": "missing"},
        {"id": "right", "text": "Water use fell by 25% in one deployment and 17% in the other.",
         "column": "right", "reading_order": None, "metadata_origin": "synthetic", "reading_order_status": "missing"},
        {"id": "note", "text": "The extracted source does not identify which platform produced either figure, and reading order is uncertain.",
         "reading_order": None, "reading_order_status": "missing"}], [], expected_unresolved_values=[25, 17])
    add("u08_cited_quotations", [{"id": "b1", "text":
        "A review quotes a prior study: 'LakeSight reduced nutrient runoff by 16%.' [2] Another cited deployment of OrchardFlow increased yield by 6% [2]. The review did not conduct either trial.",
        "reading_order": 0}], [
            fact("LakeSight", "nutrient_runoff_reduction", 16), fact("OrchardFlow", "yield_increase", 6, direction="increase")])
    folder = HERE / "fixtures"
    folder.mkdir(exist_ok=True)
    input_path, gold_path = folder / "unseen_inputs.json", HERE / "evaluation_only/unseen_gold.json"
    if input_path.exists() or gold_path.exists():
        raise SystemExit("Frozen unseen inputs/reference already exist; do not replace.")
    input_path.write_text(json.dumps({"version": "synthetic-edge-v1", "cases": inputs}, indent=2), encoding="utf-8")
    gold_path.write_text(json.dumps({"version": "synthetic-edge-v1", "review_status": "assistant_constructed; no independent human review", "cases": gold}, indent=2), encoding="utf-8")
    manifest = {"status": "frozen_before_repair_evaluation", "case_count": len(inputs),
                "expected_target_claims": sum(len(case["claims"]) for case in gold),
                "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "reference_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
                "authoring_limitations": "Unseen to the original A/B experiment and model runs, not an independently authored blind test of the implementing agent."}
    (HERE / "unseen_freeze_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
