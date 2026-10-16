from src.evidence.prose_attribution.deadline_guard import reject_late_completion, extract_bounded_document
from src.evidence.prose_attribution.source import SourceDocument
from src.evidence.prose_attribution.extractor import RepairConfig
from src.evidence.prose_attribution import deadline_guard


def test_late_completed_response_is_discarded_without_claim_publication(tmp_path):
    original = {"parsed": {"document_id": "doc", "claims": [{"subject": "untrusted"}]},
                "host_elapsed_s": 10, "hard_timeout": False,
                "completion": {"done_reason": "stop", "eval_count": 20}}
    def completed_after_deadline(*args):
        return original
    result = reject_late_completion({}, tmp_path, 3, transport=completed_after_deadline)
    assert result["parsed"] is None and result["late_completion_rejected"]
    assert result["completion"]["done_reason"] == "deadline_exceeded"
    assert result["completion_before_guard"]["done_reason"] == "stop"
    assert original["parsed"] is not None
    assert (tmp_path / "pre_deadline_guard_result.json").exists()


def test_guarded_default_remains_disabled_without_requests_or_writes(tmp_path):
    result = extract_bounded_document(SourceDocument.from_text("doc", "A sensor saved 17%."), {}, tmp_path / "disabled")
    assert result["status"] == "disabled" and result["requests"] == []
    assert not (tmp_path / "disabled").exists()


def test_output_fingerprint_distinguishes_budgets_and_host_layout_confidence(tmp_path, monkeypatch):
    def no_inference(*args, **kwargs):
        return {"status": "completed", "cache_key": "same_core_key", "elapsed_s": 0}
    monkeypatch.setattr(deadline_guard, "extract_document", no_inference)
    text = "DeltaDrip reduced water use by 17%."
    ordered = SourceDocument.from_text("doc", text, blocks=[{"id": "b1", "text": text, "reading_order": 0}])
    missing = SourceDocument.from_text("doc", text, blocks=[{"id": "b1", "text": text, "reading_order_status": "missing"}])
    a = extract_bounded_document(ordered, {}, tmp_path / "one", RepairConfig(enabled=True, max_document_requests=1))
    b = extract_bounded_document(ordered, {}, tmp_path / "three", RepairConfig(enabled=True, max_document_requests=3))
    c = extract_bounded_document(missing, {}, tmp_path / "missing", RepairConfig(enabled=True, max_document_requests=3))
    assert len({a["cache_key"], b["cache_key"], c["cache_key"]}) == 3
