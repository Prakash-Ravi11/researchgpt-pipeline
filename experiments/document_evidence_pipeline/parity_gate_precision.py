"""Re-slice the 12 parity-gate fallbacks against Criterion J.

Criterion J is fixed in PARITY_GATE_PRECISION_REPORT.md and committed BEFORE this
harness produced any number (git eeab489):

    JUSTIFIED       <=>  pdf_survival(all) > latex_survival(all)
    OVER-TRIGGERED  <=>  latex_survival(all) >= pdf_survival(all)
                         (the gate fired on a sub-split alone)

Reads the FROZEN measurement already recorded on each fallback paper's chunks
(`latex_parity_fallback`, written by process_paper_grounded from
latex_parity.check_parity). Nothing is re-run, re-fetched or re-scored.

  python -u experiments/document_evidence_pipeline/parity_gate_precision.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LI = HERE / "runs" / "latex_ingestion"
OUT = HERE / "runs" / "parity_gate_precision"
OUT.mkdir(parents=True, exist_ok=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPLITS = ("all", "table", "prose", "caption")


def main() -> int:
    reps = json.loads((LI / "reps.json").read_text(encoding="utf-8"))
    fallback_ids = sorted(p for p, r in reps.items() if r == "pdf(fallback)")
    rec = {}
    for c in json.loads((LI / "processed" / "chunks.json").read_text(encoding="utf-8")):
        f = c.get("latex_parity_fallback")
        if f and c["paper_id"] not in rec:
            rec[c["paper_id"]] = f
    missing = [p for p in fallback_ids if p not in rec]
    if missing:
        sys.exit(f"missing frozen parity record for {missing}")

    rows = []
    for pid in fallback_ids:
        r = rec[pid]
        per = r["per_location"]
        a = per.get("all", {})
        lx, pf = a.get("latex"), a.get("pdf")
        n_all = a.get("n", 0)
        justified = (pf is not None and lx is not None and pf > lx)
        lost = round(n_all * (pf - lx)) if justified else 0
        fired = []
        for s in SPLITS:
            d = per.get(s)
            if d and d["latex"] < d["pdf"]:
                fired.append(s)
        row = {"paper_id": pid, "verdict": "JUSTIFIED" if justified else "OVER_TRIGGERED",
               "n_ground_truth": r.get("n_ground_truth"),
               "all_latex": lx, "all_pdf": pf, "all_deficit": (round(pf - lx, 4) if pf is not None else None),
               "occurrences_lost_all": lost, "splits_fired": fired, "reason": r.get("reason")}
        for s in SPLITS:
            d = per.get(s)
            row[f"{s}_n"] = d["n"] if d else 0
            row[f"{s}_latex"] = d["latex"] if d else None
            row[f"{s}_pdf"] = d["pdf"] if d else None
            row[f"{s}_deficit"] = round(d["pdf"] - d["latex"], 4) if d else None
        rows.append(row)
    (OUT / "per_fallback.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    just = [r for r in rows if r["verdict"] == "JUSTIFIED"]
    over = [r for r in rows if r["verdict"] == "OVER_TRIGGERED"]
    n = len(rows)
    print("=" * 96)
    print("PARITY-GATE PRECISION — 12 fallbacks re-sliced against Criterion J (pre-registered, git eeab489)")
    print("=" * 96)
    print(f"  JUSTIFIED      {len(just)}/{n}")
    print(f"  OVER-TRIGGERED {len(over)}/{n}")
    print(f"  precision      {len(just)/n:.2f}\n")

    print(f"  {'paper':13}{'verdict':16}{'nGT':>5}{'all lx':>8}{'all pdf':>9}{'lost':>6}  splits fired (deficit)")
    for r in rows:
        fired = ", ".join(f"{s} -{r[f'{s}_deficit']:.3f} (n={r[f'{s}_n']})" for s in r["splits_fired"])
        print(f"  {r['paper_id'][:12]:13}{r['verdict']:16}{r['n_ground_truth']:>5}"
              f"{r['all_latex']:>8.3f}{r['all_pdf']:>9.3f}{r['occurrences_lost_all']:>6}  {fired}")

    print("\n  PER-SPLIT deficits that triggered each fallback")
    print(f"  {'paper':13}{'table':>22}{'prose':>22}{'caption':>22}")
    for r in rows:
        cells = []
        for s in ("table", "prose", "caption"):
            if not r[f"{s}_n"]:
                cells.append("—")
            else:
                mark = "*" if s in r["splits_fired"] else " "
                cells.append(f"{mark}{r[f'{s}_latex']:.3f}/{r[f'{s}_pdf']:.3f} n={r[f'{s}_n']}")
        print(f"  {r['paper_id'][:12]:13}{cells[0]:>22}{cells[1]:>22}{cells[2]:>22}")
    print("   (* = this split fired;  shown as latex/pdf survival)")

    if over:
        print(f"\n  OVER-TRIGGERED cases — which split fired and by how much")
        for r in over:
            print(f"    {r['paper_id'][:12]}  all latex {r['all_latex']:.3f} >= pdf {r['all_pdf']:.3f} "
                  f"(no net loss); fired on:")
            for s in r["splits_fired"]:
                print(f"       {s:8} latex {r[f'{s}_latex']:.3f} < pdf {r[f'{s}_pdf']:.3f}  "
                      f"deficit {r[f'{s}_deficit']:.3f} over n={r[f'{s}_n']} occurrences")
    else:
        print("\n  OVER-TRIGGERED cases: none")

    from collections import Counter
    fired_counter = Counter(s for r in rows for s in r["splits_fired"])
    lost_vals = sorted(r["occurrences_lost_all"] for r in just)
    print(f"\n  splits that fired, across all 12: {dict(fired_counter)}")
    if lost_vals:
        print(f"  occurrences lost on `all` (justified cases): min {lost_vals[0]}  "
              f"median {lost_vals[len(lost_vals)//2]}  max {lost_vals[-1]}")
        print(f"  justified cases losing <= 2 occurrences: "
              f"{sum(1 for v in lost_vals if v <= 2)}/{len(lost_vals)}")
    (OUT / "summary.json").write_text(json.dumps(
        {"criterion": "J: pdf_survival(all) > latex_survival(all)",
         "n": n, "justified": len(just), "over_triggered": len(over),
         "precision": round(len(just) / n, 4),
         "splits_fired_counts": dict(fired_counter),
         "occurrences_lost_all_justified": lost_vals}, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
