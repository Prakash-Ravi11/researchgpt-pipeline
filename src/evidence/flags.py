"""EXP-LATEX-01 feature flags — environment-gated, default OFF.

Two independent switches, read from the environment so an experiment arm is
selected without editing tracked config:

``RQ_LATEX_CHUNKING``
    Overrides ``evidence_grounding.latex_ingestion_enabled``. Selects the arXiv
    LaTeX e-print representation (parity-gated) over the arXiv PDF. The config
    default stays ``false`` — see ``configs/staging_config.yaml`` and
    ``experiments/document_evidence_pipeline/LATEX_ACQUISITION_REPORT.md`` for
    the Phase-4/5x negative result that put it there.

``RQ_TABLE_ATOMIC``
    Keeps a ``table`` block in ONE chunk instead of splitting it at
    ``CHUNK_WORDS``. See ``chunker.chunk_document``.

Both default to 0. Unset means "leave the configured behaviour exactly as it
is" — an unset ``RQ_LATEX_CHUNKING`` does not write ``False`` over a config that
says otherwise, it simply does not participate.

Parsing is strict: only ``0/1/false/true/no/yes/off/on`` (case-insensitive,
surrounding whitespace ignored) are accepted. Anything else raises, because an
experiment arm silently selected by a typo is worse than a crash.
"""
from __future__ import annotations

import os

LATEX_CHUNKING_ENV = "RQ_LATEX_CHUNKING"
TABLE_ATOMIC_ENV = "RQ_TABLE_ATOMIC"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class FlagError(ValueError):
    """An RQ_* environment variable holds a value that is not a boolean."""


def _parse(name: str, raw: str) -> bool:
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise FlagError(
        f"{name}={raw!r} is not a boolean. Use one of "
        f"{sorted(_TRUE | _FALSE)} (default: 0)."
    )


def flag(name: str, default: bool = False) -> bool:
    """Read one RQ_* flag. Absent or empty -> `default`."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return _parse(name, raw)


def tristate(name: str) -> bool | None:
    """Read one RQ_* flag as three-valued: True / False / None (unset).

    ``None`` means "no opinion" — the caller keeps whatever the config says.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return _parse(name, raw)


def latex_chunking_override() -> bool | None:
    """Tri-state override for ``evidence_grounding.latex_ingestion_enabled``."""
    return tristate(LATEX_CHUNKING_ENV)


def table_atomic() -> bool:
    """True when table blocks must never be split across chunks."""
    return flag(TABLE_ATOMIC_ENV, default=False)


def snapshot() -> dict[str, object]:
    """Both flags as resolved, for the run manifest."""
    return {
        LATEX_CHUNKING_ENV: os.environ.get(LATEX_CHUNKING_ENV),
        TABLE_ATOMIC_ENV: os.environ.get(TABLE_ATOMIC_ENV),
        "resolved_latex_chunking_override": latex_chunking_override(),
        "resolved_table_atomic": table_atomic(),
    }
