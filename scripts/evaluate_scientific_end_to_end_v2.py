"""Bounded paired PDF-to-returned-output evaluation; never treats partial runs as wins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding="utf-8")
    os.replace(temporary,path)
def events(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []
def append(path,row):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:
        f.write(json.dumps(row,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())

def baseline(args,folder,model):
    from src.processing.pdf_parser import process_paper_grounded
    from src.summarization.summarize import _extract_single_paper
    from src.evidence.gate import gate_paper
    from src.evidence.monitor import ExtractionTrace
    import requests
    meta={"paperId":args.paper_id,"title":args.paper_id,"has_full_text":True,
          "pdf_path":str(args.source),"representation_type":"pdf","acquisition_status":"FULL_TEXT"}
    chunks=process_paper_grounded(meta)
    write(folder/"chunks.json",chunks)
    paper={"paper_id":args.paper_id,"title":args.paper_id,"text":"\n".join(c["text"] for c in chunks),
           "_evidence_chunks":chunks,"_source_sha256":hashlib.sha256(args.source.read_bytes()).hexdigest()}
    original=requests.sessions.Session.send
    counter=0
    def observed(session,prepared,**kwargs):
        nonlocal counter
        if prepared.url!=model["base_url"].rstrip("/")+"/api/chat":
            raise RuntimeError("Evaluation permits only the existing local chat endpoint")
        if counter>=6:raise RuntimeError("Frozen six-request cap reached")
        counter+=1
        attempt=folder/"requests"/str(counter)
        write(attempt/"actual_request.json",{"url":prepared.url,"payload":json.loads(prepared.body)})
        append(folder/"requests.jsonl",{"request":counter,"state":"started","payload":json.loads(prepared.body)})
        response=original(session,prepared,**kwargs)
        iterator=response.iter_lines
        def lines(*a,**k):
            k.setdefault("chunk_size",1)
            with (attempt/"raw_response.ndjson").open("w",encoding="utf-8") as stream:
                for line in iterator(*a,**k):
                    decoded=line.decode("utf-8") if isinstance(line,bytes) else line
                    stream.write(decoded+"\n");stream.flush()
                    yield line
        response.iter_lines=lines
        return response
    trace=ExtractionTrace(folder/"trace",{"arm":"baseline","source_sha256":paper["_source_sha256"]})
    llm={**model,"temperature":0.0,"seed":42,"max_context_words":2500,"timeout_seconds":30,
         "extraction_deadline_seconds":30,"extraction_output_reservation":2048,"_diagnostic_trace":trace}
    requests.sessions.Session.send=observed
    try:
        _,record=_extract_single_paper(args.paper_id,paper,llm,{},None)
        write(folder/"extracted.json",record)
        gated=gate_paper(record,chunks,"FULL_TEXT",[])
        write(folder/"gated.json",gated)
        returned={**record,**{k:v for k,v in gated.items() if k!="acquisition_status"},"paper_id":args.paper_id}
        write(folder/"returned.json",returned)
        trace.finish("completed")
    finally:
        requests.sessions.Session.send=original
    return {"state":"partial" if record.get("_extraction_failed") or record.get("_extraction_nonconformant") else "completed",
            "partial":bool(record.get("_extraction_failed") or record.get("_extraction_nonconformant")),
            "candidate_units":len(chunks),"returned_numeric_rows":len(gated.get("quantitative_results",[])),
            "model_requests":counter,"correct_coverage":None,"source_coverage_proven":False}

def worker(args):
    sys.path.insert(0,str(args.code_root))
    folder=args.output;folder.mkdir(parents=True,exist_ok=True)
    model=json.loads(args.model_config.read_text(encoding="utf-8"))
    started=time.monotonic()
    if args.arm=="baseline":
        row=baseline(args,folder,model)
    else:
        from src.evidence.v2.runner import extract
        from src.evidence.v2.runtime import Config
        from src.evidence.v2.output import project_record
        result=extract(args.source,args.paper_id,folder/"extraction",
            config=Config(enabled=True,local_model_enabled=True),model=model)
        returned=project_record({"paper_id":args.paper_id},result)
        write(folder/"returned.json",returned)
        row={"state":result["state"],"partial":result["state"]!="complete","coverage":result["coverage"],
             "returned_numeric_rows":len(returned.get("quantitative_results",[])),
             "returned_qualitative_quotations":len(returned.get("qualitative_results",[])),
             "model_requests":len(result.get("requests",[])),"correct_coverage":None}
    import runpy
    row.update(runpy.run_path(str(ROOT/"src/evidence/v2/resources.py"))["process_memory"]())
    row.update(paper_id=args.paper_id,arm=args.arm,elapsed_seconds=time.monotonic()-started)
    write(folder/"measurement.json",row)

def completion_records(folder):
    records=[]
    for path in folder.rglob("raw_response.ndjson"):
        rows=events(path)
        end=next((r for r in reversed(rows) if r.get("done")),None)
        records.append({"path":str(path),"complete":bool(end),"done_reason":end.get("done_reason") if end else None,
            **{k:end.get(k) if end else None for k in ("prompt_eval_count","eval_count","load_duration",
                "prompt_eval_duration","eval_duration","total_duration")}})
    return records

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker",action="store_true");parser.add_argument("--arm",choices=["baseline","current"])
    parser.add_argument("--code-root",type=Path);parser.add_argument("--source",type=Path);parser.add_argument("--paper-id")
    parser.add_argument("--corpus",type=Path);parser.add_argument("--baseline-code",type=Path)
    parser.add_argument("--model-config",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--paper-ids",nargs="+",help="Explicit calibration subset; full run omits this option")
    args=parser.parse_args()
    if args.worker:return worker(args)
    if args.output.exists():raise ValueError("Choose a fresh paired-run directory")
    args.output.mkdir(parents=True)
    corpus=json.loads(args.corpus.read_text(encoding="utf-8"))
    model=json.loads(args.model_config.read_text(encoding="utf-8"))
    sources=[s for s in corpus["corpus"] if not args.paper_ids or s["paper_id"] in args.paper_ids]
    for item in sources:
        if hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()!=item["source_sha256"]:
            raise ValueError("Frozen source hash mismatch")
    manifest={"scope":"uncached_pdf_to_returned_scientific_output","papers":len(sources),
        "source_manifest_sha256":hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
        "code_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "model":model,"baseline_sha":"18af9febca88e122b05f6baef7ecbca0068eca4d",
        "document_seconds":120,"request_seconds":30,"cache":"fresh output and empty acceptance cache",
        "order":"alternating by paper","selection":"preselected calibration" if args.paper_ids else "all frozen 30 papers",
        "scope_excludes":["acquisition","embedding/index creation","dense retrieval","browser"],
        "baseline_path":"existing process_paper_grounded -> grounded extractor selection -> model -> gate",
        "settings_difference":"Baseline retains its context estimator; v2 uses 8192. Compare recorded requests.",
        "independent_accuracy":"NOT MEASURED","promotion_conditions_equal":False}
    write(args.output/"manifest.json",manifest)
    import requests
    rows=[]
    for i,source in enumerate(sources):
        for arm in (["baseline","current"] if i%2==0 else ["current","baseline"]):
            folder=args.output/source["paper_id"]/arm;folder.mkdir(parents=True)
            try:
                state=requests.get(model["base_url"]+"/api/ps",timeout=5).json()
            except requests.RequestException:state=None
            write(folder/"model_residency_before.json",state)
            command=[sys.executable,"-B",str(Path(__file__).resolve()),"--worker","--arm",arm,
                "--code-root",str(args.baseline_code if arm=="baseline" else ROOT),
                "--source",source["path"],"--paper-id",source["paper_id"],
                "--model-config",str(args.model_config.resolve()),"--output",str(folder)]
            env={**os.environ,"PYTHONPATH":str(args.baseline_code if arm=="baseline" else ROOT),
                 "HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1"}
            write(folder/"launch.json",{"command":command,"model_residency":state,"state":"started"})
            started=time.monotonic()
            child=subprocess.Popen(command,cwd=args.baseline_code if arm=="baseline" else ROOT,env=env,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                stdout,stderr=child.communicate(timeout=120)
                if child.returncode or not (folder/"measurement.json").is_file():
                    row={"state":"error","partial":True,"exit_code":child.returncode}
                else:row=json.loads((folder/"measurement.json").read_text(encoding="utf-8"))
            except subprocess.TimeoutExpired:
                # Kill the owned process tree, including any parser/model transport child.
                if os.name=="nt":subprocess.run(["taskkill","/PID",str(child.pid),"/T","/F"],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                else:child.kill()
                stdout,stderr=child.communicate()
                row={"state":"timeout","partial":True}
            (folder/"stdout.log").write_bytes(stdout);(folder/"stderr.log").write_bytes(stderr)
            completions=completion_records(folder)
            row.update(paper_id=source["paper_id"],arm=arm,host_elapsed_seconds=time.monotonic()-started,
                completion_records=completions,eligible_targets_retained=True)
            if "elapsed_seconds" not in row:row["elapsed_seconds"]=row["host_elapsed_seconds"]
            row["recorded_model_requests"]=len(list(folder.rglob("actual_request.json")))
            write(folder/"observed.json",row);append(args.output/"timing.jsonl",row);rows.append(row)
            print(source["paper_id"],arm,row["state"],round(row["host_elapsed_seconds"],2),
                  "requests",row["recorded_model_requests"],flush=True)
    sys.path.insert(0,str(ROOT))
    from src.evaluation.evidence_v2 import latency
    summary={"scope":manifest["scope"],"papers":len(sources),"rows":rows,
             "timing":{arm:latency([{**r,"elapsed_seconds":r["host_elapsed_seconds"]} for r in rows if r["arm"]==arm])
                       for arm in ("baseline","current")},
             "independent_accuracy":"NOT MEASURED","equal_correct_coverage":"NOT MEASURED",
             "promotion_latency_verdict":"NOT MEASURED",
             "reason":"Settings differ, scope excludes retrieval setup, and independently correct coverage is unavailable"}
    write(args.output/"comparison.json",summary)
    print(json.dumps({"timing":summary["timing"],"promotion_latency_verdict":summary["promotion_latency_verdict"]}))
if __name__=="__main__":main()
