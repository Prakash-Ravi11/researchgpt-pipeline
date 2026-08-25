"""
In-memory job tracking for long-running pipeline runs (topic search, bulk
corpus upload). A single-user local prototype doesn't need a real job
queue/database — an in-memory dict guarded by a lock is sufficient and keeps
this dependency-free.

Jobs are lost on server restart. That's an acceptable trade for a local
research tool; worth revisiting only if this ever needs to survive restarts
mid-run.
"""
import threading
import uuid
from datetime import datetime, timezone

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def create_job(job_type: str) -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "type": job_type,
            "stage": "queued",
            "progress": "",
            "status": "running",  # running | done | error
            "error": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    return job_id


def update_job(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def finish_job(job_id: str, error: str | None = None) -> None:
    update_job(
        job_id,
        status="error" if error else "done",
        stage="error" if error else "done",
        error=error,
    )