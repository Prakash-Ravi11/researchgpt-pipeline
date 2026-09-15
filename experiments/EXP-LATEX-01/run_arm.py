"""EXP-LATEX-01 arm runner.

One arm = one (RQ_LATEX_CHUNKING, RQ_TABLE_ATOMIC) setting run over the
canonical corpus, writing ONLY into runs/exp-latex-01/<arm>/.

    python experiments/EXP-LATEX-01/run_arm.py --arm control
    python experiments/EXP-LATEX-01/run_arm.py --arm latex
    python experiments/EXP-LATEX-01/run_arm.py --arm atomic        # factorial
    python experiments/EXP-LATEX-01/run_arm.py --arm latex_atomic  # factorial

Design notes
------------
* The runner NEVER writes outside the experiment root — `guard` enforces it on
  every path, and `--out` pointing at a canonical directory is a hard failure.
* It performs a preflight FIRST. If the environment cannot run the arm (no GPU,
  no torch, no corpus, no Ollama) it writes a preflight report explaining
  exactly what is missing and exits non-zero. It does not produce a partial
  per_paper.json that would later be mistaken for a measurement.
* Flags are set in this process's environment before the pipeline is imported,
  so the arm selection is in effect for the whole run and is recorded verbatim
  in the manifest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

import environment  # noqa: E402
import guard  # noqa: E402

ARMS = {
    "control":      {"RQ_LATEX_CHUNKING": "0", "RQ_TABLE_ATOMIC": "0",
                     "role": "CONTROL — PDF-only pipeline (Part 4)"},
    "latex":        {"RQ_LATEX_CHUNKING": "1", "RQ_TABLE_ATOMIC": "1",
                     "role": "TREATMENT — LaTeX-aware + atomic tables (Part 4)"},
    "atomic":       {"RQ_LATEX_CHUNKING": "0", "RQ_TABLE_ATOMIC": "1",
                     "role": "FACTORIAL — atomic tables alone, isolates the "
                             "secondary hypothesis from LaTeX ingestion"},
    "latex_only":   {"RQ_LATEX_CHUNKING": "1", "RQ_TABLE_ATOMIC": "0",
                     "role": "FACTORIAL — LaTeX ingestion alone; reproduces the "
                             "Phase-4/5x configuration that measured negative"},
}


def preflight(arm: str, out_dir: Path, corpus: Path | None) -> dict:
    missing = environment.missing_requirements()
    problems = list(missing)
    if corpus is not None and not corpus.exists():
        problems.append(f"corpus manifest not found: {corpus}")
    gpu = environment.gpu_info()
    if not gpu.get("torch_cuda_available"):
        problems.append("no CUDA device visible (BGE-M3 would run on CPU; the "
                        "runtime and VRAM metrics in Part 11 would be meaningless)")
    report = {
        "arm": arm,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "can_run": not problems,
        "blocking_problems": problems,
        "environment": environment.capture(REPO),
        "baseline_state": guard.assert_baseline_untouched(),
    }
    path = guard.assert_experiment_output(out_dir / "preflight.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str))
    return report


def write_manifest(arm: str, out_dir: Path, cfg_path: str, corpus: Path | None,
                   extra: dict | None = None) -> Path:
    spec = ARMS[arm]
    manifest = {
        "experiment_id": "EXP-LATEX-01",
        "arm": arm,
        "role": spec["role"],
        "flags": {k: v for k, v in spec.items() if k.startswith("RQ_")},
        "config": cfg_path,
        "corpus_manifest": str(corpus) if corpus else None,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment.capture(REPO),
        "output_dir": str(out_dir),
    }
    manifest.update(extra or {})
    p = guard.assert_experiment_output(out_dir / "manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, default=str))
    return p


def run_pipeline_arm(arm: str, cfg_path: str, out_dir: Path, corpus: Path) -> dict:
    """Execute one arm over the corpus. Requires a working environment."""
    from src.config import load_config                      # noqa: PLC0415
    from src.processing.pdf_parser import process_paper_grounded  # noqa: PLC0415
    from src.evidence.chunker import chunk_document          # noqa: PLC0415

    cfg = load_config(cfg_path)
    eg = cfg.get("evidence_grounding", {})
    papers = json.loads(corpus.read_text())
    if isinstance(papers, dict):
        papers = papers.get("papers", [])

    per_paper: dict[str, dict] = {}
    all_chunks: list[dict] = []
    failures: list[dict] = []
    t_arm = time.perf_counter()
    for i, paper in enumerate(papers, 1):
        pid = str(paper.get("paper_id") or paper.get("paperId") or f"idx{i}")
        t0 = time.perf_counter()
        try:
            records = process_paper_grounded(
                paper, latex_parity_tolerance=eg.get("latex_parity_tolerance"))
            elapsed = time.perf_counter() - t0
            all_chunks.extend(records)
            tbl = [r for r in records if r.get("block_type") == "table"]
            by_block: dict[str, int] = {}
            for r in tbl:
                by_block[r.get("block_id", "")] = by_block.get(r.get("block_id", ""), 0) + 1
            per_paper[pid] = {
                "n_chunks": len(records),
                "n_table_chunks": len(tbl),
                "tables_split": sum(1 for v in by_block.values() if v > 1),
                "tables_oversized": sum(1 for r in tbl if r.get("table_oversized")),
                "runtime_total_s": round(elapsed, 4),
                "representation": (records[0].get("representation") if records else None),
            }
        except Exception as exc:  # noqa: BLE001
            failures.append({"paper_id": pid, "stage": "process_paper_grounded",
                             "error": f"{type(exc).__name__}: {exc}"})
        if i % 10 == 0:
            print(f"  ... {i}/{len(papers)} papers", flush=True)

    out = {"arm": arm, "n_papers": len(papers),
           "arm_runtime_s": round(time.perf_counter() - t_arm, 3),
           "papers": per_paper}
    # Persist THIS arm's chunks in an arm-scoped processed dir. Stage 4 must read
    # the chunks the arm produced — pointing it at the canonical processed_dir
    # would feed both arms identical input and silently void the experiment.
    proc = guard.assert_experiment_output(out_dir / "processed")
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "chunks.json").write_text(json.dumps(all_chunks, default=str))
    out["n_chunks_total"] = len(all_chunks)
    guard.assert_experiment_output(out_dir / "per_paper.json").write_text(
        json.dumps(out, indent=2, default=str))
    guard.assert_experiment_output(out_dir / "failures.json").write_text(
        json.dumps({"arm": arm, "n_failures": len(failures),
                    "failures": failures}, indent=2))
    return out


def ollama_up(base_url: str) -> bool:
    try:
        import requests  # noqa: PLC0415
        return requests.get(f"{base_url}/api/tags", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _arm_config(cfg: dict, out_dir: Path, arm: str) -> dict:
    """Same config, with every output path redirected into this arm."""
    c = json.loads(json.dumps(cfg))
    c.setdefault("paths", {})
    c["paths"]["processed_dir"] = str(guard.assert_experiment_output(out_dir / "processed"))
    c["paths"]["chroma_dir"] = str(guard.assert_experiment_output(out_dir / "chroma"))
    c.setdefault("system", {})["collection_name"] = f"exp_latex_01_{arm}"
    return c


def run_extraction_arm(arm: str, cfg_path: str, out_dir: Path, ollama_url: str) -> dict:
    """Stage 3 + Stage 4 for ONE arm, over that arm's own chunks.

    Index and extract with the project's existing functions — no new extraction
    logic. Selection mode, prompt, seed, temperature and
    EXTRACTION_OUTPUT_RESERVATION are whatever the config says, so the arms
    differ only in the chunks they were given.
    """
    from src.config import load_config                                  # noqa: PLC0415
    from src.embedding.build_index import (build_collection, embed_chunks,  # noqa: PLC0415
                                           load_model)
    from src.summarization.summarize import (_EXTRACTION_SCHEMA_KEYS,   # noqa: PLC0415
                                             _field_has_content,
                                             extract_paper_fields,
                                             load_extraction_cache,
                                             reconstruct_paper_texts)

    cfg = _arm_config(load_config(cfg_path), out_dir, arm)
    proc = Path(cfg["paths"]["processed_dir"])
    chunks = json.loads((proc / "chunks.json").read_text())
    if not chunks:
        raise SystemExit(f"{proc/'chunks.json'} is empty — run the arm's "
                         f"ingestion before --with-extraction.")

    t0 = time.perf_counter()
    model = load_model(cfg["embedding"]["model"], cfg["embedding"]["device"])
    vecs = embed_chunks(model, chunks)
    t_embed = time.perf_counter() - t0
    t1 = time.perf_counter()
    build_collection(chunks, vecs, cfg["paths"]["chroma_dir"],
                     cfg["system"]["collection_name"])
    t_index = time.perf_counter() - t1

    max_words = cfg["llm"].get("max_context_words", 2500)
    if cfg.get("summarization", {}).get("context_selection") == "retrieval_aware":
        from src.summarization.retrieval_aware import (                 # noqa: PLC0415
            build_retrieval_aware_papers)
        papers = build_retrieval_aware_papers(cfg, max_words)
    else:
        papers = reconstruct_paper_texts(chunks, max_words)

    t2 = time.perf_counter()
    extractions = extract_paper_fields(papers, cfg["llm"], cache=load_extraction_cache(str(proc)),
                                       processed_dir=str(proc))
    t_extract = time.perf_counter() - t2

    per_paper, fails = {}, []
    for pid, ex in extractions.items():
        n = sum(1 for f in _EXTRACTION_SCHEMA_KEYS if _field_has_content(ex.get(f)))
        per_paper[pid] = {
            "evidence_fields_nonempty": n,
            "extraction_failed": bool(ex.get("_extraction_failed")),
            "selection_fallback": bool(ex.get("_selection_fallback")),
            "conformance": ex.get("_conformance"),
            "done_reason": ex.get("_done_reason"),
        }
        if ex.get("_extraction_failed") or n == 0:
            fails.append({"paper_id": pid, "stage": "extraction",
                          "category": "model/runtime",
                          "n_fields": n,
                          "done_reason": ex.get("_done_reason"),
                          "conformance": ex.get("_conformance")})

    res = {"arm": arm, "n_papers": len(papers), "n_chunks": len(chunks),
           "runtime_embed_s": round(t_embed, 3), "runtime_index_s": round(t_index, 3),
           "runtime_extract_s": round(t_extract, 3),
           "ollama_url": ollama_url, "model": cfg["llm"]["model"],
           "selection_mode": (cfg.get("selection") or {}).get("mode"),
           "extraction_output_reservation": cfg["llm"].get("extraction_output_reservation"),
           "papers": per_paper}
    guard.assert_experiment_output(out_dir / "extraction.json").write_text(
        json.dumps(res, indent=2, default=str))
    guard.assert_experiment_output(out_dir / "extractions_raw.json").write_text(
        json.dumps(extractions, indent=2, default=str))

    # merge the extraction metrics into per_paper.json WITHOUT dropping ingestion keys
    pp_path = guard.assert_experiment_output(out_dir / "per_paper.json")
    if pp_path.exists():
        pp = json.loads(pp_path.read_text())
        for pid, m in per_paper.items():
            pp["papers"].setdefault(pid, {}).update(m)
        pp["extraction"] = {k: v for k, v in res.items() if k != "papers"}
        pp_path.write_text(json.dumps(pp, indent=2, default=str))

    fpath = guard.assert_experiment_output(out_dir / "failures.json")
    existing = json.loads(fpath.read_text()) if fpath.exists() else {"failures": []}
    existing["failures"] = existing.get("failures", []) + fails
    existing["n_failures"] = len(existing["failures"])
    fpath.write_text(json.dumps(existing, indent=2, default=str))
    return res


def main():
    ap = argparse.ArgumentParser(description="Run one EXP-LATEX-01 arm.")
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--config", default="configs/staging_config.yaml")
    ap.add_argument("--corpus", default=None,
                    help="JSON manifest of the canonical corpus (collected_papers.json)")
    ap.add_argument("--out", default=None,
                    help="output dir; defaults to runs/exp-latex-01/<arm>")
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--with-extraction", action="store_true",
                    help="also run Stage 3 + Stage 4 (needs Ollama)")
    ap.add_argument("--extraction-only", action="store_true",
                    help="skip ingestion; extract from this arm's existing chunks.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    a = ap.parse_args()

    spec = ARMS[a.arm]
    for k, v in spec.items():
        if k.startswith("RQ_"):
            os.environ[k] = v

    out_dir = Path(guard.assert_experiment_output(
        a.out or f"{guard.EXPERIMENT_ROOT}/{a.arm}"))
    guard.ensure_tree()
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus = Path(a.corpus) if a.corpus else None
    print(f"EXP-LATEX-01 arm={a.arm}  {spec['role']}")
    print(f"  RQ_LATEX_CHUNKING={os.environ['RQ_LATEX_CHUNKING']}  "
          f"RQ_TABLE_ATOMIC={os.environ['RQ_TABLE_ATOMIC']}")
    print(f"  output -> {out_dir}")

    report = preflight(a.arm, out_dir, corpus)
    write_manifest(a.arm, out_dir, a.config, corpus,
                   {"preflight_can_run": report["can_run"]})

    if not report["can_run"]:
        print("\nPREFLIGHT FAILED — this environment cannot run the arm:")
        for p in report["blocking_problems"]:
            print(f"  - {p}")
        print(f"\nWrote {out_dir / 'preflight.json'}. No per_paper.json was "
              f"written: a partial arm must never be mistaken for a measurement.")
        return 2
    if a.preflight_only:
        print("\nPREFLIGHT OK (--preflight-only, nothing executed).")
        return 0
    if corpus is None and not a.extraction_only:
        print("\n--corpus is required to execute an arm.")
        return 2

    if a.with_extraction and not ollama_up(a.ollama_url):
        print(f"\n--with-extraction requested but Ollama is not answering at "
              f"{a.ollama_url}. Refusing to run the arm without the extraction "
              f"stage it asked for; start Ollama and retry.")
        return 3

    if not a.extraction_only:
        res = run_pipeline_arm(a.arm, a.config, out_dir, corpus)
        print(f"\ningestion: {res['n_papers']} papers in {res['arm_runtime_s']}s -> "
              f"{out_dir / 'per_paper.json'}")

    if a.with_extraction or a.extraction_only:
        ex = run_extraction_arm(a.arm, a.config, out_dir, a.ollama_url)
        n_ok = sum(1 for m in ex["papers"].values() if m["evidence_fields_nonempty"])
        print(f"extraction: {n_ok}/{ex['n_papers']} papers with >=1 field "
              f"(embed {ex['runtime_embed_s']}s, index {ex['runtime_index_s']}s, "
              f"extract {ex['runtime_extract_s']}s) -> {out_dir / 'extraction.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
