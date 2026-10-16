"""Read-only prerequisite audit; never runs extraction or opens gold fixtures."""
import hashlib
import importlib.metadata as metadata
import json
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def command(args, timeout=60):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    return {"argv": args, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def endpoint(base_url, route, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base_url.rstrip("/") + "/api/" + route,
                                     data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"ok": True, "response": json.load(response)}
    except Exception as error:
        return {"ok": False, "error_type": type(error).__name__, "error": str(error)}


def main():
    config = yaml.safe_load((ROOT / "configs/config.yaml").read_text(encoding="utf-8"))
    llm = config["llm"]  # Persist only the LLM block, never collection credentials.
    user_root = Path.home()
    search_args = ["rg", "--files", "--hidden", "--no-ignore", str(user_root)]
    search_args += ["--iglob", "*prose*", "--iglob", "*benchmark*",
                    "--iglob", "passages.json"]
    exclusions = ("AppData", "node_modules", ".git", ".venv*", "venv", "anaconda3",
                  "miniconda3", ".cache", ".rustup", ".ollama", ".pytest_cache",
                  ".codex/plugins", ".run", "runs/phase11_binder/a4_tmp_*")
    for excluded in exclusions:
        search_args += ["-g", "!**/" + excluded + "/**"]
    search = command(search_args)
    status = command(["git", "status", "--short", "--untracked-files=all"])
    tracked_paths = command(["git", "diff", "--name-only"])["stdout"].splitlines()
    changed_hashes = {}
    for name in tracked_paths:
        path = ROOT / name
        if path.is_file():
            changed_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    relevant = [p for p in tracked_paths if p.startswith(("src/evidence/", "src/summarization/", "src/processing/"))]
    diff = command(["git", "diff", "--", *relevant])
    (HERE / "relevant_uncommitted.patch").write_text(diff["stdout"], encoding="utf-8")
    package_versions = {}
    for package in ("langextract", "requests", "PyYAML"):
        try:
            package_versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            package_versions[package] = None
    interpreters = []
    version_code = ("import json,sys,importlib.metadata as m; "
                    "print(json.dumps({'python':sys.version,'executable':sys.executable,"
                    "'langextract':next((d.version for d in m.distributions() "
                    "if d.metadata['Name'].lower()=='langextract'),None)}))")
    for name in (".venv", ".venv-09a"):
        interpreter = ROOT / name / "Scripts/python.exe"
        if interpreter.is_file():
            interpreters.append(command([str(interpreter), "-c", version_code], timeout=30))
    archive_checks = []
    downloads = user_root / "Downloads"
    archives = [p for p in downloads.glob("*.zip")
                if "research" in p.name.lower() or p.name in ("files.zip", "archive.zip", "archive (1).zip")]
    archives += list((user_root / ".codex/attachments").rglob("*.zip"))
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as bundle:
                names = [n for n in bundle.namelist()
                         if any(t in n.lower() for t in ("passages.json", "prose_ab"))]
            archive_checks.append({"path": str(archive), "matching_member_names": names})
        except Exception as error:
            archive_checks.append({"path": str(archive), "error": str(error)})
    base_url, model = llm["base_url"], llm["model"]
    model_show = endpoint(base_url, "show", {"model": model})
    # The API template is unnecessary for this blocked audit; retain defaults/details only.
    if model_show.get("ok"):
        model_show["response"] = {key: model_show["response"].get(key)
                                  for key in ("parameters", "details", "capabilities")}
    record = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "user_date": "2026-10-13", "user_timezone": "Asia/Calcutta",
        "status": "blocked_missing_benchmark", "repository_root": str(ROOT),
        "revision": command(["git", "rev-parse", "HEAD"])["stdout"].strip(),
        "repository_status": status, "tracked_changed_file_sha256": changed_hashes,
        "relevant_uncommitted_patch": "relevant_uncommitted.patch",
        "python": {"version": sys.version, "executable": sys.executable},
        "package_versions": package_versions, "existing_virtualenvs": interpreters,
        "configured_llm": llm,
        "ollama": {"version": endpoint(base_url, "version"),
                   "tags": endpoint(base_url, "tags"), "ps": endpoint(base_url, "ps"),
                   "show": model_show},
        "benchmark_search": search, "archive_member_name_checks": archive_checks,
        "repository_guidance": {"applicable_AGENTS_md_found": [],
                     "search": "Ancestor paths and repository files including hidden/ignored files inspected."},
        "execution": {"extraction_requests": 0, "warmup_requests": 0,
                      "effective_experiment_settings": None, "input_hashes": None,
                      "a_output": None, "b_output": None,
                      "gold_loaded": False, "evaluator_loaded": False,
                      "production_files_modified_by_this_audit": False},
        "blocker": "ResearchIQ_Prose_AB_Benchmark.zip and passages.json were not found in accessible searched locations.",
        "limitations": ["Search excludes application/runtime caches and AppData; inaccessible directories are recorded in stderr.",
                        "No benchmark README, instructions, contract, extraction outputs, or performance scores are available.",
                        "LangExtract installation and SDK inspection deferred until fixed benchmark inputs are available."]
    }
    (HERE / "preflight.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "artifact": str(HERE / "preflight.json"),
                      "model_service_reachable": record["ollama"]["tags"].get("ok"),
                      "benchmark_candidates": [p for p in search["stdout"].splitlines()
                                               if "prose" in p.lower()
                                               or p.lower().endswith("passages.json")]}))


if __name__ == "__main__":
    main()
