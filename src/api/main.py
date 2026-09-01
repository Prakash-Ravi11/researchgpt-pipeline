"""
ResearchGPT API — serves the merged paper corpus to the catalog frontend.

Run:
    uvicorn src.api.main:app --reload --port 8000

Then open http://localhost:8000 in a browser.
"""
import copy
import shutil
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.api.data import load_corpus
from src.config import load_config
from src.orchestration.jobs import get_job
from src.orchestration.pipeline import run_search_pipeline, run_upload_pipeline
from src.processing.pdf_parser import clean_text, extract_pdf_text
from src.summarization.summarize import EXTRACTION_SYSTEM_PROMPT, call_ollama_json
from src.synthesis.gap_analysis import compare_against_corpus

app = FastAPI(title="ResearchGPT Catalog")

CONFIG_PATH = "configs/config.yaml"
with open(CONFIG_PATH, encoding="utf-8") as f:
    _config = load_config(CONFIG_PATH)

_corpus = load_corpus(_config["paths"])
_raw_papers_by_id = {}  # paper_id -> raw Stage 1 record (has pdf_path) — populated by _reload_corpus


def _reload_raw_papers() -> None:
    global _raw_papers_by_id
    raw_path = Path(_config["paths"]["raw_metadata_dir"]) / "collected_papers.json"
    if raw_path.exists():
        import json
        records = json.loads(raw_path.read_text(encoding="utf-8"))
        _raw_papers_by_id = {r["paperId"]: r for r in records}
    else:
        _raw_papers_by_id = {}


_reload_raw_papers()


def _reload_corpus() -> None:
    """Refreshes the in-memory corpus from disk. Call after a search/upload job
    finishes, or manually via /api/reload-corpus."""
    global _corpus
    _corpus = load_corpus(_config["paths"])
    _reload_raw_papers()


class SearchRequest(BaseModel):
    """All fields a PhD-level user might reasonably want to control per search —
    not just the query string. Anything left at its default behaves exactly like
    your current config.yaml settings."""
    query: str
    candidate_pool_size: int = 100
    target_corpus_size: int = 50
    year_start: int | None = None
    year_end: int | None = None
    relevance_threshold: float | None = None
    num_clusters: int | str | None = None  # "auto" or a fixed int (3-8 recommended)


def _build_search_config(payload: SearchRequest) -> dict:
    """Deep-copies the loaded config and overrides only what the request specified —
    everything else (LLM settings, embedding model, hardware device) stays as-is."""
    cfg = copy.deepcopy(_config)
    cfg["collection"]["domain_query"] = payload.query
    cfg["collection"]["candidate_pool_size"] = payload.candidate_pool_size
    cfg["collection"]["target_corpus_size"] = payload.target_corpus_size
    if payload.year_start is not None and payload.year_end is not None:
        cfg["collection"]["year_range"] = [payload.year_start, payload.year_end]
    if payload.relevance_threshold is not None:
        cfg["collection"]["relevance_threshold"] = payload.relevance_threshold
    if payload.num_clusters is not None:
        cfg.setdefault("categorization", {})["num_clusters"] = payload.num_clusters
    return cfg


@app.get("/api/papers")
def list_papers():
    """Catalog view — one summary row per paper, sorted by relevance score."""
    papers = list(_corpus["papers"].values())
    papers.sort(key=lambda p: p.get("relevance_score") or 0, reverse=True)
    return [
        {
            "paper_id": p["paper_id"],
            "title": p["title"],
            "year": p["year"],
            "venue": p["venue"],
            "authors": p["authors"],
            "relevance_score": p["relevance_score"],
            "has_full_text": p["has_full_text"],
            "cluster_id": p["cluster_id"],
            "category": p["category"],
            "summary": p["summary"],
        }
        for p in papers
    ]


@app.get("/api/papers/full")
def list_papers_full():
    """Every field for every paper in one response, sorted by relevance — the
    faculty-requested cumulative corpus table. Reads all of every paper's
    extracted fields at once instead of requiring N individual requests."""
    papers = list(_corpus["papers"].values())
    papers.sort(key=lambda p: p.get("relevance_score") or 0, reverse=True)
    return papers


@app.get("/api/papers/{paper_id}")
def get_paper(paper_id: str):
    """Full record view — every extracted field for one paper."""
    paper = _corpus["papers"].get(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found in corpus")
    return paper


@app.get("/api/compare")
def compare_papers(a: str, b: str):
    """Two full records returned together, for the side-by-side comparison view."""
    record_a = _corpus["papers"].get(a)
    record_b = _corpus["papers"].get(b)
    if record_a is None or record_b is None:
        missing = a if record_a is None else b
        raise HTTPException(status_code=404, detail=f"Paper not found: {missing}")
    return {"a": record_a, "b": record_b}


@app.get("/api/clusters")
def list_clusters():
    """Cluster/category definitions — used to render the folder-tab groupings."""
    return _corpus["clusters"]


@app.get("/api/papers/{paper_id}/pdf")
def get_paper_pdf(paper_id: str):
    """Serves the locally saved PDF for a paper, if one was downloaded.
    Falls back with a clear 404 (frontend uses this to fall back to
    external_link instead) rather than silently returning nothing."""
    raw = _raw_papers_by_id.get(paper_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    pdf_path = raw.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404,
                             detail="No local PDF for this paper — use external_link instead")

    return FileResponse(pdf_path, media_type="application/pdf",
                         filename=f"{paper_id}.pdf")


@app.get("/api/papers/{paper_id}/figures")
def get_paper_figures(paper_id: str):
    """List of figure image URLs extracted from this paper's PDF (empty list
    if it's abstract-only, or figure extraction hasn't been run yet)."""
    import json
    manifest_path = Path(_config["paths"]["processed_dir"]) / "figures_manifest.json"
    if not manifest_path.exists():
        return {"figures": []}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filenames = manifest.get(paper_id, [])
    return {"figures": [f"/figures/{paper_id}/{fn}" for fn in filenames]}


@app.get("/api/synthesis")
def get_corpus_synthesis():
    """Stage 5b output — the overall + per-category cross-paper synthesis.
    404s with a clear message if the current corpus predates this stage
    (e.g. it was collected before this feature existed)."""
    import json
    path = Path(_config["paths"]["processed_dir"]) / "corpus_synthesis.json"
    if not path.exists():
        raise HTTPException(status_code=404,
                             detail="No synthesis on file yet — run a new search/upload, "
                                    "or run: python -m src.synthesis.corpus_synthesis")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/gaps")
def get_gap_matrix():
    """Stage 6a output — the deterministic category x dataset gap matrix."""
    import json
    path = Path(_config["paths"]["processed_dir"]) / "gap_matrix.json"
    if not path.exists():
        raise HTTPException(status_code=404,
                             detail="No gap matrix on file yet — run a new search/upload, "
                                    "or run: python -m src.synthesis.gap_analysis")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/novelty-check")
async def novelty_check(file: UploadFile = File(...)):
    """Stage 6b — full-corpus (not one-vs-one) novelty comparison for an uploaded
    paper. Extracts the paper live (same as /api/compare-upload), then retrieves
    its most similar papers across the ENTIRE corpus and gets a grounded verdict.
    This is the genuinely RAG step: retrieval before generation, not just a raw
    LLM opinion."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        raw_text = extract_pdf_text(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read this PDF: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    cleaned = clean_text(raw_text)
    if not cleaned.strip():
        raise HTTPException(status_code=422,
                             detail="No extractable text found — is this a scanned/image-only PDF?")

    llm_cfg = _config["llm"]
    max_words = llm_cfg.get("max_context_words", 2500)
    budgeted_text = " ".join(cleaned.split()[:max_words])

    extraction = call_ollama_json(
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_content=f"Title: {file.filename}\n\nText:\n{budgeted_text}",
        temperature=llm_cfg.get("temperature", 0.2),
        timeout=llm_cfg.get("timeout_seconds", 300),
    )
    if extraction is None:
        raise HTTPException(status_code=500,
                             detail="Extraction failed — the local LLM did not return usable output. Try again.")

    try:
        result = compare_against_corpus(extraction, _config, top_k=5)
    except FileNotFoundError:
        raise HTTPException(status_code=404,
                             detail="No corpus to compare against yet — run a search or upload first.")

    return {
        "uploaded_title": file.filename.rsplit(".", 1)[0],
        "uploaded_summary": extraction.get("summary", ""),
        "uploaded_method": extraction.get("method", ""),
        **result,
    }


@app.post("/api/compare-upload")
async def compare_with_upload(existing_id: str = Form(...), file: UploadFile = File(...)):
    """Extract structured fields from an uploaded PDF live, and return it alongside
    an existing corpus record for side-by-side comparison. Runs the same Stage 4
    extraction the pipeline uses — this is a live LLM call, expect 30s-3min
    depending on paper length and your local model speed."""
    existing = _corpus["papers"].get(existing_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Paper not found in corpus")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        raw_text = extract_pdf_text(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read this PDF: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    cleaned = clean_text(raw_text)
    if not cleaned.strip():
        raise HTTPException(status_code=422,
                             detail="No extractable text found — is this a scanned/image-only PDF?")

    llm_cfg = _config["llm"]
    max_words = llm_cfg.get("max_context_words", 2500)
    budgeted_text = " ".join(cleaned.split()[:max_words])

    extraction = call_ollama_json(
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_content=f"Title: {file.filename}\n\nText:\n{budgeted_text}",
        temperature=llm_cfg.get("temperature", 0.2),
        timeout=llm_cfg.get("timeout_seconds", 300),
    )
    if extraction is None:
        raise HTTPException(status_code=500,
                             detail="Extraction failed — the local LLM did not return usable output. Try again.")

    uploaded_record = {
        "paper_id": "uploaded",
        "title": file.filename.rsplit(".", 1)[0],
        "year": None,
        "venue": "Your upload",
        "authors": [],
        "relevance_score": None,
        "has_full_text": True,
        "citation_count": None,
        "external_link": None,
        "cluster_id": None,
        "category": "Your paper",
        "extraction_failed": False,
        **extraction,
    }

    return {"a": uploaded_record, "b": existing}


@app.post("/api/search")
def start_search(payload: SearchRequest, background_tasks: BackgroundTasks):
    """Kick off a full pipeline run (Stages 1-4) for a new topic query. Returns
    immediately with a job_id — this does NOT block, since a real run can take
    30-60+ minutes depending on corpus size and your local LLM speed. Poll
    /api/jobs/{job_id} for progress."""
    from src.orchestration.jobs import create_job

    search_cfg = _build_search_config(payload)
    job_id = create_job("search")
    background_tasks.add_task(_run_and_reload, run_search_pipeline, job_id, search_cfg)
    return {"job_id": job_id}


@app.post("/api/upload-corpus")
async def start_upload_corpus(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    """Kick off a full pipeline run (Stages 2-4) over a user-supplied local PDF
    corpus — no Semantic Scholar query involved. Supports 50+ files; each is
    saved to disk, then registered exactly like a Stage 1 record would be."""
    from src.orchestration.jobs import create_job

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    upload_dir = Path(_config["paths"]["pdf_dir"]) / "user_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    skipped = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            skipped.append(f.filename)
            continue
        dest = upload_dir / f.filename
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved_paths.append(dest)

    if not saved_paths:
        raise HTTPException(status_code=400, detail="No valid PDF files in upload")

    upload_cfg = copy.deepcopy(_config)
    job_id = create_job("upload")
    background_tasks.add_task(_run_and_reload, run_upload_pipeline, job_id, upload_cfg, saved_paths)
    return {"job_id": job_id, "file_count": len(saved_paths), "skipped": skipped}


def _run_and_reload(pipeline_fn, job_id, *args) -> None:
    """Wraps a pipeline function so the in-memory corpus refreshes automatically
    once the job finishes successfully — avoids needing a separate manual step."""
    pipeline_fn(job_id, *args)
    job = get_job(job_id)
    if job and job.get("status") == "done":
        _reload_corpus()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    """Poll this while a search or upload job is running."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    return job


@app.post("/api/reload-corpus")
def reload_corpus():
    """Manually refresh the in-memory corpus from disk — normally not needed
    since jobs auto-reload on completion, but useful if you edited files by hand."""
    _reload_corpus()
    return {"papers": len(_corpus["papers"]), "clusters": len(_corpus["clusters"])}


# Serve extracted figures as static files. Must be mounted BEFORE the catch-all
# frontend mount below, or the frontend's html=True fallback would swallow these.
figures_dir = Path(_config["paths"].get("figures_dir", "data/figures"))
figures_dir.mkdir(parents=True, exist_ok=True)
app.mount("/figures", StaticFiles(directory=str(figures_dir)), name="figures")

# Serve the frontend last so /api/* and /figures routes above take priority over static matching.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")