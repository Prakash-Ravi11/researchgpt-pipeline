from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from src.synthesis.dataset_resolution import (
    DatasetResolver, canonical_dataset_names, levenshtein_similarity,
)
from src.synthesis.gap_analysis import build_gap_matrix


@pytest.mark.parametrize("label,expected", [
    ("HotPotQA", "HotpotQA"),
    ("HotpotQA (Yang et al., 2018)", "HotpotQA"),
    ("hotpot_qa dataset [12]", "HotpotQA"),
    ("Stanford Question Answering Dataset (SQuAD)", "SQuAD"),
    ("CUAD (Contract Understanding Atticus Dataset)", "CUAD"),
    ("2Wiki (Ho et al., 2020)", "2WikiMultiHopQA"),
    ("2WikimQA", "2WikiMultiHopQA"),
    ("NQDataset", "Natural Questions"),
    ("MS-MARCO", "MS MARCO"),
    ("MovieLens dataset", "MovieLens"),
    ("AIME24", "AIME 2024"),
    ("AIME_2024", "AIME 2024"),
    ("AIME 25", "AIME 2025"),
    ("HotpottQA", "HotpotQA"),
    ("Natural Questons", "Natural Questions"),
    ("Natural Questions (NQ) dataset", "Natural Questions"),
    ("Contract Understanding Atticus Dataset (CUAD)", "CUAD"),
    ("Contract Natural Language Inference (ContractNLI)", "ContractNLI"),
    ("Privacy Question Answering (PrivacyQA)", "PrivacyQA"),
    ("Commonsense Reasoning: StrategyQA", "StrategyQA"),
    ("StrategyQA (Geva et al., 2021)", "StrategyQA"),
    ("REAL-MM-RAG-Bench", "REAL-MM-RAG"),
])
def test_registry_regex_and_fuzzy_aliases(label, expected):
    result = DatasetResolver().resolve(label)
    assert result.canonical == expected
    assert result.original == label
    assert result.similarity >= 0.88
    assert result.repository


@pytest.mark.parametrize("left,right", [
    ("MMLU", "MMLU-Pro"), ("SQuAD", "SQuAD v2"),
    ("NQ", "NQ-open"), ("LegalBench", "LegalBench-RAG"),
    ("HealthcareMagic", "HealthcareMagic-101"),
    ("BraTS 2019", "BraTS 2020"), ("ISLES 2015", "ISLES 2022"),
    ("MovieLens 100K", "MovieLens 1M"),
    ("InfoSeek (Unseen-Q)", "InfoSeek (Unseen-E)"),
    ("HotpotQA (fullwiki)", "HotpotQA (distractor)"),
    ("MuSiQue (answerable)", "MuSiQue"),
    ("MS MARCO v1.0", "MS MARCO v10"),
    ("AIME 2024 I", "AIME 2024 II"),
    ("HotpotQA test", "HotpotQA train"),
    ("MMLongBench", "MMLongBench-Doc"),
    ("Natural Questions (NQ-open)", "Natural Questions (NQ)"),
])
def test_distinct_editions_configurations_and_subsets_survive(left, right):
    assert len(canonical_dataset_names([left, right])) == 2


def test_true_levenshtein_not_token_similarity():
    assert levenshtein_similarity("kitten", "sitting") == pytest.approx(4 / 7)
    assert levenshtein_similarity("", "") == 1
    assert levenshtein_similarity("a", "") == 0
    assert levenshtein_similarity("abc", "cba") == pytest.approx(1 / 3)


def test_exact_threshold_and_lower_score_abstention():
    name = "ABCDEFGHIJKLMNOPQRSTUVWXY"
    resolver = DatasetResolver(((name, (), "repository"),))
    misspelled = list(name.lower())
    for index in (3, 14, 24):
        misspelled[index] = "z"
    assert resolver.resolve("".join(misspelled)).similarity == pytest.approx(0.88)
    assert resolver.resolve("".join(misspelled)).canonical == name
    misspelled[12] = "z"
    assert resolver.resolve("".join(misspelled)).method == "unresolved"
    with pytest.raises(ValueError):
        DatasetResolver(threshold=0.87)


def test_ambiguous_match_and_transitive_chain_do_not_merge():
    registry = (("BenchmarkAA", (), "a"), ("BenchmarkAB", (), "b"))
    assert DatasetResolver(registry).resolve("BenchmarkAC").method == "unresolved"
    with pytest.raises(ValueError):
        DatasetResolver((("One", ("same",), "a"), ("Two", ("same",), "b")))
    assert DatasetResolver().resolve("HotpottQX").method == "unresolved"


def test_unknown_descriptions_are_not_fuzzy_rewritten():
    for label in ("Custom clinical cohort of 687 subjects", "DocBench and MMLongBench",
                  "HotpotQA with additional custom clinical data", "QA", "IR"):
        assert DatasetResolver().resolve(label).canonical == label


def test_matrix_counts_papers_once_and_preserves_input_evidence():
    papers = [
        {"category": "A", "datasets": ["HotPotQA", "HotpotQA (Yang et al., 2018)", "2Wiki"],
         "evidence": {"datasets": [{"value": "HotPotQA", "evidence_span": "HotPotQA"}]}},
        {"category": "A", "datasets": ["HotpottQA"]},
        {"category": "B", "datasets": ["NQ", "NQ-open"]},
    ]
    original = deepcopy(papers)
    result = build_gap_matrix(papers)
    assert papers == original
    assert result == build_gap_matrix(list(reversed(papers)))
    assert result["matrix"]["A"]["HotpotQA"] == 2
    assert result["matrix"]["B"]["HotpotQA"] == 0
    assert {"category": "B", "dataset": "HotpotQA"} in result["candidate_gaps"]
    assert result["dataset_resolution"]["raw_label_count"] == 6
    assert result["dataset_resolution"]["canonical_count"] == 4
    assert canonical_dataset_names(["hotpot_qa"]) == ["HotpotQA"]


def test_empty_or_legacy_scalar_datasets_are_handled_as_entities():
    assert canonical_dataset_names(None) == []
    assert canonical_dataset_names([None, 123, ""]) == []
    assert canonical_dataset_names("HotPotQA") == ["HotpotQA"]
    assert build_gap_matrix([])["matrix"] == {}


@pytest.mark.parametrize("uploaded,expected", [("NQ", True), ("HotPotQA", False)])
def test_uploaded_novelty_gap_uses_same_canonical_identities(tmp_path, monkeypatch, uploaded, expected):
    from src.synthesis import gap_analysis as gap
    papers = [
        {"paper_id": "a", "title": "A", "category": "A", "datasets": ["HotpotQA"]},
        {"paper_id": "b", "title": "B", "category": "B", "datasets": ["Natural Questions"]},
    ]
    (tmp_path / "paper_summaries.json").write_text(json.dumps(papers), encoding="utf-8")
    monkeypatch.setattr(gap, "prime_ollama_cache", lambda *args: None)
    monkeypatch.setattr(gap, "embed_method_texts", lambda *args: {
        "a": np.array([1., 0.]), "b": np.array([0., 1.])})
    monkeypatch.setattr(gap, "call_ollama_json", lambda **kwargs: {"novelty_verdict": "incremental"})
    model = SimpleNamespace(encode=lambda *args, **kwargs: [np.array([1., 0.])])
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(
        SentenceTransformer=lambda *args, **kwargs: model))
    result = gap.compare_against_corpus({"datasets": [uploaded]}, {
        "paths": {"processed_dir": str(tmp_path)}, "embedding": {"model": "test", "device": "cpu"},
        "llm": {"base_url": "test", "model": "test"},
    })
    assert result["fits_identified_gap"] is expected
