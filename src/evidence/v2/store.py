"""Configuration-selected host result sidecars; model flags never enable v2."""
import json
from pathlib import Path
from . import POLICY_VERSION
from .contracts import identity, coverage
from .output import project_record

def project_from_store(record, raw, directory):
    return project_from_directory(record, raw, Path(directory).resolve()/identity({"paper_id":record["paper_id"]}))


def project_from_directory(record, raw, directory):
    """Read a completed sidecar or a strictly revalidated pre-model checkpoint."""
    target=Path(directory)/"result.json"
    empty={"enabled":True,"policy_version":POLICY_VERSION,"run_id":None,
           "source_sha256":raw.get("document_sha256"),"facts":[],
           "coverage":{"processing_complete":False},"state":"deferred","reason":"scientific_sidecar_missing"}
    try:
        if not target.is_file():
            if not (target.parent/"partial_checkpoint.json").is_file():
                return project_record(record,empty)
            return project_record(record, recover_checkpoint(record,raw,target.parent))
        result=json.loads(target.read_text(encoding="utf-8"))
        seal=json.loads((target.parent/"seal.json").read_text(encoding="utf-8"))
        if identity(result)!=seal["result_sha256"]:raise ValueError("Changed sidecar")
        if not raw.get("document_sha256") or result["source_sha256"]!=raw["document_sha256"]:
            raise ValueError("Wrong source version")
        if result["policy_version"]!=POLICY_VERSION or result.get("paper_id")!=record["paper_id"]:
            raise ValueError("Wrong policy or paper")
        if result.get("enabled") is not True:raise ValueError("Disabled extraction")
        return project_record(record,result)
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        empty["reason"]="scientific_sidecar_identity_or_integrity_failure"
        return project_record(record,empty)


def recover_checkpoint(record, raw, folder):
    """Recover only facts that the recorded source still yields under host rules.

    This never reads partial model responses or replaces an invalid final result.
    It does not write back to the extraction directory or claim completion.
    """
    from .host import build_host_checkpoint
    def read(name):
        return json.loads((folder/name).read_text(encoding="utf-8"))
    def lines(name):
        return [json.loads(line) for line in (folder/name).read_text(encoding="utf-8").splitlines()]
    checkpoint=read("partial_checkpoint.json")
    manifest=read("manifest.json")
    document=read("parse/parsed.json")
    expected=raw.get("document_sha256")
    if (not expected or checkpoint["state"]!="model_pending"
            or checkpoint["source_sha256"]!=expected
            or manifest["source_sha256"]!=expected or document["source_sha256"]!=expected
            or manifest["paper_id"]!=record["paper_id"] or document["paper_id"]!=record["paper_id"]
            or manifest["policy"]!=POLICY_VERSION or manifest["config"]["enabled"] is not True
            or checkpoint["processing_complete"] is not False or checkpoint["semantic_complete"] is not False):
        raise ValueError("Checkpoint identity or state mismatch")
    started=[e for e in lines("execution.jsonl") if e.get("event")=="run_started"]
    if len(started)!=1 or started[0]["run_id"]!=checkpoint["run_id"]:
        raise ValueError("Checkpoint run mismatch")
    facts, decisions, _=build_host_checkpoint(document)
    if (identity(facts)!=identity(lines("facts_before_model.jsonl"))
            or identity(decisions)!=identity(lines("decisions_before_model.jsonl"))
            or checkpoint["fact_count"]!=len(facts) or checkpoint["candidate_count"]!=len(decisions)):
        raise ValueError("Checkpoint does not reproduce host decisions")
    for decision in decisions:
        if decision["state"]=="unresolved":
            decision.update(state="deferred",reason="model_work_not_finalized")
    counts=coverage(document,decisions)
    counts.update(processing_complete=False,semantic_complete=False)
    return {"enabled":True,"policy_version":POLICY_VERSION,"run_id":checkpoint["run_id"],
        "paper_id":record["paper_id"],"source_sha256":expected,"facts":facts,"coverage":counts,
        "state":"partial","reason":"revalidated_host_checkpoint_model_work_incomplete"}
