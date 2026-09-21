"""Shared configuration loading for CLI and API entrypoints."""

import logging
import os
from pathlib import Path

import yaml


DEFAULT_COLLECTION_NAME = "researchgpt_papers"

EXAMPLE_CONFIG = "configs/config.example.yaml"
MISSING_CONFIG_MESSAGE = (
    "Config file not found: {path}\n"
    "Copy the example and edit it:  cp {example} {path}"
)

_log = logging.getLogger(__name__)
_device_warned = False


def resolve_device(configured: str | None) -> str:
    """Return the configured device, except that a configured CUDA device becomes
    'cpu' -- with one warning -- when CUDA is not actually available.

    torch is imported lazily so that loading config does not require it.
    """
    want = (configured or "cpu").strip().lower()
    if not want.startswith("cuda"):
        return want
    try:
        import torch
        available = bool(torch.cuda.is_available())
    except Exception:  # torch missing or broken install -- treat as no CUDA
        available = False
    if available:
        return want
    global _device_warned
    if not _device_warned:
        _device_warned = True
        _log.warning(
            "CUDA was requested (embedding.device=%r) but is not available; "
            "falling back to CPU. Embedding will be substantially slower.", configured)
    return "cpu"


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
