"""Render the measured comparison and its limitations from saved artifacts."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "v2"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def percentage(value):
    return f"{100*value:.1f}%" if value is not None else "N/A"


def main():
    metrics = read(RUN / "comparative_metrics.json")
    integrity = read(RUN / "integrity_verification.json")
    tests = read(RUN / "compatibility_results.json")
    manifest = read(RUN / "comparison_run_manifest.json")
    pilot = read(HERE / "comparison_run_manifest.json")
    fields = read(RUN / "field_status_counts.json")
    new_tests = sum(count for name, count in tests["test_modules"].items() if "test_prose_attribution" in name)
    lines = ["# Prototype A bounded attribution repair — 2026-10-14", "",
             "The opt-in extension and phased comparison are implemented, but the measured complete repair **does not meet the goal of a decisive prose-extraction improvement**. It removes observed unsupported context from accepted records and reconstructs exact quotes, while losing substantial outcome coverage and optional context. Keep the complete repair experimental; the data do not support production promotion.", "",
             "All 15 intended cases have saved outputs. The audit and quotation-only phase used no new inference. The eight synthetic cases were frozen before repair evaluation. There was no production corpus run, model replacement, or reference correction.", "",
             "## Phase 1: saved-output audit", "",
             "The audit was completed and reported before extraction changes. A had 9 nonverbatim quotations, 3 context-error records, and 4 missing target quantities; B had 15 nonverbatim quotations, 2 context-error records, 6 missing quantities and 3 malformed records. Conversion and normalization did not introduce the invalid quotation strings. The original A wrapper and B null-attribute problems were already repaired offline before baseline scoring; all originals and raw responses are preserved. No numeric normalization error was found; some per-acre currency unit fields were incomplete. These failures cannot be attributed solely to PDF layout corruption. See [PHASE1_AUDIT.md](PHASE1_AUDIT.md) and `phase1_audit.json`.", "",
             "## Phase 2: isolated quotation repair", "",
             "The saved A regression claims retain every nonquotation field. Unique exact/normalized-prefix mappings repair invented terminal punctuation and whitespace; ambiguous or paraphrased text stays an alignment failure. Invalid regression quotes fall from 9 to 0, complete semantic tuples remain 11/30, context-error records remain 3, and missing quantities remain 4. Grounded complete tuples rise only from 6 to 8. No inference occurs; the phase's host conversion took 0.0277 seconds. Later comparison conversion timings are recorded separately. This is evidence for alignment improvement, not ownership repair. See [PHASE2_QUOTATION_ONLY.md](PHASE2_QUOTATION_ONLY.md).", "",
             "## Primary comparison", "",
             "Complete tuple correctness uses the seven common fields plus preserved range/bound/direction/negation/condition meaning. Its precision denominator is emitted records; recall uses unique expected outcomes. Supported-outcome recall additionally requires an exact quotation and a source-supported ownership path, while optional location/year errors are counted separately. Fully grounded tuples require the complete tuple and support for every asserted optional field. Label equivalences affect only review views, never outputs or references. Exact string fixture scoring is also retained.", ""]
    for dataset, title in (("regression", "Seven regression passages; 30 repeated target occurrences"),
                           ("unseen", "Eight frozen synthetic passages; 17 target claims")):
        lines += [f"### {title}", "",
                  "| Metric | Unchanged baseline | Quotation only | Complete repair |",
                  "|---|---:|---:|---:|"]
        summaries = [metrics["datasets"][dataset][variant] for variant in ("baseline", "quotation_only", "complete")]
        counts = [summary["counts"] for summary in summaries]
        rows = [
            ("Emitted claims", [str(c["emitted"]) for c in counts]),
            ("Complete tuples / expected", [f'{c["complete_tuple_correct"]}/{c["expected"]}' for c in counts]),
            ("Complete tuple precision", [percentage(s["complete_tuple_correctness"]) for s in summaries]),
            ("Complete tuple recall", [percentage(s["complete_tuple_recall"]) for s in summaries]),
            ("Supported outcomes / expected", [f'{c["supported_outcome_recall_numerator"]}/{c["expected"]}' for c in counts]),
            ("Supported-outcome recall", [percentage(s["supported_outcome_recall"]) for s in summaries]),
            ("Fully grounded complete tuples", [str(c["fully_grounded_tuples"]) for c in counts]),
            ("Context-error records (fields)", [f'{c["context_error_records"]} ({c["context_error_fields"]})' for c in counts]),
            ("Invalid quotations", [str(c["invalid_quotations"]) for c in counts]),
            ("Missing target quantities", [str(c["missing_source_quantities"]) for c in counts]),
            ("Missing location/year fields", [str(c["missing_context_fields"]) for c in counts]),
            ("Emitted relationship-incomplete records", [str(c["relationship_incomplete_records"]) for c in counts]),
        ]
        lines += ["| " + name + " | " + " | ".join(values) + " |" for name, values in rows]
        lines += [""]
    lines += ["The complete repair accepts nine regression outcomes, all source-supported under this assistant review, but every accepted regression record lacks its supported location. Thus it has **zero complete regression tuples**, despite zero context errors. All seven Corteva/FieldView quantities remain unpublished. Order reversal changes the accepted core outcome from water reduction to pumping-cost reduction; neither the baseline nor complete repair is order invariant.", "",
              "On synthetic inputs, the repair gains explicit range preservation and the measured market-value result, and separates cited quotations correctly. It retains respectively pairing and abstains on the ambiguous-order case. It loses the second same-paragraph deployment, all compound forecast quantities, the crop-loss increase and negated water statement. Two accepted original-trial records have null roles despite explicit first-person source evidence. Baseline invents the range midpoint 12, drops forecast qualifiers, and does not represent the negated result as such. One baseline quote cannot be mapped uniquely/exactly by the conservative quotation-only repair and remains an explicit alignment failure.", "",
              "The shared-paragraph, continuation, bounds, conditions, projections, citations and ambiguity rules are implemented and covered by tests, but passing those synthetic contract tests does not show that this local model reliably follows the source-selection contract.", "",
              "### Frozen strict regression fixture", "",
              "| Variant | Exact fixture matches | Fixture recall |", "|---|---:|---:|"]
    for variant in ("baseline", "quotation_only", "complete"):
        strict = metrics["datasets"]["regression"][variant]["strict_frozen_fixture"]
        lines.append(f'| {variant} | {strict["counts"]["matched"]}/30 | {percentage(strict["fixture_recall"])} |')
    lines += ["", "Strict labels undercount semantic equivalences; the source-reviewed comparison above is separate and does not rewrite the frozen normalizer.", "",
              "## Candidate accounting and unresolved cost", "",
              "| Dataset | Native ledger | Explicit model accounting | Associated | Outside scope | Unresolved | Ambiguous | Unpublished final proposals |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for dataset in ("regression", "unseen"):
        c = metrics["datasets"][dataset]["complete"]["counts"]
        n = c["inventory_candidates"]
        lines.append(f'| {dataset} | {c["ledger_entries"]}/{n} | {c["explicit_model_entries"]}/{n} | {c.get("candidate_state_associated",0)} | {c.get("candidate_state_outside_scope",0)} | {c.get("candidate_state_unresolved",0)} | {c.get("candidate_state_ambiguous",0)} | {c["unpublished_proposals"]} |')
    lines += ["", "Associated entries include supported contextual years and condition dependencies, not just outcome claims. Every candidate has a ledger state, including silent omissions. Baseline/quotation-only have no native inventory/accounting; their missing target quantities are a post-hoc reference audit. Ledger completeness is not extraction recall. Both attempts and all intermediate proposals remain in each `attempt_*/assessed_claims.json`; final unpublished counts do not erase earlier failures.", "",
              "Final unpublished proposal verdicts (distinct from unresolved candidate states): " + "; ".join(dataset + " " + str(fields[dataset]["final_unpublished_statuses"]) for dataset in ("regression", "unseen")) + ". Field-level and all-attempt status counts are saved in `v2/field_status_counts.json`.", "",
              "## Execution interruption and budget result", "",
              "`u02_page_continuation` produced an incomplete response after **23,551.31 seconds**. Durable stream events stopped at 01:58:27 UTC and the worker returned at 08:30:10 UTC; the cause of the gap is not established. Its configured request/document caps were 180/240 seconds. The primary run retains this failure with zero accepted claims; no output was replaced and no extra retry was made after the expired document deadline. It is not a clean model latency measurement. The observed wall-clock cap did not hold for this invocation; `hard_timeout` was false. See `v2/runs/execution_interruption.json` and `v2/integrity_verification.json`.", "",
              "A separate fail-closed transport guard was added during the remaining cases and is used by the reusable CLI. It rejects late completed responses on resumption, preserves the pre-guard result and versions its cache fingerprint. It was **not imported by the frozen comparison** and made no new model requests. Its tests cover late-response rejection and disabled behavior. Host suspension prevents any application from executing deadline enforcement during the suspension; the guard records that limitation rather than promising an unobserved guarantee.", "",
              "For a paired sensitivity analysis only, remove the interrupted input from all three variants (14 expected claims). This is not a replacement primary score:", "",
              "| Variant | Complete tuples | Supported outcomes | Remaining extraction time |", "|---|---:|---:|---:|"]
    sensitivity = {}
    for variant in ("baseline", "quotation_only", "complete"):
        summary = metrics["datasets"]["unseen"][variant]
        chosen = [case for case in summary["cases"] if case["id"] != "u02_page_continuation"]
        c = collections.Counter()
        for case in chosen:
            c.update(case["counts"])
        seconds = sum(case["elapsed_s"] for case in summary["timing"]["cases"] if case["id"] != "u02_page_continuation")
        sensitivity[variant] = {"counts": dict(c), "elapsed_s": seconds}
        lines.append(f'| {variant} | {c["complete_tuple_recall_numerator"]}/{c["expected"]} | {c["supported_outcome_recall_numerator"]}/{c["expected"]} | {seconds:.2f} s |')
    lines += ["", "This paired subset gives the repair a small supported-outcome gain, while complete tuple recall still falls. It does not establish decisive improvement or remove the budget failure from the primary record.", "",
              "## Latency, requests and tokens", "",
              "| Dataset / variant | Elapsed | Requests | Context retries | Reported prompt tokens | Reported output tokens | Completions with counters |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for dataset in ("regression", "unseen"):
        for variant in ("baseline", "quotation_only", "complete"):
            t = metrics["datasets"][dataset][variant]["timing"]["totals"]
            lines.append(f'| {dataset} / {variant} | {t["elapsed_s"]:.2f} s | {t["requests"]} | {t["context_retries"]} | {t["prompt_tokens"]} | {t["output_tokens"]} | {t["completions_with_token_counters"]} |')
    lines += ["", "Quotation-only inherits baseline inference and adds only host conversion; it makes **zero new requests**. Regression baseline timing is historical from 2026-10-13. Unseen baseline/repair order alternates. Token sums contain only available Ollama completion counters; two regression repair attempts and the interrupted unseen request have missing counters, so repair totals are partial, not estimated full usage. Client caches are bypassed; server KV/prompt reuse is retained and recorded. One regression request was hard-cancelled at the remaining document budget. All completed documents other than the interrupted case stay within the configured cap plus recorded cleanup time. Document request counts never exceed three, and no evidence unit receives more than one context retry.", "",
              "### Protocol pilot and total experiment cost", "",
              f'The preserved v1 pilot completed three documents and cancelled a fourth in-flight request: {pilot.get("actual_model_request_count",10)} actual requests, plus its separate warmup. It was stopped because the model confused JSON field meanings; the v2 prompt added a complete unrelated fictional example. No reference scoring was used to turn those failed proposals into accepted claims. See the parent `comparison_run_manifest.json`, `runs/complete/`, and `frozen_repair/`. The v2 warmup took {manifest["warmup_seconds_excluded"]:.2f} seconds and is excluded from candidate totals.', ""]
    pilot_completions = []
    for path in (HERE / "runs/complete").glob("*/attempt_*/host_result.json"):
        pilot_completions.append(read(path).get("completion", {}))
    cost = {"pilot_actual_request_files": len(list((HERE / "runs/complete").glob("*/attempt_*/actual_request.json"))),
            "pilot_completed_token_counters": sum(item.get("eval_count") is not None for item in pilot_completions),
            "pilot_reported_prompt_tokens": sum(item.get("prompt_eval_count") or 0 for item in pilot_completions),
            "pilot_reported_output_tokens": sum(item.get("eval_count") or 0 for item in pilot_completions),
            "v2_complete_requests": integrity["counts"]["actual_complete_requests"],
            "v2_new_baseline_requests": 8, "v2_warmup_requests": 1, "pilot_warmup_requests": 1}
    cost["total_new_model_requests"] = cost["pilot_actual_request_files"] + 33 + 8 + 1 + 1
    lines += [f'Total new local model requests across pilot, both warmups, final repair and unseen baseline: **{cost["total_new_model_requests"]}**. The pilot has {cost["pilot_completed_token_counters"]} preserved completion counters ({cost["pilot_reported_prompt_tokens"]} reported prompt / {cost["pilot_reported_output_tokens"]} reported output tokens); cancelled/unavailable counters remain unknown. Historical baseline requests are reused, not charged again. Caps are per versioned document invocation; pilot and final invocation costs are both disclosed.', "",
              "## Integration and verification", "",
              "The source-ID path is opt-in, with disabled defaults and a separate experiment configuration. It retains raw/normalized views, character-to-original-word maps, stable numeric occurrences and explicit missing metadata. Geometry stays in the host; multi-line/page regions remain separate. The original PDF was not reparsed, so this does not demonstrate corpus-wide layout repair. Source spans and semantic verdicts remain separate; reconstructing a larger envelope does not license ownership. Unsupported optional fields stay null and unresolved core records remain unpublished.", "",
              f'**{tests["total_passed"]} distinct tests passed**: {new_tests} new source/support/retry/summary/table-view/deadline/cache contracts; 41 existing association regressions; 30 physical-PDF table-cell checks; 20 metric-schema checks; 19 binder-v2 checks. The main suite passed 135 checks, followed by three focused guard checks including one added cache contract (two repeats). They are compatibility and behavior tests, not model accuracy. Model inference and tests both used Python 3.10.18, with inference dependencies isolated in the original experiment environment and pytest in the repository environment. The physical PDFs are generated test artifacts, not a production corpus run.', "",
              f'Integrity checks preserve {integrity["frozen_baseline_files"]} frozen baseline/reference files, {integrity["unchanged_existing_source_files"]} existing source files and {integrity["unchanged_production_record_files"]} production JSON files. Both unseen fixture hashes, all frozen v2 source/output hashes, the prepared evaluator, and the model digest match. Actual HTTP payloads confirm temperature 0, seed 42, context 8192, output budget 4096 and the same local model. `git diff --check` passed. The wall-clock exception is recorded separately, so integrity passing is not reported as universal budget success.', "",
              "## Remaining limits and next engineering work", "",
              "The candidate is not production-ready. Coverage loss is dominated by wrong occurrence selections, dropped qualifiers/conditions, and overly conservative or label-sensitive host checks; optional deployment context is frequently omitted even when it exists. Improve the selection contract and context-field batching with new frozen versions, then evaluate again on additional independently reviewed passages. Do not fill missing context from this reference fixture or treat a larger exact quote as proof of a relationship. The synthetic set is assistant-authored and the semantic review is by the implementing assistant; neither establishes blind generalization or independent factual accuracy. No reference corrections were made.", "",
              "## Artifacts", "",
              "- [Implementation and explicit usage](IMPLEMENTATION.md); opt-in CLI: `scripts/extract_prose_claims.py`.",
              "- [Evaluation protocol](EVALUATION_PROTOCOL.md), `evaluation_only/final_source_reviews.json`, and frozen reference manifests.",
              "- [Detailed metrics](v2/comparative_metrics.json), [integrity verification](v2/integrity_verification.json), and [test results](v2/compatibility_results.json).",
              "- `v2/outputs/`: the six finalized model/conversion outputs; `v2/runs/`: source maps, inventories, ledgers, actual HTTP requests, raw streams and both attempts.",
              "- `frozen_baseline/`, `phase2_quotation_only/`, root pilot artifacts, and `v2/frozen_repair/` preserve each phase independently.",
              "- [Exact command record](COMMANDS.md).", ""]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (RUN / "sensitivity_and_costs.json").write_text(json.dumps({"paired_exclusion_case": "u02_page_continuation",
                                                              "sensitivity": sensitivity, "costs": cost}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
