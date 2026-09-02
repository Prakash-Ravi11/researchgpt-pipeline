"""
STEP 4/5/6 of the extraction triage.  MEASUREMENT ONLY.

STEP 4  trace Stage-2 ops + retrieval + raw Qwen for the B/M/D papers and the
        zero-field papers (symptom under investigation).
STEP 5  rule out the UI handoff for one "Not extracted" paper.
STEP 6  field-presence determinability per field, per full-text paper.

Uses the Phase-1 seeded path (temperature 0, seed 42).  Third corpus (data/) only.

Run:  .venv/Scripts/python.exe scripts/triage_trace.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
import pymupdf  # noqa: E402

from src.processing.pdf_parser import extract_pdf_text, clean_text, chunk_text, CUTOFF_HEADINGS  # noqa: E402
from src.summarization.summarize import (  # noqa: E402
    EXTRACTION_SYSTEM_PROMPT, call_ollama_json, estimate_num_ctx,
    _parse_json_response, normalize_extraction,
)

CFG = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))
PATHS = CFG["paths"]
LLM = {**CFG["llm"], "temperature": 0, "seed": 42}
PROC = ROOT / PATHS["processed_dir"]
PDF_DIR = ROOT / PATHS["pdf_dir"]
OUT = ROOT / "experiments/document_evidence_pipeline/runs/extraction_triage"
OUT.mkdir(parents=True, exist_ok=True)

FLAT_FIELDS = {"summary", "problem_addressed", "method", "results", "inferences",
               "novelty_claim", "limitations", "key_findings", "datasets", "metrics"}
CORE = ["method", "datasets", "metrics", "results", "limitations"]

HEAD_RE = {
    "method":      re.compile(r"^\s*(\d+\.?\s+)?(materials?\s+and\s+methods?|methods?|methodology|proposed\s+method|approach|study\s+design|experimental\s+setup)\b", re.I | re.M),
    "datasets":    re.compile(r"(\bdataset\b|\bdata\s*set\b|\bstudy\s+population\b|\bparticipants\b|\bsubjects\b|\bcohort\b|\bimage\s+acquisition\b|\bdata\s+collection\b)", re.I),
    "metrics":     re.compile(r"(\bevaluation\s+metrics?\b|\bdice\b|\bIoU\b|\bHausdorff\b|\bsensitivity\b|\bspecificity\b|\bAUC\b|\bF1\b|\baccuracy\b|\bprecision\b|\brecall\b|\bp\s*[<=]\s*0?\.0)", re.I),
    "results":     re.compile(r"^\s*(\d+\.?\s+)?(results?|experiments?\s+and\s+results?|experimental\s+results?|evaluation|findings)\b", re.I | re.M),
    "limitations": re.compile(r"(\blimitations?\b|\bfuture\s+work\b|\bthreats\s+to\s+validity\b|^\s*(\d+\.?\s+)?discussion\b)", re.I | re.M),
}


def load(p): return json.loads((PROC / p).read_text(encoding="utf-8"))


def sections_hit(text: str) -> dict:
    return {k: bool(rx.search(text)) for k, rx in HEAD_RE.items()}


def retrieval_probe(pid: str, model, col):
    from src.summarization.retrieval_aware import TARGET_QUERIES
    qv = model.encode(TARGET_QUERIES, normalize_embeddings=True)
    out = {}
    for q, v in zip(TARGET_QUERIES, qv):
        r = col.query(query_embeddings=[v.tolist()], n_results=3, where={"paper_id": pid})
        ids = (r.get("ids") or [[]])[0]
        docs = (r.get("documents") or [[]])[0]
        out[q[:22]] = [{"id": i, "chars": len(d or ""), "head": (d or "")[:80].replace("\n", " ")}
                       for i, d in zip(ids, docs)]
    return out


def main():
    papers = json.loads((ROOT / "data/raw_metadata/collected_papers.json").read_text(encoding="utf-8"))
    by_id = {p["paperId"]: p for p in papers}
    summaries = {r["paper_id"]: r for r in load("paper_summaries.json")}
    doc_rows = json.loads((OUT / "per_doc.json").read_text(encoding="utf-8"))
    drow = {r["paper_id"]: r for r in doc_rows}

    zero = [r["paper_id"] for r in doc_rows if r["has_full_text"] and r["fields_returned"] == 0]
    bmd = json.loads((OUT / "trace_ids.json").read_text(encoding="utf-8"))
    trace_ids = list(dict.fromkeys(bmd + zero))
    print(f"STEP 4 — tracing {len(trace_ids)} papers: {[t[:12] for t in trace_ids]}")
    print(f"  (B/M/D: {[t[:12] for t in bmd]}   zero-field: {[t[:12] for t in zero]})\n")

    # shared models for retrieval
    import chromadb
    from sentence_transformers import SentenceTransformer
    client = chromadb.PersistentClient(path=str(ROOT / PATHS["chroma_dir"]))
    col = client.get_collection(CFG["system"]["collection_name"])
    model = SentenceTransformer(CFG["embedding"]["model"], device=CFG["embedding"]["device"])

    trace_detail = {}
    for pid in trace_ids:
        p = by_id[pid]
        pdf = PDF_DIR / f"{pid}.pdf"
        raw = extract_pdf_text(str(pdf))
        m = CUTOFF_HEADINGS.search(raw)
        cleaned = clean_text(raw)
        ck = chunk_text(cleaned, CFG["processing"]["chunk_size"], CFG["processing"]["chunk_overlap"])
        rec = {
            "bucket": drow[pid]["bucket"],
            "pages": drow[pid]["pages"],
            "raw_chars": len(raw),
            "cutoff_matched": bool(m),
            "cutoff_at_frac": round(m.start() / max(len(raw), 1), 3) if m else None,
            "cleaned_chars": len(cleaned),
            "n_chunks_from_chunk_text": len(ck),
            "n_chunks_in_corpus": drow[pid]["chunk_count"],
            "retrieval": retrieval_probe(pid, model, col),
        }
        # raw Qwen, seeded
        uc = f"Title: {p['title']}\n\nText:\n{' '.join(cleaned.split()[:CFG['llm'].get('max_context_words', 2500)])}"
        resp_raw = None
        try:
            import requests
            r = requests.post(f"{LLM['base_url']}/api/chat", json={
                "model": LLM["model"],
                "messages": [{"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                             {"role": "user", "content": uc}],
                "format": "json", "stream": False,
                "options": {"temperature": 0, "seed": 42, "num_ctx": estimate_num_ctx(uc),
                            "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1},
            }, timeout=300)
            resp_raw = r.json().get("message", {}).get("content", "")
        except Exception as e:
            rec["qwen_error"] = repr(e)
        if resp_raw is not None:
            (OUT / f"qwen_raw_{pid[:12]}.txt").write_text(resp_raw, encoding="utf-8")
            rec["qwen_raw_chars"] = len(resp_raw)
            try:
                parsed = _parse_json_response(resp_raw)
                keys = list(parsed.keys())
                rec["qwen_parsed_keys"] = keys
                rec["qwen_unexpected_keys"] = [k for k in keys if k not in FLAT_FIELDS
                                               and not k.startswith("_")]
                norm = normalize_extraction(parsed)
                rec["qwen_filled_after_normalize"] = [k for k in FLAT_FIELDS
                                                     if (norm.get(k) if k in ("datasets", "metrics") else str(norm.get(k, "")).strip())]
                rec["qwen_nested_or_markdown"] = any(
                    isinstance(v, (dict, list)) and k not in ("datasets", "metrics")
                    for k, v in parsed.items()) or bool(re.search(r"\*\*|^#{1,3}\s|\n- ", resp_raw))
            except Exception as e:
                rec["qwen_parse_error"] = repr(e)
        trace_detail[pid] = rec
        print(f"  {pid[:12]} [{rec['bucket']}] raw={rec['raw_chars']} clean={rec['cleaned_chars']} "
              f"cutoff@{rec['cutoff_at_frac']} chunks={rec['n_chunks_from_chunk_text']}/{rec['n_chunks_in_corpus']} "
              f"| qwen: unexpected_keys={rec.get('qwen_unexpected_keys')} "
              f"filled={rec.get('qwen_filled_after_normalize')} nested/md={rec.get('qwen_nested_or_markdown')}")

    (OUT / "trace_detail.json").write_text(json.dumps(trace_detail, indent=2, default=str), encoding="utf-8")

    # ---- STEP 5 -------------------------------------------------------------
    print("\nSTEP 5 — UI handoff check")
    for pid in zero[:1] or trace_ids[:1]:
        s = summaries.get(pid, {})
        filled = [k for k in FLAT_FIELDS if (s.get(k) if k in ("datasets", "metrics") else str(s.get(k, "")).strip())]
        print(f"  paper {pid[:12]}: paper_summaries.json filled fields = {filled or 'NONE'}")
        print(f"  -> backend record is {'EMPTY (not a rendering bug — backend produced nothing)' if not filled else 'NON-EMPTY (possible rendering bug!)'}")

    # ---- STEP 6 ----------------------------------------------------------------
    print("\nSTEP 6 — field-presence determinability (full-text papers)")
    ft = [r for r in doc_rows if r["has_full_text"]]
    per_field = {f: {"determinable_present": 0, "determinable_absent": 0, "undeterminable": 0} for f in CORE}
    heuristic_present = {f: 0 for f in CORE}
    rows6 = []
    for r in ft:
        pid = r["paper_id"]
        structured = (by_id[pid].get("representation_type") == "jats_xml")
        raw = extract_pdf_text(str(PDF_DIR / f"{pid}.pdf"))
        hit = sections_hit(raw)
        row = {"paper_id": pid, "structured": structured, **{f"head_{k}": hit[k] for k in CORE}}
        rows6.append(row)
        for f in CORE:
            if structured:
                (per_field[f]["determinable_present" if hit[f] else "determinable_absent"]) and None
                per_field[f]["determinable_present" if hit[f] else "determinable_absent"] += 1
            else:
                per_field[f]["undeterminable"] += 1
            if hit[f]:
                heuristic_present[f] += 1
    (OUT / "field_presence.json").write_text(json.dumps({"per_field": per_field,
                                                        "heuristic_heading_present": heuristic_present,
                                                        "rows": rows6}, indent=2), encoding="utf-8")
    print(f"  full-text papers: {len(ft)}   with a structured (JATS/LaTeX) representation: "
          f"{sum(1 for r in rows6 if r['structured'])}   arXiv-LaTeX-available (not fetched): "
          f"{sum(1 for r in ft if r['pdf_source'] == 'arxiv')}")
    print(f"  {'field':12} det-present  det-absent  undeterminable   (heuristic-heading-present)")
    for f in CORE:
        pf = per_field[f]
        print(f"  {f:12} {pf['determinable_present']:>10}  {pf['determinable_absent']:>10}  "
              f"{pf['undeterminable']:>13}   ({heuristic_present[f]}/{len(ft)})")

    print(f"\nrows -> {OUT}")


if __name__ == "__main__":
    main()
