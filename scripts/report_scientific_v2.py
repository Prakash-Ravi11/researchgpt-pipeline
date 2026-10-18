"""Reconcile actual Phase 12 artifacts without rerunning models or filling missing evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evaluation.evidence_v2 import latency,promotion_gates

def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []
def reconcile(root):
    manifest=read(root/"manifest.json")
    observed=lines(root/"timing.jsonl")
    if len(observed)!=60 or len({(r["paper_id"],r["arm"]) for r in observed})!=60:
        raise ValueError("All 60 unique arms are required; missing executions cannot be reconstructed")
    corpus=read(root.parent/"baseline/corpus.json")["corpus"]
    ids={r["paper_id"] for r in corpus}
    if {(r["paper_id"],r["arm"]) for r in observed}!={(pid,arm) for pid in ids for arm in ("baseline","current")}:
        raise ValueError("Observed arms do not match the frozen corpus")
    expected={"temperature":0.0,"seed":42,"num_ctx":8192,"num_predict":2048,
              "top_k":40,"top_p":0.9,"repeat_penalty":1.1}
    requests=[];mismatch=[];stages=[];completions=Counter();token_counts=Counter();unknown=Counter();host_states=Counter()
    for row in observed:
        pid,arm=row["paper_id"],row["arm"];folder=root/pid/arm
        actual=sorted(folder.rglob("actual_request.json"))
        if len(actual)!=row["recorded_model_requests"]:
            raise ValueError("Recorded request count does not match actual request artifacts")
        for file in actual:
            request=read(file)
            payload=request["payload"]
            options=payload.get("options",{})
            if payload.get("model")!=manifest["model"]["model"] or any(options.get(k)!=v for k,v in expected.items()):
                mismatch.append(str(file))
            host=read(file.parent/"host_result.json")
            host_state=("request_hard_timeout" if host.get("hard_timeout") else
                        "host_recorded_response" if host.get("parsed") is not None else "host_recorded_without_parsed_response") if host else "no_host_result_artifact"
            host_states[(arm,host_state)]+=1
            requests.append({"paper_id":pid,"arm":arm,"path":str(file),"host_state":host_state,
                "sha256":hashlib.sha256(file.read_bytes()).hexdigest(),"options":options})
        by_path={str(Path(c["path"]).resolve()):c for c in row.get("completion_records",[])}
        for request_file in actual:
            completion=by_path.get(str((request_file.parent/"raw_response.ndjson").resolve()),{})
            reason=completion.get("done_reason") or "no_final_done_event"
            completions[(arm,reason)]+=1
            for field in ("prompt_eval_count","eval_count"):
                value=completion.get(field)
                if value is None:unknown[(arm,field)]+=1
                else:token_counts[(arm,field)]+=value
        returned=read(folder/"returned.json")
        result=read(folder/"extraction/result.json") if arm=="current" else read(folder/"gated.json")
        source=read(folder/"extraction/parse/parsed.json") if arm=="current" else None
        before=lines(folder/"extraction/facts_before_model.jsonl") if arm=="current" else []
        decisions=lines(folder/"extraction/decisions.jsonl") if arm=="current" else []
        decision_scope="final"
        if arm=="current" and not decisions:
            decisions=lines(folder/"extraction/decisions_before_model.jsonl")
            decision_scope="before_model_checkpoint"
        candidates=source.get("candidates",[]) if source else []
        bijection=(len({d["candidate_id"] for d in decisions})==len(decisions)==len(candidates) and
                   {d["candidate_id"] for d in decisions}=={c["id"] for c in candidates}) if source else None
        residency=read(folder/"model_residency_before.json")
        stages.append({"paper_id":pid,"arm":arm,"state":row["state"],
            "model_resident_before":bool(residency.get("models")) if residency is not None else None,
            "source_candidates":len(candidates) if source else None,
            "numeric_source_candidates":sum(c["kind"]=="numeric" for c in candidates) if source else None,
            "host_numeric_facts_before_model":sum(f["kind"]=="numeric" for f in before) if arm=="current" else None,
            "host_qualitative_quotations_before_model":sum(f["kind"]=="qualitative" for f in before) if arm=="current" else None,
            "returned_record_exists":returned is not None,
            "returned_results_text_present":bool(returned.get("results")) if returned is not None else None,
            "returned_numeric_rows":len(returned.get("quantitative_results",[])) if returned is not None else None,
            "returned_qualitative_quotations":len(returned.get("qualitative_results",[])) if returned is not None else None,
            "candidate_accounting_bijection":bijection,"decision_scope":decision_scope,
            "decision_states":dict(Counter(d["state"] for d in decisions)),
            "semantic_complete":result.get("coverage",{}).get("semantic_complete") if result and arm=="current" else None})
    timing={arm:latency([{**r,"elapsed_seconds":r["host_elapsed_seconds"]} for r in observed if r["arm"]==arm])
            for arm in ("baseline","current")}
    partitions={arm:{state:latency([{**r,"elapsed_seconds":r["host_elapsed_seconds"]} for r in observed
                        if r["arm"]==arm and next(s for s in stages if s["paper_id"]==r["paper_id"] and s["arm"]==arm)["model_resident_before"]==resident])
                for state,resident in (("model_resident_before",True),("model_not_resident_before",False))}
                for arm in ("baseline","current")}
    gates=promotion_gates({"precision":None,"exact_tuple_recall":None},
                          {"precision":None,"exact_tuple_recall":None},fixtures=None,preservation=None)
    gates["gates"]["processing_complete"]={"verdict":"PASS" if all(
        s["semantic_complete"] is True for s in stages if s["arm"]=="current") else "FAIL",
        "reason":"Partial and timed-out papers remain eligible; no completeness is inferred from valid JSON or more cells"}
    for field in ("uncached_p50","uncached_p95"):
        gates["gates"][field]={"verdict":"NOT MEASURED","reason":
            "Equal independently correct coverage is unavailable; measured PDF-to-output timing excludes acquisition/index/retrieval/browser"}
    gates["eligible_for_promotion"]=False
    return {"manifest":manifest,"completed_unique_arms":len(observed),"timing":timing,
        "timing_by_model_residency":partitions,"model_settings_match_all_recorded_requests":not mismatch,
        "settings_mismatches":mismatch,"request_counts":dict(Counter(r["arm"] for r in requests)),
        "completion_counts":{str(k):v for k,v in completions.items()},
        "host_request_state_counts":{str(k):v for k,v in host_states.items()},
        "known_token_counter_totals":{str(k):v for k,v in token_counts.items()},
        "requests_missing_token_counters":{str(k):v for k,v in unknown.items()},
        "memory":{"process_peak_working_set_bytes":{arm:max((r["peak_working_set_bytes"] for r in observed if r["arm"]==arm and r.get("peak_working_set_bytes") is not None),default=None)
                  for arm in ("baseline","current")},"measured_worker_count":{arm:sum(r.get("peak_working_set_bytes") is not None for r in observed if r["arm"]==arm) for arm in ("baseline","current")},
                  "scope":"Worker counters only where measured; model service/GPU peak and killed-worker peak are unavailable"},
        "independent_precision":None,"independent_recall":None,"stages":stages,"requests":requests,**gates}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError("Choose a fresh report path")
    report=reconcile(args.run.resolve());args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("completed_unique_arms","timing","request_counts",
        "model_settings_match_all_recorded_requests","eligible_for_promotion")}))
if __name__=="__main__":main()
