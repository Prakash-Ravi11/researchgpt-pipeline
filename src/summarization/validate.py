"""
Validate & clean paper_summaries.json before Stage 5 depends on it.

Checks for and fixes:
  - Fields that came back as nested objects instead of the expected type
    (method/summary/problem_addressed/key_findings should be strings;
    datasets/metrics should be lists of strings) — this is the same issue
    that broke clustering, but the raw file was never repaired, only worked
    around at the point of use.
  - Records flagged _extraction_failed (empty fields from a failed LLM call).
  - Suspiciously empty/short summaries that succeeded technically but carry
    no real content.

Writes a cleaned copy back to paper_summaries.json (original backed up to
paper_summaries.backup.json) and prints a report of what was fixed/flagged,
so you know exactly what changed rather than trusting it silently.

Run:
    python -m src.summarization.validate --config configs/config.yaml
"""
import argparse
import json
import shutil
from pathlib import Path

import yaml

STRING_FIELDS = ["summary", "problem_addressed", "method", "key_findings"]
LIST_FIELDS = ["datasets", "metrics"]


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def stringify(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return "; ".join(stringify(v) for v in value)
    return str(value) if value is not None else ""


def listify(value) -> list[str]:
    if isinstance(value, list):
        return [stringify(v) for v in value]
    if isinstance(value, dict):
        return [f"{k.replace('_', ' ')}: {v}" for k, v in value.items()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def validate_and_clean(records: list[dict]) -> tuple[list[dict], dict]:
    report = {
        "total": len(records),
        "type_fixed": [],       # (paper_id, field, original_type)
        "extraction_failed": [],  # paper_id
        "empty_summary": [],     # paper_id, even if not flagged as failed
    }

    for r in records:
        if r.get("_extraction_failed"):
            report["extraction_failed"].append({"paper_id": r["paper_id"], "title": r["title"]})

        for field in STRING_FIELDS:
            original = r.get(field)
            if not isinstance(original, str):
                r[field] = stringify(original)
                report["type_fixed"].append({
                    "paper_id": r["paper_id"], "field": field,
                    "original_type": type(original).__name__,
                })

        for field in LIST_FIELDS:
            original = r.get(field)
            if not isinstance(original, list) or any(not isinstance(v, str) for v in original):
                r[field] = listify(original)
                report["type_fixed"].append({
                    "paper_id": r["paper_id"], "field": field,
                    "original_type": type(original).__name__,
                })

        summary = r.get("summary", "")
        if len(summary.strip()) < 20:  # essentially empty/useless
            report["empty_summary"].append({"paper_id": r["paper_id"], "title": r["title"]})

    return records, report


def print_report(report: dict) -> None:
    print(f"Checked {report['total']} papers.\n")

    if report["type_fixed"]:
        by_field = {}
        for item in report["type_fixed"]:
            by_field.setdefault(item["field"], []).append(item)
        print(f"Type issues fixed: {len(report['type_fixed'])} field(s) across "
              f"{len(set(i['paper_id'] for i in report['type_fixed']))} paper(s)")
        for field, items in by_field.items():
            print(f"  - {field}: {len(items)} record(s) were not the expected type "
                  f"(e.g. {items[0]['original_type']}) — coerced to text")
    else:
        print("No type issues found — all fields were the expected shape.")

    if report["extraction_failed"]:
        print(f"\n{len(report['extraction_failed'])} paper(s) had a failed LLM extraction "
              f"(empty fields) — these should be RE-RUN individually, not trusted as-is:")
        for item in report["extraction_failed"]:
            print(f"  - {item['title'][:80]}")

    if report["empty_summary"] and not report["extraction_failed"]:
        print(f"\n{len(report['empty_summary'])} paper(s) have a suspiciously short/empty "
              f"summary despite not being flagged as failed — worth a manual look:")
        for item in report["empty_summary"]:
            print(f"  - {item['title'][:80]}")

    if not report["extraction_failed"] and not report["empty_summary"]:
        print("\nNo failed or empty extractions — content-wise the dataset looks complete.")


def run_validation(config: dict) -> None:
    processed_dir = Path(config["paths"]["processed_dir"])
    path = processed_dir / "paper_summaries.json"
    backup_path = processed_dir / "paper_summaries.backup.json"

    records = json.loads(path.read_text(encoding="utf-8"))
    shutil.copy(path, backup_path)
    print(f"Backed up original to {backup_path}\n")

    cleaned, report = validate_and_clean(records)
    print_report(report)

    path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    print(f"\nWrote cleaned data back to {path}")


def find_weak_extractions(records: list[dict]) -> list[str]:
    """Identify papers whose extraction is empty/null-heavy even though the JSON
    parsed successfully — these passed the _extraction_failed check but carry no
    real content, so they need a genuine re-run, not just type-coercion."""
    weak = []
    for r in records:
        if r.get("_extraction_failed"):
            weak.append(r["paper_id"])
            continue
        # Count how many of the core content fields are empty after cleaning.
        empty_count = sum(1 for f in STRING_FIELDS if not r.get(f, "").strip())
        if empty_count >= 3:  # majority of fields empty = treat as a failed extraction
            weak.append(r["paper_id"])
    return weak


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--list-weak", action="store_true",
                         help="After cleaning, print paper_ids that need re-extraction (don't just report counts)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_validation(cfg)

    if args.list_weak:
        processed_dir = Path(cfg["paths"]["processed_dir"])
        records = json.loads((processed_dir / "paper_summaries.json").read_text(encoding="utf-8"))
        weak_ids = find_weak_extractions(records)
        print(f"\n{len(weak_ids)} paper(s) need re-extraction:")
        for pid in weak_ids:
            print(pid)
        (processed_dir / "weak_extractions.json").write_text(json.dumps(weak_ids, indent=2), encoding="utf-8")
        print(f"\nSaved list to {processed_dir / 'weak_extractions.json'}")