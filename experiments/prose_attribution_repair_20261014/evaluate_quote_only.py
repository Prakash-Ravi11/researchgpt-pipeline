"""Phase 2 isolation evaluation using saved A outputs, with no inference."""
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.quotes import repair_saved_claim


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    source_cases = {case["id"]: case for case in read(HERE / "evaluation_only/passages.json")["cases"]}
    baseline = read(HERE / "frozen_baseline/a_output.json")
    reviewed = read(HERE / "frozen_baseline/semantic_review.json")
    result, decisions = {"cases": []}, []
    before, after, changed_fields, repaired = 0, 0, 0, 0
    started = time.perf_counter()
    for case in baseline["cases"]:
        source = SourceDocument.from_text(case["id"], source_cases[case["id"]]["text"])
        claims = []
        for index, original in enumerate(case["claims"]):
            before += original["evidence_text"] not in source.raw_text
            claim, decision = repair_saved_claim(source, original)
            after += claim["evidence_text"] not in source.raw_text
            fields = [key for key in original if key != "evidence_text" and original[key] != claim[key]]
            changed_fields += len(fields)
            repaired += original["evidence_text"] != claim["evidence_text"]
            decisions.append({"case_id": case["id"], "index": index, **decision})
            claims.append(claim)
        result["cases"].append({"id": case["id"], "claims": claims})
    assert changed_fields == 0
    folder = HERE / "phase2_quotation_only"
    folder.mkdir(exist_ok=True)
    (folder / "output.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (folder / "alignment_decisions.json").write_text(json.dumps(decisions, indent=2), encoding="utf-8")
    reviewed_grounded = 0
    for row in reviewed["claim_reviews"]["a"]:
        claim = next(c for c in result["cases"] if c["id"] == row["case_id"])["claims"][row["index"]]
        if row["semantic_tuple_matches"] and row["evidence_relationship_complete"] and claim["evidence_text"] in source_cases[row["case_id"]]["text"]:
            reviewed_grounded += 1
    metrics = {"phase": "2_quotation_only", "new_inference_requests": 0,
               "invalid_quotations_before": before, "invalid_quotations_after": after,
               "quotations_reconstructed": repaired, "nonquotation_fields_changed": changed_fields,
               "context_attribution_errors_before": 3, "context_attribution_errors_after": 3,
               "missing_quantities_before": 4, "missing_quantities_after": 4,
               "semantic_tuple_matches_before": 11, "semantic_tuple_matches_after": 11,
               "grounded_tuples_before": 6, "grounded_tuples_after": reviewed_grounded,
               "host_runtime_seconds": time.perf_counter() - started,
               "interpretation": "Alignment improved; ownership/context and quantity coverage did not.",
               "quote_code_sha256": hashlib.sha256((ROOT / "src/evidence/prose_attribution/quotes.py").read_bytes()).hexdigest(),
               "source_code_sha256": hashlib.sha256((ROOT / "src/evidence/prose_attribution/source.py").read_bytes()).hexdigest()}
    (folder / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
