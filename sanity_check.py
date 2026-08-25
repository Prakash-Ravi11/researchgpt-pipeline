"""
ResearchGPT pipeline sanity check — verifies each stage's output end-to-end.

Run this after any pipeline stage (or all of them) to catch broken/incomplete
data immediately, rather than discovering it three stages later. This is what
would have caught the 13 null-field extractions automatically instead of
needing a manual validate.py pass after the fact.

Run:
    python sanity_check.py --config configs/config.yaml
"""
import argparse
import json
from pathlib import Path

import yaml


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "OK" if condition else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return condition


def check_stage1(paths_cfg: dict) -> bool:
    print("\n[1/4] Stage 1 — Collection")
    path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    if not check("collected_papers.json exists", path.exists()):
        return False

    papers = json.loads(path.read_text(encoding="utf-8"))
    ok = check("at least 1 paper collected", len(papers) > 0, f"{len(papers)} papers")
    ok &= check("all papers have an abstract or full text",
                all(p.get("abstract") or p.get("has_full_text") for p in papers))
    full_text = sum(1 for p in papers if p.get("has_full_text"))
    print(f"       {full_text}/{len(papers)} have full-text PDFs")
    return ok


def check_stage2(paths_cfg: dict) -> bool:
    print("\n[2/4] Stage 2 — Processing (chunking)")
    path = Path(paths_cfg["processed_dir"]) / "chunks.json"
    if not check("chunks.json exists", path.exists()):
        return False

    chunks = json.loads(path.read_text(encoding="utf-8"))
    ok = check("at least 1 chunk produced", len(chunks) > 0, f"{len(chunks)} chunks")
    ok &= check("every chunk has non-empty text",
                all(c.get("text", "").strip() for c in chunks))
    paper_ids = {c["paper_id"] for c in chunks}
    print(f"       chunks cover {len(paper_ids)} distinct papers")

    # Cross-stage check: did every collected paper actually produce chunks?
    # A paper silently disappearing here (empty abstract AND no PDF text)
    # would otherwise just vanish from every downstream stage with no signal.
    meta_path = Path(paths_cfg["raw_metadata_dir"]) / "collected_papers.json"
    if meta_path.exists():
        papers = json.loads(meta_path.read_text(encoding="utf-8"))
        collected_ids = {p["paperId"] for p in papers}
        missing = collected_ids - paper_ids
        ok &= check("every collected paper produced at least 1 chunk",
                    len(missing) == 0, f"{len(missing)} paper(s) missing" if missing else "")
        if missing:
            titles = [p["title"][:70] for p in papers if p["paperId"] in missing]
            for t in titles:
                print(f"         - {t}")

    return ok


def check_stage3(paths_cfg: dict, system_cfg: dict) -> bool:
    print("\n[3/4] Stage 3 — Embedding & ChromaDB")
    chroma_dir = Path(paths_cfg["chroma_dir"])
    if not check("chroma_db directory exists", chroma_dir.exists()):
        return False

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(system_cfg["collection_name"])
        count = collection.count()
        ok = check("collection has vectors", count > 0, f"{count} vectors indexed")

        # Cross-stage check: vector count should exactly match chunk count.
        # A silent mismatch here (e.g. from a partial/interrupted Stage 3 run,
        # or re-running Stage 3 against stale chunks) would mean retrieval is
        # quietly working off incomplete data with no error anywhere.
        chunks_path = Path(paths_cfg["processed_dir"]) / "chunks.json"
        if chunks_path.exists():
            chunk_count = len(json.loads(chunks_path.read_text(encoding="utf-8")))
            ok &= check("vector count matches chunk count",
                        count == chunk_count, f"{count} vectors vs {chunk_count} chunks")
        return ok
    except Exception as e:
        return check("collection is readable", False, str(e))


def check_stage4(paths_cfg: dict) -> bool:
    print("\n[4/4] Stage 4 — Summarization & Categorization")
    path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    if not check("paper_summaries.json exists", path.exists()):
        return False

    records = json.loads(path.read_text(encoding="utf-8"))
    ok = check("every paper has a summary record", len(records) > 0, f"{len(records)} records")

    # Cross-stage check: same set of papers as Stage 2, not just same count
    # (two different papers could cancel out a count mismatch and look fine).
    chunks_path = Path(paths_cfg["processed_dir"]) / "chunks.json"
    if chunks_path.exists():
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunk_paper_ids = {c["paper_id"] for c in chunks}
        summary_paper_ids = {r["paper_id"] for r in records}
        ok &= check("paper set matches Stage 2 exactly",
                    chunk_paper_ids == summary_paper_ids,
                    "" if chunk_paper_ids == summary_paper_ids
                    else f"{len(chunk_paper_ids ^ summary_paper_ids)} paper(s) differ")

    # This is the exact check that would have caught the 13 null-field papers
    # automatically instead of needing a manual validate.py run afterward.
    content_fields = ["summary", "problem_addressed", "method", "key_findings"]
    weak = []
    for r in records:
        empty_count = sum(1 for f in content_fields if not (r.get(f) or "").strip())
        if empty_count >= 3:
            weak.append(r.get("title", r.get("paper_id", "unknown"))[:70])

    ok &= check("no papers with mostly-empty extraction",
                len(weak) == 0, f"{len(weak)} weak paper(s)" if weak else "")
    if weak:
        print("       Weak papers (need re-extraction — see --retry-weak in summarize.py):")
        for title in weak:
            print(f"         - {title}")

    has_category = all("category" in r and r["category"] for r in records)
    ok &= check("every paper has a category assigned", has_category)

    clusters_path = Path(paths_cfg["processed_dir"]) / "clusters.json"
    if clusters_path.exists():
        clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
        labels = [c["label"] for c in clusters.values()]
        ok &= check("cluster labels are not all identical",
                    len(set(labels)) > 1, f"{len(set(labels))} distinct labels")

    return ok


def run_sanity_check(config: dict) -> None:
    print("=" * 60)
    print("RESEARCHGPT PIPELINE — SANITY CHECK")
    print("=" * 60)

    paths_cfg = config["paths"]
    system_cfg = config["system"]

    results = {
        "Stage 1 (Collection)": check_stage1(paths_cfg),
        "Stage 2 (Processing)": check_stage2(paths_cfg),
        "Stage 3 (Embedding)": check_stage3(paths_cfg, system_cfg),
        "Stage 4 (Summarization)": check_stage4(paths_cfg),
    }

    print("\n" + "=" * 60)
    all_pass = all(results.values())
    for name, passed in results.items():
        print(f"  {'✓' if passed else '✗'} {name}")
    print("=" * 60)
    print("ALL STAGES PASSED ✓" if all_pass else "SOME STAGES NEED ATTENTION ✗")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_sanity_check(cfg)