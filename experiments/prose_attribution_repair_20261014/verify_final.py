"""Verify immutable inputs, production isolation and actual request budgets."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = HERE / "v2"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    frozen = read(HERE / "freeze_manifest.json")
    for name, digest in frozen["baseline_files_sha256"].items():
        assert sha(HERE / name) == digest, name
    for section in ("repository_source_sha256", "production_records_sha256"):
        for name, digest in frozen[section].items():
            assert sha(ROOT / name) == digest, name
    unseen = read(HERE / "unseen_freeze_manifest.json")
    assert sha(HERE / "fixtures/unseen_inputs.json") == unseen["input_sha256"]
    assert sha(HERE / "evaluation_only/unseen_gold.json") == unseen["reference_sha256"]
    final = read(RUN / "comparison_outputs_finalized.json")
    for name, digest in final["output_sha256"].items():
        assert sha(RUN / name) == digest, name
    for name, digest in final["repair_source_hashes"].items():
        assert sha(ROOT / name) == digest, name
        assert sha(RUN / "frozen_repair" / name) == digest, name
    prepared = read(HERE / "evaluation_only/evaluator_prepared_manifest.json")
    assert sha(HERE / "evaluation_only/compare_final.py") == prepared["evaluator_sha256"]
    assert sha(HERE / "EVALUATION_PROTOCOL.md") == prepared["protocol_sha256"]
    manifest = read(RUN / "comparison_run_manifest.json")
    before_digest = manifest["model"]["digest"]
    after_digest = next(model["digest"] for model in manifest["model_after"]["models"] if model["name"] == manifest["model"]["name"])
    assert before_digest == after_digest
    counts = collections.Counter()
    documents = []
    budget_violations = []
    for dataset in ("regression", "unseen"):
        inputs = {case["id"]: case for case in read(HERE / "fixtures" / (dataset + "_inputs.json"))["cases"]}
        outputs = read(RUN / "outputs" / (dataset + "_complete.json"))["cases"]
        for result in outputs:
            ident = result["document_id"]
            folder = RUN / "runs/complete" / ident
            inventory = read(folder / "inventory.json")
            requests = result["requests"]
            assert len(requests) <= result["request_cap"] == 3
            assert len(set(result["retried_evidence_units"])) == len(result["retried_evidence_units"])
            assert len(requests) == 1 + len(result["retried_evidence_units"])
            # The hard cap covers inference scheduling/transport. Allow one
            # second for process cleanup, source assessment and durable output.
            if result["elapsed_s"] > result["document_time_cap_s"] + 1:
                budget_violations.append({"id": ident, "kind": "observed_document_wall_clock_overrun",
                                          "elapsed_s": result["elapsed_s"], "cap_s": result["document_time_cap_s"]})
            ledger_ids = [entry["candidate_id"] for entry in result["candidate_ledger"]]
            assert len(ledger_ids) == len(set(ledger_ids)) == len(inventory)
            assert set(ledger_ids) == {candidate["id"] for candidate in inventory}
            assert all(entry["state"] in ("associated", "outside_scope", "ambiguous", "unresolved") for entry in result["candidate_ledger"])
            for request in requests:
                attempt = folder / ("attempt_" + str(request["attempt"]).zfill(2))
                planned = read(attempt / "request.json")
                actual = read(attempt / "actual_request.json")
                payload = actual["payload"]
                assert payload["model"] == manifest["model"]["name"]
                assert actual["url"] == manifest["endpoint"].rstrip("/") + "/api/chat"
                for key, value in (("temperature", 0), ("seed", 42), ("num_ctx", 8192), ("num_predict", 4096)):
                    assert payload["options"][key] == value
                assert payload["format"] == planned["response_schema"]
                assert 0 < planned["settings"]["request_seconds"] <= 180
                if request["elapsed_s"] > planned["settings"]["request_seconds"] + 1:
                    budget_violations.append({"id": ident, "attempt": request["attempt"],
                                              "kind": "observed_request_wall_clock_overrun",
                                              "elapsed_s": request["elapsed_s"],
                                              "cap_s": planned["settings"]["request_seconds"],
                                              "hard_timeout_flag": request["hard_timeout"]})
                content = json.loads(planned["user_content"])
                assert content["document_id"] == ident
                assert all(set(unit) == {"id", "block_id", "text", "length"} for unit in content["source_units"])
                assert "evaluation_only" not in planned["user_content"]
                counts.update(actual_complete_requests=1, hard_timeouts=int(bool(request["hard_timeout"])))
            for claim in result["accepted_claims"]:
                assert claim["published"] and claim["status"] == "supported"
                assert claim["evidence_text"] in inputs[ident]["text"]
                assert claim["structural_validation"]["does_not_establish_semantic_ownership"]
                assert claim["quotation"]["ownership_established_by_reconstruction"] is False
            counts.update(accepted_claims=len(result["accepted_claims"]), documents=1,
                          context_retries=len(result["retried_evidence_units"]))
            documents.append({"id": ident, "requests": len(requests), "elapsed_s": result["elapsed_s"],
                              "time_cap_s": result["document_time_cap_s"], "cap_cleanup_allowance_s": 1})
    report = {"status": "passed_integrity_with_budget_violation" if budget_violations else "passed",
              "frozen_baseline_files": len(frozen["baseline_files_sha256"]),
              "unchanged_existing_source_files": len(frozen["repository_source_sha256"]),
              "unchanged_production_record_files": len(frozen["production_records_sha256"]),
              "unseen_inputs_and_reference_unchanged": True, "repair_code_unchanged": True,
              "prepared_evaluator_unchanged": True, "model_digest_unchanged": before_digest,
              "actual_request_settings_verified": True, "geometry_excluded_from_model_units": True,
              "bounded_retries_and_request_count_verified": True,
              "observed_wall_clock_caps_held": not budget_violations, "budget_violations": budget_violations,
              "counts": dict(counts), "documents": documents}
    (RUN / "integrity_verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "documents"}, indent=2))


if __name__ == "__main__":
    main()
