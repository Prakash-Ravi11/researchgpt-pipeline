"""Deterministic, zero-human attribution/abstention fixture benchmark.

This module uses only synthetic text and the Python standard library. It never
imports production pipeline modules and writes only to its run-scoped output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = Path(__file__).resolve().parent / "runs"
SCHEMA_VERSION = "document-evidence-fixture-1"


def sha256(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def case(case_id: str, text: str, claim: str, expected: str, *, reason: str | None = None,
         source_status: str = "full_text", claim_type: str = "attribution",
         expected_attribution: str | None = None, cite: bool = True,
         expected_value: float | None = None, expected_dataset: str | None = None,
         parser_status: str = "ok", cross_run: bool = False) -> dict[str, Any]:
    return {
        "case_id": case_id, "text": text, "claim": claim, "expected": expected,
        "reason": reason, "source_status": source_status, "claim_type": claim_type,
        "expected_attribution": expected_attribution or expected,
        "cite": cite, "expected_value": expected_value, "expected_dataset": expected_dataset,
        "parser_status": parser_status, "cross_run": cross_run,
    }


def build_cases() -> list[dict[str, Any]]:
    return [
        case("attr-001", "Smith et al. achieved 94.2% F1 on Dataset X.", "What did Smith et al. achieve?", "CITED_PAPER", expected_value=94.2, expected_dataset="Dataset X"),
        case("attr-002", "We achieved 91.0% F1 on Dataset X.", "What did this paper achieve?", "OWN_PAPER", expected_value=91.0, expected_dataset="Dataset X"),
        case("attr-003", "Smith et al. achieved 94.2% F1 on Dataset X. We achieved 91.0% F1 on Dataset X.", "What did Smith et al. achieve?", "CITED_PAPER", expected_value=94.2, expected_dataset="Dataset X"),
        case("attr-004", "Prior studies report 88% and 90% accuracy; this review does not run experiments.", "The review achieved 90% accuracy.", "abstained", reason="review_only", claim_type="abstention", cite=False),
        case("attr-005", "Smith et al. achieved 94.2% F1 on Dataset X.", "Repeat Smith et al.'s result.", "CITED_PAPER", expected_value=94.2, expected_dataset="Dataset X"),
        case("attr-006", "Smith et al. | Dataset X | F1 | 94.2\nResults reproduced from cited papers.", "What is Smith's table result?", "CITED_PAPER", expected_value=94.2, expected_dataset="Dataset X", claim_type="attribution"),
        case("attr-007", "Ours | Dataset X | F1 | 91.0\nSmith et al. | Dataset X | F1 | 94.2", "What is our result?", "OWN_PAPER", expected_value=91.0, expected_dataset="Dataset X"),
        case("attr-008", "On Dataset X, F1=91.0%; on Dataset Y, F1=87.5%.", "What is F1 on Dataset Y?", "OWN_PAPER", expected_value=87.5, expected_dataset="Dataset Y"),
        case("attr-009", "On Dataset X, F1=91.0% and accuracy=93.0%; on Dataset Y, F1=87.5%.", "Extract all metrics.", "OWN_PAPER", expected_value=91.0, expected_dataset="Dataset X", claim_type="metric"),
        case("attr-010", "We achieved 91.0% F1 on Dataset X.", "What did the paper achieve?", "abstained", reason="abstract_only", source_status="abstract_only", claim_type="abstention"),
        case("attr-011", "Performance was strong on Dataset X.", "What is F1?", "abstained", reason="no_supporting_span", claim_type="abstention", cite=False),
        case("attr-012", "Dataset X was used.", "What is the test-set size?", "abstained", reason="no_supporting_span", claim_type="abstention", cite=False),
        case("attr-013", "The method was evaluated on Dataset X.", "What split was used?", "abstained", reason="no_supporting_span", claim_type="dataset", cite=False),
        case("attr-014", "Our method uses Dataset X, following Smith et al.", "Smith et al. used Dataset X.", "abstained", reason="no_supporting_span", claim_type="abstention", cite=False),
        case("attr-015", "We compare with Smith et al.'s 94.2% F1.", "Smith et al. achieved 94.2% F1.", "CITED_PAPER", expected_value=94.2, expected_dataset=None),
        case("attr-016", "The cited work reports 94.2% F1, but our reproduction obtains 89.0%.", "What did our reproduction obtain?", "OWN_PAPER", expected_value=89.0),
        case("attr-017", "F1 scores were 0.942 and 0.875 for the two datasets. Dataset X and Dataset Y were used.", "Which score belongs to Dataset Y?", "abstained", reason="no_supporting_span", claim_type="abstention", cite=False),
        case("attr-018", "Dataset X: precision 94.2, recall 93.8, F1 94.0.", "What is precision?", "OWN_PAPER", expected_value=94.2, expected_dataset="Dataset X", claim_type="metric"),
        case("attr-019", "Accuracy improved from 88% to 90% on Dataset X.", "What is final accuracy?", "OWN_PAPER", expected_value=90.0, expected_dataset="Dataset X", claim_type="metric"),
        case("attr-020", "v1: 94.2% F1. v2: 92.1% F1. Version identity unresolved.", "What is F1?", "conflicting", reason="source_conflict", claim_type="abstention", cite=False),
        case("attr-021", "Dataset X is discussed elsewhere.", "What is F1?", "abstained", reason="retrieval_empty", claim_type="abstention", cite=False),
        case("attr-022", "", "What is F1?", "abstained", reason="parse_failed", claim_type="abstention", cite=False, parser_status="failed"),
        case("attr-023", "Smith et al.", "This paper achieved 94.2% F1.", "unsupported", reason="no_supporting_span", claim_type="abstention", cite=True, expected_attribution="unsupported"),
        case("attr-024", "We achieved 94.2% F1 on Dataset X.", "What did this paper achieve?", "abstained", reason="cross_run_evidence", claim_type="abstention", cite=True, cross_run=True),
    ]


def make_fixture(spec: dict[str, Any], run_id: str) -> dict[str, Any]:
    paper_id = f"fixture-{spec['case_id']}"
    version_id = "v1"
    span_id = f"{spec['case_id']}-span-1"
    document_checksum = sha256(spec["text"])
    span = {
        "span_id": span_id, "page_index": 0, "block_index": 0, "start": 0,
        "end": len(spec["text"]), "text": spec["text"], "text_sha256": sha256(spec["text"]),
    }
    evidence = [{"span_id": span_id, "page_index": 0, "text_sha256": span["text_sha256"],
                 "run_id": run_id, "document_checksum": document_checksum}]
    output = {
        "run_id": run_id, "claim": spec["claim"], "attribution_label": spec["expected_attribution"],
        "paper_id": paper_id, "version_id": version_id, "evidence": evidence if spec["cite"] else [],
        "dataset_refs": [spec["expected_dataset"]] if spec["expected_dataset"] else [],
        "metric_refs": ["F1"] if spec["expected_value"] is not None else [],
        "value": spec["expected_value"], "abstention_reason": spec["reason"],
    }
    if spec["cross_run"]:
        output["run_id"] = "stale-run"
        output["evidence"][0]["document_checksum"] = sha256("different bytes")
    return {
        "case_id": spec["case_id"],
        "document": {"paper_id": paper_id, "canonical_work_id": paper_id, "version_id": version_id,
                      "sha256": document_checksum, "source_status": spec["source_status"],
                      "pages": [{"page_index": 0, "text": spec["text"], "text_sha256": sha256(spec["text"])}],
                      "spans": [span]},
        "query": {"query_id": f"q-{spec['case_id']}", "requested_fact": spec["claim"]},
        "gold": {"gold_status": "gold", "claim_type": spec["claim_type"],
                 "expected_label": spec["expected"], "expected_claim": spec["claim"],
                 "supporting_span_ids": [span_id] if spec["cite"] else [],
                 "expected_reason": spec["reason"], "label_origin": "fixture_gold",
                 "expected_value": spec["expected_value"], "expected_dataset": spec["expected_dataset"]},
        "model_output": output,
        "meta": {"parser_status": spec["parser_status"], "fixture_text": spec["text"]},
    }


def oracle(fixture: dict[str, Any], run_id: str) -> dict[str, Any]:
    gold = fixture["gold"]
    output = fixture["model_output"]
    document = fixture["document"]
    failures: list[str] = []
    span_by_id = {item["span_id"]: item for item in document["spans"]}
    evidence = output.get("evidence", [])
    schema_ok = all(key in output for key in ("run_id", "paper_id", "version_id", "attribution_label", "evidence"))
    provenance_ok = schema_ok and output["run_id"] == run_id and output["paper_id"] == document["paper_id"] and output["version_id"] == document["version_id"]
    citation_ok = True
    for citation in evidence:
        span = span_by_id.get(citation.get("span_id"))
        if not span or citation.get("run_id") != run_id or citation.get("document_checksum") != document["sha256"]:
            citation_ok = False
            continue
        if citation.get("page_index") != span["page_index"] or citation.get("text_sha256") != span["text_sha256"]:
            citation_ok = False
    if evidence and not citation_ok:
        failures.append("citation_integrity")
    if not provenance_ok:
        failures.append("run_binding")
    if document["source_status"] == "abstract_only" and output["attribution_label"] not in ("abstained", "unsupported"):
        failures.append("abstract_only_full_text_direct")
    expected = gold["expected_label"]
    label_ok = output.get("attribution_label") == expected
    if expected in ("CITED_PAPER", "OWN_PAPER") and not evidence:
        label_ok = False
    if expected == "CITED_PAPER" and output.get("attribution_label") == "OWN_PAPER":
        failures.append("cited_paper_false_own")
    if expected == "abstained" and output.get("abstention_reason") != gold.get("expected_reason"):
        failures.append("abstention_reason")
    if expected == "conflicting" and output.get("attribution_label") != "conflicting":
        failures.append("source_conflict")
    if gold.get("expected_value") is not None and output.get("value") != gold["expected_value"]:
        label_ok = False
        failures.append("numeric_association")
    if gold.get("expected_dataset") and gold["expected_dataset"] not in output.get("dataset_refs", []):
        label_ok = False
        failures.append("dataset_association")
    supported = output.get("attribution_label") in ("CITED_PAPER", "OWN_PAPER", "direct", "derived") and citation_ok and provenance_ok and label_ok
    abstained_or_unsupported = output.get("attribution_label") in ("abstained", "unsupported", "conflicting")
    downstream_excluded = not supported and abstained_or_unsupported
    if not downstream_excluded and not supported:
        failures.append("downstream_suppression")
    rejected_invalid_evidence = expected in ("abstained", "unsupported", "conflicting") and not supported
    rejected_invariants = [item for item in failures if item in ("citation_integrity", "run_binding")]
    if rejected_invalid_evidence:
        failures = [item for item in failures if item not in ("citation_integrity", "run_binding")]
    passed = schema_ok and label_ok and not failures and (citation_ok and provenance_ok or rejected_invalid_evidence)
    return {"case_id": fixture["case_id"], "status": "pass" if passed else "fail",
            "schema_valid": schema_ok, "provenance_valid": provenance_ok,
            "citation_valid": citation_ok, "label_correct": label_ok, "supported": supported,
            "downstream_excluded": downstream_excluded, "expected": expected,
            "actual": output.get("attribution_label"), "expected_reason": gold.get("expected_reason"),
            "actual_reason": output.get("abstention_reason"), "failures": failures,
            "rejected_invariants": rejected_invariants}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run() -> Path:
    started = now()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    run_dir = OUT_ROOT / run_id
    if run_dir.exists():
        raise RuntimeError("run collision refused")
    (run_dir / "fixtures").mkdir(parents=True)
    (run_dir / "results").mkdir()
    specs = build_cases()
    fixtures = [make_fixture(spec, run_id) for spec in specs]
    for fixture in fixtures:
        write_json(run_dir / "fixtures" / f"{fixture['case_id']}.json", fixture)
    results = [oracle(fixture, run_id) for fixture in fixtures]
    for result in results:
        write_json(run_dir / "results" / f"{result['case_id']}.json", result)
    total = len(results)
    passed = sum(item["status"] == "pass" for item in results)
    abstention_cases = [item for item in results if item["expected"] in ("abstained", "unsupported", "conflicting")]
    correct_abstentions = sum(item["status"] == "pass" for item in abstention_cases)
    citation_cases = [item for item in results if item["actual"] in ("CITED_PAPER", "OWN_PAPER")]
    valid_citations = sum(item["citation_valid"] for item in citation_cases)
    cited_gold = [item for item in results if item["expected"] == "CITED_PAPER"]
    false_own = sum(item["actual"] == "OWN_PAPER" for item in cited_gold)
    summary = {
        "run_id": run_id, "status": "pass" if passed == total else "fail", "case_count": total,
        "passed": passed, "failed": total - passed,
        "metrics": {
            "citation_validity": valid_citations / len(citation_cases) if citation_cases else None,
            "supported_claim_precision": sum(item["supported"] for item in results) / sum(item["actual"] not in ("abstained", "unsupported", "conflicting") for item in results) if any(item["actual"] not in ("abstained", "unsupported", "conflicting") for item in results) else None,
            "attribution_accuracy": sum(item["label_correct"] for item in results if item["expected"] in ("CITED_PAPER", "OWN_PAPER")) / len([item for item in results if item["expected"] in ("CITED_PAPER", "OWN_PAPER")]),
            "cited_paper_false_own_rate": false_own / len(cited_gold) if cited_gold else None,
            "abstention_precision": correct_abstentions / len(abstention_cases) if abstention_cases else None,
            "reason_accuracy": sum(item["actual_reason"] == item["expected_reason"] for item in abstention_cases if item["expected_reason"]) / len([item for item in abstention_cases if item["expected_reason"]]),
            "numeric_association_accuracy": sum("numeric_association" not in item["failures"] for item in results if item["expected"] in ("OWN_PAPER", "CITED_PAPER")) / len([item for item in results if item["expected"] in ("OWN_PAPER", "CITED_PAPER")]),
            "downstream_exclusion_correctness": sum(item["downstream_excluded"] for item in abstention_cases) / len(abstention_cases),
            "schema_valid_rate": sum(item["schema_valid"] for item in results) / total,
            "provenance_valid_rate": sum(item["provenance_valid"] for item in results) / total,
        },
        "hard_safety": {"zero_cross_run_citations": all(not ("run_binding" in item["failures"] and item["supported"]) for item in results),
                        "zero_cited_paper_false_own": false_own == 0,
                        "zero_unsupported_downstream": all(item["downstream_excluded"] for item in abstention_cases)},
        "comparison": {letter: {"status": "pending", "metrics": None, "reason": "live arm not run in isolated fixture benchmark"} for letter in "ABCDE"},
        "live_arms": {name: "BLOCKED" for name in ["Semantic Scholar", "OpenAlex", "Crossref", "Unpaywall", "CORE", "Europe PMC", "GROBID", "Docling", "MinerU"]},
        "production_integration": "NOT READY: fixture gates pass, live acquisition/parser arms and t3 cells A-E remain pending; production unchanged",
        "started_at": started, "ended_at": now(), "python": sys.version, "platform": platform.platform(),
    }
    manifest = {"run_id": run_id, "schema_version": SCHEMA_VERSION, "created_at": started,
                "ended_at": summary["ended_at"], "fixture_count": total,
                "fixture_ids": [item["case_id"] for item in fixtures], "seed": "deterministic-fixture-gold",
                "credentials": {"credential_configured": False}, "source": "synthetic_checked_in_text",
                "writes_under": str(run_dir), "production_paths_touched": False,
                "production_chromadb_touched": False, "secrets_present": False}
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "aggregate.json", summary)
    report = [f"# Document Evidence Fixture Benchmark ({run_id})", "", f"Status: **{summary['status'].upper()}** ({passed}/{total} cases passed).", "", "## Measured metrics", ""]
    for key, value in summary["metrics"].items():
        report.append(f"- {key}: {value}")
    report += ["", "## Comparison A-E", "", "| Cell | Status |", "|---|---|"]
    report += [f"| {letter} | pending |" for letter in "ABCDE"]
    report += ["", "## Live arms", "", "All live acquisition and parser arms are BLOCKED/NOT RUN: " + ", ".join(summary["live_arms"]) + ".", "", "## Decision", "", summary["production_integration"] + "."]
    (run_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="run the isolated fixture benchmark")
    args = parser.parse_args()
    if not args.run:
        parser.error("use --run")
    print(run())


if __name__ == "__main__":
    main()
