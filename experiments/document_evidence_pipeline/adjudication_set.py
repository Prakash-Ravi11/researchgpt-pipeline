"""Adjudication set for the 14 movable claims — READ-ONLY.

Builds the ground-truth set that decides whether further work on binding is
worth doing. Reads only frozen artifacts; changes nothing.

  input : runs/parser_backend/results.json          (section 9)
          runs/parser_backend/results_hdrnorm.json  (experiment 2, treatment)
  output: runs/parser_backend/adjudication_14.json
          runs/parser_backend/adjudication_14.md

Cell population for LITERAL_MATCH is the hdrnorm TREATMENT set — the most
permissive produced so far — so the reported ceiling is a true upper bound.

    python -u experiments/document_evidence_pipeline/adjudication_set.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.evidence.anchors import NUMERIC_ANCHOR_RE as _NUMVAL          # noqa: E402

OUT = HERE / "runs" / "parser_backend"
S9 = OUT / "results.json"
HDR = OUT / "results_hdrnorm.json"

# ---- classification cues. Deliberately narrow: a form is assigned only on an
# explicit cue, otherwise UNCLEAR. Portuguese included because the corpus has a
# Portuguese paper (see report section 13.5).
_DERIVED = re.compile(
    r"\b(reduction|reduc\w*|redu[çc]\w*|increase|increment\w*|aumento|improvement|"
    r"improve\w*|melhor\w*|gain|speed[- ]?up|faster|slower|decrease|drop|"
    r"percentage point|pontos? percentuais|more than|mais de|less than|menos de|"
    r"up to|at[ée]|over|compared with cache|com uso de cache|change was)\b", re.I)
_COMPARATIVE = re.compile(
    r"\b(outperform\w*|superou|better than|worse than|competitive with|"
    r"compared (?:to|with)|versus|\bvs\.?\b|best config\w*|best|"
    r"underperform\w*|advantage|did not persist)\b", re.I)
_LITERAL = re.compile(
    r"\b(achiev\w*|scor\w*|obtained|reached|reports?|of)\b", re.I)

_PT = re.compile(r"\b(de|da|do|com|uso|etapa|mais|na|em|para|foi|teve|que|dos|das)\b", re.I)
_EN = re.compile(r"\b(the|of|with|and|was|were|on|in|for|showed|test|using)\b", re.I)

_OURS = re.compile(r"\b(ours?|our|proposed|nosso|nossa|this work|full model)\b|\(ours\)", re.I)
_MODELISH = re.compile(
    r"\b(gpt|llama|bert|roberta|mistral|gemini|claude|t5|xlnet|electra|deberta|"
    r"qwen|falcon|phi|command|minilm)\b|\b[a-z]+-?\d+(\.\d+)?[a-z]?\b", re.I)


def _fail(msg: str) -> None:
    print(f"\nSTOP: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _norm_num(s: str) -> str:
    return re.sub(r"[^\d.\-]", "", str(s))


def _infer_language(text: str) -> str:
    """INFERRED ONLY — a stopword count, never presented as detection."""
    pt, en = len(_PT.findall(text)), len(_EN.findall(text))
    if pt >= 3 and pt > en:
        return "pt (INFERRED)"
    if en >= 3 and en > pt:
        return "en (INFERRED)"
    return "UNKNOWN"


def _claim_form(text: str) -> str:
    """Mechanical, cue-driven. UNCLEAR unless a cue is explicit."""
    d, c = bool(_DERIVED.search(text)), bool(_COMPARATIVE.search(text))
    if d:
        return "DERIVED"          # the NUMBER is a delta/ratio/change
    if c:
        return "COMPARATIVE"      # the ASSERTION is an ordering
    if _LITERAL.search(text):
        return "LITERAL"
    return "UNCLEAR"


def _own_row_evidence(row_labels: list[str]) -> str:
    """Evidence present in the paper's row labels. NOT an ownership decision."""
    if not row_labels:
        return "NA"
    if any(_OURS.search(r or "") for r in row_labels):
        return "OURS_MARKER"
    if any(_MODELISH.search(r or "") for r in row_labels):
        return "MODEL_NAME"
    return "NONE"


def main() -> int:
    for p in (S9, HDR):
        if not p.exists():
            _fail(f"missing frozen artifact: {p}")
    s9 = json.loads(S9.read_text(encoding="utf-8"))
    hd = json.loads(HDR.read_text(encoding="utf-8"))
    ids = hd["papers"]
    ctrl_current = s9["results"]["current"]
    treat = hd["treatment"]

    # ---- RECONCILIATION (addition 1) -------------------------------------
    movable = {(p, c["field"], c["value"])
               for p in ids for c in (ctrl_current[p].get("claims") or [])
               if c["binding_status"] == "pdf_only"}
    in_treat = {(p, c["field"], c["value"])
                for p in ids for c in (treat[p].get("claims") or [])
                if c["binding_status"] != "no_binding_call"}
    print("== reconciliation ==")
    print(f"  movable claims in section-9 `current` arm (pdf_only) : {len(movable)}")
    print(f"  non-`no_binding_call` claims in hdrnorm treatment     : {len(in_treat)}")
    if len(movable) != 14:
        _fail(f"expected exactly 14 movable claims, found {len(movable)}")
    if movable != in_treat:
        only_a, only_b = movable - in_treat, in_treat - movable
        print("\nFINDING: claim-key drift between artifacts", file=sys.stderr)
        for k in sorted(only_a):
            print(f"  only in section-9 movable set: {k[0][:12]} [{k[1]}] {k[2][:70]!r}", file=sys.stderr)
        for k in sorted(only_b):
            print(f"  only in hdrnorm treatment    : {k[0][:12]} [{k[1]}] {k[2][:70]!r}", file=sys.stderr)
        _fail("claim (field, value) keys do not match across the two artifacts")
    print("  keys match exactly on (paper_id, field, value): OK\n")

    # ---- cell population (addition 2) ------------------------------------
    # The frozen artifacts record per-table cell COUNTS, headers and row labels,
    # but never the individual cell VALUES, so LITERAL_MATCH cannot be computed
    # from them alone. The brief permits the canonical corpus as a source, so the
    # cells are re-derived from it under the EXACT hdrnorm treatment
    # configuration (deterministic), one paper per process because pymupdf4llm
    # poisons find_tables for the rest of a process.
    #
    # INTEGRITY CHECK: the re-derived per-paper cell count must equal the count
    # the frozen artifact recorded. A mismatch means these are not the treatment
    # cells, and is reported as a finding rather than used.
    need = sorted({p for p in ids
                   for c in (treat[p].get("claims") or [])
                   if c["binding_status"] != "no_binding_call"
                   and treat[p].get("n_cells")})
    print("== re-deriving treatment cells from the canonical corpus ==")
    print(f"  papers needing cells: {len(need)} (one process each)")
    cells_by_paper: dict[str, list[dict]] = {p: [] for p in ids}
    for pid in need:
        got = _spawn_cells(pid)
        expect = treat[pid].get("n_cells") or 0
        ok = len(got) == expect
        print(f"  {pid[:12]}  re-derived {len(got):>4}  artifact {expect:>4}  "
              f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            _fail(f"cell-count mismatch for {pid}: re-derived {len(got)}, "
                  f"artifact records {expect}. These are not the treatment cells.")
        cells_by_paper[pid] = got
    print()
    return _emit(ids, ctrl_current, treat, cells_by_paper, True, hd)


def _spawn_cells(paper_id: str) -> list[dict]:
    """One isolated process: re-derive this paper's treatment cells."""
    import os
    import subprocess
    r = subprocess.run(
        [sys.executable, "-u", str(Path(__file__).resolve()), "--cells-worker",
         "--paper", paper_id],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if "@@CELLS@@" not in r.stdout:
        _fail(f"cell worker failed for {paper_id}: {(r.stderr or '')[-500:]}")
    return json.loads(r.stdout.split("@@CELLS@@", 1)[1].strip())


def _cells_worker(paper_id: str) -> int:
    """Re-derive one paper's cells under the hdrnorm treatment configuration.
    PDFS is imported from the measurement harness so the corpus path is the one
    that run used; nothing is written."""
    from parser_backend_measure import PDFS
    from src.evidence.represent_layout import blocks_from_pdf_layout
    blocks = blocks_from_pdf_layout((PDFS / f"{paper_id}.pdf").read_bytes(),
                                    paper_id, "canonical", "pymupdf4llm",
                                    collapse_header_ws=True)
    cells = [c for b in blocks if b["block_type"] == "table"
             for c in (b.get("table_cells") or [])]
    print("@@CELLS@@")
    print(json.dumps(cells, default=str))
    return 0


def _emit(ids, ctrl_current, treat, cells_by_paper, have_cells, hd) -> int:
    n_cells_tot = sum(t.get("n_cells", 0) for p in ids for t in (treat[p].get("tables") or []))
    n_tab_tot = sum(1 for p in ids for t in (treat[p].get("tables") or []) if t.get("n_cells", 0) > 0)
    print("== cell population for LITERAL_MATCH ==")
    print(f"  source     : hdrnorm TREATMENT arm (most permissive produced so far)")
    print(f"  cells      : {n_cells_tot}   tables with cells: {n_tab_tot}")
    if not have_cells:
        print("  NOTE: the frozen artifacts record per-table COUNTS and headers/row")
        print("        labels, but not individual cell VALUES. LITERAL_MATCH therefore")
        print("        cannot be computed from the artifacts alone — see report.")
    print()

    rows = []
    for p in ids:
        for c in (treat[p].get("claims") or []):
            if c["binding_status"] == "no_binding_call":
                continue
            base = next((x for x in (ctrl_current[p].get("claims") or [])
                         if (x["field"], x["value"]) == (c["field"], c["value"])), None)
            text = c["value"]
            nums = _NUMVAL.findall(text or "")
            paper_cells = cells_by_paper.get(p) or []
            row_labels = sorted({t for t in
                                 (lbl for tb in (treat[p].get("tables") or [])
                                  for lbl in (tb.get("row_labels") or []))})
            cells_available = bool(treat[p].get("n_cells"))
            if not cells_available:
                lit, hit = "NA", None
            elif not paper_cells:
                lit, hit = "UNCOMPUTABLE", None
            else:
                hit = next((cell for cell in paper_cells
                            for n in nums if _norm_num(cell.get("value")) == n), None)
                lit = bool(hit)
            rows.append({
                "paper_id": p, "field": c["field"], "claim_text": text,
                "language": _infer_language(text),
                "status_section9_current": base["binding_status"] if base else "ABSENT",
                "status_hdrnorm_treatment": c["binding_status"],
                "final": c["final"], "abstain_reason": c["abstain_reason"],
                "numbers_NUMVAL": nums,
                "cells_available_in_paper": cells_available,
                "LITERAL_MATCH": lit,
                "matching_cell": ({"row_label": hit.get("row_label"),
                                   "column_header": hit.get("column_header"),
                                   "caption": hit.get("caption"),
                                   "value": hit.get("value")} if isinstance(hit, dict) else None),
                "claim_form": _claim_form(text),
                "own_row_evidence": _own_row_evidence(row_labels),
            })

    lit_true = sum(1 for r in rows if r["LITERAL_MATCH"] is True)
    lit_na = sum(1 for r in rows if r["LITERAL_MATCH"] == "NA")
    lit_unc = sum(1 for r in rows if r["LITERAL_MATCH"] == "UNCOMPUTABLE")
    forms = Counter(r["claim_form"] for r in rows)

    payload = {
        "n_claims": len(rows),
        "cell_population": {"source": "results_hdrnorm.json treatment arm",
                            "cells": n_cells_tot, "tables_with_cells": n_tab_tot,
                            "cell_values_available_in_artifact": have_cells},
        "headline": {
            "LITERAL_MATCH_true": lit_true, "LITERAL_MATCH_false":
                sum(1 for r in rows if r["LITERAL_MATCH"] is False),
            "LITERAL_MATCH_NA_no_cells": lit_na,
            "LITERAL_MATCH_UNCOMPUTABLE": lit_unc,
            "claim_form_DERIVED": forms.get("DERIVED", 0),
            "claim_form_UNCLEAR": forms.get("UNCLEAR", 0),
            "claim_form_LITERAL": forms.get("LITERAL", 0),
            "claim_form_COMPARATIVE": forms.get("COMPARATIVE", 0),
        },
        "claims": rows,
    }
    (OUT / "adjudication_14.json").write_text(json.dumps(payload, indent=2, default=str),
                                              encoding="utf-8")
    _markdown(payload)

    print("== headline counts ==")
    print(f"  LITERAL_MATCH true      = {lit_true} of {len(rows)}"
          f"   <- ceiling on cell-literal binding")
    if lit_na or lit_unc:
        print(f"     (NA, no cells in paper = {lit_na};  UNCOMPUTABLE = {lit_unc})")
    print(f"  claim_form DERIVED      = {forms.get('DERIVED', 0)} of {len(rows)}"
          f"   <- unreachable without derived binding")
    print(f"  claim_form UNCLEAR      = {forms.get('UNCLEAR', 0)} of {len(rows)}"
          f"   <- needs adjudication")
    print(f"  (also LITERAL={forms.get('LITERAL', 0)}, COMPARATIVE={forms.get('COMPARATIVE', 0)})")
    print(f"\nwrote {OUT / 'adjudication_14.json'} and adjudication_14.md")
    return 0


def _markdown(payload) -> None:
    L = ["# Adjudication set — the 14 movable claims", "",
         f"Cell population: **{payload['cell_population']['source']}** — "
         f"{payload['cell_population']['cells']} cells across "
         f"{payload['cell_population']['tables_with_cells']} tables "
         f"(most permissive produced so far, so the ceiling is a true upper bound).", "",
         f"Cell VALUES present in the frozen artifact: "
         f"**{payload['cell_population']['cell_values_available_in_artifact']}**", "",
         "## Headline", "",
         f"- `LITERAL_MATCH` true — **{payload['headline']['LITERAL_MATCH_true']} of "
         f"{payload['n_claims']}** — ceiling on cell-literal binding",
         f"- `claim_form` DERIVED — **{payload['headline']['claim_form_DERIVED']} of "
         f"{payload['n_claims']}** — unreachable without derived binding",
         f"- `claim_form` UNCLEAR — **{payload['headline']['claim_form_UNCLEAR']} of "
         f"{payload['n_claims']}** — needs adjudication", "",
         "## Claims", ""]
    for i, r in enumerate(payload["claims"], 1):
        L += [f"### {i}. `{r['paper_id'][:12]}` · {r['field']}", "",
              f"> {r['claim_text']}", "",
              f"| field | value |", "|---|---|",
              f"| language | {r['language']} |",
              f"| status (section 9 `current`) | `{r['status_section9_current']}` |",
              f"| status (hdrnorm treatment) | `{r['status_hdrnorm_treatment']}` |",
              f"| final / reason | {r['final']} / `{r['abstain_reason']}` |",
              f"| numbers (`_NUMVAL`) | `{r['numbers_NUMVAL']}` |",
              f"| cells available in paper | {r['cells_available_in_paper']} |",
              f"| **LITERAL_MATCH** | **{r['LITERAL_MATCH']}** |",
              f"| matching cell | {r['matching_cell'] or '—'} |",
              f"| **claim_form** | **{r['claim_form']}** |",
              f"| own_row_evidence | {r['own_row_evidence']} |", ""]
    (OUT / "adjudication_14.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    sys.path.insert(0, str(HERE))          # for the cell worker's PDFS import
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells-worker", action="store_true")
    ap.add_argument("--paper")
    a = ap.parse_args()
    raise SystemExit(_cells_worker(a.paper) if a.cells_worker else main())
