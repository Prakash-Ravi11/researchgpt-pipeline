"""TASK 1 - full 60-paper acquisition rerun with the corrected 40 MB fetch cap.

Acquisition only (no retrieval, no LLM). Forces fresh fetches, rewrites the
per-paper cache, and emits a complete record + baseline A/B.

    python verify_acquisition.py
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from pipeline.acquire import acquire_paper  # noqa: E402
from pipeline.schema import FULL_TEXT, validate_acquisition_record  # noqa: E402

CORPUS = ROOT / "data" / "raw_metadata" / "collected_papers.json"
CACHE = HERE / "pipeline" / "cache"
ACQ_CACHE = CACHE / "_acq"
RUNS = HERE / "runs"


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-acqverify-{os.urandom(2).hex()}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    ACQ_CACHE.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    t0 = time.perf_counter()
    records = []
    for i, paper in enumerate(corpus, 1):
        rec, data = acquire_paper(paper, cache_dir=CACHE)  # fresh fetch, rewrites cache bytes
        (ACQ_CACHE / f"{paper['paperId']}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        records.append(rec)
        accepted = next((c for c in rec["candidates_considered"]
                         if c.get("identity_passed") and c.get("content_passed")), None)
        size = accepted.get("bytes") if accepted else None
        print(f"[{i:2}/60] {paper['paperId'][:12]} {rec['status']:24} src={str(rec['source']):16} "
              f"repr={rec['representation_type']:9} bytes={size} "
              f"idsim={rec['identity_validation'].get('signals', {}).get('title_similarity')}")
    elapsed = round(time.perf_counter() - t0, 1)

    baseline_ft = sum(1 for p in corpus if p.get("has_full_text"))
    new_ft = sum(1 for r in records if r["status"] == FULL_TEXT)
    base_ids = {p["paperId"] for p in corpus if p.get("has_full_text")}
    new_ids = {r["paper_id"] for r in records if r["status"] == FULL_TEXT}
    schema_problems = [pb for r in records for pb in validate_acquisition_record(r)]
    id_rej = sum(1 for r in records for c in r["candidates_considered"] if c.get("identity_passed") is False)
    ct_rej = sum(1 for r in records for c in r["candidates_considered"] if c.get("content_passed") is False)

    def sized(pred):
        out = []
        for r in records:
            if not pred(r):
                continue
            acc = next((c for c in r["candidates_considered"]
                        if c.get("identity_passed") and c.get("content_passed")), {})
            out.append(acc.get("bytes"))
        return out

    summary = {
        "run_id": run_id,
        "baseline_full_text": baseline_ft,
        "baseline_rate": round(baseline_ft / 60, 4),
        "canonical_full_text": new_ft,
        "canonical_rate": round(new_ft / 60, 4),
        "delta_papers": new_ft - baseline_ft,
        "delta_pp": round((new_ft - baseline_ft) / 60 * 100, 1),
        "recovered_vs_baseline": sorted(
            [(pid, next(r["source"] for r in records if r["paper_id"] == pid)) for pid in new_ids - base_ids]),
        "lost_vs_baseline": sorted(new_ids ^ new_ids if False else (base_ids - new_ids)),
        "status_distribution": dict(Counter(r["status"] for r in records)),
        "representation_distribution": dict(Counter(r["representation_type"] for r in records)),
        "full_text_source_distribution": dict(Counter(r["source"] for r in records if r["status"] == FULL_TEXT)),
        "identity_validation_candidate_rejections": id_rej,
        "content_validation_candidate_rejections": ct_rej,
        "wrong_paper_accepted": sum(
            1 for r in records if r["status"] == FULL_TEXT
            and r["identity_validation"].get("signals", {}).get("title_similarity", 0) < 0.3
            and not r["identity_validation"].get("signals", {}).get("doi_in_doc")),
        "schema_problems": schema_problems,
        "accepted_pdf_bytes_max": max([b for b in sized(lambda r: r["status"] == FULL_TEXT) if b], default=None),
        "elapsed_seconds": elapsed,
    }

    manifest = {
        "run_id": run_id, "task": "verify_40mb_acquisition_fix", "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_revision": git_rev(), "python": sys.version.split()[0], "platform": platform.platform(),
        "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "fetch_cap_bytes": 40_000_000, "credentials_used": False, "production_paths_touched": False,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (run_dir / "acquisition_records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        f"# TASK 1 - acquisition rerun with 40 MB cap ({run_id})", "",
        f"- git {manifest['git_revision'][:12]} - 60 papers - {elapsed}s - fetch cap 40 MB", "",
        f"- Baseline (shipped): **{baseline_ft}/60 ({summary['baseline_rate']:.1%})**",
        f"- Canonical post-fix: **{new_ft}/60 ({summary['canonical_rate']:.1%})**",
        f"- Gain: **{summary['delta_papers']:+d} papers ({summary['delta_pp']:+.1f} pp)**", "",
        f"- Status: {summary['status_distribution']}",
        f"- Representation: {summary['representation_distribution']}",
        f"- Full-text source: {summary['full_text_source_distribution']}",
        f"- Recovered vs baseline: {summary['recovered_vs_baseline']}",
        f"- Lost vs baseline: {summary['lost_vs_baseline'] or 'none'}",
        f"- Identity-validation candidate rejections: {id_rej}",
        f"- Content-validation candidate rejections: {ct_rej}",
        f"- **Wrong-paper accepted: {summary['wrong_paper_accepted']}**",
        f"- Largest accepted PDF: {summary['accepted_pdf_bytes_max']} bytes",
        f"- Schema problems: {schema_problems or 'none'}",
    ]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nwrote {run_dir}")


if __name__ == "__main__":
    main()
