"""Replay identical saved proposals with frozen/current validation; no inference.

Records both a fixed final-proposal cohort and the original attempt-selection
policy. Their denominators and newly accepted records must not be conflated.
"""
import collections
import argparse
import copy
import hashlib
import importlib
import importlib.util
import json
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
sys.path.insert(0, str(ROOT))
from src.evidence.prose_attribution import source as current_source, inventory as current_inventory, support as current_support
from src.evidence.prose_attribution.selection import choose_record


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def frozen_path(relative):
    return HERE / "before" / str((EXP / relative).relative_to(ROOT))


def frozen_package():
    directory = HERE / "before/src/evidence/prose_attribution"
    name = "_frozen_prose_validation"
    spec = importlib.util.spec_from_file_location(name, directory / "__init__.py", submodule_search_locations=[str(directory)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return [importlib.import_module(name + "." + part) for part in ("source", "inventory", "support", "schema")]


def source_from_saved(module, saved):
    return module.SourceDocument.from_text(saved["document_id"], saved["original_text"],
                                            blocks=saved["blocks"], metadata=saved["metadata"])


def assess(module, schema, source, candidates, frames, saved, allowed):
    raw = copy.deepcopy(saved["proposed"])
    before = digest(raw)
    try:
        if any(ref not in allowed for values in (raw.get("references") or {}).values() for ref in values):
            raise ValueError("Reference was not supplied in this attempt's bounded source context")
        result = module.assess_claim(source, candidates, frames, raw, saved["claim_id"])
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        result = schema.claim_record(source.document_id, saved["claim_id"], raw)
        result.update(status="rejected", semantic_assessment={"status": "rejected", "reason": "Malformed proposed fields: " + str(error)})
    result["attempt"] = saved["attempt"]
    assert digest(raw) == before == digest(saved["proposed"]), "Raw proposal mutated"
    return result


def select_attempts(records, corrected=False):
    selected = {}
    decisions = []
    for record in records:
        identifiers = tuple(sorted(record["proposed"].get("candidate_ids") or []))
        if identifiers:
            current = selected.get(identifiers)
            if corrected:
                chosen, decision = choose_record(current, record)
                selected[identifiers] = chosen
                if decision:
                    decisions.append({"candidate_ids": list(identifiers), **decision})
            elif current is None or record["published"] or not current["published"]:
                selected[identifiers] = record
    return list(selected.values()), decisions


def ledger_for(original, records, candidates):
    accepted = [record for record in records if record["published"]]
    by_id = {candidate["id"]: candidate for candidate in candidates}
    ledger = copy.deepcopy(original)
    for entry in ledger:
        identifier = entry["candidate_id"]
        candidate = by_id[identifier]
        linked = [record["claim_id"] for record in accepted if identifier in record["proposed"]["candidate_ids"]
                  or any(condition.get("candidate_id") == identifier for condition in record["measurement"].get("conditions", []))]
        if candidate["kind"] == "context_year":
            linked += [record["claim_id"] for record in accepted if record.get("year") == candidate["value"]
                       and candidate["sentence_id"] in record["field_support"]["year"]["source_references"]]
        entry["claim_ids"] = linked
        if linked:
            entry.update(state="associated", reason="Linked to supported replay claim/condition.")
        elif candidate["scope_reason"]:
            entry.update(state="outside_scope", reason=candidate["scope_reason"])
        elif entry["state"] != "ambiguous":
            entry.update(state="unresolved", reason="No supported attributed claim in saved-output replay.")
    return ledger


def changed(old, new, dataset, ident, cohort):
    changes = []
    for field in ("status", "published", "subject", "outcome", "measurement", "location", "year", "population", "claim_role"):
        if old.get(field) != new.get(field):
            changes.append({"field": field, "before": old.get(field), "after": new.get(field)})
    decisions = []
    for field in set(old["field_support"]) | set(new["field_support"]):
        if old["field_support"].get(field) != new["field_support"].get(field):
            decisions.append({"field": field, "before": old["field_support"].get(field), "after": new["field_support"].get(field)})
    if old["published"] and new["published"]:
        assert old["evidence_text"] == new["evidence_text"]
        assert old["quotation"] == new["quotation"]
    refs = list(dict.fromkeys(ref for values in new["proposed"].get("references", {}).values() for ref in values))
    if new["published"]:
        assert {span["sentence_id"] for span in new["quotation"]["selected_spans"]} == set(refs)
    return {"dataset": dataset, "case_id": ident, "claim_id": old["claim_id"], "cohort": cohort,
            "old_status": old["status"], "new_status": new["status"],
            "newly_accepted": not old["published"] and new["published"],
            "old_published": old["published"], "new_published": new["published"],
            "value_changes": changes, "field_decision_changes": decisions,
            "validation_adjustments": new.get("validation_adjustments", []),
            "raw_proposal_unchanged": digest(old["proposed"]) == digest(new["proposed"]),
            "source_reference_selection_unchanged": old["proposed"]["references"] == new["proposed"]["references"],
            "previously_accepted_quote_unchanged": old["evidence_text"] == new["evidence_text"] if old["published"] else None,
            "original_proposal": old["proposed"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    run = args.output_dir.resolve()
    if not run.is_relative_to(HERE.resolve()):
        raise SystemExit("Replay output directory must stay inside validation_replay")
    if (run / "replay_outputs_finalized.json").exists():
        raise SystemExit("Replay already finalized; preserve its outputs.")
    # Make accidental network/inference inside this replay fail immediately.
    socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Network forbidden during replay"))
    before_source, before_inventory, before_support, before_schema = frozen_package()
    current_schema = importlib.import_module("src.evidence.prose_attribution.schema")
    all_rows, diffs, counts = [], [], collections.Counter()
    outputs = {cohort: {version: {dataset: {"cases": []} for dataset in ("regression", "unseen")}
                        for version in ("before", "after")} for cohort in ("final_proposals", "attempt_selection")}
    for dataset in ("regression", "unseen"):
        original = read(frozen_path(f"v2/outputs/{dataset}_complete.json"))
        for case in original["cases"]:
            ident = case["document_id"]
            folder = frozen_path(f"v2/runs/complete/{ident}")
            saved_source = read(folder / "source.json")
            old_source = source_from_saved(before_source, saved_source)
            new_source = source_from_saved(current_source, saved_source)
            old_candidates, new_candidates = before_inventory.inventory(old_source), current_inventory.inventory(new_source)
            assert old_candidates == new_candidates == read(folder / "inventory.json")
            old_frames, new_frames = before_support.discourse(old_source, old_candidates), current_support.discourse(new_source, new_candidates)
            assert old_frames == new_frames, "Ownership graph changed unexpectedly"
            attempts = {"before": [], "after": []}
            by_id = {"before": {}, "after": {}}
            for path in sorted(folder.glob("attempt_*/assessed_claims.json")):
                request = read(path.parent / "request.json")
                allowed = {unit["id"] for unit in json.loads(request["user_content"])["source_units"]}
                for saved in read(path):
                    old = assess(before_support, before_schema, old_source, old_candidates, old_frames, saved, allowed)
                    assert old == saved, (ident, saved["claim_id"], "Frozen validator did not reproduce saved assessment")
                    new = assess(current_support, current_schema, new_source, new_candidates, new_frames, saved, allowed)
                    for version, record in (("before", old), ("after", new)):
                        attempts[version].append(record)
                        by_id[version][record["claim_id"]] = record
                    all_rows.append({"dataset": dataset, "case_id": ident, "before": old, "after": new})
                    diffs.append(changed(old, new, dataset, ident, "all_attempts"))
                    counts.update(all_attempt_proposals=1)
            final = {version: [by_id[version][record["claim_id"]] for record in case["accepted_claims"] + case["unpublished_claims"]]
                     for version in ("before", "after")}
            for old, new in zip(final["before"], final["after"]):
                diffs.append(changed(old, new, dataset, ident, "final_proposals"))
                counts.update(final_proposals=1)
            selected = {version: select_attempts(attempts[version], corrected=version == "after") for version in ("before", "after")}
            chronological = {version: value[0] for version, value in selected.items()}
            assert {record["claim_id"] for record in chronological["before"]} == {record["claim_id"] for record in final["before"]}
            for cohort, versions in (("final_proposals", final), ("attempt_selection", chronological)):
                for version, records in versions.items():
                    result = {"document_id": ident, "accepted_claims": [record for record in records if record["published"]],
                              "unpublished_claims": [record for record in records if not record["published"]],
                              "candidate_ledger": ledger_for(case["candidate_ledger"], records, new_candidates),
                              "selection_decisions": selected[version][1] if cohort == "attempt_selection" else [],
                              "model_requests": 0, "inference_schedule": "Original saved attempts only; not rerun or rescheduled."}
                    outputs[cohort][version][dataset]["cases"].append(result)
    write(run / "all_attempt_assessments.json", all_rows)
    write(run / "claim_level_diff.json", diffs)
    for cohort, versions in outputs.items():
        for version, datasets in versions.items():
            for dataset, output in datasets.items():
                write(run / "outputs" / f"{cohort}_{version}_{dataset}.json", output)
    files = list((run / "outputs").glob("*.json")) + [run / "all_attempt_assessments.json", run / "claim_level_diff.json"]
    source_files = list((ROOT / "src/evidence/prose_attribution").glob("*.py"))
    write(run / "replay_outputs_finalized.json", {
        "status": "replay_outputs_finalized_before_evaluation", "new_model_requests": 0,
        "outputs_sha256": {str(path.relative_to(run)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "current_code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files},
        "reference_files_read_by_replay": [], "counts": dict(counts)})
    print(json.dumps({cohort: {version: {dataset: dict(collections.Counter(record["status"] for case in output["cases"] for record in case["accepted_claims"] + case["unpublished_claims"])) for dataset, output in datasets.items()} for version, datasets in versions.items()} for cohort, versions in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
