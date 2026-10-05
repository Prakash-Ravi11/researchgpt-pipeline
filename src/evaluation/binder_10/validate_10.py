"""Phase 10 validation -- definitions in PREREG_10.md (committed 408137e, before any v2 measurement).

    # S3: legacy identity vs the starting commit (production venv)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/binder_10/validate_10.py identity
    # the deterministic arms (legacy, v2, the eight ablations) on R-prod, R-eval and R-oracle
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/binder_10/validate_10.py run
    # v2_llm (Ollama running): fresh run 1 fills the cache, then a replay from the cache, then fresh run 2
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/binder_10/validate_10.py llm fresh1|replay|fresh2
    # PDF-audit packets for every NEW bind (crops + text layer); then the criteria and the decision
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/binder_10/validate_10.py audit
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/binder_10/validate_10.py finalize

Only cached records are gated (runs/p09b_run, the acceptance chunks): no table model, no re-extraction. The 09A and
09B harnesses and the phase 08 evaluator are imported, never modified. Every arm pins
RGPT_FALLTHROUGH_POLICY=table_value_guard and RGPT_BORDERLESS_POLICY=off (PREREG B).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
import types
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src" / "evaluation" / "fallthrough_09b"))
import validate_09b as V9B                                      # noqa: E402  (imports the 09A harness as V9B.V)
V = V9B.V
import src.evidence.gate as G                                   # noqa: E402
import src.evidence.binder_v2 as B                              # noqa: E402

START = "afe1488"
RESULTS, CSV, AUDIT = HERE / "results.json", HERE / "results.csv", HERE / "audit"
LLM_CACHE = HERE / "llm_cache.jsonl"
RUNS = ROOT / "runs" / "p09b_run"
PAPERS = V9B.PAPERS
CANDS = V9B.CANDS
ORACLE_CLAIMS = ("C012", "C057", "C058")
ABLATIONS = tuple(f"v2-{m}" for m in B.MECHANISMS)
REPS = ("R-prod", "R-eval", "R-oracle")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canon(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)


def merge_results(sections: dict) -> None:
    doc = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {"artifact": "phase10_results"}
    doc.update(sections)
    RESULTS.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def set_arm(arm: str, llm_mode: str | None = None) -> None:
    os.environ.update(RGPT_FALLTHROUGH_POLICY="table_value_guard", RGPT_BORDERLESS_POLICY="off")
    os.environ["RGPT_BINDER_POLICY"] = "legacy" if arm == "legacy" else ("v2_llm" if arm.startswith("v2_llm") else "v2")
    os.environ["RGPT_BINDER_V2_DISABLE"] = arm.split("-", 1)[1] if arm.startswith("v2-") else ""
    if llm_mode:
        os.environ.update(RGPT_BINDER_LLM_MODE=llm_mode, RGPT_BINDER_LLM_CACHE=str(LLM_CACHE))
    B._CACHE.clear()


# --- representations (PREREG C) ---------------------------------------------------------------------------------
def load_rep(rep: str) -> dict[str, dict]:
    arm = {"R-prod": "L0", "R-eval": "L1"}.get(rep, "L0")
    out = {}
    for pid in PAPERS:
        o = json.loads((RUNS / f"{pid}_{arm}.json").read_text(encoding="utf-8"))
        out[pid] = {"records": o["records"], "table_blocks": o["table_blocks"], "surnames": o["surnames"]}
    if rep == "R-oracle":
        out = {pid: oracle_paper(pid, out[pid]) for pid in {p["paper_id"] for p in V.PAIRS if p["candidate_id"] in ORACLE_CLAIMS}}
    return out


def oracle_paper(pid: str, paper: dict) -> dict:
    """09A O12: the R-prod records, the target tables' caption-block chunks carry only the claims' gold cells."""
    chunks = [dict(x) for x in paper["records"]]
    ps = [p for p in V.PAIRS if p["paper_id"] == pid and p["candidate_id"] in ORACLE_CLAIMS]
    for label, page in sorted({(p["table_label"], p["table_page"]) for p in ps}):
        caps = V.caption_items(chunks, label, page)
        if not caps:
            continue
        caption = V.R._ws(caps[0]["text"])[:400]
        cells = []
        for i, p in enumerate(q for q in ps if (q["table_label"], q["table_page"]) == (label, page)):
            cell = V.table_cell(value=p["cell_text"], column_header=" / ".join(p["column_header_levels"]),
                                row_label=(p["row_label_levels"] or [""])[-1], caption=caption,
                                section=caps[0]["section"], row=i + 1, col=1)
            cell["page"] = page
            cells.append(cell)
        for x in chunks:
            if x["block_id"] == caps[0]["block_id"]:
                x["table_cells"], x["table_caption"] = cells, caption
    return {**paper, "records": chunks}


def acceptance_product() -> dict[str, dict]:
    """The product unit: the pre-gate Qwen extraction, gated on the acceptance chunks (equal to R-prod)."""
    acc = ROOT / "data_acceptance"
    chunks = json.loads((acc / "processed" / "chunks.json").read_text(encoding="utf-8"))
    meta = {r["paperId"]: r for r in json.loads((acc / "raw_metadata" / "collected_papers.json").read_text(encoding="utf-8"))}
    summaries = json.loads((ROOT / "src" / "evaluation" / "acceptance_pre10" / "pre_gate_summaries.json").read_text(encoding="utf-8"))
    by: dict[str, list] = {}
    for c in chunks:
        by.setdefault(c["paper_id"], []).append(c)
    return {s["paper_id"]: {"summary": s, "records": by.get(s["paper_id"], []),
                            "surnames": [a.get("name", "") for a in (meta.get(s["paper_id"], {}).get("authors") or [])
                                         if isinstance(a, dict)]} for s in summaries}


# --- gating one arm on one representation (PREREG F) -------------------------------------------------------------------
def cells_of(sb: dict | None) -> list[dict]:
    if not sb or sb.get("status") != "bound":
        return []
    return [b["cell"] for b in sb.get("bindings") or []] or [sb["cell"]]


def item_view(it: dict) -> dict:
    sb = it.get("structural_binding") or {}
    return {"value": it["value"], "final": it["final"], "reason": it["abstain_reason"], "status": sb.get("status"),
            "binding_type": sb.get("binding_type"), "cells": cells_of(sb)}


def gate_units(rep: str, papers: dict[str, dict]) -> dict:
    """55 pairs / 18 claims (phase 08 evaluator), Sweep A, Sweep B (and nothing else) on one representation."""
    gold_papers = sorted({p["paper_id"] for p in V.PAIRS if p["paper_id"] in papers})
    pairs = [p for p in V.PAIRS if p["paper_id"] in gold_papers and (rep != "R-oracle" or p["candidate_id"] in ORACLE_CLAIMS)]
    res = V.PE.evaluate(pairs, {pid: {"before_chunks": papers[pid]["records"], "after_chunks": papers[pid]["records"],
                                      "after_blocks": papers[pid]["table_blocks"], "surnames": papers[pid]["surnames"]}
                                for pid in gold_papers})
    gold_cells = {}
    for r in res["pairs"]:
        rec = r["after"]["reconstruction"]
        gold_cells[r["pair_id"]] = [{"row": rec["cell"]["row_label"], "col": rec["cell"]["column_header"],
                                     "value": rec["cell"]["value"], "caption": rec["cell"]["caption"]}] if rec["correct"] else []

    def unit(ev: dict, gold: list[dict], chunks: list) -> dict:
        sb = ev["binder"]
        bound = cells_of(sb)
        trace = sb.get("v2_trace") or {}
        if G._binder_policy() != "legacy":
            # Trace display caps must not cap the candidate-recall denominator.
            off = B._off()
            idx = B._index(chunks, off)
            fr = B._frame(B._prep(ev["claim"]), idx, off)
            rows = []
            for m in fr["mentions"]:
                if m["threshold"] or m["delta"] or m.get("negated") or "L_local" not in m:
                    continue
                candidates, eligible = [], []
                for i in dict.fromkeys(idx["by_value"].get(m["tok"], [])):
                    p = idx["cells"][i]
                    for part in B._value_hits(m, p):
                        candidates.append(B._cell_key(p))
                        if B.links(m, p, fr, idx, off, part)["eligible"]:
                            eligible.append(B._cell_key(p))
                rows.append({"n_candidates": len(candidates), "candidates": candidates, "eligible": eligible})
            trace = {"mentions": rows}
        return {"binder_status": ev["binder_status"], "bound_correct": ev["bound_correct"], "returned": ev["returned"],
                "gate_final": ev["gate_final"], "reasons": ev["gate_abstain_reasons"], "failure": ev["failure"],
                "binding_type": sb.get("binding_type"), "cells": bound, "gold_cells": gold,
                "wrong_bind": bool(bound) and any(c not in gold for c in bound),
                "candidates": [m.get("n_candidates", len(m.get("candidates") or [])) for m in trace.get("mentions") or []
                               if "n_candidates" in m or m.get("candidates")],
                "gold_in_candidates": any(g in (m.get("candidates") or []) for m in trace.get("mentions") or [] for g in gold),
                "gold_eligible": any(g in (m.get("eligible") or []) for m in trace.get("mentions") or [] for g in gold)}
    by_claim: dict[str, list] = {}
    for p in pairs:
        by_claim.setdefault(p["candidate_id"], []).append(p["pair_id"])
    out = {"pairs": {r["pair_id"]: unit(r["after"]["CANONICAL"], gold_cells[r["pair_id"]], papers[r["paper_id"]]["records"]) for r in res["pairs"]},
           "claims": {c["candidate_id"]: unit(c["after"]["REAL"], [g for pid in by_claim[c["candidate_id"]] for g in gold_cells[pid]], papers[c["paper_id"]]["records"])
                      for c in res["claims"]},
           "sweep_A": {}, "sweep_B": {}}
    if rep == "R-oracle":
        return out
    for c in CANDS:
        pp = papers.get(c["paper_id"])
        if pp:
            items = G.gate_paper({"results": c["claim_text"]}, pp["records"], "FULL_TEXT", pp["surnames"])["evidence"]["results"]
            out["sweep_A"][c["candidate_id"]] = [item_view(it) for it in items]
    for pid, pp in papers.items():
        for ch in pp["records"]:
            items = G.gate_paper({"results": ch["text"]}, pp["records"], "FULL_TEXT", pp["surnames"])["evidence"]["results"]
            if items:
                out["sweep_B"][f"{pid}:{ch['chunk_id']}"] = [item_view(it) for it in items]
    return out


def gate_product(product: dict[str, dict]) -> dict:
    out = {}
    for paper_id, pp in product.items():
        ev = G.gate_paper(pp["summary"], pp["records"], "FULL_TEXT", pp["surnames"])["evidence"]
        for field in ("datasets", "metrics", "results"):
            out[f"{paper_id}:{field}"] = [item_view(it) for it in ev[field]]
    return out


def run_arm(arm: str, reps: dict[str, dict], product: dict, llm_mode: str | None = None) -> dict:
    set_arm(arm, llm_mode)
    out = {rep: gate_units(rep, papers) for rep, papers in reps.items()}
    out["R-prod"]["product"] = gate_product(product)
    return out


# --- comparisons with legacy (PREREG F) ----------------------------------------------------------------------------
GOLD_KINDS, ITEM_KINDS = ("pairs", "claims"), ("sweep_A", "sweep_B", "product")


def bound_set(items: list[dict]) -> set[str]:
    return {canon({"value": it["value"], "cell": c}) for it in items for c in it["cells"]}


def compare(legacy: dict, arm: dict) -> dict:
    out = {}
    for rep in arm:
        L, A = legacy[rep], arm[rep]
        r = {"wrong_binds": [], "correct_gains": [], "lost_verified": [], "new_binds": [], "lost_binds": []}
        for kind in GOLD_KINDS:
            for uid, u in A[kind].items():
                lu = L[kind].get(uid)
                if u["wrong_bind"]:
                    r["wrong_binds"].append({"kind": kind, "unit": uid, "cells": u["cells"], "gold": u["gold_cells"]})
                if lu and u["bound_correct"] and not lu["bound_correct"]:
                    r["correct_gains"].append({"kind": kind, "unit": uid, "binding_type": u["binding_type"], "cells": u["cells"]})
                if lu and lu["bound_correct"] and not u["bound_correct"]:
                    r["lost_verified"].append({"kind": kind, "unit": uid, "legacy_cells": lu["cells"], "arm_status": u["binder_status"]})
        for kind in ITEM_KINDS:
            for uid, items in A.get(kind, {}).items():
                old = bound_set(L.get(kind, {}).get(uid, []))
                new = bound_set(items)
                for it in items:
                    for c in it["cells"]:
                        if canon({"value": it["value"], "cell": c}) not in old:
                            r["new_binds"].append({"kind": kind, "unit": uid, "value": it["value"], "cell": c,
                                                   "binding_type": it["binding_type"], "final": it["final"]})
                for c in old - new:
                    r["lost_binds"].append({"kind": kind, "unit": uid, **json.loads(c)})
        r["counts"] = {k: len(v) for k, v in r.items() if isinstance(v, list)}
        out[rep] = r
    return out


def summary(arm: dict) -> dict:
    """Bound-correct and RETURNED-with-verified-bind counts, abstention codes, candidate recall per representation."""
    out = {}
    for rep, U in arm.items():
        s = {}
        for kind in GOLD_KINDS:
            us = list(U[kind].values())
            sizes = [n for u in us for n in u["candidates"]]
            s[kind] = {"units": len(us), "bound": sum(bool(u["cells"]) for u in us), "bound_correct": sum(u["bound_correct"] for u in us),
                       "wrong_bind": sum(u["wrong_bind"] for u in us), "returned_verified": sum(u["returned"] and u["bound_correct"] for u in us),
                       "binder_status": dict(Counter(str(u["binder_status"]) for u in us)),
                       "gold_in_candidates": sum(u["gold_in_candidates"] for u in us if u["gold_cells"]),
                       "with_gold_cell": sum(bool(u["gold_cells"]) for u in us),
                       "candidate_set_size": {"median": statistics.median(sizes) if sizes else None, "max": max(sizes, default=None)}}
        for kind in ITEM_KINDS:
            items = [it for its in U.get(kind, {}).values() for it in its]
            s[kind] = {"items": len(items), "bound": sum(bool(it["cells"]) for it in items),
                       "RETURNED_verified": sum(it["final"] == G.RETURNED and bool(it["cells"]) for it in items),
                       "abstain_codes": dict(Counter(it["reason"] for it in items if it["final"] != G.RETURNED and it["reason"]))}
        out[rep] = s
    return out


def stage(u: dict) -> str:
    """Earliest failure stage of one REAL claim under v2, read on its trace (FAILURE_MAP_10 stages; "linking" is the
    v2 counterpart of legacy "verification": the gold cell holds the value but its subject/quantity links fail or
    conflict; "ranking" is a gold cell that is eligible but not chosen: ambiguity, partial binding or another cell)."""
    if not u["gold_cells"]:
        return "representation"
    if u["bound_correct"]:
        return "none" if u["returned"] else "gate"
    if u["binder_status"] == "deterministic_verification_failed":
        return "verification"
    if not u["gold_in_candidates"]:
        return "candidate_recall"
    return "ranking" if u["gold_eligible"] else "linking"


def legacy_stage(claim: str, ps: list[dict], chunks: list[dict]) -> str:
    """STEP 0's legacy stage rule (FAILURE_MAP_10): candidates = metric-column cells holding a claim number."""
    set_arm("legacy")
    cells = G.paper_table_cells(chunks)
    gold = [r["cell"] for r in (V.PE.reconstruction(cells, p) for p in ps) if r["correct"]]
    if not gold:
        return "representation"
    keys = [{"row": g["row_label"], "col": g["column_header"], "value": g["value"], "caption": g["caption"]} for g in gold]
    sb = G.structural_bind(claim, chunks)
    if sb["status"] == "bound" and sb["cell"] in keys:
        return "gate"
    mt, nums = G._metric_tokens(claim), G._NUMVAL.findall(claim)
    cand = [c for c in cells if mt and G._col_matches_metric(c.get("column_header", ""), mt)
            and any(V.PE.has_num(n, c.get("value", "")) for n in nums)]
    if not any({"row": c.get("row_label"), "col": c.get("column_header"), "value": c.get("value"), "caption": c.get("caption")} in keys for c in cand):
        return "candidate_recall"
    chosen = sb.get("candidate") or sb.get("cell")
    if sb["status"] == "wrong_cell" and chosen and any(chosen.get("row") == k["row"] and chosen.get("col") == k["col"] for k in keys):
        return "verification"
    return "ranking"


# --- modes --------------------------------------------------------------------------------------------------------
STORE = ROOT / "runs" / "binder_10"                             # full per-arm outputs (gitignored, regenerable)


def store(name: str, payload) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


def fetch(name: str):
    return json.loads((STORE / f"{name}.json").read_text(encoding="utf-8"))


def identity() -> None:
    """S3: legacy gate records identical to the starting commit on 30/30 PDFs; 55-pair evaluation; newline canary."""
    os.environ.update(RGPT_FALLTHROUGH_POLICY="table_value_guard", RGPT_BORDERLESS_POLICY="off", RGPT_BINDER_POLICY="legacy")
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{START}:src/evidence/gate.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    old = types.ModuleType("src.evidence._gate_start")
    old.__package__ = "src.evidence"
    exec(compile(src, f"{START}:src/evidence/gate.py", "exec"), old.__dict__)
    per, ctx = {}, {}
    if len(V.MAN) != 30 or len(V.PAIRS) != 55:
        raise SystemExit("STOP: S3 requires exactly 30 manifest papers and 55 pairs")
    gold = {p["paper_id"] for p in V.PAIRS}
    for pid in sorted(V.MAN):
        rec, path, surnames = V.paper(pid)
        chunks = V.PE.grounded_chunks(rec)
        inputs = [c["claim_text"] for c in CANDS if c["paper_id"] == pid] + [ch["text"] for ch in chunks]

        def records(gate, policy: str) -> str:
            os.environ["RGPT_BINDER_POLICY"] = policy
            B._CACHE.clear()
            return canon([gate.gate_paper({"results": x}, chunks, "FULL_TEXT", surnames) for x in inputs])
        base, new = records(old, "legacy"), records(G, "legacy")
        per[pid] = {"gate_records_identical": base == new, "inputs": len(inputs),
                    "sha256": hashlib.sha256(new.encode("utf-8")).hexdigest()[:16]}
        if pid in gold:
            ctx[pid] = {"before_chunks": chunks, "after_chunks": chunks, "surnames": surnames, "after_blocks": []}
    os.environ["RGPT_BINDER_POLICY"] = "legacy"
    r_old, r_new = V9B.evaluate_with(old, V.PAIRS, ctx), V9B.evaluate_with(G, V.PAIRS, ctx)
    assert len(r_old["pairs"]) == len(r_new["pairs"]) == 55
    assert len(r_old["claims"]) == len(r_new["claims"]) == 18
    diff_pairs = [a["pair_id"] for a, b in zip(r_old["pairs"], r_new["pairs"]) if canon(a) != canon(b)]
    diff_claims = [a["candidate_id"] for a, b in zip(r_old["claims"], r_new["claims"]) if canon(a) != canon(b)]
    canary = 0
    for f in [RUNS / f"{pid}_{arm}.json" for pid in PAPERS for arm in ("L0", "L1")]:
        canary += sum("\n" in str(c.get("value", "")) for ch in json.loads(f.read_text(encoding="utf-8"))["records"]
                      for c in ch.get("table_cells") or [])
    n_same = sum(v["gate_records_identical"] for v in per.values())
    merge_results({"identity": {"generated_at_utc": now(), "starting_commit": START, "binder_policy": "legacy",
                                "gate_records_identical": f"{n_same}/{len(per)}", "all_identical": n_same == len(per),
                                "pairs_with_any_difference": diff_pairs, "claims_with_any_difference": diff_claims,
                                "newline_canary": canary, "papers": per, "versions": V.versions(False)}})
    print(f"S3: gate records identical {n_same}/{len(per)}; 55-pair differences pairs {diff_pairs or 'none'} claims "
          f"{diff_claims or 'none'}; newline canary {canary}")
    if n_same != 30 or diff_pairs or diff_claims or canary:
        raise SystemExit("STOP: S3 failed; do not proceed to measurement")


def run() -> None:
    identity_result = json.loads(RESULTS.read_text(encoding="utf-8"))["identity"]
    if not (identity_result["all_identical"] and identity_result["gate_records_identical"] == "30/30"
            and not identity_result["pairs_with_any_difference"] and not identity_result["claims_with_any_difference"]
            and identity_result["newline_canary"] == 0):
        raise SystemExit("STOP: S3 must pass before measurement")
    reps = {rep: load_rep(rep) for rep in REPS}
    product = acceptance_product()
    arms = {}
    for arm in ("legacy", "v2", *ABLATIONS):
        arms[arm] = run_arm(arm, reps, product)
        store(arm, arms[arm])
        print(f"  {arm}: done", flush=True)
    claims_by = {}
    for p in V.PAIRS:
        claims_by.setdefault(p["candidate_id"], []).append(p)
    acc = json.loads((ROOT / "src" / "evaluation" / "acceptance_pre10" / "results.json").read_text(encoding="utf-8"))
    covered = {c["claim"]: c["covered"] for c in acc["gold_coverage"]["claims"]}
    stages = {}
    for cid, ps in sorted(claims_by.items()):
        row = {"product": "reaches gate" if covered.get(cid) else "product"}
        for rep, papers in reps.items():
            if ps[0]["paper_id"] not in papers or cid not in arms["v2"][rep]["claims"]:
                continue
            row[rep] = {"legacy": legacy_stage(ps[0]["claim_text"], ps, papers[ps[0]["paper_id"]]["records"]),
                        "v2": stage(arms["v2"][rep]["claims"][cid])}
        stages[cid] = row
    merge_results({"run": {
        "generated_at_utc": now(), "arms": ["legacy", "v2", *ABLATIONS], "representations": list(REPS),
        "summary": {arm: summary(a) for arm, a in arms.items()},
        "vs_legacy": {arm: compare(arms["legacy"], a) for arm, a in arms.items() if arm != "legacy"},
        "earliest_failure_stage": stages, "versions": V.versions(False)}})
    v2c = {rep: c["counts"] for rep, c in compare(arms["legacy"], arms["v2"]).items()}
    print("v2 vs legacy:", json.dumps(v2c))


def llm(mode: str) -> None:
    reps = {rep: load_rep(rep) for rep in REPS}
    product = acceptance_product()
    before = sum(1 for _ in open(LLM_CACHE, encoding="utf-8")) if LLM_CACHE.exists() else 0
    try:
        out = run_arm("v2_llm", reps, product, llm_mode={"fresh1": "fresh", "replay": "replay", "fresh2": "fresh2"}[mode])
    except B.LLMViolation as e:
        merge_results({f"llm_{mode}": {"STOP": f"LLMViolation: {e}"}})
        raise SystemExit(f"STOP (global rule): the LLM returned a cell, value or span not in its input: {e}")
    store(f"v2_llm_{mode}", out)
    calls = (sum(1 for _ in open(LLM_CACHE, encoding="utf-8")) if LLM_CACHE.exists() else 0) - before
    legacy = fetch("legacy")
    sec = {"generated_at_utc": now(), "new_cache_lines": calls, "summary": summary(out), "vs_legacy": compare(legacy, out)}
    if mode != "fresh1":
        ref = fetch("v2_llm_fresh1")
        sec["disagreements_vs_fresh1"] = [f"{rep}:{kind}:{uid}" for rep in out for kind in out[rep]
                                          for uid, u in out[rep][kind].items() if canon(u) != canon(ref[rep][kind].get(uid))]
    merge_results({f"llm_{mode}": sec})
    print(f"v2_llm {mode}: {calls} new cache lines; disagreements vs fresh1: {len(sec.get('disagreements_vs_fresh1', []))}")


def audit() -> None:
    """Packets for every NEW bind of v2 and v2_llm (sweeps and product, R-prod and R-eval): crops + text layer."""
    import pymupdf
    legacy = fetch("legacy")
    arms = {"v2": fetch("v2")}
    if (STORE / "v2_llm_fresh1.json").exists():
        arms["v2_llm"] = fetch("v2_llm_fresh1")
    reps = {rep: load_rep(rep) for rep in ("R-prod", "R-eval")}
    sha_to_pid = {Path(V.MAN[pid]["canonical_pdf_path"]).stem: pid for pid in V.MAN}
    packets: dict[str, dict] = {}
    for arm, out in arms.items():
        for rep in ("R-prod", "R-eval"):
            for nb in compare(legacy, out)[rep]["new_binds"]:
                if nb["kind"] == "sweep_A":
                    pid = next(c["paper_id"] for c in CANDS if c["candidate_id"] == nb["unit"])
                elif nb["kind"] == "sweep_B":
                    pid = nb["unit"].split(":")[0]
                else:
                    pid = sha_to_pid.get(nb["unit"].split(":")[0], nb["unit"].split(":")[0])
                key = hashlib.sha256(canon([pid, nb["value"], nb["cell"]]).encode("utf-8")).hexdigest()[:12]
                pk = packets.setdefault(key, {"id": key, "paper": pid, "value": nb["value"], "cell": nb["cell"],
                                              "occurrences": []})
                pk["occurrences"].append({"arm": arm, "rep": rep, "kind": nb["kind"], "unit": nb["unit"],
                                          "binding_type": nb["binding_type"], "final": nb["final"]})
    AUDIT.mkdir(exist_ok=True)
    for pk in packets.values():
        rep = pk["occurrences"][0]["rep"]
        paper = reps[rep][pk["paper"]]
        cell = next((c for c in G.paper_table_cells(paper["records"])
                     if {"row": c.get("row_label"), "col": c.get("column_header"), "value": c.get("value"),
                         "caption": c.get("caption")} == pk["cell"]), None)
        page = cell.get("page") if cell else None
        tb = next((b for b in paper["table_blocks"] if b.get("table_bbox") and b["page_or_node"] == f"p{page}"
                   and V.R._ws(b["text"])[:60] == V.R._ws(pk["cell"]["caption"] or "")[:60]), None)
        pk["page"], pk["pdf"] = page, V.MAN[pk["paper"]]["canonical_pdf_path"]
        if page:
            doc = pymupdf.open(pk["pdf"])
            pg = doc[page - 1]
            clip = ((pymupdf.Rect(tb["table_bbox"]) + (-10, -40, 10, 10)) & pg.rect) if tb else pg.rect
            pg.get_pixmap(dpi=150, clip=clip).save(AUDIT / f"{pk['id']}_table.png")
            (AUDIT / f"{pk['id']}_text.txt").write_text(pg.get_text("text"), encoding="utf-8")
            doc.close()
            pk["table_crop"] = f"audit/{pk['id']}_table.png"
            pk["text_layer"] = f"audit/{pk['id']}_text.txt"
            pk["crop_scope"] = "table" if tb else "full_page_including_table"
    (AUDIT / "packets.json").write_text(json.dumps(sorted(packets.values(), key=lambda p: p["id"]), indent=1,
                                                   ensure_ascii=False), encoding="utf-8")
    print(f"audit packets: {len(packets)} distinct new binds")


def finalize() -> None:
    doc = json.loads(RESULTS.read_text(encoding="utf-8"))
    legacy, v2 = fetch("legacy"), fetch("v2")
    packets = json.loads((AUDIT / "packets.json").read_text(encoding="utf-8")) if (AUDIT / "packets.json").exists() else []
    verdicts: dict[str, list] = {}
    for f in sorted(AUDIT.glob("verdicts_*.json")):
        for v in json.loads(f.read_text(encoding="utf-8")):
            verdicts.setdefault(v["id"], []).append((f.name, v["same_quantity_and_subject"] is True))
    wrong_audit = {pid for pid, v in verdicts.items() if len({name for name, _ in v}) < 2 or not all(ok for _, ok in v)}
    unaudited = [p["id"] for p in packets if p["id"] not in verdicts]

    def criteria(arm: str, out: dict) -> dict:
        cmp = compare(legacy, out)
        gold_wrong = [dict(w, rep=rep) for rep, c in cmp.items() for w in c["wrong_binds"]]
        lost = [dict(x, rep=rep) for rep, c in cmp.items() for x in c["lost_verified"] + c["lost_binds"]]
        mine = [p for p in packets if any(o["arm"] == arm for o in p["occurrences"])]
        wrong_new = [p["id"] for p in mine if p["id"] in wrong_audit or p["id"] in unaudited]
        coverage = {canon([o["rep"], o["kind"], o["unit"], p["value"], p["cell"]])
                    for p in mine for o in p["occurrences"] if o["arm"] == arm}
        for rep, comparison in cmp.items():
            for nb in comparison["new_binds"]:
                key = canon([rep, nb["kind"], nb["unit"], nb["value"], nb["cell"]])
                if key not in coverage:
                    wrong_new.append("missing_packet:" + hashlib.sha256(key.encode()).hexdigest()[:12])
        for p in mine:
            if not all(p.get(k) and (HERE / p[k]).is_file() for k in ("table_crop", "text_layer")):
                wrong_new.append("missing_pdf_evidence:" + p["id"])
        gains = [dict(g, rep=rep) for rep, c in cmp.items() if rep != "R-oracle" for g in c["correct_gains"]]
        return {"S1": {"pass": not gold_wrong and not wrong_new, "gold_wrong_binds": gold_wrong,
                       "new_binds_audited": len(mine), "new_binds_wrong_or_unaudited": wrong_new},
                "S2": {"pass": not lost, "lost_verified_binds": lost},
                "S3": {"pass": bool(doc.get("identity", {}).get("all_identical"))
                       and not doc["identity"]["pairs_with_any_difference"]
                       and not doc["identity"]["claims_with_any_difference"] and doc["identity"]["newline_canary"] == 0},
                "correct_gains": gains,
                "correct_gains_R_oracle": list(cmp.get("R-oracle", {}).get("correct_gains", []))}
    crit = {"v2": criteria("v2", v2)}
    if (STORE / "v2_llm_fresh1.json").exists():
        crit["v2_llm"] = criteria("v2_llm", fetch("v2_llm_fresh1"))
        crit["v2_llm"]["replay_and_fresh_agree"] = all(
            f"llm_{m}" in doc and "STOP" not in doc[f"llm_{m}"] and not doc[f"llm_{m}"].get("disagreements_vs_fresh1")
            for m in ("replay", "fresh2"))
    ok = lambda c: c["S1"]["pass"] and c["S2"]["pass"] and c["S3"]["pass"]
    v = crit["v2"]
    if ok(v) and v["correct_gains"]:
        decision = "ENABLE binder_policy: v2"
        lv = crit.get("v2_llm")
        gain_keys = lambda c: {(g["rep"], g["kind"], g["unit"]) for g in c["correct_gains"]}
        if lv and ok(lv) and lv["replay_and_fresh_agree"] and gain_keys(lv) > gain_keys(v):
            decision = "ENABLE binder_policy: v2_llm"
    elif not ok(v):
        decision = "NO ENABLE: v2 fails " + ", ".join(k for k in ("S1", "S2", "S3") if not v[k]["pass"])
    else:
        decision = "NO ENABLE: zero correct gains"
    merge_results({"criteria": crit, "decision": decision, "audit_unaudited": unaudited, "finalized_at_utc": now()})
    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arm", "rep", "kind", "unit", "binder_status", "bound_correct", "returned", "wrong_bind", "cells", "gold_cells"])
        names = ["legacy", "v2", *ABLATIONS] + (["v2_llm_fresh1"] if (STORE / "v2_llm_fresh1.json").exists() else [])
        for arm in names:
            out = fetch(arm)
            for rep in out:
                for kind in GOLD_KINDS:
                    for uid, u in sorted(out[rep][kind].items()):
                        w.writerow([arm, rep, kind, uid, u["binder_status"], u["bound_correct"], u["returned"],
                                    u["wrong_bind"], canon(u["cells"]), canon(u["gold_cells"])])
    print("decision:", decision)
    print(json.dumps({a: {k: c[k]["pass"] for k in ("S1", "S2", "S3")} | {"gains": len(c["correct_gains"])}
                      for a, c in crit.items()}))


if __name__ == "__main__":
    mode = sys.argv[1]
    {"identity": identity, "run": run, "audit": audit, "finalize": finalize}.get(mode, lambda: llm(sys.argv[2]))()
