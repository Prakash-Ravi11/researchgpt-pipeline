"""Build table_ledger.csv and claim_ledger.csv from a trace_on run, with the
pre-registered reconciliation assertions.

    python diagnostics/funnel/build_ledgers.py --out trace_on --dest <dir>

Read-only over the trace and the run's results.json. Every existence check uses
the binder's OWN comparison (gate._has, reproduced exactly) and the binder's own
claim-number regex (anchors.NUMERIC_ANCHOR_RE), so a "value found" here means
found by the same rule the binder would have applied.

Assertion failures are printed and the exit code is 1; nothing is reconciled
silently.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The binder's own rules, imported rather than restated where possible.
from src.evidence.anchors import NUMERIC_ANCHOR_RE  # noqa: E402

DISCARD_REASONS = ("empty_value", "empty_header", "value_equals_row_label",
                   "row_label_corner")


def has(n: str, s) -> bool:
    """gate._has, reproduced exactly (gate.py:459-465)."""
    s = str(s)
    if n == re.sub(r"[^\d.\-]", "", s):
        return True
    return bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))


def load_trace(path: Path) -> list[dict]:
    # split("\n"), not splitlines(): splitlines() also breaks on U+2028/U+2029/
    # U+0085, which json.dumps leaves unescaped inside string values.
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="trace_on")
    ap.add_argument("--dest", default=None)
    a = ap.parse_args()
    out = HERE / "out" / a.out
    dest = Path(a.dest) if a.dest else out
    dest.mkdir(parents=True, exist_ok=True)

    rows = load_trace(out / "trace.jsonl")
    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    papers = payload["papers"]
    res = payload["results"]

    # ---- index the trace -------------------------------------------------
    attach = {}                       # table_id -> A0 detail row
    for r in rows:
        if r["stage"] == "A0_attach_detail":
            attach[r["item_id"]] = r
    items = [r for r in rows if r["stage"] == "B0_evidence_item"]
    binds = [r for r in rows if r["stage"] == "B2_binder"]

    # real block_id per table, joined by index (both iterate tbl_blocks in order)
    block_ids: dict[str, str] = {}
    for pid in papers:
        for i, t in enumerate(res[pid].get("tables") or []):
            block_ids[f"{pid}:{i}"] = t.get("block_id") or ""

    # which block_ids grounded a RETURNED metric
    returned_metric_blocks = {
        (r["paper_id"], (r["detail"] or {}).get("block_id"))
        for r in items
        if (r["detail"] or {}).get("field") == "metrics"
        and (r["detail"] or {}).get("final") == "RETURNED"
    }

    # ---- table ledger ----------------------------------------------------
    tl_rows, problems = [], []
    for pid in papers:
        for i, _t in enumerate(res[pid].get("tables") or []):
            tid = f"{pid}:{i}"
            a0 = attach.get(tid)
            if a0 is None:
                problems.append(f"no A0_attach_detail row for {tid}")
                continue
            d = a0["detail"] or {}
            disc = d.get("discards") or {}
            bid = block_ids.get(tid, "")
            tl_rows.append({
                "paper_id": pid,
                "table_id": tid,
                "block_id": bid,
                "grid_returned": bool(d.get("grid_returned")),
                "gate_result": d.get("gate_result"),
                "gate_reason_codes": d.get("gate_reason_code") or "",
                "gate_reason_raw": d.get("gate_reason_raw") or "",
                "path": "cell" if d.get("extraction_path") == "cell_table" else "fallback",
                "n_cells_attached": d.get("n_attached", 0),
                "n_cells_discarded_at_attach": sum(
                    disc.get(k, 0) for k in ("empty_value", "empty_header",
                                             "value_equals_row_label")),
                "discarded_empty_value": disc.get("empty_value", 0),
                "discarded_empty_header": disc.get("empty_header", 0),
                "discarded_value_equals_row_label": disc.get("value_equals_row_label", 0),
                "row_label_corner_cells": disc.get("row_label_corner", 0),
                "rows_before_gate": d.get("rows_before_gate", 0),
                "rows_after_gate": d.get("rows_after_gate", 0),
                "contributed_to_returned_metric": (pid, bid) in returned_metric_blocks,
            })

    fields = list(tl_rows[0].keys()) if tl_rows else []
    with (dest / "table_ledger.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(tl_rows)

    n_rows = len(tl_rows)
    n_grid = sum(1 for r in tl_rows if r["grid_returned"])
    n_nogrid = n_rows - n_grid
    n_gate_rej = sum(1 for r in tl_rows if r["grid_returned"]
                     and r["gate_result"] != "passed")
    n_cell = sum(1 for r in tl_rows if r["path"] == "cell")
    n_fallback = sum(1 for r in tl_rows if r["path"] == "fallback")
    n_attached = sum(r["n_cells_attached"] for r in tl_rows)
    n_contrib = sum(1 for r in tl_rows if r["contributed_to_returned_metric"])
    ret_metric_items = [r for r in items
                        if (r["detail"] or {}).get("field") == "metrics"
                        and (r["detail"] or {}).get("final") == "RETURNED"]
    n_ret_metrics = len(ret_metric_items)
    # The harness's headline "3" counts only metrics values containing a digit
    # (parser_backend_measure.py:225-227 skips digit-free values); the gate
    # itself returns more. Both are reported so the 3 is never mistaken for all.
    n_ret_metrics_digit = sum(1 for r in ret_metric_items
                              if re.search(r"\d", (r["detail"] or {}).get("value") or ""))
    # grids that passed the gate but produced no cells (post-gate parse loss)
    n_post_parse_loss = sum(1 for r in tl_rows if r["grid_returned"]
                            and r["gate_result"] == "passed" and r["path"] == "fallback")

    A = []

    def check(name, got, want):
        ok = got == want
        A.append({"assertion": name, "got": got, "expected": want, "pass": ok})
        return ok

    check("table ledger rows == 160", n_rows, 160)
    check("grid_returned == 142", n_grid, 142)
    check("no-grid == 18", n_nogrid, 18)
    # The brief's "gate-rejected grids == 50" is the count of grid returns that
    # produced NO cell table. Measurement splits it: 46 whole-table quality-gate
    # rejections (_gate_grid, represent_layout.py:405) + 4 that PASSED the gate
    # and then produced no cell in _layout_table_cells (represent_layout.py:76-79).
    # The aggregate is asserted; the split is reported as a sub-fact, not merged.
    check("grid returns producing no cell table == 50", n_grid - n_cell, 50)
    check("  of which whole-table gate rejections == 46", n_gate_rej, 46)
    check("  of which post-gate parse losses == 4", n_post_parse_loss, 4)
    check("fallback == 68", n_fallback, 68)
    check("no-grid + no-cell-table grids == fallback",
          n_nogrid + (n_grid - n_cell), n_fallback)
    check("cell tables == 92", n_cell, 92)
    check("attached cells == 2187", n_attached, 2187)
    # This one is FALSIFIED BY MEASUREMENT, and that is the finding, not a defect
    # in the instrumentation. Not one RETURNED metric grounds to a table block:
    # every one grounds to prose. So no table "accounts for" a returned metric.
    # Recorded, not reconciled.
    A.append({"assertion": "tables contributing to returned metrics account for "
                           "the returned metrics (per brief)",
              "got": n_contrib, "expected": n_ret_metrics, "pass": False,
              "falsified_premise": "0 of the RETURNED metrics ground to a table "
                                   "block; all ground to prose blocks, so no table "
                                   "contributes to any returned metric",
              "returned_metrics_all": n_ret_metrics,
              "returned_metrics_with_a_digit": n_ret_metrics_digit})

    # ---- claim ledger ----------------------------------------------------
    # per-paper table facts for the existence checks
    per_paper = defaultdict(lambda: {"cell_tables": 0, "attached": [], "discarded": [],
                                     "fallback_text": []})
    for tid, a0 in attach.items():
        pid = a0["paper_id"]
        d = a0["detail"] or {}
        P = per_paper[pid]
        if d.get("extraction_path") == "cell_table":
            P["cell_tables"] += 1
            ids = d.get("attached_cell_ids") or []
            vals = d.get("attached_values") or []
            if len(ids) == len(vals):
                P["attached"] += list(zip(ids, vals))
            else:
                P["attached"] += [(f"{tid}#?", v) for v in vals]
            P["discarded"] += [(tid, v) for v in (d.get("discarded_values") or [])]
        else:
            P["fallback_text"].append((tid, d.get("block_text") or ""))

    cl_rows = []
    for r in items:
        d = r["detail"] or {}
        if d.get("field") not in ("metrics", "results"):
            continue
        text = d.get("value") or ""
        if not re.search(r"\d", text):
            continue                      # matches the harness's own claim population
        pid = r["paper_id"]
        nums = NUMERIC_ANCHOR_RE.findall(text)
        status = d.get("binding_status")
        entered = status is not None
        P = per_paper[pid]

        hit_cells = [cid for cid, v in P["attached"] if any(has(n, v) for n in nums)]
        hit_disc = any(any(has(n, v) for n in nums) for _t, v in P["discarded"])
        hit_fb = [t for t, txt in P["fallback_text"] if any(has(n, txt) for n in nums)]

        cl_rows.append({
            "paper_id": pid,
            "claim_id": r["item_id"],
            "field": d.get("field"),
            "claim_text": text,
            "numeric_values_raw": "|".join(nums),
            "numeric_values_normalized": "|".join(nums),
            "entered_binder": entered,
            "binding_status": status or "no_binding_call",
            "terminal_state": d.get("final") or "ABSTAINED",
            "terminal_reason_code": r["reason_code"],
            "paper_has_post_gate_cell_table": P["cell_tables"] > 0,
            "value_found_in_attached_cells": bool(hit_cells),
            "attached_cell_ids": "|".join(hit_cells[:8]),
            "value_found_in_discarded_cells": hit_disc,
            "value_found_in_gate_rejected_or_fallback_table_text": bool(hit_fb),
            "fallback_table_ids": "|".join(hit_fb[:8]),
            "grounded_block_id": d.get("block_id") or "",
            "grounded_section": d.get("section") or "",
            "attribution": d.get("attribution") or "",
        })

    cfields = list(cl_rows[0].keys()) if cl_rows else []
    with (dest / "claim_ledger.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cfields)
        w.writeheader()
        w.writerows(cl_rows)

    entered = [r for r in cl_rows if r["entered_binder"]]
    check("claim ledger rows == 22", len(cl_rows), 22)
    check("entered binder == 14", len(entered), 14)
    check("papers with a claim in the binder == 8",
          len({r["paper_id"] for r in entered}), 8)
    check("bound == 0", sum(1 for r in cl_rows if r["binding_status"] == "bound"), 0)
    unknown = [r["claim_id"] for r in entered
               if r["terminal_reason_code"] in ("", "UNKNOWN", "UNATTRIBUTED", "NONE")]
    check("every entered claim has a named terminal_reason_code", len(unknown), 0)

    # ---- 2x2 over the 14 entered claims ---------------------------------
    grid22 = Counter()
    for r in entered:
        grid22[(r["value_found_in_attached_cells"],
                r["value_found_in_gate_rejected_or_fallback_table_text"])] += 1

    # ---- report ----------------------------------------------------------
    print("== assertions ==")
    failed = [x for x in A if not x["pass"]]
    for x in A:
        print(f"  [{'PASS' if x['pass'] else 'FAIL'}] {x['assertion']:58} "
              f"got={x['got']} expected={x['expected']}")
    if problems:
        print("\n== problems ==")
        for p in problems:
            print(f"  {p}")

    print(f"\n== table ledger ==  rows={n_rows} grid_returned={n_grid} no_grid={n_nogrid} "
          f"gate_rejected={n_gate_rej} post_gate_parse_loss={n_post_parse_loss} "
          f"cell={n_cell} fallback={n_fallback} attached_cells={n_attached}")
    disc_tot = Counter()
    for r in tl_rows:
        for k in ("empty_value", "empty_header", "value_equals_row_label",
                  "row_label_corner"):
            disc_tot[k] += r.get(f"discarded_{k}", r.get("row_label_corner_cells", 0)
                                 if k == "row_label_corner" else 0)
    print(f"  cells discarded at attach: empty_value={disc_tot['empty_value']} "
          f"empty_header={disc_tot['empty_header']} "
          f"value_equals_row_label={disc_tot['value_equals_row_label']} "
          f"(row-label corner cells, by design: {disc_tot['row_label_corner']})")
    print(f"  gate reason codes: "
          f"{dict(Counter(r['gate_reason_codes'] for r in tl_rows if r['gate_reason_codes']))}")
    print(f"  tables contributing to a RETURNED metric: {n_contrib} "
          f"(RETURNED metrics: {n_ret_metrics} total, "
          f"{n_ret_metrics_digit} of them containing a digit)")

    print(f"\n== claim ledger ==  rows={len(cl_rows)} entered={len(entered)} "
          f"papers_with_entry={len({r['paper_id'] for r in entered})} "
          f"bound={sum(1 for r in cl_rows if r['binding_status'] == 'bound')}")
    print(f"  terminal reason codes: {dict(Counter(r['terminal_reason_code'] for r in cl_rows))}")
    print(f"  binding statuses: {dict(Counter(r['binding_status'] for r in cl_rows))}")

    print("\n== 2x2 over the 14 claims that entered the binder ==")
    print(f"  {'':34}{'in fallback/rejected text':>28}{'not':>8}")
    for att in (True, False):
        lab = "value IS in attached cells" if att else "value NOT in attached cells"
        print(f"  {lab:34}{grid22[(att, True)]:>28}{grid22[(att, False)]:>8}")

    print(f"\n-> {dest / 'table_ledger.csv'}\n-> {dest / 'claim_ledger.csv'}")
    (dest / "ledger_assertions.json").write_text(
        json.dumps({"assertions": A, "problems": problems,
                    "two_by_two": {f"attached={k[0]},fallback_text={k[1]}": v
                                   for k, v in grid22.items()}}, indent=1),
        encoding="utf-8")
    if failed:
        print(f"\nSTOP: {len(failed)} assertion(s) failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
