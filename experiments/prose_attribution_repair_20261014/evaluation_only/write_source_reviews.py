"""Persist explicit assistant review decisions; never edit model output or gold."""
import copy
import hashlib
import json
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RUN = EXP / "v2"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def entry(relationship=True, meaning=True, optional=True, reason="", equivalents=None):
    return {"relationship_supported": relationship, "measurement_meaning_preserved": meaning,
            "asserted_optional_fields_supported": optional, "reason": reason,
            "review_equivalences": equivalents or {}}


def main():
    finalized = read(RUN / "comparison_outputs_finalized.json")
    for name, digest in finalized["output_sha256"].items():
        assert hashlib.sha256((RUN / name).read_bytes()).hexdigest() == digest
    original = read(EXP / "frozen_baseline/semantic_review.json")["claim_reviews"]["a"]
    reviews = {dataset: {variant: {} for variant in ("baseline", "quotation_only", "complete")}
               for dataset in ("regression", "unseen")}
    for record in original:
        ident = record["case_id"]
        reviews["regression"]["baseline"].setdefault(ident, []).append(entry(
            relationship=record["evidence_relationship_complete"],
            meaning=not record["qualifier_error"] and record.get("forecast_error_condition_preserved") is not False,
            optional=not record["unsupported_context_fields"],
            reason="Reused frozen pre-repair source review: " + record["evidence_review_reason"]))
    reviews["regression"]["baseline"]["07_no_quantitative_outcomes"] = []
    # All nine accepted regression records were read against their full source
    # passages after finalization. Their named use predicates + vineyard/farm/
    # This-translated continuations support the quantities; retained year and
    # population fields belong to those deployments. Missing locations remain
    # missing, and are not supplied by this review.
    for case in read(RUN / "outputs/regression_complete.json")["cases"]:
        reviews["regression"]["complete"][case["document_id"]] = [entry(reason=
            "Named deployment and explicit vineyard/farm or This-translated antecedent support the selected amount, qualifier and outcome. Retained year/population belong to this deployment. Missing optional context remains null.")
            for claim in case["accepted_claims"]]
    reviews["unseen"]["baseline"] = {
        "u01_shared_paragraph": [entry(reason="Named AuroraDrip deployment explicitly connects Amber Vale/2022 to water reduction."),
                                  entry(reason="Named NoraLens use predicate explicitly connects Silver Plain/2023 to crop losses; repeated citation 9 is not used as study identity.")],
        "u02_page_continuation": [entry(False, True, False, "The same-trial quote omits the named CedarSpray/Northern Vale/2021 antecedent. Full input supports the claim, but its evidence does not carry the relationship."),
                                    entry(reason="Named later survey of CedarSpray users worldwide supports the bound; no local year/location is propagated.")],
        "u03_respectively": [entry(reason="Explicit respectively orders FallowFlow/MeadowMind against 13/21 in the selected comparison."),
                              entry(reason="Explicit respectively orders FallowFlow/MeadowMind against 13/21 in the selected comparison.")],
        "u04_compound_forecast": [entry(True, False, True, "Exact qualifier drops as-early-as bound; named SkyYield/system path is present. Location is missing.", {"subject": "SkyYield"}),
                                    entry(True, False, True, "Exact qualifier drops within threshold. Relative-error unit is reviewed as percent with the error outcome, without changing output.",
                                          {"subject": "SkyYield", "outcome": "prediction_error_threshold", "unit": "percent"}),
                                    entry(True, True, True, "Proportion label and quoted within-4%-for-79%-of-plots relationship preserve the compound meaning; no structured condition/population fields were emitted. Location is missing.",
                                          {"subject": "SkyYield", "outcome": "fields_within_prediction_error_threshold"})],
        "u05_ranges_and_negation": [entry(False, False, False, "Invented midpoint 12 is not the source range 10-14. The system quote omits named trial/year/location antecedent.", {"subject": "ReedScan"}),
                                    entry(False, True, False, "Up-to-9 input-cost quantity is correct, but its quote omits the named trial/year/location antecedent.", {"subject": "ReedScan"}),
                                    entry(False, True, False, "Approximate 3% crop-loss increase is correct, but its quote omits the named trial/year/location antecedent.", {"subject": "ReedScan"}),
                                    entry(False, False, False, "The output asserts a reduction quantity without representing not-observed/negation; the negative quote is retained. Named trial/year/location antecedent is absent.", {"subject": "ReedScan"})],
        "u06_projection_scope": [], "u07_ambiguous_order": [],
        "u08_cited_quotations": [entry(reason="Quoted LakeSight statement explicitly names owner/outcome/16%; citation is reported evidence, not proof of an original experiment."),
                                 entry(reason="Explicit another cited deployment names OrchardFlow/yield/6%; repeated citation 2 does not join the deployments.")],
    }
    reviews["unseen"]["complete"] = {
        "u01_shared_paragraph": [entry(reason="AuroraDrip use/outcome predicate and 2022 occur in one explicit deployment; Amber Vale remains missing, and NoraLens was not accepted.")],
        "u02_page_continuation": [],
        "u03_respectively": [entry(reason="Ordered respectively statement licenses FallowFlow -> 13, not proximity."),
                              entry(reason="Ordered respectively statement licenses MeadowMind -> 21, not proximity.")],
        "u04_compound_forecast": [],
        "u05_ranges_and_negation": [entry(reason="Original-author trial names ReedScan, followed by The system; both range bounds 10 and 14 are preserved. Original-result role is missing (null), not filled by review."),
                                    entry(reason="Explicit single original trial remains the reporting scope for up-to-9 input costs. Year/location/role remain missing, not filled by review.")],
        "u06_projection_scope": [entry(reason="Named cited field deployment connects CropSense to measured crop market value +7%; distinct projection/market-size/download quantities were not accepted.",
                                       equivalents={"outcome": "market_value_increase"})],
        "u07_ambiguous_order": [],
        "u08_cited_quotations": [entry(reason="Review explicitly quotes prior LakeSight result. Selected source preserves the quoted reporting role; it is not the review author's trial."),
                                 entry(reason="Another cited deployment directly connects OrchardFlow to yield +6%; role and separate deployment are retained.")],
    }
    for dataset in reviews:
        reviews[dataset]["quotation_only"] = copy.deepcopy(reviews[dataset]["baseline"])
        for variant in reviews[dataset]:
            for case in read(RUN / "outputs" / f"{dataset}_{variant}.json")["cases"]:
                ident = case.get("id", case.get("document_id"))
                claims = case.get("claims", case.get("accepted_claims"))
                assert len(claims) == len(reviews[dataset][variant][ident]), (dataset, variant, ident)
    reviews["review_metadata"] = {
        "assessor": "implementing assistant; no independent human review",
        "outputs_finalized_before_review": True, "outputs_or_references_changed": False,
        "legacy_extended_fields": "Legacy flat outputs lack typed role/population/direction/negation/conditions. Source meaning retained in labels and evidence is reviewed explicitly; missing typed fields are not fabricated.",
        "equivalences": "Per-record descriptor/label/unit equivalences are evaluation-only, documented above. Numeric midpoints, ranges, qualifiers, context, direction and negation are never repaired."}
    (EXP / "evaluation_only/final_source_reviews.json").write_text(json.dumps(reviews, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
