"""
Stage 1 — Collection.

Pulls candidate papers from the Semantic Scholar API, re-ranks them by
semantic relevance to the domain query using bge-m3, and downloads
open-access PDFs where available (falls back to abstract-only otherwise).

Run standalone for testing:
    python -m src.collection.semantic_scholar --config configs/config.yaml --limit 20
"""
import argparse
import json
import time
from pathlib import Path

import requests
from tqdm import tqdm

from src.config import load_config

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,year,venue,authors,fieldsOfStudy,citationCount,externalIds,openAccessPdf,tldr"


def _get_with_backoff(params: dict, headers: dict, max_retries: int = 6) -> requests.Response:
    """GET with exponential backoff on 429. Respects Retry-After when present."""
    for attempt in range(max_retries):
        resp = requests.get(SEARCH_URL, params=params, headers=headers, timeout=30)

        if resp.status_code != 429:
            # Semantic Scholar returns 400 when `offset` is past the end of the
            # result set (which happens whenever a query has fewer total hits
            # than the requested pool). That is not a real error while
            # paginating — hand the response back so the caller sees no data and
            # stops. A 400 on the very first page IS a real problem, so still raise.
            if resp.status_code == 400 and params.get("offset", 0) > 0:
                return resp
            resp.raise_for_status()
            return resp

        retry_after = resp.headers.get("Retry-After")
        wait = float(retry_after) if retry_after else (2 ** attempt)
        wait = min(wait, 60)  # don't wait more than a minute on any single attempt
        print(f"Rate limited (attempt {attempt + 1}/{max_retries}) — waiting {wait:.0f}s")
        time.sleep(wait)

    if "x-api-key" in headers:
        raise RuntimeError(
            "Still rate-limited after all retries, even with an API key attached. "
            "This usually means the request is genuinely being sent WITHOUT the key — "
            "double check configs/config.yaml has collection.api_key set correctly, "
            "AND that you fully restarted the server (Ctrl+C, not just --reload triggering) "
            "after adding it. main.py reads config.yaml once at startup, not per-request."
        )
    raise RuntimeError(
        "Still rate-limited after all retries. No API key is attached to this request — "
        "get a free one at https://www.semanticscholar.org/product/api#api-key-form and set it "
        "in config.yaml under collection.api_key, then fully restart the server (not just "
        "--reload) since config.yaml is only read once at startup."
    )


def fetch_candidates(query: str, year_range, pool_size: int, api_key: str | None = None) -> list[dict]:
    """Pull up to pool_size candidate papers from Semantic Scholar, 100 per page."""
    papers = []
    seen_ids = set()
    offset = 0
    page_size = 100
    year_filter = f"{year_range[0]}-{year_range[1]}"
    headers = {"x-api-key": api_key} if api_key else {}

    with tqdm(total=pool_size, desc="Fetching candidates") as pbar:
        while len(papers) < pool_size:
            params = {
                "query": query,
                "fields": FIELDS,
                "year": year_filter,
                "limit": min(page_size, pool_size - len(papers)),
                "offset": offset,
            }
            resp = _get_with_backoff(params, headers)

            payload = resp.json() if resp.status_code == 200 else {}
            batch = payload.get("data", [])
            if not batch:
                break  # no more results available (empty page or 400 past the end)

            # Semantic Scholar's pagination isn't perfectly stable across requests —
            # the same paper can occasionally appear on two different pages. Left
            # unfiltered, a duplicate paperId produces duplicate chunk_ids downstream
            # (Stage 2 builds chunk_id as f"{paperId}_{i}"), which ChromaDB's add()
            # rejects outright in Stage 3. Dedupe at the source instead.
            new_papers = [p for p in batch if p.get("paperId") not in seen_ids]
            duplicates = len(batch) - len(new_papers)
            if duplicates:
                print(f"  Skipped {duplicates} duplicate paper(s) from pagination overlap")

            for p in new_papers:
                seen_ids.add(p["paperId"])
            papers.extend(new_papers)
            pbar.update(len(new_papers))
            offset += params["limit"]  # advance by what we actually asked for, not a fixed 100

            # Stop as soon as Semantic Scholar signals the result set is exhausted:
            #   - it returned fewer rows than we asked for (short final page), OR
            #   - it gave no "next" cursor, OR
            #   - our offset has walked past the reported total.
            # Without this the loop keeps requesting past the end and S2 answers 400.
            total = payload.get("total")
            if (len(batch) < params["limit"] or "next" not in payload
                    or (isinstance(total, int) and offset >= total)):
                break

            # Semantic Scholar's authenticated tier is 1 req/sec CUMULATIVE across all
            # endpoints — pad slightly above 1.0s so timing overhead never pushes us over.
            time.sleep(3 if not api_key else 1.2)

    return papers[:pool_size]


def rerank_by_relevance(query: str, papers: list[dict], model_name: str,
                         device: str, top_n: int) -> list[dict]:
    """Embed the query and each abstract with bge-m3, rank by cosine similarity."""
    from sentence_transformers import SentenceTransformer
    import numpy as np

    # Drop papers with no abstract up front — nothing to rank them on.
    scoreable = [p for p in papers if p.get("abstract")]
    print(f"{len(papers) - len(scoreable)} papers dropped (no abstract available)")

    model = SentenceTransformer(model_name, device=device)
    query_vec = model.encode([query], normalize_embeddings=True)[0]
    abstracts = [p["abstract"] for p in scoreable]
    abstract_vecs = model.encode(abstracts, normalize_embeddings=True, show_progress_bar=True)

    scores = abstract_vecs @ query_vec  # cosine similarity, vectors are normalized
    for paper, score in zip(scoreable, scores):
        paper["relevance_score"] = float(score)

    ranked = sorted(scoreable, key=lambda p: p["relevance_score"], reverse=True)
    return ranked[:top_n]


def _candidate_pdf_urls(paper: dict, contact_email: str | None,
                        use_extra_sources: bool = False,
                        latex_ingestion: bool = False) -> list[tuple[str, str, str]]:
    """Ordered (source, url, representation_type) candidates for this paper's
    full text, best/most-structured source first.

    Semantic Scholar's own openAccessPdf field is often empty even when a free
    copy exists elsewhere — arXiv and Unpaywall catch many misses. With
    ``use_extra_sources`` (FINAL_REPORT.md §O), Europe PMC JATS/XML (when a
    PMCID exists) and OpenAlex are also consulted; both were validated to add
    +3 papers on the reference corpus. Crossref is included but contributed 0
    unique there — kept only because it is a cheap DOI lookup.
    """
    external_ids = paper.get("externalIds") or {}
    pmcid = external_ids.get("PubMedCentral")
    arxiv_id = external_ids.get("ArXiv")
    doi = external_ids.get("DOI")
    oa = paper.get("openAccessPdf")
    cands: list[tuple[str, str, str]] = []

    if not use_extra_sources:
        # LEGACY ordering, byte-for-byte: Semantic Scholar's own link, then arXiv,
        # then optionally Unpaywall. Nothing else is consulted.
        if oa and oa.get("url"):
            cands.append(("semantic_scholar", oa["url"], "pdf"))
        if arxiv_id:
            cands.append(("arxiv", f"https://arxiv.org/pdf/{arxiv_id}.pdf", "pdf"))
    else:
        # §O ordering: most-structured / most-reliable first.
        # Structured-representation rank (schema.STRUCTURED_REPR_RANK):
        #   JATS/XML  >  arXiv LaTeX e-print  >  any PDF
        # PyMuPDF keeps digits + page provenance but collapses table structure
        # (~9% of table-resident values stay context-bindable); JATS and LaTeX
        # both keep real tabular/caption/multicolumn.
        if pmcid:
            from src.evidence.acquire import europepmc_jats_url
            cands.append(("europepmc", europepmc_jats_url(pmcid), "jats_xml"))
        if arxiv_id:
            # LaTeX e-print ranked ABOVE arXiv PDF, BELOW JATS. CONTENT ONLY —
            # identity for this candidate comes from the paired arXiv PDF, never
            # the .tex (see download_open_access_pdfs / acquire.identity_validate).
            # DISABLED by default (Phase 4b: parity reached but downstream
            # extraction regressed — see LATEX_ACQUISITION_REPORT.md).
            if latex_ingestion:
                from src.evidence.latex_source import eprint_url
                cands.append(("arxiv_eprint", eprint_url(arxiv_id), "latex"))
            cands.append(("arxiv", f"https://arxiv.org/pdf/{arxiv_id}.pdf", "pdf"))
        if oa and oa.get("url"):
            cands.append(("semantic_scholar", oa["url"], "pdf"))
        if doi:
            from src.evidence.acquire import resolve_openalex_pdf, resolve_crossref_pdf
            oa_url, _ = resolve_openalex_pdf(doi)
            if oa_url:
                cands.append(("openalex", oa_url, "pdf"))
            cr_url, _ = resolve_crossref_pdf(doi)
            if cr_url:
                cands.append(("crossref", cr_url, "pdf"))

    if doi and contact_email:
        # Unpaywall is free, no API key, but requires a real contact email per
        # their terms of use — only attempted if one is configured.
        try:
            resp = requests.get(f"https://api.unpaywall.org/v2/{doi}",
                                 params={"email": contact_email}, timeout=15)
            resp.raise_for_status()
            location = resp.json().get("best_oa_location") or {}
            pdf_url = location.get("url_for_pdf") or location.get("url")
            if pdf_url:
                cands.append(("unpaywall", pdf_url, "pdf"))
        except requests.RequestException:
            pass  # Unpaywall lookup failing shouldn't block trying the other sources

    return cands


def download_open_access_pdfs(papers: list[dict], pdf_dir: str, contact_email: str | None = None,
                              validate: bool = False, use_extra_sources: bool = False,
                              latex_ingestion: bool = False) -> None:
    """Download full text where available; flag has_full_text either way.

    Tries multiple sources in order (structured JATS first when enabled, then
    arXiv, Semantic Scholar's own link, OpenAlex/Crossref, Unpaywall) before
    giving up — many "abstract-only" papers have a free copy elsewhere.

    Legacy path (validate=False): a candidate is accepted on the ``%PDF`` magic
    byte alone, exactly as before.

    Validated path (validate=True, FINAL_REPORT.md §O): every candidate is
    streamed under a 40 MB cap and must pass BOTH deterministic content
    validation (real article body, not a landing/error/abstract page) AND
    identity validation (title / DOI / author match) before ``has_full_text``
    is set. Per-paper provenance is recorded in ``pdf_source`` /
    ``representation_type`` / ``acquisition_status`` / ``identity_validation`` /
    ``content_validation``.
    """
    Path(pdf_dir).mkdir(parents=True, exist_ok=True)
    recovered_via_fallback = 0

    if validate:
        from src.evidence.acquire import (fetch, content_validate, identity_validate,
                                          full_text_confidence, sha256_bytes)

    for paper in tqdm(papers, desc="Downloading full text"):
        paper_id = paper.get("paperId", "unknown")
        candidates = _candidate_pdf_urls(paper, contact_email, use_extra_sources=use_extra_sources,
                                         latex_ingestion=latex_ingestion)
        paper["has_full_text"] = False
        paper["pdf_source"] = None
        paper["representation_type"] = None
        if validate:
            paper["acquisition_status"] = "NO_ACCESSIBLE_FULL_TEXT" if candidates else (
                "NO_ACCESSIBLE_FULL_TEXT" if paper.get("abstract") else "METADATA_ONLY")
            paper["acquisition_candidates"] = []

        for i, (source, url, rep_type) in enumerate(candidates):
            if not validate:
                try:
                    resp = requests.get(url, timeout=30)
                    resp.raise_for_status()
                    if not resp.content.startswith(b"%PDF"):
                        continue
                    out_path = Path(pdf_dir) / f"{paper_id}.pdf"
                    out_path.write_bytes(resp.content)
                    paper["has_full_text"] = True
                    paper["pdf_path"] = str(out_path)
                    paper["pdf_source"] = source
                    paper["representation_type"] = "pdf"
                    if i > 0:
                        recovered_via_fallback += 1
                    break
                except requests.RequestException:
                    continue

            # validated path — LaTeX e-print: CONTENT / IDENTITY SPLIT.
            # The .tex supplies content, tables and section structure ONLY.
            # Identity comes from the paired arXiv PDF (never LaTeX metadata —
            # S2ORC found author-defined LaTeX metadata worse than PDF-derived and
            # excluded it from paper matching; our wrong-paper-accepted guarantee
            # depends on this check). We keep BOTH files: the .tex for structured
            # tables, the .pdf for identity and for per-table PDF fallback when a
            # tabular environment will not parse (see represent.blocks_from_latex).
            if rep_type == "latex":
                from src.evidence.latex_source import fetch_eprint_latex
                arxiv_id = (paper.get("externalIds") or {}).get("ArXiv")
                entry = {"source": source, "url": url, "representation_type": rep_type}
                lx = (fetch_eprint_latex(arxiv_id, fetch) if arxiv_id
                      else {"ok": False, "reason": "no_arxiv_id", "latex": ""})
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None
                pr = fetch(pdf_url) if pdf_url else {"ok": False}
                pdf_bytes = pr.get("body", b"") if pr.get("ok") else b""
                latex_bytes = lx.get("latex", "").encode("utf-8")
                content = (content_validate("latex", latex_bytes) if lx.get("ok")
                           else {"checked": True, "passed": False,
                                 "reason": lx.get("reason", "eprint_failed"), "metrics": {}})
                # identity strictly from the paired PDF — identity_validate refuses
                # rep_type="latex" outright.
                identity = (identity_validate(paper, "pdf", pdf_bytes) if pdf_bytes
                            else {"checked": True, "passed": False, "signals": {},
                                  "reason": "no_paired_arxiv_pdf"})
                identity.setdefault("signals", {})["identity_source"] = "arxiv_pdf"
                pdf_content = (content_validate("pdf", pdf_bytes) if pdf_bytes
                               else {"checked": True, "passed": False,
                                     "reason": "no_paired_arxiv_pdf", "metrics": {}})
                entry.update({"content_passed": content["passed"], "content_reason": content["reason"],
                              "identity_passed": identity["passed"], "identity_reason": identity["reason"],
                              "n_tex_files": lx.get("n_tex_files"), "latex_main": lx.get("main"),
                              "paired_pdf_ok": pdf_content["passed"]})
                paper["acquisition_candidates"].append(entry)
                if not (content["passed"] and identity["passed"] and pdf_content["passed"]):
                    continue
                tex_path = Path(pdf_dir) / f"{paper_id}.tex"
                pdf_path = Path(pdf_dir) / f"{paper_id}.pdf"
                tex_path.write_bytes(latex_bytes)
                pdf_path.write_bytes(pdf_bytes)
                paper["has_full_text"] = True
                paper["pdf_path"] = str(tex_path)                  # build_document parses this
                paper["latex_pdf_fallback_path"] = str(pdf_path)   # per-table PDF fallback
                paper["pdf_source"] = source
                paper["representation_type"] = "latex"
                paper["acquisition_status"] = "FULL_TEXT"
                paper["identity_validation"] = identity            # PDF-derived, marked
                paper["content_validation"] = content              # LaTeX-derived
                paper["full_text_confidence"] = full_text_confidence(identity, content, "pdf")
                paper["document_sha256"] = sha256_bytes(latex_bytes)
                paper["latex_pdf_sha256"] = sha256_bytes(pdf_bytes)
                if i > 0:
                    recovered_via_fallback += 1
                break

            # validated path (non-latex)
            r = fetch(url)
            entry = {"source": source, "url": url, "representation_type": rep_type,
                     "http_status": r.get("http_status"), "bytes": r.get("bytes")}
            if not r.get("ok") or r["http_status"] >= 400:
                entry["result"] = f"fetch_failed:{r.get('error') or r.get('http_status')}"
                paper["acquisition_candidates"].append(entry)
                continue
            data = r["body"]
            content = content_validate(rep_type, data)
            identity = identity_validate(paper, rep_type, data)
            entry.update({"content_passed": content["passed"], "content_reason": content["reason"],
                          "identity_passed": identity["passed"], "identity_reason": identity["reason"]})
            paper["acquisition_candidates"].append(entry)
            if not (content["passed"] and identity["passed"]):
                continue
            ext = "xml" if rep_type == "jats_xml" else "pdf"
            out_path = Path(pdf_dir) / f"{paper_id}.{ext}"
            out_path.write_bytes(data)
            paper["has_full_text"] = True
            paper["pdf_path"] = str(out_path)
            paper["pdf_source"] = source
            paper["representation_type"] = rep_type
            paper["acquisition_status"] = "FULL_TEXT"
            paper["identity_validation"] = identity
            paper["content_validation"] = content
            paper["full_text_confidence"] = full_text_confidence(identity, content, rep_type)
            paper["document_sha256"] = sha256_bytes(data)
            if i > 0:
                recovered_via_fallback += 1
            break

    if recovered_via_fallback:
        print(f"  {recovered_via_fallback} paper(s) recovered via a fallback source "
              f"(Semantic Scholar's own link was missing, dead, or failed validation)")


def run_collection(config: dict, limit: int | None = None) -> list[dict]:
    coll_cfg = config["collection"]
    emb_cfg = config["embedding"]
    paths_cfg = config["paths"]

    pool_size = limit or coll_cfg["candidate_pool_size"]
    target_size = min(coll_cfg["target_corpus_size"], pool_size)

    print(f"Querying Semantic Scholar: '{coll_cfg['domain_query']}' (pool={pool_size})")
    candidates = fetch_candidates(
        query=coll_cfg["domain_query"],
        year_range=coll_cfg["year_range"],
        pool_size=pool_size,
        api_key=coll_cfg.get("api_key"),
    )
    print(f"Retrieved {len(candidates)} raw candidates")

    ranked = rerank_by_relevance(
        query=coll_cfg["domain_query"],
        papers=candidates,
        model_name=emb_cfg["model"],
        device=emb_cfg["device"],
        top_n=target_size,
    )
    print(f"Kept top {len(ranked)} papers by relevance")

    ev_cfg = config.get("evidence_grounding", {}) or {}
    grounded = bool(ev_cfg.get("enabled"))
    download_open_access_pdfs(
        ranked, paths_cfg["pdf_dir"], contact_email=coll_cfg.get("contact_email"),
        validate=grounded, use_extra_sources=grounded,
        # Phase 4b: arXiv LaTeX e-print ingestion is DISABLED by default. It reached
        # numeric parity (M1) but regressed downstream extraction — the structured
        # table text drives the model past the 768 num_predict cap (retained-subset
        # mean fields 9.91 -> 5.82 at reservation 768; ~9.09 only at 4096). See
        # experiments/document_evidence_pipeline/LATEX_ACQUISITION_REPORT.md.
        latex_ingestion=bool(ev_cfg.get("latex_ingestion_enabled", False)),
    )
    full_text_count = sum(1 for p in ranked if p.get("has_full_text"))
    if grounded:
        by_src = {}
        for p in ranked:
            if p.get("has_full_text"):
                by_src[p.get("pdf_source")] = by_src.get(p.get("pdf_source"), 0) + 1
        print(f"{full_text_count}/{len(ranked)} papers have VALIDATED full text "
              f"({len(ranked) - full_text_count} NO_ACCESSIBLE_FULL_TEXT); by source: {by_src}")
    else:
        print(f"{full_text_count}/{len(ranked)} papers have full-text PDF; "
              f"{len(ranked) - full_text_count} are abstract-only")

    Path(paths_cfg["raw_metadata_dir"]).mkdir(parents=True, exist_ok=True)
    out_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    out_path.write_text(json.dumps(ranked, indent=2), encoding="utf-8")
    print(f"Saved metadata for {len(ranked)} papers to {out_path}")

    return ranked


def re_acquire_corpus(config: dict) -> list[dict]:
    """Stage 1 — re-run full-text acquisition on an EXISTING corpus (no new
    Semantic Scholar search) through the validated canonical five-source resolver
    (Semantic Scholar + arXiv + OpenAlex + Europe PMC + Crossref).

    This is the missing wiring: `run_collection` only reaches the §O resolver via
    `evidence_grounding.enabled`, and only for a fresh search. This applies the
    same validated path — four acquisition states, identity + content validation,
    provenance, structured-preferred ordering (JATS > validated PDF > abstract),
    NO_ACCESSIBLE_FULL_TEXT abstention — to a corpus that already exists, so a
    corpus collected before §O can be upgraded without re-searching.

    Reads/writes `<raw_metadata_dir>/collected_papers.json`. arXiv LaTeX e-print
    ingestion stays whatever `evidence_grounding.latex_ingestion_enabled` says
    (default false — Phase 4b decision stands).
    """
    paths_cfg = config["paths"]
    coll_cfg = config.get("collection", {}) or {}
    ev_cfg = config.get("evidence_grounding", {}) or {}
    meta_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    papers = json.loads(meta_path.read_text(encoding="utf-8"))
    before_ft = sum(1 for p in papers if p.get("has_full_text"))
    print(f"Re-acquiring {len(papers)} papers (was {before_ft}/{len(papers)} full text) "
          f"through the canonical five-source resolver")

    download_open_access_pdfs(
        papers, paths_cfg["pdf_dir"], contact_email=coll_cfg.get("contact_email"),
        validate=True, use_extra_sources=True,
        latex_ingestion=bool(ev_cfg.get("latex_ingestion_enabled", False)),
    )

    after_ft = sum(1 for p in papers if p.get("has_full_text"))
    by_src = {}
    by_rep = {}
    for p in papers:
        if p.get("has_full_text"):
            by_src[p.get("pdf_source")] = by_src.get(p.get("pdf_source"), 0) + 1
            by_rep[p.get("representation_type")] = by_rep.get(p.get("representation_type"), 0) + 1
    print(f"  {before_ft}/{len(papers)} -> {after_ft}/{len(papers)} validated full text  "
          f"| by source: {by_src} | by representation: {by_rep}")
    meta_path.write_text(json.dumps(papers, indent=2), encoding="utf-8")
    return papers


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--limit", type=int, default=None,
                         help="Override candidate_pool_size for a quick test run")
    parser.add_argument("--reacquire", action="store_true",
                         help="Re-run the canonical five-source resolver against the existing "
                              "collected_papers.json (no new search)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.reacquire:
        re_acquire_corpus(cfg)
    else:
        run_collection(cfg, limit=args.limit)