"""R4: isolation check, transition table, H-1 flag, labeling file. Read-only.

    python diagnostics/funnel/analyze_disambiguation.py --out-root out \
        --legacy disambig_legacy --scored disambig_scored

Reads both arms' trace.jsonl and results.json. Computes:
  * h1_flattened_table_text, a READ-ONLY heuristic label -- it filters nothing;
  * the isolation check (claims with <= 1 value-matching candidate, or that never
    reach cell selection, must be identical between arms);
  * the legacy -> scored transition table for multi-candidate claims, split by the
    H-1 and F-1 labels (labels only, never filters);
  * labeling_disambig.csv.
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

SEED = 20260924
STRIP = re.compile(r"[^\d.\-]")
NUMTOK = re.compile(r"^[-+−]?\d+(?:[.,]\d+)?%?$")
F1_RE = re.compile(r"arxiv\.org|url http|doi\.org|pages?\s+\d+|proceedings|"
                   r"conference on|in emnlp|in acl|in sigir", re.I)

# statuses that mean the claim reached the cell-selection step
REACHED = {"bound", "wrong_cell", "ABSTAIN_AMBIGUOUS"}


def has(n: str, s) -> bool:
    s = str(s)
    if n == STRIP.sub("", s):
        return True
    return bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))


def load(out: Path):
    raw = (out / "trace.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(x) for x in raw.split("\n") if x.strip()]
    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return rows, payload


def tables_by_paper(rows):
    per = defaultdict(list)
    for r in rows:
        if r["stage"] != "A0_attach_detail":
            continue
        d = r["detail"] or {}
        per[r["paper_id"]].append({
            "table_id": r["item_id"], "path": d.get("extraction_path"),
            "values": [str(v) for v in (d.get("attached_values") or [])],
            "cells": d.get("attached_cells") or [],
        })
    return per


def h1_flag(claim_text: str, block_type: str | None, tables) -> tuple[bool, str]:
    """H-1 heuristic. Paragraph block AND (>=50% numeric tokens OR >=3 numeric
    tokens equal to attached-cell values of ONE single table)."""
    if (block_type or "") != "paragraph":
        return False, ""
    toks = [t for t in re.split(r"\s+", claim_text or "") if t]
    if not toks:
        return False, ""
    numeric = [t for t in toks if NUMTOK.match(t.strip("()[],;:"))]
    if len(numeric) * 2 >= len(toks):
        return True, f"numeric_token_ratio={len(numeric)}/{len(toks)}"
    nums = NUMERIC_ANCHOR_RE.findall(claim_text or "")
    for t in tables:
        if t["path"] != "cell_table":
            continue
        hits = {n for n in nums if any(has(n, v) for v in t["values"])}
        if len(hits) >= 3:
            return True, f"{len(hits)}_numeric_tokens_in_one_table:{t['table_id']}"
    return False, ""


def claim_rows(rows, payload):
    """One row per gated evidence item, in trace order (both arms align)."""
    res, papers = payload["results"], payload["papers"]
    ex = {}
    for pid in papers:
        for c in (res[pid].get("explicit_claims") or []):
            ex[(pid, c["sentence"])] = c
    tb = tables_by_paper(rows)
    binder = defaultdict(list)
    for r in rows:
        if r["stage"] == "B2_binder":
            binder[r["paper_id"]].append(r["detail"] or {})
    out = []
    for r in rows:
        if r["stage"] != "B0_evidence_item":
            continue
        d = r["detail"] or {}
        if d.get("field") not in ("metrics", "results"):
            continue
        text = d.get("value") or ""
        if not re.search(r"\d", text):
            continue
        pid = r["paper_id"]
        e = ex.get((pid, text), {})
        probe = next((p for p in binder[pid] if p.get("claim_text") == text), {})
        h1, h1why = h1_flag(text, e.get("block_type"), tb.get(pid, []))
        out.append({
            "paper_id": pid, "claim_text": text,
            "claim_id": e.get("claim_id", r["item_id"]),
            "section": e.get("section") or "", "page": str(e.get("page") or ""),
            "block_type": e.get("block_type") or "",
            "binding_status": d.get("binding_status") or "no_binding_call",
            "terminal_state": d.get("final") or "ABSTAINED",
            "terminal_reason": r["reason_code"],
            "cell": d.get("binding_cell") or {},
            "candidate": d.get("binding_candidate") or {},
            "r4": d.get("r4") or {},
            "n_value_matching": probe.get("n_value_matching_cells"),
            "metric": "|".join(probe.get("claim_metric_tokens") or []),
            "nums": "|".join(NUMERIC_ANCHOR_RE.findall(text)),
            "h1": h1, "h1_why": h1why,
            "f1": bool(F1_RE.search(e.get("section") or "") or F1_RE.search(text)),
            "table_mentions": "|".join(e.get("table_mentions_raw") or []),
        })
    return out


def cell_key(c):
    if not c:
        return None
    return (c.get("row"), c.get("col"), str(c.get("value")), c.get("caption"))


def outcome(r):
    s = r["binding_status"]
    if s == "bound":
        return "BOUND"
    if s == "wrong_cell":
        return "WRONG_CELL"
    if s == "ABSTAIN_AMBIGUOUS":
        return "ABSTAIN_AMBIGUOUS"
    return f"other:{s}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=str(HERE / "out"))
    ap.add_argument("--legacy", default="disambig_legacy")
    ap.add_argument("--scored", default="disambig_scored")
    a = ap.parse_args()
    root = Path(a.out_root)
    Lr, Lp = load(root / a.legacy)
    Sr, Sp = load(root / a.scored)
    L, S = claim_rows(Lr, Lp), claim_rows(Sr, Sp)

    if len(L) != len(S):
        print(f"*** STOP: row counts differ, legacy={len(L)} scored={len(S)}")
        return 1
    misaligned = [i for i, (x, y) in enumerate(zip(L, S))
                  if x["paper_id"] != y["paper_id"] or x["claim_text"] != y["claim_text"]]
    if misaligned:
        print(f"*** STOP: {len(misaligned)} rows misaligned")
        return 1

    # ---- isolation check ------------------------------------------------
    exceptions = []
    for x, y in zip(L, S):
        reached = x["binding_status"] in REACHED or y["binding_status"] in REACHED
        ncand = x["n_value_matching"]
        multi = reached and isinstance(ncand, int) and ncand >= 2
        if multi:
            continue                      # allowed to differ
        if (x["binding_status"] != y["binding_status"]
                or x["terminal_state"] != y["terminal_state"]
                or x["terminal_reason"] != y["terminal_reason"]
                or cell_key(x["cell"]) != cell_key(y["cell"])):
            exceptions.append({
                "claim_id": x["claim_id"], "paper_id": x["paper_id"],
                "reached_cell_selection": reached, "n_value_matching": ncand,
                "legacy": [x["binding_status"], x["terminal_state"], x["terminal_reason"]],
                "scored": [y["binding_status"], y["terminal_state"], y["terminal_reason"]],
                "claim_text": x["claim_text"][:200],
            })
    isolation_pass = not exceptions

    # ---- transition table, multi-candidate claims only ------------------
    multi = [(x, y) for x, y in zip(L, S)
             if (x["binding_status"] in REACHED or y["binding_status"] in REACHED)
             and isinstance(x["n_value_matching"], int) and x["n_value_matching"] >= 2]
    trans, trans_h1, trans_f1 = Counter(), Counter(), Counter()
    changed = []
    for x, y in multi:
        lo, so = outcome(x), outcome(y)
        if lo == "BOUND" and so == "BOUND":
            so = ("BOUND same cell" if cell_key(x["cell"]) == cell_key(y["cell"])
                  else "BOUND different cell")
            lo = "BOUND"
        key = (lo, so)
        trans[key] += 1
        trans_h1[(key, x["h1"])] += 1
        trans_f1[(key, x["f1"])] += 1
        if so != lo or (so.startswith("BOUND") and lo == "BOUND"
                        and cell_key(x["cell"]) != cell_key(y["cell"])):
            changed.append((x, y, lo, so))

    # ---- labeling file ---------------------------------------------------
    legacy_bound = [(x, y) for x, y in zip(L, S) if x["binding_status"] == "bound"]
    scored_bound = [(x, y) for x, y in zip(L, S) if y["binding_status"] == "bound"]
    rows_out, seen = [], set()

    def add(x, y, kind):
        k = (y["paper_id"], y["claim_text"], kind)
        if k in seen:
            return
        seen.add(k)
        c = y["cell"] or x["cell"] or {}
        rows_out.append({
            "kind": kind,
            "paper_id": y["paper_id"], "claim_id": y["claim_id"],
            "claim_sentence": y["claim_text"],
            "metric": y["metric"],
            "bound_cell_value": str(c.get("value") or ""),
            "row_label": c.get("row") or "",
            "column_header_path": f"{c.get('caption') or ''} > {c.get('col') or ''}",
            "table_caption": c.get("caption") or "",
            "page": y["page"],
            "score": (y["r4"] or {}).get("top_score", ""),
            "h1_flag": y["h1"], "f1_flag": y["f1"],
            "legacy_status": x["binding_status"], "scored_status": y["binding_status"],
            "human_label": "",
        })

    for x, y in scored_bound:
        if x["binding_status"] != "bound":
            add(x, y, "new_scored_binding")
        elif cell_key(x["cell"]) != cell_key(y["cell"]):
            add(x, y, "changed_scored_binding")
    for x, y in legacy_bound:
        add(x, y, "legacy_binding")

    rnd = random.Random(SEED)
    rnd.shuffle(rows_out)
    dest = root / a.scored
    with (dest / "labeling_disambig.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()) if rows_out
                           else ["empty"])
        w.writeheader()
        w.writerows(rows_out)

    # ---- H-1 counts across all buckets ---------------------------------
    h1_total = sum(1 for r in S if r["h1"])
    h1_by_status = Counter(r["binding_status"] for r in S if r["h1"])

    summary = {
        "legacy_arm": a.legacy, "scored_arm": a.scored,
        "claim_rows": len(L),
        "legacy_bound": sum(1 for r in L if r["binding_status"] == "bound"),
        "scored_bound": sum(1 for r in S if r["binding_status"] == "bound"),
        "scored_abstain_ambiguous": sum(1 for r in S
                                        if r["binding_status"] == "ABSTAIN_AMBIGUOUS"),
        "legacy_wrong_cell": sum(1 for r in L if r["binding_status"] == "wrong_cell"),
        "scored_wrong_cell": sum(1 for r in S if r["binding_status"] == "wrong_cell"),
        "legacy_status_counts": dict(Counter(r["binding_status"] for r in L)),
        "scored_status_counts": dict(Counter(r["binding_status"] for r in S)),
        "multi_candidate_claims": len(multi),
        "isolation_pass": isolation_pass,
        "isolation_exceptions": exceptions[:40],
        "isolation_exception_count": len(exceptions),
        "transition_table": {f"{k[0]} -> {k[1]}": v for k, v in trans.items()},
        "transition_by_h1": {f"{k[0][0]} -> {k[0][1]} | h1={k[1]}": v
                             for k, v in trans_h1.items()},
        "transition_by_f1": {f"{k[0][0]} -> {k[0][1]} | f1={k[1]}": v
                             for k, v in trans_f1.items()},
        "h1_total": h1_total, "h1_by_binding_status": dict(h1_by_status),
        "labeling_rows": len(rows_out),
        "labeling_by_kind": dict(Counter(r["kind"] for r in rows_out)),
        "labeling_h1_flagged": sum(1 for r in rows_out if r["h1_flag"]),
        "labeling_f1_flagged": sum(1 for r in rows_out if r["f1_flag"]),
        "labeling_eligible_excl_h1_f1": sum(1 for r in rows_out
                                            if not r["h1_flag"] and not r["f1_flag"]),
    }
    (dest / "disambiguation_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"claim rows: legacy={len(L)} scored={len(S)} aligned=True")
    print(f"legacy status : {summary['legacy_status_counts']}")
    print(f"scored status : {summary['scored_status_counts']}")
    print(f"multi-candidate claims: {len(multi)}")
    print(f"\nISOLATION: {'PASS' if isolation_pass else '*** STOP ***'} "
          f"exceptions={len(exceptions)}")
    for e in exceptions[:10]:
        print(f"  {e['claim_id']} {e['paper_id'][:12]} ncand={e['n_value_matching']} "
              f"{e['legacy']} -> {e['scored']}")
    print("\nTRANSITION TABLE (multi-candidate only):")
    for k, v in sorted(trans.items(), key=lambda kv: -kv[1]):
        print(f"  {k[0]:20} -> {k[1]:24} {v:>5}")
    print("\n  split by h1:")
    for k, v in sorted(trans_h1.items(), key=lambda kv: -kv[1]):
        print(f"    {k[0][0]:18} -> {k[0][1]:22} h1={str(k[1]):5} {v:>5}")
    print("\n  split by f1:")
    for k, v in sorted(trans_f1.items(), key=lambda kv: -kv[1]):
        print(f"    {k[0][0]:18} -> {k[0][1]:22} f1={str(k[1]):5} {v:>5}")
    print(f"\nH-1 flagged claims: {h1_total} of {len(S)}")
    print(f"  by binding status: {dict(h1_by_status)}")
    print(f"\nlabeling rows: {len(rows_out)} {dict(Counter(r['kind'] for r in rows_out))}")
    print(f"  h1-flagged={summary['labeling_h1_flagged']} "
          f"f1-flagged={summary['labeling_f1_flagged']} "
          f"eligible(excl h1/f1)={summary['labeling_eligible_excl_h1_f1']}")
    print(f"-> {dest / 'labeling_disambig.csv'}")
    return 0 if isolation_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
