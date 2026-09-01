"""Phase 2 experiment - isolated multi-source full-text acquisition resolver.

Reads the live production corpus (data/raw_metadata/collected_papers.json) but
writes ONLY beneath experiments/document_evidence_pipeline/runs/<run_id>/.
It does not import production pipeline modules and never mutates data/.

For every paper it attempts to obtain a *validated* full-text artifact from each
candidate source and classifies the disposition as one of:

    FULL_TEXT      - a real PDF or JATS/XML full text was retrieved and validated
    ABSTRACT_ONLY  - only an abstract / TLDR is available from this source
    METADATA_ONLY  - the source knows the work but exposes no free full text
    FAILED         - request error, 4xx/5xx, or an unusable payload (HTML landing page)

Baseline arm ("current_pipeline") reflects what the shipped Stage 1 actually
produced: has_full_text + a real, text-bearing PDF on disk.

Usage:
    python resolve_corpus.py --run                 # all 60 papers, all sources
    python resolve_corpus.py --run --limit 8       # quick smoke test
    python resolve_corpus.py --run --skip arxiv    # skip slow arxiv politeness wait
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
CORPUS_PATH = ROOT / "data" / "raw_metadata" / "collected_papers.json"
PDF_DIR = ROOT / "data" / "pdfs"

# Courtesy routing only (OpenAlex/Crossref "polite pool"); not authentication and
# deliberately not a real person's address.
POLITE_MAILTO = "researchgpt-acquisition-benchmark@example.org"
UA = f"researchgpt-acquisition-benchmark/1.0 (mailto:{POLITE_MAILTO})"

FULL_TEXT = "FULL_TEXT"
ABSTRACT_ONLY = "ABSTRACT_ONLY"
METADATA_ONLY = "METADATA_ONLY"
FAILED = "FAILED"

# classification thresholds for "this PDF is real full text, not a stub/landing page"
MIN_PDF_BYTES = 20_000
MIN_PDF_CHARS = 2_000
MIN_PDF_PAGES = 2
MIN_XML_CHARS = 4_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5, check=False).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def git_dirty() -> bool:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                             text=True, timeout=5, check=False).stdout.strip()
        return bool(out)
    except Exception:
        return True


def external_ids(paper: dict[str, Any]) -> dict[str, str]:
    ext = paper.get("externalIds") or {}
    return {k: str(v) for k, v in ext.items() if v is not None}


def validate_pdf_bytes(data: bytes) -> dict[str, Any]:
    """Return {'ok': bool, 'chars': int, 'pages': int, 'reason': str} using PyMuPDF."""
    if not data.startswith(b"%PDF"):
        return {"ok": False, "chars": 0, "pages": 0, "reason": "not_pdf_magic"}
    if len(data) < MIN_PDF_BYTES:
        return {"ok": False, "chars": 0, "pages": 0, "reason": f"pdf_too_small_{len(data)}B"}
    try:
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        texts = [p.get_text() for p in doc]
        pages = doc.page_count
        doc.close()
        chars = sum(len(t) for t in texts)
        nonempty = sum(1 for t in texts if t.strip())
        ok = chars >= MIN_PDF_CHARS and nonempty >= MIN_PDF_PAGES
        return {"ok": ok, "chars": chars, "pages": pages, "nonempty_pages": nonempty,
                "reason": "ok" if ok else f"thin_text_{chars}chars_{nonempty}pages"}
    except Exception as exc:
        return {"ok": False, "chars": 0, "pages": 0, "reason": f"pdf_parse_error:{type(exc).__name__}"}


def looks_like_jats(text: str) -> bool:
    head = text[:4000].lower()
    return ("<article" in head and ("jats" in head or "<front" in head or "<body" in head)) or "<!doctype article" in head


def fetch(url: str, *, accept: str | None = None, cap_bytes: int = 6_000_000,
          timeout: int = 30) -> dict[str, Any]:
    """GET with a byte cap. Returns status/content_type/bytes/latency and the body."""
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    started = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True,
                            allow_redirects=True)
        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=65536):
            buf.write(chunk)
            if buf.tell() >= cap_bytes:
                break
        body = buf.getvalue()
        return {
            "ok": True, "http_status": resp.status_code,
            "content_type": (resp.headers.get("Content-Type") or "").split(";")[0].strip(),
            "final_url": resp.url, "bytes": len(body),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "body": body,
        }
    except requests.RequestException as exc:
        return {
            "ok": False, "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "body": b"",
        }


def classify_pdf_response(r: dict[str, Any]) -> dict[str, Any]:
    if not r.get("ok"):
        return {"disposition": FAILED, "reason": r.get("error", "request_failed"),
                "latency_ms": r.get("latency_ms")}
    if r["http_status"] >= 400:
        return {"disposition": FAILED, "reason": f"http_{r['http_status']}",
                "latency_ms": r["latency_ms"]}
    body = r["body"]
    v = validate_pdf_bytes(body)
    base = {"http_status": r["http_status"], "content_type": r["content_type"],
            "bytes": r["bytes"], "final_url": r["final_url"], "latency_ms": r["latency_ms"],
            "sha256": sha256_bytes(body) if body else None,
            "pdf_chars": v.get("chars"), "pdf_pages": v.get("pages")}
    if v["ok"]:
        return {**base, "disposition": FULL_TEXT, "reason": "validated_pdf", "format": "pdf"}
    # sometimes a "pdf" url returns HTML landing page
    if body[:512].lstrip().lower().startswith(b"<!doctype html") or b"<html" in body[:512].lower():
        return {**base, "disposition": FAILED, "reason": "html_landing_page", "format": "html"}
    return {**base, "disposition": FAILED, "reason": v["reason"], "format": "pdf?"}


# ---------------------------------------------------------------------------
# Per-source resolvers. Each returns a dict describing this source's disposition.
# ---------------------------------------------------------------------------

def arm_current_pipeline(paper: dict[str, Any]) -> dict[str, Any]:
    """What the shipped Stage 1 actually delivered for this paper."""
    pid = paper.get("paperId", "")
    has_ft = bool(paper.get("has_full_text"))
    pdf_path = paper.get("pdf_path")
    disp = {"provider": "current_pipeline", "identifier": pid, "url_type": "local_file"}
    if not has_ft or not pdf_path:
        return {**disp, "disposition": ABSTRACT_ONLY, "reason": "stage1_no_full_text"}
    p = Path(pdf_path)
    if not p.is_absolute():
        p = ROOT / pdf_path
    if not p.exists():
        return {**disp, "disposition": FAILED, "reason": "pdf_path_missing_on_disk",
                "pdf_path": str(p)}
    data = p.read_bytes()
    v = validate_pdf_bytes(data)
    return {**disp, "disposition": FULL_TEXT if v["ok"] else FAILED,
            "reason": v["reason"], "format": "pdf", "bytes": len(data),
            "sha256": sha256_bytes(data), "pdf_chars": v.get("chars"),
            "pdf_pages": v.get("pages"), "pdf_path": str(p)}


def arm_s2(paper: dict[str, Any]) -> dict[str, Any]:
    oa = paper.get("openAccessPdf") or {}
    url = (oa.get("url") or "").strip()
    disp = {"provider": "semantic_scholar", "identifier": paper.get("paperId", ""),
            "url_type": "openAccessPdf.url"}
    if not url:
        return {**disp, "disposition": ABSTRACT_ONLY if paper.get("abstract") else METADATA_ONLY,
                "reason": "no_openAccessPdf_url"}
    r = fetch(url)
    return {**disp, "url": url, **classify_pdf_response(r)}


def arm_arxiv(paper: dict[str, Any]) -> dict[str, Any]:
    ext = external_ids(paper)
    arxiv_id = ext.get("ArXiv")
    disp = {"provider": "arxiv", "identifier": arxiv_id or "", "url_type": "arxiv_pdf"}
    if not arxiv_id:
        return {**disp, "disposition": METADATA_ONLY, "reason": "no_arxiv_id"}
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    r = fetch(url)
    return {**disp, "url": url, **classify_pdf_response(r)}


def arm_openalex(paper: dict[str, Any]) -> dict[str, Any]:
    ext = external_ids(paper)
    doi = ext.get("DOI")
    disp = {"provider": "openalex", "identifier": doi or "", "url_type": "doi_lookup"}
    if not doi:
        return {**disp, "disposition": METADATA_ONLY, "reason": "no_doi"}
    meta_url = f"https://api.openalex.org/works/https://doi.org/{doi}?mailto={POLITE_MAILTO}"
    r = fetch(meta_url, accept="application/json")
    if not r.get("ok") or r["http_status"] >= 400:
        return {**disp, "disposition": FAILED,
                "reason": r.get("error") or f"http_{r.get('http_status')}",
                "latency_ms": r.get("latency_ms")}
    try:
        work = json.loads(r["body"])
    except Exception:
        return {**disp, "disposition": FAILED, "reason": "openalex_bad_json",
                "latency_ms": r["latency_ms"]}
    oa = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    pdf_url = best.get("pdf_url") or oa.get("oa_url")
    is_oa = bool(oa.get("is_oa"))
    meta = {**disp, "oa_status": oa.get("oa_status"), "is_oa": is_oa,
            "oa_url": oa.get("oa_url"), "best_oa_pdf_url": best.get("pdf_url"),
            "meta_latency_ms": r["latency_ms"]}
    if not pdf_url:
        return {**meta, "disposition": METADATA_ONLY if not is_oa else ABSTRACT_ONLY,
                "reason": "openalex_no_oa_pdf_url"}
    r2 = fetch(pdf_url)
    return {**meta, "url": pdf_url, **classify_pdf_response(r2)}


def arm_europepmc(paper: dict[str, Any]) -> dict[str, Any]:
    ext = external_ids(paper)
    doi = ext.get("DOI")
    pmid = ext.get("PubMed")
    pmcid = ext.get("PubMedCentral")
    disp = {"provider": "europepmc", "url_type": "epmc_fulltext"}
    query = None
    if pmcid:
        query = f"PMCID:PMC{pmcid.lstrip('PMC')}"
        disp["identifier"] = f"PMC{pmcid.lstrip('PMC')}"
    elif pmid:
        query = f"EXT_ID:{pmid} AND SRC:MED"
        disp["identifier"] = pmid
    elif doi:
        query = f'DOI:"{doi}"'
        disp["identifier"] = doi
    else:
        return {**disp, "disposition": METADATA_ONLY, "reason": "no_doi_pmid_pmcid"}
    search_url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                  f"?query={requests.utils.quote(query)}&format=json&resultType=core")
    r = fetch(search_url, accept="application/json")
    if not r.get("ok") or r["http_status"] >= 400:
        return {**disp, "disposition": FAILED,
                "reason": r.get("error") or f"http_{r.get('http_status')}",
                "latency_ms": r.get("latency_ms")}
    try:
        js = json.loads(r["body"])
        results = js.get("resultList", {}).get("result", [])
    except Exception:
        return {**disp, "disposition": FAILED, "reason": "epmc_bad_json"}
    if not results:
        return {**disp, "disposition": METADATA_ONLY, "reason": "epmc_no_record"}
    rec = results[0]
    got_pmcid = rec.get("pmcid")
    is_oa = rec.get("isOpenAccess") == "Y"
    in_epmc = rec.get("inEPMC") == "Y"
    meta = {**disp, "epmc_pmcid": got_pmcid, "is_open_access": is_oa, "in_epmc": in_epmc,
            "has_pdf_flag": rec.get("hasPDF"), "meta_latency_ms": r["latency_ms"]}
    if got_pmcid and in_epmc:
        xml_url = (f"https://www.ebi.ac.uk/europepmc/webservices/rest/{got_pmcid}/fullTextXML")
        r2 = fetch(xml_url, accept="application/xml")
        if r2.get("ok") and r2["http_status"] < 400 and r2["bytes"] > 0:
            text = r2["body"].decode("utf-8", "ignore")
            if looks_like_jats(text) and len(text) >= MIN_XML_CHARS:
                return {**meta, "url": xml_url, "disposition": FULL_TEXT,
                        "reason": "validated_jats_xml", "format": "jats_xml",
                        "bytes": r2["bytes"], "xml_chars": len(text),
                        "sha256": sha256_bytes(r2["body"]), "latency_ms": r2["latency_ms"]}
            return {**meta, "url": xml_url, "disposition": FAILED,
                    "reason": "epmc_xml_not_jats_or_thin", "bytes": r2["bytes"],
                    "latency_ms": r2["latency_ms"]}
        return {**meta, "disposition": FAILED, "reason": "epmc_xml_fetch_failed"}
    return {**meta, "disposition": ABSTRACT_ONLY if rec.get("abstractText") else METADATA_ONLY,
            "reason": "epmc_no_open_fulltext"}


def arm_crossref(paper: dict[str, Any]) -> dict[str, Any]:
    ext = external_ids(paper)
    doi = ext.get("DOI")
    disp = {"provider": "crossref", "identifier": doi or "", "url_type": "doi_lookup"}
    if not doi:
        return {**disp, "disposition": METADATA_ONLY, "reason": "no_doi"}
    url = f"https://api.crossref.org/works/{doi}?mailto={POLITE_MAILTO}"
    r = fetch(url, accept="application/json")
    if not r.get("ok") or r["http_status"] >= 400:
        return {**disp, "disposition": FAILED,
                "reason": r.get("error") or f"http_{r.get('http_status')}",
                "latency_ms": r.get("latency_ms")}
    try:
        msg = json.loads(r["body"]).get("message", {})
    except Exception:
        return {**disp, "disposition": FAILED, "reason": "crossref_bad_json"}
    links = msg.get("link") or []
    pdf_links = [l for l in links if l.get("content-type") == "application/pdf"]
    meta = {**disp, "meta_latency_ms": r["latency_ms"],
            "has_license": bool(msg.get("license")),
            "link_count": len(links), "pdf_link_count": len(pdf_links)}
    if not pdf_links:
        return {**meta, "disposition": METADATA_ONLY, "reason": "crossref_no_pdf_link"}
    pdf_url = pdf_links[0]["URL"]
    r2 = fetch(pdf_url)
    return {**meta, "url": pdf_url, **classify_pdf_response(r2)}


SOURCE_ARMS = {
    "s2": arm_s2,
    "arxiv": arm_arxiv,
    "openalex": arm_openalex,
    "europepmc": arm_europepmc,
    "crossref": arm_crossref,
}
# politeness delay (seconds) applied AFTER each call to this source
SOURCE_DELAY = {"arxiv": 3.0, "openalex": 0.2, "crossref": 0.2, "europepmc": 0.34, "s2": 0.2}


def resolve_paper(paper: dict[str, Any], skip: set[str]) -> dict[str, Any]:
    pid = paper.get("paperId", "")
    row: dict[str, Any] = {
        "paper_id": pid,
        "title": (paper.get("title") or "")[:200],
        "external_ids": external_ids(paper),
        "has_abstract": bool(paper.get("abstract")),
        "sources": {},
    }
    row["sources"]["current_pipeline"] = arm_current_pipeline(paper)
    for name, fn in SOURCE_ARMS.items():
        if name in skip:
            row["sources"][name] = {"provider": name, "disposition": "SKIPPED"}
            continue
        try:
            row["sources"][name] = fn(paper)
        except Exception as exc:
            row["sources"][name] = {"provider": name, "disposition": FAILED,
                                    "reason": f"resolver_exception:{type(exc).__name__}: {exc}"}
        time.sleep(SOURCE_DELAY.get(name, 0.2))

    # derived per-paper verdicts
    def has_ft(src: str) -> bool:
        return row["sources"].get(src, {}).get("disposition") == FULL_TEXT

    row["baseline_full_text"] = has_ft("current_pipeline")
    multi = {s for s in (*SOURCE_ARMS, "current_pipeline") if has_ft(s)}
    row["any_source_full_text"] = bool(multi)
    row["full_text_sources"] = sorted(multi)
    row["jats_available"] = row["sources"].get("europepmc", {}).get("format") == "jats_xml"
    row["newly_recoverable"] = row["any_source_full_text"] and not row["baseline_full_text"]
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    def count(pred) -> int:
        return sum(1 for r in rows if pred(r))
    per_source: dict[str, dict[str, int]] = {}
    for s in ("current_pipeline", *SOURCE_ARMS):
        c: dict[str, int] = {}
        for r in rows:
            d = r["sources"].get(s, {}).get("disposition", "MISSING")
            c[d] = c.get(d, 0) + 1
        per_source[s] = c
    baseline_ft = count(lambda r: r["baseline_full_text"])
    multi_ft = count(lambda r: r["any_source_full_text"])
    newly = [r["paper_id"] for r in rows if r["newly_recoverable"]]
    return {
        "papers": n,
        "baseline_full_text": baseline_ft,
        "baseline_full_text_rate": round(baseline_ft / n, 4) if n else None,
        "multi_source_full_text": multi_ft,
        "multi_source_full_text_rate": round(multi_ft / n, 4) if n else None,
        "delta_papers": multi_ft - baseline_ft,
        "newly_recoverable_paper_ids": newly,
        "jats_xml_available": count(lambda r: r["jats_available"]),
        "still_unrecoverable": count(lambda r: not r["any_source_full_text"]),
        "per_source_disposition": per_source,
        "full_text_source_attribution": _source_attr(rows),
    }


def _source_attr(rows: list[dict[str, Any]]) -> dict[str, int]:
    """For each paper with any full text, which sources could independently supply it."""
    tally: dict[str, int] = {}
    for r in rows:
        for s in r["full_text_sources"]:
            tally[s] = tally.get(s, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip", action="append", default=[],
                    help="source name(s) to skip: s2 arxiv openalex europepmc crossref")
    args = ap.parse_args()

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if args.limit:
        corpus = corpus[: args.limit]
    skip = set(args.skip)

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-acq-{os.urandom(3).hex()}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    started = utc_now()
    t0 = time.perf_counter()
    rows = []
    for i, paper in enumerate(corpus, 1):
        print(f"[{i}/{len(corpus)}] {paper.get('paperId','')[:12]}  {(paper.get('title') or '')[:60]}")
        row = resolve_paper(paper, skip)
        rows.append(row)
        fts = row["full_text_sources"]
        print(f"      baseline_ft={row['baseline_full_text']}  any_ft={row['any_source_full_text']}  "
              f"sources={fts}  jats={row['jats_available']}")
    elapsed = round(time.perf_counter() - t0, 1)

    summary = summarize(rows)
    manifest = {
        "run_id": run_id, "experiment": "phase2_acquisition_resolver",
        "started_at": started, "ended_at": utc_now(), "elapsed_seconds": elapsed,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "git_revision": git_revision(), "git_dirty": git_dirty(),
        "corpus_path": str(CORPUS_PATH.relative_to(ROOT)),
        "corpus_sha256": sha256_bytes(CORPUS_PATH.read_bytes()),
        "paper_count": len(corpus), "skipped_sources": sorted(skip),
        "sources": ["current_pipeline", *SOURCE_ARMS],
        "classification_thresholds": {
            "MIN_PDF_BYTES": MIN_PDF_BYTES, "MIN_PDF_CHARS": MIN_PDF_CHARS,
            "MIN_PDF_PAGES": MIN_PDF_PAGES, "MIN_XML_CHARS": MIN_XML_CHARS},
        "writes_under": str(run_dir), "production_paths_touched": False,
        "credentials_used": False, "polite_mailto": POLITE_MAILTO,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (run_dir / "acquisition_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (run_dir / "acquisition_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        f"# Phase 2 - Multi-source acquisition ({run_id})", "",
        f"- Corpus: {len(corpus)} papers ({manifest['corpus_path']}, sha256 {manifest['corpus_sha256'][:12]})",
        f"- Git: {manifest['git_revision'][:12]} (dirty={manifest['git_dirty']})",
        f"- Elapsed: {elapsed}s   Skipped sources: {sorted(skip) or 'none'}", "",
        "## Headline", "",
        f"- Baseline (shipped pipeline) full text: **{summary['baseline_full_text']}/{summary['papers']}** "
        f"({summary['baseline_full_text_rate']:.1%})",
        f"- Any-source full text: **{summary['multi_source_full_text']}/{summary['papers']}** "
        f"({summary['multi_source_full_text_rate']:.1%})",
        f"- Delta: **+{summary['delta_papers']} papers** newly recoverable",
        f"- Still unrecoverable: {summary['still_unrecoverable']}/{summary['papers']}",
        f"- JATS/XML full text available: {summary['jats_xml_available']}/{summary['papers']}", "",
        "## Which sources can supply full text (independently)", "",
        "| source | papers with validated full text |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in summary["full_text_source_attribution"].items()], "",
        "## Per-source disposition", "",
        "| source | " + " | ".join([FULL_TEXT, ABSTRACT_ONLY, METADATA_ONLY, FAILED, "SKIPPED"]) + " |",
        "|---|---|---|---|---|---|",
    ]
    for s, c in summary["per_source_disposition"].items():
        lines.append(f"| {s} | {c.get(FULL_TEXT,0)} | {c.get(ABSTRACT_ONLY,0)} | "
                     f"{c.get(METADATA_ONLY,0)} | {c.get(FAILED,0)} | {c.get('SKIPPED',0)} |")
    lines += ["", "## Newly recoverable paper ids", "",
              ", ".join(summary["newly_recoverable_paper_ids"]) or "(none)", ""]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "\n".join(lines))
    print(f"\nWrote {run_dir}")


if __name__ == "__main__":
    main()
