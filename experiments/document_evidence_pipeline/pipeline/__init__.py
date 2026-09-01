"""Experiment harness for the document-evidence pipeline.

The validated components now live in `src/evidence/` (FINAL_REPORT.md §O).
`schema`, `attribute`, `represent`, `chunker` here are thin re-export shims over
that single production copy; `acquire`, `index`, `extract`, `decide`, `run` are
experiment-only orchestration.
"""
import sys as _sys
from pathlib import Path as _Path

# make the repo root importable so `from src.evidence...` works when the
# experiment harness is run with this directory as cwd
_REPO_ROOT = _Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))
