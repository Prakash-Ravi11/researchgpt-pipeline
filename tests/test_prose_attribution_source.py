from copy import deepcopy

import pytest

from src.evidence.prose_attribution.source import ReferenceError, SourceDocument
from src.evidence.prose_attribution.quotes import map_saved_quotation, repair_saved_claim


def test_original_and_normalized_words_remain_distinct_and_mapped():
    raw = "An o\ufb03ce\n  sensor saved 17%."
    source = SourceDocument.from_text("doc", raw)
    assert source.raw_text == raw
    assert source.normalized_text == "An office sensor saved 17%."
    span = source.span("s001")
    assert span["text"] == raw
    assert source.character_map[4]["original_word_id"] == "b1:w2"
    with pytest.raises(ReferenceError, match="normalized expansion"):
        source.span({"sentence_id": "s001", "start": 4, "end": 5})


def test_foreign_document_unknown_identifier_and_invalid_boundaries_reject():
    source = SourceDocument.from_text("doc", "A sensor saved 17%.")
    for ref in ({"sentence_id": "s001", "document_id": "other"}, "s999",
                {"sentence_id": "s001", "start": True},
                {"sentence_id": "s001", "start": -1},
                {"sentence_id": "s001", "end": 999}):
        with pytest.raises(ReferenceError):
            source.span(ref)


def test_repeated_text_is_ambiguous_for_saved_quotes_but_ids_disambiguate():
    text = "The sensor saved 17%. The sensor saved 17%."
    source = SourceDocument.from_text("doc", text)
    assert map_saved_quotation(source, "The sensor saved 17%.")["status"] == "alignment_failure"
    assert source.span("s001")["raw_start"] != source.span("s002")["raw_start"]


def test_quotation_reconstruction_never_repairs_wrong_owner_or_context():
    source = SourceDocument.from_text("doc", "In 2020, DeltaDrip reduced water use by an estimated 17% [2].")
    claim = {"subject": "OtherTool", "year": 1999, "value": 17,
             "evidence_text": "In 2020, DeltaDrip reduced water use by an estimated 17%."}
    before = deepcopy(claim)
    repaired, audit = repair_saved_claim(source, claim)
    assert claim == before
    assert repaired["subject"] == "OtherTool" and repaired["year"] == 1999
    assert repaired["evidence_text"] in source.raw_text
    assert audit["alignment"]["ownership_established"] is False
    assert audit["claim_fields_changed"] == []


def test_paraphrase_does_not_become_a_convenient_larger_paragraph_quote():
    source = SourceDocument.from_text("doc", "A cited study of DeltaDrip reduced water use by 17%. Its operator also changed the schedule.")
    assert map_saved_quotation(source, "DeltaDrip's operator saved water by 17% after changing the schedule.")["status"] == "alignment_failure"


def test_cross_page_regions_remain_separate_and_geometry_never_enters_model_units():
    blocks = [{"id": "left", "text": "A farm used DeltaDrip.", "page": 1, "column": "left", "bbox": [0, 0, 100, 20]},
              {"id": "next", "text": "The same trial saved 17%.", "page": 2, "column": "left", "bbox": [0, 0, 100, 20]}]
    source = SourceDocument.from_text("doc", "\n\n".join(block["text"] for block in blocks), blocks=blocks)
    rebuilt = source.reconstruct(["s001", "s002"])
    assert {region["page"] for region in rebuilt["regions"]} == {1, 2}
    assert all(region["bbox"] is None for region in rebuilt["regions"])
    assert rebuilt["ownership_established_by_reconstruction"] is False
    assert all(set(unit) == {"id", "block_id", "text", "length"} for unit in source.model_units())


def test_parser_paragraph_blocks_are_not_semantic_paragraph_proof():
    chunks = [{"block_id": "b", "chunk_id": "c1", "text": "Tool A saved 17%.", "block_type": "paragraph", "char_start": 0},
              {"block_id": "b", "chunk_id": "c2", "text": "Tool B saved 21%.", "block_type": "paragraph", "char_start": 100}]
    source = SourceDocument.from_chunks("doc", chunks)
    assert len({block["id"] for block in source.blocks}) == 2
    assert all(block["semantic_paragraph_boundary"] == "not_established" for block in source.blocks)
    assert source.blocks[1]["original_document_char_start"] == 100
