"""Score finalized outputs against frozen references plus separate source review.

This evaluator never calls extraction, support.py, a model, or a repair function.
Reviewer equivalences affect only evaluation views, never outputs/references.
"""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
RUN = EXP / "v2"
KEYS = ("subject", "location", "year", "outcome", "value", "unit", "qualifier")
OUTCOME_ALIASES = {
    "water_use_reduction": "water_usage_reduction",
    "water_savings": "water_saved",
    "energy_cost_reduction": "pumping_energy_cost_reduction",
    "energy_cost_reduction_for_pumping": "pumping_energy_cost_reduction",
    "pesticide_reduction": "pesticide_use_reduction",
    "cost_savings_per_acre": "cost_saved_per_acre",
    "forecast_accuracy": "fields_within_prediction_error_threshold",
    "forecast_error": "prediction_error_threshold",
}
SUBJECT_ALIASES = {
    "Corteva Agriscience AI-driven yield prediction system": "Corteva Agriscience"
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def flat(claim):
    if "measurement" not in claim:
        return {key: claim.get(key) for key in KEYS}
    measurement = claim.get("measurement") or {}
    value = (measurement.get("value") if measurement.get("kind") == "scalar"
             else (measurement.get("lower"), measurement.get("upper")))
    return {**{key: claim.get(key) for key in ("subject", "location", "year", "outcome")},
            "value": value, "unit": measurement.get("unit"), "qualifier": measurement.get("qualifier")}


def semantic_view(claim, review=None):
    view = flat(claim)
    view["outcome"] = OUTCOME_ALIASES.get(view["outcome"], view["outcome"])
    view["subject"] = SUBJECT_ALIASES.get(view["subject"], view["subject"])
    if view["unit"] == "USD_per_acre" or (view["outcome"] == "cost_saved_per_acre" and view["unit"] in ("$", "dollars")):
        view["unit"] = "USD/acre"
    if review:
        for field, value in review.get("review_equivalences", {}).items():
            assert field in ("subject", "outcome", "location", "unit")
            view[field] = value
    return view


def freeze_checks():
    finalized = read(RUN / "comparison_outputs_finalized.json")
    assert finalized["status"] == "all_outputs_finalized_before_evaluation"
    for name, digest in finalized["output_sha256"].items():
        assert sha(RUN / name) == digest, name
    frozen = read(EXP / "freeze_manifest.json")
    for name, digest in frozen["baseline_files_sha256"].items():
        assert sha(EXP / name) == digest, name
    unseen = read(EXP / "unseen_freeze_manifest.json")
    assert sha(EXP / "fixtures/unseen_inputs.json") == unseen["input_sha256"]
    assert sha(HERE / "unseen_gold.json") == unseen["reference_sha256"]
    # Store a second explicit provenance ledger regardless of manifest key names.
    return {"finalized": finalized, "unseen_manifest": unseen,
            "references_sha256": {str(p.relative_to(EXP)): sha(p) for p in
                                  (HERE / "regression_gold.json", HERE / "unseen_gold.json")},
            "evaluator_sha256": sha(Path(__file__)),
            "review_sha256": sha(HERE / "final_source_reviews.json")}


def timing(dataset, variant, cases):
    totals = collections.Counter()
    rows = []
    for case in cases:
        ident = case.get("id", case.get("document_id"))
        if variant == "complete":
            completions = [request.get("completion", {}) for request in case["requests"]]
            seconds, requests, retries = case["elapsed_s"], len(case["requests"]), len(case["retried_evidence_units"])
            timeouts = sum(bool(request.get("hard_timeout")) for request in case["requests"])
        else:
            baseline = case if variant == "baseline" else read(RUN / "outputs" / (dataset + "_baseline.json"))["cases"][len(rows)]
            completions = baseline.get("completions", [baseline.get("completion", {})])
            seconds = baseline["elapsed_s"] + (case.get("host_elapsed_s", 0) if variant == "quotation_only" else 0)
            requests, retries, timeouts = baseline["request_count"], 0, 0
        row = {"id": ident, "elapsed_s": seconds, "requests": requests, "context_retries": retries,
               "hard_timeouts": timeouts, "prompt_tokens": sum(item.get("prompt_eval_count") or 0 for item in completions),
               "output_tokens": sum(item.get("eval_count") or 0 for item in completions),
               "completions_with_token_counters": sum(item.get("eval_count") is not None for item in completions)}
        rows.append(row)
        totals.update({key: value for key, value in row.items() if key != "id"})
    return {"totals": dict(totals), "cases": rows,
            "quotation_only_new_requests": 0 if variant == "quotation_only" else None,
            "baseline_regression_historical": dataset == "regression" and variant != "complete"}


def main():
    provenance = freeze_checks()
    reviews = read(HERE / "final_source_reviews.json")
    spec = importlib.util.spec_from_file_location("frozen_fixture_evaluator", HERE / "evaluate.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    results = {}
    detail_rows = []
    for dataset in ("regression", "unseen"):
        inputs = read(EXP / "fixtures" / (dataset + "_inputs.json"))
        gold = read(HERE / ("regression_gold.json" if dataset == "regression" else "unseen_gold.json"))
        source = {case["id"]: case["text"] for case in inputs["cases"]}
        expected = {case["id"]: case["claims"] for case in gold["cases"]}
        results[dataset] = {}
        for variant in ("baseline", "quotation_only", "complete"):
            output = read(RUN / "outputs" / (dataset + "_" + variant + ".json"))
            counters, cases, views = collections.Counter(), [], {}
            strict_output = {"cases": []}
            for case in output["cases"]:
                ident = case.get("id", case.get("document_id"))
                claims = case["accepted_claims"] if variant == "complete" else case["claims"]
                references = [semantic_view(reference) for reference in expected[ident]]
                quantity_covered, tuple_covered, supported_covered, grounded_covered = set(), set(), set(), set()
                case_counts = collections.Counter()
                views[ident] = []
                for index, claim in enumerate(claims):
                    review = reviews[dataset][variant][ident][index]
                    view = semantic_view(claim, review)
                    views[ident].append(view)
                    matches = [i for i, ref in enumerate(references) if all(view[key] == ref[key] for key in ("subject", "outcome", "value", "unit"))]
                    ref_index = matches[0] if len(matches) == 1 else None
                    reference = references[ref_index] if ref_index is not None else None
                    if reference is not None:
                        quantity_covered.add(ref_index)
                    exact = bool(isinstance(claim.get("evidence_text"), str) and claim["evidence_text"] and claim["evidence_text"] in source[ident])
                    false_context, missing_context = [], []
                    if reference is not None:
                        for field in ("location", "year"):
                            if view[field] != reference[field]:
                                (missing_context if view[field] is None else false_context).append(field)
                    qualifier_ok = bool(reference is not None and view["qualifier"] == reference["qualifier"])
                    meaning_ok = bool(review["measurement_meaning_preserved"])
                    relation_ok = bool(review["relationship_supported"])
                    tuple_ok = bool(reference is not None and all(view[key] == reference[key] for key in KEYS) and meaning_ok)
                    supported = bool(reference is not None and qualifier_ok and meaning_ok and relation_ok and exact)
                    grounded = bool(tuple_ok and supported and review["asserted_optional_fields_supported"])
                    if tuple_ok:
                        tuple_covered.add(ref_index)
                    if supported:
                        supported_covered.add(ref_index)
                    if grounded:
                        grounded_covered.add(ref_index)
                    row = {"dataset": dataset, "variant": variant, "case_id": ident, "index": index,
                           "reviewed_semantic_view": view, "reference_index": ref_index,
                           "complete_tuple_correct": tuple_ok, "supported_outcome": supported,
                           "fully_grounded_tuple": grounded, "quotation_verbatim": exact,
                           "context_attribution_errors": false_context, "missing_context_fields": missing_context,
                           "source_review": review}
                    detail_rows.append(row)
                    case_counts.update(emitted=1, complete_tuple_correct=int(tuple_ok),
                                       fully_grounded_tuples=int(grounded), invalid_quotations=int(not exact),
                                       context_error_records=int(bool(false_context)), context_error_fields=len(false_context),
                                       missing_context_fields=len(missing_context), relationship_incomplete_records=int(not relation_ok),
                                       measurement_meaning_error_records=int(not meaning_ok), unmatched_core_records=int(reference is None))
                case_counts.update(expected=len(references), source_quantities_covered=len(quantity_covered),
                                   missing_source_quantities=len(references) - len(quantity_covered),
                                   complete_tuple_recall_numerator=len(tuple_covered),
                                   supported_outcome_recall_numerator=len(supported_covered),
                                   grounded_tuple_recall_numerator=len(grounded_covered))
                accounting = None
                if variant == "complete":
                    accounting = case["accounting"]
                    counters.update(inventory_candidates=accounting["total_candidates"], ledger_entries=accounting["ledger_entries"],
                                    explicit_model_entries=accounting["explicit_model_entries"],
                                    unresolved_or_ambiguous_candidates=accounting["unresolved_or_ambiguous"])
                    states = collections.Counter(entry["state"] for entry in case["candidate_ledger"])
                    counters.update({"candidate_state_" + key: value for key, value in states.items()})
                    counters.update(unpublished_proposals=len(case["unpublished_claims"]))
                counters.update(case_counts)
                cases.append({"id": ident, "counts": dict(case_counts), "accounting": accounting})
                strict_output["cases"].append({"id": ident, "claims": [{**flat(claim), "evidence_text": claim.get("evidence_text")} for claim in claims]})
            expected_count = counters["expected"]
            emitted = counters["emitted"]
            summary = {"counts": dict(counters), "cases": cases,
                       "complete_tuple_correctness": counters["complete_tuple_correct"] / emitted if emitted else None,
                       "complete_tuple_recall": counters["complete_tuple_recall_numerator"] / expected_count if expected_count else None,
                       "supported_outcome_recall": counters["supported_outcome_recall_numerator"] / expected_count if expected_count else None,
                       "fully_grounded_tuple_recall": counters["grounded_tuple_recall_numerator"] / expected_count if expected_count else None,
                       "candidate_accounting": {"native_ledger_completeness": counters["ledger_entries"] / counters["inventory_candidates"] if counters["inventory_candidates"] else (1.0 if variant == "complete" else None),
                                                "explicit_model_completeness": counters["explicit_model_entries"] / counters["inventory_candidates"] if counters["inventory_candidates"] else (1.0 if variant == "complete" else None),
                                                "legacy_note": None if variant == "complete" else "No native ledger; post-hoc missing source quantities are reported separately."},
                       "timing": timing(dataset, variant, output["cases"])}
            if dataset == "regression":
                summary["strict_frozen_fixture"] = fixture.evaluate(inputs, gold, strict_output)
                def counter(ident, keys):
                    return collections.Counter(tuple(view[key] for key in keys) for view in views[ident])
                summary["order_sensitivity"] = {}
                for name, keys in (("complete_tuple", KEYS), ("core", ("subject", "outcome", "value", "unit"))):
                    adjacent, reversed_ = counter("03_adjacent", keys), counter("04_reversed", keys)
                    summary["order_sensitivity"][name] = {"equal": adjacent == reversed_, "only_adjacent": list((adjacent-reversed_).elements()), "only_reversed": list((reversed_-adjacent).elements())}
            results[dataset][variant] = summary
    report = {"assessment": "Assistant source review against frozen references; not independent human review.",
              "definitions": {"complete_tuple": "Seven common fields match source meaning, with range bounds and source direction/negation/conditions preserved; quotation validity is separate.",
                              "supported_outcome_recall": "Unique reference outcomes with correct owner, amount/range, unit, qualifier, direction/negation/conditions, exact quote and supporting ownership path; optional location/year errors are reported separately.",
                              "fully_grounded_tuple": "Complete tuple plus exact quote, supported ownership path, and every asserted optional field supported.",
                              "native_candidate_accounting": "Every occurrence has a ledger state, including unresolved. Completeness is not extraction coverage.",
                              "quotation_only": "Same claim fields and same inference as baseline; only exact source mapping changes."},
              "review_equivalences": {"outcomes": OUTCOME_ALIASES, "subjects": SUBJECT_ALIASES},
              "provenance": provenance, "datasets": results, "claim_reviews": detail_rows}
    write(RUN / "comparative_metrics.json", report)
    print(json.dumps({dataset: {variant: {"counts": result["counts"], "tuple_recall": result["complete_tuple_recall"], "supported_recall": result["supported_outcome_recall"], "timing": result["timing"]["totals"]} for variant, result in variants.items()} for dataset, variants in results.items()}, indent=2))


if __name__ == "__main__":
    main()
