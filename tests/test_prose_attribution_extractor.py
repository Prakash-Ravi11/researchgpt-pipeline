import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.evidence.prose_attribution.extractor import RepairConfig, extract_document, run_request
from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.summary import quantitative_summary
from src.evidence.prose_attribution.support import assess_claim, discourse
from src.evidence.prose_attribution.inventory import inventory


def executor_log(log):
    def execute(request, directory, wall_seconds):
        payload = json.loads(request["user_content"])
        log.append(payload)
        return {"parsed": {"document_id": payload["document_id"], "claims": [],
                           "candidate_accounting": [{"candidate_id": c["id"], "state": "unresolved", "reason": "No owner selected."}
                                                    for c in payload["numeric_inventory"]]},
                "completion": {"done_reason": "stop"}, "host_elapsed_s": 0.001}
    return execute


def test_default_flag_makes_no_request_and_writes_no_artifacts(tmp_path):
    source = SourceDocument.from_text("doc", "A sensor saved 17%.")
    def forbidden(*args):
        raise AssertionError("Disabled feature invoked model")
    result = extract_document(source, {}, tmp_path / "disabled", request_executor=forbidden)
    assert result["status"] == "disabled" and not (tmp_path / "disabled").exists()


def test_one_retry_per_unit_and_explicit_unresolved_accounting(tmp_path):
    source = SourceDocument.from_text("doc", "DeltaDrip reduced water use by 17%.")
    log = []
    result = extract_document(source, {"base_url": "http://localhost:11434", "model": "test"}, tmp_path,
                              RepairConfig(enabled=True, max_document_requests=3), request_executor=executor_log(log))
    assert len(log) == 2
    assert result["retried_evidence_units"] == ["s001"]
    assert result["candidate_ledger"][0]["state"] == "unresolved"
    assert result["accounting"] == {"total_candidates": 1, "ledger_entries": 1, "explicit_model_entries": 1, "unresolved_or_ambiguous": 1}
    assert result["accepted_claims"] == [] and result["summary"] == []


def test_document_request_cap_is_stricter_than_unit_retry_allowances(tmp_path):
    source = SourceDocument.from_text("doc", "DeltaDrip reduced water use by 17%. OtherTool reduced crop losses by 23%. ThirdApp reduced input costs by 11%.")
    log = []
    result = extract_document(source, {"base_url": "http://localhost:11434", "model": "test"}, tmp_path,
                              RepairConfig(enabled=True, max_document_requests=2), request_executor=executor_log(log))
    assert len(log) == 2 and len(result["retried_evidence_units"]) == 1
    assert len(result["candidate_ledger"]) == 3
    assert all(entry["state"] == "unresolved" for entry in result["candidate_ledger"])


def test_cloud_endpoint_is_not_an_implicit_fallback(tmp_path):
    source = SourceDocument.from_text("doc", "A sensor saved 17%.")
    with pytest.raises(ValueError, match="local Ollama"):
        extract_document(source, {"provider": "cloud", "base_url": "https://example.com", "model": "test"}, tmp_path,
                         RepairConfig(enabled=True))


def test_hard_worker_deadline_retains_partial_stream_and_closes_request(tmp_path):
    observations = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            observations.append(self.path)
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write((json.dumps({"message": {"content": "x" * 800}, "done": False}) + "\n").encode())
            self.wfile.flush()
            time.sleep(5)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = {"document_id": "test", "attempt": 0, "prompt_version": "test",
                   "base_url": f"http://127.0.0.1:{server.server_port}", "model": "transport-test-only",
                   "system_prompt": "Return JSON.", "user_content": "unrelated transport test",
                   "response_schema": {}, "settings": {"temperature": 0, "seed": 42, "num_ctx": 256,
                                                         "num_predict": 16, "request_seconds": 10}}
        result = run_request(request, tmp_path / "attempt", 3)
        assert result["hard_timeout"] and result["host_elapsed_s"] < 4
        assert observations == ["/api/chat"]
        assert (tmp_path / "attempt/raw_response.ndjson").read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()


def test_compound_threshold_proportion_and_summary_use_only_accepted_claims():
    source = SourceDocument.from_text("doc", "DeltaYield's forecast system produced predictions. The predictions were within a 4% error for 79% of the plots.", metadata={"source_kind": "narrative_overview"})
    candidates = inventory(source)
    frames = discourse(source, candidates)
    threshold, proportion = candidates
    base = {"candidate_ids": [proportion["id"]], "subject": "DeltaYield", "outcome": "fields_within_prediction_error_threshold",
            "location": None, "year": None, "population": "plots", "claim_role": "cited_result",
            "measurement": {"kind": "scalar", "value": 79, "lower": None, "upper": None, "unit": "percent",
                            "qualifier": "exact", "direction": "proportion", "negated": False,
                            "conditions": [{"kind": "error_threshold", "candidate_id": threshold["id"], "operator": "within", "population": "plots"}]},
            "references": {field: ["s001", "s002"] for field in ("subject", "measurement", "ownership_bridge", "context", "population", "condition", "role")}}
    record = assess_claim(source, candidates, frames, base, "c1")
    assert record["published"] and record["measurement"]["conditions"][0]["value"] == 4
    summary = quantitative_summary([record, {"status": "unresolved", "published": False, "subject": "wrong"}])
    assert len(summary) == 1 and "79" in summary[0]["text"] and "within 4 percent error" in summary[0]["text"]
    base["measurement"]["conditions"] = []
    assert assess_claim(source, candidates, frames, base, "c2")["status"] == "unresolved"
