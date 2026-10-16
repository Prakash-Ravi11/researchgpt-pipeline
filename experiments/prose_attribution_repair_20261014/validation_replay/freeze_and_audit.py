"""Read-only diagnostic audit and snapshot before any validation correction."""
import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
sys.path.insert(0, str(ROOT))
from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.inventory import inventory
from src.evidence.prose_attribution.support import discourse, measurement_features, anchors, canonical_topic

CORE = ("subject", "value", "outcome", "qualifier", "condition")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source(path):
    saved = read(path)
    return SourceDocument.from_text(saved["document_id"], saved["original_text"],
                                    blocks=saved["blocks"], metadata=saved["metadata"])


def main():
    if (HERE / "before_freeze_manifest.json").exists():
        raise SystemExit("Already frozen; do not replace the pre-correction snapshot.")
    files = list((ROOT / "src/evidence/prose_attribution").glob("*.py"))
    files += list((ROOT / "tests").glob("test_prose_attribution*.py"))
    files += [ROOT / "scripts/extract_prose_claims.py"]
    for directory in (EXP / "v2", EXP / "fixtures", EXP / "evaluation_only"):
        files += [path for path in directory.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    files += [path for path in EXP.iterdir() if path.is_file()]
    files = sorted(set(files))
    hashes = {}
    for path in files:
        name = str(path.relative_to(ROOT))
        hashes[name] = sha(path)
        target = HERE / "before" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    original = read(EXP / "freeze_manifest.json")
    for key in ("repository_source_sha256", "production_records_sha256"):
        for name, digest in original[key].items():
            assert sha(ROOT / name) == digest, name
    write(HERE / "before_freeze_manifest.json", {
        "status": "frozen_before_validation_changes", "sha256": hashes,
        "production_records_sha256": original["production_records_sha256"],
        "existing_source_sha256": original["repository_source_sha256"],
        "new_model_requests": 0, "comparison_scope": "finalized v2; v1 is an excluded protocol pilot"})
    populations = {"final": [], "all_attempts": []}
    ledgers = []
    for dataset in ("regression", "unseen"):
        for case in read(EXP / "v2/outputs" / f"{dataset}_complete.json")["cases"]:
            ident = case["document_id"]
            folder = EXP / "v2/runs/complete" / ident
            source = load_source(folder / "source.json")
            candidates = inventory(source)
            assert candidates == read(folder / "inventory.json")
            frames = discourse(source, candidates)
            by_id = {candidate["id"]: candidate for candidate in candidates}
            rows = [("final", row) for row in case["accepted_claims"] + case["unpublished_claims"]]
            for path in sorted(folder.glob("attempt_*/assessed_claims.json")):
                rows += [("all_attempts", row) for row in read(path)]
            for population, record in rows:
                proposed = record["proposed"]
                support = record["field_support"]
                chosen = [by_id[identifier] for identifier in proposed.get("candidate_ids", []) if identifier in by_id]
                frame = frames[chosen[0]["id"]] if chosen else None
                feature = measurement_features(source, chosen[0], candidates) if chosen else None
                core_supported = bool(support and all(support.get(field, {}).get("status") == "supported" for field in CORE))
                reasons = [{"field": field, **decision} for field, decision in support.items()
                           if decision["status"] != "supported"]
                row = {"dataset": dataset, "case_id": ident, "claim_id": record["claim_id"],
                       "attempt": record["attempt"], "status": record["status"], "published": record["published"],
                       "core_supported": core_supported,
                       "rejected_solely_optional_context": core_supported and not record["published"],
                       "raw_proposal": proposed, "candidate_occurrences": chosen,
                       "source_units": source.model_units(), "field_support": support,
                       "structural_validation": record["structural_validation"],
                       "semantic_assessment": record["semantic_assessment"], "non_supported_decisions": reasons,
                       "validator": "src/evidence/prose_attribution/support.py:assess_claim",
                       "frame": frame, "measurement_feature": feature,
                       "context_values": {field: {"proposed": proposed.get(field), "published": record.get(field),
                                                   "decision": support.get(field)} for field in ("location", "year", "population")}}
                populations[population].append(row)
            ledgers += [{"dataset": dataset, "case_id": ident, **entry} for entry in case["candidate_ledger"]]
    summaries = {}
    for population, rows in populations.items():
        reasons = collections.Counter()
        optional = collections.Counter()
        for row in rows:
            if row["status"] != "supported" and not row["field_support"]:
                reasons[("early", row["semantic_assessment"].get("status"), None, row["semantic_assessment"].get("reason"))] += 1
            for field, decision in row["field_support"].items():
                if decision["status"] != "supported":
                    reasons[(field, decision["status"], decision.get("assessment_rule"), decision["reason"])] += 1
                if field in ("location", "year", "population"):
                    optional[(field, "model_null" if row["raw_proposal"].get(field) is None else "model_nonnull", decision["status"])] += 1
        summaries[population] = {
            "records": len(rows), "statuses": dict(collections.Counter(row["status"] for row in rows)),
            "core_supported": sum(row["core_supported"] for row in rows),
            "sole_optional_publication_failures": sum(row["rejected_solely_optional_context"] for row in rows),
            "non_supported_decision_counts": [{"field": field, "status": status, "assessment_rule": rule,
                                               "exact_artifact_reason": reason, "count": count}
                                              for (field, status, rule, reason), count in reasons.items()],
            "optional_field_counts": [{"field": field, "proposal_state": state, "field_status": status, "count": count}
                                      for (field, state, status), count in optional.items()]}
    audit = {"status": "diagnostic_extraction_before_changes", "new_model_requests": 0,
             "recorded_rejection_codes": "No machine rejection-code property exists in these claim records. Exact reason strings and assessment_rule IDs are retained; no code is invented.",
             "same_block_context_requirement": False,
             "source_rule": "assess_claim uses frame.context_ids, context reference inclusion and literal value support; no block-ID equality test for location/year. discourse separately checks missing reading order for cross-block anaphora.",
             "summaries": summaries, "candidate_ledger": {"entries": len(ledgers),
                    "states": dict(collections.Counter(entry["state"] for entry in ledgers))},
             "populations": populations}
    write(HERE / "diagnostic_audit.json", audit)
    print(json.dumps({"summaries": {name: {key: value for key, value in summary.items() if key not in ("non_supported_decision_counts", "optional_field_counts")} for name, summary in summaries.items()},
                      "candidate_ledger": audit["candidate_ledger"], "frozen_files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
