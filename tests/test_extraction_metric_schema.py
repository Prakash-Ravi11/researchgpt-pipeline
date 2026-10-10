"""Atomic Stage-4 metric contracts; no model, corpus, or network calls."""
import pytest

from src.summarization import summarize as S


def extraction(metrics):
    return {
        **{field: "Source-backed text." for field in S._STRING_EXTRACTION_FIELDS},
        "datasets": ["Cohort A, single centre"],
        "metrics": metrics,
    }


def test_extraction_schema_requires_typed_fields_and_string_metric_items():
    schema = S.EXTRACTION_JSON_SCHEMA
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["properties"]) == set(S._EXTRACTION_SCHEMA_KEYS)
    assert schema["properties"]["metrics"]["type"] == "array"
    assert schema["properties"]["metrics"]["items"] == {"type": "string"}
    assert all(schema["properties"][field] == {"type": "string"}
               for field in S._STRING_EXTRACTION_FIELDS)


@pytest.mark.parametrize("metrics", [
    [],
    ["Accuracy", "Precision", "Recall", "F1"],
    ["AUC (macro, micro)", "sensitivity"],
])
def test_atomic_metric_arrays_are_conformant(metrics):
    assert S.check_schema_conformance(extraction(metrics)) == (True, [])


@pytest.mark.parametrize("metrics,issue", [
    ("Accuracy, Precision", "metrics_is_not_list"),
    (None, "metrics_is_not_list"),
    ({"metric": "Accuracy"}, "metrics_is_not_list"),
    (["Accuracy", 1], "metrics_has_nonstring_items"),
    (["Accuracy", None], "metrics_has_nonstring_items"),
    ([{"metric": "Accuracy"}], "metrics_has_nonstring_items"),
    ([["Accuracy"]], "metrics_has_nonstring_items"),
    (["Accuracy, Precision"], "metrics_has_nonatomic_items"),
    ([""], "metrics_has_nonatomic_items"),
    (["   "], "metrics_has_nonatomic_items"),
])
def test_malformed_metric_shapes_are_rejected_before_normalization(metrics, issue):
    raw = extraction(metrics)
    ok, issues = S.check_schema_conformance(raw)
    assert not ok
    assert issue in issues
    assert raw["metrics"] == metrics


@pytest.mark.parametrize("metrics,expected", [
    ("Accuracy, Precision, Recall, F1", ["Accuracy", "Precision", "Recall", "F1"]),
    (["Accuracy, Precision", "F1"], ["Accuracy", "Precision", "F1"]),
    (["AUC (macro, micro), F1", " AUC "], ["AUC (macro, micro)", "F1", "AUC"]),
    (["Dice", "Dice", None, 3, ""], ["Dice", "Dice"]),
])
def test_legacy_metrics_normalize_atomically_without_changing_datasets(metrics, expected):
    raw = extraction(metrics)
    normalized = S.normalize_extraction(raw)
    assert normalized["metrics"] == expected
    assert normalized["datasets"] == ["Cohort A, single centre"]
    assert S.normalize_extraction(normalized) == normalized
    assert raw["metrics"] == metrics


def test_salvage_does_not_turn_invalid_metric_objects_into_strings():
    raw = extraction(["Accuracy, F1", {"score": 0.9}, 7, None])
    salvaged = S.salvage_nonconformant(raw)
    assert salvaged["metrics"] == ["Accuracy", "F1"]
    assert salvaged["datasets"] == ["Cohort A, single centre"]
    assert salvaged["results"] == raw["results"]


def test_old_prompt_cache_is_not_reused_after_schema_change():
    cached = extraction(["Accuracy"])
    text = "This paper evaluates accuracy."
    cached.update(_prompt_version="2026-09-03.numpredict-deadline", _text_hash=S._text_hash(text))
    assert not S._cache_entry_reusable(cached, text)
    cached["_prompt_version"] = S.EXTRACTION_PROMPT_VERSION
    assert S._cache_entry_reusable(cached, text)
