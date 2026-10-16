"""Unified table/prose claim records and versioned model selection contract."""
from __future__ import annotations

import hashlib
import json

from . import PROMPT_VERSION, SCHEMA_VERSION, SOURCE_VERSION, SUPPORT_VERSION
from .selection import SELECTION_VERSION

STATES = ("supported", "rejected", "unresolved")
ACCOUNTING_STATES = ("associated", "outside_scope", "ambiguous", "unresolved")
QUALIFIERS = ("exact", "approximate", "estimated", "up_to", "within", "as_early_as", "more_than", "less_than")
DIRECTIONS = ("decrease", "increase", "savings", "lead_time", "threshold", "proportion", "not_observed", "none")
ROLES = ("original_result", "cited_result", "projection", "background_statistic", "limitation")


def response_schema(source, candidates, *, unit_ids=None):
    refs = {"type": "array", "items": {"type": "string", "enum": list(unit_ids) if unit_ids is not None else [unit["id"] for unit in source.sentences]}}
    number = {"type": ["number", "null"]}
    nullable_string = {"type": ["string", "null"]}
    measurement = {"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["scalar", "range"]},
        "value": number, "lower": number, "upper": number, "unit": {"type": "string"},
        "qualifier": {"type": "string", "enum": list(QUALIFIERS)},
        "direction": {"type": "string", "enum": list(DIRECTIONS)}, "negated": {"type": "boolean"},
        "conditions": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["error_threshold", "baseline", "population_condition"]},
            "candidate_id": {"type": "string", "enum": [candidate["id"] for candidate in candidates]},
            "operator": {"type": "string"}, "population": nullable_string},
            "required": ["kind", "candidate_id", "operator", "population"], "additionalProperties": False}}},
        "required": ["kind", "value", "lower", "upper", "unit", "qualifier", "direction", "negated", "conditions"],
        "additionalProperties": False}
    claim = {"type": "object", "properties": {
        "candidate_ids": {"type": "array", "items": {"type": "string", "enum": [candidate["id"] for candidate in candidates]}},
        "subject": {"type": "string"}, "outcome": {"type": "string"},
        "location": nullable_string, "year": {"type": ["integer", "null"]},
        "population": nullable_string, "claim_role": {"type": "string", "enum": list(ROLES)},
        "measurement": measurement,
        "references": {"type": "object", "properties": {key: refs for key in
            ("subject", "measurement", "ownership_bridge", "context", "population", "condition", "role")},
            "required": ["subject", "measurement", "ownership_bridge", "context", "population", "condition", "role"],
            "additionalProperties": False}},
        "required": ["candidate_ids", "subject", "outcome", "location", "year", "population", "claim_role", "measurement", "references"],
        "additionalProperties": False}
    return {"type": "object", "properties": {
        "document_id": {"type": "string", "const": source.document_id}, "claims": {"type": "array", "items": claim},
        "candidate_accounting": {"type": "array", "items": {"type": "object", "properties": {
            "candidate_id": {"type": "string", "enum": [candidate["id"] for candidate in candidates]},
            "state": {"type": "string", "enum": list(ACCOUNTING_STATES)}, "reason": {"type": "string"}},
            "required": ["candidate_id", "state", "reason"], "additionalProperties": False}}},
        "required": ["document_id", "claims", "candidate_accounting"], "additionalProperties": False}


def cache_key(source, model_config, schema):
    value = {"source_hash": source.metadata["content_sha256"], "source_version": SOURCE_VERSION,
             "schema_version": SCHEMA_VERSION, "prompt_version": PROMPT_VERSION,
             "support_version": SUPPORT_VERSION,
             "selection_version": SELECTION_VERSION,
             "model_configuration": model_config, "response_schema": schema}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def claim_record(document_id, claim_id, proposed, *, origin="prose"):
    return {"schema_version": SCHEMA_VERSION, "document_id": document_id, "claim_id": claim_id,
            "origin": origin, "proposed": proposed, "status": "unresolved", "published": False,
            "subject": None, "outcome": None, "location": None, "year": None, "population": None,
            "claim_role": None, "measurement": None, "field_support": {},
            "structural_validation": {}, "semantic_assessment": {}, "source_regions": [], "evidence_text": None}
