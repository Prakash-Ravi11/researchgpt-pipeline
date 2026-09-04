"""Phase — arXiv LaTeX e-print as a structured representation. PARSE-SUCCESS REPORT ONLY
(no downstream measurement in this commit).

Staging only: reads the frozen canonical corpus metadata, takes its arXiv full-text
papers, and for each runs the real acquisition split —
  * e-print LaTeX  -> content / tables / section structure   (src.evidence.latex_source)
  * paired arXiv PDF -> identity (acquire.identity_validate)  + per-table fallback
then parses tables (src.evidence.represent.blocks_from_latex) and reports, per paper:
representation obtained, tables parsed / partial / fallen back, and why.

Isolated output: experiments/document_evidence_pipeline/runs/latex_acquisition/.
Production configs/ untouched. arXiv e-print requests are throttled to 1 / 3 s.

  python -u experiments/document_evidence_pipeline/latex_acquisition_report.py
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.evidence.acquire import fetch, content_validate, identity_validate  # noqa: E402
from src.evidence.latex_source import fetch_eprint_latex                     # noqa: E402
from src.evidence.represent import blocks_from_latex                         # noqa: E402

META = HERE / "runs" / "prodab-20260902T004416Z" / "canonical" / "raw_metadata" / "collected_papers.json"
OUT = HERE / "runs" / "latex_acquisition"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    papers = json.loads(META.read_text(encoding="utf-8"))
    arx = [p for p in papers if p.get("has_full_text")
           and (p.get("externalIds") or {}).get("ArXiv")]
    print(f"canonical arXiv full-text papers: {len(arx)}\n")

    rows = []
    for p in arx:
        pid = p["paperId"]
        aid = (p["externalIds"] or {})["ArXiv"]
        row = {"paper_id": pid[:12], "arxiv_id": aid, "title": (p.get("title") or "")[:60]}

        lx = fetch_eprint_latex(aid, fetch)
        pr = fetch(f"https://arxiv.org/pdf/{aid}.pdf")
        pdf_bytes = pr.get("body", b"") if pr.get("ok") else b""

        latex_bytes = lx.get("latex", "").encode("utf-8")
        content = (content_validate("latex", latex_bytes) if lx.get("ok")
                   else {"passed": False, "reason": lx.get("reason")})
        identity = (identity_validate(p, "pdf", pdf_bytes) if pdf_bytes
                    else {"passed": False, "reason": "no_paired_arxiv_pdf"})
        pdf_content = (content_validate("pdf", pdf_bytes) if pdf_bytes
                       else {"passed": False, "reason": "no_paired_arxiv_pdf"})

        accepted = bool(content["passed"] and identity["passed"] and pdf_content["passed"])
        row.update({
            "eprint_ok": lx.get("ok"), "eprint_reason": lx.get("reason"),
            "n_tex_files": lx.get("n_tex_files"), "latex_main": lx.get("main"),
            "latex_content_passed": content["passed"], "latex_content_reason": content.get("reason"),
            "identity_passed": identity["passed"], "identity_source": "arxiv_pdf",
            "identity_reason": identity.get("reason"),
            "paired_pdf_ok": pdf_content["passed"],
        })

        if accepted:
            blocks = blocks_from_latex(latex_bytes, pid, "arxiv_eprint", pdf_data=pdf_bytes)
            tbl = [b for b in blocks if b["block_type"] == "table"]
            st = Counter(b.get("table_parse_status") for b in tbl)
            fb_reasons = [b.get("table_fallback") for b in tbl
                          if b.get("table_parse_status") == "fallback_pdf"]
            partial_notes = [n for b in tbl for n in (b.get("table_notes") or [])
                             if b.get("table_parse_status") == "partial"]
            row.update({
                "representation_obtained": "latex",
                "n_blocks": len(blocks),
                "n_tables": len(tbl),
                "tables_parsed": st.get("parsed", 0),
                "tables_partial": st.get("partial", 0),
                "tables_fallback_pdf": st.get("fallback_pdf", 0),
                "total_structured_cells": sum(len(b.get("table_cells") or []) for b in tbl),
                "fallback_reasons": fb_reasons,
                "partial_notes": partial_notes,
            })
        else:
            row["representation_obtained"] = "pdf_fallback (LaTeX candidate rejected)"

        rows.append(row)
        tag = row["representation_obtained"]
        extra = (f"tables {row.get('tables_parsed',0)}p/{row.get('tables_partial',0)}part/"
                 f"{row.get('tables_fallback_pdf',0)}fb  cells={row.get('total_structured_cells',0)}"
                 if accepted else
                 f"latex_content={content.get('reason')} identity={identity.get('reason')}")
        print(f"  {row['paper_id']:14} {aid:12} {tag:38} {extra}")

    (OUT / "latex_acquisition_report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    got = [r for r in rows if r["representation_obtained"] == "latex"]
    print(f"\n== SUMMARY ({len(rows)} arXiv papers) ==")
    print(f"  LaTeX representation obtained: {len(got)} / {len(rows)}")
    print(f"  rejected -> PDF fallback:      {len(rows) - len(got)}")
    if got:
        tp = sum(r["tables_parsed"] for r in got)
        pa = sum(r["tables_partial"] for r in got)
        fb = sum(r["tables_fallback_pdf"] for r in got)
        print(f"  tables: {tp} parsed  +  {pa} partial  +  {fb} PDF-fallback  "
              f"(= {tp+pa+fb} total across {len(got)} papers)")
        print(f"  structured cells retained (value+col_header+row_label+caption+section): "
              f"{sum(r['total_structured_cells'] for r in got)}")
        rc = Counter(x.split(' -> ')[0] for r in got for x in r["fallback_reasons"])
        if rc:
            print(f"  fallback reasons: {dict(rc)}")
    print(f"\n  wrote {OUT / 'latex_acquisition_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
