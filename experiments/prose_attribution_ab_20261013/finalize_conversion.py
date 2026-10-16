"""Convert saved SDK records, preserving malformed records instead of losing a case.

No inference, expected answers or evaluator access. The original runner results
and its initial conversion failure remain available for audit.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

from normalize import normalize
from wiretap import write_json

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    initial = json.loads((HERE / "finalized.json").read_text(encoding="utf-8"))
    assert initial["gold_loaded"] is False
    for name, digest in initial["frozen_sha256"].items():
        assert sha(HERE / name) == digest, name
    assert not (HERE / "conversion_finalized.json").exists(), "Already converted"
    shutil.copy2(HERE / "finalized.json", HERE / "initial_finalized.json")
    for candidate in ("a", "b"):
        shutil.copy2(HERE / (candidate + "_output.json"), HERE / (candidate + "_output_initial.json"))
    manifest = json.loads((HERE / "run_manifest.json").read_text(encoding="utf-8"))
    result = {"cases": []}
    outcomes = []
    for path in sorted((HERE / "model_inputs").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        sdk_path = HERE / "b_sdk" / (case["id"] + ".json")
        run = next(r for r in manifest["runs"] if r["candidate"] == "b" and r["case_id"] == case["id"])
        sdk = json.loads(sdk_path.read_text(encoding="utf-8")) if sdk_path.exists() else None
        claims, decisions = [], []
        malformed = 0
        complete = bool(sdk is not None and run["request_count"] == 1
                        and all(c["done_reason"] == "stop" for c in run["completions"]))
        if complete:
            prefix = len("Input ID: " + case["id"] + "\n\n")
            for index, extraction in enumerate(sdk["extractions"]):
                attributes = extraction.get("attributes")
                bad_attributes = not isinstance(attributes, dict)
                malformed += int(bad_attributes)
                raw = {**(attributes if isinstance(attributes, dict) else {}),
                       "evidence_text": extraction.get("extraction_text")}
                normalized, changes = normalize(raw)
                claims.append(normalized)
                evidence = normalized.get("evidence_text")
                starts = [m.start() for m in re.finditer(re.escape(evidence), case["text"])] if isinstance(evidence, str) and evidence else []
                interval = extraction.get("char_interval")
                shifted = None
                if interval and interval.get("start_pos") is not None and interval.get("end_pos") is not None:
                    shifted = {"start": interval["start_pos"] - prefix, "end": interval["end_pos"] - prefix}
                verbatim = bool(shifted and 0 <= shifted["start"] <= shifted["end"] <= len(case["text"])
                                and case["text"][shifted["start"]:shifted["end"]] == evidence)
                decisions.append({"index": index, "raw_claim": raw, "normalized_claim": normalized,
                                  "normalization_changes": changes,
                                  "malformed_attributes": bad_attributes,
                                  "original_attributes": attributes,
                                  "extraction_class": extraction.get("extraction_class"),
                                  "source_alignment": {"status": "exact" if len(starts) == 1 else "ambiguous" if starts else "unresolved",
                                                       "intervals": [{"start": s, "end": s + len(evidence)} for s in starts],
                                                       "sdk_status": extraction.get("alignment_status"),
                                                       "sdk_input_interval": interval,
                                                       "sdk_source_interval": shifted,
                                                       "sdk_interval_verbatim": verbatim}})
        result["cases"].append({"id": case["id"], "claims": claims})
        write_json(HERE / "conversion_final" / ("b_" + case["id"] + ".json"), decisions)
        outcomes.append({"case_id": case["id"], "complete_inference_and_sdk_output": complete,
                         "record_count": len(claims), "malformed_attributes": malformed,
                         "initial_adapter_error": run["error"]})
    write_json(HERE / "b_output.json", result)
    a_result = {"cases": []}
    a_outcomes = []
    for path in sorted((HERE / "model_inputs").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        parsed_path = HERE / "a_parsed" / (case["id"] + ".json")
        run = next(r for r in manifest["runs"] if r["candidate"] == "a" and r["case_id"] == case["id"])
        stored = json.loads(parsed_path.read_text(encoding="utf-8")) if parsed_path.exists() else {}
        parsed = stored.get("parsed")
        complete = bool(isinstance(parsed, dict) and not parsed.get("_deadline_exceeded")
                        and run["request_count"] == 1
                        and all(c["done_reason"] == "stop" for c in run["completions"]))
        claims, decisions, reported_ids = [], [], []
        entries = parsed.get("cases", []) if complete else []
        if not isinstance(entries, list):
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            reported_ids.append(entry.get("id"))
            raw_claims = entry.get("claims", [])
            if not isinstance(raw_claims, list):
                continue
            for raw in raw_claims:
                if not isinstance(raw, dict):
                    claims.append(raw)
                    decisions.append({"index": len(claims) - 1, "raw_claim": raw,
                                      "malformed_claim": True, "source_alignment": None})
                    continue
                normalized, changes = normalize(raw)
                claims.append(normalized)
                evidence = normalized.get("evidence_text")
                starts = [m.start() for m in re.finditer(re.escape(evidence), case["text"])] if isinstance(evidence, str) and evidence else []
                decisions.append({"index": len(claims) - 1, "raw_claim": raw,
                                  "normalized_claim": normalized, "normalization_changes": changes,
                                  "reported_case_id": entry.get("id"),
                                  "source_alignment": {"status": "exact" if len(starts) == 1 else "ambiguous" if starts else "unresolved",
                                                       "intervals": [{"start": s, "end": s + len(evidence)} for s in starts]}})
        a_result["cases"].append({"id": case["id"], "claims": claims})
        write_json(HERE / "conversion_final" / ("a_" + case["id"] + ".json"), decisions)
        a_outcomes.append({"case_id": case["id"], "complete_inference": complete,
                           "record_count": len(claims), "reported_case_ids": reported_ids,
                           "wrapper_anomaly": len(reported_ids) != 1 or reported_ids != [case["id"]],
                           "initial_adapter_error": run["error"]})
    write_json(HERE / "a_output.json", a_result)
    frozen = {**initial["frozen_sha256"], "finalize_conversion.py": sha(HERE / "finalize_conversion.py")}
    final = {"status": "both_outputs_finalized_before_gold", "gold_loaded": False,
             "output_sha256": {name: sha(HERE / name) for name in ("a_output.json", "b_output.json")},
             "frozen_sha256": frozen,
             "conversion_correction": "Saved B SDK records with null attributes are retained with null common fields; populated records remain. Saved A cases entries are flattened under the known request ID, retaining reported IDs separately. No model retry or relationship repair; original initial outputs preserved.",
             "a_cases": a_outcomes, "b_cases": outcomes}
    write_json(HERE / "finalized.json", final)
    write_json(HERE / "conversion_finalized.json", final)
    print(json.dumps({"status": final["status"], "a_cases": a_outcomes, "b_cases": outcomes}, indent=2))


if __name__ == "__main__":
    main()
