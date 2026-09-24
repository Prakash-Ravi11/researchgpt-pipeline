"""JSONL funnel trace. A no-op unless `funnel_trace_enabled` is on.

DIAGNOSTIC ONLY. Nothing in `src/` imports this module. When the flag is off,
`emit()` returns before touching the filesystem, so a traced run and an untraced
run execute the same code with the same side effects (proved by
`tests/diagnostics/test_funnel_trace_noop.py` and by the trace_off / trace_on
output-hash comparison in `run_funnel.py`).

The flag lives at `evidence_grounding.funnel_trace_enabled` in
`configs/staging_config.yaml`. `RGPT_FUNNEL_TRACE` overrides it, which is how the
driver passes the decision to a worker subprocess without re-reading YAML in
every one of the 21 processes.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

# One item is one row. These are the only legal values; analyze_funnel.py asserts it.
ITEM_TYPES = frozenset({
    "table_block", "cell_table", "fallback_table", "cell", "row",
    "grid_return", "result", "claim", "candidate", "binding_attempt",
})
STATUSES = frozenset({"KEEP", "DROP", "PASS", "FAIL"})

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "staging_config.yaml"
_lock = threading.Lock()
_state: dict[str, Any] = {"path": None, "run_id": None, "arm": None}


def config_flag(config_path: Path | str = _CONFIG) -> bool:
    """`evidence_grounding.funnel_trace_enabled`, default False.

    Read with a line scan rather than yaml.safe_load: this must not fail, and
    must not import anything, when the config is absent or partly written.
    """
    try:
        for raw in Path(config_path).read_text(encoding="utf-8").splitlines():
            key, _, val = raw.partition(":")
            if key.strip() == "funnel_trace_enabled":
                return val.split("#")[0].strip().lower() == "true"
    except OSError:
        pass
    return False


def enabled() -> bool:
    """Env override first, then the config flag. Off unless explicitly on."""
    env = os.environ.get("RGPT_FUNNEL_TRACE")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return config_flag()


def configure(path: Path | str | None, run_id: str, arm: str) -> None:
    """Point the trace at a file. Does not create it — `emit` does, on first row."""
    _state.update(path=(Path(path) if path else None), run_id=run_id, arm=arm)


def emit(stage: str, item_type: str, item_id: str, status: str, *,
         paper_id: str = "", parent_id: str = "", reason_code: str = "",
         detail: Any = None, code_location: str = "") -> None:
    """Append one row. Returns immediately, touching nothing, when tracing is off.

    A removal that cannot be attributed to a condition in the code is emitted
    with reason_code UNATTRIBUTED and its code_location, never dropped silently.
    """
    if not enabled() or _state["path"] is None:
        return
    if item_type not in ITEM_TYPES:
        raise ValueError(f"item_type {item_type!r} not in {sorted(ITEM_TYPES)}")
    if status not in STATUSES:
        raise ValueError(f"status {status!r} not in {sorted(STATUSES)}")
    row = {
        "run_id": _state["run_id"], "arm": _state["arm"], "paper_id": paper_id,
        "stage": stage, "item_type": item_type, "item_id": item_id,
        "parent_id": parent_id, "status": status,
        "reason_code": reason_code or ("" if status in ("KEEP", "PASS") else "UNATTRIBUTED"),
        "detail": detail, "code_location": code_location,
    }
    line = json.dumps(row, default=str, ensure_ascii=False)
    with _lock:
        p: Path = _state["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# ---- stable IDs (STAGE_DEFINITIONS.md section 5) ---------------------------

def table_id(paper_id: str, index: int) -> str:
    return f"{paper_id}:{index}"


def cell_id(tid: str, row: Any, col: Any) -> str:
    return f"{tid}#r{row}c{col}"


def claim_id(paper_id: str, field: str, index: int) -> str:
    return f"{paper_id}:{field}:{index}"
