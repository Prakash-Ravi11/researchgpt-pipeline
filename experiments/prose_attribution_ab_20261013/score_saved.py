"""Run the supplied scorer/tests only after verifying final output fingerprints."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    finalized = json.loads((HERE / "conversion_finalized.json").read_text(encoding="utf-8"))
    for name, expected in {**finalized["output_sha256"], **finalized["frozen_sha256"]}.items():
        assert sha(HERE / name) == expected, name
    source = Path(json.loads((HERE / "input_manifest.json").read_text(encoding="utf-8"))["source_directory"])
    evaluation = HERE / "evaluation"
    (evaluation / "evaluation_only").mkdir(parents=True, exist_ok=True)
    for name in ("evaluate.py", "test_evaluate.py", "passages.json"):
        shutil.copy2(source / name, evaluation / name)
    # First evaluation fixture access is after both finalized outputs/hash checks.
    shutil.copy2(source / "evaluation_only/gold.json", evaluation / "evaluation_only/gold.json")
    commands = []
    for candidate in ("a", "b"):
        args = [sys.executable, "-B", str(evaluation / "evaluate.py"),
                "--output", str(HERE / (candidate + "_output.json")),
                "--report", str(HERE / (candidate + "_scores.json"))]
        result = subprocess.run(args, cwd=evaluation, capture_output=True, text=True,
                                encoding="utf-8", timeout=60)
        commands.append({"argv": args, "cwd": str(evaluation), "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
    args = [sys.executable, "-B", "-m", "unittest", "test_evaluate.py", "-v"]
    result = subprocess.run(args, cwd=evaluation, capture_output=True, text=True,
                            encoding="utf-8", timeout=60)
    commands.append({"argv": args, "cwd": str(evaluation), "returncode": result.returncode,
                     "stdout": result.stdout, "stderr": result.stderr})
    write = {"status": "scored_saved_outputs", "output_sha256_verified": finalized["output_sha256"],
             "fixture_sha256": sha(evaluation / "evaluation_only/gold.json"),
             "evaluator_sha256": sha(evaluation / "evaluate.py"), "commands": commands}
    (HERE / "scoring_execution.json").write_text(json.dumps(write, indent=2) + "\n", encoding="utf-8")
    for entry in commands:
        print(entry["stdout"])
        print(entry["stderr"])
    assert all(entry["returncode"] == 0 for entry in commands), "Scoring/test command failed; see scoring_execution.json"


if __name__ == "__main__":
    main()
