"""Product acceptance before Phase 10 (phase 10 package, Part 2). Run from the repository root, production .venv.

    # 1. seed data_acceptance/ with the 12 hash-pinned gold PDFs and their acquisition records (no network)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/acceptance_pre10/run_acceptance.py seed
    # 2. Stage 2 run_processing, Stage 3 run_embedding, Stage 4 run_summarization -> pre_gate_summaries.json (ONCE)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/acceptance_pre10/run_acceptance.py stages
    # 3. Stage 5 run_evidence_gate on copies of the pre-gate summaries, arm A and arm B; then the measurements
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/acceptance_pre10/run_acceptance.py gate

Only existing stage functions run; each one is recorded in results.json. This file seeds, orchestrates and measures,
and adds no pipeline logic. Two facts shape it:
- Stage 4 (summarize.py:1344-1346) calls run_evidence_gate itself when evidence_grounding.enabled. The dict
  passed to run_summarization has that flag False, so the pre-gate summaries can be saved; extraction never reads
  the flag (retrieval_aware.py:301 keys on the chunk schema).
- The fall-through and borderless flags are read from configs/staging_config.yaml only (gate.py:515,
  represent.py:419), not from the run config. Arm A sets the environment (legacy, off); arm B leaves it unset and
  records what resolved (the frozen config).
No network: the PDFs are copied from their hash-pinned paths, HF_HUB_OFFLINE=1 is set before any model import, and
Ollama is local.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "evaluation" / "borderless_09a"))
import validate_09a as V                                        # noqa: E402  (gold pairs, manifest, paper())
import src.evidence.gate as G                                   # noqa: E402
import src.evidence.represent as R                              # noqa: E402
from src.config import load_config                              # noqa: E402

CFG_PATH = ROOT / "configs" / "acceptance_config.yaml"
RESULTS = HERE / "results.json"
PRE_GATE = HERE / "pre_gate_summaries.json"
GOLD_PAPERS = sorted({p["paper_id"] for p in V.PAIRS})
ARMS = {"A": {"RGPT_FALLTHROUGH_POLICY": "legacy", "RGPT_BORDERLESS_POLICY": "off"}, "B": {}}
FIELDS = ("datasets", "metrics", "results")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def canon(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)


def merge_results(sections: dict) -> None:
    doc = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {"artifact": "acceptance_pre10"}
    doc.update(sections)
    RESULTS.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def config() -> dict:
    if Path.cwd().resolve() != ROOT:
        raise SystemExit(f"run from the repository root ({ROOT}); config paths are relative")
    return load_config(CFG_PATH)


# --- 1. seed ---------------------------------------------------------------------------------------------------
def seed() -> None:
    cfg = config()
    pdf_dir, meta_dir = Path(cfg["paths"]["pdf_dir"]), Path(cfg["paths"]["raw_metadata_dir"])
    pdf_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    records, rows = [], []
    for pid in GOLD_PAPERS:
        rec, path, _ = V.paper(pid)                    # hash-checked canonical PDF + the record the 55 pairs used
        dst = pdf_dir / path.name
        shutil.copyfile(path, dst)
        ok = sha(dst) == V.MAN[pid]["sha256"]
        if not ok:
            raise SystemExit(f"STOP: SHA-256 mismatch after copying {pid}")
        records.append({**rec, "pdf_path": dst.as_posix()})
        rows.append({"paper": pid, "paperId": rec["paperId"], "source": str(path), "copied_to": dst.as_posix(),
                     "sha256": V.MAN[pid]["sha256"], "sha256_verified": ok, "bytes": dst.stat().st_size,
                     "representation_type": rec.get("representation_type"), "acquisition_status": rec.get("acquisition_status")})
    (meta_dir / "collected_papers.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    merge_results({"seed": {"generated_at_utc": now(), "config": str(CFG_PATH.relative_to(ROOT)), "papers": rows,
                            "all_sha256_verified": all(r["sha256_verified"] for r in rows),
                            "collected_papers": (meta_dir / "collected_papers.json").as_posix()}})
    print(f"seeded {len(rows)} PDFs, SHA-256 verified {sum(r['sha256_verified'] for r in rows)}/{len(rows)}")


# --- 2. stages 2-4 (once) ----------------------------------------------------------------------------------------
def ollama_model_digest(cfg: dict) -> str | None:
    import requests
    try:
        tags = requests.get(cfg["llm"]["base_url"].rstrip("/") + "/api/tags", timeout=5).json()
        return next((m.get("digest") for m in tags.get("models", []) if m.get("name") == cfg["llm"]["model"]), None)
    except Exception as e:  # noqa: BLE001
        return f"UNAVAILABLE: {e}"


def stages() -> None:
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"   # no network for BGE-M3
    cfg = config()
    from src.preflight import check_ollama_from_config
    pre = check_ollama_from_config(cfg)
    if not pre["ok"]:
        merge_results({"stages": {"UNMEASURED": pre.get("message")}})
        raise SystemExit(f"STOP: Ollama preflight failed: {pre.get('message')}")
    from src.processing.pdf_parser import run_processing
    from src.embedding.build_index import run_embedding
    from src.summarization.summarize import run_summarization
    cfg4 = copy.deepcopy(cfg)
    cfg4["evidence_grounding"]["enabled"] = False      # stop before Stage 4's own Stage 5 hook
    ran = []
    for stage, name, fn, c in ((2, "src.processing.pdf_parser.run_processing", run_processing, cfg),
                               (3, "src.embedding.build_index.run_embedding", run_embedding, cfg),
                               (4, "src.summarization.summarize.run_summarization (evidence_grounding.enabled=False "
                                   "in the dict passed: its Stage 5 hook does not run)", run_summarization, cfg4)):
        t0 = time.perf_counter()
        fn(c)
        ran.append({"stage": stage, "function": name, "seconds": round(time.perf_counter() - t0, 1)})
        print(f"  stage {stage} done in {ran[-1]['seconds']} s", flush=True)
    processed = Path(cfg["paths"]["processed_dir"])
    shutil.copyfile(processed / "paper_summaries.json", PRE_GATE)
    # representation: the acceptance chunks must equal the 55-pair evaluation's L0 records (runs/p09b_run)
    chunks = json.loads((processed / "chunks.json").read_text(encoding="utf-8"))
    by_paper: dict[str, list] = {}
    for c in chunks:
        by_paper.setdefault(c["paper_id"], []).append(c)
    rep = {}
    for pid in GOLD_PAPERS:
        l0 = ROOT / "runs" / "p09b_run" / f"{pid}_L0.json"
        if not l0.exists():
            rep[pid] = "UNMEASURED: runs/p09b_run L0 record missing"
            continue
        rec = json.loads(l0.read_text(encoding="utf-8"))["records"]
        rep[pid] = canon(by_paper.get(rec[0]["paper_id"] if rec else None, [])) == canon(rec)
    summaries = json.loads(PRE_GATE.read_text(encoding="utf-8"))
    merge_results({"stages": {
        "generated_at_utc": now(), "stage_functions_ran": ran, "ollama": {"model": cfg["llm"]["model"],
        "digest": ollama_model_digest(cfg), "temperature": cfg["llm"]["temperature"], "seed": cfg["llm"]["seed"]},
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"), "chunks": len(chunks),
        "chunks_equal_to_L0_records_of_the_55_pair_evaluation": rep,
        "pre_gate_summaries": str(PRE_GATE.relative_to(ROOT)), "papers_summarised": len(summaries),
        "extraction_failed": [s.get("paper_id") for s in summaries if s.get("_extraction_failed")]}})
    print(f"pre-gate summaries: {len(summaries)} papers; chunks equal to L0: "
          f"{sum(v is True for v in rep.values())}/{len(rep)}")


# --- 3. stage 5 per arm, then the measurements -----------------------------------------------------------------------
def item_view(it: dict) -> dict:
    sb = it.get("structural_binding") or {}
    return {"value": it["value"][:300], "final": it["final"], "reason": it["abstain_reason"],
            "binding": sb.get("status"), "verified_bind": it["final"] == G.RETURNED and sb.get("status") == "bound"}


def gate() -> None:
    cfg = config()
    if not PRE_GATE.exists():
        raise SystemExit("run `stages` first: pre_gate_summaries.json is missing")
    seeded = json.loads((Path(cfg["paths"]["raw_metadata_dir"]) / "collected_papers.json").read_text(encoding="utf-8"))
    pid_of = {r["paperId"]: Path(r["pdf_path"]).stem for r in seeded}
    pid_of = {k: next(p for p in GOLD_PAPERS if Path(V.MAN[p]["canonical_pdf_path"]).stem == v) for k, v in pid_of.items()}
    chunks_path = Path(cfg["paths"]["processed_dir"]) / "chunks.json"
    arms, ev = {}, {}
    from src.evidence.gate import run_evidence_gate
    for arm, env in ARMS.items():
        d = ROOT / "data_acceptance" / f"gate_{arm}"
        shutil.rmtree(d, ignore_errors=True)
        (d / "processed").mkdir(parents=True)
        (d / "raw_metadata").mkdir(parents=True)
        shutil.copyfile(chunks_path, d / "processed" / "chunks.json")
        shutil.copyfile(PRE_GATE, d / "processed" / "paper_summaries.json")
        shutil.copyfile(Path(cfg["paths"]["raw_metadata_dir"]) / "collected_papers.json", d / "raw_metadata" / "collected_papers.json")
        for k in ("RGPT_FALLTHROUGH_POLICY", "RGPT_BORDERLESS_POLICY"):
            os.environ.pop(k, None)
        os.environ.update(env)
        c = copy.deepcopy(cfg)
        c["paths"].update(processed_dir=(d / "processed").as_posix(), raw_metadata_dir=(d / "raw_metadata").as_posix())
        resolved = {"fallthrough_policy": G._fallthrough_policy(), "borderless_policy": R._borderless_policy()}
        stats = run_evidence_gate(c)
        arms[arm] = {"environment": env or "unset (frozen config)", "resolved": resolved, "gate_stats": stats,
                     "dir": d.relative_to(ROOT).as_posix()}
        ev[arm] = {e["paper_id"]: e["evidence"] for e in json.loads((d / "processed" / "paper_evidence.json").read_text(encoding="utf-8"))}
    for k in ("RGPT_FALLTHROUGH_POLICY", "RGPT_BORDERLESS_POLICY"):
        os.environ.pop(k, None)

    # per arm and field type
    counts = {}
    for arm in ARMS:
        for f in FIELDS:
            items = [item_view(it) for e in ev[arm].values() for it in e[f]]
            counts.setdefault(arm, {})[f] = {
                "items": len(items), "RETURNED_with_verified_bind": sum(i["verified_bind"] for i in items),
                "RETURNED_without_bind": sum(i["final"] == G.RETURNED and not i["verified_bind"] for i in items),
                "ABSTAINED": sum(i["final"] != G.RETURNED for i in items),
                "ABSTAINED_by_reason": dict(Counter(i["reason"] for i in items if i["final"] != G.RETURNED)),
                "binder_status": dict(Counter(str(i["binding"]) for i in items))}
    # every field that changes from A to B
    sys.path.insert(0, str(ROOT / "src" / "evaluation" / "fallthrough_09b"))
    import validate_09b as V9B                                  # its `matched` helper (unchanged harness)
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    recs: dict[str, list] = {}
    for c in chunks:
        recs.setdefault(c["paper_id"], []).append(c)
    changes, unaligned = [], []
    for paper_id in sorted(ev["A"]):
        for f in FIELDS:
            a_items, b_items = ev["A"][paper_id][f], ev["B"][paper_id][f]
            if [x["value"] for x in a_items] != [x["value"] for x in b_items]:
                unaligned.append(f"{pid_of.get(paper_id, paper_id)}:{f}")
                continue
            for i, (a, b) in enumerate(zip(a_items, b_items)):
                va, vb = item_view(a), item_view(b)
                if (va["final"], va["reason"], va["binding"]) != (vb["final"], vb["reason"], vb["binding"]):
                    changes.append({"paper": pid_of.get(paper_id, paper_id), "field": f, "index": i, "value": va["value"],
                                    "A": {k: va[k] for k in ("final", "reason", "binding")},
                                    "B": {k: vb[k] for k in ("final", "reason", "binding")},
                                    **({"matched": V9B.matched(b["value"], recs.get(paper_id, []))}
                                       if b["abstain_reason"] == "table_value_unbound" else {})})
    # gold coverage: does the pre-gate extraction carry the claim's value (the guard's token rule)?
    pre = {s["paper_id"]: s for s in json.loads(PRE_GATE.read_text(encoding="utf-8"))}
    paper_id_of = {v: k for k, v in pid_of.items()}
    claims: dict[str, list] = {}
    for p in V.PAIRS:
        claims.setdefault(p["candidate_id"], []).append(p)
    coverage = []
    for cid, ps in sorted(claims.items()):
        paper_id = paper_id_of.get(ps[0]["paper_id"])
        s = pre.get(paper_id) or {}
        gold_tokens = sorted({t for p in ps for t in G.numeric_tokens(p["value_in_claim"])})
        found = []
        for f in FIELDS:
            vals = s.get(f) or []
            for v in ([vals] if isinstance(vals, str) else vals):
                hit = sorted(set(gold_tokens) & G.numeric_tokens(v))
                if hit:
                    found.append({"field": f, "tokens": hit, "value": str(v)[:300]})
        status = {}
        for arm in ARMS:
            for f in FIELDS:
                for it in (ev[arm].get(paper_id) or {}).get(f, []):
                    hit = sorted(set(gold_tokens) & G.numeric_tokens(it["value"]))
                    if hit:
                        status.setdefault(arm, []).append({"field": f, "tokens": hit, **{k: item_view(it)[k] for k in
                                                                                        ("value", "final", "reason", "binding")}})
        coverage.append({"claim": cid, "paper": ps[0]["paper_id"], "claim_subject_kind": ps[0]["claim_subject_kind"],
                         "gold_value_tokens": gold_tokens, "extraction_paper_present": bool(s),
                         "covered": bool(found), "pre_gate_fields_with_gold_value": found, "gated_items": status})
    merge_results({"gate": {"generated_at_utc": now(), "arms": arms, "per_arm_field_counts": counts,
                            "changes_A_to_B": changes, "n_changes_A_to_B": len(changes), "unaligned_fields": unaligned},
                   "gold_coverage": {"rule": "gold value_in_claim tokens vs pre-gate field tokens; gate.numeric_tokens "
                                             "(the guard's token rule, PREREG_09B D3)",
                                     "claims": coverage, "covered": sum(c["covered"] for c in coverage),
                                     "of": len(coverage)}})
    for arm in ARMS:
        print(arm, arms[arm]["resolved"], {f: (x["RETURNED_with_verified_bind"], x["RETURNED_without_bind"], x["ABSTAINED"])
                                           for f, x in counts[arm].items()})
    print(f"changes A->B: {len(changes)}; unaligned: {unaligned or 'none'}; gold coverage "
          f"{sum(c['covered'] for c in coverage)}/{len(coverage)}")


if __name__ == "__main__":
    {"seed": seed, "stages": stages, "gate": gate}[sys.argv[1]]()
