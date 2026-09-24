"""Why B-BIND and B-TABLE claims do not bind. Read-only.

    python diagnostics/funnel/classify_bindings.py --out-root out --out binding_breakdown

Reads the run's trace.jsonl and results.json. Alters no pipeline decision: it
re-runs the binder's OWN metric extraction (gate._metric_tokens) and OWN matcher
(gate._col_matches_metric) over cells the run already produced, and classifies.

Sub-reasons are assigned in the fixed order given in the brief; the FIRST match
wins, so the counts partition the population exactly once.
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

from src.evidence.anchors import NUMERIC_ANCHOR_RE           # noqa: E402
from src.evidence.gate import _col_matches_metric, _metric_tokens  # noqa: E402

STRIP = re.compile(r"[^\d.\-]")
PUNCT = re.compile(r"[^a-z0-9 ]+")
WS = re.compile(r"\s+")

# sub-reason codes, in the order the brief fixes
NO_METRIC_IN_CLAIM = "NO_METRIC_IN_CLAIM"
METRIC_IN_DROPPED_HEADER_ROW = "METRIC_IN_DROPPED_HEADER_ROW"
METRIC_IN_ROW_HEADER = "METRIC_IN_ROW_HEADER"
METRIC_NEAR_MATCH = "METRIC_NEAR_MATCH"
WRONG_CELL = "WRONG_CELL"
METRIC_ABSENT = "METRIC_ABSENT"
OTHER = "OTHER"
ORDER = [NO_METRIC_IN_CLAIM, METRIC_IN_DROPPED_HEADER_ROW, METRIC_IN_ROW_HEADER,
         METRIC_NEAR_MATCH, WRONG_CELL, METRIC_ABSENT, OTHER]


def has(n: str, s) -> bool:
    """gate._has, reproduced exactly (gate.py:459-465)."""
    s = str(s)
    if n == STRIP.sub("", s):
        return True
    return bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))


def norm_header(s: str) -> str:
    """lowercase, drop '(%)' and punctuation, collapse whitespace."""
    t = str(s or "").lower().replace("(%)", " ").replace("%", " ")
    return WS.sub(" ", PUNCT.sub(" ", t)).strip()


def lev(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near(metric_toks: set[str], header: str) -> bool:
    """Token-set equality or edit distance <= 2 on the normalised header."""
    h = norm_header(header)
    if not h or not metric_toks:
        return False
    hset = set(h.split())
    for m in metric_toks:
        if m in hset:
            return True
        for tok in hset:
            if lev(m, tok) <= 2:
                return True
        if lev(m, h) <= 2:
            return True
    return False


def load(out: Path):
    raw = (out / "trace.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(x) for x in raw.split("\n") if x.strip()]
    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return rows, payload


def build_tables(rows):
    """paper_id -> list of per-table records with raw grid + attached cells."""
    per = defaultdict(list)
    for r in rows:
        if r["stage"] != "A0_attach_detail":
            continue
        d = r["detail"] or {}
        ids = d.get("attached_cell_ids") or []
        inv = d.get("attached_cells") or []
        cells = []
        for i, c in enumerate(inv):
            cells.append({**c, "cell_id": ids[i] if i < len(ids) else f"{r['item_id']}#{i}",
                          "table_id": r["item_id"]})
        per[r["paper_id"]].append({
            "table_id": r["item_id"],
            "path": d.get("extraction_path"),
            "gate_result": d.get("gate_result"),
            "raw_grid": d.get("raw_grid") or [],
            "gated_header": d.get("gated_header") or d.get("header") or [],
            "gated_rows": d.get("gated_rows") or [],
            "block_text": d.get("block_text") or "",
            "caption": d.get("caption") or "",
            "cells": cells,
        })
    return per


def sq(x):
    return " ".join(str(x or "").split())


def candidate_positions(tables, nums):
    """Attached cells whose value matches a claim value, as grid POSITIONS.

    A position (i, c) in the gated grid is an attached cell exactly when
    represent_layout.py:110 would have kept it: c > 0, the value is non-empty, the
    column header is non-empty, and the value differs from the row label. That
    condition is replayed here rather than assumed.
    """
    out = []
    for t in tables:
        if t["path"] != "cell_table":
            continue
        hdr = t["gated_header"] or []
        for i, row in enumerate(t["gated_rows"] or []):
            lbl = sq(row[0]) if row else ""
            for c in range(1, len(row)):
                val, head = sq(row[c]), sq(hdr[c]) if c < len(hdr) else ""
                if not val or not head or val == lbl:
                    continue                      # not an attached cell
                if any(has(n, val) for n in nums):
                    out.append({"table": t, "row_i": i, "col": c, "value": val,
                                "row_label": lbl, "col_header": head})
    return out


def rows_above(t, row_i, col):
    """Text at `col` in the gated rows ABOVE row_i -- i.e. rows that
    represent_layout.py:96 did not treat as the header (only row 0 becomes one)."""
    out = []
    for i, row in enumerate((t["gated_rows"] or [])[:row_i]):
        if col < len(row):
            txt = sq(row[col])
            if txt:
                cells = [x for x in row if sq(x)]
                nonnum = [x for x in cells if not re.search(r"\d", str(x))]
                out.append({"grid_row": i, "text": txt,
                            "row_is_header_like": len(nonnum) * 2 >= len(cells)})
    return out


def classify(claim, tables, mt, nums):
    """(sub_reason, evidence). First match in ORDER wins."""
    ev = {}
    if not mt:
        return NO_METRIC_IN_CLAIM, {"note": "gate._metric_tokens(claim) is empty"}

    cands = candidate_positions(tables, nums)
    ev["n_candidate_cells"] = len(cands)
    ev["candidates"] = [{"table_id": k["table"]["table_id"], "value": k["value"],
                         "row_label": k["row_label"], "col_header": k["col_header"],
                         "header_stack": [k["col_header"]]
                         + [a["text"] for a in rows_above(k["table"], k["row_i"], k["col"])]}
                        for k in cands[:3]]

    # 2 — metric in a header row that represent_layout.py:96 discarded
    d_hits = []
    for k in cands:
        for a in rows_above(k["table"], k["row_i"], k["col"]):
            # the binder's OWN matcher only. near() belongs to rule 4; using it
            # here made `mrr` match `min` and fired on data rows.
            if _col_matches_metric(a["text"], mt):
                d_hits.append({"table_id": k["table"]["table_id"],
                               "cell_value": k["value"],
                               "kept_col_header": k["col_header"], **a})
    if d_hits:
        return METRIC_IN_DROPPED_HEADER_ROW, {**ev, "hits": d_hits[:6]}

    # 3 — metric matches the candidate's row label / stub
    r_hits = [{"table_id": k["table"]["table_id"], "cell_value": k["value"],
               "row_label": k["row_label"]}
              for k in cands
              if k["row_label"] and _col_matches_metric(k["row_label"], mt)]
    if r_hits:
        return METRIC_IN_ROW_HEADER, {**ev, "hits": r_hits[:6]}

    # 4 — near match against any header level of a candidate cell
    n_hits = []
    for k in cands:
        levels = [k["col_header"]] + [a["text"] for a in
                                      rows_above(k["table"], k["row_i"], k["col"])]
        for h in levels:
            if h and not _col_matches_metric(h, mt) and near(mt, h):
                n_hits.append({"claim_metric": "|".join(sorted(mt)), "header_text": h,
                               "table_id": k["table"]["table_id"],
                               "cell_value": k["value"]})
    if n_hits:
        return METRIC_NEAR_MATCH, {**ev, "pairs": n_hits[:10]}

    # 5 — the binding stage chose a cell and marked it wrong
    if claim.get("binding_status") == "wrong_cell":
        cand = claim.get("binding_candidate") or {}
        col = cand.get("col") or ""
        return WRONG_CELL, {**ev, "chosen_row": cand.get("row"), "chosen_col": col,
                            "metric_matched_chosen_header": bool(
                                col and _col_matches_metric(col, mt))}

    # 6 — metric matches nothing anywhere in this paper's tables
    anywhere = False
    for t in tables:
        for row in (t["raw_grid"] or []):
            if any(sq(x) and (_col_matches_metric(sq(x), mt) or near(mt, sq(x)))
                   for x in row):
                anywhere = True
                break
        if anywhere:
            break
        for c in t["cells"]:
            if (_col_matches_metric(sq(c.get("col")), mt)
                    or near(mt, sq(c.get("col")))
                    or _col_matches_metric(sq(c.get("row")), mt)):
                anywhere = True
                break
        if anywhere:
            break
    if not anywhere:
        return METRIC_ABSENT, {**ev, "note": "metric matches no header, row label or "
                                             "raw grid cell in this paper"}
    return OTHER, {**ev, "note": "metric appears somewhere in the paper but not at or "
                                 "above any candidate cell"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=str(HERE / "out"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out_root) / a.out
    rows, payload = load(out)
    papers, res = payload["papers"], payload["results"]
    tables_by_paper = build_tables(rows)

    items = [r for r in rows if r["stage"] == "B0_evidence_item"]
    ex_by_sentence = {}
    for pid in papers:
        for c in (res[pid].get("explicit_claims") or []):
            ex_by_sentence[(pid, c["sentence"])] = c

    # rebuild the bucket assignment exactly as build_ownership_ledgers does
    P = defaultdict(lambda: {"cell_tables": 0, "attached": [], "discarded": [],
                             "fallback": []})
    pageidx = {(r["paper_id"], str((r["detail"] or {}).get("page"))): (r["detail"] or {})
               for r in rows if r["stage"] == "A_page_index"}
    for pid, ts in tables_by_paper.items():
        for t in ts:
            if t["path"] == "cell_table":
                P[pid]["cell_tables"] += 1
                P[pid]["attached"] += [(c["cell_id"], c["value"]) for c in t["cells"]]
            else:
                P[pid]["fallback"].append(t)
    for r in rows:
        if r["stage"] == "A0_attach_detail":
            d = r["detail"] or {}
            if d.get("extraction_path") == "cell_table":
                P[r["paper_id"]]["discarded"] += [(r["item_id"], v)
                                                  for v in (d.get("discarded_values") or [])]

    bbind, btable, all_claims = [], [], []
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
        p = P[pid]
        hit_cells = [cid for cid, v in p["attached"] if any(has(n, v) for n in nums)]
        hit_disc = any(any(has(n, v) for n in nums) for _t, v in p["discarded"])
        hit_fb = [t for t in p["fallback"]
                  if any(has(n, t["block_text"]) for n in nums)]
        ex = ex_by_sentence.get((pid, text), {})
        pg = pageidx.get((pid, str(ex.get("page") or ""))) or {}
        if hit_cells or hit_disc or hit_fb:
            triage = ""
        else:
            labels = pg.get("table_labels_in_prose") or []
            triage = ("TABLE_POSSIBLY_UNDETECTED"
                      if labels and len(set(labels)) > int(pg.get("n_table_blocks") or 0)
                      else "PROSE_ONLY")
        rec = {"paper_id": pid, "claim_text": text, "nums": nums,
               "binding_status": status, "entered": status is not None,
               "terminal_reason": r["reason_code"],
               "binding_candidate": d.get("binding_candidate"),
               "binding_cell": d.get("binding_cell"),
               "abstain_reason": d.get("abstain_reason"),
               "hit_cells": hit_cells, "hit_fb": hit_fb}
        all_claims.append(rec)
        if status is None or status == "bound":
            continue
        if hit_cells:
            bbind.append(rec)
        elif hit_fb:
            btable.append(rec)

    # ---- 3a binding-stage outcome -------------------------------------
    def stage_outcome(rec):
        s = rec["binding_status"]
        if s == "no_binding_call":
            return "skipped:NO_NUMERIC_ANCHOR (gate.py:525)"
        if s in ("not_bindable", "wrong_cell", "pdf_only", "not_a_table_claim",
                 "no_number"):
            return s
        return f"other:{s}"

    outcomes = Counter(stage_outcome(r) for r in bbind)

    # ---- 3b sub-reasons ------------------------------------------------
    sub_rows, subs = [], Counter()
    for rec in bbind:
        mt = _metric_tokens(rec["claim_text"])
        tabs = tables_by_paper.get(rec["paper_id"], [])
        why, ev = classify(rec, tabs, mt, rec["nums"])
        subs[why] += 1
        occ = sum(1 for _cid, v in P[rec["paper_id"]]["attached"]
                  if any(has(n, v) for n in rec["nums"]))
        sub_rows.append({
            "paper_id": rec["paper_id"], "sub_reason": why,
            "binding_stage_outcome": stage_outcome(rec),
            "terminal_reason": rec["terminal_reason"],
            "claim_text": rec["claim_text"][:400],
            "extracted_metric": "|".join(sorted(mt)),
            "numeric_values": "|".join(rec["nums"]),
            "value_occurrences_in_paper": occ,
            "evidence": json.dumps(ev, ensure_ascii=False),
        })

    # ---- STEP 4 B-TABLE -------------------------------------------------
    bt_rows, bt_match = [], 0
    for rec in btable:
        mt = _metric_tokens(rec["claim_text"])
        matched, where = False, []
        for t in rec["hit_fb"]:
            heads = [x for row in (t["raw_grid"] or [])[:3] for x in row]
            stubs = [row[0] for row in (t["raw_grid"] or []) if row]
            for h in heads + stubs:
                if h and (_col_matches_metric(h, mt) or near(mt, h)):
                    matched = True
                    where.append({"table_id": t["table_id"], "text": h,
                                  "gate_result": t["gate_result"]})
            if not t["raw_grid"]:
                for line in (t["block_text"] or "").splitlines()[:6]:
                    if line and (_col_matches_metric(line, mt) or near(mt, line)):
                        matched = True
                        where.append({"table_id": t["table_id"], "text": line[:120],
                                      "gate_result": "no_grid(text only)"})
        bt_match += bool(matched)
        bt_rows.append({"paper_id": rec["paper_id"],
                        "matchable": matched,
                        "claim_text": rec["claim_text"][:300],
                        "extracted_metric": "|".join(sorted(mt)),
                        "numeric_values": "|".join(rec["nums"]),
                        "where": json.dumps(where[:4], ensure_ascii=False)[:600]})

    def write(name, data):
        with (out / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0].keys()) if data else ["empty"])
            w.writeheader()
            w.writerows(data)

    write("bbind_subreasons.csv", sub_rows)
    write("btable_check.csv", bt_rows)

    occ_by_sub = defaultdict(Counter)
    for r in sub_rows:
        occ_by_sub[r["sub_reason"]][r["value_occurrences_in_paper"]] += 1

    R = {"R1": subs[METRIC_IN_DROPPED_HEADER_ROW], "R2": subs[METRIC_IN_ROW_HEADER],
         "R3": subs[METRIC_NEAR_MATCH], "R4": subs[WRONG_CELL], "R5": bt_match}
    excluded = {"NO_METRIC_IN_CLAIM": subs[NO_METRIC_IN_CLAIM],
                "METRIC_ABSENT": subs[METRIC_ABSENT], "OTHER": subs[OTHER]}
    nxt = max(R.items(), key=lambda kv: kv[1])
    summary = {
        "b_bind_total": len(bbind), "b_table_total": len(btable),
        "binding_stage_outcomes": dict(outcomes),
        "outcomes_sum": sum(outcomes.values()),
        "sub_reasons": {k: subs[k] for k in ORDER if subs[k]},
        "sub_reasons_sum": sum(subs.values()),
        "reconciles": sum(outcomes.values()) == len(bbind) == sum(subs.values()),
        "R1_R5": R, "excluded": excluded,
        "B_TABLE_MATCHABLE": bt_match,
        "named_next_change": nxt[0], "named_next_change_n": nxt[1],
        "value_occurrences_by_sub_reason": {k: dict(v) for k, v in occ_by_sub.items()},
    }
    (out / "binding_breakdown.json").write_text(json.dumps(summary, indent=1),
                                                encoding="utf-8")

    print(f"== {a.out} ==")
    print(f"  B-BIND={len(bbind)}  B-TABLE={len(btable)}")
    print("  binding-stage outcomes:")
    for k, v in outcomes.most_common():
        print(f"    {k:44} {v:>5}")
    print(f"    {'SUM':44} {sum(outcomes.values()):>5} "
          f"{'PASS' if sum(outcomes.values()) == len(bbind) else '*** FAIL ***'}")
    print("  sub-reasons:")
    for k in ORDER:
        if subs[k]:
            print(f"    {k:44} {subs[k]:>5}")
    print(f"    {'SUM':44} {sum(subs.values()):>5} "
          f"{'PASS' if sum(subs.values()) == len(bbind) else '*** FAIL ***'}")
    print(f"  R1-R5: {R}")
    print(f"  excluded: {excluded}")
    print(f"  B-TABLE-MATCHABLE: {bt_match} of {len(btable)}")
    print(f"  NAMED NEXT CHANGE: {nxt[0]} (n={nxt[1]})")
    print(f"  -> {out}")
    return 0 if summary["reconciles"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
