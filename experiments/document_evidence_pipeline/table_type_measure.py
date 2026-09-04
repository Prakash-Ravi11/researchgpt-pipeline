"""Phase 5a (cont.) — deterministic table-type classification, fed into the gate.

  - classification distribution across structured papers
  - currently-returned quant items grounded in an ablation table
  - 10-table manual spot-check (caption text + class)
Test 2 confusion matrix is re-checked via `gate_sensitivity.py --pass det`.
  python -u experiments/document_evidence_pipeline/table_type_measure.py
"""
from __future__ import annotations
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import src.evidence.gate as G                                                # noqa: E402
from src.evidence.gate import (gate_paper, classify_table, paper_table_cells,   # noqa: E402
                               structural_bind, _table_type_for)
from src.evidence.represent import blocks_from_jats                          # noqa: E402
from src.evidence.chunker import chunk_document                             # noqa: E402
from latex_ingestion_measure import PROC, OUT as LI_OUT                      # noqa: E402

CANON = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CACHE = json.loads((CANON / "processed" / "extraction_cache.json").read_text(encoding="utf-8"))
META = {m["paperId"]: m for m in json.loads((CANON / "raw_metadata" / "collected_papers.json").read_text(encoding="utf-8"))}
OUT = HERE / "runs" / "structural_binding"
STRUCT = {"latex", "jats_xml"}
_NUM = re.compile(r"\d+\.\d+|\b\d{2,}\b")


def main() -> int:
    reps = json.loads((LI_OUT / "reps.json").read_text(encoding="utf-8"))
    chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    by_paper = defaultdict(list)
    for c in chunks:
        by_paper[c["paper_id"]].append(c)
    for pid, rep in reps.items():
        if rep == "jats_xml":
            xml = CANON / "pdfs" / f"{pid}.xml"
            if xml.exists():
                by_paper[pid] = chunk_document({"paper_id": pid, "representation": "jats_xml",
                                                "blocks": blocks_from_jats(xml.read_bytes(), pid, "europepmc")})
    struct_ids = [p for p in reps if reps[p].split("(")[0] in STRUCT]

    # ---- 1. classification distribution ----
    tables = []   # (paper, caption, class, n_cells)
    for pid in struct_ids:
        cells = paper_table_cells(by_paper[pid])
        bycap = defaultdict(list)
        for c in cells:
            bycap[c.get("caption", "")].append(c)
        for cap, cs in bycap.items():
            cls = classify_table(cap, {c.get("column_header", "") for c in cs},
                                 {c.get("row_label", "") for c in cs})
            tables.append((pid[:10], cap, cls, len(cs)))
    dist = Counter(t[2] for t in tables)
    print(f"structured papers: {len(struct_ids)}   distinct tables: {len(tables)}")
    print(f"classification distribution: {dict(dist)}")
    print(f"  (by cells: {dict(Counter(t[2] for t in tables for _ in range(t[3])))})")
    (OUT / "table_types.json").write_text(json.dumps(
        [{"paper": p, "caption": c, "class": cl, "n_cells": n} for p, c, cl, n in tables],
        indent=2), encoding="utf-8")

    # ---- 2. currently-returned quant items grounded in an ablation table ----
    _orig = G.structural_bind
    G.structural_bind = lambda v, ch: {"structured": True, "status": "bound"}   # binding OFF
    returned = []
    for pid in struct_ids:
        m = META.get(pid, {})
        rec = {"paper_id": pid, **{k: CACHE.get(pid, {}).get(k) for k in ("datasets", "metrics", "results")}}
        sn = [a.get("name", "") for a in (m.get("authors") or []) if isinstance(a, dict)]
        g = gate_paper(rec, by_paper[pid], "FULL_TEXT", sn)
        for f in ("metrics", "results"):
            for it in g["evidence"][f]:
                if it["final"] == "RETURNED" and _NUM.search(it.get("value") or ""):
                    returned.append((pid, f, it.get("value")))
    G.structural_bind = _orig
    abl = []
    for pid, f, v in returned:
        sb = structural_bind(v, by_paper[pid])
        if sb.get("status") == "bound" and sb.get("table_type") == "ablation":
            abl.append((pid[:10], f, v[:90], sb["cell"]["caption"][:80]))
    print(f"\ncurrently-returned (binding OFF) structured quant items: {len(returned)}")
    print(f"  of those, grounded in an ABLATION table: {len(abl)}")
    for r in abl:
        print(f"    [{r[0]}] {r[1]}: {r[2]}   <- table: {r[3]!r}")
    bound_types = Counter()
    for pid, f, v in returned:
        sb = structural_bind(v, by_paper[pid])
        bound_types[f"{sb.get('status')}/{sb.get('table_type')}"] += 1
    print(f"  binding-ON status/table_type of those items: {dict(bound_types)}")

    # ---- 3. 10-table manual spot-check ----
    print("\n== 10-table spot-check (deterministic sample) ==")
    sample = sorted(tables, key=lambda t: (t[0], t[1]))[:: max(1, len(tables) // 10)][:10]
    for p, cap, cls, n in sample:
        print(f"  [{p}] {cls:9} ({n:3} cells)  caption: {cap[:150]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
