"""
Detect prompt-example leakage in extracted data.

Real bug found by manual review: multiple UNRELATED papers ended up with the
literal illustrative example text from EXTRACTION_SYSTEM_PROMPT /
DATASET_FALLBACK_PROMPT copied into their "datasets" field instead of
paper-specific content — e.g. five different surveys (different countries,
different sample sizes, none of them time-boxed experiments) all show
"...across a 5-hour work session", which is the prompt's own example phrase,
not something that could coincidentally be true of five unrelated studies.
Same pattern, more blatant: one paper's dataset field is literally the
unfilled placeholder "...from N participants over [duration/condition]".

This is NOT caught by the dataset-mandatory backstop or citation validation —
those check "is there SOMETHING in the field," not "is what's there actually
about this paper." Scans every paper's dataset field for known leaked phrases
and flags them for re-extraction.

Run:
    python -m src.summarization.detect_prompt_leakage --config configs/config.yaml
"""
import argparse
import json
import re
from pathlib import Path

import yaml

# Phrases lifted directly from the extraction prompts' own illustrative
# examples — if these appear verbatim (or near-verbatim) in a paper's
# extracted fields, that's the model echoing the prompt, not reading the
# paper. Extend this list if you spot other leaked phrases on review.
KNOWN_LEAKED_PHRASES = [
    "5-hour work session",
    "N participants over [duration/condition]",
    "authors' own simulation data",  # another literal DATASET_FALLBACK_PROMPT example
    "device use dropped in the low-accessibility condition",  # EXTRACTION_SYSTEM_PROMPT's
    "total work/leisure time was unchanged",                  # own "results" field example —
                                                                 # same bug class, different field,
                                                                 # never checked until now
]

# A phrase can leak with the sample-size number swapped in ("367 participants
# across a 5-hour work session") — so match on the STABLE part of the phrase,
# not requiring the whole string to be identical.
_LEAK_PATTERNS = [re.compile(re.escape(p), re.IGNORECASE) for p in KNOWN_LEAKED_PHRASES]


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def scan_for_leakage(records: list[dict]) -> list[dict]:
    flagged = []
    for r in records:
        datasets = r.get("datasets", []) or []
        dataset_text = "; ".join(datasets) if isinstance(datasets, list) else str(datasets)
        results_text = r.get("results", "") or r.get("key_findings", "") or ""

        combined_text = f"{dataset_text} {results_text}"
        matches = [p for p, pattern in zip(KNOWN_LEAKED_PHRASES, _LEAK_PATTERNS)
                   if pattern.search(combined_text)]
        if matches:
            flagged.append({
                "paper_id": r.get("paper_id"), "title": r.get("title", ""),
                "datasets_field": dataset_text, "results_field": results_text,
                "leaked_phrases_found": matches,
            })

    return flagged


def run_scan(config: dict) -> None:
    processed_dir = Path(config["paths"]["processed_dir"])

    checked_any = False
    for filename in ["paper_summaries.json", "paper_deep_extractions.json"]:
        path = processed_dir / filename
        if not path.exists():
            continue
        checked_any = True
        records = json.loads(path.read_text(encoding="utf-8"))
        flagged = scan_for_leakage(records)

        print(f"\n{filename}: checked {len(records)} papers")
        if not flagged:
            print("  No prompt-leakage patterns found.")
            continue

        print(f"  {len(flagged)} paper(s) with suspected prompt-example leakage in their dataset field:")
        for f in flagged:
            print(f"\n    - {f['title'][:70]}")
            print(f"      leaked phrase(s): {f['leaked_phrases_found']}")
            print(f"      current datasets field: {f['datasets_field'][:120]}")

        out_path = processed_dir / f"prompt_leakage_flagged_{filename.replace('.json', '')}.json"
        out_path.write_text(json.dumps(flagged, indent=2), encoding="utf-8")
        print(f"\n  Saved {len(flagged)} flagged paper_id(s) to {out_path} — these need "
              f"re-extraction, not just a citation-validation pass.")

    if not checked_any:
        print("No paper_summaries.json or paper_deep_extractions.json found — run Stage 4 first.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_scan(cfg)