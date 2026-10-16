"""Fail closed if a suspended/delayed host returns a late worker completion.

The frozen v2 experiment predates this guard. No process can enforce elapsed
wall time while its host is suspended; on resumption a late result must not be
published, and the overrun must be visible instead of mistaken for normal timing.
"""
import hashlib
import json
import dataclasses
from pathlib import Path

from .extractor import RepairConfig, extract_document, run_request, write

TRANSPORT_VERSION = "hard-deadline-guard-v1"


def reject_late_completion(request, directory, wall_seconds, *, transport=run_request):
    result = transport(request, directory, wall_seconds)
    if result.get("host_elapsed_s", 0) > wall_seconds:
        # Preserve the pre-guard result as well as the incremental raw stream.
        write(Path(directory) / "pre_deadline_guard_result.json", result)
        result = {**result, "parsed": None, "deadline_exceeded": True,
                  "late_completion_rejected": True, "transport_version": TRANSPORT_VERSION,
                  "completion_before_guard": result.get("completion", {}),
                  "completion": {**result.get("completion", {}), "done_reason": "deadline_exceeded"}}
        write(Path(directory) / "host_result.json", result)
    return result


def extract_bounded_document(source, llm_config, output_directory, config=RepairConfig()):
    result = extract_document(source, llm_config, output_directory, config,
                              request_executor=reject_late_completion)
    if result.get("status") == "disabled":
        return result
    result["transport_version"] = TRANSPORT_VERSION
    result["cache_key_before_transport_version"] = result["cache_key"]
    result["cache_key"] = hashlib.sha256(json.dumps({"core_cache_key": result["cache_key"],
                                                    "transport_version": TRANSPORT_VERSION,
                                                    "budget_configuration": dataclasses.asdict(config),
                                                    "host_source_representation": source.as_dict()},
                                                   sort_keys=True).encode()).hexdigest()
    result["observed_document_deadline_exceeded"] = result["elapsed_s"] > config.document_seconds
    result["deadline_limitation"] = "Wall-clock enforcement requires a running host; late completions fail closed on resumption."
    write(Path(output_directory) / "result.json", result)
    return result
