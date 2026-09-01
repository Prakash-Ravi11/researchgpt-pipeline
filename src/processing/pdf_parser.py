"""
Stage 2 — Processing.

Extracts text from downloaded PDFs (PyMuPDF), falls back to the abstract for
papers with no full text, cleans obvious noise (references section, repeated
headers/footers), and splits everything into overlapping word-based chunks
ready for embedding in Stage 3.

Run standalone for testing:
    python -m src.processing.pdf_parser --config configs/config.yaml
"""
import argparse
import json
import re
from pathlib import Path

import yaml
from tqdm import tqdm

# Heading text that, once seen, marks the start of back-matter we don't want
# fed into the embedding/extraction stages (references, acknowledgments, etc).
CUTOFF_HEADINGS = re.compile(
    r"\n\s*(references|acknowledg(e)?ments|bibliography)\s*\n", re.IGNORECASE
)


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_pdf_text(pdf_path: str) -> str:
    """Extract raw text from a PDF using PyMuPDF."""
    import pymupdf as fitz  # PyMuPDF — using new import name to avoid deprecation warning

    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def clean_text(text: str) -> str:
    """Strip references/back-matter and collapse noisy whitespace."""
    match = CUTOFF_HEADINGS.search(text)
    if match:
        text = text[: match.start()]

    # Collapse repeated blank lines and excessive spacing left by PDF extraction.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Word-based sliding-window chunking with overlap.

    Guards against chunk_overlap >= chunk_size: in that case `start` would
    never advance past its previous position (end - overlap <= start), and
    the loop would spin forever re-emitting the same window. This can't
    happen with the shipped config (800/100), but a bad config edit
    (e.g. someone bumping overlap without checking) would otherwise hang
    silently instead of failing fast with a clear error.
    """
    if overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({overlap}) must be smaller than chunk_size ({chunk_size}), "
            f"otherwise chunking never advances and will loop forever."
        )

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap  # step forward, re-including the overlap window

    return chunks


def process_paper(paper: dict, chunk_size: int, overlap: int) -> list[dict]:
    """Return a list of chunk records for one paper (full text or abstract fallback)."""
    if paper.get("has_full_text") and paper.get("pdf_path"):
        try:
            raw_text = extract_pdf_text(paper["pdf_path"])
            source = "full_text"
        except Exception as e:
            print(f"  PDF extraction failed for {paper['paperId']} ({e}) — using abstract instead")
            raw_text = paper.get("abstract", "")
            source = "abstract_fallback"
    else:
        raw_text = paper.get("abstract", "")
        source = "abstract_only"

    cleaned = clean_text(raw_text)
    text_chunks = chunk_text(cleaned, chunk_size, overlap)

    records = []
    for i, chunk in enumerate(text_chunks):
        records.append({
            "chunk_id": f"{paper['paperId']}_{i}",
            "paper_id": paper["paperId"],
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "has_full_text": paper.get("has_full_text", False),
            "source": source,
            "chunk_index": i,
            "text": chunk,
        })

    return records


def process_paper_grounded(paper: dict) -> list[dict]:
    """Provenance-bearing chunking (FINAL_REPORT.md §O change 3).

    Parses the validated PDF or JATS/XML into section/page/node-anchored blocks,
    then chunks WITHIN blocks so every chunk keeps section + page/node + char
    span. Returns the same superset schema as ``process_paper`` PLUS the
    provenance fields, so Stage 3 / retrieval / the evidence gate can consume it
    while nothing that reads the legacy fields breaks.
    """
    from src.evidence.represent import build_document
    from src.evidence.chunker import chunk_document

    pid = paper["paperId"]
    rep = paper.get("representation_type") or ("pdf" if paper.get("has_full_text") else "abstract")
    acq = {"paper_id": pid, "source": paper.get("pdf_source") or "semantic_scholar",
           "representation_type": rep, "status": paper.get("acquisition_status", "")}

    data = None
    if paper.get("has_full_text") and paper.get("pdf_path"):
        p = Path(paper["pdf_path"])
        if p.exists():
            data = p.read_bytes()
    doc = build_document(acq, data, fallback_abstract=paper.get("abstract"))
    ev_chunks = chunk_document(doc)

    legacy_source = ("full_text" if doc["representation"] in ("pdf", "jats_xml")
                     else "abstract_only")
    records = []
    for i, c in enumerate(ev_chunks):
        records.append({
            "chunk_id": c["chunk_id"],
            "paper_id": pid,
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "has_full_text": paper.get("has_full_text", False),
            "source": legacy_source,
            "chunk_index": i,
            "text": c["text"],
            # provenance (§O)
            "representation": c["representation"],
            "section": c["section"],
            "page_or_node": c["page_or_node"],
            "block_id": c["block_id"],
            "block_type": c["block_type"],
            "char_start": c["char_start"],
            "char_end": c["char_end"],
        })
    return records


def run_processing(config: dict) -> list[dict]:
    proc_cfg = config["processing"]
    paths_cfg = config["paths"]
    grounded = bool((config.get("evidence_grounding", {}) or {}).get("enabled"))

    metadata_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    with open(metadata_path, encoding="utf-8") as f:
        papers = json.load(f)

    print(f"Processing {len(papers)} papers "
          f"(chunk_size={proc_cfg['chunk_size']}, overlap={proc_cfg['chunk_overlap']}"
          f"{', provenance-aware' if grounded else ''})")

    all_chunks = []
    empty_papers = []
    for paper in tqdm(papers, desc="Chunking"):
        if grounded:
            records = process_paper_grounded(paper)
        else:
            records = process_paper(paper, proc_cfg["chunk_size"], proc_cfg["chunk_overlap"])
        if not records:
            empty_papers.append(paper.get("title", paper["paperId"]))
        all_chunks.extend(records)

    if empty_papers:
        print(f"\n{len(empty_papers)} papers produced NO chunks (empty abstract + no PDF text):")
        for title in empty_papers:
            print(f"  - {title[:80]}")

    full_text_chunks = sum(1 for c in all_chunks if c["source"] == "full_text")
    print(f"\nTotal chunks: {len(all_chunks)} "
          f"({full_text_chunks} from full text, {len(all_chunks) - full_text_chunks} from abstracts)")

    out_dir = Path(paths_cfg["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "chunks.json"
    out_path.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")
    print(f"Saved {len(all_chunks)} chunks to {out_path}")

    return all_chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_processing(cfg)