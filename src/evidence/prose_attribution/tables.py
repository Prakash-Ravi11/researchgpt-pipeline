"""Lossless, opt-in unified views of the existing validated table associations.

No table parsing, fallback answers, catalog mutation or new table inference.
"""
from copy import deepcopy

from src.evidence.verifier import validate_associated_evidence
from .schema import claim_record


def unified_table_views(document_id, legacy_payload, chunks, *, enabled=False):
    if not enabled:
        return {"status": "disabled", "claims": [], "legacy_modified": False}
    baseline = deepcopy(legacy_payload)
    validation = validate_associated_evidence(legacy_payload, chunks)
    claims = []
    for index, row in enumerate(validation["accepted"]):
        source = deepcopy(row["source"])
        record = claim_record(document_id, "table:" + source["cell_id"], deepcopy(row), origin="table")
        record.update(status="supported", published=True, subject=row["method"], outcome=row["metric"],
                      dataset=row["dataset"], configuration=deepcopy(row["configuration"]),
                      measurement={"kind": "scalar", "value": row["value"], "lower": None, "upper": None,
                                   "unit": row["unit"], "qualifier": "exact", "direction": "none",
                                   "negated": False, "conditions": []},
                      structural_validation={"status": "supported", "method": "existing associated-cell validator"},
                      semantic_assessment={"status": "supported", "method": "explicit source row/configuration/header associations",
                                           "limitation": row.get("semantic_assessment", "automated assessment; independent human review pending")},
                      source_regions=[source], legacy_row=deepcopy(row))
        for field, relationship in (("subject", "method and configuration cells of this source row"),
                                    ("outcome", "metric and dataset headers associated with this source cell"),
                                    ("value", "value/unit notation in this source cell"),
                                    ("unit", "unit/scale notation preserved from the existing cell association"),
                                    ("configuration", "model/retriever configuration cells of this source row"),
                                    ("dataset", "dataset header associated with this source cell")):
            record["field_support"][field] = {"status": "supported", "source_references": [source], "relationship": relationship}
        for field in ("location", "year", "population", "claim_role"):
            record["field_support"][field] = {"status": "unresolved", "source_references": [],
                                               "reason": "Not established by the existing table association; remains null."}
        claims.append(record)
    assert legacy_payload == baseline
    return {"status": "completed", "claims": claims, "rejections": validation["rejections"], "legacy_modified": False}
