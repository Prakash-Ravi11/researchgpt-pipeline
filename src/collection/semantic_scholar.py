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

            batch = resp.json().get("data", [])
            if not batch:
                break  # no more results available

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
            offset += page_size
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


def _candidate_pdf_urls(paper: dict, contact_email: str | None) -> list[str]:
    """Build an ordered list of URLs worth trying for this paper's PDF, best
    source first. Semantic Scholar's own openAccessPdf field is often empty
    even when a free copy genuinely exists elsewhere — arXiv and Unpaywall
    catch a meaningful chunk of those misses."""
    urls = []

    oa = paper.get("openAccessPdf")
    if oa and oa.get("url"):
        urls.append(oa["url"])

    external_ids = paper.get("externalIds") or {}

    arxiv_id = external_ids.get("ArXiv")
    if arxiv_id:
        urls.append(f"https://arxiv.org/pdf/{arxiv_id}.pdf")

    doi = external_ids.get("DOI")
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
                urls.append(pdf_url)
        except requests.RequestException:
            pass  # Unpaywall lookup failing shouldn't block trying the other sources

    return urls


def download_open_access_pdfs(papers: list[dict], pdf_dir: str, contact_email: str | None = None) -> None:
    """Download PDF where available; flag has_full_text either way.

    Tries multiple sources in order (Semantic Scholar's own link, then arXiv,
    then optionally Unpaywall) before giving up on a paper — a meaningful
    fraction of "abstract-only" papers turn out to have a free copy on arXiv
    even when Semantic Scholar's own openAccessPdf field is empty.
    """
    Path(pdf_dir).mkdir(parents=True, exist_ok=True)
    recovered_via_fallback = 0

    for paper in tqdm(papers, desc="Downloading PDFs"):
        paper_id = paper.get("paperId", "unknown")
        candidate_urls = _candidate_pdf_urls(paper, contact_email)

        if not candidate_urls:
            paper["has_full_text"] = False
            continue

        downloaded = False
        for i, url in enumerate(candidate_urls):
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                if not resp.content.startswith(b"%PDF"):
                    continue  # some "PDF" links actually return an HTML landing page — skip those
                out_path = Path(pdf_dir) / f"{paper_id}.pdf"
                out_path.write_bytes(resp.content)
                paper["has_full_text"] = True
                paper["pdf_path"] = str(out_path)
                if i > 0:
                    recovered_via_fallback += 1
                downloaded = True
                break
            except requests.RequestException:
                continue  # try the next candidate source

        if not downloaded:
            paper["has_full_text"] = False

    if recovered_via_fallback:
        print(f"  {recovered_via_fallback} paper(s) recovered via arXiv/Unpaywall fallback "
              f"(Semantic Scholar's own link was missing or dead)")


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

    download_open_access_pdfs(ranked, paths_cfg["pdf_dir"], contact_email=coll_cfg.get("contact_email"))
    full_text_count = sum(1 for p in ranked if p.get("has_full_text"))
    print(f"{full_text_count}/{len(ranked)} papers have full-text PDF; "
          f"{len(ranked) - full_text_count} are abstract-only")

    Path(paths_cfg["raw_metadata_dir"]).mkdir(parents=True, exist_ok=True)
    out_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    out_path.write_text(json.dumps(ranked, indent=2), encoding="utf-8")
    print(f"Saved metadata for {len(ranked)} papers to {out_path}")

    return ranked


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--limit", type=int, default=None,
                         help="Override candidate_pool_size for a quick test run")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_collection(cfg, limit=args.limit)