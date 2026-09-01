"""Deterministic evidence utilities for ResearchGPT.

`verifier` is the original lightweight field-presence check (unchanged).
`acquire` / `represent` / `chunker` / `attribute` / `gate` are the validated
document-evidence components promoted from
experiments/document_evidence_pipeline/pipeline/ (see FINAL_REPORT.md §O).
They are only active when config['evidence_grounding']['enabled'] is true.
"""

from .verifier import verify_evidence, verify_papers

__all__ = ["verify_evidence", "verify_papers"]
