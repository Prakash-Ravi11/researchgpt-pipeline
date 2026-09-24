"""Turn trace.jsonl into the funnel tables, and check that it adds up.

    python diagnostics/funnel/analyze_funnel.py --out trace_on

Writes funnel.csv and drops_by_reason.csv beside the trace, and prints the three
things the diagnosis turns on: the 142 -> 92 step by reason, the claim funnel,
and the full per-item trace for every RETURNED result.

Conservation is asserted two ways. WITHIN a stage, in = out + dropped, which the
emitter makes true by construction. ACROSS stages, the KEEP/PASS count leaving
stage k must equal the number of items entering stage k+1 -- that one can fail,
and any failure is printed rather than reconciled.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_ROOT = HERE / "out"

# Stages that form a chain on the SAME item population, in order.
CHAIN_A = ["A1_table_block", "A2_grid_return", "A3_cell_table"]
CHAIN_B = ["B1_claim", "B2_enters_binder", "B4_binding", "B5_result"]
KEEP = ("KEEP", "PASS")


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def stage_table(rows: list[dict]) -> list[dict]:
    """in / out / dropped per stage, split by extraction_path."""
    agg: dict[tuple, Counter] = defaultdict(Counter)
    for r in rows:
        det = r.get("detail") or {}
        path = det.get("extraction_path", "n/a") if isinstance(det, dict) else "n/a"
        c = agg[(r["stage"], r["item_type"], path)]
        c["in"] += 1
        c["out" if r["status"] in KEEP else "dropped"] += 1
    out = []
    for (stage, itype, path), c in sorted(agg.items()):
        out.append({"stage": stage, "item_type": itype, "extraction_path": path,
                    "in": c["in"], "out": c["out"], "dropped": c["dropped"],
                    "conserved": c["in"] == c["out"] + c["dropped"]})
    return out


def cross_stage_violations(rows: list[dict], chain: list[str]) -> list[str]:
    per = {s: Counter() for s in chain}
    for r in rows:
        if r["stage"] in per:
            per[r["stage"]]["in"] += 1
            if r["status"] in KEEP:
                per[r["stage"]]["kept"] += 1
    bad = []
    for a, b in zip(chain, chain[1:]):
        kept, nxt = per[a]["kept"], per[b]["in"]
        if kept != nxt:
            bad.append(f"{a} kept {kept} but {b} received {nxt} (delta {nxt - kept:+d})")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="trace_on")
    a = ap.parse_args()
    out = OUT_ROOT / a.out
    rows = load(out / "trace.jsonl")
    print(f"{len(rows)} trace rows from {out / 'trace.jsonl'}\n")

    # ---- funnel.csv ------------------------------------------------------
    st = stage_table(rows)
    with (out / "funnel.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["stage", "item_type", "extraction_path",
                                           "in", "out", "dropped", "conserved"])
        w.writeheader()
        w.writerows(st)
    print("== funnel (in / out / dropped, by extraction_path) ==")
    print(f"{'stage':20}{'item_type':16}{'path':12}{'in':>7}{'out':>7}{'drop':>7}")
    for r in st:
        print(f"{r['stage']:20}{r['item_type']:16}{r['extraction_path']:12}"
              f"{r['in']:>7}{r['out']:>7}{r['dropped']:>7}")

    viol = [r for r in st if not r["conserved"]]
    print(f"\nwithin-stage conservation violations: {len(viol)}")
    for r in viol:
        print(f"  {r}")
    for name, chain in (("A", CHAIN_A), ("B", CHAIN_B)):
        bad = cross_stage_violations(rows, chain)
        print(f"cross-stage violations, chain {name}: {len(bad)}")
        for b in bad:
            print(f"  {b}")

    # ---- drops_by_reason.csv --------------------------------------------
    dr = Counter((r["stage"], r["reason_code"], r["code_location"])
                 for r in rows if r["status"] not in KEEP)
    with (out / "drops_by_reason.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "reason_code", "code_location", "count"])
        for (s, rc, loc), n in sorted(dr.items(), key=lambda kv: (kv[0][0], -kv[1])):
            w.writerow([s, rc, loc, n])
    unatt = sum(n for (s, rc, _l), n in dr.items() if rc == "UNATTRIBUTED")
    print(f"\n== drops by reason ==  (UNATTRIBUTED total: {unatt})")
    for (s, rc, loc), n in sorted(dr.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"  {s:20} {rc:34} {n:>5}   {loc}")

    # ---- the 142 -> 92 step ---------------------------------------------
    g = [r for r in rows if r["stage"] == "A2_grid_return"]
    a3 = [r for r in rows if r["stage"] == "A3_cell_table"]
    print(f"\n== TABLES: {len(g)} blocks -> "
          f"{sum(1 for r in g if r['status'] in KEEP)} grid returns -> "
          f"{sum(1 for r in a3 if r['status'] in KEEP)} cell tables ==")
    print("  removed at A2 (no grid at all):")
    for rc, n in Counter(r["reason_code"] for r in g if r["status"] not in KEEP).most_common():
        print(f"    {rc:34} {n:>4}")
    print("  removed at A3 (gate + post-gate parse):")
    for rc, n in Counter(r["reason_code"] for r in a3 if r["status"] not in KEEP).most_common():
        print(f"    {rc:34} {n:>4}")
    print("  per paper (blocks / grid returns / cell tables / dropped):")
    papers = sorted({r["paper_id"] for r in g})
    for p in papers:
        gi = [r for r in g if r["paper_id"] == p]
        ai = [r for r in a3 if r["paper_id"] == p]
        gr = sum(1 for r in gi if r["status"] in KEEP)
        ct = sum(1 for r in ai if r["status"] in KEEP)
        print(f"    {p[:12]}  {len(gi):>3} {gr:>3} {ct:>3} {len(gi) - ct:>4}")

    # ---- claims into the binder -----------------------------------------
    b2 = [r for r in rows if r["stage"] == "B2_enters_binder"]
    entered = [r for r in b2 if r["status"] in KEEP]
    print(f"\n== CLAIMS: {len(b2)} total, {len(entered)} entered the binder "
          f"({len(b2) - len(entered)} never did) ==")
    for rc, n in Counter(r["reason_code"] for r in b2 if r["status"] not in KEEP).most_common():
        print(f"    never entered: {rc:30} {n:>4}")
    per_paper = Counter(r["paper_id"] for r in entered)
    print(f"  papers with >=1 claim in the binder: {len(per_paper)} of {len(papers)}")
    for p in papers:
        print(f"    {p[:12]}  claims={sum(1 for r in b2 if r['paper_id'] == p):>2}"
              f"  entered={per_paper.get(p, 0):>2}")

    bind = [r for r in rows if r["stage"] == "B4_binding"]
    print(f"\n== BINDINGS: {sum(1 for r in bind if r['status'] == 'PASS')} bound "
          f"of {len(bind)} attempts ==")
    for rc, n in Counter(r["reason_code"] for r in bind).most_common():
        print(f"    {rc:34} {n:>4}")

    # ---- the 3 -> 0 step: full trace for every RETURNED result ----------
    res = [r for r in rows if r["stage"] == "B5_result"]
    ret = [r for r in res if r["status"] == "PASS"]
    probes = {r["paper_id"]: [] for r in rows if r["stage"] == "B2_binder"}
    for r in rows:
        if r["stage"] == "B2_binder":
            probes[r["paper_id"]].append(r)
    print(f"\n== THE {len(ret)} RETURNED RESULTS, in full ==")
    for r in ret:
        d = r["detail"] or {}
        print(f"\n  {r['item_id']}  field={d.get('field')}")
        print(f"    value        : {d.get('value')!r}")
        print(f"    binding      : {d.get('binding_status')}  (bucket {d.get('bucket')})")
        bp = [p for p in probes.get(r["paper_id"], [])
              if (p.get("detail") or {}).get("claim_text") == d.get("value")]
        if not bp:
            print("    binder       : NEVER CALLED — no numeric anchor in this value, so "
                  "gate.py:525 skips the binding branch entirely")
            print("    candidates   : none were ever considered")
            continue
        for p in bp:
            pd = p["detail"] or {}
            print(f"    claim raw    : {pd.get('claim_value_raw')}")
            print(f"    claim norm   : {pd.get('claim_value_normalized')}")
            print(f"    metric toks  : {pd.get('claim_metric_tokens')}  "
                  f"subject={pd.get('claim_subject')!r}")
            print(f"    comparison   : {pd.get('comparison')}")
            print(f"    result       : {pd.get('result')} — {pd.get('result_reason')}")
            print(f"    cells in paper: {pd.get('n_cells_in_paper')}, "
                  f"candidates considered: {len(pd.get('candidates') or [])}")
            for c in (pd.get("candidates") or [])[:12]:
                print(f"      cell raw={c['cell_raw']!r} norm={c['cell_normalized']!r} "
                      f"path={c['header_path']!r} row={c['row_label']!r} "
                      f"col_ok={c['column_matches_metric']} row_ok={c['row_matches_subject']} "
                      f"val_hits={c['value_match']}")

    print(f"\n-> {out / 'funnel.csv'}\n-> {out / 'drops_by_reason.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
