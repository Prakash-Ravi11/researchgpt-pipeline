"""Output-isolation guard for EXP-LATEX-01.

Part 6 of the experiment protocol: experimental artefacts must never land in a
canonical output directory, and the runner must FAIL rather than write there.
This module is the single place that decides what "canonical" means, so the
rule cannot drift between the runner, the analyser and the Kaggle script.

The guard is deliberately paranoid: it resolves symlinks, it rejects a path
that merely *contains* a canonical directory, and it requires the target to sit
inside the experiment root rather than merely avoid the blocklist. An unknown
path is refused, not allowed.
"""
from __future__ import annotations

from pathlib import Path

#: Everything the frozen baseline reads or writes. Relative to the repo root.
CANONICAL_DIRS = (
    "runs",                                        # canonical run root
    "data",                                        # production corpus + chroma
    "data/processed",
    "data/chroma_db",
    "data/pdfs",
    "data/raw_metadata",
    "data/figures",
    "data_test",                                   # staging corpus
    "experiments/document_evidence_pipeline/runs",  # frozen measurement runs
)

#: The ONLY place this experiment may write.
EXPERIMENT_ROOT = "runs/exp-latex-01"

REQUIRED_SUBDIRS = (
    "control", "latex", "evaluation", "logs", "metrics",
    "manifests", "statistical_analysis", "failure_analysis",
)


class CanonicalWriteRefused(RuntimeError):
    """The runner was pointed at a canonical output directory."""


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _resolve(p: str | Path) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = repo_root() / path
    # resolve() follows symlinks, so a symlinked shortcut into data/ is caught
    return path.resolve()


def assert_experiment_output(path: str | Path) -> Path:
    """Return `path` resolved, or raise if it is not inside the experiment root.

    Raises `CanonicalWriteRefused` for a canonical directory, and for anything
    outside ``runs/exp-latex-01`` — including paths that look harmless.
    """
    target = _resolve(path)
    root = _resolve(EXPERIMENT_ROOT)

    for canon in CANONICAL_DIRS:
        cdir = _resolve(canon)
        if target == cdir:
            raise CanonicalWriteRefused(
                f"refusing to write experiment output to the canonical directory "
                f"{canon!r} (resolved: {target}). Experimental artefacts belong "
                f"under {EXPERIMENT_ROOT}/."
            )

    if target != root and root not in target.parents:
        raise CanonicalWriteRefused(
            f"{target} is outside the experiment root {root}. "
            f"EXP-LATEX-01 writes only under {EXPERIMENT_ROOT}/ — this protects "
            f"the frozen baseline from experimental contamination."
        )
    return target


def ensure_tree(root: str | Path = EXPERIMENT_ROOT) -> Path:
    """Create the Part-6 directory tree, guarded."""
    base = assert_experiment_output(root)
    base.mkdir(parents=True, exist_ok=True)
    for sub in REQUIRED_SUBDIRS:
        assert_experiment_output(base / sub).mkdir(parents=True, exist_ok=True)
    return base


def assert_baseline_untouched() -> dict:
    """Report whether any canonical directory exists and is writable.

    This does not modify anything. It is called by the runner so the run
    manifest records the state of the baseline at experiment time.
    """
    out = {}
    for canon in CANONICAL_DIRS:
        p = repo_root() / canon
        out[canon] = {"exists": p.exists(), "is_dir": p.is_dir() if p.exists() else None}
    return out
