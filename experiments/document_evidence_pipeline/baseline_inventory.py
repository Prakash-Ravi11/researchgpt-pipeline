"""Read-only inventory of production corpus paths; never writes under data/."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def inventory(path: Path) -> dict[str, object]:
    files = [item for item in path.rglob("*") if item.is_file()] if path.exists() else []
    suffixes: dict[str, int] = {}
    for item in files:
        suffix = item.suffix.lower() or "<none>"
        suffixes[suffix] = suffixes.get(suffix, 0) + 1
    return {
        "path": str(path),
        "exists": path.exists(),
        "file_count": len(files),
        "byte_count": sum(item.stat().st_size for item in files),
        "suffix_counts": dict(sorted(suffixes.items())),
    }


def main() -> None:
    result = {
        "inventory_type": "read_only",
        "root": str(ROOT),
        "paths": {
            "data/raw_metadata": inventory(ROOT / "data" / "raw_metadata"),
            "data/processed": inventory(ROOT / "data" / "processed"),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
