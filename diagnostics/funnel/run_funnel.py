"""Diagnostic funnel runner — wraps the existing measurement harness.

No pipeline logic is reimplemented here. This calls
`parser_backend_measure.run_one(paper_id, arm)` verbatim, one paper per process
(pymupdf4llm poisons find_tables for the rest of a process — see
`src/evidence/represent_layout.py:41-48`), and derives the trace from what that
function already records, plus one wrapper around `structural_bind` that
observes the binder's inputs without altering its output.

    python diagnostics/funnel/run_funnel.py --arm pymupdf4llm --out baseline
    python diagnostics/funnel/run_funnel.py --arm pymupdf4llm --out trace_on --trace

Reason codes are taken from the literal conditions in the code; anything that
cannot be attributed is emitted as UNATTRIBUTED with its code_location.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "document_evidence_pipeline"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import funnel_trace as ft  # noqa: E402  (diagnostics/funnel is this file's dir)

OUT_ROOT = HERE / "out"
MARKER = "@@JSON@@"
_TABLE_LABEL_RE = __import__("re").compile(r"\b(?:Table|Tab\.)\s*([IVXLC]+|\d+)", __import__("re").I)

# ---- reason codes, each taken from the literal condition in the code -------
# src/evidence/represent_layout.py
LOC_NO_GRID = "src/evidence/represent_layout.py:386"
LOC_GATE = "src/evidence/represent_layout.py:405"
LOC_ROWDROP = "src/evidence/represent_layout.py:160-169"
LOC_ATTACH = "src/evidence/represent_layout.py:110"
LOC_PARSE_ROWS = "src/evidence/represent_layout.py:76-79"
LOC_PARSE_CELLS = "src/evidence/represent_layout.py:115-119"
# src/evidence/gate.py
LOC_ANCHOR = "src/evidence/gate.py:525 (anchors.py:27)"
LOC_BIND = "src/evidence/gate.py:390"
LOC_RETURN = "src/evidence/gate.py:571"

_GATE_CODES = {
    "too_few_data_rows": "GATE_TOO_FEW_DATA_ROWS",
    "too_few_columns": "GATE_TOO_FEW_COLUMNS",
    "empty_header_cell": "GATE_EMPTY_HEADER_CELL",
    "newline_in_header": "GATE_HEADER_NEWLINE",
    "header_too_long": "GATE_HEADER_TOO_LONG",
}
_ROW_CODES = {
    "empty_row_label": "ROW_EMPTY_LABEL",
    "newline_in_row_label": "ROW_LABEL_NEWLINE",
    "row_label_too_long": "ROW_LABEL_TOO_LONG",
}


def classify_fallback(fb: str | None) -> tuple[str, str]:
    """(reason_code, code_location) for a table's `table_fallback` string."""
    s = str(fb or "")
    if s == "no_grid_from_backend":
        return "NO_GRID_FROM_BACKEND", LOC_NO_GRID
    if s.startswith("tier1_page_error"):
        return "TIER1_PAGE_ERROR", "src/evidence/represent_layout.py:336-338"
    if s.startswith("quality_gate:"):
        body = s.split("quality_gate:", 1)[1]
        return _GATE_CODES.get(body.split(":")[0], "UNATTRIBUTED"), LOC_GATE
    if s.startswith("too_few_rows"):
        return "PARSE_TOO_FEW_ROWS", LOC_PARSE_ROWS
    if s == "no_data_cells_after_parse":
        return "PARSE_NO_DATA_CELLS", LOC_PARSE_CELLS
    if s.startswith("table-wrap_has_no_xml_grid"):
        return "PARSE_NO_XML_GRID", "src/evidence/represent_layout.py:70-74"
    return "UNATTRIBUTED", LOC_GATE


# ==========================================================================
# WORKER — one paper, one arm, one process
# ==========================================================================

def _install_binder_probe(paper_id: str):
    """Wrap gate.structural_bind so every call is traced with full detail.

    The wrapper calls the original and returns its result **unchanged**. It reads
    the same inputs the binder reads, using the gate's own helpers, so the
    reported comparison is the real one rather than a restatement of it.
    """
    from src.evidence import gate as G

    original = G.structural_bind
    seen = Counter()

    def traced(value, chunks):
        out = original(value, chunks)
        i = seen[paper_id]
        seen[paper_id] += 1
        cid = f"{paper_id}:bind:{i}"
        try:
            cells = G.paper_table_cells(chunks)
            nums = G._NUMVAL.findall(value or "")
            mtoks = G._metric_tokens(value or "")
            sm = G._SUBJECT_RE.match(value or "")
            subject = sm.group(1).strip() if sm else None
            if subject and G._OWN_ROW.search(subject):
                subject = None
            import re as _re

            def norm_cell(s):
                return _re.sub(r"[^\d.\-]", "", str(s))

            cands = []
            for c in cells:
                col = c.get("column_header", "")
                raw = c.get("value", "")
                col_ok = bool(mtoks) and G._col_matches_metric(col, mtoks)
                row_ok = G._row_matches_subject(c.get("row_label", ""), subject)
                val_hits = [n for n in nums
                            if n == norm_cell(raw)
                            or _re.search(r"(?<![\d.])" + _re.escape(n) + r"(?![\d])", str(raw))]
                if col_ok or val_hits:          # candidates the binder could reach
                    cands.append({
                        "cell_raw": raw, "cell_normalized": norm_cell(raw),
                        "header_path": f"{c.get('caption', '')} > {col}",
                        "row_label": c.get("row_label", ""),
                        "column_matches_metric": col_ok,
                        "row_matches_subject": row_ok,
                        "value_match": val_hits,
                    })
            detail = {
                "claim_text": value,
                "claim_value_raw": nums,
                "claim_value_normalized": nums,   # the binder never normalises this side
                "claim_metric_tokens": sorted(mtoks),
                "claim_subject": subject if subject is not None else "OWN",
                "n_cells_in_paper": len(cells),
                "candidates": cands,
                "comparison": "gate._has: exact match on re.sub(r'[^\\d.\\-]','',cell) "
                              "OR token-boundary substring of claim number in cell",
                "result": out.get("status"),
                "result_reason": out.get("reason"),
            }
        except Exception as e:                    # never let the probe alter a run
            detail = {"probe_error": f"{type(e).__name__}: {e}", "result": out.get("status")}
        ft.emit("B2_binder", "binding_attempt", cid,
                "PASS" if out.get("status") == "bound" else "FAIL",
                paper_id=paper_id, reason_code=str(out.get("status", "")).upper(),
                detail=detail, code_location=LOC_BIND)
        return out

    G.structural_bind = traced
    return original


def _install_attach_probe(paper_id: str):
    """Wrap represent_layout._attach to record what the gate and the attach loop
    actually did to each table.

    The wrapper calls the original and returns its result unchanged. Afterwards it
    re-derives the gated grid by calling the PURE functions _gate_grid and
    _row_drop_reason a second time (no side effects, no state), then replays the
    line-110 condition position by position to classify every discarded cell.
    That is the only way to attribute those discards: the pipeline keeps no
    counter for them (STAGE_DEFINITIONS.md A4, defect D-3).
    """
    from src.evidence import represent_layout as RL

    original = RL._attach
    idx = Counter()

    def traced(b, grid, tier, pid, source, backend, page_error=None, *,
               collapse_header_ws=False):
        original(b, grid, tier, pid, source, backend, page_error,
                 collapse_header_ws=collapse_header_ws)
        i = idx[paper_id]
        idx[paper_id] += 1
        tid = ft.table_id(paper_id, i)
        try:
            _emit_attach_detail(b, grid, tid, paper_id, collapse_header_ws)
        except Exception as e:
            ft.emit("A0_attach_detail", "table_block", tid, "DROP",
                    paper_id=paper_id, reason_code="PROBE_ERROR",
                    detail={"probe_error": "%s: %s" % (type(e).__name__, e)},
                    code_location=LOC_ATTACH)

    RL._attach = traced
    return original


def _emit_attach_detail(b, grid, tid, paper_id, collapse_header_ws):
    """One rich row per table, plus one row per discarded cell with a real reason."""
    from src.evidence.represent_layout import _gate_grid, _norm, _row_drop_reason

    parsed = b.get("table_parse_status") == "parsed"
    path = "cell_table" if parsed else "fallback"
    code, loc = classify_fallback(b.get("table_fallback"))
    block_text = b.get("text") or ""

    if grid is None:
        ft.emit("A0_attach_detail", "table_block", tid, "DROP", paper_id=paper_id,
                parent_id=paper_id, reason_code=code, code_location=loc,
                detail={"extraction_path": path, "grid_returned": False,
                        "raw_rows": 0, "raw_cols": 0, "block_text": block_text[:4000],
                        "gate_result": "no_grid", "discards": {},
                        "discarded_values": [], "attached_cell_ids": [],
                        "attached_values": [], "caption": b.get("table_caption") or ""})
        return

    g = _norm(grid)
    gated = _gate_grid(g, collapse_header_ws)      # pure; re-derivation only
    header, kept = gated["header"], gated["rows"]

    discards = {}
    discarded_values = []
    attached_ids = []

    def sq(x):
        return " ".join(str(x).split())

    if not gated["reject"]:
        for r_i, row in enumerate(kept, start=1):
            lbl = sq(row[0] if row else "")
            for j, raw_val in enumerate(row):
                val = sq(raw_val)
                head = sq(header[j]) if j < len(header) else ""
                if j == 0:
                    why = "row_label_corner"
                elif not val:
                    why = "empty_value"
                elif not head:
                    why = "empty_header"
                elif val == lbl:
                    why = "value_equals_row_label"
                else:
                    why = None
                if why is None:
                    attached_ids.append(ft.cell_id(tid, r_i, j))
                    continue
                discards[why] = discards.get(why, 0) + 1
                if val:
                    discarded_values.append(val)
                ft.emit("A4_cell_discard", "cell", "%s#r%sc%s" % (tid, r_i, j), "DROP",
                        paper_id=paper_id, parent_id=tid,
                        reason_code="CELL_" + why.upper(),
                        detail={"extraction_path": path, "value": val,
                                "header": head, "row_label": lbl},
                        code_location=LOC_ATTACH)

    row_drops = {}
    if not gated["reject"]:
        for row in (g[1:] if len(g) > 1 else []):
            w = _row_drop_reason(row[0] if row else "")
            if w:
                row_drops[w] = row_drops.get(w, 0) + 1

    ft.emit("A0_attach_detail", "table_block", tid,
            "KEEP" if parsed else "DROP", paper_id=paper_id, parent_id=paper_id,
            reason_code="" if parsed else code,
            code_location=(loc if not parsed
                           else "src/evidence/represent_layout.py:410-419"),
            detail={"extraction_path": path, "grid_returned": True,
                    "raw_rows": len(g), "raw_cols": (len(g[0]) if g else 0),
                    "gate_result": "rejected" if gated["reject"] else "passed",
                    "gate_reason_raw": gated["reject"],
                    "gate_reason_code": ("" if parsed else code),
                    "header": header, "raw_header": gated.get("raw_header") or [],
                    "rows_before_gate": gated["rows_before"],
                    "rows_after_gate": gated["rows_after"],
                    "row_drop_reasons": row_drops,
                    "discards": discards,
                    "discarded_values": discarded_values[:400],
                    "attached_cell_ids": attached_ids,
                    "n_attached": len(b.get("table_cells") or []),
                    "attached_values": [str(c.get("value", ""))
                                        for c in (b.get("table_cells") or [])],
                    # full cell inventory: lets a wrong_cell verdict (which records
                    # only row+col, never the value -- defect F-3) be resolved back
                    # to a concrete cell id and value. Read-only.
                    "attached_cells": [{"row": c.get("row_label", ""),
                                        "col": c.get("column_header", ""),
                                        "value": str(c.get("value", "")),
                                        "caption": c.get("caption", "")}
                                       for c in (b.get("table_cells") or [])],
                    "block_text": block_text[:4000],
                    "caption": b.get("table_caption") or ""})


def _install_gate_probe(paper_id: str):
    """Wrap gate.gate_paper to record each evidence item as the gate finished it.

    Read-only on the gate's own return value. This is where terminal_reason_code,
    the grounding block_id (needed to decide whether a TABLE contributed to a
    returned metric) and the attribution verdict come from.
    """
    from src.evidence import gate as G

    original = G.gate_paper

    def traced(record, chunks, acquisition_status, surnames):
        out = original(record, chunks, acquisition_status, surnames)
        try:
            for field in ("datasets", "metrics", "results"):
                for i, it in enumerate(out["evidence"].get(field) or []):
                    sb = it.get("structural_binding") or {}
                    final = it.get("final")
                    reason = it.get("abstain_reason")
                    rc = str(reason or ("RETURNED" if final == "RETURNED"
                                        else "UNATTRIBUTED")).upper()
                    ft.emit("B0_evidence_item", "claim",
                            ft.claim_id(paper_id, field, i),
                            "PASS" if final == "RETURNED" else "FAIL",
                            paper_id=paper_id, parent_id=paper_id, reason_code=rc,
                            detail={"field": field, "value": it.get("value"),
                                    "final": final, "abstain_reason": reason,
                                    "binding_status": sb.get("status"),
                                    "binding_reason": sb.get("reason"),
                                    "binding_cell": sb.get("cell"),
                                    "binding_candidate": sb.get("candidate"),
                                    "table_type": sb.get("table_type"),
                                    "block_id": it.get("block_id"),
                                    "section": it.get("section"),
                                    "block_type_grounded": it.get("block_type"),
                                    "evidence_span": (it.get("evidence_span") or "")[:400],
                                    "attribution": it.get("attribution"),
                                    "attribution_confidence":
                                        it.get("attribution_confidence"),
                                    "ownership_flag": it.get("ownership_flag"),
                                    "range_check": it.get("range_check"),
                                    "provenance_valid": it.get("provenance_valid")},
                            code_location=LOC_RETURN)
        except Exception as e:
            ft.emit("B0_evidence_item", "claim", paper_id + ":probe", "FAIL",
                    paper_id=paper_id, reason_code="PROBE_ERROR",
                    detail={"probe_error": "%s: %s" % (type(e).__name__, e)},
                    code_location=LOC_RETURN)
        return out

    G.gate_paper = traced
    return original


def _install_chunk_probe(paper_id: str):
    """Wrap chunk_document to record a per-page index of the paper.

    Read-only: calls the original and returns its result unchanged. Needed for
    existence check (e) -- is the value in the page text OUTSIDE every detected
    table block -- and for the (f) TABLE_POSSIBLY_UNDETECTED triage, neither of
    which can be answered from the gate's own output.
    """
    from src.evidence import chunker as CH

    original = CH.chunk_document

    def traced(doc):
        out = original(doc)
        try:
            pages: dict[str, dict] = {}
            for b in doc.get("blocks") or []:
                pg = str(b.get("page_or_node") or "p0")
                p = pages.setdefault(pg, {"non_table_text": [], "n_table_blocks": 0,
                                          "table_labels_in_prose": []})
                if b.get("block_type") == "table":
                    p["n_table_blocks"] += 1
                else:
                    t = b.get("text") or ""
                    p["non_table_text"].append(t)
                    p["table_labels_in_prose"] += _TABLE_LABEL_RE.findall(t)
            for pg, p in pages.items():
                ft.emit("A_page_index", "table_block", f"{paper_id}:page:{pg}", "KEEP",
                        paper_id=paper_id, parent_id=paper_id,
                        detail={"page": pg,
                                "n_table_blocks": p["n_table_blocks"],
                                "table_labels_in_prose":
                                    sorted(set(p["table_labels_in_prose"])),
                                "non_table_text": " ".join(p["non_table_text"])[:20000]},
                        code_location="src/evidence/chunker.py (read-only probe)")
        except Exception as e:
            ft.emit("A_page_index", "table_block", f"{paper_id}:page:probe", "DROP",
                    paper_id=paper_id, reason_code="PROBE_ERROR",
                    detail={"probe_error": "%s: %s" % (type(e).__name__, e)},
                    code_location="src/evidence/chunker.py (read-only probe)")
        return out

    CH.chunk_document = traced
    return original


def _emit_tables(rec: dict, paper_id: str) -> None:
    """Funnel A rows, derived from what run_one already recorded per table."""
    for i, t in enumerate(rec.get("tables") or []):
        tid = ft.table_id(paper_id, i)
        parsed = t.get("parse_status") == "parsed"
        path = "cell_table" if parsed else "fallback"
        code, loc = classify_fallback(t.get("fallback"))
        base = dict(paper_id=paper_id, parent_id=paper_id)

        # A1 every table block enters
        ft.emit("A1_table_block", "table_block", tid, "KEEP",
                detail={"extraction_path": path, "page": t.get("page"),
                        "caption": t.get("caption", "")[:200]},
                code_location="src/evidence/represent_layout.py:318", **base)

        # A2 did the backend return a grid?
        got_grid = code != "NO_GRID_FROM_BACKEND"
        ft.emit("A2_grid_return", "grid_return", tid, "KEEP" if got_grid else "DROP",
                reason_code="" if got_grid else code,
                detail={"extraction_path": path},
                code_location="src/evidence/represent_layout.py:351-354" if got_grid else loc,
                **base)
        if not got_grid:
            continue

        # A3 quality gate + post-gate parse
        ft.emit("A3_cell_table", "cell_table" if parsed else "fallback_table", tid,
                "KEEP" if parsed else "DROP", reason_code="" if parsed else code,
                detail={"extraction_path": path, "n_cells": t.get("n_cells", 0),
                        "column_headers": t.get("column_headers") or [],
                        "rows_before_gate": t.get("rows_before_gate", 0),
                        "rows_after_gate": t.get("rows_after_gate", 0)},
                code_location="src/evidence/represent_layout.py:410-419" if parsed else loc,
                **base)
        # A table REJECTED by the whole-table gate never reached the row loop, so it
        # has no row drops. But a table that PASSED the gate and then produced no
        # cell (PARSE_TOO_FEW_ROWS) did run the row loop and does have them, so the
        # row stage must cover it too -- skipping it here undercounted 45 as 37.
        gate_passed = bool(t.get("drop_reasons")) or t.get("rows_after_gate", 0) > 0
        if not parsed and not gate_passed:
            continue

        # A5 row drops (only meaningful for tables that reached the row loop)
        for reason, n in (t.get("drop_reasons") or {}).items():
            for k in range(n):
                ft.emit("A5_row", "row", f"{tid}#row_drop{k}", "DROP",
                        reason_code=_ROW_CODES.get(reason, "UNATTRIBUTED"),
                        detail={"extraction_path": path, "raw_reason": reason},
                        code_location=LOC_ROWDROP, **base)
        for k in range(t.get("rows_after_gate", 0)):
            ft.emit("A5_row", "row", f"{tid}#row{k}", "KEEP",
                    detail={"extraction_path": path}, code_location=LOC_ROWDROP, **base)

        if not parsed:
            continue

        # A4 cells. Positions discarded at represent_layout.py:110 are recorded
        # nowhere by the pipeline, so the count is DERIVED (grid area - attached)
        # and attributed to that exact line. See STAGE_DEFINITIONS.md A4.
        ncols = len(t.get("column_headers") or [])
        area = max(0, t.get("rows_after_gate", 0) * max(0, ncols - 1))
        attached = t.get("n_cells", 0)
        ft.emit("A4_cell", "cell", f"{tid}#attached", "KEEP",
                reason_code="", detail={"extraction_path": path, "n_attached": attached,
                                        "grid_area_excl_row_label": area},
                code_location="src/evidence/represent_layout.py:111", **base)
        if area > attached:
            ft.emit("A4_cell", "cell", f"{tid}#skipped", "DROP",
                    reason_code="CELL_SKIPPED_AT_ATTACH",
                    detail={"extraction_path": path, "n_skipped_derived": area - attached,
                            "note": "empty value, empty header, or value == row_label; "
                                    "the pipeline records no per-cell reason"},
                    code_location=LOC_ATTACH, **base)


def _emit_claims(rec: dict, paper_id: str) -> None:
    """Funnel B rows, derived from run_one's per-claim records."""
    for i, c in enumerate(rec.get("claims") or []):
        cid = ft.claim_id(paper_id, c.get("field", "?"), i)
        status = c.get("binding_status")
        final = c.get("final")
        ft.emit("B1_claim", "claim", cid, "KEEP",
                paper_id=paper_id, parent_id=paper_id,
                detail={"field": c.get("field"), "value": c.get("value")},
                code_location="src/evidence/gate.py:507")
        entered = status != "no_binding_call"
        ft.emit("B2_enters_binder", "claim", cid, "KEEP" if entered else "DROP",
                paper_id=paper_id, parent_id=paper_id,
                reason_code="" if entered else "NO_NUMERIC_ANCHOR",
                detail={"value": c.get("value"), "binding_status": status},
                code_location=LOC_ANCHOR)
        ft.emit("B4_binding", "binding_attempt", cid,
                "PASS" if status == "bound" else "FAIL",
                paper_id=paper_id, parent_id=paper_id,
                reason_code=str(status or "").upper(),
                detail={"value": c.get("value"), "table_type": c.get("table_type")},
                code_location=LOC_BIND)
        ft.emit("B5_result", "result", cid, "PASS" if final == "RETURNED" else "FAIL",
                paper_id=paper_id, parent_id=paper_id,
                reason_code="" if final == "RETURNED"
                else str(c.get("abstain_reason") or "UNATTRIBUTED").upper(),
                detail={"field": c.get("field"), "value": c.get("value"),
                        "binding_status": status, "bucket": c.get("bucket")},
                code_location=LOC_RETURN)


def worker(paper_id: str, arm: str, trace_path: str | None, run_id: str) -> dict:
    import parser_backend_measure as PBM

    if trace_path:
        ft.configure(trace_path, run_id, arm)
        _install_binder_probe(paper_id)
        _install_attach_probe(paper_id)
        _install_gate_probe(paper_id)
        _install_chunk_probe(paper_id)
    rec = PBM.run_one(paper_id, arm)
    if trace_path:
        _emit_tables(rec, paper_id)
        _emit_claims(rec, paper_id)
    return rec


# ==========================================================================
# DRIVER
# ==========================================================================

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# Timing and memory differ between two runs of identical code, so hashing them
# would make the no-op proof impossible to pass for reasons that say nothing
# about behaviour. The hash covers the SUBSTANTIVE output with these stripped.
VOLATILE = frozenset({"wall_seconds", "peak_rss_mb", "peak_rss_error", "total_wall_seconds"})


def _canonical(obj):
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items()) if k not in VOLATILE}
    if isinstance(obj, list):
        return [_canonical(v) for v in obj]
    return obj


def _canonical_digest(payload) -> str:
    blob = json.dumps(_canonical(payload), sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def write_hashes(out: Path) -> dict:
    """output_hashes.json for one out/ directory, volatile fields excluded."""
    h = {}
    for name in ("results.json", "counts.json"):
        f = out / name
        if f.exists():
            h[f"{name} (canonical, volatile fields excluded)"] = _canonical_digest(
                json.loads(f.read_text(encoding="utf-8")))
            h[f"{name} (raw bytes)"] = _sha256(f)
    t = out / "trace.jsonl"
    if t.exists():
        h["trace.jsonl (raw bytes)"] = _sha256(t)
        h["trace.jsonl bytes"] = t.stat().st_size
    (out / "output_hashes.json").write_text(json.dumps(h, indent=1), encoding="utf-8")
    return h


def _run_metadata(arm: str, trace: bool) -> dict:
    def sh(*cmd):
        try:
            return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                  timeout=60).stdout.strip()
        except Exception as e:
            return f"unavailable: {type(e).__name__}: {e}"

    cfg = ROOT / "configs" / "staging_config.yaml"
    return {
        "git_head": sh("git", "rev-parse", "HEAD"),
        "git_branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "git_status_clean": sh("git", "status", "--porcelain") == "",
        "config_path": str(cfg),
        "config_sha256": _sha256(cfg) if cfg.exists() else None,
        "funnel_trace_enabled_in_config": ft.config_flag(),
        "trace_requested": trace,
        "arm": arm,
        "claim_extractor": os.environ.get("RGPT_CLAIM_EXTRACTOR") or "from config",
        "ownership_policy": os.environ.get("RGPT_OWNERSHIP_POLICY") or "from config",
        "python": sys.version,
        "platform": sys.platform,
        "pip_freeze": sh(sys.executable, "-m", "pip", "freeze").splitlines(),
        "ollama_list": sh("ollama", "list").splitlines(),
        "llm_calls_in_path": 0,
        "llm_note": "no LLM call occurs in this path: claims are read from the frozen "
                    "Stage-4 extraction cache, so temperature is not a parameter of this run",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="pymupdf4llm")
    ap.add_argument("--out", required=True, help="subdirectory under diagnostics/funnel/out/")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--paper")
    ap.add_argument("--trace-path")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--hash-only", action="store_true",
                    help="recompute counts/hashes for an existing out/ dir, no re-run")
    ap.add_argument("--claim-extractor", choices=("legacy", "explicit"), default=None,
                    help="override evidence_grounding.claim_extractor for this run")
    ap.add_argument("--ownership-policy", choices=("block", "warn"), default=None,
                    help="override evidence_grounding.ownership_policy for this run")
    ap.add_argument("--out-root", default=None,
                    help="base directory for --out (default diagnostics/funnel/out)")
    a = ap.parse_args()
    global OUT_ROOT
    if a.out_root:
        OUT_ROOT = Path(a.out_root)

    if a.hash_only:
        out = OUT_ROOT / a.out
        payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
        counts = summarise(payload["results"], payload["papers"])
        (out / "counts.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
        print(json.dumps(write_hashes(out), indent=1))
        return 0

    if a.worker:
        print(MARKER)
        print(json.dumps(worker(a.paper, a.arm, a.trace_path, a.run_id), default=str))
        return 0

    import parser_backend_measure as PBM

    _, _, _, pdf_ids = PBM._load_inputs()
    out = OUT_ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    trace_path = (out / "trace.jsonl") if a.trace else None
    if trace_path and trace_path.exists():
        trace_path.unlink()
    run_id = a.run_id or f"{a.out}-{int(time.time())}"

    print(f"arm={a.arm} papers={len(pdf_ids)} trace={'on' if a.trace else 'off'} -> {out}")
    results, t0 = {}, time.perf_counter()
    for i, pid in enumerate(pdf_ids, 1):
        cmd = [sys.executable, "-u", str(Path(__file__).resolve()),
               "--worker", "--paper", pid, "--arm", a.arm, "--out", a.out,
               "--run-id", run_id]
        if a.out_root:
            cmd += ["--out-root", a.out_root]
        if a.claim_extractor:
            cmd += ["--claim-extractor", a.claim_extractor]
        if a.ownership_policy:
            cmd += ["--ownership-policy", a.ownership_policy]
        if trace_path:
            cmd += ["--trace-path", str(trace_path)]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8",
               "RGPT_FUNNEL_TRACE": "1" if a.trace else "0"}
        if a.claim_extractor:
            env["RGPT_CLAIM_EXTRACTOR"] = a.claim_extractor
        if a.ownership_policy:
            env["RGPT_OWNERSHIP_POLICY"] = a.ownership_policy
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if MARKER in p.stdout:
            results[pid] = json.loads(p.stdout.split(MARKER, 1)[1].strip())
        else:
            results[pid] = {"paper_id": pid, "arm": a.arm, "parse_ok": False,
                            "error": f"worker exit {p.returncode}; "
                                     f"stderr={(p.stderr or '')[-600:]}"}
        print(f"  [{i:2}/{len(pdf_ids)}] {pid[:12]} "
              f"{'ok' if results[pid].get('parse_ok') else 'FAIL'}")

    counts = summarise(results, pdf_ids)
    counts["wall_seconds"] = round(time.perf_counter() - t0, 1)
    (out / "counts.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    (out / "results.json").write_text(json.dumps({"papers": pdf_ids, "arm": a.arm,
                                                  "results": results}, indent=1, default=str),
                                      encoding="utf-8")
    (out / "run_metadata.json").write_text(json.dumps(_run_metadata(a.arm, a.trace), indent=1),
                                           encoding="utf-8")
    write_hashes(out)

    print(json.dumps(counts, indent=1))
    return 0


def summarise(results: dict, pdf_ids: list[str]) -> dict:
    def tot(k):
        return sum((results[p] or {}).get(k, 0) or 0 for p in pdf_ids)

    tables = [t for p in pdf_ids for t in (results[p].get("tables") or [])]
    no_grid = sum(1 for t in tables if t.get("fallback") == "no_grid_from_backend")
    bs = Counter()
    for p in pdf_ids:
        bs.update(results[p].get("binding_status_counts") or {})
    return {
        "papers": len(pdf_ids),
        "parse_ok": sum(1 for p in pdf_ids if results[p].get("parse_ok")),
        "table_blocks": tot("n_table_blocks"),
        "backend_grid_returns": tot("n_table_blocks") - no_grid,
        "post_gate_cell_tables": tot("n_tables_with_grid"),
        "fallback_pdf_tables": tot("n_tables_fallback_pdf"),
        "attached_cells": tot("n_cells"),
        "rows_dropped": tot("n_rows_dropped"),
        "returned_metrics": tot("n_returned_metrics"),
        "returned_results": tot("n_returned_results"),
        "successful_bindings": bs.get("bound", 0),
        "binding_status_counts": dict(bs),
        "claims_total": sum(bs.values()),
        "claims_entering_binder": sum(bs.values()) - bs.get("no_binding_call", 0),
    }


if __name__ == "__main__":
    raise SystemExit(main())
