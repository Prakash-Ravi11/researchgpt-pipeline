"""Frozen, value-independent normalization shared by A and B."""
import re

FIELDS = ("subject", "location", "year", "outcome", "value", "unit", "qualifier", "evidence_text")
QUALIFIERS = {"approximately": "approximate", "approx": "approximate",
              "estimate": "estimated", "up to": "up_to", "as early as": "as_early_as",
              "more than": "more_than", "less than": "less_than"}
UNITS = {"%": "percent", "percentage": "percent", "percentages": "percent",
         "percentage points": "percentage_points", "gallon": "gallons", "day": "days",
         "$ per acre": "USD_per_acre", "$/acre": "USD_per_acre",
         "usd/acre": "USD_per_acre", "dollars per acre": "USD_per_acre",
         "usd per acre": "USD_per_acre", "usd_per_acre": "USD_per_acre"}
OUTCOMES = {
    "water_usage_reduction": "water_use_reduction",
    "reduction_in_water_usage": "water_use_reduction",
    "reduction_in_water_use": "water_use_reduction",
    "water_saving": "water_savings",
    "energy_cost_reduction": "energy_cost_reduction",
    "reduction_in_energy_costs": "energy_cost_reduction",
    "pumping_energy_cost_reduction": "energy_cost_reduction",
    "crop_losses_reduction": "crop_loss_reduction",
    "reduction_in_crop_losses": "crop_loss_reduction",
    "pesticide_usage_reduction": "pesticide_use_reduction",
    "reduction_in_pesticide_use": "pesticide_use_reduction",
    "chemical_usage_reduction": "chemical_use_reduction",
    "reduction_in_chemical_use": "chemical_use_reduction",
    "cost_saving": "cost_savings",
    "reduction_in_nutrient_runoff": "nutrient_runoff_reduction",
    "yield_forecast_lead_time": "forecast_lead_time",
    "prediction_lead_time": "forecast_lead_time",
    "yield_prediction_lead_time": "forecast_lead_time",
    "forecast_margin_of_error": "forecast_error",
    "forecast_error_margin": "forecast_error",
    "yield_prediction_error": "forecast_error",
    "yield_forecast_error": "forecast_error",
    "harvest_cost_reduction": "harvesting_cost_reduction",
    "reduction_in_harvesting_costs": "harvesting_cost_reduction",
    "increase_in_market_value": "market_value_increase",
    "increase_in_yield": "yield_increase",
    "reduction_in_input_costs": "input_cost_reduction",
}
SUBJECTS = {"plantix app": "Plantix", "corteva": "Corteva Agriscience",
            "netafim's ai-powered drip irrigation system": "Netafim",
            "netafim ai-powered drip irrigation system": "Netafim",
            "xarvio's ai-driven variable rate application system": "Xarvio",
            "corteva agriscience's ai-driven yield prediction system": "Corteva Agriscience",
            "climate fieldview's ai-driven recommendations": "Climate FieldView"}


def normalize(claim):
    out = {field: claim.get(field) for field in FIELDS}
    changes = []
    def assign(field, value, rule):
        if out[field] != value:
            changes.append({"field": field, "before": out[field], "after": value, "rule": rule})
            out[field] = value
    for field in ("subject", "location", "outcome", "unit", "qualifier"):
        if isinstance(out[field], str):
            assign(field, re.sub(r"\s+", " ", out[field]).strip(), "trim_collapse_whitespace")
    if isinstance(out["year"], str) and re.fullmatch(r"\d{4}", out["year"]):
        assign("year", int(out["year"]), "numeric_year")
    if isinstance(out["value"], str):
        try:
            assign("value", float(out["value"].replace(",", "")), "numeric_string")
        except ValueError:
            pass
    if isinstance(out["subject"], str):
        assign("subject", SUBJECTS.get(out["subject"].lower(), out["subject"]), "subject_alias")
    if isinstance(out["outcome"], str):
        token = re.sub(r"[^a-z0-9]+", "_", out["outcome"].lower()).strip("_")
        assign("outcome", OUTCOMES.get(token, token), "outcome_alias_or_snake_case")
    if isinstance(out["qualifier"], str):
        token = out["qualifier"].lower()
        assign("qualifier", QUALIFIERS.get(token, token.replace(" ", "_")), "qualifier_alias")
    if isinstance(out["unit"], str):
        unit = out["unit"].lower()
        match = re.fullmatch(r"(thousand|million|billion)[ _]+(.+)", unit)
        if match and isinstance(out["value"], (int, float)):
            scale = {"thousand": 1e3, "million": 1e6, "billion": 1e9}[match.group(1)]
            assign("value", out["value"] * scale, "unit_prefix_scale")
            unit = match.group(2)
        assign("unit", UNITS.get(unit, unit.replace(" ", "_")), "unit_alias")
    return out, changes
