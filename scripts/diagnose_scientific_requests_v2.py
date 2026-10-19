"""Audit actual saved requests against current host admissibility; no inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.v2.preflight import prose_preflight,table_preflight


def read(path):return json.loads(path.read_text(encoding="utf-8"))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError("Use a fresh diagnostic output")
    counts=Counter();fields=Counter();rows=[]
    for file in sorted(args.run.glob("P*/current/extraction/prose/*/source.json")):
        saved=read(file)
        source=SourceDocument.from_text(saved["document_id"],saved["original_text"],blocks=saved["blocks"],metadata=saved["metadata"])
        if source.metadata["content_sha256"]!=saved["metadata"]["content_sha256"]:
            raise ValueError("Saved packet identity mismatch")
        guard=prose_preflight(source);actual=list(file.parent.glob("attempt_*/actual_request.json"))
        counts["prepared_prose_packets"]+=1
        counts["prepared_prose_packets_with_host_owner_witness"]+=int(guard["can_propose"])
        counts["executed_prose_requests"]+=len(actual)
        counts["executed_prose_requests_with_host_owner_witness"]+=len(actual)*int(guard["can_propose"])
        rows.append({"kind":"prose","path":str(file),"sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
                     "actual_request_paths":[str(x) for x in actual],**guard})
        result=read(file.parent/"result.json") if (file.parent/"result.json").is_file() else {}
        counts["saved_accepted_prose_claims"]+=len(result.get("accepted_claims",[]))
        for claim in result.get("unpublished_claims",[]):
            counts["unpublished_prose_claims"]+=1
            for field,decision in claim.get("field_support",{}).items():
                if decision["status"]!="supported":fields[field+":"+decision["status"]]+=1
    for file in sorted(args.run.glob("P*/current/extraction/requests/r*/actual_request.json")):
        request=read(file);content=json.loads(request["payload"]["messages"][1]["content"])
        document=read(file.parents[2]/"parse/parsed.json");guard=table_preflight(document,content["packet"])
        counts["executed_table_requests"]+=1
        counts["executed_table_requests_with_admissible_host_relation"]+=int(guard["can_propose"])
        rows.append({"kind":"table","path":str(file),"sha256":hashlib.sha256(file.read_bytes()).hexdigest(),**guard})
    result={"scope":"Saved execution audit plus deterministic policy preflight; no missing execution reconstructed",
            "new_model_requests":0,"counts":dict(counts),"unpublished_field_statuses":dict(fields),"rows":rows}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"counts":result["counts"],"unpublished_field_statuses":result["unpublished_field_statuses"]}))
if __name__=="__main__":main()
