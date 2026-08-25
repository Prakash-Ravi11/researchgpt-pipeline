"""
Verify the retrieval-aware fix on your REAL corpus, cheaply.

Doesn't call the LLM at all — just compares which chunks get selected by the
OLD front-loading approach vs the NEW retrieval-aware approach, for every
full-text paper that exceeds the word budget (the only papers where the two
approaches can differ). This is fast (only embedding queries, no generation)
so you can confirm the fix is actually doing something before spending 20+
minutes re-running full extraction.

What "working" looks like: for long papers, the new approach should include
chunks the old one dropped — specifically chunks from later in the paper
(higher chunk_index), which is where results/limitations/conclusions usually
live.

Run:
    python -m src.summarization.verify_retrieval_fix --config configs/config.yaml
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from src.summarization.summarize import reconstruct_paper_texts, load_chunks
from src.summarization.retrieval_aware import build_retrieval_aware_papers


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_verification(config: dict) -> None:
    paths_cfg = config["paths"]
    llm_cfg = config["llm"]
    max_words = llm_cfg.get("max_context_words", 2500)

    chunks = load_chunks(paths_cfg["processed_dir"])
    by_paper = defaultdict(list)
    for c in chunks:
        by_paper[c["paper_id"]].append(c)

    print(f"Comparing OLD (front-loaded) vs NEW (retrieval-aware) selection, "
          f"word budget = {max_words}\n")

    old_papers = reconstruct_paper_texts(chunks, max_words)
    print("Running retrieval-aware selection (queries ChromaDB per paper)...")
    new_papers = build_retrieval_aware_papers(config, max_words)

    affected = []
    for paper_id, paper_chunks in by_paper.items():
        total_words = sum(len(c["text"].split()) for c in paper_chunks)
        if total_words <= max_words:
            continue  # under budget — old and new are identical here by design, skip

        old_text = old_papers[paper_id]["text"]
        new_text = new_papers[paper_id]["text"]
        title = paper_chunks[0]["title"]

        # Rough proxy for "did selection actually change": compare word overlap.
        old_words = set(old_text.split())
        new_words = set(new_text.split())
        overlap = len(old_words & new_words) / max(len(old_words), 1)

        # Did the new selection pull in any chunks from later in the paper
        # that the old (front-loaded) selection didn't include at all?
        max_chunk_index = max(c["chunk_index"] for c in paper_chunks)
        old_included_idxs = {c["chunk_index"] for c in paper_chunks
                              if c["text"][:30] in old_text}
        new_included_idxs = {c["chunk_index"] for c in paper_chunks
                              if c["text"][:30] in new_text}
        new_late_chunks = {i for i in new_included_idxs if i not in old_included_idxs
                            and i > max_chunk_index * 0.5}

        affected.append({
            "title": title, "total_words": total_words,
            "text_overlap_pct": round(overlap * 100, 1),
            "new_late_chunks_included": len(new_late_chunks),
            "max_chunk_index": max_chunk_index,
        })

    if not affected:
        print("No papers exceed the word budget in this corpus — retrieval-aware "
              "selection has nothing to do differently from front-loading here. "
              "The fix is correctly a no-op for this corpus (not broken, just not "
              "yet relevant — try it on a corpus with longer full-text papers).")
        return

    print(f"{len(affected)} paper(s) exceed the word budget (where the fix can matter):\n")
    changed_count = 0
    for a in affected:
        changed = a["new_late_chunks_included"] > 0
        changed_count += changed
        marker = "CHANGED" if changed else "same as before"
        print(f"  [{marker}] {a['title'][:60]}")
        print(f"      {a['total_words']} words total, {a['text_overlap_pct']}% text overlap "
              f"with old selection, {a['new_late_chunks_included']} new late-paper chunk(s) included")

    print(f"\n{changed_count}/{len(affected)} over-budget papers got different (later-content-including) "
          f"selection under the retrieval-aware fix.")
    if changed_count == 0:
        print("WARNING: the fix ran without error but selected the same content as before for "
              "every affected paper — worth double-checking the ChromaDB query is actually "
              "filtering by paper_id correctly, or that TARGET_QUERIES are matching real content.")
    else:
        print("This confirms the fix is doing real work — proceed to a full Stage 5 rerun on a "
              "small subset next, and check if results/limitations fields improve for these "
              "specific flagged papers.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_verification(cfg)