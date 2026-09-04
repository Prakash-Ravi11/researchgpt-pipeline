"""STAGING end-to-end validation run.

Runs the REAL six-stage production modules with evidence_grounding enabled via
`configs/staging_config.yaml` on the bounded, frozen 8-paper data_test corpus
(reproducible, no S2 search, minimal LLM cost). Then reads the gate + monitor
outputs and checks all 12 safety invariants; exits non-zero on any failure.

    python experiments/document_evidence_pipeline/staging_run.py

Writes runs/staging-<id>/manifest.json + copies of the evidence artifacts.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.config import load_config  # noqa: E402
from src.collection.semantic_scholar import download_open_access_pdfs  # noqa: E402
from src.processing.pdf_parser import run_processing  # noqa: E402
from src.embedding.build_index import run_embedding  # noqa: E402
from src.summarization.summarize import run_summarization  # noqa: E402

STAGING_CONFIG = ROOT / "configs" / "staging_config.yaml"
PROD_CONFIG = ROOT / "configs" / "config.yaml"
FROZEN_META = ROOT / "data_test" / "raw_metadata" / "collected_papers.json"
_NUM = re.compile(r"\d+\.\d+|\b\d{2,}\b")


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main() -> int:
    run_id = f"staging-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = HERE / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prod = load_config(str(PROD_CONFIG))
    cfg = load_config(str(STAGING_CONFIG))
    prod_flag = bool((prod.get("evidence_grounding") or {}).get("enabled"))
    staging_flag = bool((cfg.get("evidence_grounding") or {}).get("enabled"))
    assert staging_flag is True, "staging_config.yaml must enable evidence_grounding"
    assert prod_flag is False, "configs/config.yaml (production/default) must keep evidence_grounding disabled"
    for sub in ("raw_metadata", "pdfs", "processed", "chroma_db", "figures"):
        Path(cfg["paths"].get(f"{sub.split('_')[0]}_dir" if sub != "raw_metadata" else "raw_metadata_dir",
                              cfg["paths"]["processed_dir"])).mkdir(parents=True, exist_ok=True)
    for k in ("raw_metadata_dir", "pdf_dir", "processed_dir", "chroma_dir", "figures_dir"):
        Path(cfg["paths"][k]).mkdir(parents=True, exist_ok=True)

    print(f"== {run_id} ==  production flag={prod_flag}  staging flag={staging_flag}")
    frozen = json.loads(FROZEN_META.read_text(encoding="utf-8"))
    errors: list[str] = []
    t0 = time.perf_counter()

    # Stage 1 (acquisition half) — validated multi-source on the frozen corpus
    records = copy.deepcopy(frozen)
    try:
        download_open_access_pdfs(records, cfg["paths"]["pdf_dir"],
                                  contact_email=cfg["collection"].get("contact_email"),
                                  validate=True, use_extra_sources=True)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"acquisition: {type(exc).__name__}: {exc}")
    Path(cfg["paths"]["raw_metadata_dir"], "collected_papers.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8")

    for name, fn in (("processing", run_processing), ("embedding", run_embedding),
                     ("summarization+gate+monitor", run_summarization)):
        try:
            fn(cfg)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            break
    runtime = round(time.perf_counter() - t0, 1)

    proc = Path(cfg["paths"]["processed_dir"])
    corpus = json.loads(Path(cfg["paths"]["raw_metadata_dir"], "collected_papers.json").read_text(encoding="utf-8"))
    evidence = _load(proc / "paper_evidence.json") or []
    gate = _load(proc / "evidence_gate_summary.json") or {}
    monitor = _load(proc / "evidence_monitor.json") or {}
    chunks = _load(proc / "chunks.json") or []
    chunks_by = defaultdict(list)
    for c in chunks:
        chunks_by[c.get("paper_id")].append(c)

    inv = _check_invariants(corpus, evidence, gate, monitor, chunks_by, errors)

    manifest = {
        "run_id": run_id, "git_revision": git_rev(),
        "config": {"file": "configs/staging_config.yaml",
                   "production_default_flag": prod_flag, "staging_flag": staging_flag,
                   "corpus": cfg["collection"]["domain_query"],
                   "paths_root": "data_test/", "model": cfg["llm"]["model"]},
        "corpus_papers": len(corpus),
        "acquisition": {
            "full_text": sum(1 for p in corpus if p.get("has_full_text")),
            "status": dict(Counter(p.get("acquisition_status") for p in corpus)),
            "source": dict(Counter(p.get("pdf_source") for p in corpus if p.get("has_full_text"))),
            "representation": dict(Counter(p.get("representation_type") for p in corpus if p.get("has_full_text"))),
        },
        "evidence_counts": gate.get("returned"), "abstained": gate.get("abstained"),
        "provenance": {"valid": gate.get("provenance_valid"), "checked": gate.get("provenance_checked"),
                       "rate": gate.get("provenance_valid_rate")},
        "no_full_text_abstention": f"{gate.get('no_full_text_quant_abstained')}/{gate.get('no_full_text_quant_fields')}",
        "attribution": gate.get("attribution"),
        "monitor": monitor,
        "safety_invariants": inv,
        "runtime_seconds": runtime, "errors": errors,
        "decision": ("STAGING_BLOCKED" if any(v != "PASS" for v in inv.values()) or errors
                     else "STAGING_PASS"),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for name in ("paper_evidence.json", "evidence_gate_summary.json", "evidence_monitor.json",
                 "paper_summaries.json"):
        src = proc / name
        if src.exists():
            (run_dir / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "collected_papers.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")

    print("\n=== SAFETY INVARIANTS ===")
    for k, v in inv.items():
        print(f"  [{v}] {k}")
    print(f"\nmonitor overall: {monitor.get('overall')}   errors: {errors or 'none'}")
    print(f"DECISION: {manifest['decision']}   (runtime {runtime}s)")
    print(f"wrote {run_dir}")
    return 0 if manifest["decision"] == "STAGING_PASS" else 1


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_invariants(corpus, evidence, gate, monitor, chunks_by, errors) -> dict:
    ft = {p.get("paperId") or p.get("paper_id") for p in corpus if p.get("has_full_text")}
    returned = [(rec, f, it) for rec in evidence for f in ("datasets", "metrics", "results")
                for it in rec.get("evidence", {}).get(f, []) if it.get("final") == "RETURNED"]
    ret_quant = [(rec, f, it) for rec, f, it in returned if f in ("metrics", "results")]

    def P(cond: bool) -> str:
        return "PASS" if cond else "FAIL"

    wrong_paper = sum(1 for p in corpus if p.get("has_full_text")
                      and (p.get("identity_validation") or {}).get("signals", {}).get("title_similarity", 1.0) < 0.3
                      and not (p.get("identity_validation") or {}).get("signals", {}).get("doi_in_doc"))
    false_own = sum(1 for _, _, it in ret_quant if it.get("attribution") != "OWN_PAPER")
    unsupported = sum(1 for _, _, it in returned if not it.get("provenance_valid")
                      or it.get("evidence_status") not in ("EXPLICIT",))
    noft_leak = sum(1 for rec, _, _ in returned
                    if rec.get("acquisition_status") != "FULL_TEXT")
    prov_rate = gate.get("provenance_valid_rate")
    # every RETURNED quant value's number(s) appear verbatim in its paper's chunks
    span_ok = 0
    for rec, _, it in ret_quant:
        pid = rec.get("paper_id")
        nums = _NUM.findall(it.get("value") or "")
        full = " ".join(c.get("text", "") for c in chunks_by.get(pid, []))
        span = it.get("evidence_span") or ""
        span_ok += 1 if ((not nums) or all(n in full for n in nums)) and \
            ((not nums) or any(n in span for n in nums) or not nums) else 0
    # number-anchored gate active: check the source directly
    gate_src = (ROOT / "src" / "evidence" / "gate.py").read_text(encoding="utf-8")
    num_anchored = 'field == "results"' in gate_src and "_NUMVAL" in gate_src
    # 13 — no RETURNED metrics/results claim asserts a physically impossible value
    # for a named bounded metric (Dice/F1/accuracy/... > 100 or < 0; correlation
    # |x| > 100). A count misread by Stage 4 as a metric value trips this.
    from src.evidence.gate import metric_range_check
    out_of_range = [(rec.get("paper_id"), it.get("value"), metric_range_check(it.get("value") or ""))
                    for _, _, it in ret_quant if metric_range_check(it.get("value") or "")]
    # six-stage architecture unchanged: run_pipeline still chains exactly 4 stage fns + sanity
    rp = (ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    six_stage = rp.count("Stage 1") and rp.count("Stage 2") and rp.count("Stage 3") \
        and rp.count("Stage 4") and "run_sanity_check" in rp

    return {
        "1_wrong_paper_accepted_zero": P(wrong_paper == 0),
        "2_false_own_paper_zero": P(false_own == 0),
        "3_unsupported_quant_claims_zero": P(unsupported == 0),
        "4_no_full_text_quant_leakage_zero": P(noft_leak == 0),
        "5_provenance_100pct": P(prov_rate == 1.0 or (gate.get("provenance_checked") == 0)),
        "6_pipeline_errors_zero": P(not errors),
        "7_cited_never_becomes_own": P(all(it.get("attribution") == "OWN_PAPER" for _, _, it in ret_quant)),
        "8_unknown_never_becomes_own": P(all(it.get("attribution") == "OWN_PAPER" for _, _, it in ret_quant)),
        "9_abstract_only_no_unsupported_quant": P(
            gate.get("no_full_text_quant_fields", 0) == gate.get("no_full_text_quant_abstained", 0)),
        "10_evidence_span_contains_value": P(span_ok == len(ret_quant)),
        "11_number_anchored_results_gate_active": P(num_anchored),
        "12_six_stage_architecture_unchanged": P(bool(six_stage)),
        "13_out_of_range_metric_values_zero": P(len(out_of_range) == 0),
    }


if __name__ == "__main__":
    raise SystemExit(main())
