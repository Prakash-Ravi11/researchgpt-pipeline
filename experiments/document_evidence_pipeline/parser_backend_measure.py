"""Parser-backend MEASURE — layout-aware PDF table cells vs the current PDF path.

Three arms on the 21 PDF-path papers of the frozen canonical corpus:
  current         blocks_from_pdf                  (control)
  pymupdf_tables  tier 1 only  (page.find_tables)
  pymupdf4llm     tier 1, then tier 2 (markdown pipe tables)

Each paper x arm runs in its OWN PROCESS (amendment A): pymupdf4llm.to_markdown
poisons find_tables for the rest of the process, so sharing one would silently
corrupt the tier-1 arms depending on execution order.

Corpus is read READ-ONLY by absolute path from the original working tree (it is
gitignored and absent from this worktree). Output goes only to
runs/parser_backend/ inside this worktree.

    python -u experiments/document_evidence_pipeline/parser_backend_measure.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The corpus lives in the ORIGINAL tree; this worktree has no runs/ or data/.
DATA_ROOT = Path(os.environ.get(
    "RGPT_DATA_ROOT",
    r"C:\Users\Praka\Downloads\researchgpt-pipeline\experiments\document_evidence_pipeline"))
CANON = DATA_ROOT / "runs" / "prodab-20260902T004416Z" / "canonical"
CACHE = CANON / "processed" / "extraction_cache.json"
META = CANON / "raw_metadata" / "collected_papers.json"
PDFS = CANON / "pdfs"
REPS = DATA_ROOT / "runs" / "latex_ingestion" / "reps.json"
FROZEN_CHUNKS = DATA_ROOT / "runs" / "latex_ingestion" / "processed" / "chunks.json"

OUT = HERE / "runs" / "parser_backend"
ARMS = ("current", "pymupdf_tables", "pymupdf4llm")
STRUCT = {"latex", "jats_xml"}
_NUM = re.compile(r"\d")
# A MISSED numbered heading: PyMuPDF emitted "3.1\nLayout Detection Models" as
# one block, so first_line is "3.1", _NUM_HEADING_RE never matched, and the
# section label never advanced (section 11 of the brief).
#
# Detected by the exact counterfactual — would _NUM_HEADING_RE have matched had
# the newline been a space? Testing the first line alone also catches maths like
# "1\n|Pf|", which is not a missed heading and would inflate the count.
_BARE_NUM_LINE = re.compile(r"^\s*\d+(?:\.\d+){0,2}\.?\s*$")


def _is_missed_heading(text: str) -> bool:
    from src.evidence.represent import _NUM_HEADING_RE
    lines = [ln.strip() for ln in (text or "").splitlines()]
    if len(lines) < 2 or not _BARE_NUM_LINE.match(lines[0]) or len(lines[0]) >= 70:
        return False
    return bool(_NUM_HEADING_RE.match(f"{lines[0]} {lines[1]}"))


def _fail(msg: str) -> "NoReturn":                                  # noqa: F821
    print(f"STOP: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _load_inputs():
    for p in (CACHE, META, REPS, PDFS):
        if not p.exists():
            _fail(f"missing input: {p}")
    reps = json.loads(REPS.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    meta = {m["paperId"]: m for m in json.loads(META.read_text(encoding="utf-8"))}
    pdf_ids = sorted(p for p, r in reps.items() if r.split("(")[0] not in STRUCT)
    missing = [p for p in pdf_ids if not (PDFS / f"{p}.pdf").exists()]
    if missing:
        _fail(f"{len(missing)} PDF-path papers have no PDF in {PDFS}: {missing[:3]}")
    if not pdf_ids:
        _fail(f"no PDF-path papers found via {REPS}")
    return reps, cache, meta, pdf_ids


# --------------------------------------------------------------------------
# WORKER — one paper, one arm, one process
# --------------------------------------------------------------------------

def _stale_section_blocks(blocks: list[dict]) -> int:
    """Section 11: count blocks carrying a STALE section label.

    Definition used (stated in the report): a block is stale if it follows a
    MISSED numbered heading — a non-heading block that _NUM_HEADING_RE WOULD
    have matched had its first newline been a space — and precedes the next
    successfully detected heading. Those blocks inherit the section label that
    was current before the missed heading.
    Recorded, NOT fixed: fixing it is a separate single-variable change.
    """
    stale = n = 0
    for b in blocks:
        if b.get("block_type") == "heading":
            stale = 0
            continue
        if _is_missed_heading(b.get("text") or ""):
            stale = 1                      # heading missed here; labels now stale
            continue
        n += stale
    return n


def _ablation_trigger(caption: str, headers: list[str], rows: list[str]) -> str | None:
    """A3/V3: distinguish a caption-driven ablation call from one fired solely by
    row_has_ablation (which borderless '-' cells can trip)."""
    from src.evidence.gate import _ABLATION_RE, classify_table
    if classify_table(caption or "", set(headers or []), set(rows or [])) != "ablation":
        return None
    blob = " ".join([caption or ""] + list(headers or []))
    return "caption_or_header" if _ABLATION_RE.search(blob) else "row_has_ablation_only"


def run_one(paper_id: str, arm: str) -> dict:
    from src.evidence.represent import blocks_from_pdf
    from src.evidence.represent_layout import blocks_from_pdf_layout
    from src.evidence.chunker import chunk_document
    from src.evidence.gate import gate_paper

    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    meta = {m["paperId"]: m for m in json.loads(META.read_text(encoding="utf-8"))}
    data = (PDFS / f"{paper_id}.pdf").read_bytes()

    rec: dict = {"paper_id": paper_id, "arm": arm, "parse_ok": False, "error": None,
                 "wall_seconds": None, "peak_rss_mb": None}
    t0 = time.perf_counter()
    try:
        if arm == "current":
            blocks = blocks_from_pdf(data, paper_id, "canonical")
        else:
            blocks = blocks_from_pdf_layout(data, paper_id, "canonical", arm)
        chunks = chunk_document({"paper_id": paper_id, "representation": "pdf",
                                 "blocks": blocks})
        m = meta.get(paper_id, {})
        claims = {"paper_id": paper_id,
                  **{k: cache.get(paper_id, {}).get(k) for k in ("datasets", "metrics", "results")}}
        surnames = [a.get("name", "") for a in (m.get("authors") or []) if isinstance(a, dict)]
        gated = gate_paper(claims, chunks, "FULL_TEXT", surnames)
        rec["parse_ok"] = True
    except Exception as e:                     # recorded, never swallowed
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["wall_seconds"] = round(time.perf_counter() - t0, 3)
        return rec
    rec["wall_seconds"] = round(time.perf_counter() - t0, 3)

    # ---- table-level records -------------------------------------------------
    tbl = [b for b in blocks if b["block_type"] == "table"]
    captions = Counter((b.get("table_caption") or b.get("text", "").splitlines()[0]
                        if b.get("text") else "") for b in tbl)
    tables, drop_reasons = [], Counter()
    for b in tbl:
        cap = b.get("table_caption")
        if cap is None:
            cap = (b.get("text") or "").splitlines()[0] if b.get("text") else ""
        headers = b.get("column_headers") or []
        rows = b.get("row_labels") or []
        drop_reasons.update(b.get("drop_reasons") or {})
        tables.append({
            "block_id": b["block_id"], "page": b.get("page_or_node"),
            "caption": cap, "column_headers": headers, "row_labels": rows,
            "parse_status": b.get("table_parse_status", "no_cells_attached"),
            "fallback": b.get("table_fallback"),
            "n_cells": len(b.get("table_cells") or []),
            "rows_before_gate": b.get("rows_before_gate", 0),
            "rows_after_gate": b.get("rows_after_gate", 0),
            "n_rows_dropped": b.get("n_rows_dropped", 0),
            "drop_reasons": b.get("drop_reasons") or {},
            "table_type_before": b.get("table_type_before"),
            "table_type_after": b.get("table_type_after"),
            "table_type_flipped": (b.get("table_type_before") is not None
                                   and b.get("table_type_before") != b.get("table_type_after")),
            "ablation_trigger": _ablation_trigger(cap, headers, rows),
            "caption_collision": captions[cap] > 1,
        })

    cells = [c for b in tbl for c in (b.get("table_cells") or [])]
    rec.update({
        "n_blocks": len(blocks),
        "n_table_blocks": len(tbl),
        "n_tables_with_grid": sum(1 for t in tables if t["n_cells"] > 0),
        "n_tables_fallback_pdf": sum(1 for t in tables if t["parse_status"] == "fallback_pdf"),
        "n_cells": len(cells),
        "n_cells_row_and_col_ok": sum(1 for c in cells
                                      if (c.get("row_label") or "").strip()
                                      and (c.get("column_header") or "").strip()),
        "n_cells_with_newline_in_value": sum(1 for c in cells if "\n" in str(c.get("value", ""))),
        "n_rows_dropped": sum(drop_reasons.values()),
        "drop_reasons": dict(drop_reasons),
        "n_stale_section_blocks": _stale_section_blocks(blocks),
        "tables": tables,
    })

    # ---- claim-level records -------------------------------------------------
    claims_out, statuses = [], Counter()
    n_ret = {"metrics": 0, "results": 0}
    for field in ("metrics", "results"):
        for it in gated["evidence"][field]:
            value = it.get("value") or ""
            if not _NUM.search(value):
                continue
            sb = it.get("structural_binding") or {}
            status = sb.get("status", "no_binding_call")
            statuses[status] += 1
            final = it.get("final")
            if final == "RETURNED":
                n_ret[field] += 1
            claims_out.append({
                "field": field, "value": value, "final": final,
                "binding_status": status,
                "table_type": sb.get("table_type"),
                "abstain_reason": it.get("abstain_reason"),
                "bucket": _bucket(status, final, it.get("abstain_reason")),
            })
    rec.update({"binding_status_counts": dict(statuses),
                "n_returned_metrics": n_ret["metrics"],
                "n_returned_results": n_ret["results"],
                "claims": claims_out})
    try:
        import psutil
        mi = psutil.Process().memory_info()
        rec["peak_rss_mb"] = round(getattr(mi, "peak_wset", mi.rss) / 1e6, 1)
    except Exception as e:
        rec["peak_rss_mb"] = None
        rec["peak_rss_error"] = f"{type(e).__name__}: {e}"
    return rec


def _bucket(status: str, final: str | None, reason: str | None) -> str:
    """The five-bucket departure accounting of D6(a)."""
    if status == "bound":
        if final == "RETURNED":
            return "bound_returned"
        if reason == "bound_to_ablation_table":
            return "bound_to_ablation_table"
        if reason == "bound_to_other_table":
            return "bound_to_other_table"
        return f"bound_abstained_other:{reason}"
    if status in ("wrong_cell", "pdf_only", "not_bindable", "not_a_table_claim",
                  "no_number", "no_binding_call"):
        return status if final != "RETURNED" else f"{status}_returned"
    return f"unknown:{status}"


# --------------------------------------------------------------------------
# DRIVER
# --------------------------------------------------------------------------

def _spawn(paper_id: str, arm: str) -> dict:
    p = subprocess.run(
        [sys.executable, "-u", str(Path(__file__).resolve()),
         "--worker", "--paper", paper_id, "--arm", arm],
        capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    marker = "@@JSON@@"
    if marker in p.stdout:
        return json.loads(p.stdout.split(marker, 1)[1].strip())
    return {"paper_id": paper_id, "arm": arm, "parse_ok": False, "wall_seconds": None,
            "peak_rss_mb": None,
            "error": f"worker exit {p.returncode}; stderr={(p.stderr or '')[-800:]}"}


def _frozen_baseline(pdf_ids, cache, meta):
    """Control cross-check: the SAME gate on the frozen cached chunks that
    structural_binding_measure.py uses. If the `current` arm disagrees with this,
    rebuilding blocks from the PDF is not reproducing the frozen pipeline and the
    difference is reported rather than hidden."""
    from src.evidence.gate import gate_paper
    if not FROZEN_CHUNKS.exists():
        return {"available": False, "reason": f"missing {FROZEN_CHUNKS}"}
    by = defaultdict(list)
    for c in json.loads(FROZEN_CHUNKS.read_text(encoding="utf-8")):
        by[c["paper_id"]].append(c)
    ret, statuses = 0, Counter()
    for pid in pdf_ids:
        claims = {"paper_id": pid, **{k: cache.get(pid, {}).get(k)
                                      for k in ("datasets", "metrics", "results")}}
        sn = [a.get("name", "") for a in (meta.get(pid, {}).get("authors") or [])
              if isinstance(a, dict)]
        g = gate_paper(claims, by[pid], "FULL_TEXT", sn)
        for f in ("metrics", "results"):
            for it in g["evidence"][f]:
                if not _NUM.search(it.get("value") or ""):
                    continue
                statuses[(it.get("structural_binding") or {}).get("status", "no_binding_call")] += 1
                if it["final"] == "RETURNED":
                    ret += 1
    return {"available": True, "n_returned": ret, "binding_status_counts": dict(statuses)}


def main() -> int:
    reps, cache, meta, pdf_ids = _load_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"corpus   : {CANON}")
    print(f"papers   : {len(pdf_ids)} PDF-path (census)")
    print(f"arms     : {', '.join(ARMS)}   | tesseract: NOT INSTALLED (with-tesseract UNMEASURED)")
    print(f"processes: {len(pdf_ids) * len(ARMS)} (one per paper x arm)\n")

    t0 = time.perf_counter()
    results = {a: {} for a in ARMS}
    for arm in ARMS:
        ta = time.perf_counter()
        for i, pid in enumerate(pdf_ids, 1):
            r = _spawn(pid, arm)
            results[arm][pid] = r
            flag = "" if r.get("parse_ok") else f"  ERROR {r.get('error', '')[:70]}"
            print(f"  [{arm:15}] {i:2}/{len(pdf_ids)} {pid[:12]}  "
                  f"cells={r.get('n_cells', '-'):>4} ret={r.get('n_returned_metrics', 0) + r.get('n_returned_results', 0)}"
                  f"  {r.get('wall_seconds')}s{flag}")
        print(f"  -- {arm} done in {time.perf_counter() - ta:.1f}s\n")
    wall = time.perf_counter() - t0

    flips = _claims_flipped(results, pdf_ids)
    payload = {
        "corpus": str(CANON), "papers": pdf_ids, "arms": list(ARMS),
        "tesseract": {"installed": False, "arms_with_tesseract": "UNMEASURED"},
        "total_wall_seconds": round(wall, 1),
        "frozen_chunk_baseline": _frozen_baseline(pdf_ids, cache, meta),
        "results": results, "claims_flipped": flips,
    }
    (OUT / "results.json").write_text(json.dumps(payload, indent=2, default=str),
                                      encoding="utf-8")
    _summarise(payload)
    print(f"\nwrote {OUT / 'results.json'}   total wall {wall:.1f}s")
    return 0


def _claims_flipped(results, pdf_ids) -> list[dict]:
    """Every claim whose verdict or binding status differs from `current`, listed
    individually with its value and reason. Never summarised away."""
    out = []
    for pid in pdf_ids:
        base = {(c["field"], c["value"]): c
                for c in (results["current"].get(pid, {}).get("claims") or [])}
        for arm in ARMS:
            if arm == "current":
                continue
            for c in (results[arm].get(pid, {}).get("claims") or []):
                b = base.get((c["field"], c["value"]))
                if b is None:
                    out.append({"paper_id": pid, "arm": arm, "claim_value": c["value"],
                                "field": c["field"], "from_status": "ABSENT_IN_CONTROL",
                                "to_status": c["binding_status"], "from_final": None,
                                "to_final": c["final"], "bucket": c["bucket"],
                                "reason": "claim not present in control arm"})
                    continue
                if b["binding_status"] == c["binding_status"] and b["final"] == c["final"]:
                    continue
                out.append({
                    "paper_id": pid, "arm": arm, "field": c["field"],
                    "claim_value": c["value"],
                    "from_status": b["binding_status"], "to_status": c["binding_status"],
                    "from_final": b["final"], "to_final": c["final"],
                    "bucket": c["bucket"], "table_type": c.get("table_type"),
                    "reason": c.get("abstain_reason") or "returned",
                    "direction": ("RETURNED->ABSTAINED" if b["final"] == "RETURNED"
                                  and c["final"] != "RETURNED" else
                                  "ABSTAINED->RETURNED" if b["final"] != "RETURNED"
                                  and c["final"] == "RETURNED" else "status_only"),
                })
    return out


def _summarise(payload) -> None:
    res, pdf_ids = payload["results"], payload["papers"]

    def tot(arm, key):
        return sum((res[arm][p] or {}).get(key, 0) or 0 for p in pdf_ids)

    print("== per arm ==")
    print(f"  {'arm':16}{'ok':>4}{'cells':>7}{'r+c ok':>8}{'tables':>8}{'grid':>6}"
          f"{'fallbk':>8}{'dropped':>9}{'RET m':>7}{'RET r':>7}{'wall s':>8}")
    for a in ARMS:
        ok = sum(1 for p in pdf_ids if res[a][p].get("parse_ok"))
        w = sum(res[a][p].get("wall_seconds") or 0 for p in pdf_ids)
        print(f"  {a:16}{ok:>4}{tot(a,'n_cells'):>7}{tot(a,'n_cells_row_and_col_ok'):>8}"
              f"{tot(a,'n_table_blocks'):>8}{tot(a,'n_tables_with_grid'):>6}"
              f"{tot(a,'n_tables_fallback_pdf'):>8}{tot(a,'n_rows_dropped'):>9}"
              f"{tot(a,'n_returned_metrics'):>7}{tot(a,'n_returned_results'):>7}{w:>8.1f}")

    base = tot("current", "n_returned_metrics") + tot("current", "n_returned_results")
    print(f"\n== PRIMARY: delta_returned vs current (control = {base}) ==")
    for a in ARMS:
        if a == "current":
            continue
        t = tot(a, "n_returned_metrics") + tot(a, "n_returned_results")
        papers = {f["paper_id"] for f in payload["claims_flipped"]
                  if f["arm"] == a and f["direction"] == "ABSTAINED->RETURNED"}
        print(f"  {a:16} returned={t:>3}  delta={t - base:+3}  "
              f"newly-returned claims from {len(papers)} paper(s)")

    print("\n== binding status counts ==")
    for a in ARMS:
        c = Counter()
        for p in pdf_ids:
            c.update(res[a][p].get("binding_status_counts") or {})
        print(f"  {a:16} {dict(c)}")

    print("\n== departure buckets (D6a) ==")
    for a in ARMS:
        c = Counter(cl["bucket"] for p in pdf_ids for cl in (res[a][p].get("claims") or []))
        print(f"  {a:16} {dict(c)}")

    reg = [f for f in payload["claims_flipped"] if f["direction"] == "RETURNED->ABSTAINED"]
    print(f"\n== RETURNED -> ABSTAINED transitions: {len(reg)} ==")
    for f in reg:
        print(f"  [{f['arm']}] {f['paper_id'][:12]} {f['from_status']}->{f['to_status']} "
              f"({f['reason']}): {f['claim_value'][:90]!r}")

    fb = payload["frozen_chunk_baseline"]
    if fb.get("available"):
        print(f"\n== control cross-check ==\n  frozen cached chunks: returned={fb['n_returned']} "
              f"{fb['binding_status_counts']}")
        print(f"  rebuilt `current` arm: returned={base} "
              f"{dict(Counter(k for p in pdf_ids for k, v in (res['current'][p].get('binding_status_counts') or {}).items() for _ in range(v)))}")

    flips_ab = Counter(t["ablation_trigger"] for a in ARMS for p in pdf_ids
                       for t in (res[a][p].get("tables") or []) if t["ablation_trigger"])
    print(f"\n== ablation triggers (all arms): {dict(flips_ab)} ==")
    tt = [(a, p, t) for a in ARMS for p in pdf_ids
          for t in (res[a][p].get("tables") or []) if t["table_type_flipped"]]
    print(f"== table_type flips after row drops: {len(tt)} ==")
    for a, p, t in tt[:20]:
        print(f"  [{a}] {p[:12]} {t['table_type_before']}->{t['table_type_after']} "
              f"rows {t['rows_before_gate']}->{t['rows_after_gate']} {t['caption'][:50]!r}")
    stale = {a: tot(a, "n_stale_section_blocks") for a in ARMS}
    print(f"\n== stale section-label blocks (recorded, not fixed): {stale} ==")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--paper")
    ap.add_argument("--arm", choices=ARMS)
    a = ap.parse_args()
    if a.worker:
        print("@@JSON@@")
        print(json.dumps(run_one(a.paper, a.arm), default=str))
        raise SystemExit(0)
    raise SystemExit(main())
