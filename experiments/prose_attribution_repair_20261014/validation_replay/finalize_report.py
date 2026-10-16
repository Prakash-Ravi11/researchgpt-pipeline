"""Preservation checks and exact saved-replay report; no model invocation."""
import collections
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
RUN = HERE / "final"
CHANGED = {"src/evidence/prose_attribution/__init__.py", "src/evidence/prose_attribution/support.py",
           "src/evidence/prose_attribution/schema.py", "src/evidence/prose_attribution/extractor.py"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    before = read(HERE / "before_freeze_manifest.json")
    preserved, changed = [], []
    for name, digest in before["sha256"].items():
        assert sha(HERE / "before" / name) == digest, "Snapshot changed: " + name
        if name.replace("\\", "/") in CHANGED:
            changed.append(name)
        else:
            assert sha(ROOT / name) == digest, "Original frozen artifact changed: " + name
            preserved.append(name)
    for section in ("production_records_sha256", "existing_source_sha256"):
        for name, digest in before[section].items():
            assert sha(ROOT / name) == digest
    final = read(RUN / "replay_outputs_finalized.json")
    for name, digest in final["outputs_sha256"].items():
        assert sha(RUN / name) == digest
    for name, digest in final["current_code_sha256"].items():
        assert sha(ROOT / name) == digest
        target = RUN / "code_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert sha(target) == digest
        else:
            shutil.copy2(ROOT / name, target)
    cases = {}
    test_runs = []
    for path in (HERE / "verified/checks.xml", RUN / "selection_checks.xml"):
        tree = ET.parse(path)
        rows = tree.findall(".//testcase")
        test_runs.append({"path": str(path.relative_to(HERE)), "executed": len(rows)})
        for row in rows:
            assert row.find("failure") is None and row.find("error") is None
            cases[row.attrib["classname"], row.attrib["name"]] = row
    tests = {"status": "passed", "distinct_passed": len(cases), "test_runs": test_runs,
             "executed_including_repeats": sum(run["executed"] for run in test_runs),
             "modules": dict(collections.Counter(name for name, _ in cases)),
             "model_requests": 0, "note": "Synthetic transport HTTP test uses its own fake server, never Ollama."}
    write(RUN / "test_results.json", tests)
    integrity = {"status": "passed", "snapshot_files": len(before["sha256"]),
                 "unchanged_original_files": len(preserved), "intentionally_changed_live_validation_files": changed,
                 "production_files_unchanged": len(before["production_records_sha256"]),
                 "existing_source_files_unchanged": len(before["existing_source_sha256"]),
                 "frozen_comparison_artifacts_preserved": True, "tables_source_unchanged": True,
                 "source_and_quotation_modules_unchanged": True,
                 "raw_proposals_unchanged": True, "replay_output_hashes_match": True,
                 "new_model_requests": 0, "inference_followup_started": False}
    write(RUN / "integrity_verification.json", integrity)
    metrics = read(RUN / "replay_metrics.json")
    audit = read(HERE / "diagnostic_audit.json")
    classification = read(HERE / "classification_before.json")
    diffs = read(RUN / "claim_level_diff.json")
    fixed = [row for row in diffs if row["cohort"] == "final_proposals"]
    attempts = [row for row in diffs if row["cohort"] == "all_attempts"]
    paired_context = collections.Counter()
    for dataset in ("regression", "unseen"):
        old = read(RUN / "outputs" / f"attempt_selection_before_{dataset}.json")
        new = read(RUN / "outputs" / f"attempt_selection_after_{dataset}.json")
        new_cases = {case["document_id"]: case for case in new["cases"]}
        for case in old["cases"]:
            old_rows = {tuple(row["proposed"]["candidate_ids"]): row for row in case["accepted_claims"]}
            new_rows = {tuple(row["proposed"]["candidate_ids"]): row for row in new_cases[case["document_id"]]["accepted_claims"]}
            for key, row in old_rows.items():
                assert key in new_rows, "Previously supported outcome lost"
                next_row = new_rows[key]
                assert row["evidence_text"] == next_row["evidence_text"], "Previous quote changed"
                for field in ("location", "year"):
                    if row.get(field) is None and next_row.get(field) is not None:
                        paired_context["restored_" + field] += 1
                    if row.get(field) is not None and next_row.get(field) is None:
                        paired_context["removed_" + field] += 1
    recovery = {"newly_supported_final_proposals": sum(row["newly_accepted"] for row in fixed),
                "newly_supported_attempt_proposals_including_revisions": sum(row["newly_accepted"] for row in attempts),
                "previously_accepted_final_proposals_rejected": sum(row["old_published"] and not row["new_published"] for row in fixed),
                "paired_optional_field_recovery": dict(paired_context),
                "final_necessary_rejections_or_unresolved_retained": sum(not row["old_published"] and not row["new_published"] for row in fixed)}
    write(RUN / "recovery_summary.json", recovery)
    lines = ["# Verified host correction and saved-output replay", "",
             "No core-supported proposal was rejected solely because optional context lacked support. The existing publication gate already handled that separation correctly, so it was left unchanged. The verified corrections address exact representation mismatches, misclassified references already selected by the model, a mixed area/location representation, and a later-retry context-loss defect. **No new model requests were made.**", "",
             "## Verified pre-change classification", "",
             "The audit froze 564 code/artifact files before validation edits and reproduced every one of the 74 saved assessed records byte-for-byte as JSON structures. Final proposals and intermediate attempts are not pooled as independent outcome recovery:", "",
             "| Population | Total | Supported | Rejected | Unresolved | Sole optional-context publication failures |",
             "|---|---:|---:|---:|---:|---:|"]
    for name in ("final", "all_attempts"):
        summary = audit["summaries"][name]
        lines.append(f'| {name} | {summary["records"]} | {summary["statuses"]["supported"]} | {summary["statuses"]["rejected"]} | {summary["statuses"]["unresolved"]} | {summary["sole_optional_publication_failures"]} |')
    lines += ["", "Candidate ledger entries are a third population: 101 entries, originally 24 associated, 45 outside scope, 30 unresolved and 2 ambiguous. The old v1 model-contract pilot is outside this finalized-v2 validation cohort.", "",
              "The artifacts have **no rejection-code property**. `diagnostic_audit.json` preserves each exact reason string, assessment-rule ID, responsible validator, raw proposal, candidate occurrence and source unit. The repeated diagnostic claim that location/year require the same block is **incorrect**: the old `assess_claim` checks linked context IDs, reference-bucket inclusion and literal support, not block equality. `discourse` separately restricts unlicensed cross-block anaphora with missing reading order. Valid cross-page continuation already worked.", "",
              "| Final classification before correction | Count |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in classification["classification_counts"].items()]
    lines += ["", "There were zero structurally invalid source references in the saved cohort. Scope exclusions/mixed selections and wrong quantities/qualifiers are necessary failures; a rejection alone was not used as evidence of an overly strict guard. [CLASSIFICATION_BEFORE.md](CLASSIFICATION_BEFORE.md) was written and reported before validation changes. No applicable AGENTS.md was found in the repository, relevant subdirectories or ancestors.", "",
              "## Exact demonstrated causes and corrections", "",
              "| Case / final proposal | Candidate / selected source | Old exact decisions | Correction |",
              "|---|---|---|---|"]
    defect_ids = {("02_plantix", "a1:c0"), ("04_reversed", "a1:c0"), ("u01_shared_paragraph", "a1:c1"), ("05_three_cases", "a1:c1")}
    for row in audit["populations"]["final"]:
        key = row["case_id"], row["claim_id"]
        if key not in defect_ids:
            continue
        core = [decision for decision in row["non_supported_decisions"] if decision["field"] in ("subject", "outcome", "value", "qualifier", "condition")]
        reasons = "<br>".join(decision["field"] + ": " + decision["reason"] for decision in core)
        correction = ("Exact source platform-type suffix identity plus loss/losses token identity."
                      if key[0] != "05_three_cases" else "Reclassify the exact named-subject witness from selected population s008; retain required farm path to measurement s010.")
        selected_refs = list(dict.fromkeys(ref for values in row["raw_proposal"]["references"].values() for ref in values))
        lines.append(f'| `{key[0]}/{key[1]}` | Candidates `{row["raw_proposal"]["candidate_ids"]}`; source `{selected_refs}` | {reasons} | {correction} |')
    lines += ["", "`canonical_topic('loss')` previously returned `lo`, while `canonical_topic('losses')` returned `loss`; this is a value-independent token defect. The named entity rule now accepts a source-literal platform name plus `app/system/platform` only when it matches the explicitly assessed owner. Exact subject evidence misfiled under another selected reference bucket can be reassigned, but the required ownership path must still exist. Missing names/bridges and contradictory owner proposals are not rescued.", "",
              "The raw proposals remain unchanged. New `validation_adjustments` record every source-reference reassignment, lexical/type normalization and availability diagnostic. Original source selections stay identical. Previously published quotations are unchanged; new accepted quotes are reconstructed from the same original selected units, with no extra unit added to prove a relationship.", "",
              "## Location/year diagnosis, separate from publication", "",
              "On the 17 old accepted records there are 24 applicable location/year fields: **14 model-null, 8 supported retained, 2 non-null host-null**. These are not 16 rejected claims. Model-null fields are not backfilled from source guesses or reference answers.", "",
              "- `03_adjacent/a2:c0`, year: raw 2021 is present in selected subject s001, linked explicitly to the vineyard measurement in s003. The context bucket contains only s003. The old exact reason is `Context is not tied to this claim; local context cannot propagate to general users.` Its actual cause is bucket inclusion, not a same-block rule. Reassigning the already selected s001 witness restores year 2021; location stays null, so this does **not** recover a complete tuple.",
              "- `04_reversed/a0:c4`, location: raw `500 acres in Napa Valley, California` is correctly rejected as a literal mixed field. A typed normalization removes the area modifier only after verifying both the 500-acre source occurrence and explicit geographical phrase in the same selected, supported deployment path. It restores `Napa Valley, California` and recovers **one** complete tuple. No year/qualifier/quantity is manufactured.",
              "- Four unpublished Corteva proposals (`a0:c1`, `a1:c0`, `a1:c1`, `a2:c0`) misleadingly marked null location as having no deployment context. The availability regex missed both the intervening article and the `U.S.` abbreviation. The corrected diagnostic marks this field unresolved and retains null. This change alone recovers no outcome or tuple.", "",
              "A first unscored development replay and its failing test log are preserved. The focused tests caught incomplete abbreviation handling, an expected bridge-list error in a new test, and an unrelated hyphenated-water-use predicate limitation in another new test. The latter has no saved proposal demonstrating recovery here; it was not broadly normalized. The context test was isolated with the existing space-form predicate. No scoring reference or original model output was modified.", "",
              "## Later-attempt context retention", "",
              "Replaying all attempts exposed a distinct selection defect: newly supported `05_three_cases/a1:c2` for n017 would replace supported `a0:c7` and drop its verified year 2020. `selection_addendum_before.json` records both raw records and the source evidence before the selection correction. The new rule retains the earlier **whole** record only for the same supported core and scope when the incoming supported optional-field set is a strict subset. It merges no fields or evidence and uses no confidence score. It also prevents two demonstrated population-only losses on u01. Incomparable records retain the existing latest-record policy.", "",
              "## Measured before/after replay", "",
              "Primary metrics below use all 74 saved attempts with old/current selection policies. The separate fixed 59-final-proposal replay has the same outcome and complete-tuple recovery; all eight newly supported attempt records are not counted as eight unique recovered outcomes.", "",
              "| Metric | Regression before → after (30 targets) | Unseen before → after (17 targets) |", "|---|---:|---:|"]
    summaries = metrics["cohorts"]["attempt_selection"]
    for label, key in (("Published supported outcomes", "supported_outcomes"), ("Complete tuples", "complete_tuples"),
                       ("Attribution-error records", "attribution_error_records"), ("Invalid quotations", "invalid_quotations"),
                       ("Missing quantities", "missing_quantities"), ("Unpublished final proposals", "unpublished"),
                       ("Unresolved candidates", "candidate_unresolved"), ("Ambiguous candidates", "candidate_ambiguous")):
        values = [f'{summaries["before"][dataset]["counts"].get(key,0)} → {summaries["after"][dataset]["counts"].get(key,0)}' for dataset in ("regression", "unseen")]
        lines.append("| " + label + " | " + " | ".join(values) + " |")
    lines += ["", "Supported-outcome recall: **30.0% → 40.0%** regression; **47.1% → 52.9%** unseen. Complete-tuple recall: **0% → 3.3%** regression; **29.4% → 29.4%** unseen. This is **four recovered supported outcome occurrences, but only one recovered complete tuple**. The two Plantix occurrences reuse the same underlying source fact; they are not independent accuracy samples. Complete-tuple precision is 1/12 regression and 5/9 unseen after correction; adding valid partial claims does not imply complete-tuple precision improves.", "",
              "Four fixed final proposals become supported; the other **38 old unpublished proposals remain unpublished**. All 17 old accepted outcome occurrences remain supported. No optional context rescues unresolved core ownership. Fixed-record quotations are exactly unchanged, and final selected quotes preserve the old evidence text for every previously supported occurrence. Selection changes and all necessary rejection reasons are available in the claim-level artifacts.", "",
              "### Applicable optional-field denominators", "",
              "| Dataset | Supported location fields | Supported year fields | Supported applicable context fields |", "|---|---:|---:|---:|"]
    for dataset in ("regression", "unseen"):
        a, b = [summaries[version][dataset]["counts"] for version in ("before", "after")]
        lines.append(f'| {dataset} | {a["supported_location_fields"]}/{a["applicable_location_fields"]} → {b["supported_location_fields"]}/{b["applicable_location_fields"]} | {a["supported_year_fields"]}/{a["applicable_year_fields"]} → {b["supported_year_fields"]}/{b["applicable_year_fields"]} | {a["supported_applicable_context_fields"]}/{a["applicable_context_fields"]} → {b["supported_applicable_context_fields"]}/{b["applicable_context_fields"]} |')
    lines += ["", "On the fixed old accepted-outcome set, applicability stays **24 fields** and support rises **8/24 → 10/24** (one restored year and one restored location; zero field removals). On the expanded accepted set, support is **13/32**, including the three year fields on recovered crop-loss outcomes. The denominator change is disclosed rather than presented as the same-population rate. Native accounting remains 101/101; explicit model accounting remains 97/101. Candidate states become 32 associated, 41 outside scope, 26 unresolved and 2 ambiguous. This accounting is not extraction recall.", "",
              "## Tests and preservation", "",
              f'**{tests["distinct_passed"]} distinct tests passed**: 14 new source-repair contracts, 4 record-selection contracts, and the 136 relevant existing/source/table checks. The 150-check suite passed, then 24 focused selection/integration checks passed (20 repeats). Tests cover null optional fields, explicit cross-block continuation, unsupported inheritance, general-user scope, wrong numbers, qualifiers/conditions, repeated entity/citation ambiguity, exact quotation selection and unchanged tables. The transport test uses a fake local server; no real model is called. Test passing is separate from measured extraction recovery.', "",
              f'{len(before["sha256"])} pre-edit snapshots are intact. Original comparison outputs, raw requests/responses, reference fixtures, reports and table/source/quotation modules are preserved; {len(before["production_records_sha256"])} production JSON files and {len(before["existing_source_sha256"])} existing pipeline source files match their prior hashes. The feature flag/defaults, parser, model, prompts and request budgets are unchanged. Support validation is versioned `prose-support-v3`; record selection is versioned `supported-context-retention-v1`; both are included in the experimental cache fingerprint. The corrected core remains opt-in and has not been promoted.', "",
              "Live files changed: `support.py`, `__init__.py`, `schema.py`, `extractor.py`; added `support_refs.py`, `selection.py`, `test_prose_attribution_replay_repairs.py`, `test_prose_attribution_selection.py`. New audit/replay/report tooling is isolated in this `validation_replay/` directory. There are no production/table edits.", "",
              "## Remaining failures and smallest follow-up", "",
              "The correction improves saved-proposal replay but does not show a new model run will produce the same gain or repair model omissions. There are still 18 missing regression outcomes and 8 missing unseen outcomes, 26 unresolved and 2 ambiguous numeric candidates. Required qualifiers, directions, negation and forecast conditions remain missing/wrong in nine final proposals; 17 proposals contain excluded or mixed-scope selections; eight have wrong quantities/units/measurement references; two lack selected ownership bridges; two are genuinely ambiguous. The interrupted u02 request has no assessed proposal to recover, and its three missing outcomes remain missing. All fourteen previously model-null applicable context fields stay null. This replay cannot measure future inference latency, retry count or corpus generalization.", "",
              "The smallest useful follow-up is **two source passages**, 02_plantix and 04_reversed, under the unchanged local model/prompt/schema/settings and corrected host versions. They cover app/loss representation, local-versus-general context and typed location normalization. Use one initial pass and the existing bounded retry policy: at most three requests and 240 seconds per document, at most one retry per unit, **at most six model requests total**. Measure source-supported outcomes and complete tuples separately. This is a proposed experiment only; it was not launched. No full comparison, model change, parser replacement or production promotion is authorized by this report.", "",
              "The semantic review is by the implementing assistant, and the unseen set is assistant-authored. Frozen references are used only by evaluation, never by source validation or field filling. No reference corrections were made. The general claim that all host rejections were overly strict is not supported; the demonstrated defects above are the bounded exceptions.", "",
              "## Evidence artifacts", "",
              "- [Pre-change classification](CLASSIFICATION_BEFORE.md), `diagnostic_audit.json`, `classification_before.json`, `selection_addendum_before.json`.",
              "- [Replay metrics](final/replay_metrics.json), [claim-level diff](final/claim_level_diff.json), `final/all_attempt_assessments.json` and `final/outputs/`.",
              "- [Integrity checks](final/integrity_verification.json), [test results](final/test_results.json), `before/` and `final/code_snapshot/`.",
              "- `verified/` preserves the uncorrected selection replay; root replay artifacts and `first_replay_code/` preserve the first unscored development pass.",
              "- [Command record](COMMANDS.md).", ""]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"tests": tests["distinct_passed"], "recovery": recovery, "integrity": integrity["status"]}, indent=2))


if __name__ == "__main__":
    main()
