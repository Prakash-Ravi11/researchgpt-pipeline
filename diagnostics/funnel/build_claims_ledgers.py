"""Ledgers for the explicit-claim-extraction experiment.

    python diagnostics/funnel/build_claims_ledgers.py --out-root out --out claims_explicit

Read-only over the run's trace.jsonl and results.json. Writes claim_ledger.csv,
rejection_ledger.csv, binding_review.csv and buckets.json beside them.

Every value comparison uses the binder's own rule (`gate._has`, gate.py:459-465)
and its own claim-number regex (`anchors.NUMERIC_ANCHOR_RE`), so "value found"
means found the way the binder would find it.
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

from src.evidence.anchors import NUMERIC_ANCHOR_RE  # noqa: E402

SIGN_CHARS = "-−"
STRIP = re.compile(r"[^\d.\-]")


def has(n: str, s) -> bool:
    """gate._has, reproduced exactly."""
    s = str(s)
    if n == STRIP.sub("", s):
        return True
    return bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))


def sign_of(text: str) -> str:
    """"-", "+", or "" for unsigned. Empty input is unsigned, not negative:
    `"" in SIGN_CHARS` is True for the empty string, so the guard is required."""
    t = str(text).strip()
    if not t:
        return ""
    if t[0] in SIGN_CHARS:
        return "-"
    if t[0] == "+":
        return "+"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=str(HERE / "out"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out_root) / a.out
    # split("\n"), not splitlines(): splitlines() also breaks on U+2028/U+2029/
    # U+0085, which json.dumps leaves unescaped inside string values.
    raw = (out / "trace.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(x) for x in raw.split("\n") if x.strip()]
    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    papers, res = payload["papers"], payload["results"]

    attach = {r["item_id"]: r for r in rows if r["stage"] == "A0_attach_detail"}
    items = [r for r in rows if r["stage"] == "B0_evidence_item"]
    pageidx: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r["stage"] == "A_page_index":
            d = r["detail"] or {}
            pageidx[(r["paper_id"], str(d.get("page")))] = d

    # explicit extractor records, joined to gate items by the sentence string
    ex_by_sentence: dict[tuple[str, str], dict] = {}
    rejections: list[dict] = []
    for pid in papers:
        for c in (res[pid].get("explicit_claims") or []):
            ex_by_sentence[(pid, c["sentence"])] = c
        for r in (res[pid].get("explicit_rejections") or []):
            rejections.append(r)

    # per-paper table facts
    per_paper = defaultdict(lambda: {"cell_tables": 0, "attached": [], "discarded": [],
                                     "fallback_text": []})
    for tid, a0 in attach.items():
        d = a0["detail"] or {}
        P = per_paper[a0["paper_id"]]
        if d.get("extraction_path") == "cell_table":
            P["cell_tables"] += 1
            ids, vals = d.get("attached_cell_ids") or [], d.get("attached_values") or []
            P["attached"] += (list(zip(ids, vals)) if len(ids) == len(vals)
                              else [(tid + "#?", v) for v in vals])
            P["discarded"] += [(tid, v) for v in (d.get("discarded_values") or [])]
        else:
            P["fallback_text"].append((tid, d.get("block_text") or ""))

    cl, review = [], []
    for r in items:
        d = r["detail"] or {}
        if d.get("field") not in ("metrics", "results"):
            continue
        text = d.get("value") or ""
        if not re.search(r"\d", text):
            continue
        pid = r["paper_id"]
        nums = NUMERIC_ANCHOR_RE.findall(text)
        status = d.get("binding_status")
        entered = status is not None
        P = per_paper[pid]
        ex = ex_by_sentence.get((pid, text), {})
        page = str(ex.get("page") or "")

        hit_cells = [cid for cid, v in P["attached"] if any(has(n, v) for n in nums)]
        hit_disc = any(any(has(n, v) for n in nums) for _t, v in P["discarded"])
        hit_fb = [t for t, txt in P["fallback_text"] if any(has(n, txt) for n in nums)]

        # (e) value in the page's text layer OUTSIDE every detected table block
        pg = pageidx.get((pid, page)) or {}
        page_text = pg.get("non_table_text") or ""
        on_page = bool(page_text) and any(has(n, page_text) for n in nums)

        # (f) heuristic triage for values in no table block at all
        in_any_table = bool(hit_cells) or hit_disc or bool(hit_fb)
        if in_any_table:
            triage = ""
        else:
            labels = pg.get("table_labels_in_prose") or []
            n_tb = int(pg.get("n_table_blocks") or 0)
            triage = ("TABLE_POSSIBLY_UNDETECTED"
                      if labels and len(set(labels)) > n_tb else "PROSE_ONLY")

        cl.append({
            "paper_id": pid, "claim_id": ex.get("claim_id", r["item_id"]),
            "field": d.get("field"), "claim_text": text,
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
            "value_on_page_text": on_page,
            "triage": triage,
            "rule_id": ex.get("rule_id", "LEGACY_CACHE"),
            "section": ex.get("section") or d.get("section") or "",
            "page": page,
            "grounded_block_id": d.get("block_id") or "",
            "grounded_section": d.get("section") or "",
            "attribution": d.get("attribution") or "",
        })

        # binding_review: one row per binding that produced a cell
        cell = d.get("binding_cell") or d.get("binding_candidate")
        if status in ("bound", "wrong_cell") and cell:
            cv = str(cell.get("value") or "")
            nspan = next((n for n in nums if has(n, cv)), nums[0] if nums else "")
            review.append({
                "paper_id": pid, "claim_id": ex.get("claim_id", r["item_id"]),
                "binding_status": status,
                "claim_sentence": text,
                "numeric_span": nspan,
                "bound_cell_value": cv,
                "row_header": cell.get("row") or "",
                "column_header_path": f"{cell.get('caption') or ''} > {cell.get('col') or ''}",
                "table_caption": cell.get("caption") or "",
                "page": page,
                # gate.py's wrong_cell candidate (gate.py:476-487) carries only
                # row and col, never the cell's value, so there is nothing to
                # compare a sign against. Reported as n/a rather than as a
                # mismatch. See "Found, not fixed".
                "sign_match": ("" if not cv else sign_of(nspan) == sign_of(cv)),
                "human_label": "",
            })

    def write(name, data):
        p = out / name
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0].keys()) if data else ["empty"])
            w.writeheader()
            w.writerows(data)
        return p

    write("claim_ledger.csv", cl)
    write("binding_review.csv", review)
    rej_rows = [{"paper_id": r["paper_id"], "claim_id": r["claim_id"],
                 "section": r.get("section") or "", "block_type": r.get("block_type") or "",
                 "page": r.get("page") or "", "char_span": json.dumps(r.get("char_span")),
                 "reason_code": r["reason_code"], "sentence": r.get("sentence", "")[:300]}
                for r in rejections]
    write("rejection_ledger.csv", rej_rows)
    rej_totals = Counter(r["reason_code"] for r in rejections)

    entered = [r for r in cl if r["entered_binder"]]
    nobind = [r for r in entered if r["binding_status"] != "bound"]
    B_BIND = [r for r in nobind if r["value_found_in_attached_cells"]]
    B_TABLE = [r for r in nobind if not r["value_found_in_attached_cells"]
               and r["value_found_in_gate_rejected_or_fallback_table_text"]]
    B_UNDETECTED = [r for r in nobind if r["triage"] == "TABLE_POSSIBLY_UNDETECTED"]
    B_PROSE = [r for r in nobind if r["triage"] == "PROSE_ONLY"]
    buckets = {
        "B-BIND": len(B_BIND),
        "B-BIND_by_terminal_reason": dict(Counter(r["terminal_reason_code"] for r in B_BIND)),
        "B-TABLE": len(B_TABLE),
        "B-UNDETECTED": len(B_UNDETECTED),
        "B-PROSE": len(B_PROSE),
        "claims_total": len(cl),
        "entered_binder": len(entered),
        "bound": sum(1 for r in cl if r["binding_status"] == "bound"),
        "papers_with_claim_entering_binder": len({r["paper_id"] for r in entered}),
        "papers_total": len(papers),
        "bindings_reviewed": len(review),
        "bindings_with_a_comparable_cell_value": sum(1 for r in review
                                                     if r["sign_match"] != ""),
        "bindings_sign_mismatch": sum(1 for r in review if r["sign_match"] is False),
        "bindings_sign_not_assessable": sum(1 for r in review if r["sign_match"] == ""),
        "rejection_totals": dict(rej_totals),
        "rejections_total": len(rejections),
        "returned_metrics": sum(1 for r in cl if r["field"] == "metrics"
                                and r["terminal_state"] == "RETURNED"),
        "returned_results": sum(1 for r in cl if r["field"] == "results"
                                and r["terminal_state"] == "RETURNED"),
        "binding_status_counts": dict(Counter(r["binding_status"] for r in cl)),
        "terminal_reason_counts": dict(Counter(r["terminal_reason_code"] for r in cl)),
    }
    largest = max(("B-BIND", len(B_BIND)), ("B-TABLE", len(B_TABLE)),
                  ("B-UNDETECTED", len(B_UNDETECTED)), ("B-PROSE", len(B_PROSE)),
                  key=lambda kv: kv[1])
    MAP = {"B-TABLE": "gates switched to flag-only",
           "B-UNDETECTED": "table detection (corpus audit + oracle R1)",
           "B-PROSE": "claim classification"}
    if largest[0] == "B-BIND":
        top = Counter(r["terminal_reason_code"] for r in B_BIND).most_common(1)
        mapped = f"its top terminal_reason_code: {top[0][0] if top else 'n/a'}"
    else:
        mapped = MAP[largest[0]]
    buckets["largest_bucket"] = largest[0]
    buckets["largest_bucket_n"] = largest[1]
    buckets["mapped_next_change"] = mapped
    (out / "buckets.json").write_text(json.dumps(buckets, indent=1), encoding="utf-8")

    print(f"== {a.out} ==")
    print(f"  claims={buckets['claims_total']} entered={buckets['entered_binder']} "
          f"bound={buckets['bound']} papers_with_entry="
          f"{buckets['papers_with_claim_entering_binder']}/{buckets['papers_total']}")
    print(f"  returned: metrics={buckets['returned_metrics']} "
          f"results={buckets['returned_results']}")
    print(f"  binding statuses: {buckets['binding_status_counts']}")
    print(f"  rejections={buckets['rejections_total']} {buckets['rejection_totals']}")
    print(f"  buckets: B-BIND={buckets['B-BIND']} {buckets['B-BIND_by_terminal_reason']} "
          f"B-TABLE={buckets['B-TABLE']} B-UNDETECTED={buckets['B-UNDETECTED']} "
          f"B-PROSE={buckets['B-PROSE']}")
    print(f"  bindings reviewed={buckets['bindings_reviewed']} "
          f"(comparable cell value: {buckets['bindings_with_a_comparable_cell_value']}, "
          f"not assessable: {buckets['bindings_sign_not_assessable']}) "
          f"sign_mismatch={buckets['bindings_sign_mismatch']}")
    print(f"  LARGEST: {largest[0]} (n={largest[1]}) -> {mapped}")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
