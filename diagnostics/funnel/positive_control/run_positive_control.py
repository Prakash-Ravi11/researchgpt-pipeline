"""Positive control: does the binder bind a claim to a cell that IS its cell?

Two levels, neither of which modifies a pipeline function.

  L1  src.evidence.gate.structural_bind(claim, chunks), with cells built by
      src.evidence.schema.table_cell -- the binder's real input type -- and the
      quality gate bypassed entirely. Isolates the binder's contract.

  L2  the same table injected as a RAW GRID through
      src.evidence.represent_layout._attach (the real pre-registered quality
      gate + the real cell attachment), then src.evidence.chunker.chunk_document,
      then src.evidence.gate.gate_paper. This is the real downstream path,
      including the gates and the stage that takes 142 tables to 92.

      Injection point: _attach is what blocks_from_pdf_layout calls on each table
      block once its grid is in hand (represent_layout.py:356). Handing it a
      fixture grid is exactly "as if the parser had produced them", and needs no
      change to any pipeline function.

    python diagnostics/funnel/positive_control/run_positive_control.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIXTURES = HERE / "fixtures.json"
OUT = ROOT / "diagnostics" / "funnel" / "out" / "positive_control"

PAPER = "FIXTURE"


# ---- L1 -------------------------------------------------------------------

def l1_cells(case: dict) -> list[dict]:
    """Fixture -> the binder's real input type, via schema.table_cell.

    Derived from the grid by the same rule _layout_table_cells uses (row 0 is the
    header, column 0 is the row label, a cell needs a value and a header and must
    differ from its row label) but WITHOUT the quality gate -- that is what makes
    this L1 rather than L2.
    """
    from src.evidence.schema import table_cell

    cap = case.get("caption", "")
    if case.get("cells_override"):
        return [table_cell(value=c["value"], column_header=c["column_header"],
                           row_label=c["row_label"], caption=cap, section="results",
                           row=c.get("row", 1), col=c.get("col", 1))
                for c in case["cells_override"]]
    grid = case["grid"]
    header, out = grid[0], []
    for r_i, row in enumerate(grid[1:], start=1):
        label = row[0] if row else ""
        for col, val in enumerate(row):
            if col == 0:
                continue
            head = header[col] if col < len(header) else ""
            if val and head and val != label:
                out.append(table_cell(value=val, column_header=head, row_label=label,
                                      caption=cap, section="results", row=r_i, col=col))
    return out


def l1_chunks(cells: list[dict], case: dict) -> list[dict]:
    """One chunk carrying the cells, shaped as the chunker emits a table chunk."""
    return [{
        "paper_id": PAPER, "chunk_index": 0, "block_type": "table",
        "section": "results", "source": "fixture", "representation": "pdf_layout",
        "page_or_node": "p1", "block_id": f"{PAPER}:0",
        "text": case.get("caption", ""), "table_caption": case.get("caption", ""),
        "table_cells": cells,
    }]


def run_l1(case: dict) -> dict:
    from src.evidence.gate import structural_bind

    cells = l1_cells(case)
    sb = structural_bind(case["claim"], l1_chunks(cells, case))
    return {"status": sb.get("status"), "reason": sb.get("reason"),
            "cell": sb.get("cell"), "candidate": sb.get("candidate"),
            "n_cells_given": len(cells),
            "cells_given": [{"row": c["row_label"], "col": c["column_header"],
                             "value": c["value"]} for c in cells]}


# ---- L2 -------------------------------------------------------------------

def run_l2(case: dict) -> dict:
    """Fixture grid -> real _attach (quality gate) -> chunker -> gate_paper."""
    from src.evidence.represent_layout import _attach
    from src.evidence.chunker import chunk_document
    from src.evidence.gate import gate_paper

    cap = case.get("caption", "")
    block = {
        "paper_id": PAPER, "block_id": f"{PAPER}:0", "block_type": "table",
        "section": "results", "source": "fixture", "representation": "pdf",
        "page_or_node": "p1",
        "text": cap, "char_start": 0, "char_end": len(cap),
    }
    # the real attachment path: the pre-registered quality gate, the XHTML
    # round-trip and _layout_table_cells, exactly as blocks_from_pdf_layout
    # invokes it at represent_layout.py:356.
    _attach(block, case["grid"], "pymupdf4llm", PAPER, "fixture", "pymupdf4llm")

    prose = {
        "paper_id": PAPER, "block_id": f"{PAPER}:1", "block_type": "paragraph",
        "section": "results", "source": "fixture", "representation": "pdf",
        "page_or_node": "p1",
        "text": case["claim"], "char_start": 0, "char_end": len(case["claim"]),
    }
    chunks = chunk_document({"paper_id": PAPER, "representation": "pdf",
                             "blocks": [block, prose]})
    # gate_paper takes `results` as ONE text blob and splits it into sentences
    # (gate.py:603-610); a list is ignored entirely. Each sentence must be >= 12
    # chars and contain a digit to become an evidence item.
    gated = gate_paper({"paper_id": PAPER, "datasets": None, "metrics": None,
                        "results": case["claim"]}, chunks, "FULL_TEXT", ["Ours"])
    items = gated["evidence"]["results"]
    it = items[0] if items else {}
    sb = it.get("structural_binding") or {}
    stage, reason = _stage_of_death(block, it, sb)
    return {
        "table_parse_status": block.get("table_parse_status"),
        "table_fallback": block.get("table_fallback"),
        "n_cells_attached": len(block.get("table_cells") or []),
        "column_headers": block.get("column_headers") or [],
        "rows_before_gate": block.get("rows_before_gate"),
        "rows_after_gate": block.get("rows_after_gate"),
        "drop_reasons": block.get("drop_reasons") or {},
        "binding_status": sb.get("status"),
        "binding_reason": sb.get("reason"),
        "final": it.get("final"),
        "abstain_reason": it.get("abstain_reason"),
        "stage_of_death": stage, "reason_code": reason,
        "cells_attached": [{"row": c["row_label"], "col": c["column_header"],
                            "value": c["value"]}
                           for c in (block.get("table_cells") or [])],
    }


def _stage_of_death(block: dict, item: dict, sb: dict) -> tuple[str, str]:
    """The earliest stage at which this fixture stopped being bindable."""
    sys.path.insert(0, str(ROOT / "diagnostics" / "funnel"))
    from run_funnel import classify_fallback

    if block.get("table_parse_status") != "parsed":
        return "A3_cell_table", classify_fallback(block.get("table_fallback"))[0]
    if item.get("abstain_reason") == "value_failed_sanity_check":
        return "B1_claim", "VALUE_FAILED_SANITY_CHECK"
    if item.get("abstain_reason") == "metric_value_out_of_range":
        return "B1_claim", "METRIC_VALUE_OUT_OF_RANGE"
    if not sb:
        return "B2_enters_binder", "NO_NUMERIC_ANCHOR"
    if sb.get("status") == "bound":
        if item.get("final") == "RETURNED":
            return "none", "BOUND_AND_RETURNED"
        return "B5_result", str(item.get("abstain_reason") or "UNATTRIBUTED").upper()
    return "B4_binding", str(sb.get("status") or "UNATTRIBUTED").upper()


# ---- scoring ---------------------------------------------------------------

def score(case: dict, l1: dict, l2: dict) -> dict:
    exp = case["expected"]
    if exp == "RECORD_ONLY":
        return {"l1_pass": None, "l2_pass": None}
    want_bound = exp == "BIND"
    l1_bound = l1.get("status") == "bound"
    l2_bound = l2.get("binding_status") == "bound"
    ok_cell = True
    if want_bound and l1_bound and case.get("expected_cell"):
        c = l1.get("cell") or {}
        ok_cell = (c.get("row") == case["expected_cell"]["row_label"]
                   and c.get("col") == case["expected_cell"]["column_header"])
    return {"l1_pass": bool(l1_bound == want_bound and ok_cell),
            "l2_pass": bool(l2_bound == want_bound)}


def main() -> int:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        l1 = run_l1(case)
        try:
            l2 = run_l2(case)
        except Exception as e:
            l2 = {"error": f"{type(e).__name__}: {e}", "stage_of_death": "L2_ERROR",
                  "reason_code": "L2_ERROR"}
        rows.append({"id": case["id"], "category": case["category"],
                     "claim": case["claim"], "expected": case["expected"],
                     "expected_cell": case.get("expected_cell"),
                     "L1": l1, "L2": l2, **score(case, l1, l2)})

    scored = [r for r in rows if r["l1_pass"] is not None]
    summary = {
        "n_cases": len(rows),
        "n_scored": len(scored),
        "l1_pass": sum(1 for r in scored if r["l1_pass"]),
        "l2_pass": sum(1 for r in scored if r["l2_pass"]),
        "core_l1_pass": all(r["l1_pass"] for r in scored if r["category"].startswith("core")),
        "norm_l1_failures": [r["id"] for r in scored
                             if r["category"] == "normalization" and not r["l1_pass"]],
    }
    (OUT / "positive_control_results.json").write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=1, ensure_ascii=False),
        encoding="utf-8")

    print(f"{'case':10} {'exp':11} {'L1 status':18} {'L1':4} "
          f"{'L2 stage':20} {'L2 reason':28} {'L2':4}")
    for r in rows:
        p = lambda v: "-" if v is None else ("PASS" if v else "FAIL")   # noqa: E731
        print(f"{r['id']:10} {r['expected']:11} {str(r['L1']['status']):18} "
              f"{p(r['l1_pass']):4} {str(r['L2'].get('stage_of_death')):20} "
              f"{str(r['L2'].get('reason_code'))[:28]:28} {p(r['l2_pass']):4}")
    print(f"\nL1 {summary['l1_pass']}/{summary['n_scored']} · "
          f"L2 {summary['l2_pass']}/{summary['n_scored']} · "
          f"CORE L1 {'PASS' if summary['core_l1_pass'] else 'FAIL'}")
    print(f"-> {OUT / 'positive_control_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
