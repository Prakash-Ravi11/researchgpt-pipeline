"""Experimental all-page path with explicit partial/deferred accounting."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
import time
import uuid
from . import POLICY_VERSION
from .contracts import coverage, verify_document, identity
from .runtime import Config, append_event, cache_key, parse_bounded, write_jsonl
from src.evidence.monitor import atomic_json_write

def strict_response(result, directory):
    if result.get("hard_timeout") or result.get("completion", {}).get("done_reason") != "stop":
        raise ValueError("Incomplete response cannot yield facts")
    raw_path = Path(directory) / "raw_response.ndjson"
    parts = []
    done = False
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("message", {}).get("content"):
            parts.append(event["message"]["content"])
        if event.get("done"):
            done = event.get("done_reason") == "stop"
    if not done:
        raise ValueError("No successful raw completion")
    value = json.loads("".join(parts))
    if not isinstance(value, dict):
        raise ValueError("Expected one complete response object")
    return value

def extract(source, paper_id, output, *, config=Config(), model=None):
    if not config.enabled:
        return {"enabled": False, "state": "disabled", "facts": [], "requests": []}
    folder = Path(output)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("Use a new output directory; frozen runs cannot be overwritten")
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    run_id = uuid.uuid4().hex
    for name in ("requests","raw_responses","adjudication"):
        write_jsonl(folder/(name+".jsonl"), [])
    import hashlib, subprocess
    try:
        commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
        dirty=hashlib.sha256(subprocess.check_output(["git","diff","--binary"])).hexdigest()
    except (OSError,subprocess.CalledProcessError):
        commit,dirty=None,None
    atomic_json_write(folder/"manifest.json", {"code_commit":commit,"dirty_diff_sha256":dirty,
        "source_sha256":hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "paper_id":paper_id,"config":asdict(config),"model":model,"policy":POLICY_VERSION,
        "mode":"experimental","external_document_transmission":False})
    append_event(folder/"execution.jsonl", {"event": "run_started", "run_id": run_id,
                                           "config": asdict(config), "model": model})
    document, error = parse_bounded(source, paper_id, folder/"parse",
                                   min(config.parser_seconds, config.document_seconds))
    if document is None:
        result = {"enabled": True, "state": "partial", "policy_version": POLICY_VERSION,
            "run_id": run_id, "facts": [], "requests": [],
            "coverage": {"processing_complete": False, "source_inventory_unavailable": True,
                         "reason": error, "eligible_target_denominator_must_be_retained": True}}
        atomic_json_write(folder/"result.json", result)
        return result
    result = interpret(document, folder, config=config, model=model, run_id=run_id, started=started)
    return result

def interpret(document, folder, *, config=Config(enabled=True), model=None, run_id=None, started=None):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic() if started is None else started
    run_id = run_id or uuid.uuid4().hex
    verify_document(document)
    key=cache_key(document,model,config)
    cache=Path(config.cache_directory)/key/"complete.json" if config.cache_directory else None
    if cache is not None and cache.is_file():
        payload=json.loads(cache.read_text(encoding="utf-8"))
        previous=payload["result"]
        if (payload["key"]==key and payload.get("result_sha256")==identity(previous)
                and previous["coverage"]["semantic_complete"] and identity(payload["document"])==identity(document)):
            result={**previous,"run_id":run_id,"requests":[],"cache_hit":True,
                    "cache_origin_run":previous["run_id"],"elapsed_seconds":time.monotonic()-started}
            for name,rows in [("source_units",document["units"]),("table_structures",document["tables"]),
                              ("facts",result["facts"]),("decisions",payload["decisions"]),("packets",[])]:
                write_jsonl(folder/(name+".jsonl"),rows)
            atomic_json_write(folder/"coverage.json",result["coverage"])
            atomic_json_write(folder/"result.json",result)
            atomic_json_write(folder/"seal.json",{"result_sha256":identity(result)})
            append_event(folder/"execution.jsonl",{"event":"complete_cache_reused","key":key,
                "new_model_requests":0,"original_run":previous["run_id"]})
            return result
    from .host import build_host_checkpoint
    facts, decisions, packets = build_host_checkpoint(document)
    # Persist host results before optional model work; a killed worker leaves genuine partial evidence.
    for name,rows in [("source_units",document["units"]),("table_structures",document["tables"]),
                      ("packets",packets),("facts_before_model",facts),("decisions_before_model",decisions)]:
        write_jsonl(folder/(name+".jsonl"),rows)
    atomic_json_write(folder/"partial_checkpoint.json",{"state":"model_pending","run_id":run_id,
        "source_sha256":document["source_sha256"],"fact_count":len(facts),"candidate_count":len(decisions),
        "processing_complete":False,"semantic_complete":False})
    # Semantic packets are explicit unresolved work until the optional local proposer validates them.
    from .semantic import resolve_packets
    semantic_facts, requests, semantic_errors = resolve_packets(document, packets, folder,
        config=config, model=model, deadline=started + config.document_seconds)
    from .semantic import resolve_prose
    prose_facts,prose_requests,prose_errors=resolve_prose(document,folder,config=config,model=model,
        deadline=started+config.document_seconds,request_offset=len(requests))
    requests.extend(prose_requests)
    semantic_errors.extend(prose_errors)
    facts.extend(prose_facts)
    facts.extend(semantic_facts)
    facts = list({fact["id"]: fact for fact in facts}.values())
    accepted_units = {f["source_lineage"]["value"]: f for f in semantic_facts if "value" in f["source_lineage"]}
    for candidate, decision in zip(document["candidates"], decisions):
        if candidate["unit_id"] in accepted_units:
            f = accepted_units[candidate["unit_id"]]
            decision.update(state="processed", reason="host_validated_model_relation", fact_ids=[f["id"]])
    for fact in prose_facts:
        occurrences=fact["source_lineage"].get("native_occurrences",[])
        for candidate,decision in zip(document["candidates"],decisions):
            if candidate["kind"]=="numeric" and any(o["block_id"]==candidate["unit_id"] and
                    o["start"]<=candidate["start"]<o["end"] for o in occurrences):
                decision.update(state="processed",reason="source_supported_prose_relation",fact_ids=[fact["id"]])
    exhausted = time.monotonic() >= started + config.document_seconds
    for decision in decisions:
        if decision["state"] == "unresolved" and (exhausted or semantic_errors):
            decision.update(state="deferred", reason="document_deadline" if exhausted else semantic_errors[0])
    counts = coverage(document, decisions)
    result = {"enabled": True, "policy_version": POLICY_VERSION, "run_id": run_id,
        "paper_id": document["paper_id"], "source_sha256": document["source_sha256"], "representation_id": document["representation_id"],
        "facts": facts, "requests": requests, "coverage": counts,
        "state": "complete" if counts["semantic_complete"] else "partial",
        "elapsed_seconds": time.monotonic()-started, "cache_key": cache_key(document, model, config)}
    for name, rows in [("source_units", document["units"]), ("table_structures", document["tables"]),
                       ("packets", packets), ("facts", facts), ("decisions", decisions)]:
        write_jsonl(folder/(name+".jsonl"), rows)
    atomic_json_write(folder/"coverage.json", counts)
    append_event(folder/"timing.jsonl", {"stage":"host_interpretation", "elapsed_seconds":time.monotonic()-started,
        "model_calls":len(requests), "cache_reuse":False, "partial":not counts["semantic_complete"]})
    atomic_json_write(folder/"result.json", result)
    atomic_json_write(folder/"seal.json", {"result_sha256": identity(result)})
    if cache is not None and counts["semantic_complete"]:
        atomic_json_write(cache,{"key":key,"document":document,"result":result,"result_sha256":identity(result),"decisions":decisions})
    append_event(folder/"execution.jsonl", {"event": "run_completed", "run_id": run_id,
        "state": result["state"], "elapsed_seconds": result["elapsed_seconds"],
        "cache_reuse": False, "model_requests": len(requests)})
    return result
