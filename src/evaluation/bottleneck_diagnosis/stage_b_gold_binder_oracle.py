"""Stage B -- GOLD->BINDER oracle, run on the VERIFIED_POSITIVE pairs of Stage A only.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_b_gold_binder_oracle.py

Production code is imported and called, never modified. The calls, in order:
  process_paper_grounded (the Stage 2 grounded path), blocks_from_jats / _jats_table_cells (the structured
  table -> table_cells converter), chunk_document, structural_bind, gate_paper.
No LLM, retrieval, embedding or network is used; every step is deterministic, and the whole oracle is run
twice in-process and compared.

Only the evidence representation is varied:
  R0 current       process_paper_grounded(paper) on the hash-pinned canonical PDF: exactly the chunks Stage 2
                   hands to the binder (Stage 5) when evidence grounding is enabled
  R1 gold/prod     R0 + the physically verified table, written as a JATS <table> in the PDF's own column order
                   and converted by the production JATS path (row label = first column, header = first row)
  R2 gold/entity   as R1, but with the verified entity column moved first, so the row label is the entity
                   the claim talks about (e.g. 'Proposed Method' rather than the index '04')
Claims:
  REAL             the verified claim sentence from the PDF (Stage A claim_text_verified)
  CANONICAL        "<entity> achieves a <column header> of <value>." -- only verified cell content, phrased
                   with the subject + verb + metric + number pattern the binder parses
  CANONICAL_ROWLABEL  "Row <row label> achieves a <column header> of <value>." -- the row named the way R1
                   labels it (the binder's subject regex needs a leading letter; 'Row' adds no fact)
Supplementary, reported separately and never counted as pairs: the CANONICAL probe for every row of the
verified table, so that row matching is seen on more than one row.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import pymupdf
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
import src.evidence.gate as G                                   # noqa: E402  (production, read-only use)
from src.evidence.anchors import NUMERIC_ANCHOR_RE              # noqa: E402
from src.evidence.chunker import chunk_document                 # noqa: E402
from src.evidence.represent import blocks_from_jats             # noqa: E402
from src.processing.pdf_parser import process_paper_grounded    # noqa: E402

GOLD = HERE / "verified_gold_pairs.json"
MANIFEST_V2 = HERE / "pdf_identity_manifest_v2.csv"
ACQ = Path(r"C:\Users\Praka\Downloads\rgpt-exp-parser\data\medical30_eval\raw_metadata\collected_papers.json")
OUT_JSON, OUT_CSV, OUT_MD = HERE / "gold_binder_oracle.json", HERE / "gold_binder_oracle.csv", HERE / "gold_binder_oracle_report.md"
CODE_PATH = [
    ("src/evidence/represent.py:12-15", "module contract: 'PDF table blocks do not [carry table_cells] (that is the bindability loss)'"),
    ("src/evidence/represent.py:172-176", "blocks_from_pdf types a block 'table' from its first line and attaches no table_cells"),
    ("src/evidence/represent.py:436-437", "build_document routes representation 'pdf' to blocks_from_pdf"),
    ("src/processing/pdf_parser.py:193-196", "Stage 2 copies table_cells onto chunk records only when the block has them"),
    ("src/evidence/chunker.py:50-52", "chunk_document carries table_cells only from blocks that have them"),
    ("src/evidence/gate.py:273-284", "paper_table_cells pools table_cells from the chunks (empty for a PDF paper)"),
    ("src/evidence/gate.py:432-434", "structural_bind returns status 'pdf_only' when no cells exist"),
    ("src/evidence/gate.py:528-531", "_gate_value abstains with 'unverifiable_binding' on pdf_only"),
    ("src/summarization/summarize.py:1344-1346", "the gate runs only when evidence_grounding.enabled"),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- oracle adapters (evaluation-only; production conversion does the real work) ------------------
def jats_table(vt: dict, order: list[int]) -> bytes:
    """The verified grid as a minimal JATS document, columns in `order`."""
    head = "".join(f"<th>{escape(vt['header'][i])}</th>" for i in order)
    body = "".join("<tr>" + "".join(f"<td>{escape(r[i])}</td>" for i in order) + "</tr>" for r in vt["rows"])
    return (f"<article><body><sec><title>Results</title><table-wrap><caption><p>{escape(vt['caption'])}</p></caption>"
            f"<table><tr>{head}</tr>{body}</table></table-wrap></sec></body></article>").encode("utf-8")


def column_orders(vt: dict) -> dict[str, list[int]]:
    n = len(vt["header"])
    e = vt["entity_column"]
    return {"R1_gold_production_convention": list(range(n)),
            "R2_gold_entity_first": [e] + [i for i in range(n) if i != e]}


def gold_chunks(vt: dict, order: list[int], paper_id: str) -> list[dict]:
    blocks = blocks_from_jats(jats_table(vt, order), paper_id, "oracle_verified_table")
    return chunk_document({"blocks": blocks})


def target_in_representation(vt: dict, order: list[int], row: int, col: int) -> dict:
    """What the production converter will call the target cell: row label = first column in `order`."""
    return {"row_label": vt["rows"][row][order[0]], "column_header": vt["header"][col], "value": vt["rows"][row][col]}


def entity_text(s: str) -> str:
    """Entity name without a trailing citation marker such as '[45]': the binder's subject pattern
    (gate.py:266-270) cannot contain '[' and must start with a letter; the citation is not part of the name."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", s).strip()


def canonical_claim(vt: dict, row: int, col: int) -> str:
    return f"The {entity_text(vt['rows'][row][vt['entity_column']])} achieves a {vt['header'][col]} of {vt['rows'][row][col]}."


def canonical_rowlabel_claim(vt: dict, row: int, col: int) -> str:
    return f"Row {vt['rows'][row][0]} achieves a {vt['header'][col]} of {vt['rows'][row][col]}."


def load_verified(path: Path = GOLD) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    pairs = doc["verified_gold_pairs"]
    bad = [p["key"] for p in pairs if p["verification_status"] != "VERIFIED_POSITIVE"]
    if bad:
        raise ValueError(f"oracle input must be VERIFIED_POSITIVE only; got {bad}")
    return pairs


# --- one oracle case -----------------------------------------------------------------------------
def parse_view(claim: str) -> dict:
    """How the binder reads the claim (mirrors structural_bind's own first steps, for the record only)."""
    sm = G._SUBJECT_RE.match(claim or "")
    subject = sm.group(1).strip() if sm else None
    if subject and G._OWN_ROW.search(subject):
        subject = None
    return {"numbers": NUMERIC_ANCHOR_RE.findall(claim or ""), "metric_tokens": sorted(G._metric_tokens(claim)),
            "subject": subject if subject else "OWN (implicit)"}


def run_case(claim: str, chunks: list[dict], surnames: list[str], target: dict | None) -> dict:
    cells = G.paper_table_cells(chunks)
    mt = G._metric_tokens(claim)
    sb = G.structural_bind(claim, chunks)
    gated = G.gate_paper({"results": claim}, chunks, "FULL_TEXT", surnames)
    items = [{k: it.get(k) for k in ("value", "final", "abstain_reason", "evidence_status", "attribution",
                                     "attribution_confidence", "section", "page_or_node", "block_id", "provenance_valid")}
             | {"structural_binding_status": (it.get("structural_binding") or {}).get("status")}
             for it in gated["evidence"]["results"]]
    correct = bool(target and sb.get("status") == "bound" and sb["cell"]["value"] == target["value"]
                   and sb["cell"]["col"] == target["column_header"] and sb["cell"]["row"] == target["row_label"])
    return {"binder_input_cells": len(cells),
            "metric_column_cells": sum(1 for c in cells if mt and G._col_matches_metric(c.get("column_header", ""), mt)),
            "parse": parse_view(claim), "binder": sb, "binder_status": sb.get("status"), "bound_to_gold_cell": correct,
            "gate_items": items, "gate_final": [i["final"] for i in items],
            "gate_abstain_reasons": [i["abstain_reason"] for i in items]}


def classify(real_ok: bool, canon_ok: bool) -> str:
    return {(True, True): "REAL_BOUND_CANONICAL_BOUND", (False, True): "REAL_FAIL_CANONICAL_BOUND",
            (False, False): "REAL_FAIL_CANONICAL_FAIL", (True, False): "OTHER"}[(real_ok, canon_ok)]


def first_failure(case: dict) -> str:
    if case["binder_status"] == "pdf_only":
        return "stage2_representation: PDF table has no structured cells (pdf_only)"
    if not case["bound_to_gold_cell"]:
        return f"binder: {case['binder_status']}" + (f" ({case['binder'].get('reason')})" if case["binder"].get("reason") else "")
    if any(f != "RETURNED" for f in case["gate_final"]):
        return "gate: " + ";".join(r or "" for r in case["gate_abstain_reasons"] if r)
    return "none (bound to the gold cell and RETURNED)"


def run_all(pairs: list[dict], docs_ctx: dict) -> dict:
    out = []
    for p in pairs:
        ctx = docs_ctx[p["paper_id"]]
        vt = p["verified_table"]
        tc = vt["target_cells"][0]
        row, col = tc["row"], tc["col"]
        r0 = ctx["r0_chunks"]
        reps = {"R0_current_pdf": (r0, None)}
        for name, order in column_orders(vt).items():
            reps[name] = (r0 + gold_chunks(vt, order, p["paper_id"]), target_in_representation(vt, order, row, col))
        claims = {"REAL": p["claim_text_verified"], "CANONICAL": canonical_claim(vt, row, col),
                  "CANONICAL_ROWLABEL": canonical_rowlabel_claim(vt, row, col)}
        cases = {}
        for rep, (chunks, target) in reps.items():
            for cname, claim in claims.items():
                if cname == "CANONICAL_ROWLABEL" and rep != "R1_gold_production_convention":
                    continue
                c = run_case(claim, chunks, ctx["surnames"], target)
                c["first_failure"] = first_failure(c)
                cases[f"{cname}|{rep}"] = {"claim_variant": cname, "representation": rep, "claim": claim, "target": target, **c}
        verdict = {"production_path": ("PDF_ONLY_NO_STRUCTURED_CELLS" if cases["REAL|R0_current_pdf"]["binder_status"] == "pdf_only"
                                       else cases["REAL|R0_current_pdf"]["binder_status"])}
        for rep in ("R1_gold_production_convention", "R2_gold_entity_first"):
            real, canon = cases[f"REAL|{rep}"], cases[f"CANONICAL|{rep}"]
            gate_rej = [k for k, cse in (("REAL", real), ("CANONICAL", canon))
                        if cse["bound_to_gold_cell"] and any(f != "RETURNED" for f in cse["gate_final"])]
            verdict[rep] = {"class": classify(real["bound_to_gold_cell"], canon["bound_to_gold_cell"]),
                            "cells_available_but_gate_rejected": gate_rej,
                            "real_first_failure": real["first_failure"], "canonical_first_failure": canon["first_failure"]}
        sweep = []
        for rr in range(len(vt["rows"])):
            for rep, order in column_orders(vt).items():
                chunks = r0 + gold_chunks(vt, order, p["paper_id"])
                tgt = target_in_representation(vt, order, rr, col)
                claim = canonical_claim(vt, rr, col)
                c = run_case(claim, chunks, ctx["surnames"], tgt)
                sweep.append({"row": rr, "representation": rep, "claim": claim, "binder_status": c["binder_status"],
                              "bound_to_gold_cell": c["bound_to_gold_cell"], "bound_cell": c["binder"].get("cell"),
                              "reason": c["binder"].get("reason"), "gate_final": c["gate_final"],
                              "gate_abstain_reasons": c["gate_abstain_reasons"]})
        out.append({"key": p["key"], "paper_id": p["paper_id"], "claim_id": p["claim_id"],
                    "gold": {"pdf_table_label": p["pdf_table_label"], "pdf_table_page": p["pdf_table_page"],
                             "claim_pdf_page": p["claim_pdf_page"], "cells": [{k: c[k] for k in ("cell_id", "pdf_row_label", "pdf_column_header", "pdf_observed_cell_text")} for c in p["cells"]]},
                    "cases": cases, "verdict": verdict, "supplementary_row_sweep": sweep})
    return {"pairs": out}


def r0_evidence(chunks: list[dict], value: str) -> dict:
    tables = [c for c in chunks if c.get("block_type") == "table"]
    return {"chunks": len(chunks), "chunks_with_table_cells": sum(1 for c in chunks if c.get("table_cells")),
            "table_blocks": len({c["block_id"] for c in tables}),
            "table_block_heads": sorted({(c["page_or_node"], " ".join(c["text"].split())[:90]) for c in tables}),
            "target_value_in_chunk_text": sorted({c["page_or_node"] for c in chunks if value in c["text"]}),
            "representation": sorted({c.get("representation") for c in chunks})}


def main() -> None:
    pymupdf.TOOLS.mupdf_display_errors(False)
    pairs = load_verified()
    man = {r["paper_id"]: r for r in csv.DictReader(open(MANIFEST_V2, encoding="utf-8"))}
    acq = {r["paperId"]: r for r in json.loads(ACQ.read_text(encoding="utf-8"))}
    ctx = {}
    for pid in sorted({p["paper_id"] for p in pairs}):
        path = Path(man[pid]["canonical_pdf_path"])
        if sha256(path) != man[pid]["sha256"]:
            sys.exit(f"PDF hash mismatch for {pid} -- nothing written")
        rec = acq[path.stem]
        paper = {**rec, "pdf_path": str(path)}
        chunks = process_paper_grounded(paper)
        authors = rec["authors"] if isinstance(rec["authors"], list) else json.loads(rec["authors"])
        ctx[pid] = {"r0_chunks": chunks, "surnames": [a.get("name", "") for a in authors if isinstance(a, dict)],
                    "pdf": str(path), "pdf_sha256": man[pid]["sha256"]}
    first = run_all(pairs, ctx)
    second = run_all(copy.deepcopy(pairs), ctx)
    reproducible = json.dumps(first, sort_keys=True, default=str) == json.dumps(second, sort_keys=True, default=str)

    cfg = {}
    for name in ("configs/config.yaml", "configs/staging_config.yaml"):
        p = ROOT / name
        if p.exists():
            y = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            cfg[name] = {"evidence_grounding.enabled": (y.get("evidence_grounding") or {}).get("enabled"),
                         "llm.temperature": (y.get("llm") or {}).get("temperature"), "llm.seed": (y.get("llm") or {}).get("seed")}
    r0 = {pid: r0_evidence(c["r0_chunks"], next(x["pdf_observed_cell_text"] for p in pairs if p["paper_id"] == pid for x in p["cells"]))
          for pid, c in ctx.items()}
    meta = {"stage": "B", "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": "src/evaluation/bottleneck_diagnosis/stage_b_gold_binder_oracle.py",
            "git_head": _git("rev-parse", "HEAD"), "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "python": sys.version.split()[0], "pymupdf": pymupdf.VersionBind,
            "input": "verified_gold_pairs.json", "input_sha256": sha256(GOLD),
            "input_pairs": [p["key"] for p in pairs], "input_statuses": sorted({p["verification_status"] for p in pairs}),
            "deterministic": "no LLM / retrieval / network; structural_bind and gate_paper are deterministic",
            "reproducible_in_process_double_run": reproducible, "configs": cfg,
            "pdfs": {pid: {"path": c["pdf"], "sha256": c["pdf_sha256"]} for pid, c in ctx.items()},
            "code_path_pdf_representation": CODE_PATH, "rules": __doc__}
    OUT_JSON.write_text(json.dumps({"artifact": "gold_binder_oracle", "run": meta, "r0_representation": r0, **first},
                                   indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    cols = ["paper_id", "claim_id", "claim_variant", "representation", "claim_text", "binder_input_cells",
            "metric_column_cells", "numbers", "metric_tokens", "subject", "binder_status", "bound_cell",
            "bound_to_gold_cell", "binder_reason", "gate_final", "gate_abstain_reason", "evidence_status",
            "attribution", "first_failure"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for pr in first["pairs"]:
            for c in pr["cases"].values():
                it = c["gate_items"][0] if c["gate_items"] else {}
                w.writerow({"paper_id": pr["paper_id"], "claim_id": pr["claim_id"], "claim_variant": c["claim_variant"],
                            "representation": c["representation"], "claim_text": c["claim"],
                            "binder_input_cells": c["binder_input_cells"], "metric_column_cells": c["metric_column_cells"],
                            "numbers": ";".join(c["parse"]["numbers"]), "metric_tokens": ";".join(c["parse"]["metric_tokens"]),
                            "subject": c["parse"]["subject"], "binder_status": c["binder_status"],
                            "bound_cell": json.dumps(c["binder"].get("cell"), ensure_ascii=False) if c["binder"].get("cell") else "",
                            "bound_to_gold_cell": c["bound_to_gold_cell"], "binder_reason": c["binder"].get("reason", ""),
                            "gate_final": ";".join(c["gate_final"]), "gate_abstain_reason": ";".join(r or "" for r in c["gate_abstain_reasons"]),
                            "evidence_status": it.get("evidence_status"), "attribution": it.get("attribution"),
                            "first_failure": c["first_failure"]})
    OUT_MD.write_text(report(first, meta, r0), encoding="utf-8")
    print(f"wrote {OUT_JSON.name}, {OUT_CSV.name}, {OUT_MD.name} | reproducible: {reproducible}")
    for pr in first["pairs"]:
        print(pr["key"], json.dumps(pr["verdict"], ensure_ascii=False))
        for k, c in pr["cases"].items():
            print(f"   {k:<48} binder={c['binder_status']:<17} gold_cell={c['bound_to_gold_cell']!s:<5} gate={c['gate_final']} "
                  f"{[r for r in c['gate_abstain_reasons'] if r]} | {c['first_failure']}")


def _git(*a: str) -> str:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        return f"UNAVAILABLE: {e}"


def report(res: dict, meta: dict, r0: dict) -> str:
    pairs = res["pairs"]
    cases = [c for p in pairs for c in p["cases"].values()]
    real = [c for c in cases if c["claim_variant"] == "REAL"]
    canon = [c for c in cases if c["claim_variant"] == "CANONICAL"]
    L = ["# Stage B — GOLD→BINDER oracle", "",
         f"Input: `{meta['input']}` (SHA-256 `{meta['input_sha256'][:16]}…`), **VERIFIED_POSITIVE pairs only**: "
         f"{', '.join(meta['input_pairs'])} (statuses in input: {', '.join(meta['input_statuses'])}). The verified labels are "
         "machine-assisted and not validated by a human (see the Stage A report).", "",
         "| | |", "|---|---|",
         f"| Run | {meta['generated_at_utc']}, git `{meta['git_head'][:12]}` (`{meta['git_branch']}`), PyMuPDF {meta['pymupdf']} |",
         "| Production code called (never modified) | `process_paper_grounded`, `blocks_from_jats`/`_jats_table_cells`, `chunk_document`, `structural_bind`, `gate_paper` |",
         f"| Determinism | {meta['deterministic']}; in-process double run identical: **{meta['reproducible_in_process_double_run']}** |",
         "| Reproduce | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_b_gold_binder_oracle.py` |",
         "", "## 1. Counts", "",
         f"- VERIFIED_POSITIVE pairs: **{len(pairs)}**. Tested with the real claim: **{len({c['claim'] for c in real}) and len(pairs)}**; "
         f"with the canonical claim: **{len({c['claim'] for c in canon}) and len(pairs)}**.",
         f"- Cases run: {len(cases)} (claim variant × representation), plus a supplementary row sweep over the verified table.", "",
         "| Claim | Representation | Cells visible to binder | Raw binder status | Bound to the gold cell | Gate final | Abstain reason | First failure |",
         "|---|---|---|---|---|---|---|---|"]
    for p in pairs:
        for c in p["cases"].values():
            L.append(f"| {c['claim_variant']} | {c['representation']} | {c['binder_input_cells']} | `{c['binder_status']}` | "
                     f"{c['bound_to_gold_cell']} | {', '.join(c['gate_final'])} | {', '.join(r for r in c['gate_abstain_reasons'] if r) or '—'} | "
                     f"{c['first_failure']} |")
    L += ["", "Real vs canonical, per representation (bound to the gold cell):", "",
          "| Representation | REAL bound | CANONICAL bound | Diagnostic class | Gate-rejected although bound |", "|---|---|---|---|---|"]
    for p in pairs:
        for rep in ("R1_gold_production_convention", "R2_gold_entity_first"):
            v = p["verdict"][rep]
            L.append(f"| {rep} | {p['cases']['REAL|' + rep]['bound_to_gold_cell']} | {p['cases']['CANONICAL|' + rep]['bound_to_gold_cell']} | "
                     f"**{v['class']}** | {', '.join(v['cells_available_but_gate_rejected']) or 'none'} |")
        L.append(f"| R0_current_pdf (production path) | {p['cases']['REAL|R0_current_pdf']['bound_to_gold_cell']} | "
                 f"{p['cases']['CANONICAL|R0_current_pdf']['bound_to_gold_cell']} | **{p['verdict']['production_path']}** | — |")
    L += ["", "## 2. Per pair", ""]
    for p in pairs:
        g = p["gold"]
        L += [f"### {p['key']}", "",
              f"- Gold: claim p{g['claim_pdf_page']} → {g['pdf_table_label']} p{g['pdf_table_page']}: " +
              "; ".join(f"`{c['pdf_row_label']}` × `{c['pdf_column_header']}` = `{c['pdf_observed_cell_text']}`" for c in g["cells"]), ""]
        for k, c in p["cases"].items():
            L.append(f"- **{k}** — claim: \"{c['claim']}\"")
            L.append(f"  - parse: numbers {c['parse']['numbers']}, metric tokens {c['parse']['metric_tokens']}, subject `{c['parse']['subject']}`; "
                     f"binder sees {c['binder_input_cells']} cells ({c['metric_column_cells']} under a matching metric column)")
            L.append(f"  - binder: `{json.dumps(c['binder'], ensure_ascii=False)}`")
            L.append(f"  - gate: " + "; ".join(f"{i['final']} ({i['abstain_reason'] or 'returned'}; evidence {i['evidence_status']}, "
                                                 f"attribution {i['attribution']}, provenance {i['page_or_node']})" for i in c["gate_items"]))
        L += ["", "Supplementary row sweep (canonical claim for every row of the verified table; not counted as pairs):", "",
              "| Row | Representation | Claim | Binder | Bound to gold cell | Gate |", "|---|---|---|---|---|---|"]
        for s in p["supplementary_row_sweep"]:
            L.append(f"| {s['row']} | {s['representation']} | {s['claim']} | `{s['binder_status']}` | {s['bound_to_gold_cell']} | "
                     f"{', '.join(s['gate_final'])} {', '.join(r for r in s['gate_abstain_reasons'] if r)} |")
    L += ["", "## 3. What the production PDF path gives the binder (R0)", ""]
    for pid, e in r0.items():
        L += [f"- {pid}: {e['chunks']} chunks ({', '.join(x for x in e['representation'] if x)}), **{e['chunks_with_table_cells']} with table_cells**; "
              f"{e['table_blocks']} blocks typed `table`: " + "; ".join(f"{pg}: \"{t}\"" for pg, t in e["table_block_heads"]) +
              f". The target value occurs as plain text in chunks from {', '.join(e['target_value_in_chunk_text']) or 'no chunk'}."]
    L += ["", "Code path (read, not modified) that leaves PDF tables without cells:", ""]
    L += [f"- `{ref}` — {what}" for ref, what in meta["code_path_pdf_representation"]]
    L += ["", "Configuration facts: " + "; ".join(f"`{k}`: evidence_grounding.enabled = {v['evidence_grounding.enabled']}"
                                                   for k, v in meta["configs"].items()) +
          ". With the production config the gate (and therefore the binder) is not run at all; R0 is the grounded (staging) path.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
