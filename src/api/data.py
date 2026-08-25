"""
Data layer for the ResearchGPT API.

Merges two pipeline outputs by paper_id into one record per paper:
  - collected_papers.json (Stage 1): authors, relevance_score, has_full_text, DOI/arXiv links
  - paper_summaries.json (Stage 4): summary, method, datasets, metrics, key_findings, category

Loaded once at startup and cached in memory — this is a read-only local
prototype serving ~50 records, not a database.
"""
import json
from pathlib import Path


def _external_link(external_ids: dict) -> str | None:
    """Prefer a DOI link, fall back to arXiv, else None."""
    if not external_ids:
        return None
    if external_ids.get("DOI"):
        return f"https://doi.org/{external_ids['DOI']}"
    if external_ids.get("ArXiv"):
        return f"https://arxiv.org/abs/{external_ids['ArXiv']}"
    return None


def load_corpus(paths_cfg: dict) -> dict:
    """Returns {"papers": {paper_id: record}, "clusters": {cluster_id: info}}."""
    raw_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    summaries_path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    clusters_path = Path(paths_cfg["processed_dir"]) / "clusters.json"

    raw_papers = {p["paperId"]: p for p in json.loads(raw_path.read_text(encoding="utf-8"))}
    summaries = json.loads(summaries_path.read_text(encoding="utf-8"))
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))

    merged = {}
    for s in summaries:
        pid = s["paper_id"]
        raw = raw_papers.get(pid, {})
        merged[pid] = {
            "paper_id": pid,
            "title": s.get("title", raw.get("title", "")),
            "year": s.get("year", raw.get("year")),
            "venue": s.get("venue", raw.get("venue", "")),
            "authors": [a.get("name", "") for a in raw.get("authors", [])],
            "relevance_score": raw.get("relevance_score"),
            "has_full_text": raw.get("has_full_text", False),
            "citation_count": raw.get("citationCount"),
            "external_link": _external_link(raw.get("externalIds", {})),
            "cluster_id": s.get("cluster_id"),
            "category": s.get("category", "Uncategorized"),
            "summary": s.get("summary", ""),
            "problem_addressed": s.get("problem_addressed", ""),
            "method": s.get("method", ""),
            "results": s.get("results", ""),
            "inferences": s.get("inferences", ""),
            "novelty_claim": s.get("novelty_claim", ""),
            "limitations": s.get("limitations", ""),
            "datasets": s.get("datasets", []),
            "metrics": s.get("metrics", []),
            "key_findings": s.get("key_findings", ""),
            "extraction_failed": bool(s.get("_extraction_failed", False)),
        }

    # Normalize cluster keys to strings — JSON object keys always deserialize as
    # strings even though cluster_id is an int elsewhere in the pipeline.
    cluster_info = {str(cid): info for cid, info in clusters.items()}

    return {"papers": merged, "clusters": cluster_info}