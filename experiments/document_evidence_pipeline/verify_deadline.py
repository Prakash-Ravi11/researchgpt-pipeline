"""3.2a STEP 3 — verify the hard wall-clock deadline + num_predict cap fire.

Runs Stage-4 extraction on 9879e1cce9 (medical corpus, the 7.6 h hang) alone,
seeded:
  (a) with the real config  (deadline 240 s, num_predict 768)  -> report elapsed + outcome
  (b) with extraction_deadline_seconds = 3  -> confirm the deadline trips, the paper
      is recorded _extraction_failed / wall_clock_exceeded, and the call returns promptly

  python -u experiments/document_evidence_pipeline/verify_deadline.py
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.summarization import summarize as S

ROOT = Path(__file__).resolve().parents[2]
PID = "9879e1cce9918b9f5eb4b0a8e14494a834f91102"
BASE = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b",
        "timeout_seconds": 300, "temperature": 0, "seed": 42}

ch = json.loads((ROOT / "data/processed/chunks.json").read_text(encoding="utf-8"))
pcs = sorted([c for c in ch if c["paper_id"] == PID], key=lambda c: c["chunk_index"])
# legacy-style assembly (medical is legacy schema)
words, parts = 0, []
for c in pcs:
    w = c["text"].split()
    take = w[:2500 - words]
    parts.append(" ".join(take)); words += len(take)
    if words >= 2500:
        break
paper = {"paper_id": PID, "title": pcs[0]["title"], "year": pcs[0]["year"],
         "venue": pcs[0]["venue"], "text": " ".join(parts)}
print(f"paper {PID[:12]}  assembled {words} words  ({len(pcs)} chunks)\n")

for label, extra in (("(a) real config (deadline 240, num_predict 768)", {}),
                     ("(b) deadline forced to 3 s", {"extraction_deadline_seconds": 3})):
    S.prime_ollama_cache({**BASE})
    t0 = time.time()
    _, ex = S._extract_single_paper(PID, paper, {**BASE, **extra}, cache={}, processed_dir=None)
    dt = time.time() - t0
    print(f"{label}")
    print(f"   elapsed        : {dt:.1f} s")
    print(f"   _conformance   : {ex.get('_conformance')}")
    print(f"   _extraction_failed : {ex.get('_extraction_failed')}")
    print(f"   _failure_reason: {ex.get('_failure_reason')}   _elapsed_s: {ex.get('_elapsed_s')}")
    filled = [k for k in S._EXTRACTION_SCHEMA_KEYS
              if (ex.get(k) if k in ('datasets', 'metrics') else str(ex.get(k, '')).strip())]
    print(f"   non-empty fields (must be 0 for a failure, never silent-empty pass): {filled}")
    print(f"   process continued to here: YES\n")
