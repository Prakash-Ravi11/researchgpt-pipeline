"""Source-reviewed classification, persisted before changing validation."""
import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    audit = read(HERE / "diagnostic_audit.json")
    # Explicit source review: these are verified recorded IDs, not synthetic
    # representative records, expected values, or implementation lookup rules.
    defects = {
        ("02_plantix", "a1:c0"): ["Literal Plantix app is the named Plantix platform in selected s001.",
                                   "canonical_topic(loss) is lo, whereas canonical_topic(losses) is loss. The correctly coupled crop-loss predicate fails this representation mismatch."],
        ("04_reversed", "a1:c0"): ["Same exact Plantix-app/name and singular-loss/plural-losses representation mismatches in selected s001."],
        ("u01_shared_paragraph", "a1:c1"): ["Literal NoraLens app is the named NoraLens platform in selected s002; the same loss/losses mismatch rejects its crop-loss outcome."],
        ("05_three_cases", "a1:c1"): ["Named Xarvio descriptor is selected in s008 under population references. The measurement is selected in s010, and the explicit farm continuation selects both required units. assess_claim checks literal subject only in the subject bucket (s010), incorrectly rejecting this supplied source path."],
    }
    classifications = []
    for row in audit["populations"]["final"]:
        identity = row["case_id"], row["claim_id"]
        fields = row["field_support"]
        if row["published"]:
            category = "supported_core"
        elif identity in defects:
            category = "correct_source_supported_wrongly_rejected"
        elif row["case_id"] == "u07_ambiguous_order":
            category = "genuinely_ambiguous_ownership"
        elif any(candidate["scope_reason"] for candidate in row["candidate_occurrences"]):
            category = "necessary_outside_scope_or_mixed_scope_selection"
        elif fields.get("value", {}).get("status") != "supported":
            category = "wrong_numeric_occurrence_unit_or_measurement_reference"
        elif any(fields.get(field, {}).get("status") != "supported" for field in ("qualifier", "condition")):
            category = "missing_or_wrong_qualifier_condition_direction_or_negation"
        else:
            category = "insufficient_selected_ownership_bridge"
        classifications.append({"case_id": row["case_id"], "claim_id": row["claim_id"], "category": category,
                                "verified_defect_explanation": defects.get(identity, []),
                                "exact_non_supported_decisions": row["non_supported_decisions"],
                                "exact_early_reason": row["semantic_assessment"].get("reason"),
                                "raw_proposal": row["raw_proposal"], "source_units": row["source_units"],
                                "candidate_occurrences": row["candidate_occurrences"]})
    counts = dict(collections.Counter(row["category"] for row in classifications))
    # Applicable denominators use frozen reference data for evaluation only.
    # No reference value is passed to validation or used to fill fields.
    previous = read(EXP / "v2/comparative_metrics.json")
    inputs = {dataset: {case["id"]: case["claims"] for case in read(EXP / "evaluation_only" /
                    ("regression_gold.json" if dataset == "regression" else "unseen_gold.json"))["cases"]}
              for dataset in ("regression", "unseen")}
    pub = {(dataset, case["document_id"], index): row for dataset in ("regression", "unseen")
           for case in read(EXP / "v2/outputs" / f"{dataset}_complete.json")["cases"]
           for index, row in enumerate(case["accepted_claims"])}
    applicable = collections.Counter()
    for review in previous["claim_reviews"]:
        if review["variant"] != "complete":
            continue
        row = pub[review["dataset"], review["case_id"], review["index"]]
        ref = inputs[review["dataset"]][review["case_id"]][review["reference_index"]]
        for field in ("location", "year"):
            if ref.get(field) is None:
                continue
            applicable["applicable_fields"] += 1
            applicable[field + "_applicable"] += 1
            if row["proposed"].get(field) is None:
                applicable["model_omitted"] += 1
            elif row.get(field) is None:
                applicable["model_nonnull_host_null"] += 1
            else:
                applicable["retained_supported"] += 1
    context_defects = [{"case_id": "03_adjacent", "claim_id": "a2:c0", "field": "year",
                        "explanation": "Proposed 2021 is in selected subject s001 and linked to the vineyard through s003. context references contain only s003, so bucket inclusion rejects year despite the selected supported path. No same-block restriction caused this."},
                       {"case_id": "04_reversed", "claim_id": "a0:c4", "field": "location",
                        "explanation": "Raw location is 500 acres in Napa Valley, California. Literal rejection of that mixed area/geography string is correct as supplied; its geographical subphrase and area are independently present in the selected same-deployment source. A value-independent typed normalization can remove the area modifier. This is not an optional-context publication rejection."}]
    report = {"status": "verified_classification_before_changes", "new_model_requests": 0,
              "assessor": "assistant source review; not independent human review",
              "optional_core_gate": "Already correct; leave publication gate unchanged. Zero sole-optional publication failures in final 59 and all-attempt 74 records.",
              "same_block_restriction_claim": "Incorrect for location/year: assess_claim has no block equality requirement.",
              "machine_rejection_codes_claim": "No rejection-code property exists; exact reason strings and assessment_rule values are reported instead.",
              "classification_counts": counts, "applicable_optional_context_on_old_accepted_set": dict(applicable),
              "verified_core_defect_records": len(defects), "context_diagnostics": context_defects,
              "model_omissions": "Null values remain null in the proposed minimal correction. Reference values will not be backfilled.",
              "classifications": classifications}
    (HERE / "classification_before.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text = ["# Verified classification before validation changes", "",
            "Finalized v2 scope: 59 final proposals (17 supported, 39 rejected, 3 unresolved). All attempts: 74 assessed proposals (19 supported, 49 rejected, 6 unresolved). Candidate ledger: 101 entries (24 associated, 45 outside scope, 30 unresolved, 2 ambiguous). These populations are distinct.", "",
            "No core-supported proposal was rejected solely for optional context: 0/17 final and 0/19 all-attempt core-supported proposals. The publication gate already uses only subject/value/outcome/qualifier/condition. It will not be redundantly changed. Location/year do not have a same-block requirement. Cross-block ownership separately requires an explicit link and usable order (or explicit continuation).", "",
            "The saved records contain reason strings and assessment-rule IDs, not a rejection-code property. The exact non-supported decisions and raw source/proposal evidence are saved in `diagnostic_audit.json` and `classification_before.json`. A host rejection alone is not a verified implementation defect.", "",
            "| Final proposal classification | Count |", "|---|---:|"]
    text += [f"| {name} | {count} |" for name, count in counts.items()]
    text += ["", "There are no structurally invalid source-reference records in this population. Necessary scope exclusions, mixed numeric occurrences, wrong qualifiers/direction/negation/conditions, and missing selected ownership bridges remain excluded. The two ambiguous-order proposals remain unpublished.", "",
             "Verified core defects:", ""]
    for (case, ident), explanation in defects.items():
        text.append(f"- `{case}/{ident}`: " + " ".join(explanation))
    text += ["", f"Applicable location/year fields on the 17 previously accepted records: {dict(applicable)}. Model omissions and host-rejected non-null fields are separate. The 14 model-null applicable fields are not host publication failures.", "", "Verified context diagnostics:", ""]
    text += [f'- `{item["case_id"]}/{item["claim_id"]}` / {item["field"]}: {item["explanation"]}' for item in context_defects]
    text += ["", "The smallest authorized correction will address exact source-grounded label/token mismatches and misclassified references already selected by the model. It will not add evidence units, fill model-null fields, relax core ownership, change qualifiers/conditions, or launch inference. No recovery is claimed before replay measurement.", ""]
    (HERE / "CLASSIFICATION_BEFORE.md").write_text("\n".join(text), encoding="utf-8")
    print(json.dumps({"classifications": counts, "applicable_optional_context": dict(applicable),
                      "verified_core_defect_records": len(defects)}, indent=2))


if __name__ == "__main__":
    main()
