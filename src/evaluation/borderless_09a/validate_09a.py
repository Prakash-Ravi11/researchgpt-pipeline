"""Phase 09A validation — definitions in PREREG_09A.md (committed before any run).

    # Step 1: oracle ceiling (no table models)
    PYTHONIOENCODING=utf-8 .venv-09a/Scripts/python.exe -B src/evaluation/borderless_09a/validate_09a.py oracle
    # O18: flag-off identity vs the baseline commit (production venv, Python 3.10)
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/borderless_09a/validate_09a.py identity
    # Step 5: one child process per paper and policy, CPU only
    PYTHONIOENCODING=utf-8 .venv-09a/Scripts/python.exe -B src/evaluation/borderless_09a/validate_09a.py run

Each mode merges its own section into results.json and keeps the others. The production code path is
unchanged: process_paper_grounded -> build_document -> blocks_from_pdf (ruled path, then the
borderless hook when RGPT_BORDERLESS_POLICY=consensus). Evaluation uses the phase 08 evaluator
(postfix_evaluate.py) and the Stage B oracle's run_case, both unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIAG = ROOT / "src" / "evaluation" / "bottleneck_diagnosis"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DIAG))

import pymupdf                                                  # noqa: E402
import src.evidence.gate as G                                   # noqa: E402
import src.evidence.represent as R                              # noqa: E402
from src.evidence.schema import table_cell                      # noqa: E402
from src.processing.pdf_parser import process_paper_grounded    # noqa: E402
import postfix_evaluate as PE                                   # noqa: E402  (phase 08 evaluator, unchanged)
import stage_b_gold_binder_oracle as O                          # noqa: E402  (unchanged; main() never called)

RESULTS = HERE / "results.json"
CROPS = HERE / "crops"
BASELINE = "797a922"
CROP_DPI = 150
NEG = [("P019", "Table 1", 9), ("P019", "Table 2", 10), ("P027", "Table 1", 6), ("P020", "TABLE III", 14),
       ("P024", "Table 2", 8)]
GOLD = json.loads((DIAG / "postfix_claim_cell_gold.json").read_text(encoding="utf-8"))
PAIRS = GOLD["verified_pairs"]
P08 = json.loads((DIAG / "postfix_binder_oracle.json").read_text(encoding="utf-8"))
MAN = {r["paper_id"]: r for r in csv.DictReader(open(DIAG / "pdf_identity_manifest_v2.csv", encoding="utf-8"))}


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def target_set() -> tuple[list[dict], dict[tuple, list[str]]]:
    """Claims whose phase 08 failure is 'table not reconstructed', and their tables (must be 10 / 11)."""
    by_pid = {p["pair_id"]: p for p in PAIRS}
    claims = [c for c in P08["claims"] if c["after"]["REAL"]["failure"] == "representation:table_not_reconstructed"]
    tables: dict[tuple, list[str]] = defaultdict(list)
    for c in claims:
        for t in sorted({(by_pid[x]["paper_id"], by_pid[x]["table_label"], by_pid[x]["table_page"]) for x in c["pair_ids"]}):
            tables[t].append(c["candidate_id"])
    if (len(tables), len(claims)) != (10, 11):
        raise SystemExit(f"STOP: target set is {len(tables)} tables / {len(claims)} claims, not 10 / 11")
    return claims, dict(tables)


_ACQ: dict | None = None


def paper(pid: str) -> tuple[dict, Path, list[str]]:
    global _ACQ
    if _ACQ is None:
        _ACQ = {r["paperId"]: r for r in json.loads(O.ACQ.read_text(encoding="utf-8"))}
    path = Path(MAN[pid]["canonical_pdf_path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != MAN[pid]["sha256"]:
        raise SystemExit(f"PDF hash mismatch for {pid} -- nothing written")
    rec = _ACQ[path.stem]
    authors = rec["authors"] if isinstance(rec["authors"], list) else json.loads(rec["authors"])
    return {**rec, "pdf_path": str(path)}, path, [a.get("name", "") for a in authors if isinstance(a, dict)]


def caption_items(items: list[dict], label: str, page: int) -> list[dict]:
    """Blocks or chunks typed 'table' on `page` whose text starts with the table label."""
    rx = re.compile(re.escape(PE.nk(label)) + r"\b")
    return [x for x in items if x.get("block_type") == "table" and x.get("page_or_node") == f"p{page}"
            and rx.match(PE.nk(x.get("text")))]


def merge_results(section: str, payload) -> None:
    doc = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {"artifact": "phase09a_results"}
    doc[section] = payload
    RESULTS.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def versions(heavy: bool) -> dict:
    from importlib import metadata
    names = ["pymupdf", "pyyaml", "tqdm"] + (["docling", "docling-core", "docling-ibm-models", "docling-parse",
                                            "transformers", "timm", "torch", "torchvision"] if heavy else [])
    out = {"python": sys.version.split()[0]}
    for n in names:
        try:
            out[n] = metadata.version(n)
        except metadata.PackageNotFoundError:
            out[n] = None
    return out


# --- Step 1: oracle ceiling ---------------------------------------------------------------------------------------
def oracle() -> None:
    os.environ["RGPT_BORDERLESS_POLICY"] = "off"
    claims, _ = target_set()
    by_pid = {p["pair_id"]: p for p in PAIRS}
    cache: dict[str, list[dict]] = {}
    rows = []
    for c in claims:
        pid = c["paper_id"]
        rec, _, surnames = paper(pid)
        if pid not in cache:
            cache[pid] = process_paper_grounded(rec)
        chunks = [dict(x) for x in cache[pid]]
        ps = [by_pid[x] for x in c["pair_ids"]]
        gold_keys, problems = [], []
        for label, page in sorted({(p["table_label"], p["table_page"]) for p in ps}):
            caps = caption_items(chunks, label, page)
            if not caps:
                problems.append(f"no caption chunk for {label} p{page}")
                continue
            block_id = caps[0]["block_id"]
            caption = R._ws(caps[0]["text"])[:400]
            cells = []
            for i, p in enumerate(q for q in ps if (q["table_label"], q["table_page"]) == (label, page)):
                cell = table_cell(value=p["cell_text"], column_header=" / ".join(p["column_header_levels"]),
                                  row_label=(p["row_label_levels"] or [""])[-1], caption=caption,
                                  section=caps[0]["section"], row=i + 1, col=1)
                cell["page"] = page
                cells.append(cell)
                gold_keys.append({"row": cell["row_label"], "col": cell["column_header"], "value": cell["value"],
                                  "caption": cell["caption"]})
            for x in chunks:
                if x["block_id"] == block_id:
                    x["table_cells"], x["table_caption"] = cells, caption
        case = O.run_case(c["claim_text"], chunks, surnames, None)
        sb = case["binder"]
        bound = sb.get("status") == "bound" and sb.get("cell") in gold_keys
        rows.append({"candidate_id": c["candidate_id"], "paper_id": pid, "pair_ids": c["pair_ids"],
                     "tables": sorted({f"{p['table_label']} p{p['table_page']}" for p in ps}), "claim": c["claim_text"],
                     "oracle_cells": gold_keys, "problems": problems, "binder_status": sb.get("status"),
                     "bound_cell": sb.get("cell"), "binder_reason": sb.get("reason"), "parse": case["parse"],
                     "bound_to_gold_cell": bound, "gate_final": case["gate_final"],
                     "gate_abstain_reasons": case["gate_abstain_reasons"],
                     "classification": "bindable" if bound else "binder-blocked"})
    payload = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "versions": versions(False),
               "claims": rows, "bindable": [r["candidate_id"] for r in rows if r["bound_to_gold_cell"]],
               "binder_blocked": [r["candidate_id"] for r in rows if not r["bound_to_gold_cell"]]}
    merge_results("oracle", payload)
    print(f"oracle: {len(payload['bindable'])} bindable / {len(rows)}; binder-blocked: {payload['binder_blocked']}")
    for r in rows:
        print(f"  {r['candidate_id']} {r['paper_id']} {r['tables']}: {r['binder_status']} gold={r['bound_to_gold_cell']} "
              f"gate={r['gate_final']} {[x for x in r['gate_abstain_reasons'] if x]} {r['problems'] or ''}")


# --- O18: flag-off identity vs the baseline commit --------------------------------------------------------------
def baseline_module() -> types.ModuleType:
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASELINE}:src/evidence/represent.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    mod = types.ModuleType("src.evidence._represent_baseline")
    mod.__package__ = "src.evidence"
    exec(compile(src, f"{BASELINE}:src/evidence/represent.py", "exec"), mod.__dict__)
    return mod


def identity() -> None:
    os.environ.pop("RGPT_BORDERLESS_POLICY", None)
    policy = R._borderless_policy()
    base = baseline_module()
    per, ctx = {}, {}
    gold_papers = {p["paper_id"] for p in PAIRS}
    for pid in sorted(MAN):
        rec, path, surnames = paper(pid)
        data = path.read_bytes()
        b0 = json.dumps(base.blocks_from_pdf(data, pid, "x"), sort_keys=True, ensure_ascii=False)
        b1 = json.dumps(R.blocks_from_pdf(data, pid, "x"), sort_keys=True, ensure_ascii=False)
        c0, c1 = PE.grounded_chunks(rec, base.blocks_from_pdf), PE.grounded_chunks(rec)
        r0, r1 = json.dumps(c0, sort_keys=True, ensure_ascii=False), json.dumps(c1, sort_keys=True, ensure_ascii=False)
        per[pid] = {"blocks_identical": b0 == b1, "records_identical": r0 == r1, "blocks_sha256": sha(b1)[:16],
                    "records_sha256": sha(r1)[:16]}
        if pid in gold_papers:
            ctx[pid] = {"before_chunks": c0, "after_chunks": c1, "surnames": surnames,
                        "after_blocks": R.build_document({"paper_id": pid, "source": "eval", "representation_type": "pdf"},
                                                         data)["blocks"]}
    res = PE.evaluate(PAIRS, ctx)
    diff_pairs = [r["pair_id"] for r in res["pairs"]
                  if json.dumps({k: r["before"][k] for k in ("reconstruction", "CANONICAL")}, sort_keys=True, default=str)
                  != json.dumps({k: r["after"][k] for k in ("reconstruction", "CANONICAL")}, sort_keys=True, default=str)]
    diff_claims = [c["candidate_id"] for c in res["claims"]
                   if json.dumps(c["before"], sort_keys=True, default=str) != json.dumps(c["after"], sort_keys=True, default=str)]
    payload = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "baseline": BASELINE,
               "policy_resolved": policy, "versions": versions(False), "papers": per,
               "all_blocks_identical": all(v["blocks_identical"] for v in per.values()),
               "all_records_identical": all(v["records_identical"] for v in per.values()),
               "pairs_evaluated": len(res["pairs"]), "claims_evaluated": len(res["claims"]),
               "pairs_with_any_difference": diff_pairs, "claims_with_any_difference": diff_claims}
    merge_results("identity", payload)
    print(f"identity (policy={policy}): blocks identical {sum(v['blocks_identical'] for v in per.values())}/{len(per)}; "
          f"records identical {sum(v['records_identical'] for v in per.values())}/{len(per)}; "
          f"55-pair evaluation differences: pairs {diff_pairs or 'none'}, claims {diff_claims or 'none'}")


# --- Step 5: one child process per paper and policy -------------------------------------------------------------
def child(pid: str, policy: str, out: str) -> None:
    os.environ["RGPT_BORDERLESS_POLICY"] = policy
    rec, _, surnames = paper(pid)
    captured = []
    orig = R.build_document

    def capture(*a, **k):
        d = orig(*a, **k)
        captured.append(d)
        return d
    R.build_document = capture
    t0 = time.perf_counter()
    records = process_paper_grounded(rec)
    wall = time.perf_counter() - t0
    keys = ("block_id", "block_type", "page_or_node", "section", "text", "table_parse_status", "table_fallback",
            "table_backend", "table_bbox", "table_row_label_rule", "table_shape", "table_borderless")
    tables = [{k: b.get(k) for k in keys} | {"n_cells": len(b.get("table_cells") or [])}
              for b in captured[-1]["blocks"] if b["block_type"] == "table"]
    Path(out).write_text(json.dumps({"paper_id": pid, "policy": policy, "wall_seconds": round(wall, 2),
                                     "surnames": surnames, "records": records, "table_blocks": tables,
                                     "versions": versions(policy != "off")}, ensure_ascii=False, default=str),
                         encoding="utf-8")


def crop(path: Path, page: int, bbox, name: str) -> str | None:
    if not bbox:
        return None
    CROPS.mkdir(exist_ok=True)
    doc = pymupdf.open(path)
    r = pymupdf.Rect(bbox) + (-8, -8, 8, 8)
    doc[page - 1].get_pixmap(dpi=CROP_DPI, clip=r & doc[page - 1].rect).save(CROPS / name)
    doc.close()
    return f"crops/{name}"


def regression_reasons(pair_row: dict, claim_row: dict) -> list[str]:
    why = []
    if pair_row["before"]["reconstruction"]["correct"] and not pair_row["after"]["reconstruction"]["correct"]:
        why.append("reconstruction_lost")
    for tag, b, a in (("CANONICAL", pair_row["before"]["CANONICAL"], pair_row["after"]["CANONICAL"]),
                      ("REAL", claim_row["before"]["REAL"], claim_row["after"]["REAL"])):
        if b["bound_correct"] and not a["bound_correct"]:
            why.append(f"{tag}:bound_lost")
        if b["returned"] and not a["returned"]:
            why.append(f"{tag}:return_lost")
        if not b["returned"] and a["returned"] and not a["bound_correct"]:
            why.append(f"{tag}:unverified_return")
    return why


def run() -> None:
    from src.evidence import borderless as B            # pure helpers only; heavy deps load inside the children
    claims, tables = target_set()
    gold_papers = sorted({p["paper_id"] for p in PAIRS})
    papers = sorted(set(gold_papers) | {n[0] for n in NEG})
    tmp = Path(tempfile.mkdtemp(prefix="p09a_"))
    outputs: dict[str, dict[str, dict]] = {"off": {}, "consensus": {}}
    unmeasured, child_wall = [], {}
    try:
        for policy in ("off", "consensus"):
            for pid in papers:
                out = tmp / f"{pid}_{policy}.json"
                env = {**os.environ, "RGPT_BORDERLESS_POLICY": policy, "CUDA_VISIBLE_DEVICES": "",
                       "PYTHONIOENCODING": "utf-8"}
                t0 = time.perf_counter()
                p = subprocess.run([sys.executable, "-B", str(Path(__file__)), "child", pid, policy, str(out)], env=env,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
                child_wall[f"{pid}:{policy}"] = round(time.perf_counter() - t0, 1)
                print(f"  child {pid} {policy}: rc={p.returncode} {child_wall[f'{pid}:{policy}']}s", flush=True)
                if p.returncode != 0 or not out.exists():
                    unmeasured.append({"paper_id": pid, "policy": policy, "returncode": p.returncode,
                                       "error": (p.stderr or "")[-3000:]})
                    continue
                outputs[policy][pid] = json.loads(out.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    measured = [pid for pid in gold_papers if pid in outputs["off"] and pid in outputs["consensus"]]
    pairs = [p for p in PAIRS if p["paper_id"] in measured]
    ctx = {pid: {"before_chunks": outputs["off"][pid]["records"], "after_chunks": outputs["consensus"][pid]["records"],
                 "after_blocks": outputs["consensus"][pid]["table_blocks"], "surnames": outputs["off"][pid]["surnames"]}
           for pid in measured}
    res = PE.evaluate(pairs, ctx)
    claim_rows = {c["candidate_id"]: c for c in res["claims"]}
    by_pid = {p["pair_id"]: p for p in PAIRS}
    oracle_rows = {r["candidate_id"]: r for r in (json.loads(RESULTS.read_text(encoding="utf-8")).get("oracle", {})
                                                   .get("claims", []) if RESULTS.exists() else [])}

    # per target table
    table_rows = []
    for (pid, label, page), cids in sorted(tables.items()):
        row = {"paper_id": pid, "table": label, "page": page, "claims": cids}
        if pid not in outputs["consensus"]:
            row["status"] = "UNMEASURED"
            table_rows.append(row)
            continue
        blk = caption_items(outputs["consensus"][pid]["table_blocks"], label, page)
        det = (blk[0].get("table_borderless") if blk else None) or {}
        row.update({"caption_block_found": bool(blk), "table_parse_status": blk[0]["table_parse_status"] if blk else None,
                    "table_fallback": blk[0]["table_fallback"] if blk else None, "verdict": det.get("verdict"),
                    "code": det.get("code"), "error": det.get("error"), "agree": det.get("agree")})
        cmap = {cc["candidate_id"]: cc for cc in claims}
        tpairs = [by_pid[x] for c in cids for x in cmap[c]["pair_ids"]
                  if (by_pid[x]["table_label"], by_pid[x]["table_page"]) == (label, page)]
        for k in ("A", "B"):
            d = (det.get("parsers") or {}).get(k) or {}
            pc = d.get("cells") or []
            row[k] = {"candidate": d.get("candidate"), "shape": d.get("shape"), "header": d.get("header"),
                      "rule": d.get("rule"), "G1": (d.get("G1") or {}).get("pass"), "G2": (d.get("G2") or {}).get("pass"),
                      "G3": (d.get("G3") or {}).get("pass"), "G3_problem": (d.get("G3") or {}).get("problem"),
                      "false_cells_G1": len((d.get("G1") or {}).get("failures") or []),
                      "G2_missing": len((d.get("G2") or {}).get("missing") or []),
                      "G2_duplicated": len((d.get("G2") or {}).get("duplicated") or []),
                      "absorbed_text": d.get("absorbed_text") or [], "seconds_page": d.get("seconds_page"),
                      "captions_on_page": d.get("captions_on_page"), "error": d.get("error"),
                      "G1_failures": (d.get("G1") or {}).get("failures"), "G2_missing_words": (d.get("G2") or {}).get("missing"),
                      "G2_duplicated_words": (d.get("G2") or {}).get("duplicated"),
                      "target_cells_correct": sum(PE.reconstruction(pc, p)["correct"] for p in tpairs),
                      "target_cells": len(tpairs)}
        row["triples_only_in_A"], row["triples_only_in_B"] = det.get("triples_only_in_A"), det.get("triples_only_in_B")
        row["accepted_target_cells_correct"] = sum(res_p["after"]["reconstruction"]["correct"] for res_p in res["pairs"]
                                                   if res_p["pair_id"] in {p["pair_id"] for p in tpairs})
        if det.get("verdict") == "accepted":
            row["crop"] = crop(Path(MAN[pid]["canonical_pdf_path"]), page, blk[0].get("table_bbox"),
                               f"{pid}_{label.replace(' ', '')}_p{page}_accepted.png")
        table_rows.append(row)

    # per target claim
    claim_trans = []
    for c in claims:
        cid = c["candidate_id"]
        cr = claim_rows.get(cid)
        orc = oracle_rows.get(cid, {})
        if not cr:
            claim_trans.append({"candidate_id": cid, "paper_id": c["paper_id"], "status": "UNMEASURED"})
            continue
        b, a = cr["before"]["REAL"], cr["after"]["REAL"]
        claim_trans.append({"candidate_id": cid, "paper_id": c["paper_id"],
                            "oracle": {"binder_status": orc.get("binder_status"), "bound_to_gold_cell": orc.get("bound_to_gold_cell"),
                                       "gate_final": orc.get("gate_final")},
                            "before": {"binder_status": b["binder_status"], "bound_correct": b["bound_correct"],
                                       "gate_final": b["gate_final"], "failure": b["failure"]},
                            "after": {"binder_status": a["binder_status"], "bound_correct": a["bound_correct"],
                                      "gate_final": a["gate_final"], "failure": a["failure"],
                                      "bound_cell": a["binder"].get("cell")}})

    # NEG
    neg_rows, p2_fail, p2_unmeasured = [], [], []
    for pid, label, page in NEG:
        out = outputs["consensus"].get(pid)
        blk = caption_items(out["table_blocks"], label, page) if out else []
        if not blk:
            neg_rows.append({"paper_id": pid, "table": label, "page": page, "status": "UNMEASURED",
                             "reason": "paper output missing" if not out else "caption block not located"})
            p2_unmeasured.append(f"{pid} {label}")
            continue
        det = blk[0].get("table_borderless") or {}
        cells = [cell for ch in out["records"] if ch.get("block_id") == blk[0]["block_id"] for cell in (ch.get("table_cells") or [])]
        uniq = list({json.dumps(x, sort_keys=True): x for x in cells}.values())
        bb = blk[0].get("table_bbox") or next((d.get("bbox") for d in (det.get("parsers") or {}).values() if d and d.get("bbox")), None) \
            or det.get("caption_bbox")
        neg_rows.append({"paper_id": pid, "table": label, "page": page, "verdict": det.get("verdict") or "not_routed",
                         "code": det.get("code"), "table_fallback": blk[0]["table_fallback"], "accepted_cells": uniq,
                         "parsers": {k: {x: (d or {}).get(x) for x in ("candidate", "shape", "header", "seconds_page")}
                                     | {g: ((d or {}).get(g) or {}).get("pass") for g in ("G1", "G2", "G3")}
                                     for k, d in (det.get("parsers") or {}).items()},
                         "crop": crop(Path(MAN[pid]["canonical_pdf_path"]), page, bb,
                                      f"{pid}_{label.replace(' ', '')}_p{page}_NEG.png")})

    # regression, P4, canary
    regressions = []
    for pr in res["pairs"]:
        why = regression_reasons(pr, claim_rows[pr["candidate_id"]])
        if why:
            regressions.append({"pair_id": pr["pair_id"], "reasons": why})
    accepted_cells, absent = [], []
    for pid, out in outputs["consensus"].items():
        acc_ids = {b["block_id"] for b in out["table_blocks"] if (b.get("table_backend") or "").startswith("borderless")}
        if not acc_ids:
            continue
        doc = pymupdf.open(MAN[pid]["canonical_pdf_path"])
        seen = set()
        for ch in out["records"]:
            if ch.get("block_id") in acc_ids:
                for cell in ch.get("table_cells") or []:
                    k = (ch["block_id"], cell["row"], cell["col"])
                    if k in seen:
                        continue
                    seen.add(k)
                    accepted_cells.append((pid, cell))
                    words = B.page_words(doc[cell["page"] - 1])
                    if not B.find_runs(words, cell["value"]):
                        absent.append({"paper_id": pid, "cell": cell})
        doc.close()
    canary = sum(1 for out in outputs["consensus"].values() for ch in out["records"] for cell in (ch.get("table_cells") or [])
                 if "\n" in str(cell.get("value", "")))

    # criteria
    bound_claims = [t for t in claim_trans if (t.get("after") or {}).get("bound_correct")]
    p1 = len(bound_claims) >= 3 and len({t["paper_id"] for t in bound_claims}) >= 2
    neg_accepted = [n for n in neg_rows if n.get("verdict") == "accepted"]
    if p2_unmeasured:
        p2 = "UNMEASURED"
    elif neg_accepted:
        p2 = "MANUAL_CHECK_REQUIRED"
    else:
        p2 = True
    p3 = not regressions and not [u for u in unmeasured if u["paper_id"] in gold_papers]
    p4 = not absent
    crit = {"P1": {"pass": p1, "target_claims_bound": [t["candidate_id"] for t in bound_claims],
                   "papers": sorted({t["paper_id"] for t in bound_claims})},
            "P2": {"pass": p2, "neg_accepted": [f"{n['paper_id']} {n['table']}" for n in neg_accepted],
                   "neg_unmeasured": p2_unmeasured},
            "P3": {"pass": p3, "regressions": regressions, "pairs_compared": len(res["pairs"])},
            "P4": {"pass": p4, "accepted_cells": len(accepted_cells), "absent_from_text_layer": absent}}
    if all(crit[k]["pass"] is True for k in crit):
        decision = "ENABLE: all four PASS -> separate commit 'enable borderless_policy=consensus by default'"
    elif crit["P2"]["pass"] is not True or crit["P4"]["pass"] is not True:
        decision = "KEEP DEFAULT OFF: P2 or P4 not passed (see criteria)"
    elif not p3:
        decision = "KEEP DEFAULT OFF: P3 failed (regressions)"
    else:
        decision = "KEEP DEFAULT OFF: only P1 failed (safe, fewer than 3 claims gained)"
    payload = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "papers": papers, "papers_measured_for_pairs": measured, "unmeasured": unmeasured,
               "child_wall_seconds": child_wall,
               "versions": {"off": next(iter(outputs["off"].values()), {}).get("versions"),
                            "consensus": next(iter(outputs["consensus"].values()), {}).get("versions")},
               "target_tables": table_rows, "target_claims": claim_trans, "neg": neg_rows,
               "summary_off_vs_on": PE.summarize(res, pairs), "criteria": crit, "canary_newline_cells": canary,
               "decision": decision,
               "all_borderless_blocks": {pid: [{k: b.get(k) for k in ("page_or_node", "text", "table_parse_status",
                                                                     "table_fallback", "table_backend", "n_cells")}
                                               | {"verdict": (b.get("table_borderless") or {}).get("verdict"),
                                                  "code": (b.get("table_borderless") or {}).get("code"),
                                                  "seconds": {k: ((b.get("table_borderless") or {}).get("parsers") or {})
                                                              .get(k, {}).get("seconds_page") for k in ("A", "B")}}
                                               for b in out["table_blocks"] if b.get("table_borderless")]
                                         for pid, out in outputs["consensus"].items()}}
    merge_results("validation", payload)
    print(json.dumps({"criteria": {k: v["pass"] for k, v in crit.items()}, "canary": canary, "decision": decision,
                      "unmeasured": [(u["paper_id"], u["policy"]) for u in unmeasured]}, indent=1))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "oracle":
        oracle()
    elif mode == "identity":
        identity()
    elif mode == "child":
        child(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "run":
        run()
    else:
        raise SystemExit(f"unknown mode {mode}")
