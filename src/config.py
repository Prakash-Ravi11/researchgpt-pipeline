"""Shared configuration loading for CLI and API entrypoints."""

import os
from pathlib import Path

import yaml


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
    return config
