"""Environment doctor — one line per check, PASS / WARN / FAIL.

Exits non-zero if any check FAILs. WARN never fails the run: a missing GPU or an
uncached embedding model are slow, not broken.

Reuses src.config.resolve_device and src.preflight.check_ollama so there is one
definition of "which device" and "is Ollama usable".

    python scripts/doctor.py [--config configs/config.yaml]
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import EXAMPLE_CONFIG, load_config, resolve_device  # noqa: E402
from src.preflight import check_ollama_from_config  # noqa: E402

REQUIRED = ["requests", "yaml", "tqdm", "numpy", "fastapi", "uvicorn",
            "sentence_transformers", "chromadb", "sklearn", "fitz", "openpyxl"]
PKG_HINT = {"yaml": "pyyaml", "sklearn": "scikit-learn", "fitz": "pymupdf"}

results: list[tuple[str, str]] = []


def record(status: str, line: str) -> None:
    results.append((status, line))
    print(f"{status:4}  {line}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/config.yaml")
    args = ap.parse_args()

    # 1 -- Python
    v = sys.version_info
    record("PASS" if v >= (3, 10) else "FAIL",
           f"Python {v.major}.{v.minor}.{v.micro} (need >= 3.10)")

    # 2 -- packages
    missing = [PKG_HINT.get(m, m) for m in REQUIRED if importlib.util.find_spec(m) is None]
    record("PASS" if not missing else "FAIL",
           "required packages importable" if not missing
           else f"missing packages: {', '.join(missing)}  ->  pip install -r requirements.txt")

    # 3 -- config
    cfg = None
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        record("FAIL", f"config not found at {cfg_path}  ->  cp {EXAMPLE_CONFIG} {cfg_path}")
    else:
        try:
            cfg = load_config(cfg_path)
            record("PASS", f"config present and parses ({cfg_path})")
        except Exception as exc:
            record("FAIL", f"config at {cfg_path} does not parse: {type(exc).__name__}: {exc}")

    # 4 -- data directories
    if cfg is None:
        record("WARN", "data directories not checked (no usable config)")
    else:
        bad = []
        for key, path in (cfg.get("paths") or {}).items():
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                bad.append(f"{key}={path} ({type(exc).__name__})")
        record("PASS" if not bad else "FAIL",
               "configured data directories exist or can be created" if not bad
               else f"cannot create: {'; '.join(bad)}")

    # 5 -- GPU (WARN, never FAIL)
    configured = ((cfg or {}).get("embedding") or {}).get("device", "cpu")
    resolved = resolve_device(configured)
    if resolved.startswith("cuda"):
        record("PASS", f"GPU available; embedding device resolved to {resolved!r}")
    elif str(configured).strip().lower().startswith("cuda"):
        record("WARN", "CUDA requested but unavailable — running in CPU mode, "
                       "which is substantially slower")
    else:
        record("WARN", f"embedding device configured as {configured!r} — CPU mode, "
                       "which is substantially slower")

    # 6 + 7 -- Ollama reachable, model pulled (one probe, reused)
    if cfg is None:
        record("WARN", "Ollama not checked (no usable config)")
        record("WARN", "model presence not checked (no usable config)")
    else:
        pre = check_ollama_from_config(cfg)
        record("PASS" if pre["ollama_reachable"] else "FAIL",
               f"Ollama reachable at {pre['base_url']}" if pre["ollama_reachable"]
               else pre["message"])
        if pre["ollama_reachable"]:
            record("PASS" if pre["model_present"] else "FAIL",
                   f"model {pre['model']!r} is installed" if pre["model_present"]
                   else pre["message"])
        else:
            record("WARN", "model presence not checked (Ollama unreachable)")

    # 8 -- embedding model cached locally (WARN; never downloads)
    name = ((cfg or {}).get("embedding") or {}).get("model", "BAAI/bge-m3")
    slug = "models--" + str(name).replace("/", "--")
    import os
    roots = [Path(os.environ.get("HF_HOME", "")) / "hub" if os.environ.get("HF_HOME") else None,
             Path.home() / ".cache" / "huggingface" / "hub"]
    cached = any(r is not None and (r / slug).exists() for r in roots)
    record("PASS" if cached else "WARN",
           f"embedding model {name!r} is cached locally" if cached
           else f"embedding model {name!r} is not cached — it downloads (~2 GB) on first run")

    failed = sum(1 for s, _ in results if s == "FAIL")
    warned = sum(1 for s, _ in results if s == "WARN")
    print(f"\n{len(results)} checks: {len(results) - failed - warned} PASS, {warned} WARN, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
