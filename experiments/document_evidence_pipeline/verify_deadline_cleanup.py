"""3.2d STEP 1 — verify the deadline path CLEANS UP (no leaked socket / thread).

Forces a 3 s deadline on 9879e1cce9 FIVE times in succession, seeded.  Reports per
iteration: live thread count, surviving worker-thread names, elapsed.  After the
fifth: Ollama responsiveness.  A rising thread count or creeping elapsed = leak.

  python -u experiments/document_evidence_pipeline/verify_deadline_cleanup.py
"""
from __future__ import annotations
import json, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import requests
from src.summarization import summarize as S

ROOT = Path(__file__).resolve().parents[2]
PID = "9879e1cce9918b9f5eb4b0a8e14494a834f91102"
CFG = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "timeout_seconds": 300,
       "temperature": 0, "seed": 42, "extraction_deadline_seconds": 3}

ch = json.loads((ROOT / "data/processed/chunks.json").read_text(encoding="utf-8"))
pcs = sorted([c for c in ch if c["paper_id"] == PID], key=lambda c: c["chunk_index"])
w, parts = 0, []
for c in pcs:
    t = c["text"].split()[:2500 - w]
    parts.append(" ".join(t)); w += len(t)
    if w >= 2500:
        break
paper = {"paper_id": PID, "title": pcs[0]["title"], "year": pcs[0]["year"],
         "venue": pcs[0]["venue"], "text": " ".join(parts)}

baseline_threads = threading.active_count()
baseline_names = sorted(t.name for t in threading.enumerate())
print(f"baseline: active_count={baseline_threads}  names={baseline_names}\n")

def non_main_workers():
    return sorted(t.name for t in threading.enumerate()
                  if t is not threading.main_thread() and not t.name.startswith(("pydevd", "SockThread")))

elapseds = []
for i in range(1, 6):
    S.prime_ollama_cache({**CFG})
    t0 = time.time()
    _, ex = S._extract_single_paper(PID, paper, {**CFG}, cache={}, processed_dir=None)
    dt = time.time() - t0
    elapseds.append(dt)
    time.sleep(1.0)  # let any orphan settle before we count
    print(f"iter {i}: elapsed={dt:5.1f}s  conformance={ex.get('_conformance'):18} "
          f"failed={ex.get('_extraction_failed')}  reason={ex.get('_failure_reason')}")
    print(f"         active_count={threading.active_count()}  non-main workers={non_main_workers()}")

print(f"\nelapsed per iter: {[round(e,1) for e in elapseds]}  (must stay ~3s, no upward creep)")
print(f"thread count baseline {baseline_threads} -> final {threading.active_count()}  "
      f"(must not rise)")

# Ollama responsiveness + request count
try:
    ps = requests.get("http://localhost:11434/api/ps", timeout=10).json()
    print(f"\nOllama /api/ps after 5 iters: {len(ps.get('models', []))} model(s) loaded, responsive=YES")
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5:7b", "messages": [{"role": "user", "content": "reply OK"}],
        "stream": False, "options": {"num_predict": 5, "temperature": 0, "seed": 42}}, timeout=60)
    print(f"  trivial follow-up request: HTTP {r.status_code}, done_reason={r.json().get('done_reason')}")
except Exception as e:
    print(f"\nOllama NOT responsive after 5 iters: {e!r}")
