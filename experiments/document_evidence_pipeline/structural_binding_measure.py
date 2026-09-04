"""Phase 5a MEASURE — structural cell binding in the evidence gate.

  1. returned metrics/results count, structural-binding OFF vs ON, split by
     structured (LaTeX-retained + JATS) vs PDF-only.
  2. cross-row acceptances on structured papers (must be 0) + 4 new probe classes:
     correct row/wrong column, correct column/wrong row, correct metric/wrong
     condition, cross-table substitution.

Isolated: reuses the Phase-4b canonical re-chunk (LaTeX parity gate ON so
structured cells exist), reads Stage-4 output from the frozen extraction cache,
runs the REAL gate_paper. Writes runs/structural_binding/.
  python -u experiments/document_evidence_pipeline/structural_binding_measure.py
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
from src.evidence.gate import (gate_paper, structural_bind, paper_table_cells,  # noqa: E402
                               _METRIC_TOKENS, _col_matches_metric)
from src.evidence.represent import blocks_from_jats                          # noqa: E402
from src.evidence.chunker import chunk_document                             # noqa: E402
from latex_ingestion_measure import _rechunk_canonical, PROC, OUT as LI_OUT   # noqa: E402

CANON = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CACHE = CANON / "processed" / "extraction_cache.json"
META = CANON / "raw_metadata" / "collected_papers.json"
OUT = HERE / "runs" / "structural_binding"
OUT.mkdir(parents=True, exist_ok=True)
_NUM = re.compile(r"\d")
STRUCT = {"latex", "jats_xml"}


def _returned(rec, chunks, surnames, acq):
    g = gate_paper(rec, chunks, acq, surnames)
    out = []
    for f in ("metrics", "results"):
        for it in g["evidence"][f]:
            if it["final"] == "RETURNED" and _NUM.search(it.get("value") or ""):
                out.append((f, it.get("value"), (it.get("structural_binding") or {}).get("status")))
    return out


def main() -> int:
    if not (LI_OUT / "reps.json").exists() or not (PROC / "chunks.json").exists():
        ft_ids, reps = _rechunk_canonical()
        (LI_OUT / "reps.json").write_text(json.dumps(reps, indent=2), encoding="utf-8")
    reps = json.loads((LI_OUT / "reps.json").read_text(encoding="utf-8"))
    chunks_all = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    by_paper = defaultdict(list)
    for c in chunks_all:
        by_paper[c["paper_id"]].append(c)
    # _rechunk_canonical copies FROZEN chunks for non-arXiv papers -> the 2 JATS
    # papers have no table_cells. Re-process them here through the cell-bearing path.
    for pid, rep in reps.items():
        if rep == "jats_xml":
            xml = CANON / "pdfs" / f"{pid}.xml"
            if xml.exists():
                blocks = blocks_from_jats(xml.read_bytes(), pid, "europepmc")
                by_paper[pid] = chunk_document({"paper_id": pid, "representation": "jats_xml",
                                                "blocks": blocks})
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    meta = {m["paperId"]: m for m in json.loads(META.read_text(encoding="utf-8"))}
    ft_ids = sorted(reps)
    print(f"papers: {len(ft_ids)}  reps: {dict(Counter(reps.values()))}")
    cell_counts = {p: len(paper_table_cells(by_paper[p])) for p in ft_ids}
    print(f"papers with >=1 structured cell: {sum(1 for v in cell_counts.values() if v)}  "
          f"(total cells {sum(cell_counts.values())})")

    # ---- 1. returned count, binding OFF vs ON ----
    def run(label):
        rows = {}
        for pid in ft_ids:
            m = meta.get(pid, {})
            rec = {"paper_id": pid, **{k: cache.get(pid, {}).get(k) for k in
                                       ("datasets", "metrics", "results")}}
            sn = [a.get("name", "") for a in (m.get("authors") or []) if isinstance(a, dict)]
            rows[pid] = _returned(rec, by_paper[pid], sn, "FULL_TEXT")
        return rows

    _orig = G.structural_bind
    G.structural_bind = lambda v, ch: {"structured": True, "status": "bound"}   # neutralise
    off = run("OFF")
    G.structural_bind = _orig
    on = run("ON")

    def split(rows):
        s = sum(len(v) for p, v in rows.items() if reps[p].split("(")[0] in STRUCT)
        pdf = sum(len(v) for p, v in rows.items() if reps[p].split("(")[0] not in STRUCT)
        return s, pdf

    o_s, o_p = split(off)
    n_s, n_p = split(on)
    print("\n== 1. RETURNED numeric metrics/results — binding OFF vs ON ==")
    print(f"  {'subset':22} {'OFF':>6} {'ON':>6} {'delta':>7}")
    print(f"  {'structured (LaTeX+JATS)':22} {o_s:>6} {n_s:>6} {n_s - o_s:>7}")
    print(f"  {'PDF-only':22} {o_p:>6} {n_p:>6} {n_p - o_p:>7}   (reduction = CORRECTION)")
    print(f"  {'total':22} {o_s + o_p:>6} {n_s + n_p:>6} {n_s + n_p - o_s - o_p:>7}")
    binding_status = Counter(st for v in on.values() for _, _, st in v)
    print(f"  ON returned-item binding status: {dict(binding_status)}")
    (OUT / "returned_counts.json").write_text(json.dumps(
        {"off": {p: off[p] for p in off}, "on": {p: on[p] for p in on},
         "reps": reps, "cell_counts": cell_counts}, indent=2, default=str), encoding="utf-8")

    # ---- 2. cross-row + 4 new probe classes on STRUCTURED papers ----
    print("\n== 2. binding probes on structured papers ==")
    probes = []
    for pid in ft_ids:
        if reps[pid].split("(")[0] not in STRUCT:
            continue
        cells = paper_table_cells(by_paper[pid])
        # group cells by (caption) -> table; need >=2 rows and >=2 cols
        tabs = defaultdict(list)
        for c in cells:
            tabs[c.get("caption", "")].append(c)
        m = meta.get(pid, {})
        sn = [a.get("name", "") for a in (m.get("authors") or []) if isinstance(a, dict)]

        def gate(claim):
            rec = {"paper_id": pid, "metrics": [], "results": claim}
            g = gate_paper(rec, by_paper[pid], "FULL_TEXT", sn)
            its = g["evidence"]["results"]
            it = its[-1] if its else {}
            return it.get("final"), it.get("abstain_reason") or it.get("attribution"), \
                (it.get("structural_binding") or {}).get("status")

        _clean = re.compile(r"^[\sA-Za-z0-9().,%\-↑↓/]+$")   # drop LaTeX-junk labels
        _numv = re.compile(r"^-?\d+(?:\.\d+)?$")

        def metric_cols(t):
            return sorted({c["column_header"] for c in t if c["column_header"]
                           and _clean.match(c["column_header"])
                           and _col_matches_metric(c["column_header"], _METRIC_TOKENS)})

        _own = re.compile(r"\b(our[s]?|proposed|full model|full|hybrid| RAG\b|method|framework|pipeline)\b", re.I)
        good_tabs = [t for t in tabs.values() if len(t) >= 4 and metric_cols(t)
                     and len({c["row_label"] for c in t if c["row_label"] and _clean.match(c["row_label"])}) >= 2]
        for t in good_tabs[:3]:
            mcols = metric_cols(t)
            rows = sorted({c["row_label"] for c in t if c["row_label"] and _clean.match(c["row_label"])})
            if len(mcols) < 1 or len(rows) < 2:
                continue
            cA = mcols[0]
            cB = mcols[1] if len(mcols) > 1 else None
            # rA = an OWN-method row if the table has one, else the first row
            rA = next((r for r in rows if _own.search(r)), rows[0])
            rB = next((r for r in rows if r != rA), rows[0])
            def _sane(s):
                m = re.sub(r"[^\d.\-]", "", str(s))
                if not _numv.match(m):
                    return None
                try:
                    x = abs(float(m))
                except ValueError:
                    return None
                return m if 0.05 <= x <= 100 else None   # skip p-values / junk / raw counts

            def cval(r, c):
                return next((_sane(x["value"]) for x in t if x["row_label"] == r
                             and x["column_header"] == c and _sane(x["value"])), None)
            vAA, vAB, vBA = cval(rA, cA), (cval(rA, cB) if cB else None), cval(rB, cA)
            mk = lambda subj, met, num: f"{subj} reports a {met} of {num} on the benchmark."
            cases = []
            if vAA and re.sub(r"[^\d.\-]", "", str(vAA)):
                cases.append(("correct_cell", mk(rA, cA, re.sub(r'[^\d.\-]', '', str(vAA)))))
            if vAB and vAB != vAA:
                cases.append(("correct_row_wrong_col", mk(rA, cA, re.sub(r'[^\d.\-]', '', str(vAB)))))
            if vBA and vBA != vAA:
                cases.append(("correct_col_wrong_row", mk(rA, cA, re.sub(r'[^\d.\-]', '', str(vBA)))))
            other = next((re.sub(r"[^\d.\-]", "", str(x["value"])) for ot in good_tabs if ot is not t
                          for x in ot if x["value"] and _numv.match(re.sub(r"[^\d.\-]", "", str(x["value"])))
                          and re.sub(r"[^\d.\-]", "", str(x["value"])) not in
                          {re.sub(r"[^\d.\-]", "", str(y['value'])) for y in t}), None)
            if other:
                cases.append(("cross_table_substitution", mk(rA, cA, other)))
            for cls, claim in cases:
                fin, reason, st = gate(claim)
                want = "RETURNED" if cls == "correct_cell" else "ABSTAINED"
                probes.append({"paper_id": pid[:10], "class": cls, "claim": claim,
                               "final": fin, "want": want, "reason": str(reason),
                               "binding_status": st, "WRONG": fin != want,
                               "FOOLED": fin == "RETURNED" and cls != "correct_cell"})

    (OUT / "binding_probes.json").write_text(json.dumps(probes, indent=2, default=str), encoding="utf-8")
    by_cls = defaultdict(Counter)
    for p in probes:
        by_cls[p["class"]][p["final"]] += 1
    print(f"  {'class':26} {'want':>9} {'n':>3} {'RETURNED':>9} {'ABSTAINED':>10}  {'WRONG':>6}")
    for cls in ("correct_cell", "correct_row_wrong_col", "correct_col_wrong_row",
                "cross_table_substitution"):
        c = by_cls.get(cls)
        if not c:
            print(f"  {cls:26} {'—':>9} {'0':>3}  (no probes constructed)")
            continue
        want = "RETURNED" if cls == "correct_cell" else "ABSTAINED"
        wrong = sum(1 for p in probes if p["class"] == cls and p["WRONG"])
        print(f"  {cls:26} {want:>9} {sum(c.values()):>3} {c.get('RETURNED', 0):>9} "
              f"{c.get('ABSTAINED', 0):>10}  {wrong:>6}")
    xrows = [p for p in probes if p["class"] == "correct_col_wrong_row" and p["FOOLED"]]
    print(f"\n  cross-row acceptances on structured papers: {len(xrows)}   (MUST be 0)")
    fooled = [p for p in probes if p["FOOLED"]]
    missed = [p for p in probes if p["class"] == "correct_cell" and p["final"] != "RETURNED"]
    print(f"  adversarial probes accepted (FOOLED): {len(fooled)}")
    for p in fooled:
        print(f"    FOOLED [{p['paper_id']}] {p['class']}: {p['claim']}  -> {p['reason']}")
    print(f"  correct_cell probes wrongly rejected: {len(missed)} / {by_cls['correct_cell'].get('RETURNED',0)+len(missed)}")
    for p in missed[:6]:
        print(f"    MISSED [{p['paper_id']}] bind={p['binding_status']} reason={p['reason']}  {p['claim'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
