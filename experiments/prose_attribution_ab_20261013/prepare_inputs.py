"""Copy fixed non-evaluation material and verify source hashes."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    source = parser.parse_args().benchmark.resolve()
    (HERE / "benchmark").mkdir(exist_ok=True)
    (HERE / "model_inputs").mkdir(exist_ok=True)
    for name in ("README.md", "instructions.txt", "passages.json"):
        shutil.copy2(source / name, HERE / "benchmark" / name)
    data = json.loads((source / "passages.json").read_text(encoding="utf-8"))
    manifest = []
    for case in data["cases"]:
        digest = hashlib.sha256(case["text"].encode("utf-8")).hexdigest()
        assert digest == case["sha256"], case["id"]
        (HERE / "model_inputs" / (case["id"] + ".json")).write_text(
            json.dumps({"id": case["id"], "text": case["text"]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        manifest.append({"id": case["id"], "sha256": digest, "characters": len(case["text"])})
    shutil.copy2(source / "instructions.txt", HERE / "model_inputs/instructions.txt")
    (HERE / "input_manifest.json").write_text(json.dumps({
        "provided_material": "already extracted directory; original ZIP not supplied",
        "source_directory": str(source), "case_count": len(manifest), "cases": manifest}, indent=2), encoding="utf-8")
    print("Verified and assembled", len(manifest), "fixed inputs; no evaluation material accessed.")


if __name__ == "__main__":
    main()
