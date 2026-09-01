"""
Stage 6 — Gap detection + novelty comparison.

Two pieces, deliberately kept separate from free-form LLM guessing:

  1. build_gap_matrix — a deterministic category x dataset matrix built from
     the already-extracted, already-clustered corpus. Sparse/empty cells are
     candidate research gaps. No LLM involved — this is counting, not
     guessing, which is what makes it defensible in an actual literature
     review rather than just an LLM's opinion.

  2. compare_against_corpus — genuinely RAG: given a newly-extracted paper
     (e.g. an uploaded draft), retrieves its most similar existing papers by
     method-embedding similarity across the WHOLE corpus (not just one paper
     at a time, unlike the earlier one-vs-one compare feature), checks
     whether its (category, dataset) combination lands in an identified gap,
     and asks the LLM for a verdict GROUNDED in those retrieved papers by
     name — not an unaided judgment.

Run standalone (gap matrix only — novelty comparison needs a target paper,
so it's invoked from the API, not this CLI):
    python -m src.synthesis.gap_analysis --config configs/config.yaml
"""
import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from src.summarization.summarize import _stringify, call_ollama_json, embed_method_texts

NOVELTY_SYSTEM_PROMPT = """You are assessing the novelty of a paper against a corpus of related work. You are given \
the target paper's summary and method, plus the summaries and methods of its most similar existing papers in the \
corpus (retrieved by embedding similarity). Ground your assessment in the specific papers listed — do not speak in \
generalities. Respond with ONLY a JSON object:
- "overlap_summary": 2-3 sentences on how the target paper overlaps with the similar papers listed, naming them
- "distinguishing_factors": 2-3 sentences on what appears genuinely different about the target paper
- "novelty_verdict": one of "likely novel", "incremental", "substantially overlapping"

Respond with ONLY the JSON object, no other text."""

NOVELTY_NUM_CTX = 4096


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_gap_matrix(papers: list[dict]) -> dict:
    """category -> dataset -> count. Sparse/empty cells are candidate gaps.
    Deterministic — no LLM call in this function.

    Reads each paper's ``datasets`` list from paper_summaries.json. When the
    evidence gate is enabled (FINAL_REPORT.md §O) that list has already been
    filtered to RETURNED (grounded + attributed) datasets only, so a gap is
    never derived from an unsupported/abstained dataset mention."""
    categories = sorted({p.get("category", "Uncategorized") for p in papers})
    all_datasets = sorted({d for p in papers for d in p.get("datasets", []) if d})

    matrix = {c: {d: 0 for d in all_datasets} for c in categories}
    for p in papers:
        cat = p.get("category", "Uncategorized")
        for d in p.get("datasets", []):
            if d in matrix.get(cat, {}):
                matrix[cat][d] += 1

    candidate_gaps = [
        {"category": c, "dataset": d}
        for c in categories for d in all_datasets
        if matrix[c][d] == 0
    ]

    return {
        "categories": categories,
        "datasets": all_datasets,
        "matrix": matrix,
        "candidate_gaps": candidate_gaps,
    }


def run_gap_analysis(config: dict) -> dict:
    paths_cfg = config["paths"]
    summaries_path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    papers = json.loads(summaries_path.read_text(encoding="utf-8"))

    print(f"Building category x dataset gap matrix from {len(papers)} papers...")
    result = build_gap_matrix(papers)
    print(f"  {len(result['categories'])} categories x {len(result['datasets'])} datasets, "
          f"{len(result['candidate_gaps'])} empty (candidate-gap) cells")

    out_path = Path(paths_cfg["processed_dir"]) / "gap_matrix.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved gap matrix to {out_path}")
    return result


def compare_against_corpus(uploaded_extraction: dict, config: dict, top_k: int = 5) -> dict:
    """RAG step: embed the uploaded paper's method field, retrieve the top_k most
    similar papers from across the ENTIRE corpus (not just one comparison target),
    check gap-matrix fit using the nearest match's category as an approximation,
    then get an LLM verdict grounded in those retrieved papers."""
    paths_cfg = config["paths"]
    emb_cfg = config["embedding"]
    llm_cfg = config["llm"]

    summaries_path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    papers = json.loads(summaries_path.read_text(encoding="utf-8"))
    papers_by_id = {p["paper_id"]: p for p in papers}
    extractions = {p["paper_id"]: p for p in papers}

    corpus_embeddings = embed_method_texts(extractions, emb_cfg["model"], emb_cfg["device"])

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(emb_cfg["model"], device=emb_cfg["device"])
    model.max_seq_length = 256
    uploaded_text = _stringify(uploaded_extraction.get("method") or uploaded_extraction.get("summary", ""))
    uploaded_vec = model.encode([uploaded_text], normalize_embeddings=True, convert_to_numpy=True)[0]

    scored = [(pid, float(np.dot(uploaded_vec, vec))) for pid, vec in corpus_embeddings.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_matches = scored[:top_k]

    similar_papers = [
        {
            "paper_id": pid,
            "title": papers_by_id[pid]["title"],
            "category": papers_by_id[pid].get("category", ""),
            "similarity": round(sim, 4),
        }
        for pid, sim in top_matches
    ]

    gap_result = build_gap_matrix(papers)
    # Approximation: the uploaded paper hasn't been clustered (it's not in the
    # corpus), so we use its single nearest match's category as a stand-in for
    # "where would this paper likely be categorized" when checking gap-fit.
    approx_category = similar_papers[0]["category"] if similar_papers else None
    uploaded_datasets = uploaded_extraction.get("datasets", [])
    fits_gap = None
    if approx_category and approx_category in gap_result["categories"]:
        fits_gap = any(
            g["category"] == approx_category and g["dataset"] in uploaded_datasets
            for g in gap_result["candidate_gaps"]
        )

    lines = [f"TARGET PAPER — Summary: {uploaded_extraction.get('summary', '')} "
             f"Method: {uploaded_extraction.get('method', '')}",
             "MOST SIMILAR EXISTING PAPERS (retrieved by embedding similarity):"]
    for pid, sim in top_matches:
        p = papers_by_id[pid]
        lines.append(f"- {p['title']} (similarity {sim:.2f}): {p.get('method', '')}")
    user_content = "\n".join(lines)

    verdict = call_ollama_json(
        base_url=llm_cfg["base_url"], model=llm_cfg["model"],
        system_prompt=NOVELTY_SYSTEM_PROMPT, user_content=user_content,
        temperature=llm_cfg.get("temperature", 0.2),
        timeout=llm_cfg.get("timeout_seconds", 300),
        num_ctx=NOVELTY_NUM_CTX,
    )
    if verdict is None:
        verdict = {"overlap_summary": "", "distinguishing_factors": "", "novelty_verdict": "unknown"}

    return {
        "similar_papers": similar_papers,
        "approx_category": approx_category,
        "fits_identified_gap": fits_gap,
        **verdict,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_gap_analysis(cfg)