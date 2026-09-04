"""
Stage 5b — Collective corpus synthesis.

Reads the already-extracted per-paper fields (Stage 4/5a output) and produces
a cross-paper narrative: the shared problem landscape, common methods/trends,
dominant datasets/metrics, and points of convergence or conflict across the
corpus — the kind of synthesis a human writes in a literature review's
"related work" section, generated FROM the structured extraction table
rather than by re-reading all the papers.

Cheap relative to Stage 4: this reads paper_summaries.json (short structured
text), not PDFs — one LLM call per category plus one overall, not one call
per paper.

Run standalone:
    python -m src.synthesis.corpus_synthesis --config configs/config.yaml
"""
import argparse
import difflib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import yaml

from src.summarization.summarize import call_ollama_json, estimate_num_ctx, prime_ollama_cache

SYNTHESIS_SYSTEM_PROMPT = """You are writing the collective synthesis section of a literature review, given \
structured summaries of multiple papers that share a research domain. Do not describe each paper individually — \
synthesize ACROSS them. Every claim you make must be traceable back to specific papers in the input — do not \
generalize beyond what the input actually supports, and do not blend details from different papers into a claim \
neither individually supports. Respond with ONLY a JSON object with these exact keys:
- "shared_problem_landscape": 2-4 sentences on the common problem(s) this set of papers addresses
- "common_methods_trends": 2-4 sentences on recurring technical approaches or trends across these papers
- "dominant_datasets_metrics": which datasets and metrics appear most across these papers, and any notable lack of standardization
- "convergence_or_conflicts": where these papers' results or claims agree, and where they genuinely conflict or take different positions
- "example_papers": a list of 3-5 paper titles from the input that most directly support the claims above — pick the papers a reader should open first to spot-check this synthesis, not just the first ones listed. Copy each title EXACTLY as given in the input — do not add brackets, tags, or any other text to it, and do not paraphrase or shorten it.

Respond with ONLY the JSON object, no other text."""


def _normalize_title(title: str) -> str:
    """Collapse cosmetic differences that aren't real mismatches: smart vs
    straight quotes/apostrophes, en/em-dashes vs hyphens, a trailing period,
    extra whitespace, and case — all common LLM "copy" habits (or, in the
    trailing-period case, an artifact of how titles get stored upstream).
    NOT stripped here: bracket/tag suffixes — those are handled separately in
    _validate_example_papers so a stripped-suffix match can be logged
    distinctly from a plain formatting difference.
    """
    t = unicodedata.normalize("NFKC", title)
    t = t.replace("\u2019", "'").replace("\u2018", "'")  # smart apostrophes -> straight
    t = t.replace("\u201c", '"').replace("\u201d", '"')  # smart quotes -> straight
    t = t.replace("\u2013", "-").replace("\u2014", "-")  # en-dash / em-dash -> hyphen
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\.$", "", t)  # trailing period — titles don't normally end with one;
                                # seen in practice as a storage artifact, not an LLM habit
    return t.lower()


def _validate_example_papers(cited_titles: list, real_titles: set[str], group_label: str) -> tuple[list[str], bool]:
    """Anti-hallucination check: keep only cited titles that actually exist in
    this group's input — but don't let brittle exact-matching produce false
    positives on real titles the LLM only reformatted slightly (smart quotes,
    dashes, an appended category tag, minor truncation). Three tiers, strictest first:
      1. Exact match after normalizing quotes/dashes/whitespace/case
      2. Same, after stripping a trailing "[...]" or "(...)" annotation
      3. Fuzzy match (>=90% similarity) against the closest real title
    Only titles that fail all three are treated as likely fabricated and
    dropped — that's a much stronger claim than "didn't match verbatim."

    Returns (verified_titles, all_cited_were_rejected). The second value lets
    the caller distinguish "this group genuinely had nothing worth citing"
    from "the LLM cited things but every single one looked fabricated" —
    those need different follow-up (the second is a real quality problem
    worth investigating, the first is normal), and were previously
    indistinguishable once example_papers came back empty either way.
    """
    if not cited_titles:
        return [], False

    normalized_real = {_normalize_title(t): t for t in real_titles}
    verified, dropped = [], []

    for cited in cited_titles:
        norm_cited = _normalize_title(cited)

        if norm_cited in normalized_real:
            verified.append(normalized_real[norm_cited])  # use the corpus's exact title, not the LLM's
            continue

        stripped = re.sub(r"\s*[\[\(][^\]\)]*[\]\)]\s*$", "", cited).strip()
        norm_stripped = _normalize_title(stripped)
        if norm_stripped in normalized_real:
            verified.append(normalized_real[norm_stripped])
            print(f"    (matched '{cited}' to a real title after stripping an appended tag)")
            continue

        best_match, best_ratio = None, 0.0
        for norm_real, original_real in normalized_real.items():
            ratio = difflib.SequenceMatcher(None, norm_cited, norm_real).ratio()
            if ratio > best_ratio:
                best_match, best_ratio = original_real, ratio

        if best_ratio >= 0.90:
            verified.append(best_match)
            print(f"    (fuzzy-matched '{cited}' to real title '{best_match}' at {best_ratio:.0%} similarity)")
        else:
            dropped.append(cited)

    if dropped:
        print(f"    WARNING: '{group_label}' synthesis cited {len(dropped)} paper title(s) that could NOT "
              f"be matched to the actual input even fuzzily — likely genuinely fabricated: {dropped}")

    all_rejected = len(cited_titles) > 0 and len(verified) == 0
    return verified, all_rejected


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _paper_line(p: dict, compact: bool) -> str:
    """compact=True is used for the OVERALL pass, which sees every paper in the
    corpus at once — at 40-50 papers with the current (intentionally deep)
    extraction fields, including full problem/method/results text per paper
    was overflowing even a generous context window and silently producing
    empty/garbled output. Per-category passes see far fewer papers each, so
    they keep the fuller detail — that's not the group that was failing."""
    if compact:
        return (f"- {p.get('title', '')} [{p.get('category', '')}] "
                f"— {p.get('key_findings', '')} "
                f"Datasets: {', '.join(p.get('datasets', []))}")
    return (f"- {p.get('title', '')} [{p.get('category', '')}] "
            f"— Problem: {p.get('problem_addressed', '')} "
            f"Method: {p.get('method', '')} "
            f"Results: {p.get('results', '')} "
            f"Datasets: {', '.join(p.get('datasets', []))} "
            f"Metrics: {', '.join(p.get('metrics', []))}")


def _synthesize_group(papers: list[dict], llm_cfg: dict, group_label: str, compact: bool) -> dict:
    lines = [_paper_line(p, compact=compact) for p in papers]
    user_content = "\n".join(lines)
    real_titles = {p.get("title", "") for p in papers}

    # Sized to what THIS group's content actually needs, same reasoning as
    # Stage 4's per-paper extraction — a fixed context size was the root
    # cause of the overall pass silently failing on larger corpora.
    # `output_reservation` is the 3.2b name for what used to be
    # `response_budget_tokens` (CONTEXT_BUDGET_REPORT.md §3.2b). This call site was
    # missed in that rename and raised TypeError on every fresh synthesis run.
    num_ctx = estimate_num_ctx(user_content, system_prompt=SYNTHESIS_SYSTEM_PROMPT,
                                output_reservation=500, min_ctx=2048, max_ctx=8192)

    result = call_ollama_json(
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        user_content=user_content,
        temperature=llm_cfg.get("temperature", 0.0),
        timeout=llm_cfg.get("timeout_seconds", 300),
        num_ctx=num_ctx,
        seed=llm_cfg.get("seed"),
    )
    if result is None:
        print(f"    Synthesis FAILED for '{group_label}' ({len(papers)} papers, num_ctx={num_ctx}) "
              f"— LLM call timed out or returned unparseable output after retries")
        result = {
            "shared_problem_landscape": "", "common_methods_trends": "",
            "dominant_datasets_metrics": "", "convergence_or_conflicts": "",
            "example_papers": [], "_synthesis_failed": True,
        }
    else:
        verified, all_rejected = _validate_example_papers(
            result.get("example_papers", []), real_titles, group_label
        )
        result["example_papers"] = verified
        if all_rejected:
            # Previously indistinguishable from "nothing worth citing" — now
            # explicit, same principle as _extraction_failed/_no_dataset_stated
            # elsewhere in this pipeline: flag ambiguous-empty states rather
            # than let them look identical to a genuinely clean result.
            result["_all_example_papers_rejected"] = True
            print(f"    WARNING: EVERY cited example for '{group_label}' was rejected as unmatched — "
                  f"this synthesis section has NO verified example papers, not just fewer than requested")
    return result


def run_corpus_synthesis(config: dict) -> dict:
    paths_cfg = config["paths"]
    llm_cfg = config["llm"]

    prime_ollama_cache(llm_cfg)  # reproducibility: fixed prompt-cache start (no-op unless seed set)

    summaries_path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    papers = json.loads(summaries_path.read_text(encoding="utf-8"))

    print(f"Synthesizing across {len(papers)} papers (overall pass first, compact per-paper detail)...")
    overall = _synthesize_group(papers, llm_cfg, group_label="OVERALL", compact=True)

    by_category = defaultdict(list)
    for p in papers:
        by_category[p.get("category", "Uncategorized")].append(p)

    print(f"Synthesizing per category ({len(by_category)} categories, full per-paper detail)...")
    per_category = {}
    for category, group in by_category.items():
        per_category[category] = _synthesize_group(group, llm_cfg, group_label=category, compact=False)

    failed_count = sum(1 for r in [overall, *per_category.values()] if r.get("_synthesis_failed"))
    if failed_count:
        print(f"  {failed_count} synthesis section(s) failed — flagged in output, "
              f"visible in the UI rather than silently blank")

    rejected_count = sum(1 for r in [overall, *per_category.values()] if r.get("_all_example_papers_rejected"))
    if rejected_count:
        print(f"  {rejected_count} synthesis section(s) had ALL cited examples rejected as unmatched — "
              f"worth a manual look, this may indicate the fuzzy-match threshold needs tuning")

    output = {"overall": overall, "per_category": per_category, "paper_count": len(papers)}

    out_path = Path(paths_cfg["processed_dir"]) / "corpus_synthesis.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved corpus synthesis to {out_path}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_corpus_synthesis(cfg)