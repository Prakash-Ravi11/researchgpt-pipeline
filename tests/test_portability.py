"""Portability tests — headless. No GPU, no Ollama, no data required."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.config as config  # noqa: E402
from src.preflight import check_ollama  # noqa: E402


def test_resolve_device_falls_back_to_cpu_without_cuda(monkeypatch):
    """A configured cuda device becomes cpu when CUDA is unavailable, and is
    left alone when it is available."""
    class _FakeCuda:
        def __init__(self, available):
            self._available = available

        def is_available(self):
            return self._available

    class _FakeTorch:
        def __init__(self, available):
            self.cuda = _FakeCuda(available)

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(False))
    monkeypatch.setattr(config, "_device_warned", False, raising=False)
    assert config.resolve_device("cuda") == "cpu"
    assert config.resolve_device("cuda:0") == "cpu"
    assert config.resolve_device("cpu") == "cpu"

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(True))
    assert config.resolve_device("cuda") == "cuda"
    assert config.resolve_device("cpu") == "cpu"


def test_missing_config_message_and_nonzero_exit(tmp_path):
    """run_pipeline.py with an absent config prints the copy instruction and exits non-zero."""
    missing = tmp_path / "nope.yaml"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "run_pipeline.py"), "--config", str(missing)],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "Config file not found" in out
    assert "configs/config.example.yaml" in out


def test_preflight_reports_unreachable_host():
    """An unused port yields a clear, actionable failure rather than an exception."""
    res = check_ollama("http://127.0.0.1:1", "qwen2.5:7b", timeout=2.0)
    assert res["ok"] is False
    assert res["ollama_reachable"] is False
    assert res["model_present"] is False
    assert "not reachable" in res["message"]
    assert "ollama serve" in res["message"]
