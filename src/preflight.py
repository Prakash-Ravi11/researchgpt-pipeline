"""Startup preflight checks for external services.

Shared by run_pipeline.py, src/api/main.py and scripts/doctor.py so there is one
definition of "is Ollama usable" and one set of user-facing messages.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def check_ollama(base_url: str, model: str, timeout: float = 5.0) -> dict:
    """Is the configured Ollama reachable, and is the configured model pulled?

    Returns {ok, ollama_reachable, model_present, message}. The message always
    names the exact command that fixes the problem.
    """
    base = (base_url or "").rstrip("/")
    result = {"ok": False, "ollama_reachable": False, "model_present": False,
              "message": "", "base_url": base, "model": model}

    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as r:
            tags = json.loads(r.read().decode())
    except Exception as exc:
        result["message"] = (
            f"Ollama is not reachable at {base} ({type(exc).__name__}). "
            f"Start Ollama, then retry:  ollama serve")
        return result

    result["ollama_reachable"] = True
    names = {m.get("name", "") for m in tags.get("models", [])}
    # Ollama reports "qwen2.5:7b"; accept a bare name matching the ":latest" form too.
    present = model in names or f"{model}:latest" in names or any(
        n.split(":", 1)[0] == model for n in names)
    result["model_present"] = bool(present)

    if not present:
        result["message"] = (
            f"Ollama is running at {base} but model {model!r} is not installed. "
            f"Install it:  ollama pull {model}")
        return result

    result["ok"] = True
    result["message"] = f"Ollama reachable at {base}; model {model!r} is installed."
    return result


def check_ollama_from_config(config: dict, timeout: float = 5.0) -> dict:
    """check_ollama() against the llm block of a loaded config."""
    llm = config.get("llm", {}) or {}
    return check_ollama(llm.get("base_url", "http://localhost:11434"),
                        llm.get("model", ""), timeout=timeout)
