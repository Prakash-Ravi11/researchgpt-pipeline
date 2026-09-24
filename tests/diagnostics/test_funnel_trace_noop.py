"""The funnel trace must be a no-op when its flag is off.

Additive: no existing test is touched. These pin the property the whole
diagnosis rests on -- that turning tracing on cannot change what the pipeline
does -- at the one place where it could go wrong, `funnel_trace.emit`.

The corpus-level version of the same proof is the trace_off / trace_on
output-hash comparison in `diagnostics/funnel/run_funnel.py`; this is the unit
form of it, runnable without the corpus.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "diagnostics" / "funnel"))

import funnel_trace as ft  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Every test decides the flag explicitly; none inherits the environment."""
    monkeypatch.delenv("RGPT_FUNNEL_TRACE", raising=False)
    yield
    ft.configure(None, "", "")


def test_config_default_is_off():
    """The shipped config must keep tracing off."""
    assert ft.config_flag() is False


def test_config_flag_absent_file_is_off(tmp_path):
    assert ft.config_flag(tmp_path / "nope.yaml") is False


def test_emit_writes_nothing_when_off(tmp_path, monkeypatch):
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "0")
    target = tmp_path / "nested" / "trace.jsonl"
    ft.configure(target, "run", "arm")
    for _ in range(50):
        ft.emit("A1", "table_block", "t0", "DROP", reason_code="X",
                code_location="f.py:1", detail={"a": 1})
    assert not target.exists()
    assert not target.parent.exists(), "emit must not even create its directory"


def test_emit_writes_nothing_when_unconfigured(tmp_path, monkeypatch):
    """On, but with no path: still nothing, and no exception."""
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "1")
    ft.configure(None, "run", "arm")
    ft.emit("A1", "table_block", "t0", "KEEP")


def test_emit_writes_rows_when_on(tmp_path, monkeypatch):
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "1")
    target = tmp_path / "trace.jsonl"
    ft.configure(target, "run7", "armA")
    ft.emit("A2", "grid_return", "p:0", "DROP", paper_id="p",
            reason_code="NO_GRID_FROM_BACKEND", code_location="x.py:386",
            detail={"extraction_path": "fallback"})
    rows = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    r = rows[0]
    assert r["run_id"] == "run7" and r["arm"] == "armA" and r["paper_id"] == "p"
    assert r["item_type"] == "grid_return" and r["status"] == "DROP"
    assert r["reason_code"] == "NO_GRID_FROM_BACKEND"
    assert r["code_location"] == "x.py:386"
    assert r["detail"] == {"extraction_path": "fallback"}


def test_unnamed_removal_is_unattributed_not_silent(tmp_path, monkeypatch):
    """A DROP with no reason code must be visible as UNATTRIBUTED."""
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "1")
    target = tmp_path / "trace.jsonl"
    ft.configure(target, "r", "a")
    ft.emit("S", "cell", "c1", "DROP", code_location="y.py:110")
    ft.emit("S", "cell", "c2", "KEEP")
    rows = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["reason_code"] == "UNATTRIBUTED"
    assert rows[1]["reason_code"] == ""


@pytest.mark.parametrize("bad", ["chunk", "paper", ""])
def test_bad_item_type_rejected(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "1")
    ft.configure(tmp_path / "t.jsonl", "r", "a")
    with pytest.raises(ValueError):
        ft.emit("S", bad, "i", "KEEP")


def test_bad_status_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "1")
    ft.configure(tmp_path / "t.jsonl", "r", "a")
    with pytest.raises(ValueError):
        ft.emit("S", "cell", "i", "REMOVED")


def test_bad_item_type_not_validated_when_off(tmp_path, monkeypatch):
    """Off means off: no validation, no cost, no raise."""
    monkeypatch.setenv("RGPT_FUNNEL_TRACE", "0")
    ft.configure(tmp_path / "t.jsonl", "r", "a")
    ft.emit("S", "not_a_real_type", "i", "NOT_A_STATUS")


def test_stable_ids():
    assert ft.table_id("pid", 3) == "pid:3"
    assert ft.cell_id("pid:3", 2, 5) == "pid:3#r2c5"
    assert ft.claim_id("pid", "results", 1) == "pid:results:1"


def test_src_does_not_import_funnel_trace():
    """Nothing in src/ may depend on the diagnostic module."""
    hits = [p for p in (ROOT / "src").rglob("*.py")
            if "funnel_trace" in p.read_text(encoding="utf-8", errors="replace")]
    assert hits == []
