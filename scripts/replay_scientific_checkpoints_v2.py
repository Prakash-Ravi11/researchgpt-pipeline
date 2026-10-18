"""Read-only replay of recorded host checkpoints; no parser or model requests."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evidence.v2.store import project_from_directory
from src.evaluation.evidence_v2 import FIELDS,latency


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def snapshot(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--corpus",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve();output=args.output.resolve()
    if output.exists() or output==run or run in output.parents:
        raise ValueError("Use a fresh output directory outside the frozen run")
    original=snapshot(run);rows=[]
    corpus=read(args.corpus)["corpus"]
    for item in corpus:
        pid=item["paper_id"];sha=item["source_sha256"]
        if hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()!=sha:
            raise ValueError("Source hash mismatch")
        folder=run/pid/"current";before=read(folder/"returned.json")
        started=time.monotonic()
        after=project_from_directory({"paper_id":pid},{"document_sha256":sha},folder/"extraction")
        elapsed=time.monotonic()-started
        facts=after["scientific_facts"];numeric=[f for f in facts if f["kind"]=="numeric"]
        if before and before.get("scientific_facts")!=facts:
            raise ValueError("Existing final facts were not preserved")
        before_ids={f["id"] for f in (before or {}).get("scientific_facts",[])}
        recovered=[f for f in numeric if f["id"] not in before_ids]
        # FIELDS is the already frozen exact-tuple definition. This structural
        # counter is not an independent correctness score or a new acceptance gate.
        complete=[f for f in numeric if all(f.get(k) is not None for k in FIELDS)]
        before_complete=[f for f in (before or {}).get("scientific_facts",[])
                         if f["kind"]=="numeric" and all(f.get(k) is not None for k in FIELDS)]
        row={"paper_id":pid,"source_sha256":sha,"original_returned_record_exists":before is not None,
            "before_numeric_records":len((before or {}).get("quantitative_results",[])),
            "after_numeric_records":len(numeric),"recovered_numeric_fact_ids":[f["id"] for f in recovered],
            "before_qualitative_quotations":len((before or {}).get("qualitative_results",[])),
            "after_qualitative_quotations":len(after["qualitative_results"]),
            "before_structurally_complete_exact_tuples":len(before_complete),
            "after_structurally_complete_exact_tuples":len(complete),
            "numeric_records_with_unknown_measurement_origin":sum(f.get("measurement_origin") is None for f in numeric),
            "state":after["scientific_extraction"]["state"],"elapsed_seconds":elapsed,
            "partial":not after["scientific_extraction"]["coverage"].get("semantic_complete",False),
            "coverage":after["scientific_extraction"]["coverage"],
            "source_artifacts":str(folder/"extraction")}
        destination=output/pid;destination.mkdir(parents=True)
        (destination/"before.json").write_text(json.dumps(before,indent=2),encoding="utf-8")
        (destination/"after.json").write_text(json.dumps(after,indent=2),encoding="utf-8")
        rows.append(row)
    unchanged=original==snapshot(run)
    if not unchanged:raise ValueError("Frozen run artifacts changed during replay")
    summary={"scope":"saved_host_checkpoint_to_API_projection_only","model_requests":0,
        "reconstructed_model_outputs":False,"frozen_run_unchanged":unchanged,"frozen_files_checked":len(original),
        "rows":rows,"timing":latency(rows),
        "before_numeric_records":sum(r["before_numeric_records"] for r in rows),
        "after_numeric_records":sum(r["after_numeric_records"] for r in rows),
        "recovered_host_numeric_records":sum(len(r["recovered_numeric_fact_ids"]) for r in rows),
        "before_qualitative_quotations":sum(r["before_qualitative_quotations"] for r in rows),
        "after_qualitative_quotations":sum(r["after_qualitative_quotations"] for r in rows),
        "before_structurally_complete_exact_tuples":sum(r["before_structurally_complete_exact_tuples"] for r in rows),
        "after_structurally_complete_exact_tuples":sum(r["after_structurally_complete_exact_tuples"] for r in rows),
        "exact_tuple_fields":list(FIELDS),"independently_correct_tuple_recovery":"NOT MEASURED",
        "note":"Core-host-supported records are not independently correct complete scientific tuples; frozen end-to-end timings are unchanged"}
    (output/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    (output/"frozen_run_hashes.json").write_text(json.dumps(original,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in {"rows"}}))

if __name__=="__main__":main()
