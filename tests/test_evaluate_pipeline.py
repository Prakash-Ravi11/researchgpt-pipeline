import asyncio
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

import evaluate_pipeline as evaluation


def chunk(text="We improved accuracy by 35%.", paper="p1", cid="c1"):
    return {"paper_id": paper, "chunk_id": cid, "chunk_index": 0,
            "block_id": "b1", "page_or_node": "p1", "source": "full_text",
            "representation": "pdf", "text": text, "char_start": 100, "char_end": 100 + len(text)}


def evidence(text="We improved accuracy by 35%."):
    return {"value": "Accuracy improved by 35%.", "final": "RETURNED",
            "evidence_span": text, "char_start": 100, "char_end": 100 + len(text),
            "block_id": "b1", "page_or_node": "p1", "source": "full_text",
            "representation": "pdf", "attribution": "OWN_PAPER",
            "evidence_status": "ENTAILED", "provenance_valid": True}


def corpus(tmp_path):
    chunks = [chunk(), chunk("An abstract without quantitative results.", paper="p2", cid="c2")]
    traces = {"p1": {"mode": "legacy", "selected_chunk_ids": ["c1"]},
              "p2": {"mode": "passthrough"}}
    summaries = []
    for index, c in enumerate(chunks):
        summaries.append({"paper_id": c["paper_id"], "title": f"Paper {index}", "cluster_id": index,
                          "summary": "An extraction", "acquisition_status": "FULL_TEXT" if index == 0 else "NO_FULL_TEXT",
                          "_text_hash": hashlib.sha256(c["text"].encode()).hexdigest()[:16],
                          "evidence": {"results": [evidence()] if index == 0 else []}})
    for filename, data in (("paper_summaries.json", summaries), ("chunks.json", chunks),
                           ("retrieval_selection.json", traces)):
        (tmp_path / filename).write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_actual_extraction_order_and_word_cap():
    chunks = {"a": chunk("first paragraph text", cid="a"),
              "b": chunk("second paragraph text", cid="b")}
    texts, ids = evaluation.extraction_contexts("p1", chunks,
        {"selected_chunk_ids": ["b", "a"]}, 4)
    assert texts == ["second paragraph text", "first"]
    assert ids == ["b", "a"]


@pytest.mark.parametrize("ids", [["missing"], ["a", "a"], ["foreign"]])
def test_invalid_retrieval_trace_fails(ids):
    chunks = {"a": chunk(), "foreign": chunk(paper="another")}
    with pytest.raises(ValueError):
        evaluation.extraction_contexts("p1", chunks, {"selected_chunk_ids": ids}, 10)


@pytest.mark.parametrize("value,expected", [
    ("[12.95% improvement, 3.56% boost]", True), ("95HD and NDCG@10", False),
    ("73Rho of 73", True), ("F1 score of 0.37", True), ("Improvement of 1%", True),
    ("See [12, 35] in 2024", False), ("No numeric results reported", False),
])
def test_quantitative_cohort_excludes_identifiers_and_citations(value, expected):
    assert evaluation.has_quantitative_value(value) is expected


@pytest.mark.parametrize("mutation", [
    {"char_start": 101}, {"char_end": 129}, {"attribution": "CITED_PAPER"},
    {"source": "abstract"}, {"block_id": "other"}, {"evidence_span": "We improved accuracy by 36%."},
])
def test_recovered_evidence_requires_real_owned_offsets(mutation):
    item = {**evidence(), **mutation}
    with pytest.raises(ValueError):
        evaluation.locate_source("p1", item, [chunk()])


def test_overlapping_chunks_and_legacy_enclosing_offsets():
    correct = chunk()
    wrong = chunk("A different overlapping source", cid="c0")
    assert evaluation.locate_source("p1", evidence(), [wrong, correct])[2] == "c1"
    legacy = evidence("improved accuracy by 35%.")
    legacy.update(evidence_status="EXPLICIT", char_start=100, char_end=128)
    assert evaluation.locate_source("p1", legacy, [correct])[0] == "improved accuracy by 35%."


def test_prepare_preserves_abstention_and_recovered_cohorts(tmp_path):
    _, papers = evaluation.prepare_corpus(corpus(tmp_path), expected_papers=2)
    assert len(papers) == 2
    assert papers[0]["claims"][0]["recovered"]
    assert papers[0]["claims"][0]["source_chunk_id"] == "c1"
    assert papers[1]["claims"] == []
    aggregate = evaluation.aggregate(papers)
    assert aggregate["recovered_quantitative_claims"] == 1
    assert aggregate["papers_without_quantitative_results"] == 1
    assert aggregate["context_precision"] == {"mean": None, "scored": 0, "eligible": 2, "unscored": 2}


def test_input_hash_mismatch_prevents_scoring_stale_outputs(tmp_path):
    path = corpus(tmp_path)
    chunks = evaluation.read_json(path / "chunks.json")
    chunks[0]["text"] = "Changed input"
    (path / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluation.prepare_corpus(path, expected_papers=2)


def test_saved_labels_and_paper_id_alignment_determine_silhouette():
    summaries = [{"paper_id": str(i), "cluster_id": i // 2} for i in range(4)]
    vectors = {"3": [10, 11], "2": [10, 10], "1": [0, 1], "0": [0, 0]}
    result = evaluation.calculate_topic_separation(summaries, vectors)
    assert result["score"] > .9
    assert result["cluster_sizes"] == {"0": 2, "1": 2}
    mixed = deepcopy(summaries)
    for i, s in enumerate(mixed):
        s["cluster_id"] = i % 2
    assert evaluation.calculate_topic_separation(mixed, vectors)["score"] < 0
    with pytest.raises(ValueError, match="IDs"):
        evaluation.calculate_topic_separation(summaries, {"wrong": [0, 0]})


@pytest.mark.parametrize("labels", [[0, 0, 0], [0, 1, 2], [0]])
def test_undefined_separation_is_null(labels):
    summaries = [{"paper_id": str(i), "cluster_id": label} for i, label in enumerate(labels)]
    result = evaluation.calculate_topic_separation(summaries, {str(i): [i, 1] for i in range(len(labels))})
    assert result["score"] is None
    assert result["reason"]


def test_ollama_length_termination_is_not_accepted():
    def result(reason):
        return SimpleNamespace(generations=[[SimpleNamespace(generation_info={"done_reason": reason})]])
    assert evaluation.ollama_finished(result("stop"))
    assert not evaluation.ollama_finished(result("length"))
    assert not evaluation.ollama_finished(SimpleNamespace(generations=[]))


def test_ragas_failure_is_null_and_source_scope_is_independent(tmp_path):
    _, papers = evaluation.prepare_corpus(corpus(tmp_path), expected_papers=2)
    class Judge:
        def __init__(self, score): self.score = score; self.samples = []
        async def single_turn_ascore(self, sample, timeout=None):
            self.samples.append(sample)
            return self.score
    precision, faithfulness = Judge(float("nan")), Judge(.9)
    asyncio.run(evaluation.score_ragas(papers[0], precision, faithfulness, 1))
    assert papers[0]["context_precision"] is None
    assert "context_precision" in papers[0]["errors"]
    claim = papers[0]["claims"][0]
    assert claim["faithfulness"] == .9
    assert faithfulness.samples[0].response == claim["value"]
    assert faithfulness.samples[0].retrieved_contexts == [claim["source_context"]]
    aggregate = evaluation.aggregate(papers)
    assert aggregate["recovered_results"]["faithfulness"]["mean"] == .9
    assert aggregate["context_precision"]["scored"] == 0


def test_ragas_metrics_can_run_separately_without_repeating_judgments(tmp_path):
    _, papers = evaluation.prepare_corpus(corpus(tmp_path), expected_papers=2)
    class Judge:
        def __init__(self): self.calls = 0
        async def single_turn_ascore(self, sample, timeout=None):
            self.calls += 1
            return .8
    precision, faithfulness = Judge(), Judge()
    asyncio.run(evaluation.score_ragas(papers[0], precision, faithfulness, 1, {"faithfulness"}))
    assert precision.calls == 0 and faithfulness.calls == 1
    asyncio.run(evaluation.score_ragas(papers[0], precision, faithfulness, 1))
    assert precision.calls == 1 and faithfulness.calls == 1
    assert set(papers[0]["completed_ragas_metrics"]) == {"context_precision", "faithfulness"}


def test_bertscore_pair_direction_and_no_silent_truncation():
    class Scorer:
        _tokenizer = SimpleNamespace(model_max_length=5, encode=lambda text, **kw: text.split())
        def score(self, candidates, references):
            assert candidates == ["a paraphrased claim"]
            assert references == ["the source sentence"]
            return [.91], [.85], [.88]
    claims = [{"value": "a paraphrased claim", "reference": "the source sentence", "errors": {}, "bertscore": None},
              {"value": "one two three four five six", "reference": "a source", "errors": {}, "bertscore": None},
              {"value": "bad", "errors": {"provenance": "invalid"}, "bertscore": None}]
    evaluation.score_bertscore(claims, Scorer())
    assert claims[0]["bertscore"] == {"precision": .91, "recall": .85, "f1": .88}
    assert claims[1]["bertscore"] is None
    assert "token limit" in claims[1]["errors"]["bertscore"]
    assert claims[2]["bertscore"] is None


def test_cli_preparation_custom_report_resume_and_fingerprint(tmp_path):
    run_dir = tmp_path / "run"
    processed = run_dir / "processed"
    processed.mkdir(parents=True)
    corpus(processed)
    (run_dir / "config.yaml").write_text(
        "llm:\n  model: judge\n  base_url: http://localhost:11434\n  max_context_words: 2500\n"
        "embedding:\n  model: cached-encoder\n", encoding="utf-8")
    report_path = run_dir / "custom-evaluation.json"
    args = ["--run-dir", str(run_dir), "--output", str(report_path),
            "--expected-papers", "2", "--prepare-only"]
    assert evaluation.main(args) == 0
    first = evaluation.read_json(report_path)
    assert first["status"] == "prepared"
    assert evaluation.main([*args, "--resume"]) == 0
    assert evaluation.read_json(report_path)["fingerprint"] == first["fingerprint"]
    with pytest.raises(ValueError, match="different inputs"):
        evaluation.main([*args, "--resume", "--judge-model", "another"])
    assert evaluation.read_json(report_path)["fingerprint"] == first["fingerprint"]


def test_cli_does_not_overwrite_pipeline_artifacts(tmp_path):
    run_dir = tmp_path / "run"
    processed = run_dir / "processed"
    processed.mkdir(parents=True)
    corpus(processed)
    (run_dir / "config.yaml").write_text(
        "llm:\n  model: judge\n  base_url: http://localhost:11434\n"
        "embedding:\n  model: cached-encoder\n", encoding="utf-8")
    original = (processed / "chunks.json").read_bytes()
    with pytest.raises(SystemExit):
        evaluation.main(["--run-dir", str(run_dir), "--expected-papers", "2", "--prepare-only",
                         "--output", str(processed / "chunks.json")])
    assert (processed / "chunks.json").read_bytes() == original
