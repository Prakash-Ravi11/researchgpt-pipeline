"""Phase 09B validation -- definitions in PREREG_09B.md (committed 591d063, before any run).

    # STEP 2: identity vs 864f2e8 (production venv; fallthrough legacy, borderless off)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/fallthrough_09b/validate_09b.py identity
    # STEP 3: the 2x2 run. One child process per paper per arm, CPU only, outputs cached in <workdir>. Order:
    # L0, G0, L1, the L1 reproduction check (STOP on any difference), G1, then the analysis.
    CUDA_VISIBLE_DEVICES="" PYTHONIOENCODING=utf-8 .venv-09a/Scripts/python.exe -B src/evaluation/fallthrough_09b/validate_09b.py run <workdir>
    # building blocks of `run`: children for some arms; the analysis alone (results path optional)
    ... validate_09b.py children <workdir> <arm>...
    ... validate_09b.py analyze <workdir> [<results.json>]

Each mode merges its own sections into results.json and keeps the others. The children are 09A's own child
(validate_09a.child: process_paper_grounded with the build_document capture); they do not gate. All gating runs
in this process with RGPT_FALLTHROUGH_POLICY set per arm, through the unchanged phase 08 evaluator
(postfix_evaluate.evaluate) and the Stage B oracle's run_case. The 09A harness is imported, never modified.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import types
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src" / "evaluation" / "borderless_09a"))
import validate_09a as V                                        # noqa: E402  (09A harness: gold, NEG, child, analysis)
import src.evidence.gate as G                                   # noqa: E402
from src.evidence import borderless as B                        # noqa: E402  (pure helpers; no table model)

RESULTS = HERE / "results.json"
BASELINE = "864f2e8"
ARMS = {"L0": ("legacy", "off"), "G0": ("table_value_guard", "off"),
        "L1": ("legacy", "consensus"), "G1": ("table_value_guard", "consensus")}
PAPERS = sorted({p["paper_id"] for p in V.PAIRS} | {n[0] for n in V.NEG})
GOLD_PAPERS = sorted({p["paper_id"] for p in V.PAIRS})
CANDS = json.loads((V.DIAG / "postfix_candidates.json").read_text(encoding="utf-8"))["candidates"]
REGRESSED_09A = ["PF001", "PF002", "PF006", "PF017", "PF018", "PF019"]
EXPECT_NEG = {("P019", "Table 1"): ("accepted", None), ("P019", "Table 2"): ("accepted", None),
              ("P027", "Table 1"): ("rejected", "G3"), ("P020", "TABLE III"): ("rejected", "G1"),
              ("P024", "Table 2"): ("rejected", "no_candidate")}
VOLATILE = {"generated_at_utc", "child_wall_seconds", "versions", "seconds", "seconds_page"}
KINDS = ("pairs", "claims", "sweep_A")                          # the criterion units (D12); sweep_B is supplementary


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canon(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)


def merge_results(sections: dict, path: Path = RESULTS) -> None:
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"artifact": "phase09b_results"}
    doc.update(sections)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


# --- STEP 2: identity vs 864f2e8 (D7) ----------------------------------------------------------------------------
def old_gate() -> types.ModuleType:
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASELINE}:src/evidence/gate.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    mod = types.ModuleType("src.evidence._gate_baseline")
    mod.__package__ = "src.evidence"
    exec(compile(src, f"{BASELINE}:src/evidence/gate.py", "exec"), mod.__dict__)
    return mod


def evaluate_with(gate, pairs: list[dict], ctx: dict) -> dict:
    """The phase 08 evaluator with `gate` as its gate module (PE.G and the oracle's O.G)."""
    saved = V.PE.G, V.O.G
    V.PE.G = V.O.G = gate
    try:
        return V.PE.evaluate(pairs, ctx)
    finally:
        V.PE.G, V.O.G = saved


def identity() -> None:
    os.environ["RGPT_BORDERLESS_POLICY"] = "off"
    old = old_gate()
    per, ctx = {}, {}
    for pid in sorted(V.MAN):
        rec, path, surnames = V.paper(pid)
        chunks = V.PE.grounded_chunks(rec)
        inputs = [c["claim_text"] for c in CANDS if c["paper_id"] == pid] + [ch["text"] for ch in chunks]

        def records(gate, policy: str) -> str:
            os.environ["RGPT_FALLTHROUGH_POLICY"] = policy
            return canon([gate.gate_paper({"results": x}, chunks, "FULL_TEXT", surnames) for x in inputs])
        base, new, guard = records(old, "legacy"), records(G, "legacy"), records(G, "table_value_guard")
        per[pid] = {"gate_records_identical": base == new, "inputs": len(inputs),
                    "candidate_claims": sum(c["paper_id"] == pid for c in CANDS),
                    "gate_items": sum(len(r["evidence"]["results"]) for r in json.loads(new)),
                    "cells": len(G.paper_table_cells(chunks)), "records_sha256": hashlib.sha256(new.encode("utf-8")).hexdigest()[:16],
                    "differs_under_table_value_guard": guard != base}
        if pid in GOLD_PAPERS:
            ctx[pid] = {"before_chunks": chunks, "after_chunks": chunks, "surnames": surnames,
                        "after_blocks": V.R.build_document({"paper_id": pid, "source": "eval", "representation_type": "pdf"},
                                                           path.read_bytes())["blocks"]}
    os.environ["RGPT_FALLTHROUGH_POLICY"] = "legacy"
    r_old, r_new = evaluate_with(old, V.PAIRS, ctx), evaluate_with(G, V.PAIRS, ctx)
    diff_pairs = [a["pair_id"] for a, b in zip(r_old["pairs"], r_new["pairs"]) if canon(a) != canon(b)]
    diff_claims = [a["candidate_id"] for a, b in zip(r_old["claims"], r_new["claims"]) if canon(a) != canon(b)]
    n_same = sum(v["gate_records_identical"] for v in per.values())
    payload = {"generated_at_utc": now(), "baseline": BASELINE, "fallthrough_policy": "legacy",
               "borderless_policy_resolved": V.R._borderless_policy(), "versions": V.versions(False), "papers": per,
               "gate_records_identical": f"{n_same}/{len(per)}", "all_gate_records_identical": n_same == len(per),
               "gate_inputs": sum(v["inputs"] for v in per.values()), "gate_items": sum(v["gate_items"] for v in per.values()),
               "pairs_evaluated": len(r_new["pairs"]), "claims_evaluated": len(r_new["claims"]),
               "pairs_with_any_difference": diff_pairs, "claims_with_any_difference": diff_claims,
               "sensitivity_control": {"note": "the same records under table_value_guard; a difference shows the "
                                               "comparison can see the guard",
                                       "papers_that_differ": sorted(p for p, v in per.items() if v["differs_under_table_value_guard"])}}
    merge_results({"identity": payload})
    print(f"identity vs {BASELINE} (legacy, off): gate records identical {n_same}/{len(per)} "
          f"({payload['gate_inputs']} inputs, {payload['gate_items']} items); 55-pair evaluation differences: "
          f"pairs {diff_pairs or 'none'}, claims {diff_claims or 'none'}; under table_value_guard "
          f"{len(payload['sensitivity_control']['papers_that_differ'])} papers differ")


# --- STEP 3: children (D8) ---------------------------------------------------------------------------------------
def children(work: Path, arms: list[str]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    logf = work / "children_log.json"
    log = json.loads(logf.read_text(encoding="utf-8")) if logf.exists() else {}
    inv = {"started_utc": now(), "arms": arms, "reused_outputs": []}     # one entry per invocation: a resume is visible
    log.setdefault("_invocations", []).append(inv)
    logf.write_text(json.dumps(log, indent=1), encoding="utf-8")
    for arm in arms:
        fp, bp = ARMS[arm]
        for pid in PAPERS:
            out, key = work / f"{pid}_{arm}.json", f"{pid}:{arm}"
            if out.exists():
                inv["reused_outputs"].append(key)
                continue
            env = {**os.environ, "RGPT_FALLTHROUGH_POLICY": fp, "RGPT_BORDERLESS_POLICY": bp,
                   "CUDA_VISIBLE_DEVICES": "", "PYTHONIOENCODING": "utf-8"}
            start, t0 = now(), time.perf_counter()
            p = subprocess.run([sys.executable, "-B", str(Path(__file__)), "child", pid, arm, str(out)], env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            wall = round(time.perf_counter() - t0, 1)
            log[key] = {"returncode": p.returncode, "wall_seconds": wall, "started_utc": start, "ended_utc": now(),
                        "error": None if p.returncode == 0 and out.exists() else (p.stderr or "")[-3000:]}
            logf.write_text(json.dumps(log, indent=1), encoding="utf-8")
            print(f"  child {pid} {arm}: rc={p.returncode} {wall}s", flush=True)
    logf.write_text(json.dumps(log, indent=1), encoding="utf-8")


def load(work: Path, pid: str, arm: str) -> dict | None:
    f = work / f"{pid}_{arm}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


# --- L1 reproduction (D11) ---------------------------------------------------------------------------------------
def v9a_payload(work: Path, off_arm: str, on_arm: str, fallthrough: str) -> dict:
    """09A's own run() analysis, with its child call replaced by our arms (policy off -> off_arm, consensus -> on_arm),
    no crop written and 09A's results.json untouched."""
    captured = {}

    def fake_run(cmd, **_):
        pid, policy, out = cmd[-3:]
        src = work / f"{pid}_{off_arm if policy == 'off' else on_arm}.json"
        if not src.exists():
            return types.SimpleNamespace(returncode=1, stderr=f"missing child output {src.name}")
        shutil.copyfile(src, out)
        return types.SimpleNamespace(returncode=0, stderr="")
    saved = V.subprocess, V.merge_results, V.crop
    V.subprocess = types.SimpleNamespace(run=fake_run)
    V.merge_results = lambda section, payload: captured.update({section: payload})
    V.crop = lambda path, page, bbox, name: f"crops/{name}" if bbox else None
    os.environ["RGPT_FALLTHROUGH_POLICY"] = fallthrough
    try:
        V.run()
    finally:
        V.subprocess, V.merge_results, V.crop = saved
    return json.loads(canon(captured["validation"]))


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k not in VOLATILE}
    return [strip(v) for v in x] if isinstance(x, list) else x


def differences(a, b, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(set(a) | set(b), key=str)
                for d in (differences(a[k], b[k], f"{path}/{k}") if k in a and k in b else [f"{path}/{k} (one side only)"])]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path} (length {len(a)} vs {len(b)})"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    return [] if canon(a) == canon(b) else [path]


def reproduction(work: Path) -> dict:
    stored = json.loads(V.RESULTS.read_text(encoding="utf-8"))["validation"]
    got = v9a_payload(work, "L0", "L1", "legacy")
    diffs = differences(strip(stored), strip(got))
    return {"compared_with": "src/evaluation/borderless_09a/results.json#validation", "arms": ["L0", "L1"],
            "identical": not diffs, "n_differences": len(diffs), "differences": diffs[:200],
            "ignored_keys": sorted(VOLATILE), "versions_identical": canon(stored.get("versions")) == canon(got.get("versions")),
            "versions_09a": stored.get("versions"), "versions_now": got.get("versions")}


def run(work: Path) -> None:
    print("REMINDER: keep the laptop plugged in and awake for the whole run (two CPU consensus arms, ~7 h each in "
          "09A); 09A run 2 had a suspend gap.", flush=True)
    children(work, ["L0", "G0", "L1"])
    rep = reproduction(work)
    if not rep["identical"]:
        merge_results({"reproduction": rep})
        raise SystemExit(f"STOP: L1 does not reproduce 09A ({rep['n_differences']} differences); see results.json "
                         "'reproduction'. G1 not run, no criteria, no decision.")
    print("L1 reproduces 09A's validation payload exactly; running G1", flush=True)
    children(work, ["G1"])
    analyze(work)


# --- gating per arm (D9, D10) --------------------------------------------------------------------------------------
def unit(ev: dict, records: list[dict]) -> dict:
    u = {"binder_status": ev["binder_status"], "gate_final": ev["gate_final"],
         "gate_abstain_reasons": ev["gate_abstain_reasons"], "bound_correct": ev["bound_correct"],
         "returned": ev["returned"], "failure": ev["failure"], "bound_cell": ev["binder"].get("cell")}
    m = {t: src for it in ev["gate_items"] if it["abstain_reason"] == "table_value_unbound"
         for t, src in matched(it["value"], records).items()}
    return u | ({"matched": m} if m else {})


def matched(value: str, records: list[dict]) -> dict:
    """Where each of the claim's values is a table token: cell values, then table-block text (first 3 sources)."""
    toks, out = G.claim_value_tokens(value), {}
    for cell in G.paper_table_cells(records):
        for t in toks & G.numeric_tokens(cell.get("value")):
            out.setdefault(t, []).append(f"cell [{cell.get('row_label')} | {cell.get('column_header')}] = "
                                         f"{cell.get('value')!r} in {str(cell.get('caption'))[:50]!r}")
    for c in records:
        if c.get("block_type") == "table":
            for t in toks & G.numeric_tokens(c.get("text")):
                out.setdefault(t, []).append(f"table block {c.get('chunk_id')}: {c.get('text', '')[:70]!r}")
    return {t: v[:3] for t, v in sorted(out.items())}


def item(it: dict, records: list[dict]) -> dict:
    sb = it.get("structural_binding")
    out = {"value": it["value"][:300], "final": it["final"], "reason": it["abstain_reason"],
           "binding": it.get("structural_binding_status") if sb is None else sb.get("status")}
    if it["abstain_reason"] == "table_value_unbound":
        out["matched"] = matched(it["value"], records)
    return out


def gate_arm(work: Path, arm: str) -> dict:
    os.environ["RGPT_FALLTHROUGH_POLICY"] = ARMS[arm][0]
    outs = {pid: load(work, pid, arm) for pid in PAPERS}
    gold = [pid for pid in GOLD_PAPERS if outs[pid]]
    res = V.PE.evaluate([p for p in V.PAIRS if p["paper_id"] in gold],
                        {pid: {"before_chunks": outs[pid]["records"], "after_chunks": outs[pid]["records"],
                               "after_blocks": outs[pid]["table_blocks"], "surnames": outs[pid]["surnames"]} for pid in gold})
    sweep_a, sweep_b = {}, {}
    for c in CANDS:
        o = outs.get(c["paper_id"])
        if o:
            for i, it in enumerate(V.O.run_case(c["claim_text"], o["records"], o["surnames"], None)["gate_items"]):
                sweep_a[f"{c['candidate_id']}#{i}"] = item(it, o["records"])
    for o in filter(None, outs.values()):
        for ch in o["records"]:
            for i, it in enumerate(G.gate_paper({"results": ch["text"]}, o["records"], "FULL_TEXT",
                                                o["surnames"])["evidence"]["results"]):
                sweep_b[f"{ch['chunk_id']}#{i}"] = item(it, o["records"])
    return {"pairs": {r["pair_id"]: unit(r["after"]["CANONICAL"], outs[r["paper_id"]]["records"]) for r in res["pairs"]},
            "claims": {c["candidate_id"]: unit(c["after"]["REAL"], outs[c["paper_id"]]["records"]) for c in res["claims"]},
            "sweep_A": sweep_a, "sweep_B": sweep_b, "missing_children": [pid for pid in PAPERS if not outs[pid]]}


def ret(u: dict) -> bool:
    return u["returned"] if "returned" in u else u["final"] == G.RETURNED


def bound(u: dict) -> bool:
    return u["bound_correct"] if "returned" in u else u["binding"] == "bound"


def vb(u: dict) -> bool:                                         # RETURNED with a verified bind
    return ret(u) and bound(u)


def nb(u: dict) -> bool:                                         # RETURNED without a verified bind
    return ret(u) and not bound(u)


def view(u: dict) -> dict:
    keys = ("binder_status", "gate_final", "gate_abstain_reasons", "bound_correct", "returned") if "returned" in u \
        else ("final", "reason", "binding")
    return {k: u[k] for k in keys}


def counts(units: dict) -> dict:
    us = list(units.values())
    return {"units": len(us), "RETURNED": sum(map(ret, us)), "RETURNED_with_verified_bind": sum(map(vb, us)),
            "RETURNED_without_bind": sum(map(nb, us)),
            "binder_status": dict(Counter(str(u.get("binder_status", u.get("binding"))) for u in us)),
            "abstain_reasons": dict(Counter(r for u in us for r in (u.get("gate_abstain_reasons") or [u.get("reason")]) if r))}


def transitions(base: dict, other: dict) -> list[dict]:
    out = []
    for k in sorted(base.keys() | other.keys()):
        a, b = base.get(k), other.get(k)
        if a is None or b is None or a.get("value") != b.get("value"):
            out.append({"id": k, "UNMEASURED": "unit missing or not aligned across arms"})
        elif canon(view(a)) != canon(view(b)):
            out.append({"id": k, **({"value": a["value"]} if "value" in a else {}), "before": view(a), "after": view(b),
                        **({"matched": b["matched"]} if b.get("matched") else {})})
    return out


def removed(lo: dict, g: dict) -> list[dict]:
    return [{"id": k, **({"value": u["value"]} if "value" in u else {}), "before": view(u), "after": view(g[k]),
             **({"matched": g[k]["matched"]} if g[k].get("matched") else {})}
            for k, u in sorted(lo.items()) if k in g and ret(u) and not ret(g[k])]


# --- criteria and decision (D12-D14) -------------------------------------------------------------------------------
def criteria(A: dict, gpay: dict, stored: dict) -> dict:
    by_pair = {p["pair_id"]: p for p in V.PAIRS}
    reg = stored["criteria"]["P3"]["regressions"]
    if sorted(r["pair_id"] for r in reg) != REGRESSED_09A:
        raise SystemExit(f"STOP: 09A's stored regressions are {[r['pair_id'] for r in reg]}, not {REGRESSED_09A}")
    q1_units = [("pairs", r["pair_id"]) if why.startswith("CANONICAL") else ("claims", by_pair[r["pair_id"]]["candidate_id"])
                for r in reg for why in r["reasons"]]
    q1 = [{"unit": f"{kind}:{uid}", "G1_returned": (A["G1"][kind].get(uid) or {}).get("returned"),
           "G1_reasons": (A["G1"][kind].get(uid) or {}).get("gate_abstain_reasons"),
           "G1_matched": (A["G1"][kind].get(uid) or {}).get("matched")} for kind, uid in q1_units]

    def q2(lo: str, g: str) -> list[str]:
        return [f"{kind}:{k}" for kind in KINDS for k, u in A[lo][kind].items() if vb(u) and not (k in A[g][kind] and vb(A[g][kind][k]))]

    def q3(lo: str, g: str) -> list[str]:
        return [f"{kind}:{k}" for kind in KINDS for k, u in A[g][kind].items() if nb(u) and not (k in A[lo][kind] and nb(A[lo][kind][k]))]
    q2v, q3v = {"L0->G0": q2("L0", "G0"), "L1->G1": q2("L1", "G1")}, {"G0 vs L0": q3("L0", "G0"), "G1 vs L1": q3("L1", "G1")}

    e1 = {cid: A["G1"]["claims"].get(cid, {}).get("bound_correct") for cid in ("C013", "C085")}
    stored_neg = {(n["paper_id"], n["table"]): n for n in stored["neg"]}
    e2 = []
    for n in gpay["neg"]:
        key, s = (n["paper_id"], n["table"]), stored_neg.get((n["paper_id"], n["table"]), {})
        same_cells = canon(n.get("accepted_cells") or []) == canon(s.get("accepted_cells") or [])
        e2.append({"table": f"{n['paper_id']} {n['table']}", "verdict": n.get("verdict"), "code": n.get("code"),
                   "expected": EXPECT_NEG.get(key), "09A": [s.get("verdict"), s.get("code")],
                   "accepted_cells": len(n.get("accepted_cells") or []), "cells_identical_to_09A": same_cells,
                   "ok": (n.get("verdict"), n.get("code")) == EXPECT_NEG.get(key) == (s.get("verdict"), s.get("code"))
                         and same_cells})
    p019_cells = sum(x["accepted_cells"] for x in e2 if x["table"].startswith("P019"))
    e3 = [f"{p['pair_id']}:{'CANONICAL' if kind == 'pairs' else 'REAL'}" for p in V.PAIRS
          for kind, uid in (("pairs", p["pair_id"]), ("claims", p["candidate_id"]))
          if uid in A["L0"][kind] and uid in A["G1"][kind] and not A["L0"][kind][uid]["returned"]
          and A["G1"][kind][uid]["returned"] and not A["G1"][kind][uid]["bound_correct"]]
    p4 = gpay["criteria"]["P4"]
    e5 = [f"{kind}:{k}" for kind in KINDS for k, u in A["L0"][kind].items() if bound(u) and not (k in A["G1"][kind] and bound(A["G1"][kind][k]))]
    crit = {"Q1": {"pass": all(x["G1_returned"] is False for x in q1), "units": q1},
            "Q2": {"pass": not any(q2v.values()), "violations": q2v},
            "Q3": {"pass": not any(q3v.values()), "violations": q3v},
            "E1": {"pass": all(e1.values()), "G1_bound_correct": e1},
            "E2": {"pass": len(e2) == len(EXPECT_NEG) and all(x["ok"] for x in e2) and p019_cells == 48,
                   "tables": e2, "P019_accepted_cells": p019_cells},
            "E3": {"pass": not e3, "violations": e3},
            "E4": {"pass": not p4["absent_from_text_layer"], "accepted_cells": p4["accepted_cells"],
                   "absent_from_text_layer": p4["absent_from_text_layer"]},
            "E5": {"pass": not e5, "violations": e5}}
    # D15, per criterion: a missing child output among the arms x papers a criterion reads, or a unit not aligned
    # across arms, makes that criterion UNMEASURED (never PASS).
    units = set(GOLD_PAPERS) | {c["paper_id"] for c in CANDS if c["paper_id"] in PAPERS}
    need = {"Q1": (["G1"], {by_pair[r["pair_id"]]["paper_id"] for r in reg}), "Q2": (list(ARMS), units),
            "Q3": (list(ARMS), units), "E1": (["G1"], {p["paper_id"] for p in V.PAIRS if p["candidate_id"] in e1}),
            "E2": (["G1"], {n[0] for n in V.NEG}), "E3": (["L0", "G1"], set(GOLD_PAPERS)),
            "E4": (["G1"], set(PAPERS)), "E5": (["L0", "G1"], units)}
    unaligned = {arm: [f"{kind}:{t['id']}" for kind in KINDS for t in transitions(A["L0"][kind], A[arm][kind])
                       if "UNMEASURED" in t] for arm in ("L1", "G0", "G1")}
    for k, (arms, papers) in need.items():
        miss = sorted(f"{a}:{p}" for a in arms for p in papers if p in A[a]["missing_children"])
        bad = [u for a in arms if a != "L0" for u in unaligned[a]] if k in ("Q2", "Q3", "E5") else []
        if miss or bad:
            crit[k].update({"pass": "UNMEASURED", "missing_children": miss, "unaligned_units": bad[:50]})
    return crit


def decide(crit: dict) -> str:
    q = [k for k in ("Q1", "Q2", "Q3") if crit[k]["pass"] is not True]
    e = [k for k in ("E1", "E2", "E3", "E4", "E5") if crit[k]["pass"] is not True]
    if q:
        return f"KEEP BOTH DEFAULTS (fallthrough_policy=legacy, borderless_policy=off): {', '.join(q)} not PASS"
    if e:
        return f"ENABLE fallthrough_policy=table_value_guard ONLY; borderless_policy stays off: {', '.join(e)} not PASS"
    return "ENABLE fallthrough_policy=table_value_guard, then borderless_policy=consensus (two separate commits)"


def timing(work: Path) -> dict:
    logf = work / "children_log.json"
    log = json.loads(logf.read_text(encoding="utf-8")) if logf.exists() else {}
    per: dict = {}
    for arm in ("L1", "G1"):
        for pid in PAPERS:
            for b in (load(work, pid, arm) or {}).get("table_blocks", []):
                d = b.get("table_borderless") or {}
                if d.get("page") is not None:
                    per.setdefault(arm, {}).setdefault(pid, {})[str(d["page"])] = {
                        k: ((d.get("parsers") or {}).get(k) or {}).get("seconds_page") for k in ("A", "B")}
    summary = {}
    for arm, papers in per.items():
        for k in ("A", "B"):
            s = [v[k] for pages in papers.values() for v in pages.values() if v[k] is not None]
            summary.setdefault(arm, {})[k] = {"pages": len(s), "min": min(s, default=None), "max": max(s, default=None),
                                              "total": round(sum(s), 1)}
    walls = {arm: round(sum(v.get("wall_seconds") or 0 for k, v in log.items() if k.endswith(f":{arm}")), 1) for arm in ARMS}
    return {"per_parser_seconds_per_page": per, "per_parser_summary": summary, "child_wall_seconds_total": walls,
            "children": log, "parsers": B.BACKENDS}


def analyze(work: Path, out: Path = RESULTS) -> None:
    stored = json.loads(V.RESULTS.read_text(encoding="utf-8"))["validation"]
    rep = reproduction(work)
    A = {arm: gate_arm(work, arm) for arm in ARMS}
    gpay = v9a_payload(work, "G0", "G1", "table_value_guard")
    crit = criteria(A, gpay, stored)
    decision = decide(crit) if rep["identical"] else "NONE: L1 does not reproduce 09A (STOP); criteria not used"
    same_repr = {f"{a}=={b}": {pid: canon((load(work, pid, a) or {}).get("records")) == canon((load(work, pid, b) or {}).get("records"))
                               for pid in PAPERS} for a, b in (("L0", "G0"), ("L1", "G1"))}
    removed_by_guard = {f"{lo}->{g}": {kind: removed(A[lo][kind], A[g][kind]) for kind in ("pairs", "claims", "sweep_A", "sweep_B")}
                        for lo, g in (("L0", "G0"), ("L1", "G1"))}
    payload = {
        "generated_at_utc": now(), "papers": PAPERS, "arms": {k: {"fallthrough_policy": f, "borderless_policy": b}
                                                              for k, (f, b) in ARMS.items()},
        "versions": {arm: (load(work, PAPERS[0], arm) or {}).get("versions") for arm in ARMS},
        "timing": timing(work), "representation_identical_across_fallthrough": same_repr,
        "summary_2x2": {arm: {kind: counts(A[arm][kind]) for kind in ("pairs", "claims", "sweep_A", "sweep_B")} for arm in ARMS},
        "pairs": {k: {arm: view(A[arm]["pairs"][k]) | {"bound_cell": A[arm]["pairs"][k]["bound_cell"]} for arm in ARMS
                      if k in A[arm]["pairs"]} for k in A["L0"]["pairs"]},
        "claims": {k: {arm: view(A[arm]["claims"][k]) | {"failure": A[arm]["claims"][k]["failure"]} for arm in ARMS
                       if k in A[arm]["claims"]} for k in A["L0"]["claims"]},
        "sweep_A_items": {arm: A[arm]["sweep_A"] for arm in ARMS},
        "transitions_vs_L0": {arm: {kind: transitions(A["L0"][kind], A[arm][kind]) for kind in ("pairs", "claims", "sweep_A", "sweep_B")}
                              for arm in ("L1", "G0", "G1")},
        "returns_removed_by_guard": removed_by_guard,
        "returns_removed_by_guard_counts": {k: {kind: len(v) for kind, v in d.items()} for k, d in removed_by_guard.items()},
        "guard_arms_in_09A_format": {k: gpay[k] for k in ("summary_off_vs_on", "criteria", "neg", "canary_newline_cells", "unmeasured")},
        "criteria": crit, "decision": decision}
    merge_results({"reproduction": rep, "run": payload}, out)
    print("reproduction of 09A by L1: " + ("IDENTICAL" if rep["identical"] else f"{rep['n_differences']} differences"))
    for arm in ARMS:
        s = payload["summary_2x2"][arm]
        print(f"  {arm}: " + "; ".join(f"{kind} {x['RETURNED']} returned ({x['RETURNED_with_verified_bind']} verified, "
                                       f"{x['RETURNED_without_bind']} without bind) of {x['units']}" for kind, x in s.items()))
    print("criteria: " + ", ".join(f"{k} {v['pass']}" for k, v in crit.items() if k[0] in "QE"))
    print(f"returns removed by the guard: {payload['returns_removed_by_guard_counts']}")
    print(f"decision: {decision}")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "identity":
        identity()
    elif mode == "child":
        V.child(sys.argv[2], ARMS[sys.argv[3]][1], sys.argv[4])
    elif mode == "children":
        children(Path(sys.argv[2]), sys.argv[3:])
    elif mode == "run":
        run(Path(sys.argv[2]))
    elif mode == "analyze":
        analyze(Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else RESULTS)
    else:
        raise SystemExit(f"unknown mode {mode}")
