"""EXP-LATEX-01 on Kaggle (target accelerator: T4 x2). Parts 7-10.

Purpose, per the protocol: GPU benchmarking, BGE-M3 embedding performance,
ingestion performance, VRAM measurement, and the two full 60-paper arms.

THE VALID COMPARISON IS WITHIN THIS NOTEBOOK: PDF-only vs LaTeX-aware on the
SAME Kaggle hardware. Numbers from the project's RTX 3050 history are NOT a
control for these and must not be differenced against them (Part 7).

Run order:
    python kaggle_exp_latex_01.py --stage env         # Part 7 capture
    python kaggle_exp_latex_01.py --stage benchmark   # Part 8, ~10 papers
    python kaggle_exp_latex_01.py --stage arm --arm control   # Part 9
    python kaggle_exp_latex_01.py --stage arm --arm latex     # Part 10
    python kaggle_exp_latex_01.py --stage analyze

Notes for the Kaggle session
----------------------------
* Ollama (qwen2.5:7b) drives Stage-4 extraction. It is NOT present on Kaggle by
  default. Stages that need it are skipped unless --with-extraction is passed
  AND an Ollama endpoint answers; the skip is recorded, never silently ignored.
  Without extraction, arms still measure acquisition, parsing, chunking,
  embedding, indexing, runtime and VRAM — but NOT the Part-11 D/E/F/G families.
* T4 is 16 GB, the project's reference GPU is 6 GB. The Part-15 VRAM gate
  (<= 5.5 GB) is a statement about local deployability; on T4 it is measured,
  not enforced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parent.parent
for p in (str(EXP), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import environment  # noqa: E402
import guard  # noqa: E402

BENCH_N = 10


# --- resource sampling ------------------------------------------------------

class PeakSampler:
    """Peak VRAM (per visible GPU) and peak RSS across a code block."""

    def __init__(self):
        self.peak_vram_mib = {}
        self.peak_ram_mib = 0.0
        self._torch = None
        try:
            import torch  # noqa: PLC0415
            self._torch = torch
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    torch.cuda.reset_peak_memory_stats(i)
        except Exception:  # noqa: BLE001
            pass

    def sample_ram(self):
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        self.peak_ram_mib = max(self.peak_ram_mib,
                                                float(line.split()[1]) / 1024.0)
        except Exception:  # noqa: BLE001
            pass

    def finish(self) -> dict:
        self.sample_ram()
        if self._torch is not None and self._torch.cuda.is_available():
            for i in range(self._torch.cuda.device_count()):
                self.peak_vram_mib[f"cuda:{i}"] = round(
                    self._torch.cuda.max_memory_allocated(i) / (1024 ** 2), 1)
        smi = _nvidia_peak()
        return {"peak_vram_mib_torch_allocated": self.peak_vram_mib,
                "nvidia_smi_memory_used_mib": smi,
                "peak_ram_mib": round(self.peak_ram_mib, 1),
                "vram_note": "torch max_memory_allocated is the process's tensor "
                             "allocation; nvidia-smi memory.used is the whole "
                             "device including other tenants. Report both."}


def _nvidia_peak():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        return [dict(zip(("index", "used_mib", "total_mib"), l.split(", ")))
                for l in out.splitlines() if l]
    except Exception:  # noqa: BLE001
        return "unavailable"


def ollama_available(base_url="http://localhost:11434") -> bool:
    try:
        import requests  # noqa: PLC0415
        return requests.get(f"{base_url}/api/tags", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


# --- Part 8: 10-paper benchmark --------------------------------------------

def stage_benchmark(args, out_root: Path):
    """Per-stage timings on ~10 representative papers, both arms."""
    corpus = json.loads(Path(args.corpus).read_text())
    papers = corpus.get("papers", corpus) if isinstance(corpus, dict) else corpus
    subset = papers[:BENCH_N]
    rows = []
    for arm, (latex, atomic) in (("control", ("0", "0")), ("latex", ("1", "1"))):
        os.environ["RQ_LATEX_CHUNKING"] = latex
        os.environ["RQ_TABLE_ATOMIC"] = atomic
        for paper in subset:
            rows.append(_benchmark_one(paper, arm, args))
    bench_dir = guard.assert_experiment_output(out_root / "metrics")
    bench_dir.mkdir(parents=True, exist_ok=True)
    (bench_dir / "benchmark_metrics.json").write_text(
        json.dumps({"experiment_id": "EXP-LATEX-01", "stage": "benchmark",
                    "n_papers": len(subset), "environment": environment.capture(REPO),
                    "rows": rows}, indent=2, default=str))
    if rows:
        import csv  # noqa: PLC0415
        keys = sorted({k for r in rows for k in r})
        with (bench_dir / "benchmark_metrics.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(f"wrote {bench_dir/'benchmark_metrics.json'} and .csv ({len(rows)} rows)")


def _benchmark_one(paper: dict, arm: str, args) -> dict:
    """Part 8's fifteen measurements for one paper."""
    from src.config import load_config  # noqa: PLC0415
    from src.processing.pdf_parser import process_paper_grounded  # noqa: PLC0415

    cfg = load_config(args.config)
    eg = cfg.get("evidence_grounding", {})
    pid = str(paper.get("paper_id") or paper.get("paperId") or "?")
    sampler = PeakSampler()
    row = {"arm": arm, "paper_id": pid}

    t0 = time.perf_counter()
    try:
        records = process_paper_grounded(
            paper, latex_parity_tolerance=eg.get("latex_parity_tolerance"))
        row["ingest_total_s"] = round(time.perf_counter() - t0, 4)
        row["n_chunks"] = len(records)
        tbl = [r for r in records if r.get("block_type") == "table"]
        row["n_table_chunks"] = len(tbl)
        blocks: dict[str, int] = {}
        for r in tbl:
            blocks[r.get("block_id", "")] = blocks.get(r.get("block_id", ""), 0) + 1
        row["n_tables"] = len(blocks)
        row["tables_split"] = sum(1 for v in blocks.values() if v > 1)
        row["tables_oversized"] = sum(1 for r in tbl if r.get("table_oversized"))
        row["n_figure_captions"] = sum(
            1 for r in records if r.get("block_type") == "figure_caption")
        row["n_equations_inline"] = sum(r.get("text", "").count("$") // 2 for r in records)
        row["representation"] = records[0].get("representation") if records else None
        row["structural_objects"] = row["n_tables"] + row["n_figure_captions"]
        row["error"] = ""
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["ingest_total_s"] = round(time.perf_counter() - t0, 4)

    # embedding + indexing, measured separately
    if not row.get("error") and args.with_embedding:
        try:
            texts = [r["text"] for r in records]
            t1 = time.perf_counter()
            model = _load_bge(args.embed_model, args.device)
            row["embed_model_load_s"] = round(time.perf_counter() - t1, 4)
            t2 = time.perf_counter()
            vecs = model.encode(texts, batch_size=args.batch_size,
                                show_progress_bar=False, normalize_embeddings=True)
            row["embed_s"] = round(time.perf_counter() - t2, 4)
            row["embed_chunks_per_s"] = (round(len(texts) / row["embed_s"], 3)
                                         if row["embed_s"] else None)
            row["embed_dim"] = int(getattr(vecs, "shape", [0, 0])[1]) if len(texts) else 0
        except Exception as exc:  # noqa: BLE001
            row["embed_error"] = f"{type(exc).__name__}: {exc}"
    row.update(sampler.finish())
    return row


_BGE = {}


def _load_bge(name: str, device: str):
    if name not in _BGE:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        _BGE[name] = SentenceTransformer(name, device=device)
    return _BGE[name]


# --- Parts 9/10: full arms --------------------------------------------------

def stage_arm(args, out_root: Path):
    import run_arm  # noqa: PLC0415
    sys.argv = ["run_arm.py", "--arm", args.arm, "--config", args.config,
                "--corpus", args.corpus, "--out", str(out_root / args.arm)]
    code = run_arm.main()
    if code:
        print(f"arm {args.arm} did not complete (exit {code})")
    return code


def stage_acquire(args, out_root: Path):
    """Stage 1 on Kaggle: seed the canonical 60 identities, then re-acquire.

    Uses the repository's own five-source resolver (`re_acquire_corpus`) — no new
    acquisition logic here. The seed is paper IDENTITIES only, hashed, extracted
    read-only from the frozen P1 artifact; PDFs/LaTeX are fetched fresh, so the
    acquisition outcome measured here is THIS run's, not the frozen one's.
    """
    import shutil  # noqa: PLC0415
    from src.config import load_config  # noqa: PLC0415
    from src.collection.semantic_scholar import re_acquire_corpus  # noqa: PLC0415

    seed = EXP / "corpus" / "canonical_60.json"
    meta = json.loads((EXP / "corpus" / "canonical_60.manifest.json").read_text())
    digest = hashlib.sha256(seed.read_bytes()).hexdigest()
    if digest != meta["sha256_canonical_60_json"]:
        raise SystemExit(f"corpus seed hash mismatch: {digest} != "
                         f"{meta['sha256_canonical_60_json']} — refusing to run "
                         f"an experiment on an unverified corpus.")
    cfg = load_config(args.config)
    meta_dir = Path(cfg["paths"]["raw_metadata_dir"])
    meta_dir.mkdir(parents=True, exist_ok=True)
    target = meta_dir / "collected_papers.json"
    if target.exists() and not args.force_reacquire:
        print(f"{target} exists; pass --force-reacquire to overwrite")
    else:
        shutil.copyfile(seed, target)
    papers = re_acquire_corpus(cfg)
    got = sum(1 for p_ in papers if p_.get("has_full_text"))
    rec = {"corpus": meta, "seed_sha256": digest,
           "acquired_full_text_this_run": got, "n_papers": len(papers),
           "frozen_any_source_full_text": meta["frozen_any_source_full_text"],
           "note": "acquired_full_text_this_run is MEASURED here; the frozen "
                   "figure is historical and is carried only for comparison.",
           "timestamp_utc": datetime.now(timezone.utc).isoformat()}
    d = guard.assert_experiment_output(out_root / "manifests")
    d.mkdir(parents=True, exist_ok=True)
    (d / "corpus_acquisition.json").write_text(json.dumps(rec, indent=2, default=str))
    print(f"full text this run: {got}/{len(papers)}  "
          f"(frozen historical: {meta['frozen_any_source_full_text']}/60)")
    print(f"corpus manifest -> {target}")


def stage_env(args, out_root: Path):
    env = environment.capture(REPO)
    env["ollama_available"] = ollama_available(args.ollama_url)
    env["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    env["kaggle"] = {k: v for k, v in os.environ.items() if "KAGGLE" in k.upper()}
    d = guard.assert_experiment_output(out_root / "manifests")
    d.mkdir(parents=True, exist_ok=True)
    p = d / "kaggle_environment.json"
    p.write_text(json.dumps(env, indent=2, default=str))
    print(json.dumps({"gpu": env["gpu"], "ollama": env["ollama_available"]},
                     indent=2, default=str))
    print(f"wrote {p}")
    if not env["gpu"].get("torch_cuda_available"):
        print("\nWARNING: no CUDA device. Runtime and VRAM figures from this "
              "session are not comparable to a GPU run and must not be reported "
              "as GPU measurements.")


def stage_analyze(args, out_root: Path):
    import analyze  # noqa: PLC0415
    analyze.run("control", "latex", out_root)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=["env", "acquire", "benchmark", "arm", "analyze"])
    ap.add_argument("--arm", default="control")
    ap.add_argument("--config", default="configs/staging_config.yaml")
    ap.add_argument("--corpus", default="data/raw_metadata/collected_papers.json")
    ap.add_argument("--out", default=guard.EXPERIMENT_ROOT)
    ap.add_argument("--embed-model", default="BAAI/bge-m3")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--with-embedding", action="store_true")
    ap.add_argument("--with-extraction", action="store_true")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--force-reacquire", action="store_true")
    args = ap.parse_args()

    out_root = Path(guard.assert_experiment_output(args.out))
    guard.ensure_tree(out_root)
    return {"env": stage_env, "acquire": stage_acquire,
            "benchmark": stage_benchmark, "arm": stage_arm,
            "analyze": stage_analyze}[args.stage](args, out_root) or 0


if __name__ == "__main__":
    sys.exit(main())
