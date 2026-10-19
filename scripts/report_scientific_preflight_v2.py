"""Reconcile bounded preflight controls from actual artifacts; no model calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evaluation.evidence_v2 import FIELDS,latency


def read(p):return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
def snapshot(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
def reconcile(root):
    original=snapshot(root);comparison=read(root/"comparison.json");manifest=comparison["manifest"]
    ids=manifest["selected_papers"];rows=comparison["rows"]
    if len(rows)!=2*len(ids) or {(r["paper_id"],r["arm"]) for r in rows}!={(p,a) for p in ids for a in ("before","after")}:
        raise ValueError("Missing or duplicate actual control executions")
    counts=Counter();tokens=Counter();requests=[];details=[];preservation=[]
    expected={"temperature":0.0,"seed":42,"num_ctx":8192,"num_predict":2048,"top_k":40,"top_p":0.9,"repeat_penalty":1.1}
    for row in rows:
        pid,arm=row["paper_id"],row["arm"];folder=root/pid/arm
        actual=sorted(folder.rglob("actual_request.json"))
        if len(actual)!=row["requests"]:raise ValueError("Actual request count mismatch")
        for path in actual:
            payload=read(path)["payload"]
            if payload["model"]!=manifest["model"]["model"] or any(payload["options"].get(k)!=v for k,v in expected.items()):
                raise ValueError("Model settings mismatch")
            raw=path.parent/"raw_response.ndjson";events=[]
            if raw.is_file():events=[json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
            end=next((e for e in reversed(events) if e.get("done")),{})
            host=read(path.parent/"host_result.json")
            state="host_request_timeout" if host and host.get("hard_timeout") else "host_response_recorded" if host else "no_host_result_after_document_interrupt"
            counts[(arm,state)]+=1;counts[(arm,"request_attempts")]+=1
            counts[(arm,"requests_without_raw_stream_file")]+=int(not raw.is_file())
            counts[(arm,"successful_raw_stop")]+=int(end.get("done_reason")=="stop")
            for key in ("prompt_eval_count","eval_count"):
                if end.get(key) is None:counts[(arm,"requests_with_unknown_"+key)]+=1
                else:tokens[(arm,key)]+=end[key]
            requests.append({"paper_id":pid,"arm":arm,"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "raw_stream_exists":raw.is_file(),"raw_done_reason":end.get("done_reason"),"host_state":state,
                "prompt_eval_count":end.get("prompt_eval_count"),"eval_count":end.get("eval_count")})
        record=read(folder/"api_returned.json");facts=record["scientific_facts"]
        complete=[f for f in facts if f["kind"]=="numeric" and all(f.get(k) is not None for k in FIELDS)]
        cov=record["scientific_extraction"]["coverage"]
        details.append({**{k:row[k] for k in ("paper_id","arm","state","elapsed_seconds","requests","model_resident_before")},
            "numeric_records":len(record["quantitative_results"]),"qualitative_quotations":len(record["qualitative_results"]),
            "structurally_complete_exact_tuples":len(complete),"coverage":cov,
            "direct_worker_returned":row["direct_worker_returned_record_exists"]})
    for pid in ids:
        before=read(root/pid/"before/api_returned.json");after=read(root/pid/"after/api_returned.json")
        a={f["id"]:f for f in before["scientific_facts"]};b={f["id"]:f for f in after["scientific_facts"]}
        preservation.append({"paper_id":pid,"facts_before":len(a),"facts_after":len(b),
            "all_before_facts_preserved":all(b.get(k)==v for k,v in a.items()),"new_fact_ids":sorted(b.keys()-a.keys()),
            "candidate_denominator_unchanged":before["scientific_extraction"]["coverage"]["candidate_total"]==after["scientific_extraction"]["coverage"]["candidate_total"]})
    totals={arm:{field:sum(r[field] for r in details if r["arm"]==arm) for field in ("numeric_records","qualitative_quotations","structurally_complete_exact_tuples")} for arm in ("before","after")}
    if original!=snapshot(root):raise ValueError("Control artifacts changed during reconciliation")
    return {"scope":manifest["scope"],"before_SHA":manifest["before_SHA"],"after_SHA":manifest["after_SHA"],
        "timing":comparison["timing"],"request_attempts":comparison["request_counts"],"counts":{str(k):v for k,v in counts.items()},
        "known_token_totals":{str(k):v for k,v in tokens.items()},
        "timing_by_initial_model_residency":{arm:{label:latency([r for r in details if r["arm"]==arm and r["model_resident_before"]==resident]) for label,resident in (("resident",True),("not_resident",False))} for arm in ("before","after")},
        "totals":totals,"preservation":preservation,"rows":details,"requests":requests,
        "control_files_preserved":len(original),"control_artifact_hashes":original,
        "new_model_requests_for_reconciliation":0,"independent_accuracy":"NOT MEASURED","eligible_for_promotion":False,
        "limits":"Three preselected examples; prior request attempts may have no recorded response or token counters. No inference throughput or equal-correct-coverage promotion gain is established."}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path,required=True);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError("Use a fresh reconciliation output")
    report=reconcile(args.run.resolve());args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("timing","request_attempts","counts","totals","preservation","control_files_preserved")}))
if __name__=="__main__":main()
