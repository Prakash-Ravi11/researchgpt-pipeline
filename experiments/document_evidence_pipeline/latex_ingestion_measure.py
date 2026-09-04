"""4b — measure what the LaTeX-ingestion phase (4a) changed. Measurement only; no
ingestion code changes in this commit.

  M1  bindability: numeric-value survival LaTeX path vs PDF path (Test 1 re-run,
      table / prose / caption split)
  M2  downstream: canonical 34 full-text, content_aware@10, seeded, clean cache,
      arXiv papers re-ingested via LaTeX; vs post-3.2b baseline
  M3  0549e2e9 alone
  M4  field-presence determinability, three-way, coverage-when-present over
      determinable-present only

Isolated under runs/latex_ingestion/. Canonical frozen corpus, data_test and the
medical corpus are read-only; nothing writes data/processed/ or configs/.

  python -u experiments/document_evidence_pipeline/latex_ingestion_measure.py [--m1 --m2]
"""
from __future__ import annotations
import argparse, json, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import extraction_fidelity as EF                                             # noqa: E402
from src.processing.pdf_parser import process_paper_grounded                 # noqa: E402
from src.evidence.latex_source import fetch_eprint_latex                     # noqa: E402


def _assembled_tex(arxiv_id: str) -> str | None:
    """The SAME \\input-resolved LaTeX blob production uses (src.evidence.latex_source),
    from the cached e-print .blob — not extraction_fidelity's crude concat."""
    blob = EPRINT / f"{arxiv_id}.blob"
    if not blob.exists():
        return None
    lx = fetch_eprint_latex(arxiv_id, lambda url: {"ok": True, "http_status": 200,
                                                   "body": blob.read_bytes(), "bytes": blob.stat().st_size})
    return lx["latex"] if lx.get("ok") else None
from src.embedding.build_index import load_model, embed_chunks, build_collection  # noqa: E402
from src.summarization import summarize as S                                 # noqa: E402
from src.summarization.retrieval_aware import build_retrieval_aware_papers   # noqa: E402

CANON = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
PDFDIR = CANON / "pdfs"
EPRINT = HERE / "runs" / "extraction_fidelity" / "eprint"
OUT = HERE / "runs" / "latex_ingestion"
OUT.mkdir(parents=True, exist_ok=True)
PROC = OUT / "processed"
CHROMA = OUT / "chroma_db"
COLL = "latex_ingestion"

LLM = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "timeout_seconds": 300,
       "temperature": 0, "seed": 42, "max_context_words": 2500,
       "extraction_deadline_seconds": 240, "extraction_output_reservation": 768}
CORE = ["method", "datasets", "metrics", "results", "limitations"]
FLAT = list(S._EXTRACTION_SCHEMA_KEYS)
BASE = {"mean": 9.65, "method": 1.00, "datasets": 0.97, "metrics": 0.91, "results": 0.94,
        "limitations": 0.94, "conf": "32 conformant / 2 salvaged / 0 nonconformant"}


def nef(rec):
    out = []
    for f in FLAT:
        v = rec.get(f)
        if f in ("datasets", "metrics"):
            if isinstance(v, list) and any(str(x).strip() for x in v):
                out.append(f)
        elif str(v or "").strip():
            out.append(f)
    return out


# ------------------------------------------------------------------ M1
def _chunks_via(pair, rep):
    """rep='pdf' -> real PDF grounded path;  rep='latex' -> 4a LaTeX path."""
    if rep == "pdf":
        p = {"paperId": pair["paper_id"], "title": "", "year": None, "venue": "",
             "has_full_text": True, "pdf_path": pair["pdf"], "representation_type": "pdf",
             "pdf_source": "arxiv", "acquisition_status": "FULL_TEXT", "abstract": ""}
        return process_paper_grounded(p)
    asm = _assembled_tex(pair["arxiv"])
    if not asm:
        return None
    tex = OUT / "asm_tex" / f"{pair['arxiv']}.tex"
    tex.parent.mkdir(parents=True, exist_ok=True)
    tex.write_text(asm, encoding="utf-8")
    p = {"paperId": pair["paper_id"], "title": "", "year": None, "venue": "",
         "has_full_text": True, "pdf_path": str(tex), "representation_type": "latex",
         "latex_pdf_fallback_path": pair["pdf"], "pdf_source": "arxiv_eprint",
         "acquisition_status": "FULL_TEXT", "abstract": ""}
    return process_paper_grounded(p)


def _survive(gt_list, chunks):
    if chunks is None:
        return None
    rows = []
    for gt in gt_list:
        v = gt["value"]
        gt_words = {w for w in re.findall(r"[a-z]{4,}", gt["context"].lower())}
        meaningful = gt["location"] in ("table", "caption") or bool(gt.get("metric_hint")) or bool(gt.get("dataset_hint"))
        lax = any(v in c["text"] for c in chunks)   # value present anywhere
        hit = None
        for c in chunks:
            if v in c["text"]:
                cw = set(re.findall(r"[a-z]{4,}", c["text"].lower()))
                if not gt_words or (gt_words & cw):
                    hit = c
                    break
        prov = bool(hit) and bool(hit.get("section")) and bool(hit.get("page_or_node"))
        ctx_ok = False
        if hit:
            idx = hit["text"].find(v)
            win = hit["text"][max(0, idx - 90): idx + 90]
            needles = [x for x in (gt.get("metric_hint"), gt.get("dataset_hint")) if x]
            ctx_ok = (bool(needles) and any(n.lower() in win.lower() for n in needles)) \
                or bool(EF._METRIC_WORDS.search(win)) or bool(EF._DATASET_WORDS.search(win))
        rows.append({"loc": gt["location"], "meaningful": meaningful,
                     "verbatim_lax": lax, "verbatim": bool(hit), "provenance": prov,
                     "bindable": bool(hit and ctx_ok), "bindable_lax": bool(lax and ctx_ok)})
    return rows


def _rate(rows, key, loc=None):
    sub = [r for r in rows if r["meaningful"] and (loc is None or r["loc"] == loc)]
    return (round(sum(r[key] for r in sub) / len(sub), 3), len(sub)) if sub else (None, 0)


def measure1():
    pairs = EF._pairs()
    pairs = EF.step1(pairs)
    pairs = EF.step2(pairs)
    usable = [p for p in pairs if p.get("gt_count", 0) > 0 and p.get("pdf")]
    print(f"M1 — bindability, {len(usable)} paired papers with numeric ground truth\n")
    pool = {"latex": defaultdict(Counter), "pdf": defaultdict(Counter)}
    fell_back = []
    per_paper = []
    parity_fb = []
    for p in usable:
        gt = p["ground_truth"]
        lx_chunks = _chunks_via(p, "latex")
        pdf_chunks = _chunks_via(p, "pdf")
        if lx_chunks is None:
            fell_back.append((p["paper_id"][:12], p.get("latex_status")))
        pf_rec = next((c["latex_parity_fallback"] for c in (lx_chunks or [])
                       if c.get("latex_parity_fallback")), None)
        if pf_rec:
            parity_fb.append((p["paper_id"][:12], pf_rec["latex_survival"], pf_rec["pdf_survival"],
                              pf_rec["n_ground_truth"]))
        lx = _survive(gt, lx_chunks)
        pf = _survive(gt, pdf_chunks)
        row = {"paper_id": p["paper_id"][:12], "arxiv": p.get("arxiv"), "kind": p["kind"],
               "gt": len(gt), "latex_ok": lx is not None}
        for tag, rows in (("latex", lx), ("pdf", pf)):
            if rows is None:
                continue
            for loc in (None, "table", "prose", "caption"):
                b, n = _rate(rows, "bindable", loc)
                vb, _ = _rate(rows, "verbatim", loc)
                pr, _ = _rate(rows, "provenance", loc)
                k = loc or "all"
                row[f"{tag}_{k}_bindable"] = b
                row[f"{tag}_{k}_verbatim"] = vb
                row[f"{tag}_{k}_prov"] = pr
                if n:
                    ss = [r for r in rows if r["meaningful"] and (loc is None or r["loc"] == loc)]
                    pool[tag][k]["n"] += n
                    pool[tag][k]["bind"] += sum(r["bindable"] for r in ss)
                    pool[tag][k]["bind_lax"] += sum(r["bindable_lax"] for r in ss)
                    pool[tag][k]["vb"] += sum(r["verbatim"] for r in ss)
                    pool[tag][k]["vb_lax"] += sum(r["verbatim_lax"] for r in ss)
                    pool[tag][k]["prov"] += sum(r["provenance"] for r in ss)
        per_paper.append(row)
        print(f"  {row['paper_id']:14} {p['kind']:11} gt={len(gt):4}  "
              f"BINDABLE table L={row.get('latex_table_bindable')} P={row.get('pdf_table_bindable')} | "
              f"prose L={row.get('latex_prose_bindable')} P={row.get('pdf_prose_bindable')}")
    (OUT / "m1_per_paper.json").write_text(json.dumps(per_paper, indent=2), encoding="utf-8")
    print(f"\n== M1 POOLED (meaningful numeric values). L=LaTeX path  P=PDF path ==")
    print(f"  {'split':8} {'n':>5} | {'vb_lax L/P':>13} | {'vb_strict L/P':>15} | "
          f"{'bind_lax L/P':>15} | {'bind_strict L/P':>17}")
    for k in ("all", "table", "prose", "caption"):
        L, P = pool["latex"][k], pool["pdf"][k]
        if not L["n"] and not P["n"]:
            continue
        def r(c, key):
            return f"{c[key]/c['n']:.3f}" if c["n"] else "  -  "
        print(f"  {k:8} {max(L['n'],P['n']):>5} | {r(L,'vb_lax')}/{r(P,'vb_lax')} | "
              f"{r(L,'vb')}/{r(P,'vb')} | {r(L,'bind_lax')}/{r(P,'bind_lax')} | "
              f"{r(L,'bind')}/{r(P,'bind')}")
    print(f"\n  papers that fell back to PDF (no usable .tex): {fell_back or 'none'}")
    print(f"  papers that hit the PARITY GATE fallback (latex_survival < pdf_survival): {len(parity_fb)}")
    for pid, ls, ps, ng in parity_fb:
        print(f"     {pid}: latex_survival={ls} pdf_survival={ps} (n_gt={ng})")
    (OUT / "m1_pooled.json").write_text(
        json.dumps({t: {k: dict(v) for k, v in d.items()} for t, d in pool.items()},
                   indent=2), encoding="utf-8")


# ------------------------------------------------------------------ M2/M3/M4
def _rechunk_canonical():
    """Isolated processed dir: 24 arXiv papers re-chunked via the 4a LaTeX path,
    10 non-arXiv papers copied verbatim from the frozen canonical chunks."""
    PROC.mkdir(parents=True, exist_ok=True)
    meta = {m["paperId"]: m for m in json.loads((CANON / "raw_metadata" / "collected_papers.json").read_text(encoding="utf-8"))}
    frozen = json.loads((CANON / "processed" / "chunks.json").read_text(encoding="utf-8"))
    ft_ids = sorted({c["paper_id"] for c in frozen if c.get("has_full_text")})
    reps = {}
    all_chunks = []
    asm_dir = OUT / "asm_tex"
    asm_dir.mkdir(parents=True, exist_ok=True)
    for pid in ft_ids:
        m = meta.get(pid, {})
        aid = (m.get("externalIds") or {}).get("ArXiv")
        paired_pdf = PDFDIR / f"{pid}.pdf"
        asm = _assembled_tex(aid) if aid else None          # production \input-resolved
        if aid and asm and paired_pdf.exists():
            tex = asm_dir / f"{aid}.tex"
            tex.write_text(asm, encoding="utf-8")
            p = {"paperId": pid, "title": m.get("title", ""), "year": m.get("year"),
                 "venue": m.get("venue", ""), "has_full_text": True,
                 "pdf_path": str(tex), "representation_type": "latex",
                 "latex_pdf_fallback_path": str(paired_pdf),
                 "pdf_source": "arxiv_eprint", "acquisition_status": "FULL_TEXT",
                 "abstract": m.get("abstract", "")}
            recs = process_paper_grounded(p, latex_parity_tolerance=0.0)
            reps[pid] = "latex" if recs and recs[0].get("representation") == "latex" else "pdf(fallback)"
            all_chunks.extend(recs)
        else:
            pcs = [c for c in frozen if c["paper_id"] == pid]
            all_chunks.extend(pcs)
            reps[pid] = (pcs[0].get("representation") if pcs else "abstract") or "pdf"
    # carry the abstract-only papers too (retrieval build reads the whole file)
    for c in frozen:
        if not c.get("has_full_text"):
            all_chunks.append(c)
    (PROC / "chunks.json").write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")
    print(f"  re-chunked: {Counter(reps.values())}  ({len(all_chunks)} chunks total)")
    return ft_ids, reps


def _cfg():
    return {"paths": {"processed_dir": str(PROC), "chroma_dir": str(CHROMA)},
            "embedding": {"model": "BAAI/bge-m3", "device": "cuda"},
            "system": {"collection_name": COLL},
            "llm": LLM,     # _apply_selection_circuit_breaker reads config["llm"]
            "selection": {"mode": "content_aware", "max_passages": 10}}


def measure234():
    reps_path = OUT / "reps.json"
    if reps_path.exists() and (PROC / "chunks.json").exists():
        print("  reusing existing re-chunk from a prior run")
        reps = json.loads(reps_path.read_text(encoding="utf-8"))
        ft_ids = sorted(reps)
    else:
        ft_ids, reps = _rechunk_canonical()
        reps_path.write_text(json.dumps(reps, indent=2), encoding="utf-8")
    if (CHROMA / "chroma.sqlite3").exists() and reps_path.exists():
        print("  reusing existing Chroma index from a prior run")
    else:
        chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
        print("  building isolated Chroma index...")
        model = load_model("BAAI/bge-m3", "cuda")
        build_collection(chunks, embed_chunks(model, chunks), str(CHROMA), COLL)
        del model
        try:
            import gc, torch
            gc.collect(); torch.cuda.empty_cache()
        except Exception:
            pass

    papers_all = build_retrieval_aware_papers(_cfg(), 2500)
    papers = {p: papers_all[p] for p in ft_ids if p in papers_all}
    # persist the extraction cache under PROC so a crash after the ~23-min LLM pass
    # (e.g. a downstream KeyError) does not cost a full re-run.
    cache_path = PROC / "extraction_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if cache:
        print(f"  reusing {len(cache)} cached extractions from a prior run")
    t0 = time.time()
    ext = S.extract_paper_fields(dict(papers), dict(LLM), cache=cache, processed_dir=str(PROC))
    ext = S._apply_selection_circuit_breaker(_cfg(), ext, 2500)
    dt = time.time() - t0

    rows = []
    for pid in papers:
        r = ext[pid]
        rows.append({"paper_id": pid, "rep": reps.get(pid), "n": len(nef(r)), "fields": nef(r),
                     "conformance": r.get("_conformance"), "variant": r.get("_domain_variant"),
                     "selection_fallback": bool(r.get("_selection_fallback")),
                     "extraction_failed": bool(r.get("_extraction_failed")),
                     "failure_reason": r.get("_failure_reason"),
                     "done_reason": r.get("_done_reason"),
                     "response_truncated": bool(r.get("_response_truncated")),
                     "salvage_accounting": r.get("_salvage_accounting")})
    (OUT / "m2_rows.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    n = len(rows)

    # ---- M2 ----
    print(f"\n== M2 — canonical {n} full-text, content_aware@10, seeded, clean cache "
          f"({dt:.0f}s, {dt/n:.0f}s/paper) ==")
    mean = sum(r["n"] for r in rows) / n
    print(f"  mean non-empty fields/paper: {mean:.2f}   (post-3.2b baseline {BASE['mean']})")
    print(f"  conformance: {dict(Counter(r['conformance'] for r in rows))}   (baseline {BASE['conf']})")
    print(f"  circuit-breaker fallbacks: {sum(r['selection_fallback'] for r in rows)} "
          f"{[r['paper_id'][:10] for r in rows if r['selection_fallback']]}")
    print(f"  _extraction_failed: {sum(r['extraction_failed'] for r in rows)} "
          f"{[(r['paper_id'][:10], r['failure_reason']) for r in rows if r['extraction_failed']]}")
    dr = Counter(str(r["done_reason"]) for r in rows)
    length = [r for r in rows if r["done_reason"] == "length"]
    length_conf = [r for r in length if r["conformance"] in ("conformant", "salvaged")]
    print(f"  done_reason: {dict(dr)}")
    print(f"  done_reason=='length': {len(length)}  {[r['paper_id'][:10] for r in length]}")
    if length_conf:
        print(f"  !! length AND conformant/salvaged (cap cutting real content): "
              f"{[(r['paper_id'][:10], r['conformance']) for r in length_conf]}")
    for f in CORE:
        g = sum(1 for r in rows if f in r["fields"])
        print(f"    {f:12} {g}/{n} ({g/n:.0%})   baseline {BASE[f]:.0%}")

    # AMENDMENT A — per-field coverage split by representation subset
    retained = [r for r in rows if r["rep"] == "latex"]
    arxiv_fb = [r for r in rows if r["rep"] == "pdf(fallback)"]
    non_arxiv = [r for r in rows if r["rep"] not in ("latex", "pdf(fallback)")]
    print(f"\n  -- M2 by representation subset (Amendment A) --")
    print(f"  RETAINED (LaTeX) n={len(retained)} | ARXIV_FALLBACK n={len(arxiv_fb)} | "
          f"OTHER(non-arXiv/JATS/PDF) n={len(non_arxiv)}")
    def _cov(sub):
        if not sub:
            return "  (n=0)"
        return "  ".join(f"{f[:4]} {sum(1 for r in sub if f in r['fields'])}/{len(sub)} "
                         f"({sum(1 for r in sub if f in r['fields'])/len(sub):.0%})" for f in CORE)
    print(f"    RETAINED     mean {sum(r['n'] for r in retained)/max(1,len(retained)):.2f}  | {_cov(retained)}")
    print(f"    ARXIV_FB     mean {sum(r['n'] for r in arxiv_fb)/max(1,len(arxiv_fb)):.2f}  | {_cov(arxiv_fb)}")
    print(f"    OTHER        mean {sum(r['n'] for r in non_arxiv)/max(1,len(non_arxiv)):.2f}  | {_cov(non_arxiv)}")
    # RETAINED vs its own frozen (pre-LaTeX) baseline
    try:
        _prev = {r["paper_id"]: r for r in json.loads(
            (HERE / "runs" / "context_budget" / "canonical_ca10_v2.json").read_text(encoding="utf-8"))}
        rb = [(_prev[r["paper_id"]]["n"], r["n"]) for r in retained if r["paper_id"] in _prev]
        if rb:
            print(f"    RETAINED vs post-3.2b frozen: mean {sum(a for a,_ in rb)/len(rb):.2f} -> "
                  f"{sum(b for _,b in rb)/len(rb):.2f}  "
                  f"(better {sum(1 for a,b in rb if b>a)}, worse {sum(1 for a,b in rb if b<a)}, "
                  f"same {sum(1 for a,b in rb if a==b)})")
    except FileNotFoundError:
        pass

    # per-paper vs frozen cov_canon_ca10 baseline
    try:
        prev = {r["paper_id"]: r for r in json.loads(
            (HERE / "runs" / "context_budget" / "canonical_ca10_v2.json").read_text(encoding="utf-8"))}
    except FileNotFoundError:
        prev = {}
    worse = []
    print("  per-paper vs post-3.2b (changes only):")
    for r in rows:
        b = prev.get(r["paper_id"], {}).get("n")
        if b is not None and r["n"] != b:
            tag = "WORSE" if r["n"] < b else "better"
            if r["n"] < b:
                worse.append((r["paper_id"][:12], b, r["n"], r["rep"], r["conformance"]))
            print(f"    {r['paper_id'][:12]} {b:2}->{r['n']:2} {tag:6} rep={r['rep']} conf={r['conformance']}")
    print(f"  papers WORSE: {worse or 'none'}")

    # ---- M3 ----
    z = next((r for r in rows if r["paper_id"].startswith("0549e2e9")), None)
    print(f"\n== M3 — 0549e2e9 ==")
    if z:
        sa = z["salvage_accounting"]
        print(f"  rep={z['rep']} (JATS, not arXiv — 4a's JATS change adds structured cells "
              f"but leaves the table BLOCK TEXT unchanged, so no LaTeX effect here)")
        print(f"  conformance={z['conformance']}  done_reason={z['done_reason']}  "
              f"response_truncated={z['response_truncated']}  fields={z['n']}  "
              f"circuit_breaker={z['selection_fallback']}")
        if sa:
            print(f"  salvage: direct={sa.get('direct_fields')} recovered={sa.get('recovered_fields')} "
                  f"discarded_keys={sa.get('discarded_top_level_keys')} "
                  f"discarded_chars={sa.get('discarded_char_volume')}")
        else:
            print(f"  salvage accounting: none (not salvaged)")

    # ---- M4 (Amendment B) ----
    print(f"\n== M4 — field-presence determinability (first real denominator) ==")
    STRUCT = {"latex", "jats_xml"}
    det = [r for r in rows if (r["rep"] or "").split("(")[0] in STRUCT]
    n_latex = sum(1 for r in det if r["rep"] == "latex")
    n_jats = sum(1 for r in det if (r["rep"] or "").split("(")[0] == "jats_xml")
    print(f"  structured representation exists for {len(det)}/{n} papers "
          f"= {n_latex} LaTeX-retained + {n_jats} JATS. This is the FIRST point in the "
          f"project with a real presence denominator.")
    print(f"  (rep mix: {dict(Counter((r['rep'] or '').split('(')[0] for r in rows))})")
    for f in CORE:
        present = sum(1 for r in det if f in r["fields"])
        absent = len(det) - present
        undet = n - len(det)
        cwp = present / len(det) if det else None
        print(f"    {f:12} determinable-present {present:2} / determinable-absent {absent:2} "
              f"/ undeterminable {undet:2}   coverage-when-present {cwp:.0%}" if cwp is not None
              else f"    {f:12} no determinable papers")
    print(f"\n  undeterminable ({n - len(det)}) is reported separately, never folded into "
          f"either bucket. 'determinable-absent' here still leans on heuristic PDF/JATS "
          f"section labels for the LaTeX subset — a lower bound on presence, not gospel.")


def _retained_extract(reservation: int, tag: str) -> list[dict]:
    """Extraction on the 11 RETAINED (LaTeX) papers only, seeded, clean cache,
    reusing the existing isolated PROC/CHROMA. `reservation` overrides
    extraction_output_reservation for this run only."""
    reps = json.loads((OUT / "reps.json").read_text(encoding="utf-8"))
    ret_ids = sorted(p for p, r in reps.items() if r == "latex")
    papers_all = build_retrieval_aware_papers(_cfg(), 2500)
    papers = {p: papers_all[p] for p in ret_ids if p in papers_all}
    llm = {**LLM, "extraction_output_reservation": reservation}
    print(f"  {tag}: {len(papers)} RETAINED papers, extraction_output_reservation={reservation}")
    ext = S.extract_paper_fields(dict(papers), dict(llm), cache={}, processed_dir=None)
    ext = S._apply_selection_circuit_breaker({**_cfg(), "llm": llm}, ext, 2500)
    rows = [{"paper_id": p, "n": len(nef(ext[p])), "fields": nef(ext[p]),
             "conformance": ext[p].get("_conformance"),
             "done_reason": ext[p].get("_done_reason"),
             "response_truncated": bool(ext[p].get("_response_truncated")),
             "extraction_failed": bool(ext[p].get("_extraction_failed"))} for p in papers]
    (OUT / f"{tag}.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    n = len(rows)
    length = [r["paper_id"][:10] for r in rows if r["done_reason"] == "length"]
    frozen = {r["paper_id"]: r["n"] for r in json.loads(
        (HERE / "runs" / "context_budget" / "canonical_ca10_v2.json").read_text(encoding="utf-8"))}
    fb = [(r["paper_id"][:12], frozen.get(r["paper_id"]), r["n"], r["conformance"]) for r in rows]
    print(f"  mean non-empty fields/paper: {sum(r['n'] for r in rows)/n:.2f}   "
          f"(capped 768 run: 4.73  |  post-3.2b frozen: 9.91)")
    print(f"  done_reason=='length': {len(length)}  {length}")
    print(f"  conformance: {dict(Counter(r['conformance'] for r in rows))}")
    print(f"  _extraction_failed: {sum(r['extraction_failed'] for r in rows)}")
    for f in CORE:
        g = sum(1 for r in rows if f in r["fields"])
        print(f"    {f:12} {g}/{n} ({g/n:.0%})")
    print("  per paper (frozen -> this run):")
    for pid, fr, nn, cf in sorted(fb, key=lambda x: x[2]):
        print(f"    {pid} {str(fr):>4} -> {nn:2}  {cf}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m1", action="store_true")
    ap.add_argument("--m2", action="store_true")
    ap.add_argument("--diag-uncap", type=int, metavar="RESERVATION",
                    help="TASK 1 diagnostic: re-extract the 11 RETAINED papers with this "
                         "extraction_output_reservation (raise until done_reason==length is 0)")
    ap.add_argument("--m2-retained", action="store_true",
                    help="TASK 2: re-extract the 11 RETAINED papers at the normal 768 reservation")
    a = ap.parse_args()
    if a.diag_uncap:
        _retained_extract(a.diag_uncap, f"diag_uncap_{a.diag_uncap}")
        return
    if a.m2_retained:
        # TASK 2 changed the table-block text routing -> rebuild chunks + index first
        for p in (OUT / "reps.json", PROC / "chunks.json"):
            p.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(CHROMA, ignore_errors=True)
        ft_ids, reps = _rechunk_canonical()
        (OUT / "reps.json").write_text(json.dumps(reps, indent=2), encoding="utf-8")
        chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
        model = load_model("BAAI/bge-m3", "cuda")
        build_collection(chunks, embed_chunks(model, chunks), str(CHROMA), COLL)
        del model
        try:
            import gc, torch
            gc.collect(); torch.cuda.empty_cache()
        except Exception:
            pass
        _retained_extract(768, "m2_retained_768")
        return
    do_all = not (a.m1 or a.m2)
    if a.m1 or do_all:
        measure1()
    if a.m2 or do_all:
        measure234()


if __name__ == "__main__":
    main()
