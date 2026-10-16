"""Execute frozen baseline and opt-in repair; no evaluator/reference assembly."""
import dataclasses
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = HERE / "v2"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE / "frozen_baseline"))
from wiretap import Wiretap
from normalize import normalize
from src.summarization.summarize import call_ollama_json
from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.quotes import repair_saved_claim
from src.evidence.prose_attribution.extractor import RepairConfig, extract_document


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_for(case, dataset):
    blocks = case.get("blocks")
    if blocks is None:
        parts = case["text"].split("\n\n")
        segments = case.get("source_segments") or []
        blocks = [{"id": f"b{index + 1}", "text": text, "reading_order": index,
                   "reading_order_status": "provided_benchmark_input_order",
                   "page": segments[index].get("page") if index < len(segments) else None,
                   "column": segments[index].get("column") if index < len(segments) else None,
                   "metadata_origin": "benchmark-provided; original PDF not reread"} for index, text in enumerate(parts)]
    return SourceDocument.from_text(case["id"], case["text"], blocks=blocks,
                                    metadata={"source_kind": "narrative_overview", "dataset": dataset,
                                              "original_pdf_text_available": False,
                                              "upstream_normalization": "benchmark whitespace collapse" if dataset == "regression" else None,
                                              "metadata_origin": "synthetic" if dataset == "unseen" else "benchmark-provided"})


def legacy_baseline(case, llm, adapter, tap):
    directory = RUN / "runs/baseline" / case["id"]
    if (directory / "result.json").exists():
        return read(directory / "result.json")
    directory.mkdir(parents=True, exist_ok=True)
    adapter.HERE = directory
    tap.label = "baseline_" + case["id"]
    before, started = len(tap.records), time.perf_counter()
    error = None
    try:
        adapter.run_a(case, read(HERE / "frozen_baseline/common_task.json")["instructions"], llm)
    except Exception as failure:
        error = {"type": type(failure).__name__, "message": str(failure)}
    elapsed = time.perf_counter() - started
    parsed_path = directory / "a_parsed" / (case["id"] + ".json")
    saved = read(parsed_path) if parsed_path.exists() else {}
    parsed = saved.get("parsed")
    claims, reported = [], []
    if isinstance(parsed, dict) and saved.get("meta", {}).get("done_reason") == "stop":
        for entry in parsed.get("cases", []):
            if isinstance(entry, dict) and isinstance(entry.get("claims"), list):
                reported.append(entry.get("id"))
                claims.extend(normalize(claim)[0] if isinstance(claim, dict) else claim for claim in entry["claims"])
    captured = tap.records[before:]
    completion = {}
    if captured:
        for line in reversed(captured[-1].get("raw_response_lines", [])):
            if line:
                item = json.loads(line)
                if item.get("done"):
                    completion = item
                    break
    result = {"id": case["id"], "claims": claims, "elapsed_s": elapsed, "request_count": len(captured),
              "reported_case_ids": reported, "wrapper_or_conversion_error": error,
              "completion": {key: completion.get(key) for key in ("done_reason", "prompt_eval_count", "prompt_eval_cached_count", "eval_count")}}
    write(directory / "result.json", result)
    return result


def quote_only(case, baseline, source):
    directory = RUN / "runs/quotation_only" / case["id"]
    started = time.perf_counter()
    claims, decisions = [], []
    for index, original in enumerate(baseline["claims"]):
        updated, decision = repair_saved_claim(source, original)
        claims.append(updated)
        decisions.append({"index": index, **decision})
    result = {"id": case["id"], "claims": claims, "host_elapsed_s": time.perf_counter() - started,
              "inherited_inference_elapsed_s": baseline["elapsed_s"], "new_requests": 0, "decisions": decisions}
    write(directory / "result.json", result)
    return result


def main():
    if (RUN / "comparison_outputs_finalized.json").exists():
        raise SystemExit("Comparison already finalized; do not overwrite this run.")
    frozen = read(HERE / "freeze_manifest.json")
    for name, digest in frozen["baseline_files_sha256"].items():
        assert sha(HERE / name) == digest, name
    for name, digest in frozen["repository_source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    llm = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))["llm"]
    tags = requests.get(llm["base_url"] + "/api/tags", timeout=10).json()
    model = next(model for model in tags["models"] if model["name"] == llm["model"])
    expected_digest = read(HERE / "frozen_baseline/run_manifest.json")["model_before"]["models"][0]["digest"]
    assert model["digest"] == expected_digest, "Local model changed from the frozen baseline"
    config_values = yaml.safe_load((HERE / "experiment_config.yaml").read_text(encoding="utf-8"))["prose_attribution_repair"]
    config = RepairConfig(**{key: value for key, value in config_values.items() if key in {field.name for field in dataclasses.fields(RepairConfig)}})
    regression_path = HERE / "fixtures/regression_inputs.json"
    if not regression_path.exists():
        shutil.copy2(ROOT / "experiments/prose_attribution_ab_20261013/benchmark/passages.json", regression_path)
    regression = read(regression_path)["cases"]
    unseen = read(HERE / "fixtures/unseen_inputs.json")["cases"]
    assert len(regression) == 7 and len(unseen) == 8
    for case in regression + unseen:
        assert hashlib.sha256(case["text"].encode("utf-8")).hexdigest() == case["sha256"]
    code_files = list((ROOT / "src/evidence/prose_attribution").glob("*.py")) + [HERE / "run_comparison.py", HERE / "experiment_config.yaml"]
    code_hashes = {str(path.relative_to(ROOT)): sha(path) for path in code_files}
    snapshot = RUN / "frozen_repair"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in code_files:
        target = snapshot / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert sha(target) == sha(path), "Repair code changed during resume"
        else:
            shutil.copy2(path, target)
    manifest = {"status": "running", "client_date": "2026-10-14", "timezone": "Asia/Calcutta",
                "python": sys.version, "python_executable": sys.executable,
                "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "model": model, "endpoint": llm["base_url"], "repair_config": dataclasses.asdict(config),
                "repair_source_hashes": code_hashes, "input_hashes": {case["id"]: case["sha256"] for case in regression + unseen},
                "cache_policy": "client bypass; server KV reuse retained", "run_records": [],
                "baseline_regression": "saved unchanged 2026-10-13 run; not regenerated", "evaluation_files_loaded_by_model_assembly": [],
                "protocol_pilot": "v1 stopped after three completed documents plus one cancelled in-flight request; its raw attempts remain in the parent experiment directory."}
    write(RUN / "comparison_run_manifest.json", manifest)
    spec = importlib.util.spec_from_file_location("frozen_prototype_a", HERE / "frozen_baseline/run_experiment.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    historical = read(HERE / "frozen_baseline/a_output.json")
    historical_run = read(HERE / "frozen_baseline/run_manifest.json")
    outputs = {dataset: {variant: {"cases": []} for variant in ("baseline", "quotation_only", "complete")} for dataset in ("regression", "unseen")}
    started = time.perf_counter()
    with Wiretap(RUN / "baseline_http", llm["base_url"]) as tap:
        tap.label = "warmup"
        warm_start = time.perf_counter()
        warm = call_ollama_json(llm["base_url"], llm["model"], 'Return exactly {"ok":true}.',
                                "An unrelated brass bell rings once.", temperature=0, seed=42, max_retries=0,
                                num_ctx=8192, num_predict=4096, timeout=60, deadline_seconds=60)
        assert warm == {"ok": True}, "Warmup failed"
        manifest["warmup_seconds_excluded"] = time.perf_counter() - warm_start
        for dataset, cases in (("regression", regression), ("unseen", unseen)):
            for index, case in enumerate(cases):
                source = source_for(case, dataset)
                if dataset == "regression":
                    saved = next(item for item in historical["cases"] if item["id"] == case["id"])
                    timing = next(item for item in historical_run["runs"] if item["candidate"] == "a" and item["case_id"] == case["id"])
                    baseline = {**saved, "elapsed_s": timing["elapsed_s"], "request_count": timing["request_count"], "completions": timing["completions"], "historical": True}
                    complete = extract_document(source, llm, RUN / "runs/complete" / case["id"], config)
                else:
                    if index % 2 == 0:
                        baseline = legacy_baseline(case, llm, adapter, tap)
                        complete = extract_document(source, llm, RUN / "runs/complete" / case["id"], config)
                    else:
                        complete = extract_document(source, llm, RUN / "runs/complete" / case["id"], config)
                        baseline = legacy_baseline(case, llm, adapter, tap)
                quote = quote_only(case, baseline, source)
                outputs[dataset]["baseline"]["cases"].append(baseline)
                outputs[dataset]["quotation_only"]["cases"].append(quote)
                outputs[dataset]["complete"]["cases"].append(complete)
                record = {"dataset": dataset, "case_id": case["id"], "baseline_seconds": baseline["elapsed_s"],
                          "complete_seconds": complete["elapsed_s"], "accepted_claims": len(complete["accepted_claims"]),
                          "unpublished_claims": len(complete["unpublished_claims"]), "requests": len(complete["requests"]),
                          "retries": len(complete["retried_evidence_units"]), "accounting": complete["accounting"]}
                manifest["run_records"].append(record)
                write(RUN / "comparison_run_manifest.json", manifest)
                print(json.dumps(record), flush=True)
    for dataset, variants in outputs.items():
        for variant, result in variants.items():
            write(RUN / "outputs" / f"{dataset}_{variant}.json", result)
    for path in code_files:
        assert sha(path) == code_hashes[str(path.relative_to(ROOT))], "Repair changed during model evaluation"
    manifest.update(status="all_outputs_finalized_before_evaluation", total_wall_seconds=time.perf_counter() - started,
                    model_after=requests.get(llm["base_url"] + "/api/tags", timeout=10).json())
    write(RUN / "comparison_run_manifest.json", manifest)
    write(RUN / "comparison_outputs_finalized.json", {"status": manifest["status"], "output_sha256": {str(path.relative_to(RUN)): sha(path) for path in (RUN / "outputs").glob("*.json")},
                                                       "repair_source_hashes": code_hashes, "new_evaluation_reference_loaded": False})
    print("All baseline, quotation-only and complete-repair outputs finalized before comparative evaluation.", flush=True)


if __name__ == "__main__":
    main()
