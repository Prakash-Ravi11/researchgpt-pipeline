"""Opt-in Prototype A extension with per-unit retries and hard document caps."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from . import PROMPT_VERSION, SCHEMA_VERSION, SOURCE_VERSION, SUPPORT_VERSION
from .inventory import inventory, initial_ledger, model_inventory
from .schema import cache_key, response_schema, claim_record
from .support import assess_claim, discourse, ambiguous_source
from .summary import quantitative_summary
from .selection import choose_record, SELECTION_VERSION

SYSTEM_PROMPT = """Extract separate, source-referenced quantitative outcome claims.
The source may cite external examples. Treat its numbers as reported claims,
not independently verified experiments. Preserve original-result versus cited-result
roles; only explicitly first-person trial statements establish original results.
Extract outcome changes, absolute resource savings and forecast performance.
Exclude deployment area/scale, citation numbers, downloads, image-processing volume,
market size and market-growth projections; account for them as outside_scope.
Use every supplied numeric occurrence ID exactly in candidate_accounting, as
associated, outside_scope, ambiguous, or unresolved. Distinct occurrences remain
distinct even if their number/citation is repeated. Do not hide missing outcomes
by classifying them outside scope. Ranges select both component IDs.
Select source sentence identifiers for each field, measurement, ownership bridge,
context, population, condition and role. Each identifier is a bounded source unit.
Never write quotation text. The host retrieves original words and regions.
Named entities, exact spans and paragraph presence do not independently prove a
relationship. Link a platform to the measurement through an explicit use/outcome
predicate, supported unique antecedent, continuation, or ordered respectively pairing.
Keep separate deployments separate within one paragraph. Join pages/blocks only
with supporting continuation. A local example cannot date/locate a later general
platform-user statistic. Unsupported optional context becomes null. If ownership
is ambiguous, omit the attributed claim and mark its occurrence ambiguous/unresolved.
Use concise platform names and snake_case outcomes. Scalar/range values, units,
qualifier, direction, negation, population and conditions must retain source meaning.
Currency savings per acre use USD_per_acre. Distinguish percent from percentage_points.
Preserve approximate, estimated, up_to, within, as_early_as, more_than, less_than;
use exact only for unqualified values. Never turn a range/bound/negation into a
measured exact outcome. Return a separate error-threshold claim and a connected
proportion claim, with the threshold candidate in conditions and explicit population.
For these forecast quantities, use forecast_lead_time, prediction_error_threshold,
and fields_within_prediction_error_threshold. Conditions specify kind=error_threshold
and operator=within. Absolute saved amounts use direction=savings; relative reductions
use decrease. Original first-person trials use original_result, even in an overview.
Do not infer joint technology use or study identity from repeated citations.
Respond only with the supplied JSON selection contract; no summary or quotations.

Field meanings: subject is the named technology/platform, never an outcome label.
outcome is the measured quantity/change label, never only a direction such as decrease.
location is a geographic place, excluding deployment area, technology or population.
population is a verbatim noun phrase (for example users or fields), not snake_case.
measurement references always include the sentence containing the selected number.
subject references include the sentence naming the platform; ownership_bridge adds
antecedent sentences for The system, The app, This translated or continuation.
Relative percent reductions use decrease, not savings. Absolute gallons/currency
saved use savings. Conditions remain [] except for explicitly stated thresholds/baselines.

Unrelated fictional example input:
document_id=fictional_example
s001: A trial of the fictional Nimbus fog collector in Lark Island in 2017 reduced cleaning costs by 17%.
n001=2017 (s001); n002=17% (s001).
Unrelated fictional example JSON output:
{"document_id":"fictional_example","claims":[{"candidate_ids":["n002"],
"subject":"Nimbus","outcome":"cleaning_cost_reduction","location":"Lark Island",
"year":2017,"population":null,"claim_role":"cited_result",
"measurement":{"kind":"scalar","value":17,"lower":null,"upper":null,
"unit":"percent","qualifier":"exact","direction":"decrease","negated":false,"conditions":[]},
"references":{"subject":["s001"],"measurement":["s001"],"ownership_bridge":[],
"context":["s001"],"population":[],"condition":[],"role":["s001"]}}],
"candidate_accounting":[{"candidate_id":"n001","state":"outside_scope","reason":"Contextual year, not an outcome."},
{"candidate_id":"n002","state":"associated","reason":"Cleaning-cost claim."}]}
Copy this JSON field structure for the current document, using its own source IDs,
platforms and quantities. This fictional example supplies no document answers.
"""


@dataclass(frozen=True)
class RepairConfig:
    enabled: bool = False
    max_document_requests: int = 3
    document_seconds: float = 240
    request_seconds: float = 180
    num_ctx: int = 8192
    num_predict: int = 4096
    temperature: float = 0.0
    seed: int = 42

    def __post_init__(self):
        if self.max_document_requests < 1 or self.document_seconds <= 0 or self.request_seconds <= 0:
            raise ValueError("Positive, bounded request/time budgets are required")


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_request(request, directory, wall_seconds):
    """One child/socket at a time; termination enforces the absolute host cap."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    request_path, response_path = directory / "request.json", directory / "response.json"
    write(request_path, request)
    command = [sys.executable, "-B", "-m", "src.evidence.prose_attribution.request_worker",
               "--request", str(request_path.resolve()), "--response", str(response_path.resolve())]
    start = time.perf_counter()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", cwd=Path(__file__).resolve().parents[3])
    hard_timeout = False
    try:
        stdout, stderr = process.communicate(timeout=wall_seconds)
    except subprocess.TimeoutExpired:
        hard_timeout = True
        process.kill()  # closes the worker's socket before another request starts
        stdout, stderr = process.communicate()
    result = json.loads(response_path.read_text(encoding="utf-8")) if response_path.is_file() else {"parsed": None}
    result.update(hard_timeout=hard_timeout, worker_exit_code=process.returncode,
                  host_elapsed_s=time.perf_counter() - start, stdout=stdout, stderr=stderr)
    completion = {}
    raw_path = directory / "raw_response.ndjson"
    if raw_path.is_file():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            try:
                part = json.loads(line)
                if part.get("done"):
                    completion = part
            except ValueError:
                pass
    result["completion"] = {key: completion.get(key) for key in
                            ("done_reason", "prompt_eval_count", "prompt_eval_cached_count", "eval_count", "total_duration", "eval_duration")}
    write(directory / "host_result.json", result)
    return result


def extract_document(source, llm_config, output_directory, config=RepairConfig(), *, request_executor=run_request):
    if not config.enabled:
        return {"status": "disabled", "accepted_claims": [], "requests": [], "production_fields_modified": False}
    if llm_config.get("provider", "ollama") != "ollama" or urlparse(llm_config["base_url"]).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("This prototype requires the explicitly configured local Ollama provider")
    started, deadline = time.perf_counter(), time.perf_counter() + config.document_seconds
    folder = Path(output_directory)
    folder.mkdir(parents=True, exist_ok=True)
    candidates = inventory(source)
    frames = discourse(source, candidates)
    schema = response_schema(source, candidates)
    write(folder / "source.json", source.as_dict())
    write(folder / "inventory.json", candidates)
    ledger = initial_ledger(candidates)
    by_id = {candidate["id"]: candidate for candidate in candidates}
    requests, records, retried_units, selection_decisions = [], {}, set(), []
    settings = {"temperature": config.temperature, "seed": config.seed, "num_ctx": config.num_ctx,
                "num_predict": config.num_predict, "top_k": 40, "top_p": 0.9, "repeat_penalty": 1.1,
                "request_seconds": config.request_seconds}
    cache = cache_key(source, {**llm_config, **settings}, schema)

    def execute(unit_id=None, unresolved_fields=None):
        remaining = deadline - time.perf_counter()
        if len(requests) >= config.max_document_requests or remaining <= 0:
            return False
        if unit_id is not None:
            if unit_id in retried_units:
                return False
            retried_units.add(unit_id)
        if unit_id is None:
            units, selected_candidates = source.model_units(), candidates
        else:
            selected_candidates = [candidate for candidate in candidates if candidate["sentence_id"] == unit_id]
            identifiers = {unit_id}
            for candidate in selected_candidates:
                identifiers.update(frames[candidate["id"]]["required_refs"])
                identifiers.update(frames[candidate["id"]]["context_ids"])
            # A missing named antecedent warrants the closest explicit source
            # unit(s), but no guessed ownership is supplied to the model.
            if len(identifiers) == 1:
                position = next(i for i, unit in enumerate(source.sentences) if unit["id"] == unit_id)
                identifiers.update(unit["id"] for unit in source.sentences[max(0, position - 2):position])
            units = [unit for unit in source.model_units() if unit["id"] in identifiers]
        content = {"document_id": source.document_id, "source_units": units,
                   "numeric_inventory": model_inventory(selected_candidates)}
        if unit_id is not None:
            content["context_resolution"] = {"evidence_unit": unit_id, "missing_relationships": unresolved_fields,
                                              "instruction": "Resolve these fields from this smallest retrieved context, or preserve ambiguity/null. This unit gets no further retry."}
        attempt = len(requests)
        request = {"document_id": source.document_id, "attempt": attempt, "prompt_version": PROMPT_VERSION,
                   "schema_version": SCHEMA_VERSION, "source_version": SOURCE_VERSION,
                   "base_url": llm_config["base_url"], "model": llm_config["model"],
                   "system_prompt": SYSTEM_PROMPT, "user_content": json.dumps(content, ensure_ascii=False),
                   "response_schema": response_schema(source, selected_candidates, unit_ids=[unit["id"] for unit in units]),
                   "settings": {**settings, "request_seconds": min(config.request_seconds, remaining)}}
        result = request_executor(request, folder / f"attempt_{attempt:02d}", min(config.request_seconds, remaining))
        requests.append({"attempt": attempt, "evidence_unit": unit_id, "retrieved_units": [unit["id"] for unit in units],
                         "missing_relationships": unresolved_fields, "elapsed_s": result.get("host_elapsed_s"),
                         "hard_timeout": result.get("hard_timeout"), "completion": result.get("completion", {})})
        parsed = result.get("parsed")
        if (not isinstance(parsed, dict) or parsed.get("document_id") != source.document_id
                or result.get("hard_timeout") or result.get("completion", {}).get("done_reason") != "stop"):
            requests[-1]["error"] = "invalid_document_response_or_incomplete_generation"
            return True
        attempt_records = []
        for index, proposed in enumerate(parsed.get("claims") or []):
            if not isinstance(proposed, dict):
                continue
            try:
                allowed_ids = {unit["id"] for unit in units}
                if any(ref not in allowed_ids for values in (proposed.get("references") or {}).values() for ref in values):
                    raise ValueError("Reference was not supplied in this attempt's bounded source context")
                record = assess_claim(source, candidates, frames, proposed, f"a{attempt}:c{index}")
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                record = claim_record(source.document_id, f"a{attempt}:c{index}", proposed)
                record.update(status="rejected", semantic_assessment={"status": "rejected", "reason": "Malformed proposed fields: " + str(error)})
            record["attempt"] = attempt
            attempt_records.append(record)
            identifiers = tuple(sorted(proposed.get("candidate_ids") or []))
            if identifiers:
                current = records.get(identifiers)
                # A retry can revise this numeric occurrence's proposed fields;
                # every prior attempt is retained separately, never overwritten.
                chosen, decision = choose_record(current, record)
                records[identifiers] = chosen
                if decision:
                    selection_decisions.append({"attempt": attempt, "candidate_ids": list(identifiers), **decision})
        accounting_seen = set()
        for item in parsed.get("candidate_accounting") or []:
            identifier = item.get("candidate_id") if isinstance(item, dict) else None
            if identifier not in by_id or identifier in accounting_seen:
                continue
            accounting_seen.add(identifier)
            entry = next(entry for entry in ledger if entry["candidate_id"] == identifier)
            entry["explicit_model_accounting"] = True
            if item.get("state") == "ambiguous" and (frames[identifier]["status"] == "unresolved" or ambiguous_source(source.sentence(by_id[identifier]["sentence_id"])["text"])):
                entry.update(state="ambiguous", reason=item.get("reason"))
            elif item.get("state") == "outside_scope" and by_id[identifier]["scope_reason"]:
                entry.update(state="outside_scope", reason=by_id[identifier]["scope_reason"])
            elif not by_id[identifier]["scope_reason"]:
                entry.update(state="unresolved", reason="Model proposal still needs a supported relationship.")
        write(folder / f"attempt_{attempt:02d}" / "assessed_claims.json", attempt_records)
        return True

    execute()
    while len(requests) < config.max_document_requests and time.perf_counter() < deadline:
        unresolved = {}
        accepted_ids = {identifier for record in records.values() if record["published"] for identifier in record["proposed"]["candidate_ids"]}
        for candidate in candidates:
            if candidate["scope_reason"] or candidate["id"] in accepted_ids:
                continue
            unit_id = candidate["sentence_id"]
            if unit_id in retried_units or ambiguous_source(source.sentence(unit_id)["text"]):
                continue
            if frames[candidate["id"]]["status"] == "unresolved" and ambiguous_source(source.raw_text):
                # The source itself explicitly withholds the missing identity;
                # another model pass cannot recover evidence that is absent.
                continue
            unresolved.setdefault(unit_id, []).append({"candidate_id": candidate["id"], "field": "core_ownership_or_measurement", "reason": frames[candidate["id"]]["reason"]})
        for record in records.values():
            if not record["published"]:
                continue
            candidate = by_id[record["proposed"]["candidate_ids"][0]]
            unit_id = candidate["sentence_id"]
            if unit_id in retried_units:
                continue
            fields = [field for field in ("location", "year") if record["field_support"][field]["status"] == "unresolved"]
            if fields:
                unresolved.setdefault(unit_id, []).append({"candidate_id": candidate["id"], "fields": fields, "reason": "Optional deployment context remains unresolved."})
        if not unresolved:
            break
        unit_id = max(unresolved, key=lambda identifier: len(unresolved[identifier]))
        if not execute(unit_id, unresolved[unit_id]):
            break
    accepted = [record for record in records.values() if record["published"]]
    for entry in ledger:
        linked = [record["claim_id"] for record in accepted if entry["candidate_id"] in record["proposed"]["candidate_ids"]
                  or any(condition.get("candidate_id") == entry["candidate_id"] for condition in record["measurement"].get("conditions", []))]
        context_candidate = by_id[entry["candidate_id"]]
        if context_candidate["kind"] == "context_year":
            linked += [record["claim_id"] for record in accepted if record.get("year") == context_candidate["value"]
                       and context_candidate["sentence_id"] in record["field_support"]["year"]["source_references"]]
        if linked:
            entry.update(state="associated", reason="Linked to supported claim/condition.", claim_ids=linked)
        elif not by_id[entry["candidate_id"]]["scope_reason"] and entry["state"] != "ambiguous":
            entry.update(state="unresolved", reason="No supported attributed claim after bounded context resolution.")
    result = {"status": "completed_with_unresolved" if any(entry["state"] in ("unresolved", "ambiguous") for entry in ledger) else "completed",
              "document_id": source.document_id, "versions": {"prompt": PROMPT_VERSION, "schema": SCHEMA_VERSION, "source": SOURCE_VERSION, "support": SUPPORT_VERSION, "selection": SELECTION_VERSION},
              "cache_key": cache, "cache_policy": "bypass", "accepted_claims": accepted,
              "unpublished_claims": [record for record in records.values() if not record["published"]],
              "candidate_ledger": ledger, "requests": requests, "retried_evidence_units": sorted(retried_units),
              "selection_decisions": selection_decisions,
              "elapsed_s": time.perf_counter() - started, "document_time_cap_s": config.document_seconds,
              "request_cap": config.max_document_requests, "summary": quantitative_summary(accepted),
              "accounting": {"total_candidates": len(ledger), "ledger_entries": len(ledger),
                             "explicit_model_entries": sum(entry["explicit_model_accounting"] for entry in ledger),
                             "unresolved_or_ambiguous": sum(entry["state"] in ("unresolved", "ambiguous") for entry in ledger)},
              "production_fields_modified": False}
    write(folder / "result.json", result)
    return result
