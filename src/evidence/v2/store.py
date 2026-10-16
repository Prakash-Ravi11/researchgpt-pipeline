"""Configuration-selected host result sidecars; model flags never enable v2."""
import json
from pathlib import Path
from . import POLICY_VERSION
from .contracts import identity
from .output import project_record

def project_from_store(record, raw, directory):
    target=Path(directory).resolve()/identity({"paper_id":record["paper_id"]})/"result.json"
    empty={"enabled":True,"policy_version":POLICY_VERSION,"run_id":None,
           "source_sha256":raw.get("document_sha256"),"facts":[],
           "coverage":{"processing_complete":False},"state":"deferred","reason":"scientific_sidecar_missing"}
    if not target.is_file():return project_record(record,empty)
    try:
        result=json.loads(target.read_text(encoding="utf-8"))
        seal=json.loads((target.parent/"seal.json").read_text(encoding="utf-8"))
        if identity(result)!=seal["result_sha256"]:raise ValueError("Changed sidecar")
        if not raw.get("document_sha256") or result["source_sha256"]!=raw["document_sha256"]:
            raise ValueError("Wrong source version")
        if result["policy_version"]!=POLICY_VERSION or result.get("paper_id")!=record["paper_id"]:
            raise ValueError("Wrong policy or paper")
        if result.get("enabled") is not True:raise ValueError("Disabled extraction")
        return project_record(record,result)
    except (OSError,ValueError,KeyError,TypeError):
        empty["reason"]="scientific_sidecar_identity_or_integrity_failure"
        return project_record(record,empty)
