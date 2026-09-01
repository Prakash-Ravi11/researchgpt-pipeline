"""Canonical document-evidence pipeline (isolated experiment).

Import order of the modules:
    schema -> acquire -> represent -> chunker -> index -> extract -> attribute -> decide -> run

Nothing here imports from src/ (production) except read-only reuse of the
sibling acquisition resolver's HTTP helpers. Nothing writes under data/.
"""
