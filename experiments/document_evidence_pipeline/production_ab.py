"""Phase 9 — paired PRODUCTION A/B on the frozen 60-paper corpus.

Runs the ACTUAL six-stage production modules (not the experiment harness) twice:

  BASELINE  evidence_grounding.enabled = false  (exact legacy behaviour)
  CANONICAL evidence_grounding.enabled = true   (the 5 FINAL_REPORT sec-O changes)

Same corpus (data/raw_metadata/collected_papers.json), same Ollama model/config,
isolated scratch paths (never touches data/chroma_db or data/processed).

  python production_ab.py --arm baseline
  python production_ab.py --arm canonical
  python production_ab.py --arm both        # baseline then canonical
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from src.config import load_config  # noqa: E402

FROZEN_CORPUS = ROOT / "data" / "raw_metadata" / "collected_papers.json"
RUNS = HERE / "runs"
BASE_CONFIG = ROOT / "configs" / "config.yaml"


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def make_arm_config(scratch: Path, enabled: bool) -> dict:
    cfg = load_config(str(BASE_CONFIG))
    cfg = copy.deepcopy(cfg)
    d = scratch
    cfg["paths"] = {
        "raw_metadata_dir": str(d / "raw_metadata"),
        "pdf_dir": str(d / "pdfs"),
        "processed_dir": str(d / "processed"),
        "chroma_dir": str(d / "chroma_db"),
        "figures_dir": str(d / "figures"),
    }
    cfg.setdefault("evidence_grounding", {})["enabled"] = enabled
    cfg.setdefault("summarization", {})["context_selection"] = "retrieval_aware"
    for sub in ("raw_metadata", "pdfs", "processed", "chroma_db", "figures"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return cfg


def run_arm(name: str, enabled: bool, run_dir: Path) -> dict:
    from src.processing.pdf_parser import run_processing
    from src.embedding.build_index import run_embedding
    from src.summarization.summarize import run_summarization
    from src.collection.semantic_scholar import download_open_access_pdfs

    scratch = run_dir / name
    cfg = make_arm_config(scratch, enabled)
    frozen = json.loads(FROZEN_CORPUS.read_text(encoding="utf-8"))
    meta_out = Path(cfg["paths"]["raw_metadata_dir"]) / "collected_papers.json"

    t0 = time.perf_counter()
    errors = []

    if enabled:
        # CANONICAL: re-resolve acquisition for the SAME 60 records (no re-search),
        # exactly as production Stage 1 would with the flag on.
        records = copy.deepcopy(frozen)
        try:
            download_open_access_pdfs(records, cfg["paths"]["pdf_dir"],
                                      contact_email=cfg["collection"].get("contact_email"),
                                      validate=True, use_extra_sources=True)
        except Exception as exc:
            errors.append(f"acquisition: {type(exc).__name__}: {exc}")
        meta_out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    else:
        # BASELINE: frozen corpus as-is (its has_full_text flags = the shipped 31).
        meta_out.write_text(json.dumps(frozen, indent=2), encoding="utf-8")

    acq_seconds = round(time.perf_counter() - t0, 1)

    for stage_name, fn in (("processing", run_processing),
                           ("embedding", run_embedding),
                           ("summarization", run_summarization)):
        try:
            fn(cfg)
        except Exception as exc:
            import traceback
            errors.append(f"{stage_name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            break

    total_seconds = round(time.perf_counter() - t0, 1)
    summaries = _load(Path(cfg["paths"]["processed_dir"]) / "paper_summaries.json") or []
    evidence = _load(Path(cfg["paths"]["processed_dir"]) / "paper_evidence.json")
    gate_stats = _load(Path(cfg["paths"]["processed_dir"]) / "evidence_gate_summary.json")
    corpus = json.loads(meta_out.read_text(encoding="utf-8"))

    metrics = summarize_arm(name, corpus, summaries, evidence, gate_stats)
    metrics.update({"acq_seconds": acq_seconds, "total_seconds": total_seconds, "errors": errors})
    (run_dir / f"{name}_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    shutil.copy(meta_out, run_dir / f"{name}_collected_papers.json")
    if summaries:
        (run_dir / f"{name}_paper_summaries.json").write_text(
            json.dumps(summaries, indent=2), encoding="utf-8")
    if evidence:
        (run_dir / f"{name}_paper_evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\n[{name}] {json.dumps(metrics, indent=2)}")
    return metrics


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def summarize_arm(name, corpus, summaries, evidence, gate_stats) -> dict:
    n = len(corpus)
    full_text = sum(1 for p in corpus if p.get("has_full_text"))
    acq_status = Counter(p.get("acquisition_status", "n/a") for p in corpus)
    src = Counter(p.get("pdf_source") for p in corpus if p.get("has_full_text"))
    repr_d = Counter(p.get("representation_type") for p in corpus if p.get("has_full_text"))

    wrong_paper = 0
    for p in corpus:
        iv = p.get("identity_validation") or {}
        sig = iv.get("signals") or {}
        if p.get("has_full_text") and iv and sig.get("title_similarity", 1.0) < 0.3 \
                and not sig.get("doi_in_doc"):
            wrong_paper += 1

    ds = sum(len(s.get("datasets") or []) for s in summaries)
    ms = sum(len(s.get("metrics") or []) for s in summaries)
    rs = sum(1 for s in summaries if (s.get("results") or "").strip())

    out = {
        "arm": name, "corpus_size": n,
        "full_text_acquired": full_text,
        "full_text_rate": round(full_text / n, 4) if n else None,
        "acquisition_status": dict(acq_status),
        "full_text_source": dict(src),
        "representation": dict(repr_d),
        "wrong_paper_accepted": wrong_paper,
        "papers_summarised": len(summaries),
        "datasets_returned_total": ds,
        "metrics_returned_total": ms,
        "papers_with_results_text": rs,
    }
    if gate_stats:
        out["evidence_gate"] = gate_stats
    if evidence:
        prov_ok = prov_tot = 0
        attr = Counter()
        no_ft_quant = no_ft_abstain = 0
        for rec in evidence:
            no_ft = rec.get("acquisition_status") != "FULL_TEXT"
            for field, items in (rec.get("evidence") or {}).items():
                for it in items:
                    if it.get("evidence_status") == "EXPLICIT":
                        prov_tot += 1
                        prov_ok += 1 if it.get("provenance_valid") else 0
                    if field in ("metrics", "results") and it.get("evidence_status") == "EXPLICIT":
                        attr[it.get("attribution")] += 1
                    if no_ft:
                        no_ft_quant += 1
                        if it.get("final") == "ABSTAINED":
                            no_ft_abstain += 1
        out["provenance_valid"] = f"{prov_ok}/{prov_tot}"
        out["provenance_valid_rate"] = round(prov_ok / prov_tot, 4) if prov_tot else None
        out["attribution_quantitative"] = dict(attr)
        out["no_full_text_quant_fields"] = no_ft_quant
        out["no_full_text_quant_abstained"] = no_ft_abstain
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "canonical", "both"], required=True)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    run_id = args.run_id or f"prodab-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "started_at": stamp(), "git_revision": git_rev(),
        "frozen_corpus_sha256": __import__("hashlib").sha256(FROZEN_CORPUS.read_bytes()).hexdigest(),
        "corpus_papers": len(json.loads(FROZEN_CORPUS.read_text(encoding="utf-8"))),
        "arm": args.arm,
    }, indent=2), encoding="utf-8")

    results = {}
    if args.arm in ("baseline", "both"):
        results["baseline"] = run_arm("baseline", False, run_dir)
    if args.arm in ("canonical", "both"):
        results["canonical"] = run_arm("canonical", True, run_dir)

    if len(results) == 2:
        _write_report(run_dir, run_id, results["baseline"], results["canonical"])
    print(f"\nwrote {run_dir}")


def _write_report(run_dir, run_id, b, c):
    L = [
        f"# Phase 9 — production A/B ({run_id})", "",
        "| axis | BASELINE (flag off) | CANONICAL (flag on) |", "|---|---|---|",
        f"| full-text acquired | {b['full_text_acquired']}/{b['corpus_size']} "
        f"({b['full_text_rate']:.1%}) | {c['full_text_acquired']}/{c['corpus_size']} "
        f"({c['full_text_rate']:.1%}) |",
        f"| acquisition status | {b['acquisition_status']} | {c['acquisition_status']} |",
        f"| full-text source | {b['full_text_source']} | {c['full_text_source']} |",
        f"| representation | {b['representation']} | {c['representation']} |",
        f"| wrong-paper accepted | {b['wrong_paper_accepted']} | {c['wrong_paper_accepted']} |",
        f"| datasets returned (total) | {b['datasets_returned_total']} | {c['datasets_returned_total']} |",
        f"| metrics returned (total) | {b['metrics_returned_total']} | {c['metrics_returned_total']} |",
        f"| papers w/ results text | {b['papers_with_results_text']} | {c['papers_with_results_text']} |",
        f"| provenance valid | {b.get('provenance_valid','n/a')} | {c.get('provenance_valid','n/a')} |",
        f"| attribution (quant) | {b.get('attribution_quantitative','n/a')} | {c.get('attribution_quantitative','n/a')} |",
        f"| no-full-text quant abstained | "
        f"{b.get('no_full_text_quant_abstained','n/a')}/{b.get('no_full_text_quant_fields','n/a')} | "
        f"{c.get('no_full_text_quant_abstained','n/a')}/{c.get('no_full_text_quant_fields','n/a')} |",
        f"| acq seconds | {b['acq_seconds']} | {c['acq_seconds']} |",
        f"| total seconds | {b['total_seconds']} | {c['total_seconds']} |",
        f"| errors | {b['errors'] or 'none'} | {c['errors'] or 'none'} |",
    ]
    (run_dir / "report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))


if __name__ == "__main__":
    main()
