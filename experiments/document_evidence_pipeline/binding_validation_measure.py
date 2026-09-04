"""Binding-contract validation on the expanded structured set (Phase 5).

The Phase-5 binding contract (structural_bind, cases 1-5) was validated on 2 JATS
papers -> Matrix C sensitivity 0.667 on n=3 positives. The re-acquired medical
corpus (runs/medical_reacquire/) now carries 11 Europe PMC JATS papers with
structured table cells. This harness re-runs the whole binding measurement on the
medical corpus (JATS-derived structure) so it can be compared, side by side and
NOT pooled, against the canonical corpus (LaTeX-derived structure, already in
runs/structural_binding/).

Isolated: reads runs/medical_reacquire/raw_metadata + pdfs; writes ONLY under
runs/binding_validation/. Six stages unchanged; no gate/selector/acquisition
edits. Seeded path (temperature 0, seed 42), clean extraction cache.

  python -u experiments/document_evidence_pipeline/binding_validation_measure.py

Tasks:
  1  process the 11 JATS papers through Stage 2 + VERIFY structured cells exist
     (stop condition: near-zero cells across the 11)
  2  binding measurement over the medical corpus with the real gate active
  3  4 adversarial probe classes on the 11 JATS papers (acceptances MUST be 0)
  4  Test 2 mutation suite incl. medical JATS papers, v2 oracle, 3 matrices
     (run separately: gate_sensitivity.py --medical)
  5  cross-domain comparison canonical(LaTeX) vs medical(JATS)
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.config import load_config                                             # noqa: E402
from src.processing.pdf_parser import run_processing                           # noqa: E402
from src.evidence.represent import build_document                             # noqa: E402
from src.embedding.build_index import load_model, embed_chunks, build_collection  # noqa: E402
from src.summarization import summarize as S                                   # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers     # noqa: E402
import src.evidence.gate as G                                                  # noqa: E402
from src.evidence.gate import (gate_paper, structural_bind, paper_table_cells,  # noqa: E402
                               classify_table, _METRIC_TOKENS, _col_matches_metric)

REACQ = HERE / "runs" / "medical_reacquire"
META = REACQ / "raw_metadata" / "collected_papers.json"
OUT = HERE / "runs" / "binding_validation"
PROC = OUT / "processed"
CHROMA = OUT / "chroma_db"
COLL = "researchgpt_binding_validation"
OUT.mkdir(parents=True, exist_ok=True)

_NUM = re.compile(r"\d")
STRUCT_REPS = {"jats_xml", "latex"}


def _cfg() -> dict:
    c = load_config(str(ROOT / "configs" / "staging_config.yaml"))
    c["paths"] = {"raw_metadata_dir": str(REACQ / "raw_metadata"),
                  "pdf_dir": str(REACQ / "pdfs"),
                  "processed_dir": str(PROC), "chroma_dir": str(CHROMA)}
    c["system"]["collection_name"] = COLL
    # staging defaults already: evidence_grounding.enabled true,
    # latex_ingestion_enabled false, seed 42, temp 0, reservation 768.
    return c


# --------------------------------------------------------------------------- #
# TASK 1 — process + verify structured cells
# --------------------------------------------------------------------------- #
def task1_process_and_verify(cfg: dict) -> tuple[dict, list[str], list[str]]:
    papers = json.loads(META.read_text(encoding="utf-8"))
    by_id = {p["paperId"]: p for p in papers}
    ft = [p["paperId"] for p in papers if p.get("has_full_text")]
    jats_ids = [p["paperId"] for p in papers
                if p.get("representation_type") == "jats_xml" and p.get("has_full_text")]
    pdf_ids = [p["paperId"] for p in papers
               if p.get("representation_type") == "pdf" and p.get("has_full_text")]

    if not (PROC / "chunks.json").exists():
        print("  running Stage 2 (grounded, provenance-aware) on the medical corpus...")
        run_processing(cfg)
    chunks_all = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    by_paper: dict[str, list[dict]] = defaultdict(list)
    for c in chunks_all:
        by_paper[c["paper_id"]].append(c)

    print("\n" + "=" * 74)
    print("TASK 1 — 11 JATS medical papers through Stage 2 : structured-cell verify")
    print("=" * 74)
    print(f"  medical corpus: {len(papers)} papers | full-text {len(ft)} "
          f"| JATS {len(jats_ids)} | PDF {len(pdf_ids)}")

    # per-paper: chunk cells + document-level table stats (re-parse: cheap XML)
    rows = []
    tot_cells = tot_tables = tot_structured = tot_fallback = papers_with_table = 0
    blockcnt: Counter = Counter()
    for pid in jats_ids:
        pcs = by_paper.get(pid, [])
        for c in pcs:
            blockcnt[c.get("block_type", "?")] += 1
        cell_n = len(paper_table_cells(pcs))
        xml = REACQ / "pdfs" / f"{pid}.xml"
        acq = {"paper_id": pid, "source": "europepmc", "representation_type": "jats_xml"}
        doc = build_document(acq, xml.read_bytes() if xml.exists() else None,
                             fallback_abstract=by_id[pid].get("abstract"))
        n_tab = doc["n_tables"]
        n_str = doc["n_tables_structured"]
        n_fb = doc["n_tables_fallback_pdf"]
        has_tab_block = any(c.get("block_type") == "table" for c in pcs)
        papers_with_table += 1 if has_tab_block else 0
        tot_cells += cell_n
        tot_tables += n_tab
        tot_structured += n_str
        tot_fallback += n_fb
        rows.append({"paper_id": pid, "chunks": len(pcs), "chunk_cells": cell_n,
                     "n_tables": n_tab, "tables_structured": n_str,
                     "tables_fallback": n_fb, "has_table_block": has_tab_block,
                     "title": (by_id[pid].get("title") or "")[:56]})

    print(f"\n  {'paper':14}{'chunks':>7}{'cells':>7}{'tables':>8}{'structured':>12}"
          f"{'fallback':>10}  title")
    for r in rows:
        print(f"  {r['paper_id'][:12]:14}{r['chunks']:>7}{r['chunk_cells']:>7}"
              f"{r['n_tables']:>8}{r['tables_structured']:>12}{r['tables_fallback']:>10}  "
              f"{r['title']}")

    print(f"\n  block_type distribution (all JATS chunks): {dict(blockcnt)}")
    print(f"  papers with >=1 table block            : {papers_with_table}/{len(jats_ids)}")
    print(f"  tables parsed to structured cells      : {tot_structured}/{tot_tables}")
    print(f"  tables fallen back to PDF              : {tot_fallback}/{tot_tables}")
    print(f"  total structured cells across 11 JATS  : {tot_cells}")

    stop = tot_cells < 22 or tot_structured == 0  # ~<2 cells/paper => nothing to measure
    print(f"\n  STOP CONDITION (near-zero cells) : {'TRIGGERED — HALTING' if stop else 'not triggered'}")
    (OUT / "task1_verify.json").write_text(json.dumps(
        {"rows": rows, "block_types": dict(blockcnt), "papers_with_table_block": papers_with_table,
         "tables": tot_tables, "tables_structured": tot_structured, "tables_fallback": tot_fallback,
         "total_cells": tot_cells, "stop": stop, "jats_ids": jats_ids, "pdf_ids": pdf_ids},
        indent=2), encoding="utf-8")
    if stop:
        sys.exit("TASK 1 stop condition: JATS parsing produced no usable cells on this corpus.")
    return by_paper, jats_ids, pdf_ids


# --------------------------------------------------------------------------- #
# Stage 3 + Stage 4 (seeded, clean cache)
# --------------------------------------------------------------------------- #
def build_index_and_extract(cfg: dict, ft_ids: list[str]) -> dict:
    if not (CHROMA / "chroma.sqlite3").exists():
        chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
        print("  building isolated Chroma index (bge-m3/cuda)...")
        model = load_model("BAAI/bge-m3", "cuda")
        build_collection(chunks, embed_chunks(model, chunks), str(CHROMA), COLL)
        del model
        try:
            import gc, torch
            gc.collect(); torch.cuda.empty_cache()
        except Exception:
            pass
    else:
        print("  reusing existing Chroma index")

    papers_all = build_retrieval_aware_papers(cfg, cfg["llm"].get("max_context_words", 2500))
    papers = {p: papers_all[p] for p in ft_ids if p in papers_all}
    cache_path = PROC / "extraction_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if cache:
        print(f"  reusing {len(cache)} cached extractions")
    t0 = time.time()
    ext = S.extract_paper_fields(dict(papers), dict(cfg["llm"]), cache=cache, processed_dir=str(PROC))
    ext = S._apply_selection_circuit_breaker(cfg, ext, cfg["llm"].get("max_context_words", 2500))
    print(f"  Stage 4 extraction: {len(papers)} papers in {time.time() - t0:.0f}s")
    return ext


# --------------------------------------------------------------------------- #
# TASK 2 — binding measurement with the real gate
# --------------------------------------------------------------------------- #
def task2_binding(cfg: dict, by_paper: dict, jats_ids: list[str], pdf_ids: list[str], ext: dict):
    meta = {m["paperId"]: m for m in json.loads(META.read_text(encoding="utf-8"))}
    ft_ids = jats_ids + pdf_ids
    reps = {pid: meta[pid].get("representation_type") for pid in ft_ids}

    evidence_out = []
    returned = []          # (pid, rep, field, value, bind_status, table_type)
    case_dist: Counter = Counter()
    bound_hits = []
    for pid in ft_ids:
        e = ext.get(pid, {})
        rec = {"paper_id": pid, "datasets": e.get("datasets"),
               "metrics": e.get("metrics"), "results": e.get("results")}
        sn = [a.get("name", "") for a in (meta[pid].get("authors") or []) if isinstance(a, dict)]
        g = gate_paper(rec, by_paper.get(pid, []), "FULL_TEXT", sn)
        evidence_out.append({"paper_id": pid, "acquisition_status": "FULL_TEXT",
                             "evidence": g["evidence"]})
        for field in ("metrics", "results"):
            for it in g["evidence"][field]:
                sb = it.get("structural_binding") or {}
                st = sb.get("status")
                val = it.get("value") or ""
                if _NUM.search(val):
                    case_dist[str(st)] += 1
                    if st == "bound":
                        bound_hits.append((pid[:10], reps[pid], field, val[:80],
                                           sb.get("table_type")))
                if it.get("final") == "RETURNED" and _NUM.search(val):
                    returned.append((pid, reps[pid], field, val, st, sb.get("table_type")))

    (PROC / "paper_evidence.json").write_text(json.dumps(evidence_out, indent=2), encoding="utf-8")

    s_ret = [r for r in returned if r[1] in STRUCT_REPS]
    p_ret = [r for r in returned if r[1] not in STRUCT_REPS]
    print("\n" + "=" * 74)
    print("TASK 2 — binding measurement, medical corpus, gate ACTIVE")
    print("=" * 74)
    print(f"  RETURNED numeric metrics/results:")
    print(f"    structured (11 JATS) : {len(s_ret)}")
    print(f"    PDF-only    (12 PDF) : {len(p_ret)}")
    print(f"    total                : {len(returned)}")
    print(f"\n  structural_bind case distribution (all numeric metrics/results items):")
    for k in ("pdf_only", "not_bindable", "bound", "wrong_cell", "not_a_table_claim", "None"):
        print(f"    {k:20} {case_dist.get(k, 0)}")
    other = {k: v for k, v in case_dist.items() if k not in
             ("pdf_only", "not_bindable", "bound", "wrong_cell", "not_a_table_claim", "None")}
    if other:
        print(f"    other                {other}")
    print(f"\n  claims that reached `bound` : {case_dist.get('bound', 0)}   "
          f"(canonical LaTeX real-extraction bound count is also 0 — 5 RETURNED structured "
          f"items there, all via not_bindable/not_a_table_claim fall-through)")
    for h in bound_hits:
        print(f"    bound [{h[0]}] {h[1]:8} {h[2]:8} type={h[4]}  {h[3]!r}")

    (OUT / "task2_binding.json").write_text(json.dumps(
        {"returned_total": len(returned), "returned_structured": len(s_ret),
         "returned_pdf_only": len(p_ret), "case_distribution": dict(case_dist),
         "bound_count": case_dist.get("bound", 0), "bound_hits": bound_hits,
         "returned": [{"paper_id": r[0], "rep": r[1], "field": r[2], "value": r[3],
                       "bind_status": r[4], "table_type": r[5]} for r in returned]},
        indent=2, default=str), encoding="utf-8")
    return reps


# --------------------------------------------------------------------------- #
# TASK 3 — adversarial probes on the 11 JATS papers
# --------------------------------------------------------------------------- #
_CLEAN = re.compile(r"^[\sA-Za-z0-9().,%\-/]+$")
_NUMV = re.compile(r"^-?\d+(?:\.\d+)?$")
_OWN = re.compile(r"\b(our[s]?|proposed|full model|full|hybrid|method|framework|model|group|"
                  r"cases?|patients?|intervention|exposed|treated)\b", re.I)


def _sane(s):
    m = re.sub(r"[^\d.\-]", "", str(s))
    if not _NUMV.match(m):
        return None
    try:
        x = abs(float(m))
    except ValueError:
        return None
    return m if 0.05 <= x <= 1000 else None


def task3_probes(by_paper: dict, jats_ids: list[str]):
    meta = {m["paperId"]: m for m in json.loads(META.read_text(encoding="utf-8"))}
    probes = []
    for pid in jats_ids:
        cells = paper_table_cells(by_paper.get(pid, []))
        if not cells:
            continue
        sn = [a.get("name", "") for a in (meta[pid].get("authors") or []) if isinstance(a, dict)]
        tabs: dict[str, list[dict]] = defaultdict(list)
        for c in cells:
            tabs[c.get("caption", "")].append(c)

        def gate(claim):
            rec = {"paper_id": pid, "metrics": [], "results": claim}
            g = gate_paper(rec, by_paper.get(pid, []), "FULL_TEXT", sn)
            its = g["evidence"]["results"]
            it = its[-1] if its else {}
            return (it.get("final"), it.get("abstain_reason") or it.get("attribution"),
                    (it.get("structural_binding") or {}).get("status"))

        def metric_cols(t):
            return sorted({c["column_header"] for c in t if c.get("column_header")
                           and _CLEAN.match(c["column_header"])
                           and _col_matches_metric(c["column_header"], _METRIC_TOKENS)})

        def clean_rows(t):
            return sorted({c["row_label"] for c in t if c.get("row_label")
                           and _CLEAN.match(c["row_label"])})

        good = [t for t in tabs.values()
                if len(t) >= 4 and metric_cols(t) and len(clean_rows(t)) >= 2]
        for t in good[:4]:
            mcols = metric_cols(t)
            rows = clean_rows(t)
            cA = mcols[0]
            cB = mcols[1] if len(mcols) > 1 else None
            rA = next((r for r in rows if _OWN.search(r)), rows[0])
            rB = next((r for r in rows if r != rA), rows[0])
            rC = next((r for r in rows if r not in (rA, rB)), None)  # "wrong condition"

            def cval(r, c):
                return next((_sane(x["value"]) for x in t if x.get("row_label") == r
                             and x.get("column_header") == c and _sane(x["value"])), None)

            vAA = cval(rA, cA)
            vAB = cval(rA, cB) if cB else None
            vBA = cval(rB, cA)
            vCA = cval(rC, cA) if rC else None
            mk = lambda subj, met, num: f"{subj} reports a {met} of {num} on the study cohort."
            cases = []
            if vAA:
                cases.append(("correct_cell", mk(rA, cA, vAA)))
            if vAB and vAB != vAA:
                cases.append(("correct_row_wrong_col", mk(rA, cA, vAB)))
            if vBA and vBA != vAA:
                cases.append(("correct_col_wrong_row", mk(rA, cA, vBA)))
            if vCA and vCA not in (vAA, vBA):
                cases.append(("correct_metric_wrong_condition", mk(rA, cA, vCA)))
            allnums_t = {re.sub(r"[^\d.\-]", "", str(y.get("value"))) for y in t}
            other = next((re.sub(r"[^\d.\-]", "", str(x.get("value")))
                          for ot in good if ot is not t for x in ot
                          if x.get("value") and _NUMV.match(re.sub(r"[^\d.\-]", "", str(x.get("value"))))
                          and re.sub(r"[^\d.\-]", "", str(x.get("value"))) not in allnums_t), None)
            if other:
                cases.append(("cross_table_substitution", mk(rA, cA, other)))
            for cls, claim in cases:
                fin, reason, st = gate(claim)
                want = "RETURNED" if cls == "correct_cell" else "ABSTAINED"
                probes.append({"paper_id": pid[:10], "class": cls, "claim": claim,
                               "final": fin, "want": want, "reason": str(reason),
                               "binding_status": st, "WRONG": fin != want,
                               "FOOLED": fin == "RETURNED" and cls != "correct_cell"})

    (OUT / "task3_probes.json").write_text(json.dumps(probes, indent=2, default=str), encoding="utf-8")
    by_cls: dict[str, Counter] = defaultdict(Counter)
    for p in probes:
        by_cls[p["class"]][p["final"]] += 1
    print("\n" + "=" * 74)
    print("TASK 3 — adversarial probes on the 11 JATS papers")
    print("=" * 74)
    print(f"  {'class':32}{'want':>10}{'n':>4}{'RETURNED':>10}{'ABSTAINED':>11}{'WRONG':>7}")
    adv = ("correct_row_wrong_col", "correct_col_wrong_row",
           "correct_metric_wrong_condition", "cross_table_substitution")
    for cls in ("correct_cell",) + adv:
        c = by_cls.get(cls)
        if not c:
            print(f"  {cls:32}{'—':>10}{0:>4}  (no probes constructed)")
            continue
        want = "RETURNED" if cls == "correct_cell" else "ABSTAINED"
        wrong = sum(1 for p in probes if p["class"] == cls and p["WRONG"])
        print(f"  {cls:32}{want:>10}{sum(c.values()):>4}{c.get('RETURNED', 0):>10}"
              f"{c.get('ABSTAINED', 0):>11}{wrong:>7}")
    fooled = [p for p in probes if p["FOOLED"]]
    print(f"\n  adversarial acceptances (FOOLED) : {len(fooled)}   (MUST be 0)")
    for p in fooled:
        print(f"    FOOLED [{p['paper_id']}] {p['class']}: {p['claim']}  -> {p['reason']}")
    xrow = [p for p in probes if p["class"] == "correct_col_wrong_row" and p["FOOLED"]]
    print(f"  cross-row acceptances            : {len(xrow)}   (MUST be 0)")
    return probes


# --------------------------------------------------------------------------- #
# TASK 5 — cross-domain comparison (NOT pooled)
# --------------------------------------------------------------------------- #
def task5_cross_domain(reps_medical: dict):
    sb = HERE / "runs" / "structural_binding"
    canon_rc = json.loads((sb / "returned_counts.json").read_text(encoding="utf-8"))
    canon_probes = json.loads((sb / "binding_probes.json").read_text(encoding="utf-8"))
    med_t2 = json.loads((OUT / "task2_binding.json").read_text(encoding="utf-8"))
    med_probes = json.loads((OUT / "task3_probes.json").read_text(encoding="utf-8"))

    # canonical case distribution: recompute from its ON returned-items + structural_bind
    canon_on = canon_rc["on"]
    canon_reps = canon_rc["reps"]
    canon_struct_ret = sum(len(v) for p, v in canon_on.items()
                           if canon_reps.get(p, "").split("(")[0] in STRUCT_REPS)
    canon_pdf_ret = sum(len(v) for p, v in canon_on.items()
                        if canon_reps.get(p, "").split("(")[0] not in STRUCT_REPS)
    canon_bind = Counter()
    for p, v in canon_on.items():
        for item in v:
            st = item[2] if len(item) > 2 else None
            canon_bind[str(st)] += 1
    canon_bound = canon_bind.get("bound", 0)
    canon_fooled = sum(1 for p in canon_probes if p.get("FOOLED"))
    canon_cc_ret = sum(1 for p in canon_probes
                       if p["class"] == "correct_cell" and p["final"] == "RETURNED")
    canon_cc_tot = sum(1 for p in canon_probes if p["class"] == "correct_cell")

    med_bind = med_t2["case_distribution"]
    med_bound = med_t2["bound_count"]
    med_fooled = sum(1 for p in med_probes if p.get("FOOLED"))
    med_cc_ret = sum(1 for p in med_probes
                     if p["class"] == "correct_cell" and p["final"] == "RETURNED")
    med_cc_tot = sum(1 for p in med_probes if p["class"] == "correct_cell")

    print("\n" + "=" * 74)
    print("TASK 5 — cross-domain comparison  (side by side, NOT pooled)")
    print("=" * 74)
    print(f"  {'':34}{'canonical (LaTeX)':>20}{'medical (JATS)':>18}")
    print(f"  {'structured papers':34}{'13 (11 tex + 2 jats)':>20}{'11 jats':>18}")
    print(f"  {'RETURNED quant — structured':34}{canon_struct_ret:>20}{med_t2['returned_structured']:>18}")
    print(f"  {'RETURNED quant — PDF-only':34}{canon_pdf_ret:>20}{med_t2['returned_pdf_only']:>18}")
    for k in ("pdf_only", "not_bindable", "bound", "wrong_cell", "not_a_table_claim", "None"):
        print(f"  {'case ' + k:34}{canon_bind.get(k, 0):>20}{med_bind.get(k, 0):>18}")
    print(f"  {'bound count':34}{canon_bound:>20}{med_bound:>18}")
    print(f"  {'correct_cell probes RETURNED':34}{f'{canon_cc_ret}/{canon_cc_tot}':>20}{f'{med_cc_ret}/{med_cc_tot}':>18}")
    print(f"  {'adversarial acceptances (FOOLED)':34}{canon_fooled:>20}{med_fooled:>18}")

    (OUT / "task5_cross_domain.json").write_text(json.dumps({
        "canonical": {"structured_papers": 13, "returned_structured": canon_struct_ret,
                      "returned_pdf_only": canon_pdf_ret, "case_distribution": dict(canon_bind),
                      "bound": canon_bound, "correct_cell_returned": [canon_cc_ret, canon_cc_tot],
                      "fooled": canon_fooled},
        "medical": {"structured_papers": 11, "returned_structured": med_t2["returned_structured"],
                    "returned_pdf_only": med_t2["returned_pdf_only"],
                    "case_distribution": med_bind, "bound": med_bound,
                    "correct_cell_returned": [med_cc_ret, med_cc_tot], "fooled": med_fooled},
    }, indent=2, default=str), encoding="utf-8")


def main() -> int:
    cfg = _cfg()
    by_paper, jats_ids, pdf_ids = task1_process_and_verify(cfg)
    ext = build_index_and_extract(cfg, jats_ids + pdf_ids)
    reps_medical = task2_binding(cfg, by_paper, jats_ids, pdf_ids, ext)
    task3_probes(by_paper, jats_ids)
    task5_cross_domain(reps_medical)
    print(f"\nwrote {OUT}")
    print("NEXT: python -u experiments/document_evidence_pipeline/gate_sensitivity.py --medical  (Task 4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
