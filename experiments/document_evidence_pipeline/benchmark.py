"""Read-only repository baseline and source/parser feasibility benchmark.

The benchmark intentionally avoids production imports and writes only beneath
``experiments/document_evidence_pipeline/runs/<run_id>``.  It treats existing
JSON and PDF files as observations, never as mutable benchmark inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = Path(__file__).resolve().parent / "runs"
JSON_FILES = ("collected_papers.json", "chunks.json", "paper_summaries.json", "extraction_cache.json",
              "extraction_quality_audit.json", "weak_extractions.json", "automated_retrieval_benchmark.json",
              "figures_manifest.json", "gap_matrix.json", "retry_progress.json")
ID_KEYS = ("paper_id", "paperId", "paperId", "id", "corpus_id", "chunk_id", "chunkId")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return []


def record_count(value: Any) -> int:
    return len(value) if isinstance(value, (list, dict)) else 0


def identifier(record: dict[str, Any]) -> str | None:
    for key in ID_KEYS:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def field_value(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def memory_mb() -> float | None:
    if resource is None:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(usage / (1024 * 1024), 3) if sys.platform != "win32" else round(usage / 1024, 3)
    except (AttributeError, OSError):
        return None


def inventory(path: Path) -> dict[str, Any]:
    files = [item for item in path.rglob("*") if item.is_file()] if path.exists() else []
    return {"exists": path.exists(), "file_count": len(files),
            "byte_count": sum(item.stat().st_size for item in files),
            "suffix_counts": {suffix: sum(item.suffix.lower() == suffix for item in files)
                              for suffix in sorted({item.suffix.lower() or "<none>" for item in files})}}


def load_baseline() -> tuple[dict[str, Any], dict[str, Any]]:
    raw_path = ROOT / "data" / "raw_metadata" / "collected_papers.json"
    processed = ROOT / "data" / "processed"
    raw = safe_json(raw_path) or []
    papers = items(raw)
    chunks = items(safe_json(processed / "chunks.json"))
    summaries = items(safe_json(processed / "paper_summaries.json"))
    weak_value = safe_json(processed / "weak_extractions.json")
    weak = items(weak_value)
    pdfs = list((ROOT / "data" / "pdfs").rglob("*.pdf")) if (ROOT / "data" / "pdfs").exists() else []
    paper_ids = {identifier(paper) for paper in papers} - {None}
    chunk_paper_ids = {identifier(chunk) for chunk in chunks if identifier(chunk)}
    availability: dict[str, int] = {"abstract_present": 0, "abstract_missing": 0,
                                     "full_text_present": 0, "full_text_missing": 0}
    type_counts: dict[str, dict[str, int]] = {}
    field_presence: dict[str, int] = {}
    for paper in papers:
        abstract = field_value(paper, ("abstract", "abstractText", "abstract_text"))
        full_text = field_value(paper, ("full_text", "fullText", "full_text_path", "pdf_path", "pdfPath"))
        availability["abstract_present" if isinstance(abstract, str) and abstract.strip() else "abstract_missing"] += 1
        has_full = bool(full_text) or bool(paper.get("has_full_text")) or any(pid and pid in pdf.name for pdf in pdfs for pid in [identifier(paper)])
        availability["full_text_present" if has_full else "full_text_missing"] += 1
        for key, value in paper.items():
            field_presence[key] = field_presence.get(key, 0) + 1
            type_counts.setdefault(key, {})[type(value).__name__] = type_counts.setdefault(key, {}).get(type(value).__name__, 0) + 1
    chunks_by_paper: dict[str, int] = {}
    for chunk in chunks:
        pid = identifier(chunk)
        if pid:
            chunks_by_paper[pid] = chunks_by_paper.get(pid, 0) + 1
    covered = paper_ids & set(chunks_by_paper)
    verifier = deterministic_metrics()
    artifact_consistency = stage_consistency(papers, chunks, summaries, weak)
    baseline = {
        "status": "measured",
        "paper_count": len(papers),
        "paper_id_count": len(paper_ids),
        "abstract_full_text_availability": availability,
        "pdf_count": len(pdfs),
        "chunk_count": len(chunks),
        "chunk_coverage": {"papers_with_chunks": len(covered), "papers_without_chunks": len(paper_ids - covered),
                            "coverage_rate": len(covered) / len(paper_ids) if paper_ids else None,
                            "chunk_paper_ids_without_metadata": len(set(chunks_by_paper) - paper_ids)},
        "field_presence_count": dict(sorted(field_presence.items())),
        "field_type_counts": {key: dict(sorted(value.items())) for key, value in sorted(type_counts.items())},
        "weak_extraction_count": record_count(weak_value),
        "current_deterministic_verifier": verifier,
        "stage_artifact_id_consistency": artifact_consistency,
        "timing_ms": {"baseline_read_and_measure": None},
        "peak_memory_mb": memory_mb(),
    }
    return baseline, {"papers": papers, "pdfs": pdfs, "chunks": chunks}


def deterministic_metrics() -> dict[str, Any]:
    """Run the checked-in deterministic verifier without modifying its fixtures."""
    try:
        from runner import build_cases, make_fixture, oracle  # local experiment module only
        run_id = "benchmark-verifier"
        results = [oracle(make_fixture(spec, run_id), run_id) for spec in build_cases()]
        abstentions = [item for item in results if item["expected"] in ("abstained", "unsupported", "conflicting")]
        cited = [item for item in results if item["expected"] == "CITED_PAPER"]
        return {"status": "measured", "case_count": len(results), "passed": sum(item["status"] == "pass" for item in results),
                "failed": sum(item["status"] == "fail" for item in results),
                "citation_validity": sum(item["citation_valid"] for item in results) / len(results),
                "abstention_precision": sum(item["status"] == "pass" for item in abstentions) / len(abstentions),
                "cited_paper_false_own_rate": sum(item["actual"] == "OWN_PAPER" for item in cited) / len(cited),
                "provenance_valid_rate": sum(item["provenance_valid"] for item in results) / len(results)}
    except Exception as exc:  # benchmark must still emit baseline evidence
        return {"status": "blocked", "reason": type(exc).__name__}


def stage_consistency(papers: list[dict[str, Any]], chunks: list[dict[str, Any]], summaries: list[dict[str, Any]], weak: list[dict[str, Any]]) -> dict[str, Any]:
    sets = {"raw_metadata": {identifier(item) for item in papers if identifier(item)},
            "chunks": {identifier(item) for item in chunks if identifier(item)},
            "summaries": {identifier(item) for item in summaries if identifier(item)},
            "weak_extractions": {identifier(item) for item in weak if identifier(item)}}
    core_sets = [sets[name] for name in ("raw_metadata", "chunks", "summaries")]
    union = set().union(*core_sets) if core_sets else set()
    common = set.intersection(*core_sets) if core_sets else set()
    return {"status": "measured", "artifact_id_counts": {key: len(value) for key, value in sets.items()},
            "union_id_count": len(union), "intersection_id_count": len(common),
            "ids_not_shared_by_all": {key: len(value - common) for key, value in sets.items()},
            "note": "ID keys are inferred from common field names; hashes are not recomputed across semantic stages."}


def probe_url(url: str, label: str) -> dict[str, Any]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "researchgpt-evidence-benchmark/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            body = response.read(4096)
            return {"source": label, "status": "measured", "http_status": response.status,
                    "content_type": response.headers.get("Content-Type"), "sample_bytes": len(body),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"source": label, "status": "blocked", "reason": type(exc).__name__,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def source_probes(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dois: list[str] = []
    pmids: list[str] = []
    for paper in papers:
        doi = field_value(paper, ("doi", "DOI"))
        pmid = field_value(paper, ("pmid", "PMID", "pubmed_id"))
        if isinstance(paper.get("externalIds"), dict):
            doi = doi or paper["externalIds"].get("DOI")
            pmid = pmid or paper["externalIds"].get("PubMed") or paper["externalIds"].get("PMID")
        if doi and str(doi) not in dois:
            dois.append(str(doi))
        if pmid and str(pmid) not in pmids:
            pmids.append(str(pmid))
    probes: list[dict[str, Any]] = [{"source": "OpenAlex", "status": "blocked", "reason": "no_applicable_identifier"},
                                    {"source": "Crossref", "status": "blocked", "reason": "no_applicable_identifier"},
                                    {"source": "Unpaywall", "status": "blocked", "reason": "no_applicable_identifier"},
                                    {"source": "Europe PMC", "status": "blocked", "reason": "no_applicable_identifier"}]
    if dois:
        encoded = urllib.parse.quote(dois[0], safe="")
        probes[0] = probe_url(f"https://api.openalex.org/works/https://doi.org/{encoded}", "OpenAlex")
        probes[1] = probe_url(f"https://api.crossref.org/works/{encoded}", "Crossref")
        probes[2] = {"source": "Unpaywall", "status": "blocked", "reason": "email_parameter_required; no secret supplied"}
    if pmids:
        probes[3] = probe_url(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{urllib.parse.quote(pmids[0])}&format=json", "Europe PMC")
    for probe in probes:
        probe["identifier_applicable"] = probe["source"] in ("OpenAlex", "Crossref", "Unpaywall") and bool(dois) or probe["source"] == "Europe PMC" and bool(pmids)
        probe["credential_configured"] = False
    return probes


def parser_results(pdfs: list[Path]) -> dict[str, Any]:
    result: dict[str, Any] = {"tool_availability": {}, "pymupdf": {"status": "blocked", "sample": None}, "proxies": {}}
    for name, module in (("PyMuPDF", "fitz"), ("ChromaDB", "chromadb"), ("requests", "requests"), ("psutil", "psutil"),
                         ("GROBID", "grobid_client"), ("Docling", "docling"), ("MinerU", "mineru")):
        result["tool_availability"][name] = {"available": importlib.util.find_spec(module) is not None}
    if result["tool_availability"]["PyMuPDF"]["available"] and pdfs:
        started = time.perf_counter()
        try:
            import fitz
            document = fitz.open(pdfs[0])
            texts = [page.get_text("text") for page in document]
            text = "\n".join(texts)
            result["pymupdf"] = {"status": "measured", "sample_pdf": pdfs[0].name, "page_count": len(document),
                                  "text_chars": len(text), "nonempty_pages": sum(bool(item.strip()) for item in texts),
                                  "latency_ms": round((time.perf_counter() - started) * 1000, 3), "peak_memory_mb": memory_mb()}
        except Exception as exc:
            result["pymupdf"] = {"status": "blocked", "reason": type(exc).__name__}
    elif not pdfs:
        result["pymupdf"] = {"status": "blocked", "reason": "no_local_pdf"}
    result["proxies"] = {"sections": "pending", "tables": "pending", "figures": "pending",
                          "reason": "Current PyMuPDF text probe does not establish structural section/table/figure recall."}
    return result


def chroma_status() -> dict[str, Any]:
    path = ROOT / "data" / "chroma_db"
    if importlib.util.find_spec("chromadb") is None:
        return {"status": "blocked", "reason": "chromadb_not_importable", "path_exists": path.exists()}
    started = time.perf_counter()
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(path))
        collections = client.list_collections()
        return {"status": "measured", "collection_count": len(collections),
                "collections": [{"name": c.name, "count": c.count()} for c in collections],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
    except BaseException as exc:
        return {"status": "blocked", "reason": type(exc).__name__, "path_exists": path.exists()}


def run() -> Path:
    started = utc_now()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.urandom(4).hex()}"
    run_dir = OUT_ROOT / run_id
    if run_dir.exists():
        raise RuntimeError("run collision refused")
    run_dir.mkdir(parents=True)
    started_clock = time.perf_counter()
    baseline, context = load_baseline()
    baseline["timing_ms"]["baseline_read_and_measure"] = round((time.perf_counter() - started_clock) * 1000, 3)
    sources = source_probes(context["papers"])
    parsers = parser_results(context["pdfs"])
    chroma = chroma_status()
    cells = {letter: {"status": "PENDING", "metrics": None, "reason": "Cell A-E execution not part of read-only baseline pass"} for letter in "ABCDE"}
    manifest = {"run_id": run_id, "schema_version": "document-evidence-baseline-1", "started_at": started,
                "ended_at": utc_now(), "python": sys.version, "platform": platform.platform(),
                "git_revision": git_revision(), "git_dirty": git_dirty(), "source_roots": ["data/raw_metadata", "data/processed", "data/pdfs", "data/chroma_db"],
                "writes_under": str(run_dir), "production_paths_touched": False, "production_chromadb_writes": False,
                "secrets_present": False, "credentials": {"credential_configured": False},
                "input_file_sha256": input_hashes(), "cells": cells}
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "baseline.json", baseline)
    write_json(run_dir / "source_results.json", {"status": "measured", "probes": sources})
    write_json(run_dir / "parser_results.json", {"status": "measured", "parsers": parsers, "chroma": chroma})
    decision = "READY" if all(item.get("status") == "measured" for item in (baseline,)) and all(cell["status"] == "MEASURED" for cell in cells.values()) else "NOT READY"
    report = [f"# Document Evidence Baseline ({run_id})", "", f"Decision: **{decision}**", "",
              "## Baseline", f"- Papers: {baseline['paper_count']}", f"- PDFs: {baseline['pdf_count']}",
              f"- Chunks: {baseline['chunk_count']}", f"- Weak extractions: {baseline['weak_extraction_count']}",
              f"- Chunk coverage: {baseline['chunk_coverage']['coverage_rate']}",
              f"- Deterministic verifier: {baseline['current_deterministic_verifier']}",
              f"- Stage ID consistency: {baseline['stage_artifact_id_consistency']}", "",
              "## Source and parser probes", *[f"- {probe['source']}: {probe['status']} ({probe.get('reason', probe.get('http_status', 'n/a'))})" for probe in sources],
              f"- PyMuPDF: {parsers['pymupdf']['status']}", f"- ChromaDB: {chroma['status']}",
              f"- Optional structural parsers: {parsers['tool_availability']}", "",
              "## Cells A-E", "", "| Cell | Status |", "|---|---|", *[f"| {letter} | PENDING |" for letter in "ABCDE"], "",
              "## Limitations", "- A-E retrieval, reranking, structured extraction, stress, and abstention cells remain PENDING.",
              "- Structural section/table/figure proxies remain PENDING; text extraction alone is not structural validation.",
              "- Unpaywall was not called because its public endpoint requires a contact email; no credential or secret was supplied.",
              "- The decision is NOT READY until the required cells and structural/parser evidence are measured."]
    (run_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return run_dir


def git_revision() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=3, check=False).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def git_dirty() -> bool | None:
    try:
        return bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=3, check=False).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def input_hashes() -> dict[str, str]:
    paths = [ROOT / "data" / "raw_metadata" / "collected_papers.json"] + [ROOT / "data" / "processed" / name for name in JSON_FILES]
    result = {}
    for path in paths:
        if path.exists():
            result[str(path.relative_to(ROOT))] = digest_bytes(path.read_bytes())
    return result


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="run isolated read-only document evidence baseline")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        parser.error("use --run")
    print(run())


if __name__ == "__main__":
    main()