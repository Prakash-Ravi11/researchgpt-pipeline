"""
Orchestrates the full pipeline as one background job, with status updates
between stages so the frontend can show real progress instead of a bare
spinner. Two entry points:

  run_search_pipeline  — new topic query, pulled live from Semantic Scholar
                          (Stages 1-4, unchanged from your existing scripts)
  run_upload_pipeline  — a user-supplied local PDF corpus (50+ files),
                          skipping Stage 1's API call entirely — builds the
                          same collected_papers.json shape directly from the
                          uploads so Stages 2-4 run completely unchanged

Both call your existing stage functions directly rather than reimplementing
anything — this file is glue, not new pipeline logic.
"""
import json
import uuid
from pathlib import Path

from src.collection.semantic_scholar import run_collection as run_search_collection
from src.embedding.build_index import build_collection, embed_chunks, load_chunks, load_model
from src.orchestration.jobs import finish_job, update_job
from src.processing.figure_extractor import run_figure_extraction
from src.processing.pdf_parser import run_processing
from src.summarization.summarize import run_summarization
from src.synthesis.corpus_synthesis import run_corpus_synthesis
from src.synthesis.gap_analysis import run_gap_analysis


def _run_stage3(config: dict) -> None:
    """Same steps as build_index.run_embedding, minus the sanity_query call —
    that call requires a domain_query, which an uploaded corpus may not have."""
    paths_cfg = config["paths"]
    emb_cfg = config["embedding"]

    chunks = load_chunks(paths_cfg["processed_dir"])
    model = load_model(emb_cfg["model"], emb_cfg["device"])
    embeddings = embed_chunks(model, chunks)

    chroma_dir = paths_cfg.get("chroma_dir", "data/chroma_db")
    collection_name = config.get("system", {}).get("collection_name", "researchgpt_papers")
    build_collection(chunks, embeddings, chroma_dir, collection_name)


def run_search_pipeline(job_id: str, config: dict) -> None:
    """Stages 1-4 for a new topic query."""
    try:
        pool = config["collection"]["candidate_pool_size"]
        update_job(job_id, stage="collecting", progress=f"pulling up to {pool} candidates")
        run_search_collection(config)

        update_job(job_id, stage="processing", progress="parsing and chunking PDFs")
        run_processing(config)

        update_job(job_id, stage="extracting_figures", progress="pulling figures/diagrams from full-text PDFs")
        run_figure_extraction(config)

        update_job(job_id, stage="embedding", progress="embedding chunks + building index")
        _run_stage3(config)

        update_job(job_id, stage="extracting", progress="running per-paper LLM extraction — the slow step")
        run_summarization(config)

        update_job(job_id, stage="synthesizing", progress="corpus-level synthesis across all papers")
        run_corpus_synthesis(config)

        update_job(job_id, stage="gap_analysis", progress="building category x dataset gap matrix")
        run_gap_analysis(config)

        finish_job(job_id)
    except Exception as e:
        finish_job(job_id, error=f"{type(e).__name__}: {e}")


def run_upload_pipeline(job_id: str, config: dict, saved_pdf_paths: list[Path]) -> None:
    """Stages 2-4 for a user-supplied local PDF corpus. Registers the uploaded
    files as if Stage 1 had produced them, then runs the same downstream
    pipeline unchanged."""
    paths_cfg = config["paths"]
    try:
        update_job(job_id, stage="registering", progress=f"0/{len(saved_pdf_paths)} files registered")
        records = []
        for i, pdf_path in enumerate(saved_pdf_paths):
            records.append({
                "paperId": uuid.uuid4().hex[:12],
                "title": pdf_path.stem.replace("_", " ").replace("-", " "),
                "year": None,
                "venue": "User-uploaded corpus",
                "authors": [],
                "relevance_score": None,  # no query to rank against for a raw upload
                "has_full_text": True,
                "pdf_path": str(pdf_path),
                "citationCount": None,
                "externalIds": {},
            })
            update_job(job_id, progress=f"{i + 1}/{len(saved_pdf_paths)} files registered")

        Path(paths_cfg["raw_metadata_dir"]).mkdir(parents=True, exist_ok=True)
        out_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
        out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

        update_job(job_id, stage="processing", progress="parsing and chunking PDFs")
        run_processing(config)

        update_job(job_id, stage="extracting_figures", progress="pulling figures/diagrams from full-text PDFs")
        run_figure_extraction(config)

        update_job(job_id, stage="embedding", progress="embedding chunks + building index")
        _run_stage3(config)

        update_job(job_id, stage="extracting", progress="running per-paper LLM extraction — the slow step")
        run_summarization(config)

        update_job(job_id, stage="synthesizing", progress="corpus-level synthesis across all papers")
        run_corpus_synthesis(config)

        update_job(job_id, stage="gap_analysis", progress="building category x dataset gap matrix")
        run_gap_analysis(config)

        finish_job(job_id)
    except Exception as e:
        finish_job(job_id, error=f"{type(e).__name__}: {e}")