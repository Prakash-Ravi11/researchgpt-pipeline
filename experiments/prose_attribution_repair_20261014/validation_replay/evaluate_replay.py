"""Evaluation-only frozen-reference comparison after replay output finalization."""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
RUN = HERE / "final"
ROOT = EXP.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def frozen(relative):
    return HERE / "before" / str((EXP / relative).relative_to(ROOT))


def main():
    finalized = read(RUN / "replay_outputs_finalized.json")
    for name, digest in finalized["outputs_sha256"].items():
        assert hashlib.sha256((RUN / name).read_bytes()).hexdigest() == digest
    spec = importlib.util.spec_from_file_location("frozen_semantic_evaluation", frozen("evaluation_only/compare_final.py"))
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    gold = {dataset: {case["id"]: case["claims"] for case in read(frozen("evaluation_only/" +
                       ("regression_gold.json" if dataset == "regression" else "unseen_gold.json")))["cases"]}
            for dataset in ("regression", "unseen")}
    inputs = {dataset: {case["id"]: case["text"] for case in read(frozen(f"fixtures/{dataset}_inputs.json"))["cases"]}
              for dataset in ("regression", "unseen")}
    original_outputs = {dataset: read(frozen(f"v2/outputs/{dataset}_complete.json")) for dataset in ("regression", "unseen")}
    prior = read(frozen("v2/comparative_metrics.json"))
    prior_review = {}
    for row in prior["claim_reviews"]:
        if row["variant"] == "complete":
            case = next(case for case in original_outputs[row["dataset"]]["cases"] if case["document_id"] == row["case_id"])
            claim = case["accepted_claims"][row["index"]]
            prior_review[row["dataset"], row["case_id"], claim["claim_id"]] = row["source_review"]
    # Explicit review of newly supported attempt IDs against saved source:
    # named app/use + crop-loss predicate; or named farm antecedent in selected
    # population source plus its scalar cost/runoff predicate. This is an
    # implementing-assistant review, not independent human adjudication.
    source_review = {
        ("02_plantix", "a0:c0"): "Selected s001 names Plantix app, 2019 and the 50% crop-loss reduction; qualifier/direction are exact/decrease.",
        ("02_plantix", "a1:c0"): "Selected s001 names Plantix app, 2019 and the 50% crop-loss reduction; qualifier/direction are exact/decrease.",
        ("04_reversed", "a0:c0"): "Selected s001 names Plantix app and the 50% crop-loss reduction in 2019. Reversal does not change that local statement.",
        ("04_reversed", "a1:c0"): "Selected s001 names Plantix app and the 50% crop-loss reduction in 2019. Reversal does not change that local statement.",
        ("05_three_cases", "a1:c1"): "Selected s008 names Xarvio and the corn farm; selected s010 explicitly links the farm to cost savings of $45 per acre. Unit denominator and savings direction are preserved; context stays null.",
        ("05_three_cases", "a1:c2"): "Selected s008 names Xarvio and the corn farm; selected s010 explicitly links the farm to nutrient runoff reduction of 15%. This later record has year null; it is not selected over the richer earlier source record.",
        ("u01_shared_paragraph", "a0:c0"): "AuroraDrip is explicitly implemented by the Amber Vale/2022 farm and connected to water-use reduction of 20%; source population is a farm.",
        ("u01_shared_paragraph", "a0:c1"): "Selected s002 explicitly names NoraLens app, Silver Plain/2023 farm and crop-loss reduction of 20%; repeated citation 9 does not join it to AuroraDrip.",
        ("u01_shared_paragraph", "a1:c1"): "Selected s002 explicitly names NoraLens app, Silver Plain/2023 farm and crop-loss reduction of 20%; repeated citation 9 does not join it to AuroraDrip.",
    }
    results, details = {}, []
    for cohort in ("final_proposals", "attempt_selection"):
        results[cohort] = {}
        for version in ("before", "after"):
            results[cohort][version] = {}
            for dataset in ("regression", "unseen"):
                output = read(RUN / "outputs" / f"{cohort}_{version}_{dataset}.json")
                totals, cases = collections.Counter(), []
                for case in output["cases"]:
                    ident = case["document_id"]
                    refs = [evaluator.semantic_view(ref) for ref in gold[dataset][ident]]
                    covered, supported, complete = set(), set(), set()
                    counts = collections.Counter(expected=len(refs), emitted=len(case["accepted_claims"]),
                                                 unpublished=len(case["unpublished_claims"]))
                    for record in case["accepted_claims"]:
                        identity = dataset, ident, record["claim_id"]
                        review = prior_review.get(identity)
                        if review is None:
                            assert (ident, record["claim_id"]) in source_review, identity
                            review = {"relationship_supported": True, "measurement_meaning_preserved": True,
                                      "asserted_optional_fields_supported": True,
                                      "reason": source_review[ident, record["claim_id"]]}
                        view = evaluator.semantic_view(record, review)
                        matched = [i for i, ref in enumerate(refs) if all(view[key] == ref[key] for key in ("subject", "outcome", "value", "unit"))]
                        index = matched[0] if len(matched) == 1 else None
                        ref = refs[index] if index is not None else None
                        exact = record["evidence_text"] in inputs[dataset][ident]
                        tuple_ok = bool(ref and all(view[key] == ref[key] for key in evaluator.KEYS) and review["measurement_meaning_preserved"])
                        source_supported = bool(ref and view["qualifier"] == ref["qualifier"] and exact
                                                and review["relationship_supported"] and review["measurement_meaning_preserved"])
                        errors = []
                        if ref is not None:
                            covered.add(index)
                            for field in ("location", "year"):
                                if ref[field] is not None:
                                    counts["applicable_" + field + "_fields"] += 1
                                    counts["applicable_context_fields"] += 1
                                    counts["supported_applicable_context_fields"] += int(view[field] == ref[field])
                                    counts["supported_" + field + "_fields"] += int(view[field] == ref[field])
                                    counts["model_null_applicable_context_fields"] += int(record["proposed"].get(field) is None)
                                if view[field] is not None and view[field] != ref[field]:
                                    errors.append(field)
                        if source_supported:
                            supported.add(index)
                        if tuple_ok:
                            complete.add(index)
                        counts.update(invalid_quotations=int(not exact), attribution_error_records=int(bool(errors)),
                                      attribution_error_fields=len(errors), unmatched_core_records=int(ref is None))
                        details.append({"cohort": cohort, "version": version, "dataset": dataset,
                                        "case_id": ident, "claim_id": record["claim_id"], "reference_index": index,
                                        "view": view, "supported_outcome": source_supported, "complete_tuple": tuple_ok,
                                        "quotation_verbatim": exact, "attribution_errors": errors, "source_review": review})
                    counts.update(source_quantities_covered=len(covered), missing_quantities=len(refs)-len(covered),
                                  supported_outcomes=len(supported), complete_tuples=len(complete))
                    states = collections.Counter(entry["state"] for entry in case["candidate_ledger"])
                    counts.update({"candidate_" + state: count for state, count in states.items()})
                    counts.update(candidate_entries=len(case["candidate_ledger"]),
                                  explicit_model_entries=sum(entry["explicit_model_accounting"] for entry in case["candidate_ledger"]))
                    totals.update(counts)
                    cases.append({"case_id": ident, "counts": dict(counts), "selection_decisions": case["selection_decisions"]})
                results[cohort][version][dataset] = {"counts": dict(totals), "cases": cases,
                    "supported_outcome_recall": totals["supported_outcomes"] / totals["expected"],
                    "complete_tuple_recall": totals["complete_tuples"] / totals["expected"],
                    "complete_tuple_precision": totals["complete_tuples"] / totals["emitted"],
                    "applicable_context_completeness": totals["supported_applicable_context_fields"] / totals["applicable_context_fields"]}
    # Confirm the old replay independently matches the already-scored repair.
    for dataset in ("regression", "unseen"):
        old = results["final_proposals"]["before"][dataset]["counts"]
        prior_counts = prior["datasets"][dataset]["complete"]["counts"]
        assert old["supported_outcomes"] == prior_counts["supported_outcome_recall_numerator"]
        assert old["complete_tuples"] == prior_counts["complete_tuple_recall_numerator"]
    report = {"status": "scored_saved_output_replay", "new_model_requests": 0,
              "assessment": "Implementing assistant source review and frozen-reference matching; independent human review pending.",
              "definitions": {"final_proposals": "Revalidate exactly the 59 old final proposals, preserving their identity.",
                              "attempt_selection": "Revalidate all 74 saved attempts, then apply old/current record-selection policy respectively; no rescheduling or new inference.",
                              "supported_outcomes": "Unique target occurrences with matching owner/outcome/quantity/unit/qualifier, exact selected quotation and reviewed measurement/ownership relationship.",
                              "complete_tuples": "Seven common fields plus reviewed range/condition/direction/negation meaning; not all merely accepted core claims.",
                              "applicable_context_denominator": "Location/year required by the matched frozen reference; non-applicable null fields excluded. Denominator changes when more outcomes are accepted."},
              "cohorts": results, "claim_reviews": details,
              "reference_sha256": {name: hashlib.sha256(frozen("evaluation_only/" + name).read_bytes()).hexdigest()
                                   for name in ("regression_gold.json", "unseen_gold.json")}}
    write(RUN / "replay_metrics.json", report)
    print(json.dumps({dataset: {version: results["attempt_selection"][version][dataset]["counts"] for version in ("before", "after")} for dataset in ("regression", "unseen")}, indent=2))


if __name__ == "__main__":
    main()
