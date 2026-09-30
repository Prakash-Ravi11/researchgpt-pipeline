"""Stage A -- verify the 44 candidate claim->cell pairs against the physical PDFs.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py --evidence-only
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py

Two inputs, kept apart on purpose:
  1. deterministic evidence, recomputed on every run, read-only on the candidate ZIP and on the
     canonical PDFs pinned by Phase 2.1 (hash-checked before use);
  2. stage_a_adjudications.json -- one recorded, machine-assisted decision per pair (status, reason,
     PDF observations). It is data, not code. Every decision is validated against the evidence.
Optional: stage_a_independent_verification.json (a second, independent machine-assisted pass),
compared pair by pair for agreement.

Outputs (never written if a validation fails): verified_gold_pairs.json, gold_pair_verification.csv,
gold_pair_verification_report.md. With --evidence-only the script prints the evidence and writes
nothing into the repository.

Decision rules (the same text was given to the independent verifiers). The unit is the whole pair:
(claim, candidate table, the FULL set of candidate cells). The first definitive failure decides.
  1 CLAIM   WRONG_CLAIM if the claim text is not in the PDF; or it is predominantly the table's own
            content (header/cell/caption text read as a sentence) with no natural-language sentence
            asserting a candidate cell value; or it only points to a table; or the only shared numbers
            are structural (section/table/page numbers, years, citations) or substrings; or the
            natural-language part is only qualitative/comparative. Mixed text: judge the sentence only.
  2 TABLE   WRONG_TABLE if the candidate table object (label/caption/page/region/content) is not the
            table the claim cites (body-text region, anchored on a sentence, other page, collapsed label).
  3 CELLS   every candidate cell must exist at its row/column in that PDF table AND be asserted by the
            claim for that row and column: otherwise WRONG_ROW / WRONG_COLUMN / WRONG_CELL (any other
            cell failure, incl. multi-cell sets with any unsupported cell, header/text fragments, merged
            cells, numeric coincidence); AMBIGUOUS if the value fits several cells equally or structure
            cannot be resolved; NOT_VERIFIABLE if the PDF lacks the evidence.
  4 VERIFIED_POSITIVE only if 1-3 pass. Claim values beyond the candidate cells -> incomplete, not a rejection.
Labels are machine-assisted and not validated by a human (RESEARCH_DIRECTIVE.md, "Labelling authority").
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from src.evidence.anchors import find_anchors  # noqa: E402  (production anchor rule, read-only use)

ZIP = ROOT / "src" / "evaluation" / "candidate_gold" / "researchgpt_candidate_gold_30_2026-09-28 (1).zip"
MANIFEST_V2 = HERE / "pdf_identity_manifest_v2.csv"
ADJ = HERE / "stage_a_adjudications.json"
INDEP = HERE / "stage_a_independent_verification.json"
OUT_JSON, OUT_CSV, OUT_MD = HERE / "verified_gold_pairs.json", HERE / "gold_pair_verification.csv", HERE / "gold_pair_verification_report.md"
STATUSES = ["VERIFIED_POSITIVE", "WRONG_CLAIM", "WRONG_TABLE", "WRONG_ROW", "WRONG_COLUMN", "WRONG_CELL",
            "AMBIGUOUS", "NOT_VERIFIABLE"]
NUM = re.compile(r"\d+(?:\.\d+)?")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", unicodedata.normalize("NFKD", s or "").casefold())


def toks(s: str) -> set[str]:
    return set(re.findall(r"[0-9a-z]{2,}", unicodedata.normalize("NFKD", s or "").casefold()))


def numbers(s: str) -> list[str]:
    return NUM.findall(s or "")


def meaningful_numbers(claim: str) -> list[str]:
    """Production anchor rule (drops years, [refs], Table/Section numbers, arXiv ids) plus a leading
    section-number strip, e.g. '2.1.1 MRI datasets' / '5.4 Ablation experiment'."""
    body = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+(?=[A-Z])", "", claim or "")
    return [v for v, _ in find_anchors(body)]


def load_candidates() -> tuple[list[dict], dict]:
    zf = zipfile.ZipFile(ZIP)
    members = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    pairs = []
    for n in sorted(x for x in zf.namelist() if re.fullmatch(r"P\d{3}\.json", x)):
        d = json.loads(zf.read(n))
        claims = {e["claim_id"]: e for e in d["10_quantitative_results"]["evidence"]}
        tabs = {t["table_id"]: t for t in d["TABLE_GROUND_TRUTH"]["tables"]}
        cells = {c["cell_id"]: c for c in d["TABLE_GROUND_TRUTH"]["cells"]}
        for p in d["CLAIM_TABLE_LINKING"]["gold_claim_cell_pairs"]:
            t = tabs[p["table_id"]]
            pairs.append({"key": f"{d['paper_id']}/{p['pair_id']}", "paper_id": d["paper_id"], "pair_id": p["pair_id"],
                          "claim_id": p["claim_id"], "claim_text": claims[p["claim_id"]]["source_text"],
                          "claim_page": claims[p["claim_id"]]["page"], "table_id": p["table_id"],
                          "table_printed_label": t["printed_label"], "table_caption": t["caption"],
                          "table_page": t["page"], "table_bbox": t["bbox"], "binding_basis": p["binding_basis"],
                          "candidate_confidence": p["confidence"], "cells": [cells[c] for c in p["cell_ids"]]})
    return pairs, members


def label_pages(doc, label: str) -> list[int]:
    """Pages where a line starts with the printed label (e.g. 'Table 3', 'TABLE IV')."""
    m = re.fullmatch(r"\s*table\s+([0-9]+|[ivxlcdm]+|[a-z])\s*", label or "", re.I)
    if not m:
        return []
    pat = re.compile(rf"^\s*table\s*{re.escape(m.group(1))}(?![0-9a-z])", re.I | re.M)
    return [i + 1 for i, pg in enumerate(doc) if pat.search(pg.get_text())]


def evidence_for(pair: dict, doc) -> dict:
    n = doc.page_count
    ctoks = toks(pair["claim_text"])
    page_cov = []
    for i in range(n):
        pt = toks(doc[i].get_text())
        page_cov.append(len(ctoks & pt) / len(ctoks) if ctoks else 0.0)
    best = max(range(n), key=lambda i: page_cov[i]) + 1
    tp = pair["table_page"]
    in_range = 1 <= tp <= n
    bbox = pymupdf.Rect(pair["table_bbox"]) if in_range else None
    bbox_text = doc[tp - 1].get_text(clip=bbox + (-3, -3, 3, 3)) if in_range else ""
    page_text = doc[tp - 1].get_text() if in_range else ""
    bbox_toks = toks(bbox_text)
    mnums = meaningful_numbers(pair["claim_text"])
    cap = norm(pair["table_caption"])[:60]
    cells = []
    for c in pair["cells"]:
        cn = numbers(c["raw_text"])
        prim = cn[0] if cn else None
        cells.append({
            "cell_id": c["cell_id"], "row_index": c["row_index"], "column_index": c["column_index"],
            "raw_text": c["raw_text"], "row_label": c["row_label"], "column_label": c["column_label"],
            "numeric_value": c["numeric_value"],
            "text_found_in_candidate_region": bool(norm(c["raw_text"])) and norm(c["raw_text"]) in norm(bbox_text),
            "text_found_on_table_page": bool(norm(c["raw_text"])) and norm(c["raw_text"]) in norm(page_text),
            "cell_numbers": cn,
            "numbers_whole_token_in_claim_meaningful": sorted(set(cn) & set(mnums)),
            "primary_number_occurrences_in_region": sum(1 for x in numbers(bbox_text) if x == prim) if prim else 0,
            "primary_number_occurrences_in_document": sum(1 for pg in doc for x in numbers(pg.get_text()) if x == prim) if prim else 0,
        })
    return {
        "claim_token_count": len(ctoks),
        "claim_coverage_on_stated_page": round(page_cov[pair["claim_page"] - 1], 3) if 1 <= pair["claim_page"] <= n else None,
        "claim_best_page": best, "claim_coverage_on_best_page": round(page_cov[best - 1], 3),
        "claim_share_inside_candidate_region": round(len(ctoks & bbox_toks) / len(ctoks), 3) if ctoks else 0.0,
        "claim_numbers": numbers(pair["claim_text"]), "claim_meaningful_numbers": mnums,
        "table_page_in_range": in_range, "caption_prefix_found_on_table_page": bool(cap) and cap in norm(page_text),
        "label_line_pages": label_pages(doc, pair["table_printed_label"]),
        "candidate_region_text_head": " ".join(bbox_text.split())[:240],
        "cells": cells,
    }


def main() -> None:
    evidence_only = "--evidence-only" in sys.argv
    pymupdf.TOOLS.mupdf_display_errors(False)
    man = {r["paper_id"]: r for r in csv.DictReader(open(MANIFEST_V2, encoding="utf-8"))}
    pairs, members = load_candidates()
    pdf_info, docs = {}, {}
    for pid in sorted({p["paper_id"] for p in pairs}):
        path = Path(man[pid]["canonical_pdf_path"])
        h = sha256(path)
        if h != man[pid]["sha256"]:
            sys.exit(f"PDF hash mismatch for {pid}: {h} != {man[pid]['sha256']} -- nothing written")
        docs[pid] = pymupdf.open(path)
        pdf_info[pid] = {"canonical_pdf_path": str(path), "sha256": h, "pages": docs[pid].page_count,
                         "phase2_1_status": man[pid]["identity_status_v2"]}
    ev = {p["key"]: evidence_for(p, docs[p["paper_id"]]) for p in pairs}
    if evidence_only:
        for p in pairs:
            e = ev[p["key"]]
            print(f"{p['key']:<10} cells={len(p['cells']):>2} claim_cov(stated p{p['claim_page']})={e['claim_coverage_on_stated_page']} "
                  f"best=p{e['claim_best_page']}({e['claim_coverage_on_best_page']}) in_region={e['claim_share_inside_candidate_region']} "
                  f"meaningful={e['claim_meaningful_numbers'][:8]} caption_found={e['caption_prefix_found_on_table_page']} "
                  f"label_pages={e['label_line_pages']} cells_in_region={sum(c['text_found_in_candidate_region'] for c in e['cells'])}/{len(e['cells'])} "
                  f"cells_value_in_claim={sum(bool(c['numbers_whole_token_in_claim_meaningful']) for c in e['cells'])}")
        return

    adj = json.loads(ADJ.read_text(encoding="utf-8"))
    decisions = adj["decisions"]
    problems = []
    if sorted(decisions) != sorted(p["key"] for p in pairs):
        problems.append(f"adjudicated keys != candidate keys: missing {sorted(set(p['key'] for p in pairs) - set(decisions))}, "
                        f"extra {sorted(set(decisions) - set(p['key'] for p in pairs))}")
    for p in pairs:
        d = decisions.get(p["key"])
        if not d:
            continue
        if d["status"] not in STATUSES:
            problems.append(f"{p['key']}: invalid status {d['status']!r}")
        if d["status"] == "VERIFIED_POSITIVE":
            e = ev[p["key"]]
            if not (e["claim_coverage_on_best_page"] >= 0.9 and e["table_page_in_range"] and d.get("pdf_table_page")):
                problems.append(f"{p['key']}: VERIFIED_POSITIVE without claim/table evidence in the PDF")
            for c in p["cells"]:
                obs = (d.get("cells") or {}).get(c["cell_id"])
                if not obs or not obs.get("asserted_by_claim") or not obs.get("pdf_observed_cell_text"):
                    problems.append(f"{p['key']}: VERIFIED_POSITIVE cell {c['cell_id']} lacks a PDF observation")
                    continue
                page = docs[p["paper_id"]][d["pdf_table_page"] - 1].get_text()
                if norm(obs["pdf_observed_cell_text"]) not in norm(page):
                    problems.append(f"{p['key']}: observed cell text {obs['pdf_observed_cell_text']!r} not on PDF page {d['pdf_table_page']}")
    if problems:
        sys.exit("VALIDATION FAILED -- nothing written:\n  " + "\n  ".join(problems))

    indep = {}
    if INDEP.exists():
        for g in json.loads(INDEP.read_text(encoding="utf-8"))["groups"]:
            for r in (g.get("result") or {}).get("pairs", []):
                indep[f"{r['paper_id']}/{r['pair_id']}"] = r

    records = []
    for p in pairs:
        d, e = decisions[p["key"]], ev[p["key"]]
        cell_recs = []
        for c, ce in zip(p["cells"], e["cells"]):
            obs = (d.get("cells") or {}).get(c["cell_id"], {})
            cell_recs.append({"cell_id": c["cell_id"], "candidate_row_index": c["row_index"],
                              "candidate_column_index": c["column_index"], "candidate_row_label": c["row_label"],
                              "candidate_column_label": c["column_label"], "candidate_cell_raw_text": c["raw_text"],
                              "candidate_numeric_value": c["numeric_value"], "evidence": ce,
                              "pdf_row_index": obs.get("pdf_row_index"), "pdf_column_index": obs.get("pdf_column_index"),
                              "pdf_row_label": obs.get("pdf_row_label"), "pdf_column_header": obs.get("pdf_column_header"),
                              "pdf_observed_cell_text": obs.get("pdf_observed_cell_text"),
                              "pdf_observed_numeric_value": obs.get("pdf_observed_numeric_value"),
                              "asserted_by_claim": obs.get("asserted_by_claim"),
                              "cell_assessed": bool(obs)})
        ind = indep.get(p["key"])
        records.append({
            "key": p["key"], "paper_id": p["paper_id"], "pair_id": p["pair_id"], "claim_id": p["claim_id"],
            "candidate_table_id": p["table_id"], "candidate_table_printed_label": p["table_printed_label"],
            "candidate_table_caption": p["table_caption"], "candidate_table_page": p["table_page"],
            "candidate_table_bbox": p["table_bbox"], "candidate_binding_basis": p["binding_basis"],
            "claim_text": p["claim_text"], "claim_page": p["claim_page"],
            "verification_status": d["status"], "verification_reason": d["reason"],
            "evidence_excerpt": d.get("evidence_excerpt", ""), "confidence": d["confidence"],
            "verification_method": d["method"], "labels_are": "machine-assisted, unvalidated",
            "claim_text_verified": d.get("claim_text_verified"), "claim_pdf_page": d.get("claim_pdf_page"),
            "pdf_table_label": d.get("pdf_table_label"), "pdf_table_page": d.get("pdf_table_page"),
            "incomplete_missing_values": d.get("incomplete_missing_values", []),
            "manual_or_ambiguous_interpretation": d.get("interpretation_note"),
            "verified_table": d.get("verified_table"),
            "first_pass_status": d.get("first_pass_status", d["status"]),
            "independent_status": ind["status"] if ind else None,
            # agreement is measured on the FIRST-pass status (before the independent pass was read)
            "independent_agrees": (ind["status"] == d.get("first_pass_status", d["status"])) if ind else None,
            "independent_reason": ind["reason"] if ind else None,
            "evidence": {k: v for k, v in e.items() if k != "cells"}, "cells": cell_recs,
        })

    counts = Counter(r["verification_status"] for r in records)
    by_paper = defaultdict(Counter)
    for r in records:
        by_paper[r["paper_id"]][r["verification_status"]] += 1
    agree = [r["independent_agrees"] for r in records if r["independent_agrees"] is not None]
    pos_agree = [r for r in records if r["independent_status"] is not None and
                 (r["first_pass_status"] == "VERIFIED_POSITIVE") == (r["independent_status"] == "VERIFIED_POSITIVE")]
    summary = {"candidate_pairs": len(records), **{s: counts.get(s, 0) for s in STATUSES},
               "papers_with_candidate_pairs": len(by_paper),
               "papers_with_verified_positive": sorted(p for p, c in by_paper.items() if c.get("VERIFIED_POSITIVE")),
               "verified_positive_cell_links": sum(len(r["cells"]) for r in records if r["verification_status"] == "VERIFIED_POSITIVE"),
               "independent_pass_pairs_compared": len(agree),
               "independent_exact_status_agreement": sum(agree),
               "independent_positive_vs_not_agreement": len(pos_agree),
               "final_status_agreement_after_resolution": sum(r["independent_status"] == r["verification_status"] for r in records),
               "resolved_disagreements": [f"{r['key']}: first pass {r['first_pass_status']} vs independent {r['independent_status']}"
                                          f" -> final {r['verification_status']}" for r in records if r["independent_agrees"] is False],
               "agreement_note": "first-pass statuses vs the independent pass; raw agreement only (pilot, n<50: no kappa, per RESEARCH_DIRECTIVE.md)"}
    meta = {"stage": "A", "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": "src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py",
            "git_head": _git("rev-parse", "HEAD"), "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "python": sys.version.split()[0], "pymupdf": pymupdf.VersionBind,
            "candidate_zip": str(ZIP.relative_to(ROOT)).replace("\\", "/"), "candidate_zip_sha256": sha256(ZIP),
            "candidate_zip_member_sha256": members, "adjudications_file_sha256": sha256(ADJ),
            "independent_file_sha256": sha256(INDEP) if INDEP.exists() else None,
            "pdf_identity_source": "pdf_identity_manifest_v2.csv (Phase 2.1)", "pdfs": pdf_info,
            "labels_are": "machine-assisted, unvalidated (not human-validated gold)",
            "adjudication_protocol": adj.get("protocol"), "rules": __doc__}
    OUT_JSON.write_text(json.dumps({"artifact": "verified_gold_pairs", "run": meta, "summary": summary,
                                    "verified_gold_pairs": [r for r in records if r["verification_status"] == "VERIFIED_POSITIVE"],
                                    "all_candidate_pairs": records}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    cols = ["paper_id", "pair_id", "claim_id", "candidate_table_id", "candidate_cell_id", "verification_status",
            "claim_text", "claim_page", "claim_pdf_page", "pdf_table_label", "pdf_table_page", "pdf_row_index",
            "pdf_column_index", "pdf_row_label", "pdf_column_header", "candidate_cell_raw_text", "pdf_observed_cell_text",
            "candidate_numeric_value", "pdf_observed_numeric_value", "asserted_by_claim", "cell_text_found_in_candidate_region",
            "verification_reason", "evidence_excerpt", "confidence", "verification_method", "independent_status", "labels_are"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            for c in r["cells"]:
                w.writerow({"paper_id": r["paper_id"], "pair_id": r["pair_id"], "claim_id": r["claim_id"],
                            "candidate_table_id": r["candidate_table_id"], "candidate_cell_id": c["cell_id"],
                            "verification_status": r["verification_status"], "claim_text": r["claim_text"],
                            "claim_page": r["claim_page"], "claim_pdf_page": r["claim_pdf_page"],
                            "pdf_table_label": r["pdf_table_label"], "pdf_table_page": r["pdf_table_page"],
                            "pdf_row_index": c["pdf_row_index"], "pdf_column_index": c["pdf_column_index"],
                            "pdf_row_label": c["pdf_row_label"], "pdf_column_header": c["pdf_column_header"],
                            "candidate_cell_raw_text": c["candidate_cell_raw_text"],
                            "pdf_observed_cell_text": c["pdf_observed_cell_text"] if c["cell_assessed"] else "not assessed (pair failed before the cell step)",
                            "candidate_numeric_value": c["candidate_numeric_value"],
                            "pdf_observed_numeric_value": c["pdf_observed_numeric_value"], "asserted_by_claim": c["asserted_by_claim"],
                            "cell_text_found_in_candidate_region": c["evidence"]["text_found_in_candidate_region"],
                            "verification_reason": r["verification_reason"], "evidence_excerpt": r["evidence_excerpt"],
                            "confidence": r["confidence"], "verification_method": r["verification_method"],
                            "independent_status": r["independent_status"], "labels_are": r["labels_are"]})

    # checkpoint: JSON and CSV agree
    back = list(csv.DictReader(open(OUT_CSV, encoding="utf-8")))
    per_pair = {(x["paper_id"], x["pair_id"]): x["verification_status"] for x in back}
    assert len(back) == sum(len(r["cells"]) for r in records), "CSV row count != JSON cell count"
    assert all(per_pair[(r["paper_id"], r["pair_id"])] == r["verification_status"] for r in records), "CSV/JSON status mismatch"
    assert len({(r["paper_id"], r["pair_id"]) for r in records}) == 44 == len(records), "not exactly 44 pairs"
    OUT_MD.write_text(report(records, summary, meta, by_paper), encoding="utf-8")
    print(f"wrote {OUT_JSON.name}, {OUT_CSV.name}, {OUT_MD.name}")
    print("checkpoint: 44 pairs adjudicated, one status each, positives validated against the PDF, CSV == JSON")
    print("summary:", json.dumps(summary, ensure_ascii=False))


def _git(*a: str) -> str:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        return f"UNAVAILABLE: {e}"


def report(records: list[dict], summary: dict, meta: dict, by_paper: dict) -> str:
    L = ["# Stage A — verification of the 44 candidate claim→cell pairs", "",
         "**Status of these labels:** machine-assisted and **not validated by a human** "
         "(RESEARCH_DIRECTIVE.md, \"Labelling authority\"). Only pairs marked `VERIFIED_POSITIVE` are treated as verified "
         "gold pairs downstream; the candidate dataset as a whole is **not** gold.", "",
         "| | |", "|---|---|",
         f"| Candidate source | `{meta['candidate_zip']}` (SHA-256 `{meta['candidate_zip_sha256'][:16]}…`) |",
         "| Physical PDFs | the canonical copies pinned by Phase 2.1 (`pdf_identity_manifest_v2.csv`), re-hashed before use |",
         f"| Run | {meta['generated_at_utc']}, git `{meta['git_head'][:12]}` (`{meta['git_branch']}`), PyMuPDF {meta['pymupdf']} |",
         "| Method | deterministic PDF evidence (recomputed each run) + one recorded adjudication per pair "
         "(`stage_a_adjudications.json`) + an independent second pass (`stage_a_independent_verification.json`) |",
         "| Reproduce | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -B src/evaluation/bottleneck_diagnosis/stage_a_verify_pairs.py` |",
         "", "## 1. Summary", "", f"- Total candidate pairs: **{summary['candidate_pairs']}**", ""]
    L += ["| Status | Pairs |", "|---|---|"] + [f"| {s} | {summary[s]} |" for s in STATUSES]
    L += ["", f"- Verified gold pairs: **{summary['VERIFIED_POSITIVE']}**, covering {summary['verified_positive_cell_links']} cell link(s), "
              f"in paper(s): {', '.join(summary['papers_with_verified_positive']) or 'none'}.",
          f"- Independent second pass: {summary['independent_pass_pairs_compared']} pairs compared; exact status agreement "
          f"{summary['independent_exact_status_agreement']}/{summary['independent_pass_pairs_compared']}; positive-vs-not agreement "
          f"{summary['independent_positive_vs_not_agreement']}/{summary['independent_pass_pairs_compared']} ({summary['agreement_note']}).",
          "", "## 2. Paper-level distribution", "", "| Paper | Pairs | " + " | ".join(STATUSES) + " |",
          "|---|---|" + "---|" * len(STATUSES)]
    for pid in sorted(by_paper):
        c = by_paper[pid]
        L.append(f"| {pid} | {sum(c.values())} | " + " | ".join(str(c.get(s, 0) or "") for s in STATUSES) + " |")
    L += ["", "## 3. Every pair", "", "| Pair | Status | Cells | Claim (start) | Reason | Confidence | Independent pass |",
          "|---|---|---|---|---|---|---|"]
    for r in records:
        L.append(f"| {r['key']} | **{r['verification_status']}** | {len(r['cells'])} | {' '.join(r['claim_text'].split())[:70]}… | "
                 f"{r['verification_reason']} | {r['confidence']} | {r['independent_status'] or '—'}"
                 f"{'' if r['independent_agrees'] in (None, True) else ' (disagrees)'} |")
    reasons = Counter(r["verification_status"] for r in records if r["verification_status"] != "VERIFIED_POSITIVE")
    L += ["", "## 4. Why pairs were rejected", ""]
    for s, n in reasons.most_common():
        L.append(f"- **{s}** ({n}): " + "; ".join(sorted({r['verification_reason'].split(' — ')[0] for r in records
                                                              if r['verification_status'] == s}))[:1200])
    notes = [r for r in records if r["manual_or_ambiguous_interpretation"]]
    L += ["", "## 5. Pairs that needed manual or ambiguous interpretation", ""]
    L += [f"- {r['key']} ({r['verification_status']}): {r['manual_or_ambiguous_interpretation']}" for r in notes] or ["- none"]
    dis = [r for r in records if r["independent_agrees"] is False]
    L += ["", "## 6. Disagreements with the independent pass and how they were resolved", ""]
    L += [f"- {r['key']}: this pass **{r['verification_status']}**, independent pass **{r['independent_status']}** "
          f"(\"{r['independent_reason'][:220]}\"). Resolution: {r['manual_or_ambiguous_interpretation'] or r['verification_reason']}"
          for r in dis] or ["- none"]
    L += ["", "## 7. Verified gold pairs", ""]
    for r in records:
        if r["verification_status"] == "VERIFIED_POSITIVE":
            L.append(f"- **{r['key']}** — claim p{r['claim_pdf_page']}: \"{r['claim_text_verified']}\" → {r['pdf_table_label']} (p{r['pdf_table_page']}): "
                     + "; ".join(f"row `{c['pdf_row_label']}` × column `{c['pdf_column_header']}` = `{c['pdf_observed_cell_text']}`" for c in r["cells"])
                     + (f". Incomplete: claim also states {', '.join(r['incomplete_missing_values'])}." if r["incomplete_missing_values"] else "."))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
