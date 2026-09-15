"""Environment capture for EXP-LATEX-01 (Part 7).

Records exactly what the arm ran on, so a control and a treatment measured on
different hardware can never be silently compared. Every field is either a
measured value or the string "unavailable" — never a guess.
"""
from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGES = ("torch", "sentence_transformers", "transformers", "chromadb",
            "pymupdf", "fitz", "numpy", "scipy", "FlagEmbedding", "requests", "yaml")


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "unavailable"
    except Exception:  # noqa: BLE001
        return "unavailable"


def gpu_info() -> dict:
    info: dict = {"nvidia_smi_present": bool(shutil.which("nvidia-smi"))}
    if info["nvidia_smi_present"]:
        info["query"] = _run(["nvidia-smi",
                              "--query-gpu=name,memory.total,driver_version,compute_cap",
                              "--format=csv,noheader"])
        info["raw_header"] = _run(["nvidia-smi"]).splitlines()[:4]
    try:
        torch = importlib.import_module("torch")
        info["torch_cuda_available"] = bool(torch.cuda.is_available())
        info["torch_cuda_version"] = getattr(torch.version, "cuda", None)
        info["n_gpus"] = torch.cuda.device_count() if torch.cuda.is_available() else 0
        info["devices"] = [
            {"index": i,
             "name": torch.cuda.get_device_name(i),
             "total_memory_mib": torch.cuda.get_device_properties(i).total_memory // (1024 ** 2),
             "capability": ".".join(map(str, torch.cuda.get_device_capability(i)))}
            for i in range(info.get("n_gpus", 0))]
    except Exception as exc:  # noqa: BLE001
        info["torch"] = f"unavailable ({type(exc).__name__})"
    return info


def package_versions() -> dict:
    out = {}
    for name in PACKAGES:
        try:
            m = importlib.import_module(name)
            out[name] = str(getattr(m, "__version__", "present (no __version__)"))
        except Exception as exc:  # noqa: BLE001
            out[name] = f"unavailable ({type(exc).__name__})"
    return out


def git_info(repo: Path) -> dict:
    def g(*args):
        try:
            return subprocess.run(["git", "-C", str(repo), *args],
                                  capture_output=True, text=True,
                                  timeout=30).stdout.strip() or "unavailable"
        except Exception:  # noqa: BLE001
            return "unavailable"
    return {
        "commit": g("rev-parse", "HEAD"),
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "describe": g("describe", "--tags", "--always", "--dirty"),
        "status_porcelain": g("status", "--porcelain"),
        "tags": g("tag", "--points-at", "HEAD"),
    }


def capture(repo: Path) -> dict:
    return {
        "python": sys.version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "gpu": gpu_info(),
        "packages": package_versions(),
        "git": git_info(repo),
        "env_flags": {k: v for k, v in os.environ.items() if k.startswith("RQ_")},
    }


def missing_requirements() -> list[str]:
    """What this environment cannot do. Empty list means an arm can run."""
    missing = []
    for pkg, why in (("torch", "BGE-M3 embedding"),
                     ("sentence_transformers", "BGE-M3 embedding"),
                     ("chromadb", "vector indexing"),
                     ("pymupdf", "PDF parsing")):
        try:
            importlib.import_module(pkg)
        except Exception:  # noqa: BLE001
            missing.append(f"{pkg} (needed for {why})")
    return missing


if __name__ == "__main__":
    print(json.dumps(capture(Path(__file__).resolve().parent.parent.parent), indent=2))
