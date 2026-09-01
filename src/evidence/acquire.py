"""Stage 1/2 boundary — deterministic identity + content validation and
multi-source full-text resolution.

Promoted, unchanged in behaviour, from the validated experiment
(experiments/document_evidence_pipeline/pipeline/acquire.py + resolve_corpus.py).
No credentials. Only the five already-approved sources are consulted:
Semantic Scholar (caller-supplied), arXiv, OpenAlex, Europe PMC, Crossref.
"""
from __future__ import annotations

import hashlib
import io
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests

from .schema import REPR_JATS, REPR_PDF, title_similarity

# Courtesy routing only (OpenAlex / Crossref "polite pool") — not authentication,
# and deliberately not a real person's address.
POLITE_MAILTO = "researchgpt-acquisition@example.org"
UA = f"researchgpt/1.0 (mailto:{POLITE_MAILTO})"

# a legitimate image-heavy paper PDF can run 20-30 MB; an unbounded read is a
# DoS/OOM risk, a small cap silently truncates the title page and breaks identity
FETCH_CAP_BYTES = 40_000_000

MIN_PDF_BYTES = 20_000
MIN_PDF_CHARS = 2_000
MIN_PDF_PAGES = 2
MIN_BODY_WORDS = 1_500
MIN_JATS_SECS = 2
MIN_XML_CHARS = 4_000


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fetch(url: str, *, accept: str | None = None, cap_bytes: int = FETCH_CAP_BYTES,
          timeout: int = 30) -> dict[str, Any]:
    """GET with a hard byte cap. Never raises; returns a status dict + body."""
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
        return {"ok": True, "http_status": resp.status_code,
                "content_type": (resp.headers.get("Content-Type") or "").split(";")[0].strip(),
                "final_url": resp.url, "bytes": len(body),
                "latency_ms": round((time.perf_counter() - started) * 1000, 1), "body": body}
    except requests.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1), "body": b""}


def validate_pdf_bytes(data: bytes) -> dict[str, Any]:
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
    return ("<article" in head and ("jats" in head or "<front" in head or "<body" in head)) \
        or "<!doctype article" in head


def _jats_parts(data: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return {"ok": False, "reason": f"xml_parse_error:{exc}"}
    if root.tag.split("}")[-1] != "article":
        return {"ok": False, "reason": f"root_not_article:{root.tag.split('}')[-1]}"}
    title_el = root.find(".//{*}article-title")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""
    body = root.find(".//{*}body")
    secs = body.findall(".//{*}sec") if body is not None else []
    body_text = " ".join("".join(p.itertext()) for p in (body.iter() if body is not None else []))
    return {"ok": True, "title": title, "n_secs": len(secs),
            "body_words": len(body_text.split()), "root": root}


def content_validate(rep_type: str, data: bytes) -> dict[str, Any]:
    """Is this a substantive article body — not a landing page, error page,
    abstract stub, or corrupt file?"""
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
    v = validate_pdf_bytes(data)
    words = (v.get("chars") or 0) / 6
    ok = v["ok"] and (words >= MIN_BODY_WORDS or (v.get("pages") or 0) >= 3)
    return {"checked": True, "passed": bool(ok),
            "reason": "ok" if ok else (v["reason"] if not v["ok"] else f"abstract_sized_{int(words)}w"),
            "metrics": {"pdf_chars": v.get("chars"), "pdf_pages": v.get("pages"),
                        "nonempty_pages": v.get("nonempty_pages")}}


def _pdf_title_text(data: bytes) -> str:
    try:
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        txt = "\n".join(p.get_text() for p in list(doc)[:2])
        doc.close()
        return txt
    except Exception:
        return ""


def identity_validate(paper: dict[str, Any], rep_type: str, data: bytes) -> dict[str, Any]:
    """Does this document actually belong to `paper`? Never accept a wrong paper."""
    meta_title = paper.get("title") or ""
    ext = {k: str(v) for k, v in (paper.get("externalIds") or {}).items() if v is not None}
    doi = (ext.get("DOI") or "").lower()
    surnames = [n.get("name", "").split()[-1].lower()
                for n in (paper.get("authors") or []) if isinstance(n, dict) and n.get("name")]

    if rep_type == REPR_JATS:
        j = _jats_parts(data)
        probe = j.get("title", "") if j.get("ok") else ""
        blob = (probe + " " + " ".join(
            "".join(el.itertext()) for el in j["root"].iter()
            if el.tag.split("}")[-1] == "surname")).lower() if j.get("ok") else ""
    else:
        probe = _pdf_title_text(data)
        blob = probe.lower()

    t_sim = title_similarity(meta_title, probe)
    doi_hit = bool(doi) and doi in blob
    surn_hits = sum(1 for s in surnames if s and len(s) > 2 and s in blob)
    surn_frac = surn_hits / len(surnames) if surnames else 0.0

    passed = (t_sim >= 0.60 or (doi_hit and t_sim >= 0.30) or (surn_frac >= 0.5 and t_sim >= 0.40))
    return {"checked": True, "passed": bool(passed),
            "signals": {"title_similarity": round(t_sim, 3), "doi_in_doc": doi_hit,
                        "author_surname_frac": round(surn_frac, 3)},
            "reason": "ok" if passed else
            f"title_sim={t_sim:.2f} doi_hit={doi_hit} surname_frac={surn_frac:.2f}"}


def full_text_confidence(identity: dict, content: dict, rep_type: str) -> float:
    base = 0.5 * identity["signals"].get("title_similarity", 0.0)
    if identity["signals"].get("doi_in_doc"):
        base += 0.2
    base += 0.2 * identity["signals"].get("author_surname_frac", 0.0)
    if content["passed"]:
        base += 0.25
    if rep_type == REPR_JATS:
        base += 0.05
    return round(min(1.0, base), 3)


# --- multi-source URL resolution (metadata lookups only) --------------------
def resolve_openalex_pdf(doi: str) -> tuple[str | None, dict[str, Any]]:
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
    return (best.get("pdf_url") or oa.get("oa_url")), {"is_oa": bool(oa.get("is_oa")),
                                                       "oa_status": oa.get("oa_status")}


def resolve_crossref_pdf(doi: str) -> tuple[str | None, dict[str, Any]]:
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


def europepmc_jats_url(pmcid: str) -> str:
    pmc = "PMC" + str(pmcid).lstrip("PMC")
    return f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML"
