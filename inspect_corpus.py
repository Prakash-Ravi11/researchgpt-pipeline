"""Quick sanity check on Stage 1 output — run before scaling to the full pull."""
import json

with open("data/raw_metadata/collected_papers.json", encoding="utf-8") as f:
    papers = json.load(f)

print(f"Total papers: {len(papers)}\n")

for p in papers:
    score = p.get("relevance_score", 0)
    full_text = "PDF" if p.get("has_full_text") else "abstract-only"
    print(f"{score:.3f}  [{full_text:13}]  {p['title'][:75]}")