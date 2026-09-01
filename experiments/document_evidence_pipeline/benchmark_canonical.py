"""LEVEL 2 / LEVEL 3 benchmark for the canonical document-evidence pipeline.

  python benchmark_canonical.py --level2         # 6-paper representative subset
  python benchmark_canonical.py --level3         # full 60-paper corpus (ONE final run)
  python benchmark_canonical.py --level3 --no-cache-acq   # force re-acquisition

Reads live corpus (read-only). Writes only under runs/<run_id>/. Acquisition
artifacts are content-cached under pipeline/cache/ so re-runs don't re-hit the
network or re-parse.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time

# Windows console defaults to cp1252; paper titles/labels can contain
# characters outside it. Reconfigure so a stray character never crashes a run
# after hours of work.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from pipeline.run import prepare_paper, extract_paper  # noqa: E402
from pipeline.represent import build_document  # noqa: E402
from pipeline.chunker import chunk_document  # noqa: E402
from pipeline.index import RetrievalIndex  # noqa: E402
from pipeline.schema import (  # noqa: E402
    FULL_TEXT, NO_ACCESSIBLE_FULL_TEXT, ABSTRACT_ONLY, FAILED, BLOCKED,
    EVIDENCE_FIELDS, EXPLICIT, INFERRED, MISSING, UNSUPPORTED, RETURNED, ABSTAINED,
    OWN_PAPER, CITED_PAPER, UNKNOWN, validate_acquisition_record,
)

CORPUS = ROOT / "data" / "raw_metadata" / "collected_papers.json"
CACHE = HERE / "pipeline" / "cache"
ACQ_CACHE = CACHE / "_acq"
RUNS = HERE / "runs"

LEVEL2_IDS = [
    "2009dbb5",  # arXiv full text
    "ef1e4a16",  # OpenAlex PDF-only (newly recovered vs baseline)
    "0549e2e9",  # Europe PMC JATS/XML
    "c1e75f6f",  # abstract-only -> NO_ACCESSIBLE_FULL_TEXT
    "18ded60e",  # also inaccessible
    "f3b06a91",  # arXiv, contains comparison / cited-result language
]

LLM_CFG = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "temperature": 0.1}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def load_corpus(level2: bool) -> list[dict[str, Any]]:
    papers = json.loads(CORPUS.read_text(encoding="utf-8"))
    if not level2:
        return papers
    picked = []
    for pref in LEVEL2_IDS:
        for p in papers:
            if p["paperId"].startswith(pref):
                picked.append(p)
                break
    return picked


def prepare_with_cache(paper: dict[str, Any], use_cache: bool) -> dict[str, Any]:
    pid = paper["paperId"]
    ACQ_CACHE.mkdir(parents=True, exist_ok=True)
    acq_path = ACQ_CACHE / f"{pid}.json"
    pdf_path, xml_path = CACHE / f"{pid}.pdf", CACHE / f"{pid}.xml"

    if use_cache and acq_path.exists():
        acq = json.loads(acq_path.read_text(encoding="utf-8"))
        data = None
        if acq.get("representation_type") == "jats_xml" and xml_path.exists():
            data = xml_path.read_bytes()
        elif acq.get("representation_type") == "pdf" and pdf_path.exists():
            data = pdf_path.read_bytes()
        doc = build_document(acq, data, fallback_abstract=paper.get("abstract"))
        chunks = chunk_document(doc)
        return {"paper_id": pid, "title": paper.get("title", ""),
                "authors": [a.get("name", "") for a in (paper.get("authors") or []) if isinstance(a, dict)],
                "baseline_has_full_text": bool(paper.get("has_full_text")),
                "acquisition": acq, "document": {k: v for k, v in doc.items() if k != "blocks"},
                "blocks": doc["blocks"], "chunks": chunks, "prepare_seconds": 0.0, "cached": True}

    prepared = prepare_paper(paper, cache_dir=CACHE)
    acq_path.write_text(json.dumps(prepared["acquisition"], indent=2), encoding="utf-8")
    prepared["cached"] = False
    return prepared


def aggregate(paper_results: list[dict[str, Any]], prepared: list[dict[str, Any]],
              corpus: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(corpus)
    baseline_ft = sum(1 for p in corpus if p.get("has_full_text"))
    acq_status = Counter(pr["acquisition"]["status"] for pr in prepared)
    new_ft = sum(1 for pr in prepared if pr["acquisition"]["status"] == FULL_TEXT)
    repr_dist = Counter(pr["document"]["representation"] for pr in prepared)
    src_dist = Counter(pr["acquisition"].get("source") for pr in prepared
                       if pr["acquisition"]["status"] == FULL_TEXT)

    # identity / content rejections across all candidates considered
    id_fail = content_fail = 0
    for pr in prepared:
        for c in pr["acquisition"].get("candidates_considered", []):
            if c.get("identity_passed") is False:
                id_fail += 1
            if c.get("content_passed") is False:
                content_fail += 1

    # schema validity
    schema_problems = []
    for pr in prepared:
        schema_problems += validate_acquisition_record(pr["acquisition"])

    # evidence-level
    ev_rows = [e for r in paper_results for e in r["evidence"]]
    by_field: dict[str, Counter] = {f: Counter() for f in EVIDENCE_FIELDS}
    prov_valid = prov_total = 0
    returned_by_field: dict[str, int] = {f: 0 for f in EVIDENCE_FIELDS}
    attr_counts = Counter()
    for e in ev_rows:
        by_field[e["field"]][e["evidence_status"]] += 1
        if e["final"] == RETURNED:
            returned_by_field[e["field"]] += 1
        if e["evidence_status"] in (EXPLICIT, INFERRED):
            prov_total += 1
            prov_valid += 1 if e["provenance_valid"] else 0
        if e["field"] in ("results", "metrics") and e["evidence_status"] in (EXPLICIT, INFERRED):
            attr_counts[e["attribution"]] += 1

    fulltext_papers = {pr["paper_id"] for pr in prepared
                       if pr["acquisition"]["status"] == FULL_TEXT}
    noft_papers = {pr["paper_id"] for pr in prepared
                   if pr["acquisition"]["status"] in (NO_ACCESSIBLE_FULL_TEXT, ABSTRACT_ONLY, FAILED, BLOCKED)}
    # abstention correctness: for papers with no full text, quantitative fields MUST abstain
    noft_quant = [e for r in paper_results if r["paper_id"] in noft_papers
                  for e in r["evidence"] if e["field"] in ("dataset", "metrics", "results")]
    noft_quant_abstained = sum(1 for e in noft_quant if e["final"] == ABSTAINED)

    return {
        "corpus_size": n,
        "acquisition": {
            "baseline_full_text": baseline_ft,
            "baseline_full_text_rate": round(baseline_ft / n, 4),
            "new_full_text": new_ft,
            "new_full_text_rate": round(new_ft / n, 4),
            "delta_papers": new_ft - baseline_ft,
            "status_distribution": dict(acq_status),
            "representation_distribution": dict(repr_dist),
            "full_text_source_distribution": dict(src_dist),
            "identity_validation_failures": id_fail,
            "content_validation_failures": content_fail,
            "wrong_paper_accepted": _wrong_paper_accepted(prepared),
            "schema_problems": schema_problems,
        },
        "evidence": {
            "fields": {f: dict(by_field[f]) for f in EVIDENCE_FIELDS},
            "returned_by_field": returned_by_field,
            "provenance_valid_rate": round(prov_valid / prov_total, 4) if prov_total else None,
            "provenance_checked": prov_total,
            "attribution_on_quantitative": dict(attr_counts),
            "abstention_on_no_fulltext_quant": {
                "total_quant_fields": len(noft_quant),
                "abstained": noft_quant_abstained,
                "abstention_rate": round(noft_quant_abstained / len(noft_quant), 4) if noft_quant else None,
            },
        },
    }


def _wrong_paper_accepted(prepared: list[dict[str, Any]]) -> int:
    """An accepted FULL_TEXT whose identity signals look wrong = title_similarity < 0.3 and no doi hit."""
    bad = 0
    for pr in prepared:
        acq = pr["acquisition"]
        if acq["status"] != FULL_TEXT:
            continue
        sig = acq["identity_validation"].get("signals", {})
        if sig.get("title_similarity", 0) < 0.3 and not sig.get("doi_in_doc"):
            bad += 1
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level2", action="store_true")
    ap.add_argument("--level3", action="store_true")
    ap.add_argument("--no-cache-acq", action="store_true")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()
    if not (args.level2 or args.level3):
        ap.error("choose --level2 or --level3")
    level2 = args.level2

    corpus = load_corpus(level2)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-canon-{'L2' if level2 else 'L3'}-{os.urandom(2).hex()}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    started = utc()
    t0 = time.perf_counter()

    print(f"== {run_id} :: {len(corpus)} papers ==")
    prepared: list[dict[str, Any]] = []
    for i, paper in enumerate(corpus, 1):
        pr = prepare_with_cache(paper, use_cache=not args.no_cache_acq)
        prepared.append(pr)
        a = pr["acquisition"]
        print(f"[{i}/{len(corpus)}] {pr['paper_id'][:12]} {a['status']:22} "
              f"src={a.get('source')} repr={pr['document']['representation']} "
              f"blocks={pr['document']['n_blocks']} chunks={len(pr['chunks'])} cached={pr.get('cached')}")
    acq_seconds = round(time.perf_counter() - t0, 1)

    print("-- building shared retrieval index --")
    index = RetrievalIndex(device=args.device, fresh=True)
    total_chunks = 0
    for pr in prepared:
        total_chunks += index.add_chunks(pr["chunks"])
    print(f"   indexed {total_chunks} chunks")

    print("-- extraction (LLM) --")
    t1 = time.perf_counter()
    paper_results = []
    for i, pr in enumerate(prepared, 1):
        res = extract_paper(pr, index, LLM_CFG)
        paper_results.append(res)
        print(f"[{i}/{len(prepared)}] {pr['paper_id'][:12]} returned={res['n_returned']} "
              f"abstained={res['n_abstained']} status={res['acquisition_status']}")
    extract_seconds = round(time.perf_counter() - t1, 1)

    vram = {}
    try:
        import torch
        if torch.cuda.is_available():
            vram = {"peak_torch_vram_mb": round(torch.cuda.max_memory_allocated() / 2**20, 1),
                    "reserved_torch_vram_mb": round(torch.cuda.max_memory_reserved() / 2**20, 1)}
    except Exception:
        pass

    summary = aggregate(paper_results, prepared, corpus)
    manifest = {
        "run_id": run_id, "level": 2 if level2 else 3, "started_at": started, "ended_at": utc(),
        "acq_seconds": acq_seconds, "extract_seconds": extract_seconds,
        "total_seconds": round(time.perf_counter() - t0, 1),
        "seconds_per_paper_extract": round(extract_seconds / max(1, len(prepared)), 1),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "git_revision": git_rev(),
        "corpus_path": str(CORPUS.relative_to(ROOT)),
        "corpus_sha256": __import__("hashlib").sha256(CORPUS.read_bytes()).hexdigest(),
        "paper_count": len(corpus), "llm": LLM_CFG, "device": args.device, **vram,
        "reranker_used": False, "production_paths_touched": False, "credentials_used": False,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "acquisition_records.json").write_text(
        json.dumps([pr["acquisition"] for pr in prepared], indent=2), encoding="utf-8")
    (run_dir / "documents.json").write_text(
        json.dumps([pr["document"] for pr in prepared], indent=2), encoding="utf-8")
    (run_dir / "evidence_results.json").write_text(json.dumps(paper_results, indent=2), encoding="utf-8")

    a = summary["acquisition"]; e = summary["evidence"]
    lines = [
        f"# Canonical pipeline — {'LEVEL 2 subset' if level2 else 'LEVEL 3 full corpus'} ({run_id})", "",
        f"- git {manifest['git_revision'][:12]} · {manifest['paper_count']} papers · "
        f"acq {acq_seconds}s · extract {extract_seconds}s · device {args.device} · reranker OFF", "",
        "## Acquisition", "",
        f"- Baseline full text: {a['baseline_full_text']}/{summary['corpus_size']} ({a['baseline_full_text_rate']:.1%})",
        f"- Canonical full text: {a['new_full_text']}/{summary['corpus_size']} ({a['new_full_text_rate']:.1%})  "
        f"-> delta {a['delta_papers']:+d}",
        f"- Status: {a['status_distribution']}",
        f"- Representation: {a['representation_distribution']}",
        f"- Full-text source: {a['full_text_source_distribution']}",
        f"- Identity-validation candidate rejections: {a['identity_validation_failures']}",
        f"- Content-validation candidate rejections: {a['content_validation_failures']}",
        f"- **Wrong-paper accepted: {a['wrong_paper_accepted']}**",
        f"- Schema problems: {a['schema_problems'] or 'none'}", "",
        "## Evidence", "",
        f"- Provenance-valid rate (of EXPLICIT/INFERRED items): {e['provenance_valid_rate']} "
        f"(n={e['provenance_checked']})",
        f"- Attribution on quantitative fields: {e['attribution_on_quantitative']}",
        f"- Abstention on no-full-text quantitative fields: "
        f"{e['abstention_on_no_fulltext_quant']['abstained']}/{e['abstention_on_no_fulltext_quant']['total_quant_fields']} "
        f"({e['abstention_on_no_fulltext_quant']['abstention_rate']})", "",
        "| field | EXPLICIT | INFERRED | UNSUPPORTED | MISSING | RETURNED |", "|---|---|---|---|---|---|",
    ]
    for f in EVIDENCE_FIELDS:
        fc = e["fields"][f]
        lines.append(f"| {f} | {fc.get(EXPLICIT,0)} | {fc.get(INFERRED,0)} | {fc.get(UNSUPPORTED,0)} "
                     f"| {fc.get(MISSING,0)} | {e['returned_by_field'][f]} |")
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nwrote {run_dir}")


if __name__ == "__main__":
    main()
