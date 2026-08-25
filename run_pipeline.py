"""
Run the full ResearchGPT pipeline end-to-end: Stage 1 -> 2 -> 3 -> 4 -> sanity check.

Useful for stress-testing against a different domain/config without manually
chaining 5 commands — e.g. to check the pipeline holds up on paper types very
different from your main corpus (different citation styles, longer surveys,
heavier math notation, etc):

    python run_pipeline.py --config configs/test_config.yaml

Stops immediately if any stage fails, rather than continuing on broken data.
"""
import argparse
import sys

import yaml

from src.collection.semantic_scholar import run_collection
from src.processing.pdf_parser import run_processing
from src.embedding.build_index import run_embedding
from src.summarization.summarize import run_summarization
from sanity_check import run_sanity_check


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_all(config: dict, config_path: str) -> bool:
    stages = [
        ("Stage 1 — Collection", lambda: run_collection(config)),
        ("Stage 2 — Processing", lambda: run_processing(config)),
        ("Stage 3 — Embedding", lambda: run_embedding(config)),
        ("Stage 4 — Summarization", lambda: run_summarization(config)),
    ]

    for name, fn in stages:
        print(f"\n{'#' * 60}")
        print(f"# {name}")
        print(f"{'#' * 60}")
        try:
            fn()
        except Exception as e:
            print(f"\n!! {name} FAILED: {e}")
            print("Stopping — not running further stages on broken data.")
            return False

    print(f"\n{'#' * 60}")
    print("# Sanity Check")
    print(f"{'#' * 60}")
    run_sanity_check(config)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    success = run_all(cfg, args.config)
    sys.exit(0 if success else 1)