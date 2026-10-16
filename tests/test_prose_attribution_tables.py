from copy import deepcopy
import importlib.util
from pathlib import Path

from src.evidence.prose_attribution.tables import unified_table_views


def test_existing_simrag_rows_and_publication_are_unchanged_by_unified_view():
    path = Path(__file__).with_name("test_extraction_associations.py")
    spec = importlib.util.spec_from_file_location("existing_association_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload, chunks = module.supported_case()
    before_payload, before_chunks = deepcopy(payload), deepcopy(chunks)
    baseline = module.evaluate(payload, chunks)
    result = unified_table_views("synthetic", payload, chunks, enabled=True)
    assert result["claims"] and not result["legacy_modified"]
    assert payload == before_payload and chunks == before_chunks
    assert module.evaluate(payload, chunks) == baseline and baseline["complete"]
    for record, original in zip(result["claims"], payload["results"]["rows"]):
        assert record["subject"] == original["method"]
        assert record["measurement"]["value"] == original["value"]
        assert record["measurement"]["unit"] == original["unit"]
        assert record["claim_role"] is None
