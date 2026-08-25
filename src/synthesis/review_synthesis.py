"""
Human-readable synthesis review — for manually spot-checking whether the
corpus synthesis's CLAIMS actually match what its cited papers say, not just
whether the cited titles are real (that's already verified automatically by
corpus_synthesis.py; this checks something that can't be automated).

For a given category (or all), prints the synthesis narrative next to the
full extracted record of every paper it cites as an example — read both and
judge for yourself whether "these papers converge on X" etc. actually holds
up against what those papers really say.

Run:
    python -m src.synthesis.review_synthesis --config configs/config.yaml
    python -m src.synthesis.review_synthesis --config configs/config.yaml --category "Case-Control and Survey Analysis"
"""
import argparse
import json
import textwrap
from pathlib import Path

import yaml


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def wrap(text: str, indent: str = "    ") -> str:
    if not text:
        return f"{indent}(empty)"
    return textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)


def print_group(label: str, group: dict, papers_by_title: dict) -> None:
    print(f"\n{'#' * 78}")
    print(f"# {label}")
    print("#" * 78)

    if group.get("_synthesis_failed"):
        print("\n  *** THIS SECTION FAILED TO GENERATE — nothing to review ***")
        return

    print("\n[SHARED PROBLEM LANDSCAPE]")
    print(wrap(group.get("shared_problem_landscape", "")))

    print("\n[COMMON METHODS / TRENDS]")
    print(wrap(group.get("common_methods_trends", "")))

    print("\n[DOMINANT DATASETS / METRICS]")
    print(wrap(group.get("dominant_datasets_metrics", "")))

    print("\n[CONVERGENCE OR CONFLICTS]")
    print(wrap(group.get("convergence_or_conflicts", "")))

    if group.get("_all_example_papers_rejected"):
        print("\n  *** ALL cited example papers were rejected as unmatched — "
              "no real papers to cross-check this section against ***")
        return

    example_titles = group.get("example_papers", [])
    print(f"\n[CITED AS EXAMPLES — {len(example_titles)} paper(s)] — read these against the claims above:")
    for title in example_titles:
        paper = papers_by_title.get(title)
        print(f"\n  --- {title[:90]}")
        if not paper:
            print("      (not found in paper_summaries.json — unexpected, worth checking)")
            continue
        print(f"      Problem:  {textwrap.shorten(paper.get('problem_addressed', ''), 140)}")
        print(f"      Method:   {textwrap.shorten(paper.get('method', ''), 140)}")
        print(f"      Results:  {textwrap.shorten(paper.get('results', paper.get('key_findings', '')), 140)}")
        print(f"      Datasets: {', '.join(paper.get('datasets', []) or []) or '(none listed)'}")


def run_review(config: dict, category_filter: str | None) -> None:
    processed_dir = Path(config["paths"]["processed_dir"])

    synthesis_path = processed_dir / "corpus_synthesis.json"
    summaries_path = processed_dir / "paper_summaries.json"
    if not synthesis_path.exists():
        raise RuntimeError("corpus_synthesis.json not found — run corpus_synthesis.py first.")
    if not summaries_path.exists():
        raise RuntimeError("paper_summaries.json not found — run Stage 4 first.")

    synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    papers = json.loads(summaries_path.read_text(encoding="utf-8"))
    papers_by_title = {p["title"]: p for p in papers}

    if category_filter:
        if category_filter not in synthesis["per_category"]:
            available = list(synthesis["per_category"].keys())
            raise RuntimeError(f"Category '{category_filter}' not found. Available: {available}")
        print_group(f"CATEGORY: {category_filter}", synthesis["per_category"][category_filter], papers_by_title)
    else:
        print_group("OVERALL (whole corpus)", synthesis["overall"], papers_by_title)
        for cat, group in synthesis["per_category"].items():
            print_group(f"CATEGORY: {cat}", group, papers_by_title)

    print(f"\n\n{'=' * 78}")
    print("Read each section above and ask: does the narrative claim actually match what")
    print("the cited papers' Problem/Method/Results say? Vague claims that could apply to")
    print("almost any paper in the field are a red flag, even with real citations attached.")
    print("=" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--category", default=None,
                         help="Review just one category (default: overall + all categories)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_review(cfg, args.category)