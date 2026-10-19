"""Bounded before/after v2 PDF-to-API controls; no promotion accuracy inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evidence.v2.runtime import terminate_owned
from src.evidence.v2.store import project_from_directory
from src.evaluation.evidence_v2 import latency
from scripts.evaluate_scientific_end_to_end_v2 import completion_records


def read(p):return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2),encoding="utf-8")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_code(directory,hashes):
    if any(sha(directory/name)!=value for name,value in hashes.items()):raise ValueError("Frozen code snapshot changed")
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("before-code","selection","corpus","model-config","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args();args.output=args.output.resolve();before=args.before_code.resolve()
    if args.output.exists() or ROOT/".run" not in args.output.parents:raise ValueError("Use fresh isolated outputs")
    selection=read(args.selection);hashes=read(args.selection.parent/"before-code-hashes.json")
    verify_code(before,hashes)
    sources={r["paper_id"]:r for r in read(args.corpus)["corpus"]}
    ids=selection["preselected_paired_controls"];model=read(args.model_config)
    import requests
    tags=requests.get(model["base_url"]+"/api/tags",timeout=5).json()
    matches=[m for m in tags["models"] if m["name"]==model["model"]]
    if len(matches)!=1 or matches[0]["digest"]!=model["model_digest"]:raise ValueError("Model digest changed")
    for pid in ids:
        if sha(Path(sources[pid]["path"]))!=sources[pid]["source_sha256"]:raise ValueError("Source changed")
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip():raise ValueError("Commit reviewed code before control execution")
    manifest={"scope":"uncached_v2_PDF_to_API_projection_before_after_preflight","selected_papers":ids,
        "before_SHA":selection["resume_base_SHA"],"after_SHA":head,"model":model,
        "limits":selection["control_limits"],"order":"alternating by paper","application_cache":"fresh, no acceptance cache",
        "scope_excludes":["acquisition","embedding/index","dense retrieval","browser"],
        "independent_accuracy":"NOT MEASURED","default_feature_enabled":False,
        "frozen_snapshot_files":len(hashes),"code_directories":{"before":str(before),"after":str(ROOT)},
        "note":"Snapshot file hashes establish before code identity; Git discovery inside an archive may find its containing checkout"}
    write(args.output/"manifest.json",manifest);rows=[]
    for i,pid in enumerate(ids):
        source=sources[pid]
        for arm in (["before","after"] if i%2==0 else ["after","before"]):
            folder=args.output/pid/arm;code=before if arm=="before" else ROOT
            state=requests.get(model["base_url"]+"/api/ps",timeout=5).json();write(folder/"model_residency_before.json",state)
            command=[sys.executable,"-B",str(ROOT/"scripts/evaluate_scientific_end_to_end_v2.py"),"--worker","--arm","current",
                "--code-root",str(code),"--source",source["path"],"--paper-id",pid,
                "--model-config",str(args.model_config.resolve()),"--output",str(folder)]
            write(folder/"launch.json",{"command":command,"code_SHA":manifest[arm+"_SHA"],"source_sha256":source["source_sha256"]})
            env={**os.environ,"PYTHONPATH":str(code),"PYTHONDONTWRITEBYTECODE":"1","HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1"}
            started=time.monotonic();child=subprocess.Popen(command,cwd=code,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            timed_out=False
            try:stdout,stderr=child.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                timed_out=True;terminate_owned(child);stdout,stderr=child.communicate()
            (folder/"stdout.log").write_bytes(stdout);(folder/"stderr.log").write_bytes(stderr)
            worker_returned=read(folder/"returned.json")
            # Both arms use the already implemented strict reader, including actual
            # checkpoint recovery. Missing worker outputs remain explicitly missing.
            projected=project_from_directory({"paper_id":pid},{"document_sha256":source["source_sha256"]},folder/"extraction")
            write(folder/"api_returned.json",projected)
            actual=sorted(folder.rglob("actual_request.json"));mismatches=[]
            expected={"temperature":0.0,"seed":42,"num_ctx":8192,"num_predict":2048,"top_k":40,"top_p":0.9,"repeat_penalty":1.1}
            for f in actual:
                payload=read(f)["payload"]
                if payload["model"]!=model["model"] or any(payload["options"].get(k)!=v for k,v in expected.items()):mismatches.append(str(f))
            if mismatches:raise ValueError("Request settings differ")
            row={"paper_id":pid,"arm":arm,"state":"timeout" if timed_out else "error" if child.returncode else "partial",
                "partial":not projected["scientific_extraction"]["coverage"].get("semantic_complete",False),
                "elapsed_seconds":time.monotonic()-started,"worker_exit_code":child.returncode,
                "direct_worker_returned_record_exists":worker_returned is not None,
                "api_numeric_records":len(projected["quantitative_results"]),"api_qualitative_quotations":len(projected["qualitative_results"]),
                "coverage":projected["scientific_extraction"]["coverage"],"requests":len(actual),
                "completion_records":completion_records(folder),"model_resident_before":bool(state.get("models")),
                "fact_identities":[f["id"] for f in projected["scientific_facts"]]}
            write(folder/"observed.json",row);rows.append(row);write(args.output/"running.json",rows)
            print(pid,arm,row["state"],round(row["elapsed_seconds"],3),"requests",len(actual),flush=True)
    verify_code(before,hashes);preservation=[]
    for pid in ids:
        a=read(args.output/pid/"before/api_returned.json");b=read(args.output/pid/"after/api_returned.json")
        old={f["id"]:f for f in a["scientific_facts"]};new={f["id"]:f for f in b["scientific_facts"]}
        preservation.append({"paper_id":pid,"all_before_facts_preserved":all(new.get(k)==v for k,v in old.items()),
            "new_fact_ids":sorted(new.keys()-old.keys()),"missing_or_changed_fact_ids":[k for k,v in old.items() if new.get(k)!=v]})
    result={"manifest":manifest,"rows":rows,"timing":{arm:latency([r for r in rows if r["arm"]==arm]) for arm in ("before","after")},
        "request_counts":{arm:sum(r["requests"] for r in rows if r["arm"]==arm) for arm in ("before","after")},
        "preservation":preservation,"frozen_before_code_unchanged":True,
        "eligible_for_promotion":False,"independent_precision_recall_and_correct_tuple_recovery":"NOT MEASURED",
        "note":"Preselected controls show behavior only on these examples; incomplete coverage is not a speed improvement gate"}
    write(args.output/"comparison.json",result)
    print(json.dumps({"timing":result["timing"],"request_counts":result["request_counts"],"preservation":preservation}),flush=True)
if __name__=="__main__":main()
