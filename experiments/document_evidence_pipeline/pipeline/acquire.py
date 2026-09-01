"""P0 - canonical acquisition + identity + content validation.

Reuses the sibling resolver's HTTP/validation helpers (read-only import) and
adds: candidate ordering (structured representation preferred), deterministic
identity validation (no wrong-paper acceptance), deterministic content
validation (no landing page / abstract / error page accepted), and a single
canonical acquisition record per paper.
"""
from __future__ import annotations

import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ACQ_DIR = HERE.parent / "acquisition"
if str(ACQ_DIR) not in sys.path:
    sys.path.insert(0, str(ACQ_DIR))

import requests  # noqa: E402
from resolve_corpus import (  # noqa: E402  (sibling experiment module, read-only helpers)
    fetch, validate_pdf_bytes, looks_like_jats, sha256_bytes,
    POLITE_MAILTO, external_ids as _ext_ids,
)

from .schema import (  # noqa: E402
    FULL_TEXT, NO_ACCESSIBLE_FULL_TEXT, FAILED, BLOCKED,
    REPR_JATS, REPR_PDF, REPR_NONE,
    canonical_acquisition_record, title_similarity, norm_tokens,
)

MIN_BODY_WORDS = 1500
MIN_JATS_SECS = 2


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------
def discover_candidates(paper: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered candidate list. Structured (JATS) first, then reliable PDF
    (arXiv), then opportunistic PDF (S2 / OpenAlex / Crossref)."""
    ext = _ext_ids(paper)
    cands: list[dict[str, Any]] = []

    pmcid = ext.get("PubMedCentral")
    if pmcid:
        pmc = "PMC" + pmcid.lstrip("PMC")
        cands.append({"source": "europepmc", "representation_type": REPR_JATS,
                      "url": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML",
                      "identifier": pmc})

    arxiv_id = ext.get("ArXiv")
    if arxiv_id:
        cands.append({"source": "arxiv", "representation_type": REPR_PDF,
                      "url": f"https://arxiv.org/pdf/{arxiv_id}.pdf", "identifier": arxiv_id})

    oa = (paper.get("openAccessPdf") or {}).get("url")
    if oa:
        cands.append({"source": "semantic_scholar", "representation_type": REPR_PDF,
                      "url": oa.strip(), "identifier": paper.get("paperId", "")})

    doi = ext.get("DOI")
    if doi:
        cands.append({"source": "openalex", "representation_type": REPR_PDF,
                      "url": None, "identifier": doi, "needs": "openalex_lookup"})
        cands.append({"source": "crossref", "representation_type": REPR_PDF,
                      "url": None, "identifier": doi, "needs": "crossref_lookup"})
    return cands


def _resolve_openalex_pdf(doi: str) -> tuple[str | None, dict[str, Any]]:
    r = fetch(f"https://api.openalex.org/works/https://doi.org/{doi}?mailto={POLITE_MAILTO}",
              accept="application/json", cap_bytes=1_000_000)
    if not r.get("ok") or r["http_status"] >= 400:
        return None, {"reason": r.get("error") or f"http_{r.get('http_status')}"}
    try:
        import json
        work = json.loads(r["body"])
    except Exception:
        return None, {"reason": "openalex_bad_json"}
    best = work.get("best_oa_location") or {}
    oa = work.get("open_access") or {}
    return best.get("pdf_url") or oa.get("oa_url"), {"is_oa": bool(oa.get("is_oa")),
                                                     "oa_status": oa.get("oa_status")}


def _resolve_crossref_pdf(doi: str) -> tuple[str | None, dict[str, Any]]:
    r = fetch(f"https://api.crossref.org/works/{doi}?mailto={POLITE_MAILTO}",
              accept="application/json", cap_bytes=1_000_000)
    if not r.get("ok") or r["http_status"] >= 400:
        return None, {"reason": r.get("error") or f"http_{r.get('http_status')}"}
    try:
        import json
        msg = json.loads(r["body"]).get("message", {})
    except Exception:
        return None, {"reason": "crossref_bad_json"}
    pdfs = [l for l in (msg.get("link") or []) if l.get("content-type") == "application/pdf"]
    return (pdfs[0]["URL"] if pdfs else None), {"link_count": len(msg.get("link") or [])}


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def _pdf_title_text(data: bytes) -> str:
    try:
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        txt = "\n".join(p.get_text() for p in list(doc)[:2])
        doc.close()
        return txt
    except Exception:
        return ""


def _jats_parts(data: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return {"ok": False, "reason": f"xml_parse_error:{exc}"}
    tag = root.tag.split("}")[-1]
    if tag != "article":
        return {"ok": False, "reason": f"root_not_article:{tag}"}
    title_el = root.find(".//{*}article-title")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""
    body = root.find(".//{*}body")
    secs = body.findall(".//{*}sec") if body is not None else []
    body_text = " ".join("".join(p.itertext()) for p in (body.iter() if body is not None else []))
    return {"ok": True, "title": title, "n_secs": len(secs),
            "body_words": len(body_text.split()), "root": root}


def content_validate(rep_type: str, data: bytes) -> dict[str, Any]:
    """Deterministic: is this a substantive article body (not landing/abstract/error)?"""
    if not data:
        return {"checked": True, "passed": False, "reason": "empty_response", "metrics": {}}
    head = data[:400].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<title>error" in head:
        return {"checked": True, "passed": False, "reason": "html_or_error_page", "metrics": {}}

    if rep_type == REPR_JATS:
        j = _jats_parts(data)
        if not j["ok"]:
            return {"checked": True, "passed": False, "reason": j["reason"], "metrics": {}}
        ok = j["n_secs"] >= MIN_JATS_SECS and j["body_words"] >= MIN_BODY_WORDS
        return {"checked": True, "passed": ok,
                "reason": "ok" if ok else f"thin_jats_secs{j['n_secs']}_words{j['body_words']}",
                "metrics": {"n_secs": j["n_secs"], "body_words": j["body_words"]}}

    # PDF
    v = validate_pdf_bytes(data)
    words = (v.get("chars") or 0) / 6  # rough
    ok = v["ok"] and (words >= MIN_BODY_WORDS or (v.get("pages") or 0) >= 3)
    return {"checked": True, "passed": bool(ok),
            "reason": "ok" if ok else (v["reason"] if not v["ok"] else f"abstract_sized_{int(words)}w"),
            "metrics": {"pdf_chars": v.get("chars"), "pdf_pages": v.get("pages"),
                        "nonempty_pages": v.get("nonempty_pages")}}


def identity_validate(paper: dict[str, Any], rep_type: str, data: bytes) -> dict[str, Any]:
    """Deterministic: does this document actually belong to `paper`? No wrong-paper accept."""
    meta_title = paper.get("title") or ""
    ext = _ext_ids(paper)
    doi = (ext.get("DOI") or "").lower()
    authors = [a.get("name", "") for a in (paper.get("authors") or []) if isinstance(a, dict)]
    surnames = [n.split()[-1].lower() for n in authors if n.split()]

    if rep_type == REPR_JATS:
        j = _jats_parts(data)
        doc_title = j.get("title", "") if j.get("ok") else ""
        probe = doc_title
        blob = (doc_title + " " + " ".join(
            "".join(el.itertext()) for el in j["root"].iter() if el.tag.split("}")[-1] == "surname"
        )).lower() if j.get("ok") else ""
    else:
        probe = _pdf_title_text(data)
        blob = probe.lower()

    t_sim = title_similarity(meta_title, probe)
    doi_hit = bool(doi) and doi in blob
    surn_hits = sum(1 for s in surnames if s and len(s) > 2 and s in blob)
    surn_frac = surn_hits / len(surnames) if surnames else 0.0

    passed = (
        t_sim >= 0.60
        or (doi_hit and t_sim >= 0.30)
        or (surn_frac >= 0.5 and t_sim >= 0.40)
    )
    reason = "ok" if passed else f"title_sim={t_sim:.2f} doi_hit={doi_hit} surname_frac={surn_frac:.2f}"
    return {"checked": True, "passed": bool(passed),
            "signals": {"title_similarity": round(t_sim, 3), "doi_in_doc": doi_hit,
                        "author_surname_frac": round(surn_frac, 3)},
            "reason": reason}


def _confidence(identity: dict, content: dict, rep_type: str) -> float:
    base = 0.5 * identity["signals"].get("title_similarity", 0.0)
    if identity["signals"].get("doi_in_doc"):
        base += 0.2
    base += 0.2 * identity["signals"].get("author_surname_frac", 0.0)
    if content["passed"]:
        base += 0.25
    if rep_type == REPR_JATS:
        base += 0.05
    return round(min(1.0, base), 3)


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------
def acquire_paper(paper: dict[str, Any], cache_dir: Path | None = None) -> tuple[dict[str, Any], bytes | None]:
    """Return (canonical_acquisition_record, accepted_document_bytes_or_None)."""
    pid = paper.get("paperId", "")
    rec = canonical_acquisition_record(pid)
    ext = _ext_ids(paper)
    rec["doi"] = ext.get("DOI")
    rec["other_identifiers"] = ext
    rec["provenance"] = {"discovery": "semantic_scholar_search"}
    abstract_available = bool(paper.get("abstract"))

    t0 = time.perf_counter()
    accepted_bytes: bytes | None = None
    for cand in discover_candidates(paper):
        entry = {"source": cand["source"], "representation_type": cand["representation_type"],
                 "identifier": cand.get("identifier")}
        url = cand["url"]
        meta: dict[str, Any] = {}
        if cand.get("needs") == "openalex_lookup":
            url, meta = _resolve_openalex_pdf(cand["identifier"])
        elif cand.get("needs") == "crossref_lookup":
            url, meta = _resolve_crossref_pdf(cand["identifier"])
        entry.update(meta)
        if not url:
            entry.update({"status": "no_url", "reason": meta.get("reason", "no_candidate_url")})
            rec["candidates_considered"].append(entry)
            time.sleep(0.2)
            continue

        r = fetch(url, cap_bytes=8_000_000)
        entry["url"] = url
        entry["latency_ms"] = r.get("latency_ms")
        if not r.get("ok") or r["http_status"] >= 400:
            entry.update({"status": FAILED, "reason": r.get("error") or f"http_{r.get('http_status')}"})
            rec["candidates_considered"].append(entry)
            time.sleep(0.3 if cand["source"] != "arxiv" else 3.0)
            continue

        data = r["body"]
        content = content_validate(cand["representation_type"], data)
        identity = identity_validate(paper, cand["representation_type"], data)
        entry.update({"content_passed": content["passed"], "content_reason": content["reason"],
                      "identity_passed": identity["passed"], "identity_reason": identity["reason"],
                      "bytes": len(data), "sha256": sha256_bytes(data)})
        rec["candidates_considered"].append(entry)

        if content["passed"] and identity["passed"]:
            rec.update({
                "source": cand["source"],
                "candidate_url": url,
                "representation_type": cand["representation_type"],
                "status": FULL_TEXT,
                "identity_validation": identity,
                "content_validation": content,
                "full_text_confidence": _confidence(identity, content, cand["representation_type"]),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "provenance": {
                    "discovery": "semantic_scholar_search",
                    "source": cand["source"],
                    "representation": cand["representation_type"],
                    "document_url": url,
                    "document_sha256": sha256_bytes(data),
                    "identifier": cand.get("identifier"),
                },
            })
            accepted_bytes = data
            if cache_dir is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                ext_name = "xml" if cand["representation_type"] == REPR_JATS else "pdf"
                (cache_dir / f"{pid}.{ext_name}").write_bytes(data)
            break
        time.sleep(0.3 if cand["source"] != "arxiv" else 3.0)

    if accepted_bytes is None:
        tried = [c for c in rec["candidates_considered"] if c.get("status") != "no_url" or c.get("reason") != "no_candidate_url"]
        if not rec["candidates_considered"]:
            rec["status"] = NO_ACCESSIBLE_FULL_TEXT if abstract_available else FAILED
            rec["failure_reason"] = "no_candidate_sources"
        elif all(c.get("status") == BLOCKED for c in rec["candidates_considered"]):
            rec["status"] = BLOCKED
            rec["failure_reason"] = "all_candidates_blocked"
        else:
            rec["status"] = NO_ACCESSIBLE_FULL_TEXT
            rec["failure_reason"] = "checked_{}_routes_no_validated_full_text".format(len(tried))
        rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        rec["representation_type"] = REPR_NONE
        rec["identity_validation"]["checked"] = True
        rec["content_validation"]["checked"] = True

    rec["abstract_available"] = abstract_available
    return rec, accepted_bytes
