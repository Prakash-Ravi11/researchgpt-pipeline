"""Adjudication set for the 14 movable claims — READ-ONLY.

Builds the ground-truth set that decides whether further work on binding is
worth doing. Reads frozen artifacts plus the canonical corpus; changes nothing.

  input : runs/parser_backend/results.json          (section 9)
          runs/parser_backend/results_hdrnorm.json  (experiment 2, treatment)
          the canonical corpus (cell VALUES are not in the artifacts)
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
ADJ = OUT / "adjudication_14.json"

# ---- claim_form, CORRECTED SEMANTICS --------------------------------------
# claim_form describes how the claimed NUMBER is represented in the available
# evidence, NOT how the sentence is phrased. Words like "best", "improvement",
# "reduction" or "faster" never by themselves establish DERIVED.
#
#   LITERAL      the claimed number is explicitly present as a cell value
#   DERIVED      not printed, but mechanically calculable from actual cells
#                (derivation recorded; unsupportable -> UNCLEAR)
#   COMPARATIVE  asserts a relation and cannot be reduced to one numerical
#                derivation from the available evidence
#   UNCLEAR      no defensible classification
#
# Papers with no cells cannot be adjudicated mechanically; those are classified
# from claim text alone and marked TEXT_ONLY (amendment to section 5).

# Text-only cues, used ONLY for the no-cell papers.
_TXT_DELTA = re.compile(
    r"\b(reduction|reduc\w*|redu[cz]\w*|increase|aumento|improvement|improve\w*|"
    r"melhor\w*|gain|speed[- ]?up|faster|slower|decrease|drop|"
    r"percentage point|pontos? percentuais)\b", re.I)
_TXT_METRIC_VALUE = re.compile(
    r"\b(accuracy|precision|recall|f1|f-score|dice|iou|auc|bleu|rouge|mae|rmse|"
    r"perplexity|ndcg|map|exact match|score|rate|error|latency)\b", re.I)
_TXT_RELATION = re.compile(
    r"\b(outperform\w*|superou|better than|worse than|competitive with|"
    r"compared (?:to|with)|versus|vs\.?|underperform\w*|"
    r"significativamente menor|mais de|more than|less than)\b", re.I)

_PT = re.compile(r"\b(de|da|do|com|uso|etapa|mais|na|em|para|foi|teve|que|dos|das)\b", re.I)
_EN = re.compile(r"\b(the|of|with|and|was|were|on|in|for|showed|test|using)\b", re.I)

_OURS = re.compile(r"\b(ours?|our|proposed|nosso|nossa|this work|full model)\b", re.I)
_MODELISH = re.compile(
    r"\b(gpt|llama|bert|roberta|mistral|gemini|claude|t5|xlnet|electra|deberta|"
    r"qwen|falcon|phi|command|minilm)\b", re.I)

# One clean number per cell, or nothing. A cell like '[-10.2, 1.9]' or
# 'US$ 0,10 / 1M tokens' holds two numbers and is rejected rather than guessed at.
_NUMTOK = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
# Derivation tolerances, fixed and reported. Percentage-valued operations get one
# percentage point, because these claims are explicitly approximate
# ("aproximadamente", "cerca de"); everything else gets 1% or 0.01, whichever is
# larger.
_PCT_TOL = 1.0


def _fail(msg: str) -> None:
    print(f"\nSTOP: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _norm_num(s: str) -> str:
    """FROZEN — the section-9 literal-match normalisation. Do not change."""
    return re.sub(r"[^\d.\-]", "", str(s))


_MAX_RESIDUAL_ALPHA = 2     # enough for a unit like "ms", "pp", "s"


def _single_number(value: str) -> float | None:
    """A cell that IS a number, not a cell that merely contains one.

    Requires exactly one numeric token AND numeric dominance: after removing the
    number, markdown and punctuation, at most a unit's worth of letters may
    remain. Without this, prose cells like '20 tokens por requisicao' or
    'RAG (k = 1)' parse as measurements and manufacture false derivations —
    e.g. (35 ms - 20 tokens) / 20 tokens * 100 = 75.0, an exact numeric match
    to a claim about latency that means nothing.
    """
    txt = re.sub(r"[*_~$%]", " ", str(value or ""))
    toks = _NUMTOK.findall(txt)
    if len(toks) != 1:
        return None
    residual = re.sub(r"[^A-Za-z]", "", txt.replace(toks[0], " ", 1))
    if len(residual) > _MAX_RESIDUAL_ALPHA:
        return None
    try:
        return float(toks[0].replace(",", "."))
    except ValueError:
        return None


def _signed_claim_numbers(text: str, nums: list[str]) -> list[str]:
    """The claim's numbers as the SENTENCE writes them, sign included.

    _NUMVAL does not capture a leading '-', so "the accuracy change was -4.1
    points" yields '4.1'. LITERAL_MATCH is frozen and keeps the unsigned form;
    claim_form asks whether the claimed number is *explicitly present* in a cell,
    so it must see the sign the sentence actually wrote.
    """
    out = []
    for n in nums:
        out.append(n)
        for m in re.finditer(re.escape(n), text or ""):
            if (text or "")[max(0, m.start() - 1):m.start()] == "-":
                out.append("-" + n)
    return out


def _cell_numbers(cells: list[dict]) -> list[tuple[dict, float]]:
    out = []
    for c in cells:
        v = _single_number(c.get("value"))
        if v is not None:
            out.append((c, v))
    return out


def _literal_cell(nums_signed: list[str], cells: list[dict]) -> dict | None:
    for c in cells:
        v = _single_number(c.get("value"))
        if v is None:
            continue
        for n in nums_signed:
            try:
                if abs(v - float(n)) < 1e-9:
                    return c
            except ValueError:
                continue
    return None


def _find_derivations(nums: list[str], cells: list[dict]) -> list[dict]:
    """Mechanically supportable derivations of a claimed number from real cells.

    Pairs are restricted to cells sharing a row label or a column header — a
    derivation across unrelated cells is not defensible. Sums over a whole
    column are NOT searched; that is stated rather than silently assumed.
    """
    numeric = _cell_numbers(cells)
    targets = []
    for n in nums:
        try:
            targets.append((n, float(n)))
        except ValueError:
            pass
    found: list[dict] = []

    def _rec(n, op, result, src):
        found.append({"claimed": n, "operation": op, "result": round(result, 4),
                      "abs_error": round(abs(result - float(n)), 4),
                      "source_cells": [{"row_label": c.get("row_label"),
                                        "column_header": c.get("column_header"),
                                        "value": c.get("value")} for c in src]})

    for n, tgt in targets:
        for c, v in numeric:                       # single-cell unit conversion
            for op, res in ((f"{v} / 100", v / 100.0), (f"{v} * 100", v * 100.0)):
                if abs(res - tgt) <= max(0.01, abs(tgt) * 0.01):
                    _rec(n, f"unit_conversion: {op}", res, [c])
        for i, (ca, a) in enumerate(numeric):      # ordered pairs, same row/col
            for j, (cb, b) in enumerate(numeric):
                if i == j or a == 0:
                    continue
                if not ((ca.get("row_label") or "") == (cb.get("row_label") or "")
                        or (ca.get("column_header") or "") == (cb.get("column_header") or "")):
                    continue
                for op, res, is_pct in (
                        (f"pct_decrease: ({a} - {b}) / {a} * 100", (a - b) / a * 100.0, True),
                        (f"pct_increase: ({b} - {a}) / {a} * 100", (b - a) / a * 100.0, True),
                        (f"ratio_pct: {a} / {b} * 100", (a / b * 100.0) if b else None, True),
                        (f"difference: {a} - {b}", a - b, False)):
                    if res is None:
                        continue
                    tol = _PCT_TOL if is_pct else max(0.01, abs(tgt) * 0.01)
                    if abs(res - tgt) <= tol:
                        _rec(n, op, res, [ca, cb])
    found.sort(key=lambda d: d["abs_error"])
    # Dedupe: the same derivation can surface twice via symmetric operations.
    seen, uniq = set(), []
    for f in found:
        k = (tuple(sorted((c["row_label"], c["column_header"], c["value"])
                          for c in f["source_cells"])), round(f["result"], 2))
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


_TXT_ADJACENCY = 15     # chars between a metric term and its number


def _number_attached_to_metric(text: str) -> bool:
    """A metric term with a number ACTUALLY ATTACHED to it.

    Co-presence is not enough: "low-latency inference ... passed 20 privacy
    tests" mentions a metric word and a number, but the number counts tests, not
    a metric value. Requiring adjacency stops that being called LITERAL.
    """
    for m in _TXT_METRIC_VALUE.finditer(text or ""):
        lo = max(0, m.start() - _TXT_ADJACENCY)
        window = (text or "")[lo:m.end() + _TXT_ADJACENCY]
        if re.search(r"\d", window):
            return True
    return False


def _claim_form_text_only(text: str) -> str:
    """Amendment to section 5: no cells exist, so classify from text alone."""
    if _TXT_DELTA.search(text):
        return "DERIVED"
    if _number_attached_to_metric(text):
        return "LITERAL"
    if _TXT_RELATION.search(text):
        return "COMPARATIVE"
    return "UNCLEAR"


def _adjudicate(text: str, nums: list[str], cells: list[dict],
                cells_available: bool) -> dict:
    """Corrected claim_form. LITERAL_MATCH is neither consulted nor changed."""
    if not cells_available:
        return {"claim_form": _claim_form_text_only(text),
                "claim_form_confidence": "TEXT_ONLY",
                "claim_form_basis": "claim text only (paper has no cells)",
                "derivation_evidence": "NA_NO_CELLS",
                "ambiguous_derivation": False}
    lit = _literal_cell(_signed_claim_numbers(text, nums), cells)
    if lit is not None:
        return {"claim_form": "LITERAL", "claim_form_confidence": "MECHANICAL",
                "claim_form_basis": "claimed number explicitly present as a cell value",
                "derivation_evidence": {"literal_cell": {
                    "row_label": lit.get("row_label"),
                    "column_header": lit.get("column_header"),
                    "value": lit.get("value"), "caption": lit.get("caption")}},
                "ambiguous_derivation": False}
    ders = _find_derivations(nums, cells)
    if len(ders) == 1:
        return {"claim_form": "DERIVED", "claim_form_confidence": "MECHANICAL",
                "claim_form_basis": f"uniquely derivable from cells (tolerance "
                                    f"{_PCT_TOL} pp for percentage operations)",
                "derivation_evidence": {"primary": ders[0], "n_candidates": 1,
                                        "all_candidates": ders},
                "ambiguous_derivation": False}
    if len(ders) > 1:
        # Section 5: more than one arithmetically valid derivation means the
        # derivation has NOT been established, so this is UNCLEAR, not DERIVED.
        return {"claim_form": "UNCLEAR", "claim_form_confidence": "MECHANICAL",
                "claim_form_basis": f"{len(ders)} competing derivations fit the "
                                    f"claimed number; none is established",
                "derivation_evidence": {"competing_candidates": ders[:6],
                                        "n_candidates": len(ders)},
                "ambiguous_derivation": True}
    if _TXT_RELATION.search(text):
        return {"claim_form": "COMPARATIVE", "claim_form_confidence": "MECHANICAL",
                "claim_form_basis": "asserts a relation; no single numerical "
                                    "derivation from the available cells",
                "derivation_evidence": None, "ambiguous_derivation": False}
    return {"claim_form": "UNCLEAR", "claim_form_confidence": "MECHANICAL",
            "claim_form_basis": "not printed in a cell and no mechanically "
                                "supportable derivation from the available cells",
            "derivation_evidence": None, "ambiguous_derivation": False}


def _infer_language(text: str) -> str:
    """INFERRED ONLY — a stopword count, never presented as detection."""
    pt, en = len(_PT.findall(text)), len(_EN.findall(text))
    if pt >= 3 and pt > en:
        return "pt (INFERRED)"
    if en >= 3 and en > pt:
        return "en (INFERRED)"
    return "UNKNOWN"


def _own_row_evidence(row_labels: list[str]) -> str:
    """Paper-level evidence in row labels. NOT an ownership decision."""
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
    prev = json.loads(ADJ.read_text(encoding="utf-8")) if ADJ.exists() else None
    s9 = json.loads(S9.read_text(encoding="utf-8"))
    hd = json.loads(HDR.read_text(encoding="utf-8"))
    ids = hd["papers"]
    ctrl_current = s9["results"]["current"]
    treat = hd["treatment"]

    # ---- RECONCILIATION --------------------------------------------------
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
        _fail("claim (field, value) keys do not match across the two artifacts")
    print("  keys match exactly on (paper_id, field, value): OK\n")

    # ---- cell population -------------------------------------------------
    # The frozen artifacts record per-table cell COUNTS, headers and row labels,
    # but never the individual cell VALUES, so LITERAL_MATCH is not computable
    # from them alone. The corpus is permitted, so cells are re-derived under the
    # EXACT hdrnorm treatment configuration, one paper per process because
    # pymupdf4llm poisons find_tables for the rest of a process.
    #
    # INTEGRITY CHECK: each re-derived per-paper cell count must equal the count
    # the frozen artifact recorded, or the run stops.
    need = sorted({p for p in ids for c in (treat[p].get("claims") or [])
                   if c["binding_status"] != "no_binding_call" and treat[p].get("n_cells")})
    print("== re-deriving treatment cells from the canonical corpus ==")
    print(f"  papers needing cells: {len(need)} (one process each)")
    cells_by_paper: dict[str, list[dict]] = {p: [] for p in ids}
    for pid in need:
        got = _spawn_cells(pid)
        expect = treat[pid].get("n_cells") or 0
        print(f"  {pid[:12]}  re-derived {len(got):>4}  artifact {expect:>4}  "
              f"{'OK' if len(got) == expect else 'MISMATCH'}")
        if len(got) != expect:
            _fail(f"cell-count mismatch for {pid}: re-derived {len(got)}, artifact "
                  f"records {expect}. These are not the treatment cells.")
        cells_by_paper[pid] = got
    print()
    return _emit(ids, ctrl_current, treat, cells_by_paper, prev)


def _spawn_cells(paper_id: str) -> list[dict]:
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
    PDFS comes from the measurement harness so the corpus path is the one that
    run used. Nothing is written."""
    from parser_backend_measure import PDFS
    from src.evidence.represent_layout import blocks_from_pdf_layout
    blocks = blocks_from_pdf_layout((PDFS / f"{paper_id}.pdf").read_bytes(),
                                    paper_id, "canonical", "pymupdf4llm",
                                    collapse_header_ws=True)
    print("@@CELLS@@")
    print(json.dumps([c for b in blocks if b["block_type"] == "table"
                      for c in (b.get("table_cells") or [])], default=str))
    return 0


def _emit(ids, ctrl_current, treat, cells_by_paper, prev) -> int:
    n_cells_tot = sum(t.get("n_cells", 0) for p in ids for t in (treat[p].get("tables") or []))
    n_tab_tot = sum(1 for p in ids for t in (treat[p].get("tables") or [])
                    if t.get("n_cells", 0) > 0)
    print("== cell population for LITERAL_MATCH ==")
    print(f"  source: hdrnorm TREATMENT arm (most permissive produced so far)")
    print(f"  cells : {n_cells_tot}   tables with cells: {n_tab_tot}\n")

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
            row_labels = sorted({lbl for tb in (treat[p].get("tables") or [])
                                 for lbl in (tb.get("row_labels") or [])})
            cells_available = bool(treat[p].get("n_cells"))

            # ---- LITERAL_MATCH: FROZEN rule, unchanged -------------------
            if not cells_available:
                lit, hit = "NA", None
            else:
                hit = next((cell for cell in paper_cells
                            for n in nums if _norm_num(cell.get("value")) == n), None)
                lit = bool(hit)

            adj = _adjudicate(text, nums, paper_cells, cells_available)
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
                "own_row_evidence": _own_row_evidence(row_labels),
                **adj,
            })

    forms = Counter(r["claim_form"] for r in rows)
    lit_t = sum(1 for r in rows if r["LITERAL_MATCH"] is True)
    lit_f = sum(1 for r in rows if r["LITERAL_MATCH"] is False)
    lit_na = sum(1 for r in rows if r["LITERAL_MATCH"] == "NA")
    text_only = sum(1 for r in rows if r["claim_form_confidence"] == "TEXT_ONLY")

    payload = {
        "n_claims": len(rows),
        "claim_form_semantics": "CORRECTED: describes how the claimed NUMBER is "
                                "represented in the evidence, not the sentence's wording",
        "derivation_tolerance": {"percentage_operations_pp": _PCT_TOL,
                                 "other_operations": "max(0.01, 1% of claimed)",
                                 "column_sums_searched": False,
                                 "pairs_restricted_to": "same row_label or same column_header"},
        "cell_population": {"source": "results_hdrnorm.json treatment arm",
                            "cells": n_cells_tot, "tables_with_cells": n_tab_tot},
        "headline": {
            "LITERAL_MATCH_true": lit_t, "LITERAL_MATCH_false": lit_f,
            "LITERAL_MATCH_NA": lit_na,
            "claim_form_LITERAL": forms.get("LITERAL", 0),
            "claim_form_DERIVED": forms.get("DERIVED", 0),
            "claim_form_COMPARATIVE": forms.get("COMPARATIVE", 0),
            "claim_form_UNCLEAR": forms.get("UNCLEAR", 0),
            "claim_form_TEXT_ONLY_not_mechanically_adjudicated": text_only,
        },
        "claims": rows,
    }
    ADJ.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _markdown(payload)

    print("== headline counts ==")
    h = payload["headline"]
    print(f"  LITERAL_MATCH true  = {h['LITERAL_MATCH_true']}/14")
    print(f"  LITERAL_MATCH false = {h['LITERAL_MATCH_false']}/14")
    print(f"  LITERAL_MATCH NA    = {h['LITERAL_MATCH_NA']}/14")
    print(f"  claim_form LITERAL     = {h['claim_form_LITERAL']}/14")
    print(f"  claim_form DERIVED     = {h['claim_form_DERIVED']}/14")
    print(f"  claim_form COMPARATIVE = {h['claim_form_COMPARATIVE']}/14")
    print(f"  claim_form UNCLEAR     = {h['claim_form_UNCLEAR']}/14")
    print(f"  of which TEXT_ONLY (never mechanically adjudicated) = {text_only}/14")

    return _validate(rows, prev)


def _validate(rows, prev) -> int:
    print("\n== validation ==")
    ok = True

    def chk(label, cond):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'OK  ' if cond else 'FAIL'} {label}")

    chk("exactly 14 claims", len(rows) == 14)
    if prev is None:
        print("  SKIP no previous adjudication artifact to compare against")
    else:
        pk = {(r["paper_id"], r["field"], r["claim_text"]) for r in prev["claims"]}
        nk = {(r["paper_id"], r["field"], r["claim_text"]) for r in rows}
        chk("same (paper_id, field, value) keys as before", pk == nk)
        pl = {(r["paper_id"], r["claim_text"]): r["LITERAL_MATCH"] for r in prev["claims"]}
        nl = {(r["paper_id"], r["claim_text"]): r["LITERAL_MATCH"] for r in rows}
        chk("LITERAL_MATCH values unchanged", pl == nl)
        pn = {(r["paper_id"], r["claim_text"]): r["numbers_NUMVAL"] for r in prev["claims"]}
        nn = {(r["paper_id"], r["claim_text"]): r["numbers_NUMVAL"] for r in rows}
        chk("extracted numbers unchanged", pn == nn)
        chk("cell population unchanged",
            prev["cell_population"]["cells"] == 2199
            and prev["cell_population"]["tables_with_cells"] == 93)
        changed = [(r["paper_id"], r["claim_text"],
                    next(q["claim_form"] for q in prev["claims"]
                         if (q["paper_id"], q["claim_text"]) == (r["paper_id"], r["claim_text"])),
                    r["claim_form"]) for r in rows]
        changed = [c for c in changed if c[2] != c[3]]
        print(f"  ---- claim_form changed on {len(changed)} of 14 records ----")
        for pid, txt, a, b in changed:
            print(f"       {pid[:12]} {a} -> {b}   {txt[:66]!r}")
    chk("all DERIVED have mechanically supportable evidence",
        all(isinstance(r["derivation_evidence"], dict) and "primary" in r["derivation_evidence"]
            for r in rows if r["claim_form"] == "DERIVED"
            and r["claim_form_confidence"] == "MECHANICAL"))
    chk("all no-cell claims are NA + TEXT_ONLY + NA_NO_CELLS",
        all(r["LITERAL_MATCH"] == "NA" and r["claim_form_confidence"] == "TEXT_ONLY"
            and r["derivation_evidence"] == "NA_NO_CELLS"
            for r in rows if not r["cells_available_in_paper"]))
    chk("5 no-cell claims remain LITERAL_MATCH = NA",
        sum(1 for r in rows if r["LITERAL_MATCH"] == "NA") == 5)
    print(f"\n  {'ALL VALIDATION CHECKS PASS' if ok else 'VALIDATION FAILED'}")
    return 0 if ok else 1


def _markdown(payload) -> None:
    h = payload["headline"]
    L = ["# Adjudication set — the 14 movable claims", "",
         "`claim_form` semantics: **CORRECTED** — describes how the claimed NUMBER is",
         "represented in the available evidence, not how the sentence is phrased.", "",
         f"Cell population: **{payload['cell_population']['source']}** — "
         f"{payload['cell_population']['cells']} cells across "
         f"{payload['cell_population']['tables_with_cells']} tables "
         f"(most permissive produced so far, so the ceiling is a true upper bound).", "",
         f"Derivation search: pairs restricted to same row label or same column header; "
         f"tolerance {payload['derivation_tolerance']['percentage_operations_pp']} pp for "
         f"percentage operations; column sums NOT searched.", "",
         "## Headline", "",
         f"| count | of 14 |", "|---|---|",
         f"| `LITERAL_MATCH` true | **{h['LITERAL_MATCH_true']}** |",
         f"| `LITERAL_MATCH` false | {h['LITERAL_MATCH_false']} |",
         f"| `LITERAL_MATCH` NA | {h['LITERAL_MATCH_NA']} |",
         f"| `claim_form` LITERAL | **{h['claim_form_LITERAL']}** |",
         f"| `claim_form` DERIVED | **{h['claim_form_DERIVED']}** |",
         f"| `claim_form` COMPARATIVE | {h['claim_form_COMPARATIVE']} |",
         f"| `claim_form` UNCLEAR | {h['claim_form_UNCLEAR']} |",
         f"| of which TEXT_ONLY, never mechanically adjudicated | "
         f"{h['claim_form_TEXT_ONLY_not_mechanically_adjudicated']} |", "",
         "## Claims", ""]
    for i, r in enumerate(payload["claims"], 1):
        de = r["derivation_evidence"]
        if isinstance(de, dict) and "primary" in de:
            d = de["primary"]
            dtxt = (f"`{d['operation']}` = {d['result']} (claimed {d['claimed']}, "
                    f"abs err {d['abs_error']}) from "
                    + "; ".join(f"[{c['row_label']} × {c['column_header']} = {c['value']}]"
                                for c in d["source_cells"])
                    + (f" — {de['n_candidates']} candidate(s)" if de.get("n_candidates") else ""))
        elif isinstance(de, dict) and "literal_cell" in de:
            c = de["literal_cell"]
            dtxt = f"cell [{c['row_label']} × {c['column_header']} = {c['value']}]"
        else:
            dtxt = str(de) if de else "—"
        L += [f"### {i}. `{r['paper_id'][:12]}` · {r['field']}", "",
              f"> {r['claim_text']}", "",
              "| field | value |", "|---|---|",
              f"| language | {r['language']} |",
              f"| status (section 9 `current`) | `{r['status_section9_current']}` |",
              f"| status (hdrnorm treatment) | `{r['status_hdrnorm_treatment']}` |",
              f"| final / reason | {r['final']} / `{r['abstain_reason']}` |",
              f"| numbers (`_NUMVAL`) | `{r['numbers_NUMVAL']}` |",
              f"| **LITERAL_MATCH** | **{r['LITERAL_MATCH']}** |",
              f"| matching cell | {r['matching_cell'] or '—'} |",
              f"| **claim_form** | **{r['claim_form']}** |",
              f"| confidence | {r['claim_form_confidence']} |",
              f"| basis | {r['claim_form_basis']} |",
              f"| derivation evidence | {dtxt} |",
              f"| ambiguous derivation | {r['ambiguous_derivation']} |",
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
