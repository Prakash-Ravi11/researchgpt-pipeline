"""Post-fix evaluation, steps 2-3.
(2) Assemble the verified claim->cell gold from the two blind readings of the harvested candidates.
(3) Run every verified pair and claim through the actual pipeline BEFORE and AFTER the PDF table-cell fix, and re-run the
    unchanged Stage B GOLD->BINDER oracle for P003.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/postfix_evaluate.py <labels.json> <candidates.json>

<candidates.json> is written by postfix_mine_claims.py. <labels.json> holds the blind readings as
[{reader, group, labels: [...]}, ...]: reader A_claim_first and reader B_cell_first each read every candidate once.

Gold rules (fixed before any evaluation result was seen):
  reading    invalid when its claim_text_exact is non-empty and not an exact substring of the harvested claim_text.
  agreement  both readings VERIFIED_POSITIVE, their claims equal or one containing the other (gold claim = the longer),
             and >= 1 target on which both agree: same table label and page, same innermost row label, same leaf column
             header (case- and whitespace-insensitive), same numeric value  -> VERIFIED_POSITIVE, one pair per agreed
             target. Both readings with the same non-positive status -> that status. Anything else -> AMBIGUOUS
             (reader disagreement); never a pair.
Evaluation rules:
  BEFORE     git HEAD's src/evidence/represent.py blocks_from_pdf (read with `git show`, executed in memory);
  AFTER      the working tree. Both through process_paper_grounded on the hash-pinned PDF, then the Stage B oracle's own
             run_case (structural_bind + gate_paper), unchanged.
  units      CANONICAL is evaluated per PAIR: stage_b_gold_binder_oracle.canonical_claim over the verified cell,
             "The <row> achieves a <header> of <value>.". REAL is evaluated per CLAIM: the gold sentence verbatim; the
             binder returns ONE cell per claim (the first number with a metric-column hit, gate.py:467-479), so a claim
             is bound correctly when it binds ANY of its own verified target cells.
             (Revised before any evaluation output was read: the first version scored REAL per pair, which would have
             counted the other targets of a correctly bound multi-value claim as binder failures.)
  table      reconstructed when the paper has cells on the table page whose caption starts with the table label.
  target     a cell of that table whose value holds the claimed number (the binder's token rule, gate.py:459-465).
             Row correct: row_label equals the innermost verified row label; column correct: column_header equals the
             verified header path joined " / " or its leaf (both case/whitespace-normalised). Whitespace-only
             differences are reported as artifacts and never counted correct.
  bound correct  structural_bind status bound AND its cell (row, col, value, caption) is a reconstructed target cell.
  failure    the earliest stage: representation (table not reconstructed / target cell wrong) -> binder -> gate. The
             gate is judged for REAL claims only: an own_method claim not RETURNED, or a baseline_or_cited claim
             RETURNED, is a gate failure; for dataset/other claims and for CANONICAL probes the gate outcome is reported.
Labels are machine-assisted and unvalidated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import types
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import src.evidence.gate as G                                  # noqa: E402  (production, read-only use)
import src.evidence.represent as R                             # noqa: E402
from src.processing.pdf_parser import process_paper_grounded   # noqa: E402
import stage_b_gold_binder_oracle as O                         # noqa: E402  (unchanged; main() never called)

GOLD_JSON, GOLD_CSV = HERE / "postfix_claim_cell_gold.json", HERE / "postfix_claim_cell_gold.csv"
GOLD_MD = HERE / "postfix_claim_cell_report.md"
OR_JSON, OR_CSV, OR_MD = (HERE / f"postfix_binder_oracle{x}" for x in (".json", ".csv", "_report.md"))
STAGE_A_CSV = HERE / "gold_pair_verification.csv"
READERS = ("A_claim_first", "B_cell_first")
LABELS_ARE = "machine-assisted, unvalidated"


def nk(s) -> str:
    return " ".join(str(s or "").split()).lower()


def wk(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def has_num(n: str, s) -> bool:
    """The binder's value test (src/evidence/gate.py:459-465), reproduced for the evaluator."""
    s = str(s)
    return n == re.sub(r"[^\d.\-]", "", s) or bool(re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", s))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*a: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"UNAVAILABLE: {e}"


# --- (2) gold assembly ------------------------------------------------------------------------------------------
def target_key(t: dict) -> tuple:
    return (nk(t["table_label"]), int(t["table_page"]), wk((t["row_label_levels"] or [""])[-1]),
            wk((t["column_header_levels"] or [""])[-1]), round(float(t["numeric_value"]), 9))


def assemble(cands: list[dict], runs: list[dict]) -> tuple[list[dict], list[dict]]:
    readings: dict[str, dict[str, dict]] = defaultdict(dict)
    for run in runs:
        for lab in run["labels"] or []:
            readings[lab["candidate_id"]][run["reader"]] = lab
    decided, pairs = [], []
    for c in cands:
        rd = {}
        for r in READERS:
            lab = readings[c["candidate_id"]].get(r)
            if lab is None:
                rd[r] = {"status": "MISSING_READING"}
                continue
            ok = not lab["claim_text_exact"] or lab["claim_text_exact"] in c["claim_text"]
            rd[r] = {**lab, "status": lab["status"] if ok else "INVALID_TRANSCRIPTION"}
        a, b = rd[READERS[0]], rd[READERS[1]]
        final, reason, claim, agreed = None, "", "", []
        if a["status"] == b["status"] == "VERIFIED_POSITIVE":
            ca, cb = a["claim_text_exact"], b["claim_text_exact"]
            if ca and cb and (ca in cb or cb in ca):
                claim = max(ca, cb, key=len)
                kb = {target_key(t): t for t in b["targets"]}
                agreed = [(t, kb[target_key(t)]) for t in a["targets"] if target_key(t) in kb]
                final = "VERIFIED_POSITIVE" if agreed else "AMBIGUOUS"
                reason = ("both readings VERIFIED_POSITIVE; " + (f"{len(agreed)} agreed target(s)" if agreed else
                          "no target agreed (table/page/row/leaf column/value)"))
            else:
                final, reason = "AMBIGUOUS", "both VERIFIED_POSITIVE but the claim sentences differ"
        elif a["status"] == b["status"]:
            final, reason = a["status"], "both readings agree"
        else:
            final, reason = "AMBIGUOUS", f"reader disagreement: A={a['status']}, B={b['status']}"
        d = {"candidate_id": c["candidate_id"], "paper_id": c["paper_id"], "claim_page": c["claim_page"],
             "reference": c["reference"], "harvested_claim_text": c["claim_text"], "context_sentence": c.get("context_sentence"),
             "table_refs": c["table_refs"], "final_status": final, "final_reason": reason, "gold_claim_text": claim,
             "readings": rd, "statuses_agree": a["status"] == b["status"]}
        decided.append(d)
        for ta, tb in agreed:
            dis = [k for k in ("claim_subject_kind", "table_orientation") if a.get(k) != b.get(k)]
            dis += [k for k in ("row_index_cell", "cell_text") if wk(ta[k]) != wk(tb[k])]
            pairs.append({"pair_id": f"PF{len(pairs) + 1:03d}", "candidate_id": c["candidate_id"], "paper_id": c["paper_id"],
                          "claim_text": claim, "claim_page": c["claim_page"], "reference": c["reference"],
                          "context_sentence": c.get("context_sentence"),
                          "table_label": ta["table_label"], "table_page": int(ta["table_page"]),
                          "row_label_levels": ta["row_label_levels"], "row_index_cell": ta["row_index_cell"],
                          "column_header_levels": ta["column_header_levels"], "cell_text": ta["cell_text"],
                          "numeric_value": ta["numeric_value"], "value_in_claim": ta["value_in_claim"],
                          "other_cells_with_same_value": max(ta["other_cells_with_same_value"], tb["other_cells_with_same_value"]),
                          "claim_subject_kind": a["claim_subject_kind"], "table_orientation": a["table_orientation"],
                          "reader_disagreements": dis, "reading_B_target": tb,
                          "verification_status": "VERIFIED_POSITIVE",
                          "verification_method": "manual: page render + PDF text layer; two blind machine readers "
                                                 "(claim-first, cell-first); exact-substring claim check",
                          "verification_confidence": "high" if ta["other_cells_with_same_value"] == 0 == tb["other_cells_with_same_value"] else "medium",
                          "labels_are": LABELS_ARE})
    return decided, pairs


def evidence_excerpt(path: Path, page: int, value: str, row: str) -> str:
    doc = pymupdf.open(path)
    lines = [ln.strip() for ln in doc[page - 1].get_text("text").splitlines() if ln.strip()]
    doc.close()
    hits = [i for i, ln in enumerate(lines) if has_num(value, ln)]
    near = [i for i in hits if wk(row) and wk(row) in wk(" ".join(lines[max(0, i - 6):i + 1]))]
    i = (near or hits or [None])[0]
    return "" if i is None else " | ".join(lines[max(0, i - 2): i + 2])


def stage_a_overlap(claim: str) -> list[str]:
    rows = list(csv.DictReader(open(STAGE_A_CSV, encoding="utf-8")))
    k = wk(claim)
    return sorted({f"{r['paper_id']}/{r['pair_id']}:{r['verification_status']}" for r in rows
                   if k and (k in wk(r["claim_text"]) or wk(r["claim_text"]) in k) and len(wk(r["claim_text"])) > 20})


# --- (3) evaluation ---------------------------------------------------------------------------------------------
def head_represent() -> types.ModuleType:
    src = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:src/evidence/represent.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    mod = types.ModuleType("src.evidence._represent_head")
    mod.__package__ = "src.evidence"
    exec(compile(src, "HEAD:src/evidence/represent.py", "exec"), mod.__dict__)
    return mod


def grounded_chunks(paper: dict, blocks_fn=None) -> list[dict]:
    if blocks_fn is None:
        return process_paper_grounded(paper)
    orig, R.blocks_from_pdf = R.blocks_from_pdf, blocks_fn
    try:
        return process_paper_grounded(paper)
    finally:
        R.blocks_from_pdf = orig


def canonical(p: dict) -> str:
    vt = {"rows": [[(p["row_label_levels"] or [""])[-1], p["value_in_claim"]]],
          "header": ["", " ".join(p["column_header_levels"])], "entity_column": 0}
    return O.canonical_claim(vt, 0, 1)


def table_cells_of(cells: list[dict], p: dict) -> list[dict]:
    lab = re.escape(nk(p["table_label"])) + r"\b"
    return [c for c in cells if c.get("page") == p["table_page"] and re.match(lab, nk(c.get("caption")))]


def row_match(c: dict, p: dict) -> str:
    lv = p["row_label_levels"] or [""]
    if nk(c["row_label"]) == nk(lv[-1]):
        return "exact"
    if any(nk(c["row_label"]) == nk(x) for x in lv[:-1]):
        return "outer_level_only"
    if wk(c["row_label"]) == wk(lv[-1]):
        return "whitespace_artifact"
    if p["row_index_cell"] and nk(c["row_label"]) == nk(p["row_index_cell"]):
        return "index_as_label"
    return "wrong"


def col_match(c: dict, p: dict) -> str:
    lv = p["column_header_levels"] or [""]
    full, leaf = " / ".join(lv), lv[-1]
    if nk(c["column_header"]) in (nk(full), nk(leaf)):
        return "exact"
    if len(lv) > 1 and nk(c["column_header"]) == nk(lv[0]):
        return "top_level_only"
    if wk(c["column_header"]) in (wk(full), wk(leaf)):
        return "whitespace_artifact"
    return "wrong"


def reconstruction(cells: list[dict], p: dict) -> dict:
    tab = table_cells_of(cells, p)
    if not tab:
        return {"table_structured": False, "cell": None, "row": None, "col": None, "value": None, "correct": False}
    hits = [c for c in tab if has_num(p["value_in_claim"], c["value"])]
    if not hits:
        return {"table_structured": True, "cell": None, "row": None, "col": None, "value": "missing", "correct": False}
    best = max(hits, key=lambda c: ((row_match(c, p) == "exact") + (col_match(c, p) == "exact"), -hits.index(c)))
    val = "exact" if nk(best["value"]) == nk(p["cell_text"]) else ("whitespace_artifact" if wk(best["value"]) == wk(p["cell_text"]) else "token")
    rm, cm = row_match(best, p), col_match(best, p)
    return {"table_structured": True, "cell": {k: best.get(k) for k in ("row_label", "column_header", "value", "caption", "row", "col", "page")},
            "row": rm, "col": cm, "value": val, "correct": rm == "exact" and cm == "exact"}


def run_claim(claim: str, chunks: list[dict], surnames: list[str], values: list[str], recs: list[dict]) -> dict:
    """One claim through the oracle's own run_case; bound correct = bound to one of `recs`' reconstructed target cells."""
    targets = [r["cell"] for r in recs if r["correct"]]
    case = O.run_case(claim, chunks, surnames, {"row_label": targets[0]["row_label"], "column_header": targets[0]["column_header"],
                                                "value": targets[0]["value"]} if targets else None)
    sb = case["binder"]
    keys = [{"row": t["row_label"], "col": t["column_header"], "value": t["value"], "caption": t["caption"]} for t in targets]
    hit = keys.index(sb["cell"]) if sb.get("status") == "bound" and sb.get("cell") in keys else None
    items = [i for i in case["gate_items"] if any(has_num(v, i["value"]) for v in values)] or case["gate_items"]
    return {"claim": claim, "binder_status": sb.get("status"), "binder": sb, "bound_correct": hit is not None,
            "bound_target_index": hit, "binder_input_cells": case["binder_input_cells"],
            "metric_column_cells": case["metric_column_cells"], "parse": case["parse"], "gate_items": items,
            "returned": any(i["final"] == G.RETURNED for i in items), "gate_final": [i["final"] for i in items],
            "gate_abstain_reasons": [i["abstain_reason"] for i in items]}


def binding_failure(recs: list[dict], ev: dict) -> str | None:
    if not any(r["table_structured"] for r in recs):
        return "representation:table_not_reconstructed"
    if not any(r["correct"] for r in recs):
        r = next(r for r in recs if r["table_structured"])
        if r["value"] == "missing":
            return "representation:target_value_not_in_reconstructed_table"
        bad = ([f"row_{r['row']}"] if r["row"] != "exact" else []) + ([f"column_{r['col']}"] if r["col"] != "exact" else [])
        return "representation:target_cell_" + "+".join(bad)
    if not ev["bound_correct"]:
        return "binder:" + ("bound_to_other_cell" if ev["binder_status"] == "bound" else str(ev["binder_status"]))
    return None


def gate_failure(kind: str, ev: dict) -> str:
    reason = ";".join(r for r in ev["gate_abstain_reasons"] if r) or "returned"
    if kind == "own_method" and not ev["returned"]:
        return f"gate:{reason}"
    if kind == "baseline_or_cited" and ev["returned"]:
        return "gate:returned_a_non_own_claim"
    return "none"


def evaluate(pairs: list[dict], ctx: dict) -> dict:
    pair_rows = []
    for p in pairs:
        c = ctx[p["paper_id"]]
        row = {"pair_id": p["pair_id"], "candidate_id": p["candidate_id"], "paper_id": p["paper_id"],
               "claim_subject_kind": p["claim_subject_kind"]}
        for rep in ("before", "after"):
            chunks = c[f"{rep}_chunks"]
            rec = reconstruction(G.paper_table_cells(chunks), p)
            ev = run_claim(canonical(p), chunks, c["surnames"], [p["value_in_claim"]], [rec])
            ev["failure"] = binding_failure([rec], ev) or "none"
            row[rep] = {"representation": sorted({x.get("representation") for x in chunks}), "chunks": len(chunks),
                        "chunks_with_table_cells": sum(1 for x in chunks if x.get("table_cells")),
                        "reconstruction": rec, "CANONICAL": ev}
        tb = [b for b in c["after_blocks"] if b["block_type"] == "table" and b["page_or_node"] == f"p{p['table_page']}"
              and re.match(re.escape(nk(p["table_label"])) + r"\b", nk(b["text"]))]
        row["after"]["table_block"] = [{k: b.get(k) for k in ("text", "table_parse_status", "table_fallback",
                                                                "table_row_label_rule", "table_shape")} for b in tb]
        pair_rows.append(row)
    by_claim: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_claim[p["candidate_id"]].append(p)
    claim_rows = []
    for cid, ps in by_claim.items():
        c = ctx[ps[0]["paper_id"]]
        row = {"candidate_id": cid, "paper_id": ps[0]["paper_id"], "claim_text": ps[0]["claim_text"],
               "claim_subject_kind": ps[0]["claim_subject_kind"], "pair_ids": [p["pair_id"] for p in ps]}
        for rep in ("before", "after"):
            recs = [next(r[rep]["reconstruction"] for r in pair_rows if r["pair_id"] == p["pair_id"]) for p in ps]
            ev = run_claim(ps[0]["claim_text"], c[f"{rep}_chunks"], c["surnames"], [p["value_in_claim"] for p in ps], recs)
            correct_pairs = [p["pair_id"] for p, r in zip(ps, recs) if r["correct"]]
            ev["bound_pair_id"] = correct_pairs[ev["bound_target_index"]] if ev["bound_correct"] else None
            ev["pairs_correctly_reconstructed"] = correct_pairs
            ev["failure"] = binding_failure(recs, ev) or gate_failure(row["claim_subject_kind"], ev)
            row[rep] = {"REAL": ev}
        claim_rows.append(row)
    return {"pairs": pair_rows, "claims": claim_rows}


def p003_stage_b(ctx_fn, head_blocks) -> dict:
    """The unchanged Stage B oracle (load_verified + run_all), ctx built as its main() builds it."""
    pairs = O.load_verified()
    after = O.run_all(pairs, ctx_fn(pairs, None))
    before = O.run_all(pairs, ctx_fn(pairs, head_blocks))
    stored = json.loads((HERE / "gold_binder_oracle.json").read_text(encoding="utf-8"))
    out = {"input": "verified_gold_pairs.json", "input_sha256": sha256(O.GOLD), "pairs": []}
    for pa, pb, ps, gp in zip(after["pairs"], before["pairs"], stored["pairs"], pairs):
        vt, tc = gp["verified_table"], gp["verified_table"]["target_cells"][0]
        gold = {"row": vt["rows"][tc["row"]][vt["entity_column"]], "col": vt["header"][tc["col"]], "value": vt["rows"][tc["row"]][tc["col"]]}
        r0 = {}
        for k in ("REAL|R0_current_pdf", "CANONICAL|R0_current_pdf"):
            ca = pa["cases"][k]
            cell = ca["binder"].get("cell") or {}
            r0[k] = {"claim": ca["claim"],
                     "before_stored": _case_view(ps["cases"][k]), "before_live": _case_view(pb["cases"][k]), "after": _case_view(ca),
                     "after_bound_cell_equals_verified_gold_cell": {x: cell.get(x) for x in ("row", "col", "value")} == gold,
                     "after_bound_cell_caption": cell.get("caption")}
        changed = {k: {"stored": _case_view(ps["cases"][k]), "after": _case_view(pa["cases"][k])}
                   for k in ps["cases"] if not k.endswith("R0_current_pdf") and ps["cases"][k] != pa["cases"][k]}
        out["pairs"].append({"key": pa["key"], "verified_gold_cell": gold, "r0": r0,
                             "verdict_before_stored": ps["verdict"], "verdict_after": pa["verdict"],
                             "live_before_equals_stored_before": all(pb["cases"][k] == ps["cases"][k] for k in ps["cases"]),
                             "r1_r2_cases_changed_vs_stored": changed})
    return out


def _case_view(c: dict) -> dict:
    it = (c.get("gate_items") or [{}])[0]
    return {"binder_status": c["binder_status"], "binder_input_cells": c["binder_input_cells"],
            "bound_cell": c["binder"].get("cell"), "oracle_bound_to_gold_cell": c["bound_to_gold_cell"],
            "gate_final": c["gate_final"], "gate_abstain_reasons": c["gate_abstain_reasons"],
            "attribution": it.get("attribution"), "provenance": it.get("page_or_node")}


# --- driver -----------------------------------------------------------------------------------------------------
def main(labels_path: Path, cands_path: Path) -> None:
    pymupdf.TOOLS.mupdf_display_errors(False)
    cdoc = json.loads(cands_path.read_text(encoding="utf-8"))
    runs = json.loads(labels_path.read_text(encoding="utf-8"))
    decided, pairs = assemble(cdoc["candidates"], runs)
    man = {r["paper_id"]: r for r in csv.DictReader(open(O.MANIFEST_V2, encoding="utf-8"))}
    acq = {r["paperId"]: r for r in json.loads(O.ACQ.read_text(encoding="utf-8"))}
    for p in pairs:
        path = Path(man[p["paper_id"]]["canonical_pdf_path"])
        p["evidence_excerpt"] = evidence_excerpt(path, p["table_page"], p["value_in_claim"], (p["row_label_levels"] or [""])[-1])
        p["overlaps_candidate_zip_pairs"] = stage_a_overlap(p["claim_text"])
    head = head_represent()

    def paper(pid: str) -> tuple[dict, Path, list[str]]:
        path = Path(man[pid]["canonical_pdf_path"])
        if sha256(path) != man[pid]["sha256"]:
            sys.exit(f"PDF hash mismatch for {pid} -- nothing written")
        rec = acq[path.stem]
        authors = rec["authors"] if isinstance(rec["authors"], list) else json.loads(rec["authors"])
        return {**rec, "pdf_path": str(path)}, path, [a.get("name", "") for a in authors if isinstance(a, dict)]

    ctx = {}
    for pid in sorted({p["paper_id"] for p in pairs}):
        rec, path, surnames = paper(pid)
        ctx[pid] = {"before_chunks": grounded_chunks(rec, head.blocks_from_pdf), "after_chunks": grounded_chunks(rec),
                    "after_blocks": R.build_document({"paper_id": pid, "source": "eval", "representation_type": "pdf"},
                                                     path.read_bytes())["blocks"],
                    "surnames": surnames, "pdf": str(path), "pdf_sha256": man[pid]["sha256"]}
    first = evaluate(pairs, ctx)
    second = evaluate(json.loads(json.dumps(pairs)), ctx)
    reproducible = json.dumps(first, sort_keys=True, default=str) == json.dumps(second, sort_keys=True, default=str)

    def oracle_ctx(ps: list[dict], blocks_fn) -> dict:     # the logic of stage_b_gold_binder_oracle.main() lines 226-238
        out = {}
        for pid in sorted({x["paper_id"] for x in ps}):
            rec, path, surnames = paper(pid)
            out[pid] = {"r0_chunks": grounded_chunks(rec, blocks_fn), "surnames": surnames, "pdf": str(path),
                        "pdf_sha256": man[pid]["sha256"]}
        return out
    p003 = p003_stage_b(oracle_ctx, head.blocks_from_pdf)

    meta = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": "src/evaluation/bottleneck_diagnosis/postfix_evaluate.py", "git_head": git("rev-parse", "HEAD"),
            "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"), "working_tree_represent_py_sha256": sha256(ROOT / "src/evidence/represent.py"),
            "python": sys.version.split()[0], "pymupdf": pymupdf.VersionBind, "labels_are": LABELS_ARE,
            "candidates_file_sha256": sha256(cands_path), "labels_file_sha256": sha256(labels_path),
            "reproducible_in_process_double_run": reproducible, "rules": __doc__, "harvest_rules": cdoc["rules"]}
    write_gold(decided, pairs, cdoc, meta)
    write_oracle(first, pairs, p003, meta)
    print(f"wrote {GOLD_JSON.name}, {GOLD_CSV.name}, {GOLD_MD.name}, {OR_JSON.name}, {OR_CSV.name}, {OR_MD.name} | "
          f"pairs {len(pairs)} | claims {len(first['claims'])} | reproducible {reproducible}")


# --- writers ----------------------------------------------------------------------------------------------------
def gold_counts(decided: list[dict], pairs: list[dict]) -> dict:
    n = len(decided)
    agree = sum(d["statuses_agree"] for d in decided)
    return {"candidates": n, "final_status": dict(Counter(d["final_status"] for d in decided)),
            "status_agreement_raw": f"{agree}/{n}",
            "status_agreement_label": "raw agreement between two machine readers (not a human-labelled kappa category)"
                                      + (" -- pilot, n<50" if n < 50 else ""),
            "reader_statuses": {r: dict(Counter(d["readings"][r]["status"] for d in decided)) for r in READERS},
            "verified_claims": len({p["candidate_id"] for p in pairs}), "verified_pairs": len(pairs),
            "papers": sorted({p["paper_id"] for p in pairs}),
            "by_reference": dict(Counter(p["reference"] for p in pairs)),
            "by_subject_kind_pairs": dict(Counter(p["claim_subject_kind"] for p in pairs)),
            "by_subject_kind_claims": dict(Counter(k for _, k in {(p["candidate_id"], p["claim_subject_kind"]) for p in pairs})),
            "by_orientation": dict(Counter(p["table_orientation"] for p in pairs)),
            "overlapping_candidate_zip_pairs": sorted({x for p in pairs for x in p["overlaps_candidate_zip_pairs"]})}


def write_gold(decided, pairs, cdoc, meta) -> None:
    counts = gold_counts(decided, pairs)
    GOLD_JSON.write_text(json.dumps({"artifact": "postfix_claim_cell_gold", "run": meta, "counts": counts,
                                     "harvest_stats": cdoc["per_paper_stats"], "verified_pairs": pairs,
                                     "candidates": decided}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    cols = ["pair_id", "candidate_id", "paper_id", "claim_page", "claim_text", "reference", "table_label", "table_page",
            "row_label", "row_label_levels", "row_index_cell", "column_header", "column_header_levels", "cell_text",
            "numeric_value", "value_in_claim", "other_cells_with_same_value", "claim_subject_kind", "table_orientation",
            "evidence_excerpt", "overlaps_candidate_zip_pairs", "verification_status", "verification_method",
            "verification_confidence", "reader_disagreements", "labels_are"]
    with open(GOLD_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in pairs:
            w.writerow({**{k: p.get(k) for k in cols}, "row_label": (p["row_label_levels"] or [""])[-1],
                        "row_label_levels": " > ".join(p["row_label_levels"]), "column_header": " / ".join(p["column_header_levels"]),
                        "column_header_levels": " > ".join(p["column_header_levels"]),
                        "overlaps_candidate_zip_pairs": ";".join(p["overlaps_candidate_zip_pairs"]),
                        "reader_disagreements": ";".join(p["reader_disagreements"])})
    L = ["# Post-fix claim → cell gold (mined from the 30 physical PDFs)", "",
         f"Labels are **{LABELS_ARE}**: two blind machine readers, not a human. Generated {meta['generated_at_utc']} at git "
         f"`{meta['git_head'][:12]}` (`{meta['git_branch']}`).", "",
         "## 1. How the set was built", "",
         "1. **Harvest** (`postfix_mine_claims.py`, deterministic; never calls find_tables, the binder or the gate): every "
         "sentence that names a table, or directly follows a sentence naming exactly one table (\"contextual\"), carries a "
         "meaningful number, and has that number printed on the table's page outside the sentence itself.",
         "2. **Two blind readings** of every candidate against the page renders + PDF text layer: reader A claim-first, "
         "reader B cell-first; neither saw the other, the candidate ZIP, Stage A or any pipeline output.",
         "3. **Agreement** (rules fixed before evaluation, see `postfix_evaluate.py`): a pair is VERIFIED_POSITIVE only when "
         "both readers say so, their claim sentences coincide, and they agree on table, page, row, leaf column and value. "
         "The claim is an exact substring of the PDF text layer (checked); nothing is paraphrased or generated.", "",
         "## 2. Counts", "",
         f"- Harvested candidates: **{counts['candidates']}**; final status: " +
         ", ".join(f"{k} {v}" for k, v in sorted(counts["final_status"].items())) + ".",
         f"- Reader status agreement: {counts['status_agreement_raw']} — {counts['status_agreement_label']}.",
         "- Reader status distributions: " + "; ".join(f"{r}: " + ", ".join(f"{k} {v}" for k, v in sorted(s.items()))
                                                        for r, s in counts["reader_statuses"].items()) + ".",
         f"- **Verified claims: {counts['verified_claims']}; verified pairs: {counts['verified_pairs']}** from "
         f"{len(counts['papers'])} papers ({', '.join(counts['papers'])}).",
         f"- By reference (pairs): {counts['by_reference']}; claim subject (claims): {counts['by_subject_kind_claims']}; "
         f"claim subject (pairs): {counts['by_subject_kind_pairs']}; table orientation (pairs): {counts['by_orientation']}.",
         "- The subject kind belongs to the claim sentence: a multi-value own-method claim can include a baseline's cell "
         "(e.g. 'ours 0.926 versus 0.920 for nnU-Net').",
         f"- Same sentence as one of the 44 candidate-ZIP pairs (the cell may differ): "
         f"{', '.join(counts['overlapping_candidate_zip_pairs']) or 'none'}.", "",
         "## 3. Verified pairs", "",
         "| Pair | Claim | Paper | Claim p. | Table (p.) | Row | Column | Cell | Subject | Claim text |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for p in pairs:
        L.append(f"| {p['pair_id']} | {p['candidate_id']} | {p['paper_id']} | {p['claim_page']} | {p['table_label']} (p{p['table_page']}) | "
                 f"{' > '.join(p['row_label_levels'])} | {' / '.join(p['column_header_levels'])} | `{p['cell_text']}` | "
                 f"{p['claim_subject_kind']} | {p['claim_text'][:160].replace('|', '/')}{'…' if len(p['claim_text']) > 160 else ''} |")
    L += ["", "## 4. Candidates not verified", "", "| Candidate | Paper | Final | Why |", "|---|---|---|---|"]
    for d in decided:
        if d["final_status"] != "VERIFIED_POSITIVE":
            L.append(f"| {d['candidate_id']} | {d['paper_id']} | {d['final_status']} | {d['final_reason']}; A: "
                     f"{(d['readings'][READERS[0]].get('reason') or '')[:110].replace('|', '/')} |")
    L += ["", "## 5. Limits", "",
          "- The readers are machine readers; the labels are suggestions until a human confirms them (RESEARCH_DIRECTIVE.md, Labelling authority).",
          "- The harvest only sees sentences that name a table (or directly follow one that does) and whose number is printed "
          "verbatim on the table page: claims stating a value in another format (0.91 vs 91%) or pointing to a table from "
          "further away are not in the set.",
          f"- Harvest totals per paper are in `{GOLD_JSON.name}` (`harvest_stats`)."]
    GOLD_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


def summarize(res: dict, pairs: list[dict]) -> dict:
    s = {}
    for rep in ("before", "after"):
        rec = [r[rep]["reconstruction"] for r in res["pairs"]]
        can = [r[rep]["CANONICAL"] for r in res["pairs"]]
        real = [c[rep]["REAL"] for c in res["claims"]]
        own = [e for e, c in zip(real, res["claims"]) if c["claim_subject_kind"] == "own_method"]
        s[rep] = {"pairs": len(rec), "claims": len(real),
                  "pairs_table_structured": sum(x["table_structured"] for x in rec),
                  "pairs_target_value_in_a_reconstructed_cell": sum(bool(x["cell"]) for x in rec),
                  "pairs_correctly_reconstructed": sum(x["correct"] for x in rec),
                  "pairs_row_match": dict(Counter(str(x["row"]) for x in rec)),
                  "pairs_column_match": dict(Counter(str(x["col"]) for x in rec)),
                  "CANONICAL_pairs": {"binder_status": dict(Counter(e["binder_status"] for e in can)),
                                      "bound_correct": sum(e["bound_correct"] for e in can),
                                      "returned": sum(e["returned"] for e in can),
                                      "failure": dict(Counter(e["failure"] for e in can))},
                  "REAL_claims": {"binder_status": dict(Counter(e["binder_status"] for e in real)),
                                  "bound_correct": sum(e["bound_correct"] for e in real),
                                  "returned": sum(e["returned"] for e in real),
                                  "own_method_claims": len(own),
                                  "own_method_bound_correct_and_returned": sum(e["bound_correct"] and e["returned"] for e in own),
                                  "failure": dict(Counter(e["failure"] for e in real)),
                                  "gate_abstain_reasons": dict(Counter(r for e in real for r in e["gate_abstain_reasons"] if r))}}
    return s


def write_oracle(res, pairs, p003, meta) -> None:
    summ = summarize(res, pairs)
    OR_JSON.write_text(json.dumps({"artifact": "postfix_binder_oracle", "run": meta, "p003_stage_b_acceptance": p003,
                                   "summary": summ, **res}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    by = {p["pair_id"]: p for p in pairs}
    cols = ["unit", "id", "pair_ids", "paper_id", "claim_subject_kind", "representation", "variant", "claim_text",
            "table_structured", "target_cell_reconstructed", "row_match", "column_match", "value_match", "reconstructed_cell",
            "binder_status", "bound_cell", "bound_correct", "gate_final", "gate_abstain_reason", "attribution", "returned", "failure"]

    def csv_row(unit, uid, pids, paper, kind, rep, var, e, rc):
        return {"unit": unit, "id": uid, "pair_ids": ";".join(pids), "paper_id": paper, "claim_subject_kind": kind,
                "representation": rep, "variant": var, "claim_text": e["claim"],
                "table_structured": rc.get("table_structured"), "target_cell_reconstructed": rc.get("correct"),
                "row_match": rc.get("row"), "column_match": rc.get("col"), "value_match": rc.get("value"),
                "reconstructed_cell": json.dumps(rc["cell"], ensure_ascii=False) if rc.get("cell") else "",
                "binder_status": e["binder_status"],
                "bound_cell": json.dumps(e["binder"].get("cell"), ensure_ascii=False) if e["binder"].get("cell") else "",
                "bound_correct": e["bound_correct"], "gate_final": ";".join(e["gate_final"]),
                "gate_abstain_reason": ";".join(x or "" for x in e["gate_abstain_reasons"]),
                "attribution": ";".join(str(i.get("attribution")) for i in e["gate_items"]),
                "returned": e["returned"], "failure": e["failure"]}
    with open(OR_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in res["pairs"]:
            for rep in ("before", "after"):
                w.writerow(csv_row("pair", r["pair_id"], [r["pair_id"]], r["paper_id"], r["claim_subject_kind"], rep, "CANONICAL",
                                   r[rep]["CANONICAL"], r[rep]["reconstruction"]))
        for c in res["claims"]:
            for rep in ("before", "after"):
                w.writerow(csv_row("claim", c["candidate_id"], c["pair_ids"], c["paper_id"], c["claim_subject_kind"], rep, "REAL",
                                   c[rep]["REAL"], {}))
    b, a = summ["before"], summ["after"]
    L = ["# Post-fix GOLD→BINDER evaluation (PDF table-cell fix)", "",
         f"Run {meta['generated_at_utc']}, git `{meta['git_head'][:12]}` (`{meta['git_branch']}`) + working-tree "
         f"`src/evidence/represent.py` (SHA-256 `{meta['working_tree_represent_py_sha256'][:16]}…`); PyMuPDF {meta['pymupdf']}. "
         f"In-process double run identical: **{meta['reproducible_in_process_double_run']}**. Gold labels are {LABELS_ARE}.", "",
         "BEFORE = git HEAD `blocks_from_pdf` (executed from `git show`); AFTER = working tree. Everything else — "
         "`process_paper_grounded`, `chunk_document`, `structural_bind`, `gate_paper` and the Stage B oracle — is unchanged. "
         "REAL claims are scored per claim (the binder returns one cell per claim), CANONICAL probes per pair; this unit "
         "split was fixed before any evaluation output was read (see the script docstring).", "",
         "## 1. P003/G002 — the unchanged Stage B oracle (`load_verified` + `run_all`)", ""]
    for pp in p003["pairs"]:
        L += [f"Verified gold cell: `{pp['verified_gold_cell']['row']}` × `{pp['verified_gold_cell']['col']}` = "
              f"`{pp['verified_gold_cell']['value']}`. Live BEFORE identical to the stored `gold_binder_oracle.json`: "
              f"**{pp['live_before_equals_stored_before']}**.", "",
              "| Claim | Before (stored Stage B) | Before (live HEAD) | After | Bound cell = verified gold cell |", "|---|---|---|---|---|"]
        for k, v in pp["r0"].items():
            f = lambda c: (f"`{c['binder_status']}`, {'/'.join(c['gate_final'])}"
                           f"{' (' + ';'.join(x for x in c['gate_abstain_reasons'] if x) + ')' if any(c['gate_abstain_reasons']) else ''}"
                           f", attribution {c['attribution']}")
            L.append(f"| {k.split('|')[0]} | {f(v['before_stored'])} | {f(v['before_live'])} | {f(v['after'])}; cell "
                     f"`{json.dumps({x: (v['after']['bound_cell'] or {}).get(x) for x in ('row', 'col', 'value')}, ensure_ascii=False)}` | "
                     f"{v['after_bound_cell_equals_verified_gold_cell']} |")
        L += ["", f"Oracle verdict production_path: before `{pp['verdict_before_stored']['production_path']}` → after "
                  f"`{pp['verdict_after']['production_path']}`. The oracle's own `bound_to_gold_cell` flag is always False for R0 "
                  "(it passes no target for R0, stage_b_gold_binder_oracle.py:174); gold identity is checked in the last column.", ""]
        if pp["r1_r2_cases_changed_vs_stored"]:
            L += ["R1/R2 (verified table injected on top of R0) changed because their R0 base now carries PDF cells:", ""]
            for k, v in pp["r1_r2_cases_changed_vs_stored"].items():
                L.append(f"- {k}: `{v['stored']['binder_status']}` ({v['stored']['binder_input_cells']} cells) → "
                         f"`{v['after']['binder_status']}` ({v['after']['binder_input_cells']} cells), bound "
                         f"`{json.dumps({x: (v['after']['bound_cell'] or {}).get(x) for x in ('row', 'col')}, ensure_ascii=False)}`, "
                         f"gate {'/'.join(v['after']['gate_final'])}")
            L.append("")
    kinds = dict(Counter(c["claim_subject_kind"] for c in res["claims"]))
    L += ["## 2. Mined verified set — before → after", "",
          f"{a['claims']} claims / {a['pairs']} pairs from {len({p['paper_id'] for p in pairs})} papers; claim subjects {kinds}.", "",
          "| | Before | After |", "|---|---|---|",
          f"| Pairs: table structured (cells on the table page) | {b['pairs_table_structured']} | {a['pairs_table_structured']} |",
          f"| Pairs: target value in a reconstructed cell | {b['pairs_target_value_in_a_reconstructed_cell']} | {a['pairs_target_value_in_a_reconstructed_cell']} |",
          f"| Pairs: target cell correctly reconstructed (table, row, column, value) | {b['pairs_correctly_reconstructed']} | {a['pairs_correctly_reconstructed']} |",
          f"| CANONICAL (pairs): binder status | {b['CANONICAL_pairs']['binder_status']} | {a['CANONICAL_pairs']['binder_status']} |",
          f"| CANONICAL (pairs): bound to the correct cell | {b['CANONICAL_pairs']['bound_correct']} | {a['CANONICAL_pairs']['bound_correct']} |",
          f"| CANONICAL (pairs): RETURNED | {b['CANONICAL_pairs']['returned']} | {a['CANONICAL_pairs']['returned']} |",
          f"| REAL (claims): binder status | {b['REAL_claims']['binder_status']} | {a['REAL_claims']['binder_status']} |",
          f"| REAL (claims): bound to one of its verified cells | {b['REAL_claims']['bound_correct']} | {a['REAL_claims']['bound_correct']} |",
          f"| REAL (claims): RETURNED | {b['REAL_claims']['returned']} | {a['REAL_claims']['returned']} |",
          f"| REAL own-method claims bound correctly and RETURNED | {b['REAL_claims']['own_method_bound_correct_and_returned']}/{b['REAL_claims']['own_method_claims']} | "
          f"{a['REAL_claims']['own_method_bound_correct_and_returned']}/{a['REAL_claims']['own_method_claims']} |",
          "", f"Row match of the reconstructed target (after): {a['pairs_row_match']}; column match: {a['pairs_column_match']}.", "",
          "## 3. Failure categories after the fix (earliest stage)", "",
          "- **REAL claims**: " + "; ".join(f"{k}: {v}" for k, v in sorted(a["REAL_claims"]["failure"].items(), key=lambda x: -x[1])),
          f"  - gate abstain reasons: {a['REAL_claims']['gate_abstain_reasons'] or 'none'}",
          "- **CANONICAL pairs** (representation → binder; gate reported, not judged): " +
          "; ".join(f"{k}: {v}" for k, v in sorted(a["CANONICAL_pairs"]["failure"].items(), key=lambda x: -x[1])), "",
          "## 4. Per claim (REAL, after)", "",
          "| Claim | Paper | Subject | Pairs | Correctly reconstructed | Binder → bound cell | Gate | Failure |", "|---|---|---|---|---|---|---|---|"]
    for c in res["claims"]:
        e = c["after"]["REAL"]
        cell = e["binder"].get("cell") or {}
        L.append(f"| {c['candidate_id']} | {c['paper_id']} | {c['claim_subject_kind']} | {', '.join(c['pair_ids'])} | "
                 f"{', '.join(e['pairs_correctly_reconstructed']) or '—'} | `{e['binder_status']}`"
                 f"{' ' + json.dumps({x: cell.get(x) for x in ('row', 'col', 'value')}, ensure_ascii=False) if cell else ''}"
                 f"{' ✓' if e['bound_correct'] else ''} | {'/'.join(e['gate_final'])} "
                 f"{';'.join(x for x in e['gate_abstain_reasons'] if x)} | {e['failure']} |")
    L += ["", "## 5. Per pair (after)", "",
          "| Pair | Paper | Table | Structured | Reconstructed target (row/col/value) | CANONICAL binder → gate | CANONICAL failure |",
          "|---|---|---|---|---|---|---|"]
    for r in res["pairs"]:
        p, rc, e = by[r["pair_id"]], r["after"]["reconstruction"], r["after"]["CANONICAL"]
        L.append(f"| {r['pair_id']} | {r['paper_id']} | {p['table_label']} p{p['table_page']} | {rc['table_structured']} | "
                 f"{rc['row']}/{rc['col']}/{rc['value']} | `{e['binder_status']}`{' ✓' if e['bound_correct'] else ''} → "
                 f"{'/'.join(e['gate_final'])} | {e['failure']} |")
    L += ["", "## 6. Tables that were not reconstructed (caption block status after the fix)", ""]
    seen = set()
    for r in res["pairs"]:
        for tb in r["after"].get("table_block", []):
            k = (r["paper_id"], tb["text"][:40])
            if not r["after"]["reconstruction"]["table_structured"] and k not in seen:
                seen.add(k)
                L.append(f"- {r['paper_id']} \"{tb['text'][:60]}\": {tb['table_parse_status']} — {tb['table_fallback']}")
        if not r["after"].get("table_block") and not r["after"]["reconstruction"]["table_structured"] and (r["paper_id"], "") not in seen:
            seen.add((r["paper_id"], ""))
            L.append(f"- {r['paper_id']} {by[r['pair_id']]['table_label']} p{by[r['pair_id']]['table_page']}: no caption block of "
                     "that label on the table page")
    L += ["", "Reproduce: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/postfix_evaluate.py "
          "<labels.json> <candidates.json>` (inputs recorded by SHA-256 in the JSON)."]
    OR_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
