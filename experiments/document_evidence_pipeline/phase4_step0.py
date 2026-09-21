"""PHASE 4 STEP 0 — parse and verify Prakash's binary labels from the audit sheet.

Does no other work. Ground truth is human_audit.md and nothing else: no provisional
label, no judge output, no Phase 3 suggestion is read here or used as a substitute.

Writes runs/phase4_denominator/human_labels.json + step0_report.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHEET = HERE / "runs" / "phase3_label_assist" / "human_audit.md"
ROUTING = HERE / "runs" / "phase3_label_assist" / "routing.json"
SAMPLE_U = HERE / "runs" / "phase3_composition" / "sample_unnamed.json"
SAMPLE_N = HERE / "runs" / "phase3_composition" / "sample_named.json"
OUT = HERE / "runs" / "phase4_denominator"

ALLOWED = {"Y", "N", "UNCERTAIN"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = SHEET.read_text(encoding="utf-8")

    # 0.1 -- ids present, in sheet order, with duplicate detection
    blocks = re.split(r"^### ", text, flags=re.M)[1:]
    ids_in_order = [b.split("\n", 1)[0].strip() for b in blocks]
    dup = [i for i, c in Counter(ids_in_order).items() if c > 1]

    # parse one answer per block
    parsed, problems = {}, []
    for b in blocks:
        sid = b.split("\n", 1)[0].strip()
        hits = re.findall(r"^->(.*)$", b, flags=re.M)
        if len(hits) != 1:
            problems.append({"id": sid, "issue": f"{len(hits)} answer lines", "verbatim": hits})
            continue
        raw = hits[0].strip()
        norm = raw.upper()
        if norm in ALLOWED:
            parsed[sid] = norm
        elif raw == "Y / N":
            problems.append({"id": sid, "issue": "blank (unanswered)", "verbatim": raw})
        else:
            problems.append({"id": sid, "issue": "unparseable/ambiguous", "verbatim": raw})

    # 0.4 -- n established from the artifacts, not assumed
    sheet_u = [i for i in ids_in_order if i.startswith("U")]
    sheet_n = [i for i in ids_in_order if i.startswith("N")]
    parsed_a = {k: v for k, v in parsed.items() if k.startswith("U")}
    parsed_b = {k: v for k, v in parsed.items() if k.startswith("N")}

    # 0.5 -- the 5 ids in the Phase 3 sample but not on the sheet
    full_u = [r["sample_id"] for r in json.loads(SAMPLE_U.read_text(encoding="utf-8"))]
    full_n = [r["sample_id"] for r in json.loads(SAMPLE_N.read_text(encoding="utf-8"))]
    full = full_u + full_n
    absent = [i for i in full if i not in set(ids_in_order)]
    routing = {r["id"]: r for r in json.loads(ROUTING.read_text(encoding="utf-8"))["items"]}
    absent_prov = []
    for i in absent:
        r = routing.get(i)
        absent_prov.append({
            "id": i,
            "provenance": "routing.json" if r else "UNKNOWN",
            "route": r["route"] if r else None,
            "why": r["why"] if r else None,
            "rules_fired": r["rules_fired"] if r else None,
            "provisional_label": r["provisional_label"] if r else None,
            "status": "UNAUDITED — no human label assigned, excluded from every human-label denominator",
        })

    rep = {
        "input_files_read": [str(SHEET), str(ROUTING), str(SAMPLE_U), str(SAMPLE_N)],
        "0.1_ids_present_in_sheet": ids_in_order,
        "0.1_count": len(ids_in_order),
        "0.1_duplicates": dup,
        "0.2_answered": len(parsed),
        "0.2_problems": problems,
        "0.3_counts_task_A": dict(Counter(parsed_a.values())),
        "0.3_counts_task_B": dict(Counter(parsed_b.values())),
        "0.4_n_task_A_on_sheet": len(sheet_u), "0.4_n_task_A_parsed": len(parsed_a),
        "0.4_n_task_B_on_sheet": len(sheet_n), "0.4_n_task_B_parsed": len(parsed_b),
        "0.5_phase3_sample_size": len(full),
        "0.5_absent_from_sheet": absent_prov,
    }
    (OUT / "human_labels.json").write_text(json.dumps(parsed, indent=1), encoding="utf-8")
    (OUT / "step0_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")

    print(f"0.1  ids present: {len(ids_in_order)}  duplicates: {dup or 'none'}")
    print(f"0.2  answered: {len(parsed)}   problems: {len(problems)}")
    for p in problems:
        print(f"       {p['id']}: {p['issue']} -> {p['verbatim']!r}")
    print(f"0.3  Task A: {dict(Counter(parsed_a.values()))}")
    print(f"     Task B: {dict(Counter(parsed_b.values()))}")
    print(f"0.4  Task A on sheet {len(sheet_u)}, parsed {len(parsed_a)} | "
          f"Task B on sheet {len(sheet_n)}, parsed {len(parsed_b)}")
    print(f"0.5  absent from sheet ({len(absent)}): {[a['id'] for a in absent_prov]}")
    for a in absent_prov:
        print(f"       {a['id']}: {a['provenance']} route={a['route']} "
              f"rules={a['rules_fired']} provisional={a['provisional_label']}")
    gate = len(parsed) >= 85 and not problems and not dup
    print(f"\nSTEP 0 GATE: {'PASS' if gate else 'FAIL'}")


if __name__ == "__main__":
    main()
