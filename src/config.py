"""Shared configuration loading for CLI and API entrypoints."""

import os
from pathlib import Path

import yaml

from src.evidence import flags


DEFAULT_COLLECTION_NAME = "researchgpt_papers"


def load_config(config_path: str | Path) -> dict:
    """Load YAML and resolve secrets from environment variables.

    Environment variables take precedence so API keys are not required in the
    tracked YAML file and every entrypoint uses the same effective settings.
    """
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    collection = config.setdefault("collection", {})
    env_key = os.environ.get("S2_API_KEY", "").strip()
    file_key = str(collection.get("api_key") or "").strip()
    collection["api_key"] = env_key or file_key or None

    system = config.setdefault("system", {})
    system.setdefault("collection_name", DEFAULT_COLLECTION_NAME)

    _apply_latex_chunking_override(config)
    return config


def _apply_latex_chunking_override(config: dict) -> None:
    """EXP-LATEX-01: let ``RQ_LATEX_CHUNKING`` select the LaTeX ingestion arm.

    Tri-state. Unset (the default) touches nothing, so every existing run keeps
    whatever the YAML says — production stays on the PDF path.

    Deliberately narrow: it sets ONLY
    ``evidence_grounding.latex_ingestion_enabled``. It never sets
    ``evidence_grounding.enabled``, so it cannot turn the grounding path on in a
    config where that is false; in such a config the override is inert.
    """
    override = flags.latex_chunking_override()
    if override is None:
        return
    config.setdefault("evidence_grounding", {})["latex_ingestion_enabled"] = override
