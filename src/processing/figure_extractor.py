"""
Extracts embedded figures/diagrams from full-text PDFs.

Pulls actual embedded raster images out of each PDF (PyMuPDF's raw image
extraction), not page screenshots — this gets real figure/diagram assets as
they exist in the file. A size filter drops tiny images (icons, logos,
publisher decorations) that aren't real figures.

Abstract-only papers have no PDF and are skipped — nothing to extract.

Run standalone (e.g. to backfill figures for a corpus you already collected):
    python -m src.processing.figure_extractor --config configs/config.yaml
"""
import argparse
import json
from pathlib import Path

import yaml
from tqdm import tqdm

# Images smaller than this are almost always icons, logos, or decorative
# elements, not real figures — tuned conservatively to avoid dropping small
# but genuine diagrams (e.g. a compact architecture box).
MIN_WIDTH = 150
MIN_HEIGHT = 150
MIN_AREA = 40000  # guards against thin decorative strips passing the width/height check alone


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_figures_from_pdf(pdf_path: str, paper_id: str, out_dir: Path) -> list[str]:
    """Pulls embedded raster images from one PDF, filters out icon-sized noise,
    saves the rest to out_dir/paper_id/. Returns saved filenames (not full paths)."""
    import pymupdf

    paper_dir = out_dir / paper_id
    doc = pymupdf.open(pdf_path)
    saved = []
    seen_xrefs = set()  # the same image can be referenced by multiple pages (e.g. a repeated logo)

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            width, height = img[2], img[3]
            if width < MIN_WIDTH or height < MIN_HEIGHT or (width * height) < MIN_AREA:
                continue  # too small to be a real figure

            try:
                base = doc.extract_image(xref)
            except Exception:
                continue  # a small fraction of embedded images are malformed/unsupported — skip, don't crash the run

            ext = base.get("ext", "png")
            filename = f"p{page_index + 1}_x{xref}.{ext}"
            paper_dir.mkdir(parents=True, exist_ok=True)
            (paper_dir / filename).write_bytes(base["image"])
            saved.append(filename)

    doc.close()
    return saved


def run_figure_extraction(config: dict) -> dict[str, list[str]]:
    paths_cfg = config["paths"]
    raw_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    papers = json.loads(raw_path.read_text(encoding="utf-8"))

    figures_dir = Path(paths_cfg.get("figures_dir", "data/figures"))
    manifest = {}

    full_text_papers = [p for p in papers if p.get("has_full_text") and p.get("pdf_path")]
    print(f"Extracting figures from {len(full_text_papers)} full-text papers "
          f"({len(papers) - len(full_text_papers)} abstract-only papers skipped — no PDF to extract from)")

    for paper in tqdm(full_text_papers, desc="Extracting figures"):
        try:
            saved = extract_figures_from_pdf(paper["pdf_path"], paper["paperId"], figures_dir)
        except Exception as e:
            print(f"  Figure extraction failed for {paper['paperId']} ({e}) — skipping")
            saved = []
        if saved:
            manifest[paper["paperId"]] = saved

    total_figures = sum(len(v) for v in manifest.values())
    print(f"Extracted {total_figures} figures across {len(manifest)} papers")

    manifest_path = Path(paths_cfg["processed_dir"]) / "figures_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved manifest to {manifest_path}")

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_figure_extraction(cfg)