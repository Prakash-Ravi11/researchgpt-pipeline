"""Authoritative input text, normalized-to-original maps and bounded references.

Geometry stays here in the host. Parser blocks are never asserted to be semantic
paragraphs. Missing PDF/word geometry remains missing.
"""
from __future__ import annotations

import bisect
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from . import SOURCE_VERSION


class ReferenceError(ValueError):
    pass


def normalize_with_map(text: str):
    characters, mapping = [], []
    for index, original in enumerate(text):
        for char in unicodedata.normalize("NFKC", original):
            if char.isspace():
                if not characters:
                    continue
                if characters[-1] == " ":
                    mapping[-1][1] = index + 1
                else:
                    characters.append(" ")
                    mapping.append([index, index + 1])
            else:
                characters.append(char)
                mapping.append([index, index + 1])
    if characters and characters[-1] == " ":
        characters.pop()
        mapping.pop()
    return "".join(characters), mapping


def _sentences(text):
    start = 0
    for match in re.finditer(r"[.!?](?:['\"])?(?:\s*\[\d+(?:,\s*\d+)*\])?\s+", text):
        prefix = text[:match.start() + 1]
        if re.search(r"(?:\b[A-Z]\.[A-Z]|\b(?:Dr|Mr|Ms|Prof|Fig|vs))\.$", prefix):
            continue
        end = match.end()
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            yield start, end
        start = match.end()
    if start < len(text):
        yield start, len(text)


@dataclass
class SourceDocument:
    document_id: str
    raw_text: str
    normalized_text: str
    character_map: list
    blocks: list
    words: list
    sentences: list
    metadata: dict

    @classmethod
    def from_text(cls, document_id, text, *, blocks=None, metadata=None):
        if not isinstance(document_id, str) or not document_id or not isinstance(text, str):
            raise ValueError("Document identity and original input text are required")
        supplied = blocks or [{"id": "b1", "text": text}]
        if "\n\n".join(block["text"] for block in supplied) != text:
            raise ValueError("Block text does not reproduce the authoritative input")
        normalized, mapping = normalize_with_map(text)
        block_records, words, sentences = [], [], []
        raw_cursor = 0
        for ordinal, block in enumerate(supplied):
            raw = block["text"]
            record = {**block, "id": str(block.get("id", f"b{ordinal + 1}")),
                      "raw_start": raw_cursor, "raw_end": raw_cursor + len(raw),
                      "semantic_paragraph_boundary": block.get("semantic_paragraph_boundary", "not_established"),
                      "reading_order_status": block.get("reading_order_status", "provided" if block.get("reading_order") is not None else "observed_input_order_only"),
                      "geometry_status": "provided_block_geometry" if block.get("bbox") is not None else "missing",
                      "parser_version": block.get("parser_version"),
                      "metadata_status": {key: "provided" if block.get(key) is not None else "missing"
                                          for key in ("page", "column", "section", "header", "caption", "association_tables", "parser_version")}}
            block_records.append(record)
            provided_words = block.get("words", [])
            for word_number, match in enumerate(re.finditer(r"\S+", raw)):
                word = {"id": f"{record['id']}:w{word_number + 1}", "block_id": record["id"],
                        "text": match.group(), "raw_start": raw_cursor + match.start(),
                        "raw_end": raw_cursor + match.end(), "bbox": None, "line_id": None,
                        "geometry_status": "missing"}
                # Word geometry is usable only with explicit matching character
                # offsets, not guessed from token ordering or a large block box.
                matches = [p for p in provided_words
                           if p.get("char_start") == match.start() and p.get("char_end") == match.end()
                           and p.get("text") == match.group()]
                if len(matches) == 1:
                    word.update(bbox=matches[0].get("bbox"), line_id=matches[0].get("line_id"),
                                geometry_status="provided" if matches[0].get("bbox") else "missing")
                words.append(word)
            block_normalized, local_map = normalize_with_map(raw)
            for begin, end in _sentences(block_normalized):
                original_begin = raw_cursor + local_map[begin][0]
                original_end = raw_cursor + local_map[end - 1][1]
                sentences.append({"id": f"s{len(sentences) + 1:03d}", "block_id": record["id"],
                                  "text": block_normalized[begin:end], "length": end - begin,
                                  "raw_start": original_begin, "raw_end": original_end,
                                  "character_map": [[raw_cursor + a, raw_cursor + b] for a, b in local_map[begin:end]],
                                  "boundary_status": "host_sentence_segmentation; not a semantic ownership boundary"})
            raw_cursor += len(raw) + 2
        if len({block["id"] for block in block_records}) != len(block_records):
            raise ValueError("Duplicate block identifiers")
        starts = [word["raw_start"] for word in words]
        mapped_characters = []
        for begin, end in mapping:
            index = bisect.bisect_right(starts, begin) - 1
            word_id = words[index]["id"] if index >= 0 and begin < words[index]["raw_end"] else None
            mapped_characters.append({"raw_start": begin, "raw_end": end, "original_word_id": word_id})
        info = {"source_version": SOURCE_VERSION,
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "normalization_rules": ["unicode_nfkc", "collapse_whitespace"],
                "original_pdf_text_available": False, "parser_version": None,
                **(metadata or {})}
        return cls(document_id, text, normalized, mapped_characters, block_records, words, sentences, info)

    def as_dict(self):
        return {"document_id": self.document_id, "original_text": self.raw_text,
                "normalized_text": self.normalized_text, "normalized_character_to_original_word": self.character_map,
                "blocks": self.blocks, "original_words": self.words, "sentences": self.sentences,
                "metadata": self.metadata}

    def model_units(self):
        return [{"id": unit["id"], "block_id": unit["block_id"], "text": unit["text"],
                 "length": unit["length"]} for unit in self.sentences]

    @classmethod
    def from_chunks(cls, document_id, chunks, *, metadata=None):
        blocks = []
        for index, chunk in enumerate(chunks):
            block = {**chunk, "id": chunk.get("block_id") or chunk.get("chunk_id") or f"b{index + 1}",
                     "parser_block_type": chunk.get("block_type"),
                     "semantic_paragraph_boundary": "not_established",
                     "original_document_char_start": chunk.get("char_start"),
                     "original_document_char_end": chunk.get("char_end")}
            if "page" not in block:
                block["page"] = chunk.get("page_or_node")
            blocks.append(block)
        # Several chunks can share a parser block; retain chunk identities
        # without falsely merging their original text into one paragraph.
        seen = set()
        for index, block in enumerate(blocks):
            if block["id"] in seen:
                block["id"] = str(block["id"]) + f":chunk{index + 1}"
            seen.add(block["id"])
        return cls.from_text(document_id, "\n\n".join(block["text"] for block in blocks),
                             blocks=blocks, metadata={"representation_scope": "provided_chunks", **(metadata or {})})

    def sentence(self, identifier):
        found = [unit for unit in self.sentences if unit["id"] == identifier]
        if len(found) != 1:
            raise ReferenceError("Unknown or ambiguous sentence identifier: " + str(identifier))
        return found[0]

    def span(self, reference):
        if isinstance(reference, str):
            reference = {"sentence_id": reference}
        if not isinstance(reference, dict):
            raise ReferenceError("Source reference must be an identifier or span object")
        if reference.get("document_id", self.document_id) != self.document_id:
            raise ReferenceError("Reference document identity mismatch")
        unit = self.sentence(reference.get("sentence_id"))
        begin, end = reference.get("start", 0), reference.get("end", unit["length"])
        if type(begin) is not int or type(end) is not int or not (0 <= begin < end <= unit["length"]):
            raise ReferenceError("Invalid normalized span boundaries")
        if ((begin > 0 and unit["character_map"][begin] == unit["character_map"][begin - 1])
                or (end < unit["length"] and unit["character_map"][end - 1] == unit["character_map"][end])):
            raise ReferenceError("Span cuts a normalized expansion of an original character")
        raw_begin = unit["character_map"][begin][0]
        raw_end = unit["character_map"][end - 1][1]
        return {"document_id": self.document_id, "sentence_id": unit["id"], "block_id": unit["block_id"],
                "normalized_start": begin, "normalized_end": end,
                "raw_start": raw_begin, "raw_end": raw_end,
                "text": self.raw_text[raw_begin:raw_end], "normalized_text": unit["text"][begin:end],
                "regions": self.regions(raw_begin, raw_end)}

    def regions(self, start, end):
        regions = []
        for block in self.blocks:
            begin, finish = max(start, block["raw_start"]), min(end, block["raw_end"])
            if begin >= finish:
                continue
            selected = [word for word in self.words if word["block_id"] == block["id"]
                        and word["raw_start"] < finish and word["raw_end"] > begin]
            groups = {}
            for word in selected:
                groups.setdefault(word.get("line_id") or "unavailable", []).append(word)
            for line, members in groups.items():
                boxes = [word["bbox"] for word in members if word.get("bbox")]
                bbox = ([min(box[0] for box in boxes), min(box[1] for box in boxes),
                         max(box[2] for box in boxes), max(box[3] for box in boxes)] if len(boxes) == len(members) and boxes else None)
                regions.append({"block_id": block["id"], "page": block.get("page"), "column": block.get("column"),
                                "section": block.get("section"), "line_id": None if line == "unavailable" else line,
                                "word_ids": [word["id"] for word in members], "bbox": bbox,
                                "geometry_status": "provided_word_geometry" if bbox else "missing_for_selected_words",
                                "block_bbox": block.get("bbox"), "raw_start": begin, "raw_end": finish})
        return regions

    def reconstruct(self, references):
        if not references:
            raise ReferenceError("No references selected")
        spans = [self.span(reference) for reference in references]
        start, end = min(span["raw_start"] for span in spans), max(span["raw_end"] for span in spans)
        return {"status": "supported", "structural_validation_only": True,
                "document_id": self.document_id, "content_sha256": self.metadata["content_sha256"],
                "selected_spans": spans, "evidence_text": self.raw_text[start:end],
                "envelope_includes_unselected_text": sum(span["raw_end"] - span["raw_start"] for span in spans) < end - start,
                "regions": self.regions(start, end), "raw_start": start, "raw_end": end,
                "ownership_established_by_reconstruction": False}
