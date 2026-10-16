"""One sequential, alternating A/B pass. Does not access evaluator or gold."""
import dataclasses
import hashlib
import importlib.metadata as metadata
import inspect
import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests
import yaml
import langextract as lx
from langextract.core import data
from langextract.providers.ollama import OllamaLanguageModel, OLLAMA_FORMAT_HANDLER

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.summarization.summarize import call_ollama_json
from src.evidence.monitor import ExtractionTrace
from normalize import FIELDS, normalize
from wiretap import Wiretap, write_json

SETTINGS = {"temperature": 0.0, "seed": 42, "num_ctx": 8192, "num_predict": 4096,
            "top_k": 40, "top_p": 0.9, "repeat_penalty": 1.1, "timeout_seconds": 240}
EXAMPLE_TEXT = ("A trial of the fictional Nimbus fog collector in Lark Island in 2017 "
                "reduced cleaning costs by 17%.")
EXAMPLE_CLAIM = {"subject": "Nimbus", "location": "Lark Island", "year": 2017,
                 "outcome": "cleaning_cost_reduction", "value": 17,
                 "unit": "percent", "qualifier": "exact", "evidence_text": EXAMPLE_TEXT}
EXTRA_INSTRUCTIONS = """
Treat blank-line-separated examples as separate deployment context boundaries.
Return one study-level record for each numerical outcome; separate distinct
quantities, including forecast error bounds and the proportion satisfying a bound.
Use a concise named brand/product as subject. Use null for unsupported location or
year, and a JSON number for value. Keep an explicit condition in evidence even
when another record describes the threshold. Repeated evidence spans are allowed
when several quantities share ownership context. Do not omit a claim solely because
another claim uses the same evidence. Evidence must include enough contiguous
context to support the subject and stated local fields, even if this requires a
whole paragraph. Do not fill fields from the fictional example.
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def common_input(case):
    return "Input ID: " + case["id"] + "\n\n" + case["text"]


def boundary_spans(text):
    return [{"index": index, "start": match.start(), "end": match.end()}
            for index, match in enumerate(re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text))]


def align_a(text, evidence):
    if not isinstance(evidence, str) or not evidence:
        return {"status": "invalid_evidence", "intervals": []}
    starts = [m.start() for m in re.finditer(re.escape(evidence), text)]
    return {"status": "exact" if len(starts) == 1 else "ambiguous" if starts else "unresolved",
            "intervals": [{"start": start, "end": start + len(evidence)} for start in starts]}


def convert(claims, text, sdk=None, prefix_length=0):
    converted, decisions = [], []
    for index, raw in enumerate(claims):
        if not isinstance(raw, dict):
            decisions.append({"index": index, "error": "claim_not_object", "raw": raw})
            converted.append(raw)
            continue
        normalized, changes = normalize(raw)
        converted.append(normalized)
        alignment = align_a(text, normalized.get("evidence_text"))
        if sdk is not None:
            extraction = sdk[index]
            interval = extraction.char_interval
            alignment["sdk_status"] = getattr(extraction.alignment_status, "value", None)
            alignment["sdk_input_interval"] = dataclasses.asdict(interval) if interval else None
            shifted = None
            if interval and interval.start_pos is not None and interval.end_pos is not None:
                shifted = {"start": interval.start_pos - prefix_length,
                           "end": interval.end_pos - prefix_length}
            alignment["sdk_source_interval"] = shifted
            alignment["sdk_interval_verbatim"] = bool(
                shifted and 0 <= shifted["start"] <= shifted["end"] <= len(text)
                and text[shifted["start"]:shifted["end"]] == normalized["evidence_text"])
        missing = [field for field in FIELDS if field not in raw]
        decisions.append({"index": index, "raw_claim": raw, "normalized_claim": normalized,
                          "normalization_changes": changes, "missing_raw_fields": missing,
                          "source_alignment": alignment})
    return converted, decisions


def run_a(case, instructions, config):
    trace = ExtractionTrace(HERE / "a_traces", {"case_id": case["id"], "cache_policy": "bypass",
                                              "context_boundaries": boundary_spans(case["text"])})
    example = {"cases": [{"id": "fictional_example", "claims": [EXAMPLE_CLAIM]}]}
    system = (instructions + "\nReturn ONLY JSON: {\"cases\":[{\"id\":\"input ID\","
              "\"claims\":[{\"subject\":...,\"location\":...,\"year\":...,"
              "\"outcome\":...,\"value\":...,\"unit\":...,\"qualifier\":...,"
              "\"evidence_text\":...}]}]}. An empty result uses claims: [].\n"
              "Unrelated fictional example input:\nInput ID: fictional_example\n\n"
              + EXAMPLE_TEXT + "\nExample output:\n" + json.dumps(example))
    meta = {}
    parsed = call_ollama_json(config["base_url"], config["model"], system, common_input(case),
                             temperature=SETTINGS["temperature"], max_retries=0,
                             timeout=SETTINGS["timeout_seconds"], num_ctx=SETTINGS["num_ctx"],
                             seed=SETTINGS["seed"], num_predict=SETTINGS["num_predict"],
                             deadline_seconds=SETTINGS["timeout_seconds"], meta_out=meta, trace=trace)
    write_json(HERE / "a_parsed" / (case["id"] + ".json"), {"parsed": parsed, "meta": meta})
    if not isinstance(parsed, dict) or parsed.get("_deadline_exceeded"):
        trace.finish("failed")
        raise RuntimeError("ResearchIQ invocation failed or exceeded deadline")
    if meta.get("done_reason") != "stop":
        trace.finish("failed")
        raise RuntimeError("Incomplete generation: " + str(meta.get("done_reason")))
    entries = parsed.get("cases")
    if not isinstance(entries, list) or len(entries) != 1 or entries[0].get("id") != case["id"]:
        trace.finish("failed")
        raise ValueError("Case wrapper does not match input ID")
    claims = entries[0].get("claims")
    if not isinstance(claims, list):
        trace.finish("failed")
        raise ValueError("claims is not an array")
    out, decisions = convert(claims, case["text"])
    trace.emit("study_claims", {"claims": out, "conversion": decisions})
    trace.finish("completed")
    return out, decisions


def run_b(case, instructions, config):
    example = data.ExampleData(
        text="Input ID: fictional_example\n\n" + EXAMPLE_TEXT,
        extractions=[data.Extraction(extraction_class="claim", extraction_text=EXAMPLE_TEXT,
                                     attributes={k: v for k, v in EXAMPLE_CLAIM.items() if k != "evidence_text"})])
    provider = OllamaLanguageModel(
        model_id=config["model"], model_url=config["base_url"],
        timeout=SETTINGS["timeout_seconds"], temperature=SETTINGS["temperature"],
        seed=SETTINGS["seed"], num_ctx=SETTINGS["num_ctx"],
        max_output_tokens=SETTINGS["num_predict"], top_k=SETTINGS["top_k"],
        top_p=SETTINGS["top_p"], repeat_penalty=SETTINGS["repeat_penalty"])
    description = (instructions + "\nUse extraction_class claim for each study-level record. "
                   "extraction_text is the exact evidence_text; attributes contain subject, "
                   "location, year, outcome, value, unit, qualifier. Use null for unsupported "
                   "location/year, numeric year/value, and an empty extractions array if none.")
    result = lx.extract(
        text_or_documents=common_input(case), prompt_description=description,
        examples=[example], model=provider, max_char_buffer=20000,
        temperature=SETTINGS["temperature"], batch_length=1, max_workers=1,
        use_schema_constraints=False, extraction_passes=1, context_window_chars=None,
        resolver_params={"format_handler": OLLAMA_FORMAT_HANDLER, "suppress_parse_errors": False},
        show_progress=False, fetch_urls=False)
    sdk = result.extractions or []
    write_json(HERE / "b_sdk" / (case["id"] + ".json"),
               {"document_id": case["id"], "text": result.text,
                "extractions": [dataclasses.asdict(extraction) for extraction in sdk]})
    claims = []
    for extraction in sdk:
        if not isinstance(extraction.attributes, dict):
            raise ValueError("LangExtract claim attributes are not an object")
        claims.append({**extraction.attributes, "evidence_text": extraction.extraction_text})
    return convert(claims, case["text"], sdk=sdk,
                   prefix_length=len(common_input(case)) - len(case["text"]))


def completion(record):
    if "raw_response_text" in record:
        try:
            return json.loads(record["raw_response_text"])
        except ValueError:
            return {}
    for line in reversed(record.get("raw_response_lines", [])):
        try:
            chunk = json.loads(line)
            if chunk.get("done"):
                return chunk
        except ValueError:
            pass
    return {}


def main():
    if (HERE / "finalized.json").exists():
        raise SystemExit("This single-pass run is already finalized; use a new run directory for repeats.")
    config = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))["llm"]
    assert config["provider"] == "ollama"
    inputs = HERE / "model_inputs"
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(inputs.glob("*.json"))]
    assert len(cases) == 7
    manifest = json.loads((HERE / "input_manifest.json").read_text(encoding="utf-8"))
    for case, expected in zip(cases, manifest["cases"]):
        assert case["id"] == expected["id"]
        assert hashlib.sha256(case["text"].encode("utf-8")).hexdigest() == expected["sha256"]
    instructions = (inputs / "instructions.txt").read_text(encoding="utf-8") + EXTRA_INSTRUCTIONS
    write_json(HERE / "common_task.json", {"instructions": instructions,
                                         "fictional_example_text": EXAMPLE_TEXT,
                                         "fictional_example_claim": EXAMPLE_CLAIM})
    frozen = {name: sha(HERE / name) for name in ("normalize.py", "NORMALIZATION.md", "run_experiment.py", "wiretap.py")}
    inspected_files = {"ollama_provider": Path(inspect.getfile(OllamaLanguageModel)),
                       "extraction_sdk": Path(lx.__file__).parent / "extraction.py"}
    sdk_snapshot = HERE / "sdk_inspection"
    sdk_snapshot.mkdir(exist_ok=True)
    for name, path in inspected_files.items():
        (sdk_snapshot / (name + ".py")).write_bytes(path.read_bytes())
    info = {"status": "running", "python": sys.version, "python_executable": sys.executable,
            "langextract": metadata.version("langextract"), "settings_requested": SETTINGS,
            "configured_llm": config, "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "model_before": requests.get(config["base_url"] + "/api/tags", timeout=10).json(),
            "ollama_version": requests.get(config["base_url"] + "/api/version", timeout=10).json(),
            "frozen_sha256": frozen, "examples": 1, "cache": "client cache bypass; server KV reuse not cleared",
            "timeout_limitations": "A: 240s inline streamed deadline and read-gap timeout; B: 240s nonstreaming requests timeout, no SDK total-duration guard",
            "provider_support": {"temperature": True, "seed": True, "context": True, "output_budget": True,
                                 "strict_output_schema": False},
            "input_directory": str(inputs), "evaluation_input_paths": [], "runs": []}
    write_json(HERE / "run_manifest.json", info)
    outputs = {"a": {"cases": []}, "b": {"cases": []}}
    start_total = time.perf_counter()
    with Wiretap(HERE / "http", config["base_url"]) as tap:
        tap.label = "warmup"
        warm_start = time.perf_counter()
        warm = call_ollama_json(config["base_url"], config["model"],
                                'You are a JSON echo service. Reply with exactly {"ok": true}.',
                                "An unrelated brass bell rings once.", temperature=0.0, seed=42,
                                max_retries=0, timeout=60, deadline_seconds=60,
                                num_ctx=8192, num_predict=4096)
        info["warmup"] = {"elapsed_s": time.perf_counter() - warm_start, "parsed": warm,
                          "requests": len(tap.records)}
        if warm != {"ok": True}:
            raise RuntimeError("Warmup failed")
        for index, case in enumerate(cases):
            order = ("a", "b") if index % 2 == 0 else ("b", "a")
            for candidate in order:
                tap.label = candidate + "_" + case["id"]
                before = len(tap.records)
                start = time.perf_counter()
                run = {"candidate": candidate, "case_id": case["id"], "case_order": list(order),
                       "sha256": manifest["cases"][index]["sha256"], "error": None}
                try:
                    claims, decisions = (run_a if candidate == "a" else run_b)(case, instructions, config)
                except Exception as error:
                    claims, decisions = [], []
                    run["error"] = {"type": type(error).__name__, "message": str(error),
                                    "traceback": traceback.format_exc()}
                run["elapsed_s"] = time.perf_counter() - start
                records = tap.records[before:]
                run["request_count"] = len(records)
                run["completions"] = [{"request_index": record["index"],
                                       "done_reason": completion(record).get("done_reason"),
                                       "prompt_eval_count": completion(record).get("prompt_eval_count"),
                                       "eval_count": completion(record).get("eval_count"),
                                       "effective_options": (record.get("payload") or {}).get("options")}
                                      for record in records]
                if not run["error"] and any(c["done_reason"] != "stop" for c in run["completions"]):
                    run["error"] = {"type": "IncompleteGeneration", "message": "Completion reason is not stop"}
                    claims = []
                run["claim_count"] = len(claims)
                outputs[candidate]["cases"].append({"id": case["id"], "claims": claims})
                write_json(HERE / "conversion" / (candidate + "_" + case["id"] + ".json"), decisions)
                info["runs"].append(run)
                write_json(HERE / "run_manifest.json", info)
                print(json.dumps({k: run[k] for k in ("candidate", "case_id", "elapsed_s", "claim_count", "request_count", "error")}), flush=True)
        info["http_request_count_including_warmup"] = len(tap.records)
    for candidate in ("a", "b"):
        outputs[candidate]["cases"].sort(key=lambda case: case["id"])
        write_json(HERE / (candidate + "_output.json"), outputs[candidate])
    info["total_wall_seconds_including_warmup"] = time.perf_counter() - start_total
    info["model_after"] = requests.get(config["base_url"] + "/api/tags", timeout=10).json()
    info["status"] = "finalized_before_evaluation"
    write_json(HERE / "run_manifest.json", info)
    assert all(sha(HERE / name) == digest for name, digest in frozen.items())
    write_json(HERE / "finalized.json", {"status": info["status"],
                                        "output_sha256": {name: sha(HERE / name) for name in ("a_output.json", "b_output.json")},
                                        "frozen_sha256": frozen, "gold_loaded": False})
    print("Both outputs finalized; evaluator and gold have not been loaded.", flush=True)


if __name__ == "__main__":
    main()
