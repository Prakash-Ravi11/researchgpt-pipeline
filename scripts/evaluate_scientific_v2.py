"""Paired native-stage diagnostic on all frozen sources; never claims model latency."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def worker(args):
    root=Path(args.code_root)
    sys.path.insert(0,str(root))
    started=time.monotonic()
    if args.arm=="baseline":
        from src.evidence.represent import blocks_from_pdf
        blocks=blocks_from_pdf(Path(args.source).read_bytes(),args.paper_id,"full_text")
        result={"paper_id":args.paper_id,"units":len(blocks),
                "table_cells":sum(len(b.get("table_cells",[])) for b in blocks),
                "tables":sum(bool(b.get("table_cells")) for b in blocks),
                "facts":None,"scientific_decisions":None,"state":"native_stage_complete"}
    else:
        from src.evidence.v2.inventory import inventory_pdf
        from src.evidence.v2.runner import interpret
        from src.evidence.v2.runtime import Config
        document=inventory_pdf(Path(args.source),args.paper_id)
        output=Path(args.output)
        result=interpret(document,output,config=Config(enabled=True))
        result={"paper_id":args.paper_id,"pages":len(document["pages"]),
                "units":len(document["units"]),"table_cells":sum(len(t["cell_ids"]) for t in document["tables"]),
                "tables":len(document["tables"]),"numeric_facts":sum(f["kind"]=="numeric" for f in result["facts"]),
                "qualitative_source_quotations":sum(f["kind"]=="qualitative" for f in result["facts"]),
                "coverage":result["coverage"],"state":result["state"],"partial":result["state"]!="complete"}
    result["elapsed_seconds"]=time.monotonic()-started
    import runpy
    resource_module=runpy.run_path(str(Path(__file__).resolve().parents[1]/"src/evidence/v2/resources.py"))
    result.update(resource_module["process_memory"]())
    result["model_requests"]=0
    Path(args.output).mkdir(parents=True,exist_ok=True)
    (Path(args.output)/"stage.json").write_text(json.dumps(result,indent=2),encoding="utf-8")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker",action="store_true")
    p.add_argument("--arm",choices=["baseline","current"])
    p.add_argument("--code-root");p.add_argument("--source");p.add_argument("--paper-id")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--corpus",type=Path);p.add_argument("--baseline-code",type=Path)
    p.add_argument("--seconds-per-arm",type=float,default=120)
    args=p.parse_args()
    if args.worker:return worker(args)
    root=Path(__file__).resolve().parents[1]
    if args.output.exists():raise ValueError("Choose a fresh diagnostic directory")
    args.output.mkdir(parents=True)
    corpus=json.loads(args.corpus.read_text(encoding="utf-8"))
    rows=[]
    manifest={"scope":"paired_native_inventory_and_host_diagnostics","model_inference":False,
              "accuracy_authority":corpus["label_authority"],
              "no_end_to_end_latency_claim":True,"sources":corpus["corpus"],
              "code_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
              "timeout_per_arm":args.seconds_per_arm,"order":"alternating by paper"}
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    for index,source in enumerate(corpus["corpus"]):
        for arm in (["baseline","current"] if index%2==0 else ["current","baseline"]):
            folder=args.output/source["paper_id"]/arm
            if source["status"]!="hash_verified":
                rows.append({"paper_id":source["paper_id"],"arm":arm,"state":"unavailable",
                             "elapsed_seconds":0,"eligible_targets_retained":True});continue
            actual=hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest()
            if actual!=source["source_sha256"]:raise ValueError("Frozen source changed")
            command=[sys.executable,"-B",str(Path(__file__).resolve()),"--worker","--arm",arm,
                "--code-root",str(args.baseline_code if arm=="baseline" else root),
                "--source",source["path"],"--paper-id",source["paper_id"],"--output",str(folder)]
            started=time.monotonic()
            process=subprocess.Popen(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                stdout,stderr=process.communicate(timeout=args.seconds_per_arm)
                if process.returncode or not (folder/"stage.json").exists():
                    row={"paper_id":source["paper_id"],"state":"error","elapsed_seconds":time.monotonic()-started,
                         "error":stderr.decode("utf-8",errors="replace")}
                else:row=json.loads((folder/"stage.json").read_text(encoding="utf-8"))
            except subprocess.TimeoutExpired:
                process.kill();process.communicate()
                row={"paper_id":source["paper_id"],"state":"timeout","partial":True,
                     "elapsed_seconds":time.monotonic()-started,"eligible_targets_retained":True}
            row["arm"]=arm;row["host_elapsed_seconds"]=time.monotonic()-started
            rows.append(row)
            with (args.output/"timing.jsonl").open("a",encoding="utf-8") as f:
                f.write(json.dumps(row)+"\n");f.flush();os.fsync(f.fileno())
            print(source["paper_id"],arm,row["state"],round(row["elapsed_seconds"],2),flush=True)
    sys.path.insert(0,str(root))
    from src.evaluation.evidence_v2 import latency,promotion_gates
    summary={"scope":manifest["scope"],"papers":len(corpus["corpus"]),"rows":rows,
             "timing":{arm:latency([r for r in rows if r["arm"]==arm]) for arm in ["baseline","current"]},
             "model_requests":0,"independent_precision":None,"independent_recall":None,
             **promotion_gates({"precision":None,"exact_tuple_recall":None},
                               {"precision":None,"exact_tuple_recall":None})}
    (args.output/"comparison.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({"papers":summary["papers"],"model_requests":0,"timing":summary["timing"],
                      "eligible_for_promotion":summary["eligible_for_promotion"]}))
if __name__=="__main__":main()
