"""STEP 3c — run the STEP 3b classifier on the positive-control fixtures.

    python diagnostics/funnel/classify_positive_control.py

STRUCT-1 is the expected METRIC_IN_DROPPED_HEADER_ROW case: its grid has two
header rows and represent_layout.py:96 keeps only the first, so the metric `f1`
survives only in the row that is discarded. If STRUCT-1 does NOT classify that
way, the classifier is suspect and the report must say so.

Read-only. Builds each fixture's table exactly as the real path does, by calling
represent_layout._attach on the fixture grid, then classifies with the same
functions classify_bindings.py uses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.evidence.anchors import NUMERIC_ANCHOR_RE            # noqa: E402
from src.evidence.gate import _metric_tokens, structural_bind  # noqa: E402
from src.evidence.represent_layout import _attach, _gate_grid, _norm  # noqa: E402

from classify_bindings import METRIC_IN_DROPPED_HEADER_ROW, classify  # noqa: E402

FIX = HERE / "positive_control" / "fixtures.json"
OUT = ROOT / "out" / "binding_breakdown"
PAPER = "FIXTURE"


def build_table(case):
    """The fixture's grid through the REAL attach path, shaped as the trace records it."""
    cap = case.get("caption", "")
    b = {"paper_id": PAPER, "block_id": f"{PAPER}:0", "block_type": "table",
         "section": "results", "source": "fixture", "representation": "pdf",
         "page_or_node": "p1", "text": cap, "char_start": 0, "char_end": len(cap)}
    _attach(b, case["grid"], "pymupdf4llm", PAPER, "fixture", "pymupdf4llm")
    g = _norm(case["grid"])
    gated = _gate_grid(g, False)
    cells = [{"row": c.get("row_label", ""), "col": c.get("column_header", ""),
              "value": str(c.get("value", "")), "caption": c.get("caption", ""),
              "cell_id": f"{PAPER}:0#r{c.get('row')}c{c.get('col')}",
              "table_id": f"{PAPER}:0"}
             for c in (b.get("table_cells") or [])]
    # classify() now locates candidates by position from gated_header/gated_rows,
    # so cells only need the label/header strings the trace records.
    for cell, src in zip(cells, b.get("table_cells") or []):
        cell["row_label"] = src.get("row_label", "")
        cell["col_header"] = src.get("column_header", "")
    return {"table_id": f"{PAPER}:0", "path": b.get("table_parse_status") == "parsed"
            and "cell_table" or "fallback",
            "gate_result": "rejected" if gated["reject"] else "passed",
            "raw_grid": [[str(x) for x in row] for row in g],
            "gated_header": gated["header"],
            "gated_rows": [[str(x) for x in row] for row in gated["rows"]],
            "block_text": cap, "caption": cap, "cells": cells}


def main() -> int:
    cases = json.loads(FIX.read_text(encoding="utf-8"))["cases"]
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    for case in cases:
        t = build_table(case)
        claim = case["claim"]
        mt = _metric_tokens(claim)
        nums = NUMERIC_ANCHOR_RE.findall(claim)
        sb = structural_bind(claim, [{"paper_id": PAPER, "block_type": "table",
                                      "section": "results", "table_cells":
                                          [{"value": c["value"],
                                            "column_header": c["col_header"],
                                            "row_label": c["row_label"],
                                            "caption": c["caption"],
                                            "section": "results",
                                            "row": c["row"], "col": c["col"],
                                            "spans": {}}
                                           for c in t["cells"]]}])
        rec = {"binding_status": sb.get("status"),
               "binding_candidate": sb.get("candidate")}
        why, ev = classify(rec, [t], mt, nums)
        out.append({"id": case["id"], "binding_status": sb.get("status"),
                    "extracted_metric": "|".join(sorted(mt)),
                    "sub_reason": why, "n_cells": len(t["cells"]),
                    "gated_header": t["gated_header"],
                    "evidence": ev})

    struct1 = next((r for r in out if r["id"] == "STRUCT-1"), None)
    ok = bool(struct1 and struct1["sub_reason"] == METRIC_IN_DROPPED_HEADER_ROW)
    payload = {"struct1_classified_as": struct1["sub_reason"] if struct1 else None,
               "struct1_expected": METRIC_IN_DROPPED_HEADER_ROW,
               "classifier_validated": ok, "cases": out}
    (OUT / "classifier_validation.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"{'case':10} {'bind status':18} {'metric':14} sub_reason")
    for r in out:
        print(f"{r['id']:10} {str(r['binding_status']):18} "
              f"{r['extracted_metric'][:14]:14} {r['sub_reason']}")
    print()
    print(f"STRUCT-1 -> {struct1['sub_reason'] if struct1 else 'MISSING'} "
          f"(expected {METRIC_IN_DROPPED_HEADER_ROW})")
    print("CLASSIFIER VALIDATED" if ok else
          "*** CLASSIFIER SUSPECT: STRUCT-1 did not classify as expected ***")
    print(f"-> {OUT / 'classifier_validation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
