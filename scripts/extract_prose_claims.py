"""Explicit opt-in CLI for source-referenced prose claims; no catalog writes."""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evidence.prose_attribution.extractor import RepairConfig
from src.evidence.prose_attribution.deadline_guard import extract_bounded_document
from src.evidence.prose_attribution.source import SourceDocument


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", required=True,
                        help="JSON containing document_id, text, optional blocks and metadata.")
    parser.add_argument("--config", default=str(ROOT / "configs/config.yaml"))
    parser.add_argument("--repair-config", help="YAML with prose_attribution_repair.enabled: true; otherwise disabled.")
    parser.add_argument("--output", required=True, help="New output directory, separate from production records.")
    args = parser.parse_args()
    options = yaml.safe_load(Path(args.repair_config).read_text(encoding="utf-8")) if args.repair_config else {}
    values = (options or {}).get("prose_attribution_repair", {})
    names = {field.name for field in dataclasses.fields(RepairConfig)}
    config = RepairConfig(**{key: value for key, value in values.items() if key in names})
    if not config.enabled:
        print(json.dumps({"status": "disabled", "requests": 0, "production_fields_modified": False}))
        return
    folder = Path(args.output)
    if folder.exists():
        parser.error("--output must be a new directory so earlier attempts remain intact")
    data = json.loads(Path(args.source_json).read_text(encoding="utf-8"))
    source = SourceDocument.from_text(data["document_id"], data["text"],
                                      blocks=data.get("blocks"), metadata=data.get("metadata"))
    llm = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["llm"]
    result = extract_bounded_document(source, llm, folder, config)
    print(json.dumps({"status": result["status"], "accepted": len(result["accepted_claims"]),
                      "accounting": result["accounting"], "requests": len(result["requests"]),
                      "output": str(folder.resolve()), "production_fields_modified": False}))


if __name__ == "__main__":
    main()
