"""
Fix the 12 (or however many) papers flagged by detect_prompt_leakage.py.

Critical: extraction_cache.json caches by paper_id and skips the LLM call
entirely for anything already cached. If you just fixed the prompt and
reran Stage 4 normally, these papers would be served their OLD bad cached
answer and the fix would silently do nothing for them. This script evicts
them from cache first, so they're forced through the (now-fixed) prompt.

Run AFTER patching EXTRACTION_SYSTEM_PROMPT / DATASET_FALLBACK_PROMPT in
summarize.py, and after running detect_prompt_leakage.py to produce the
flagged-papers file this reads:

    python -m src.summarization.fix_flagged_leakage --config configs/config.yaml
"""
import argparse
import json
from pathlib import Path

import yaml

from src.summarization.summarize import (
    load_chunks, reconstruct_paper_texts, extract_paper_fields,
    load_extraction_cache, save_extraction_cache,
)
from src.summarization.detect_prompt_leakage import scan_for_leakage


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_fix(config: dict) -> None:
    paths_cfg = config["paths"]
    llm_cfg = config["llm"]
    processed_dir = Path(paths_cfg["processed_dir"])

    flagged_path = processed_dir / "prompt_leakage_flagged_paper_summaries.json"
    if not flagged_path.exists():
        raise RuntimeError(
            "No flagged-papers file found. Run: "
            "python -m src.summarization.detect_prompt_leakage --config configs/config.yaml  first."
        )
    flagged = json.loads(flagged_path.read_text(encoding="utf-8"))
    flagged_ids = {f["paper_id"] for f in flagged}
    print(f"Re-extracting {len(flagged_ids)} flagged paper(s)...")

    # The critical step: evict these papers from the persistent cache BEFORE
    # extraction, so extract_paper_fields is forced to actually call the LLM
    # again instead of silently returning the same bad cached answer.
    cache = load_extraction_cache(paths_cfg["processed_dir"])
    evicted = 0
    for pid in flagged_ids:
        if pid in cache:
            del cache[pid]
            evicted += 1
    save_extraction_cache(paths_cfg["processed_dir"], cache)
    print(f"Evicted {evicted} paper(s) from extraction_cache.json (forces real re-extraction, not a cache hit)")

    chunks = load_chunks(paths_cfg["processed_dir"])
    all_papers = reconstruct_paper_texts(chunks, llm_cfg.get("max_context_words", 2500))
    papers_to_redo = {pid: all_papers[pid] for pid in flagged_ids if pid in all_papers}

    # Slightly higher temperature helps break out of the exact-phrase anchoring
    # pattern that caused this in the first place.
    retry_llm_cfg = {**llm_cfg, "temperature": max(llm_cfg.get("temperature", 0.2), 0.4)}
    new_extractions = extract_paper_fields(papers_to_redo, retry_llm_cfg, cache={}, processed_dir=None)

    # Verify the fix actually worked before trusting it — re-run the same
    # detector against the NEW extractions, not just assume the prompt patch
    # fixed everything.
    check_records = [{"paper_id": pid, "title": all_papers[pid]["title"], **ex}
                      for pid, ex in new_extractions.items()]
    still_leaking = scan_for_leakage(check_records)

    summaries_path = processed_dir / "paper_summaries.json"
    records = json.loads(summaries_path.read_text(encoding="utf-8"))
    for r in records:
        if r["paper_id"] in new_extractions:
            for k, v in new_extractions[r["paper_id"]].items():
                r[k] = v

    summaries_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nUpdated {summaries_path}")

    if still_leaking:
        print(f"\n{len(still_leaking)} paper(s) STILL show leaked phrases after re-extraction with the "
              f"patched prompt — the prompt fix may not be applied correctly, or these need manual review:")
        for f in still_leaking:
            print(f"  - {f['title'][:70]}: {f['leaked_phrases_found']}")
    else:
        print(f"\nAll {len(flagged_ids)} flagged papers re-extracted clean — no leaked phrases detected "
              f"in the new extractions. Confirmed, not just assumed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_fix(cfg)