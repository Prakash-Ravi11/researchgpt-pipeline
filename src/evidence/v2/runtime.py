"""Atomic artifacts, append-only execution ledger and killable local workers."""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from . import POLICY_VERSION, PROMPT_VERSION, SCHEMA_VERSION
from .contracts import identity
from src.evidence.monitor import atomic_json_write

@dataclass(frozen=True)
class Config:
    enabled: bool = False
    document_seconds: float = 120
    parser_seconds: float = 45
    max_model_requests: int = 6
    request_seconds: float = 30
    max_regions: int = 2
    max_actions_per_region: int = 2
    local_model_enabled: bool = False
    cache_directory: str | None = None

    def __post_init__(self):
        if min(self.document_seconds, self.parser_seconds, self.request_seconds) <= 0:
            raise ValueError("Deadlines must be positive")
        if not 0 <= self.max_model_requests <= 6 or not 0 <= self.max_regions <= 2 or not 0 <= self.max_actions_per_region <= 2:
            raise ValueError("Configured budget exceeds frozen initial safety bounds")

def append_event(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

def write_jsonl(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def cache_key(document, model, config):
    import hashlib
    code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    settings = {k:v for k,v in vars(config).items() if k != "cache_directory"}
    tokenizer_hashes={}
    if model and model.get("tokenizer_path"):
        for name in ("tokenizer.json","tokenizer_config.json"):
            path=Path(model["tokenizer_path"])/name
            tokenizer_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return identity({"document": document, "implementation": code, "model": model,
                     "tokenizer_files":tokenizer_hashes,"config": settings,
                     "policy": POLICY_VERSION, "schema": SCHEMA_VERSION, "prompt": PROMPT_VERSION})


def terminate_owned(process):
    """Terminate the owned Windows launcher and descendants, then reap it."""
    if process.poll() is not None:
        return
    if os.name=="nt":
        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    else:
        process.kill()
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def run_model_request(request,directory,seconds):
    """Reuse October's worker/protocol with an owned process-tree timeout boundary."""
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    request_path=folder/"request.json";response_path=folder/"response.json"
    atomic_json_write(request_path,request)
    command=[sys.executable,"-B","-m","src.evidence.prose_attribution.request_worker",
             "--request",str(request_path.resolve()),"--response",str(response_path.resolve())]
    started=time.monotonic()
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    timeout=False
    try:
        stdout,stderr=child.communicate(timeout=max(.001,seconds))
    except subprocess.TimeoutExpired:
        timeout=True
        terminate_owned(child)
        stdout,stderr=child.communicate()
    elapsed=time.monotonic()-started
    result=json.loads(response_path.read_text(encoding="utf-8")) if response_path.is_file() else {"parsed":None}
    completion={}
    raw=folder/"raw_response.ndjson"
    if raw.is_file():
        for line in raw.read_text(encoding="utf-8").splitlines():
            try:
                row=json.loads(line)
                if row.get("done"):completion=row
            except ValueError:
                continue
    result.update(host_elapsed_s=elapsed,hard_timeout=timeout,worker_exit_code=child.returncode,
                  stdout=stdout.decode("utf-8",errors="replace"),stderr=stderr.decode("utf-8",errors="replace"),
                  completion=completion)
    if timeout or elapsed>seconds:
        result.update(parsed=None,late_completion_rejected=True,completion_before_guard=completion,
                      completion={**completion,"done_reason":"deadline_exceeded"})
    atomic_json_write(folder/"host_result.json",result)
    return result

def parse_bounded(source, paper_id, directory, seconds):
    folder = Path(directory); folder.mkdir(parents=True, exist_ok=True)
    output = folder / "parsed.json"
    command = [sys.executable, "-B", "-m", "src.evidence.v2.worker",
               "--source", str(Path(source).resolve()), "--paper-id", paper_id, "--output", str(output)]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        terminate_owned(process)
        stdout, stderr = process.communicate()
        atomic_json_write(folder / "parser_completion.json", {"state": "timeout",
            "elapsed_seconds": time.monotonic()-started, "exit_code": process.returncode})
        return None, "parser_timeout"
    finally:
        if process.poll() is None:
            terminate_owned(process)
    record = {"state": "complete" if process.returncode == 0 else "error",
              "elapsed_seconds": time.monotonic()-started, "exit_code": process.returncode,
              "stderr": stderr.decode("utf-8", errors="replace")}
    atomic_json_write(folder / "parser_completion.json", record)
    if process.returncode or not output.exists():
        return None, "parser_error"
    return json.loads(output.read_text(encoding="utf-8")), None
