"""Phase 1 only: freeze and audit existing responses without inference."""
import collections
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "experiments/prose_attribution_ab_20261013"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    frozen = HERE / "frozen_baseline"
    if (HERE / "freeze_manifest.json").exists():
        raise SystemExit("Baseline already frozen; do not replace the audit.")
    frozen.mkdir(exist_ok=True)
    names = ("run_experiment.py", "normalize.py", "wiretap.py", "finalize_conversion.py",
             "a_output.json", "b_output.json", "a_output_initial.json", "b_output_initial.json",
             "common_task.json", "input_manifest.json", "run_manifest.json", "semantic_review.json",
             "a_scores.json", "b_scores.json", "conversion_finalized.json", "requirements-experiment.lock")
    for name in names:
        shutil.copy2(BASE / name, frozen / name)
    for directory in ("a_parsed", "b_sdk", "http", "conversion_final", "model_inputs"):
        shutil.copytree(BASE / directory, frozen / directory)
    evaluation = HERE / "evaluation_only"
    evaluation.mkdir(exist_ok=True)
    for name in ("evaluate.py", "test_evaluate.py", "passages.json"):
        shutil.copy2(BASE / "evaluation" / name, evaluation / name)
    shutil.copy2(BASE / "evaluation/evaluation_only/gold.json", evaluation / "regression_gold.json")
    source_names = ("src/summarization/summarize.py", "src/evidence/monitor.py",
                    "src/evidence/schema.py", "src/evidence/verifier.py", "src/evidence/represent.py",
                    "src/evidence/chunker.py", "src/processing/pdf_parser.py", "src/config.py")
    source_hashes = {}
    for name in source_names:
        destination = frozen / "repository" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
        source_hashes[name] = sha(ROOT / name)
    record_names = ("data/processed/paper_summaries.json", "data/processed/chunks.json",
                    "data/processed/extraction_cache.json", "data/processed/paper_evidence.json")
    production = {name: sha(ROOT / name) for name in record_names if (ROOT / name).is_file()}
    review = read(BASE / "semantic_review.json")
    audit = {"phase": "1_audit_only", "new_inference_requests": 0, "candidates": {},
             "conversion_audit": {}, "separation": "Layout, quote alignment, association and omissions remain separate.",
             "layout_conclusion": "Fixed inputs were already extracted prose. No evidence establishes layout corruption as the sole cause.",
             "normalization_conclusion": "Zero observed numeric/relationship changes from normalization; strict terminology incompatibility is distinct from factual error. Incomplete per-acre units originated in model attributes.",
             "initial_conversion_failures": {"a": "Multiple same-ID case wrappers in 04/05 and empty cases wrapper in 07; fixed before prior scoring without inference.",
                                             "b": "Null attributes caused initial whole-case rejection in 02; valid records and malformed record retained before prior scoring."}}
    for candidate in ("a", "b"):
        changes = collections.Counter()
        altered_evidence = 0
        output = read(BASE / (candidate + "_output.json"))
        for case in output["cases"]:
            conversion = read(BASE / "conversion_final" / (candidate + "_" + case["id"] + ".json"))
            for item in conversion:
                for change in item.get("normalization_changes", []):
                    changes[(change["field"], change["rule"])] += 1
                if item.get("raw_claim", {}).get("evidence_text") != item.get("normalized_claim", {}).get("evidence_text"):
                    altered_evidence += 1
        records = review["claim_reviews"][candidate]
        quotes = [{"case_id": row["case_id"], "index": row["index"], "evidence": row["claim"]["evidence_text"],
                   "origin": "model output; normalization/conversion retained this text",
                   "relationship_complete": row["evidence_relationship_complete"]}
                  for row in records if not row["evidence_verbatim"]]
        association = [{"case_id": row["case_id"], "index": row["index"],
                        "unsupported_context_fields": row["unsupported_context_fields"],
                        "claim": row["claim"]}
                       for row in records if row["unsupported_context_fields"]]
        audit["candidates"][candidate] = {"counts": review["candidates"][candidate]["reviewed_counts"],
                                          "omitted_quantities": [{"case_id": case["id"], "quantities": case["missing_source_quantities"]}
                                                                 for case in review["candidates"][candidate]["cases"] if case["missing_source_quantities"]],
                                          "invalid_quotations": quotes, "association_errors": association}
        audit["conversion_audit"][candidate] = {"evidence_strings_changed_by_conversion": altered_evidence,
                                                 "normalization_decisions": [{"field": key[0], "rule": key[1], "count": count}
                                                                             for key, count in sorted(changes.items())]}
        assert altered_evidence == 0
    hashes = {str(path.relative_to(HERE)): sha(path) for folder in (frozen, evaluation)
              for path in folder.rglob("*") if path.is_file()}
    manifest = {"status": "baseline_and_reference_frozen_before_extraction_changes",
                "baseline_files_sha256": hashes, "repository_source_sha256": source_hashes,
                "production_records_sha256": production, "new_inference_requests": 0}
    (HERE / "freeze_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (HERE / "phase1_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps({"phase": audit["phase"], "new_inference_requests": 0,
                      "evidence_conversion_changes": {c: audit["conversion_audit"][c]["evidence_strings_changed_by_conversion"] for c in ("a", "b")},
                      "counts": {c: audit["candidates"][c]["counts"] for c in ("a", "b")}}, indent=2))


if __name__ == "__main__":
    main()
