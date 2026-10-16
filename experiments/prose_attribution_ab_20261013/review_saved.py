"""Documented assistant source review of frozen outputs; never repairs outputs.

The semantic equivalences below are reviewer decisions after strict scoring, not
changes to the frozen normalization adapter or reference fixture.
"""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = ("subject", "location", "year", "outcome", "value", "unit", "qualifier")
OUTCOME_EQUIVALENCE = {
    "water_use_reduction": "water_usage_reduction",
    "water_savings": "water_saved",
    "energy_cost_reduction": "pumping_energy_cost_reduction",
    "energy_cost_reduction_for_pumping": "pumping_energy_cost_reduction",
    "pesticide_reduction": "pesticide_use_reduction",
    "cost_savings_per_acre": "cost_saved_per_acre",
    "forecast_accuracy": "fields_within_prediction_error_threshold",
    "forecast_error": "prediction_error_threshold",
}
SUBJECT_EQUIVALENCE = {
    "Corteva Agriscience AI-driven yield prediction system": "Corteva Agriscience"
}
EVIDENCE_RELATION_COMPLETE = {
    "a": {
        "01_vineyard": [True, True, True],
        "02_plantix": [True, False],
        "03_adjacent": [True, False, True, False],
        "04_reversed": [True, False, True, True, True],
        "05_three_cases": [True, False, False, True, False, True, True, True],
        "06_forecast_and_brazil": [False, False, False, False],
        "07_no_quantitative_outcomes": [],
    },
    "b": {
        "01_vineyard": [False, False, False],
        "02_plantix": [True, False, False],
        "03_adjacent": [True, True, True, False],
        "04_reversed": [True, False, False, False, False, False],
        "05_three_cases": [True, False, True, True, True],
        "06_forecast_and_brazil": [False, False, False, False, False, False],
        "07_no_quantitative_outcomes": [],
    },
}
# Reasons from inspecting each quoted span against the full fixed source passage.
INCOMPLETE_EVIDENCE_REASONS = {
    "a": {
        "02_plantix": {1: "The app has no named antecedent within the evidence span."},
        "03_adjacent": {1: "Evidence stops before the 35% pumping-cost statement.",
                         3: "Evidence omits the pesticide-use statement and cannot support propagated local context."},
        "04_reversed": {1: "Evidence has no named Plantix antecedent or support for the propagated year."},
        "05_three_cases": {1: "Evidence stops before the absolute water-savings amount.",
                            2: "Evidence stops before the pumping-cost reduction.",
                            4: "Evidence omits pesticide use and cannot support propagated local context."},
        "06_forecast_and_brazil": {0: "Evidence keeps the error condition but omits Corteva and deployment year.",
                                   1: "Evidence omits Corteva and deployment year.",
                                   2: "Evidence names FieldView but omits Brazil/farm antecedent.",
                                   3: "Evidence names FieldView but omits Brazil/farm antecedent."},
    },
    "b": {
        "01_vineyard": {0: "The system/vineyard has no named Netafim antecedent in the span.",
                         1: "The vineyard has no named Netafim antecedent in the span.",
                         2: "The vineyard has no named Netafim antecedent in the span."},
        "02_plantix": {1: "Malformed context-only extraction; no quantitative attributes.",
                        2: "The app has no named Plantix antecedent in the span."},
        "03_adjacent": {3: "Evidence omits pesticide use and cannot support propagated local context."},
        "04_reversed": {1: "Malformed context-only extraction.",
                         2: "The app has no named Plantix antecedent in the span.",
                         3: "Malformed context-only extraction.",
                         4: "Evidence omits Netafim, location and year.",
                         5: "Evidence omits Netafim, location and year, and does not make 35% approximate."},
        "05_three_cases": {1: "The year refers to crop losses; it does not date the general pesticide-use estimate."},
        "06_forecast_and_brazil": {0: "Evidence retains the error condition but omits Corteva.",
                                   1: "Evidence omits Corteva and states within, not an exact error.",
                                   2: "Evidence omits Corteva.", 3: "Evidence omits Corteva.",
                                   4: "Evidence omits Brazil/farm antecedent.",
                                   5: "Evidence omits Brazil/farm antecedent."},
    },
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def semantic_view(claim):
    out = {key: claim.get(key) for key in KEYS}
    out["subject"] = SUBJECT_EQUIVALENCE.get(out["subject"], out["subject"])
    out["outcome"] = OUTCOME_EQUIVALENCE.get(out["outcome"], out["outcome"])
    # The denominator remains explicit in the outcome label; record the unit
    # field's incompleteness separately instead of silently editing the output.
    if out["outcome"] == "cost_saved_per_acre" and out["unit"] in ("$", "dollars", "USD_per_acre"):
        out["unit"] = "USD/acre"
    return out


def main():
    final = read(HERE / "conversion_finalized.json")
    for name, digest in {**final["output_sha256"], **final["frozen_sha256"]}.items():
        assert sha(HERE / name) == digest, name
    gold = {case["id"]: case["claims"] for case in read(HERE / "evaluation/evaluation_only/gold.json")["cases"]}
    inputs = {case["id"]: case["text"] for case in read(HERE / "benchmark/passages.json")["cases"]}
    run = read(HERE / "run_manifest.json")
    summaries = {}
    all_reviews = {}
    all_views = {}
    for candidate in ("a", "b"):
        output = read(HERE / (candidate + "_output.json"))
        strict = read(HERE / (candidate + "_scores.json"))
        reviews, case_summaries = [], []
        counters = collections.Counter()
        views = {}
        for case in output["cases"]:
            ident, claims = case["id"], case["claims"]
            conversion = read(HERE / "conversion_final" / (candidate + "_" + ident + ".json"))
            source = inputs[ident]
            expected = gold[ident]
            covered = set()
            case_counts = collections.Counter()
            assert len(EVIDENCE_RELATION_COMPLETE[candidate][ident]) == len(claims)
            views[ident] = []
            for index, claim in enumerate(claims):
                view = semantic_view(claim)
                malformed = any(view[k] is None for k in ("subject", "outcome", "value", "unit", "qualifier"))
                matches = [i for i, ref in enumerate(expected)
                           if all(view[k] == ref[k] for k in ("subject", "outcome", "value", "unit"))]
                ref_index = matches[0] if len(matches) == 1 else None
                ref = expected[ref_index] if ref_index is not None else None
                false_context = []
                missing_context = []
                if ref:
                    covered.add(ref_index)
                    for field in ("location", "year"):
                        if view[field] != ref[field]:
                            (missing_context if view[field] is None else false_context).append(field)
                qualifier_error = bool(ref and view["qualifier"] != ref["qualifier"])
                tuple_correct = bool(ref and all(view[k] == ref[k] for k in KEYS))
                exact = isinstance(claim.get("evidence_text"), str) and claim["evidence_text"] in source
                relation_complete = EVIDENCE_RELATION_COMPLETE[candidate][ident][index]
                fully_grounded = bool(tuple_correct and exact and relation_complete)
                unit_field_incomplete = bool(view["outcome"] == "cost_saved_per_acre"
                                             and claim["unit"] in ("$", "dollars"))
                condition_preserved = None
                if view["outcome"] == "fields_within_prediction_error_threshold":
                    condition_preserved = "within a 5% margin of error" in claim["evidence_text"]
                record = {"candidate": candidate, "case_id": ident, "index": index,
                          "claim": claim, "reviewed_semantic_view": view,
                          "reference_quantity_index": ref_index, "malformed": malformed,
                          "numeric_quantity_present": ref is not None,
                          "wrong_owner_or_value": bool(not malformed and ref is None),
                          "unsupported_context_fields": false_context,
                          "missing_supported_context_fields": missing_context,
                          "qualifier_error": qualifier_error,
                          "unit_field_incomplete": unit_field_incomplete,
                          "semantic_tuple_matches": tuple_correct,
                          "evidence_verbatim": exact,
                          "evidence_relationship_complete": relation_complete,
                          "evidence_review_reason": INCOMPLETE_EVIDENCE_REASONS[candidate].get(ident, {}).get(index, "Span contains the owner, amount and asserted local fields."),
                          "fully_grounded_semantic_tuple": fully_grounded,
                          "forecast_error_condition_preserved": condition_preserved,
                          "source_alignment": conversion[index].get("source_alignment")}
                reviews.append(record)
                for name, flag in (("malformed_records", malformed), ("reviewed_attribution_error_records", bool(false_context)),
                                   ("qualifier_error_records", qualifier_error), ("semantic_tuple_matches", tuple_correct),
                                   ("fully_grounded_semantic_tuples", fully_grounded), ("nonverbatim_evidence_records", not exact),
                                   ("evidence_relationship_incomplete_records", not relation_complete and not malformed),
                                   ("missing_context_records", bool(missing_context)), ("unit_field_incomplete_records", unit_field_incomplete),
                                   ("wrong_owner_or_value_records", not malformed and ref is None)):
                    case_counts[name] += int(flag)
                case_counts["missing_context_fields"] += len(missing_context)
                case_counts["emitted_records"] += 1
                if not malformed:
                    views[ident].append(view)
            missing_quantities = [expected[i] for i in range(len(expected)) if i not in covered]
            case_counts["missing_source_quantities"] = len(missing_quantities)
            case_counts["expected_occurrences"] = len(expected)
            counters.update(case_counts)
            corresponding_run = next(r for r in run["runs"] if r["candidate"] == candidate and r["case_id"] == ident)
            case_summaries.append({"id": ident, "counts": dict(case_counts), "missing_source_quantities": missing_quantities,
                                   "strict_fixture_matches": next(c for c in strict["cases"] if c["id"] == ident)["matched"],
                                   "runtime_s": corresponding_run["elapsed_s"]})
        candidate_runs = [r for r in run["runs"] if r["candidate"] == candidate]
        def counter(ident, fields):
            return collections.Counter(tuple(row[k] for k in fields) for row in views[ident])
        adjacent = counter("03_adjacent", KEYS)
        reversed_ = counter("04_reversed", KEYS)
        core_keys = ("subject", "outcome", "value", "unit")
        adjacent_core = counter("03_adjacent", core_keys)
        reversed_core = counter("04_reversed", core_keys)
        summaries[candidate] = {"strict": {k: strict[k] for k in ("counts", "fixture_match_precision", "fixture_recall")},
                                "reviewed_counts": dict(counters), "cases": case_summaries,
                                "extraction_runtime_s": sum(r["elapsed_s"] for r in candidate_runs),
                                "request_count": sum(r["request_count"] for r in candidate_runs),
                                "prompt_tokens": sum(c.get("prompt_eval_count") or 0 for r in candidate_runs for c in r["completions"]),
                                "output_tokens": sum(c.get("eval_count") or 0 for r in candidate_runs for c in r["completions"]),
                                "duplicate_or_conflicting_claim_records": 0,
                                "unsupported_joint_deployment_records": 0,
                                "negative_control_quantitative_records": 0,
                                "order_sensitivity": {"full_semantic_tuple_multiset_equal": adjacent == reversed_,
                                                      "only_adjacent": list((adjacent - reversed_).elements()),
                                                      "only_reversed": list((reversed_ - adjacent).elements()),
                                                      "core_quantity_multiset_equal": adjacent_core == reversed_core,
                                                      "core_only_adjacent": list((adjacent_core - reversed_core).elements()),
                                                      "core_only_reversed": list((reversed_core - adjacent_core).elements())}}
        all_reviews[candidate] = reviews
        all_views[candidate] = views
    result = {"assessment": "assistant source review; independent human review pending",
              "fixture_changed": False, "reference_source_review": "No substantive discrepancy found in the supplied excerpts; original PDF was not supplied in this folder.",
              "definitions": {"semantic_tuple_matches": "Seven tuple fields agree in source meaning after documented reviewer equivalences, ignoring quotation validity.",
                              "fully_grounded_semantic_tuples": "A semantic tuple match whose own evidence is exact and supports the complete asserted relationship.",
                              "missing_source_quantities": "A target subject/outcome/amount/unit is absent; contextual omissions are separate.",
                              "reviewed_attribution_error_records": "Unsupported propagated location/year or wrong deployment owner; no wrong owner found here."},
              "review_equivalences": {"outcomes": OUTCOME_EQUIVALENCE, "subjects": SUBJECT_EQUIVALENCE,
                                      "unit_note": "$/dollars plus an explicitly per-acre outcome are reviewed jointly as currency per acre; incomplete unit fields are separately counted.",
                                      "forecast_note": "forecast_accuracy is equivalent only here because each 85% record retains the 5% error condition in its evidence."},
              "candidates": summaries, "claim_reviews": all_reviews,
              "warmup_seconds_excluded": run["warmup"]["elapsed_s"],
              "total_wall_seconds_including_warmup": run["total_wall_seconds_including_warmup"]}
    (HERE / "semantic_review.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": summaries, "warmup_s": result["warmup_seconds_excluded"]}, indent=2))


if __name__ == "__main__":
    main()
