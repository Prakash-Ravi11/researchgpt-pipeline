"""Ledgers for the ownership_policy experiment (block vs warn).

    python diagnostics/funnel/build_ownership_ledgers.py --out-root out --out ownership_warn

Read-only over the run's trace.jsonl and results.json. Writes claim_ledger.csv,
rejection_ledger.csv, binding_review.csv, buckets.json, and for the warn arm
labeling_sample.csv + labeling_reserve.csv.

Adds over build_claims_ledgers.py:
  * B-NONE, so every entered-and-unbound claim gets exactly one bucket, each with
    a reason code, and the buckets are asserted to sum to (entered - bound);
  * wrong_cell resolution -- the gate records only (row, col) for a wrong_cell
    verdict, never the cell's value (defect F-3), so the chosen cell is looked up
    in the paper's attached-cell inventory to recover its id and value;
  * the STEP 2 binding_review columns.

Every value comparison uses the binder's own rule (gate._has, gate.py:459-465).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
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
SEED = 20260924
SAMPLE_N, RESERVE_N = 60, 40

# F-1: a block whose section label or sentence reads as a bibliography line.
F1_RE = re.compile(r"arxiv\.org|url http|doi\.org|pages?\s+\d+|proceedings|"
                   r"conference on|in emnlp|in acl|in sigir", re.I)
TABLE_LABEL_RE = re.compile(r"\b(?:table|tab\.)\s*([IVXLC]+|\d+)", re.I)


def has(n: str, s) -> bool:
    s = str(s)
    if n == STRIP.sub("", s):
        return True
    return bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))


def sign_of(text: str) -> str:
    t = str(text).strip()
    if not t:
        return ""
    if t[0] in SIGN_CHARS:
        return "-"
    return "+" if t[0] == "+" else ""


def table_label(text: str) -> str:
    m = TABLE_LABEL_RE.search(text or "")
    return f"Table {m.group(1)}" if m else ""


def norm_label(lbl: str) -> str:
    m = TABLE_LABEL_RE.search(lbl or "")
    return (m.group(1) or "").upper() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=str(HERE / "out"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out_root) / a.out
    raw = (out / "trace.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(x) for x in raw.split("\n") if x.strip()]
    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    papers, res = payload["papers"], payload["results"]

    attach = {r["item_id"]: r for r in rows if r["stage"] == "A0_attach_detail"}
    items = [r for r in rows if r["stage"] == "B0_evidence_item"]
    pageidx = {(r["paper_id"], str((r["detail"] or {}).get("page"))): (r["detail"] or {})
               for r in rows if r["stage"] == "A_page_index"}

    ex_by_sentence, rejections = {}, []
    for pid in papers:
        for c in (res[pid].get("explicit_claims") or []):
            ex_by_sentence[(pid, c["sentence"])] = c
        rejections += (res[pid].get("explicit_rejections") or [])

    # per-paper table facts, including the full attached-cell inventory
    P = defaultdict(lambda: {"cell_tables": 0, "attached": [], "discarded": [],
                             "fallback_text": [], "cells": []})
    for tid, a0 in attach.items():
        d = a0["detail"] or {}
        p = P[a0["paper_id"]]
        if d.get("extraction_path") == "cell_table":
            p["cell_tables"] += 1
            ids, vals = d.get("attached_cell_ids") or [], d.get("attached_values") or []
            p["attached"] += (list(zip(ids, vals)) if len(ids) == len(vals)
                              else [(tid + "#?", v) for v in vals])
            inv = d.get("attached_cells") or []
            for i, c in enumerate(inv):
                p["cells"].append({**c, "cell_id": ids[i] if i < len(ids) else f"{tid}#{i}",
                                   "table_id": tid})
            p["discarded"] += [(tid, v) for v in (d.get("discarded_values") or [])]
        else:
            p["fallback_text"].append((tid, d.get("block_text") or ""))

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
        p = P[pid]
        ex = ex_by_sentence.get((pid, text), {})
        page = str(ex.get("page") or "")
        oflag = d.get("ownership_flag") or ""

        hit_cells = [cid for cid, v in p["attached"] if any(has(n, v) for n in nums)]
        hit_disc = any(any(has(n, v) for n in nums) for _t, v in p["discarded"])
        hit_fb = [t for t, txt in p["fallback_text"] if any(has(n, txt) for n in nums)]

        pg = pageidx.get((pid, page)) or {}
        page_text = pg.get("non_table_text") or ""
        on_page = bool(page_text) and any(has(n, page_text) for n in nums)

        in_any_table = bool(hit_cells) or hit_disc or bool(hit_fb)
        if in_any_table:
            triage = ""
        else:
            labels = pg.get("table_labels_in_prose") or []
            n_tb = int(pg.get("n_table_blocks") or 0)
            triage = ("TABLE_POSSIBLY_UNDETECTED"
                      if labels and len(set(labels)) > n_tb else "PROSE_ONLY")

        f1 = bool(F1_RE.search(ex.get("section") or "") or F1_RE.search(text))

        cl.append({
            "paper_id": pid, "claim_id": ex.get("claim_id", r["item_id"]),
            "field": d.get("field"), "claim_text": text,
            "numeric_values_raw": "|".join(nums),
            "numeric_values_normalized": "|".join(nums),
            "entered_binder": entered,
            "binding_status": status or "no_binding_call",
            "terminal_state": d.get("final") or "ABSTAINED",
            "terminal_reason_code": r["reason_code"],
            "ownership_flag": oflag,
            "paper_has_post_gate_cell_table": p["cell_tables"] > 0,
            "value_found_in_attached_cells": bool(hit_cells),
            "attached_cell_ids": "|".join(hit_cells[:8]),
            "value_found_in_discarded_cells": hit_disc,
            "value_found_in_gate_rejected_or_fallback_table_text": bool(hit_fb),
            "fallback_table_ids": "|".join(hit_fb[:8]),
            "value_on_page_text": on_page,
            "triage": triage,
            "f1_bibliography_heuristic": f1,
            "rule_id": ex.get("rule_id", "LEGACY_CACHE"),
            "section": ex.get("section") or d.get("section") or "",
            "page": page,
            "grounded_block_id": d.get("block_id") or "",
            "attribution": d.get("attribution") or "",
        })

        cell = d.get("binding_cell") or d.get("binding_candidate")
        if status in ("bound", "wrong_cell") and cell:
            cv = str(cell.get("value") or "")
            crow, ccol = cell.get("row") or "", cell.get("col") or ""
            # wrong_cell gives only (row, col): resolve it to a real cell
            chosen_id, chosen_cap = "", cell.get("caption") or ""
            if not cv or not chosen_cap:
                for c in p["cells"]:
                    if c["row"] == crow and c["col"] == ccol:
                        chosen_id = c["cell_id"]
                        cv = cv or c["value"]
                        chosen_cap = chosen_cap or c["caption"]
                        break
            nspan = next((n for n in nums if has(n, cv)), nums[0] if nums else "")
            matching = [c for c in p["cells"] if nspan and has(nspan, c["value"])]
            occurrences = len(matching)
            cmention = "|".join(ex.get("table_mentions_raw") or [])
            blabel = table_label(chosen_cap)
            if not cmention:
                agree = "no_mention"
            else:
                want = {norm_label(m) for m in (ex.get("table_mentions_raw") or [])}
                agree = "true" if norm_label(blabel) in want and blabel else "false"
            review.append({
                "paper_id": pid, "claim_id": ex.get("claim_id", r["item_id"]),
                "binding_status": status,
                "claim_sentence": text,
                "numeric_span": nspan,
                "chosen_cell_id": chosen_id,
                "bound_cell_value": cv,
                "row_header": crow,
                "column_header_path": f"{chosen_cap} > {ccol}",
                "table_caption": chosen_cap,
                "page": page,
                "value_matching_cells": "|".join(
                    f"{c['cell_id']}={c['value']}@{c['row']}/{c['col']}" for c in matching[:6]),
                "value_occurrences_in_paper": occurrences,
                "claim_table_mention": cmention,
                "bound_table_label": blabel,
                "mention_matches_bound_table": agree,
                "ownership_flag": oflag,
                "f1_bibliography_heuristic": f1,
                "sign_match": ("" if not cv else sign_of(nspan) == sign_of(cv)),
                "human_label": "",
            })

    def write(name, data, fields=None):
        with (out / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields or (list(data[0].keys()) if data
                                                         else ["empty"]))
            w.writeheader()
            w.writerows(data)

    write("claim_ledger.csv", cl)
    write("binding_review.csv", review)
    write("rejection_ledger.csv",
          [{"paper_id": r["paper_id"], "claim_id": r["claim_id"],
            "section": r.get("section") or "", "block_type": r.get("block_type") or "",
            "page": r.get("page") or "", "reason_code": r["reason_code"],
            "sentence": r.get("sentence", "")[:300]} for r in rejections])

    # ---- buckets, now exhaustive ----------------------------------------
    entered = [r for r in cl if r["entered_binder"]]
    bound = [r for r in cl if r["binding_status"] == "bound"]
    nobind = [r for r in entered if r["binding_status"] != "bound"]

    def bucket_of(r):
        if r["value_found_in_attached_cells"]:
            return "B-BIND", ""
        if r["value_found_in_gate_rejected_or_fallback_table_text"]:
            return "B-TABLE", ""
        if r["triage"] == "TABLE_POSSIBLY_UNDETECTED":
            return "B-UNDETECTED", ""
        if r["triage"] == "PROSE_ONLY":
            return "B-PROSE", ""
        # exhaustive remainder: previously unbucketed
        if r["value_found_in_discarded_cells"]:
            return "B-NONE", "VALUE_ONLY_IN_DISCARDED_CELLS"
        if not r["numeric_values_raw"]:
            return "B-NONE", "NO_NUMERIC_VALUE_IN_CLAIM"
        return "B-NONE", "UNCLASSIFIED"

    bk, bnone_reasons = Counter(), Counter()
    for r in nobind:
        b, why = bucket_of(r)
        bk[b] += 1
        r["bucket"] = b
        r["bucket_reason"] = why
        if b == "B-NONE":
            bnone_reasons[why] += 1
    write("claim_ledger.csv", cl)      # rewrite with bucket columns

    total_bucketed = sum(bk.values())
    expected = len(entered) - len(bound)
    reconciles = total_bucketed == expected

    flagged = [r for r in review if r["ownership_flag"]]
    unflagged = [r for r in review if not r["ownership_flag"]]

    # ---- labeling sample / reserve --------------------------------------
    rnd = random.Random(SEED)
    order = list(flagged)
    rnd.shuffle(order)
    sample_flagged, reserve = order[:SAMPLE_N], order[SAMPLE_N:SAMPLE_N + RESERVE_N]
    sample = unflagged + sample_flagged
    rnd.shuffle(sample)
    if flagged or unflagged:
        write("labeling_sample.csv", sample)
        write("labeling_reserve.csv", reserve, fields=list(review[0].keys()) if review else None)

    # The pre-registered decision rule counts FLAGGED BINDINGS. Warn mode admits
    # many newly-RETURNED claims but almost none of them are bindings, so that
    # denominator can be tiny. The claim-level population is emitted alongside it,
    # clearly separate, so the human can choose the denominator. This does NOT
    # apply or alter the pre-registered rule.
    flagged_claims = [r for r in cl if r["ownership_flag"]]
    if flagged_claims:
        rc = random.Random(SEED)
        order_c = list(flagged_claims)
        rc.shuffle(order_c)
        write("labeling_sample_claims.csv",
              [{**r, "human_label": ""} for r in order_c[:SAMPLE_N]])
        write("labeling_reserve_claims.csv",
              [{**r, "human_label": ""} for r in order_c[SAMPLE_N:SAMPLE_N + RESERVE_N]])

    new_bindings = flagged
    buckets = {
        "arm": a.out,
        "claims_total": len(cl), "entered_binder": len(entered), "bound": len(bound),
        "papers_with_claim_entering_binder": len({r["paper_id"] for r in entered}),
        "papers_total": len(papers),
        "returned_metrics": sum(1 for r in cl if r["field"] == "metrics"
                                and r["terminal_state"] == "RETURNED"),
        "returned_results": sum(1 for r in cl if r["field"] == "results"
                                and r["terminal_state"] == "RETURNED"),
        "returned_total": sum(1 for r in cl if r["terminal_state"] == "RETURNED"),
        "ownership_flagged_claims": sum(1 for r in cl if r["ownership_flag"]),
        "buckets": dict(bk),
        "B-NONE_reasons": dict(bnone_reasons),
        "B-BIND_by_terminal_reason": dict(Counter(
            r["terminal_reason_code"] for r in nobind if bucket_of(r)[0] == "B-BIND")),
        "bucket_sum": total_bucketed, "expected_sum": expected,
        "buckets_reconcile": reconciles,
        "binding_status_counts": dict(Counter(r["binding_status"] for r in cl)),
        "terminal_reason_counts": dict(Counter(r["terminal_reason_code"] for r in cl)),
        "bindings_reviewed": len(review),
        "bindings_flagged": len(flagged), "bindings_unflagged": len(unflagged),
        "bindings_sign_mismatch": sum(1 for r in review if r["sign_match"] is False),
        "bindings_sign_not_assessable": sum(1 for r in review if r["sign_match"] == ""),
        "labeling_sample_rows": len(sample), "labeling_reserve_rows": len(reserve),
        "flagged_returned_claims": len(flagged_claims),
        "labeling_sample_claims_rows": min(len(flagged_claims), SAMPLE_N),
        "labeling_reserve_claims_rows": max(0, min(len(flagged_claims) - SAMPLE_N,
                                                   RESERVE_N)),
        "new_bindings_mention_agreement": dict(Counter(
            r["mention_matches_bound_table"] for r in new_bindings)),
        "new_bindings_value_occurrences": dict(Counter(
            r["value_occurrences_in_paper"] for r in new_bindings)),
        "new_bindings_f1_bibliography": sum(1 for r in new_bindings
                                            if r["f1_bibliography_heuristic"]),
        "f1_bibliography_claims": sum(1 for r in cl if r["f1_bibliography_heuristic"]),
    }
    (out / "buckets.json").write_text(json.dumps(buckets, indent=1), encoding="utf-8")

    print(f"== {a.out} ==")
    print(f"  claims={buckets['claims_total']} entered={buckets['entered_binder']} "
          f"bound={buckets['bound']} returned={buckets['returned_total']} "
          f"papers={buckets['papers_with_claim_entering_binder']}/{buckets['papers_total']}")
    print(f"  ownership-flagged claims: {buckets['ownership_flagged_claims']}")
    print(f"  buckets: {dict(bk)}")
    print(f"  B-NONE reasons: {dict(bnone_reasons)}")
    print(f"  B-BIND by reason: {buckets['B-BIND_by_terminal_reason']}")
    print(f"  RECONCILIATION: sum={total_bucketed} expected(entered-bound)={expected} "
          f"{'PASS' if reconciles else '*** FAIL ***'}")
    print(f"  bindings: total={len(review)} flagged={len(flagged)} unflagged={len(unflagged)} "
          f"sign_mismatch={buckets['bindings_sign_mismatch']}")
    print(f"  new-binding mention agreement: {buckets['new_bindings_mention_agreement']}")
    print(f"  new-binding value occurrences: {buckets['new_bindings_value_occurrences']}")
    print(f"  new bindings flagged by F-1 heuristic: {buckets['new_bindings_f1_bibliography']}")
    print(f"  labeling_sample={buckets['labeling_sample_rows']} "
          f"reserve={buckets['labeling_reserve_rows']}")
    print(f"  -> {out}")
    return 0 if reconciles else 1


if __name__ == "__main__":
    raise SystemExit(main())
