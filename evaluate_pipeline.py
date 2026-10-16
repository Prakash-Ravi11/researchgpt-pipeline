"""Evaluate saved ResearchIQ outputs; never rerun extraction or fit new clusters.

Install with .\\.venv\\Scripts\\python.exe -m pip install -r requirements-evaluation.txt
Run with .\\.venv\\Scripts\\python.exe -B evaluate_pipeline.py --run-dir
    .run/corpus50_final4_20261010 --resume
Use --prepare-only to validate inputs without model inference, or --paper-id ID
for a bounded smoke test. The default expected corpus size is 50.
Use --metrics faithfulness bertscore topic_separation for the cheaper source
checks, then --metrics context_precision --resume with the SAME model settings.
Context Precision requires one judge request per supplied passage and is slower.

Context Precision uses RAGAS's response-conditioned, reference-free variant on
the ordered passages actually supplied to extraction (including its word cap).
Faithfulness evaluates RETURNED quantitative results against independently
located source passages. ENTAILED / PROSE_GROUNDED results form a recovered
subset; this is a status-based cohort, not a measured before/after recovery rate.
BERTScore compares each result to its verified evidence sentence. It measures
similarity, not numeric correctness, entailment, recall, or independent gold
accuracy. Missing/failed metrics are null and excluded from means, with counts.
Silhouette evaluates existing cluster labels on normalized topic embeddings
(problem_addressed, falling back to summary), matching the pipeline topic basis.

Models run sequentially on CPU by default to avoid competing with Ollama VRAM.
The JSON report is the only output artifact and supports fingerprinted resume.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.request import urlopen

import numpy as np

RECOVERED_STATUSES = {"PROSE_GROUNDED", "ENTAILED"}
METRICS = ("context_precision", "faithfulness", "bertscore", "topic_separation")
RESPONSE_FIELDS = (
    "summary", "problem_addressed", "method", "datasets", "metrics", "results",
    "inferences", "novelty_claim", "limitations", "key_findings",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def extraction_contexts(paper_id, chunks_by_id, trace, max_words):
    """Reproduce retrieval_aware._assemble without retrieval or re-ranking."""
    if trace.get("mode") == "passthrough":
        selected = sorted(
            (c for c in chunks_by_id.values() if c["paper_id"] == paper_id),
            key=lambda c: c["chunk_index"],
        )
    else:
        ids = trace.get("selected_chunk_ids")
        if not ids or len(ids) != len(set(ids)):
            raise ValueError(f"{paper_id}: missing or duplicate selected chunk IDs")
        selected = []
        for cid in ids:
            chunk = chunks_by_id.get(cid)
            if chunk is None or chunk["paper_id"] != paper_id:
                raise ValueError(f"{paper_id}: selected chunk missing or belongs to another paper")
            selected.append(chunk)
    passages, used_ids, used = [], [], 0
    for chunk in selected:
        words = chunk["text"].split()[:max_words - used]
        if words:
            passages.append(" ".join(words))
            used_ids.append(chunk["chunk_id"])
            used += len(words)
        if used >= max_words:
            break
    return passages, used_ids


def locate_source(paper_id, evidence, chunks):
    """Validate offsets ourselves, rather than trust provenance_valid flags.

    Legacy EXPLICIT evidence uses enclosing block offsets; recovered prose uses
    exact sentence offsets. Check the appropriate contract for both schemas.
    """
    start, end = evidence.get("char_start"), evidence.get("char_end")
    span = evidence.get("evidence_span")
    if (not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or start < 0 or end <= start or not isinstance(span, str) or not span.strip()):
        raise ValueError("missing or invalid evidence offsets/span")
    if evidence.get("attribution") != "OWN_PAPER" or evidence.get("source") != "full_text":
        raise ValueError("quantitative result lacks full-text author ownership")
    exact = evidence.get("evidence_status") in RECOVERED_STATUSES
    for chunk in chunks:
        if (chunk["paper_id"] != paper_id
                or any(chunk.get(k) != evidence.get(k)
                       for k in ("block_id", "page_or_node", "source", "representation"))):
            continue
        cs, ce = chunk.get("char_start"), chunk.get("char_end")
        if not isinstance(cs, int) or not isinstance(ce, int):
            continue
        text = chunk["text"]
        if exact:
            valid = cs <= start < end <= ce and text[start - cs:end - cs] == span
        else:
            pos = text.find(span, max(0, start - cs))
            valid = pos >= 0 and start <= cs + pos < cs + pos + len(span) <= end
        if valid:
            return span, chunk["text"], chunk["chunk_id"]
    raise ValueError("evidence span/offsets do not match an indexed source passage")


def has_quantitative_value(value):
    """Honor metric-ID masking without treating formatted result lists as citations."""
    from src.evidence.anchors import NUMERIC_ANCHOR_RE
    from src.evidence.binder_v2 import _identifier_spans

    excluded = _identifier_spans(value)
    excluded += [m.span() for m in re.finditer(r"\[\s*\d+(?:\s*[,;-]\s*\d+)*\s*\]", value)]
    tokens = list(NUMERIC_ANCHOR_RE.finditer(value))
    tokens += list(re.finditer(r"(?<!\w)\d\s*%", value))
    return any(not re.fullmatch(r"(?:19|20)\d{2}", m.group())
               and not any(a <= m.start() and m.end() <= b for a, b in excluded) for m in tokens)


def prepare_corpus(processed_dir: Path, max_words=2500, expected_papers=50):

    summaries = read_json(processed_dir / "paper_summaries.json")
    chunks = read_json(processed_dir / "chunks.json")
    traces = read_json(processed_dir / "retrieval_selection.json")
    ids = [s["paper_id"] for s in summaries]
    if len(ids) != len(set(ids)) or (expected_papers and len(ids) != expected_papers):
        raise ValueError(f"Expected {expected_papers} unique papers; found {len(ids)}")
    chunks_by_id = {c["chunk_id"]: c for c in chunks}
    if len(chunks_by_id) != len(chunks) or set(ids) != {c["paper_id"] for c in chunks}:
        raise ValueError("Chunks contain duplicates or do not match the summary corpus")
    by_paper = defaultdict(list)
    for chunk in chunks:
        by_paper[chunk["paper_id"]].append(chunk)
    papers = []
    for summary in summaries:
        pid = summary["paper_id"]
        contexts, used_ids = extraction_contexts(pid, chunks_by_id, traces.get(pid, {}), max_words)
        text_hash = hashlib.sha256(" ".join(contexts).encode("utf-8")).hexdigest()[:16]
        if not summary.get("_text_hash") or summary["_text_hash"] != text_hash:
            raise ValueError(f"{pid}: reconstructed extraction context hash mismatch")
        if not isinstance(summary.get("evidence"), dict):
            raise ValueError(f"{pid}: missing gated evidence")
        response = json.dumps({k: summary[k] for k in RESPONSE_FIELDS if summary.get(k)}, ensure_ascii=False)
        question = (
            f"Extract the research problem, method, datasets, evaluation metrics, results, "
            f"findings, novelty, and limitations reported by the authors of {summary['title']}. "
            "Preserve reported quantitative values and their dataset and metric context."
        )
        claims = []
        for index, evidence in enumerate(summary["evidence"].get("results", [])):
            value = evidence.get("value")
            if evidence.get("final") != "RETURNED" or not isinstance(value, str) or not has_quantitative_value(value):
                continue
            claim = {
                "claim_id": f"{pid}:results:{index}", "value": value,
                "evidence_status": evidence.get("evidence_status"),
                "recovered": evidence.get("evidence_status") in RECOVERED_STATUSES,
                "faithfulness": None, "bertscore": None, "errors": {},
                "source": {k: evidence.get(k) for k in (
                    "block_id", "page_or_node", "char_start", "char_end", "attribution")},
            }
            try:
                reference, passage, cid = locate_source(pid, evidence, by_paper[pid])
                claim.update(reference=reference, source_context=passage, source_chunk_id=cid)
            except ValueError as exc:
                claim["errors"]["provenance"] = str(exc)
            claims.append(claim)
        papers.append({
            "paper_id": pid, "title": summary["title"], "cluster_id": summary.get("cluster_id"),
            "acquisition_status": summary.get("acquisition_status"),
            "user_input": question, "response": response,
            "retrieved_contexts": contexts, "used_chunk_ids": used_ids,
            "context_precision": None, "completed_ragas_metrics": [], "errors": {}, "claims": claims,
        })
    return summaries, papers


def calculate_topic_separation(summaries, embeddings, metric="euclidean"):
    """Silhouette [-1,1] for existing labels. Undefined configurations return null."""
    from sklearn.metrics import silhouette_score

    ids = [s["paper_id"] for s in summaries]
    labels = [s.get("cluster_id") for s in summaries]
    if len(set(ids)) != len(ids) or set(embeddings) != set(ids):
        raise ValueError("Topic embeddings must match paper IDs exactly")
    if any(label is None for label in labels):
        raise ValueError("Missing saved cluster assignments")
    counts = Counter(str(label) for label in labels)
    result = {"score": None, "metric": metric, "paper_count": len(ids),
              "cluster_sizes": dict(sorted(counts.items())), "reason": None}
    if not 2 <= len(counts) < len(ids):
        result["reason"] = "Silhouette requires 2 <= number of clusters < number of papers"
        return result
    matrix = np.stack([embeddings[pid] for pid in ids])
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("Invalid topic embeddings")
    if metric == "cosine" and np.any(np.linalg.norm(matrix, axis=1) == 0):
        raise ValueError("Cosine separation is undefined for zero vectors")
    result["score"] = float(silhouette_score(matrix, [str(x) for x in labels], metric=metric))
    return result


def ollama_finished(result):
    """RAGAS 0.2 doesn't recognize Ollama's done_reason; reject truncated output."""
    generations = [g for group in result.generations for g in group]
    return bool(generations) and all(
        (g.generation_info or {}).get("done_reason",
            getattr(g, "message", None).response_metadata.get("done_reason")
            if getattr(g, "message", None) is not None else None) == "stop"
        for g in generations
    )


def build_ragas_metrics(model, base_url, timeout):
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    from langchain_ollama import ChatOllama
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference
    from ragas.run_config import RunConfig

    config = RunConfig(timeout=timeout, max_retries=1, max_workers=1, seed=42)
    judge = ChatOllama(model=model, base_url=base_url, temperature=0, seed=42,
                       num_ctx=8192, num_predict=2048, client_kwargs={"timeout": timeout})
    llm = LangchainLLMWrapper(judge, run_config=config, is_finished_parser=ollama_finished)
    metrics = (LLMContextPrecisionWithoutReference(llm=llm), Faithfulness(llm=llm))
    for metric in metrics:
        metric.init(config)
    return metrics


async def score_ragas(paper, precision, faithfulness, timeout, metrics=("context_precision", "faithfulness")):
    from ragas import SingleTurnSample

    async def score(metric, response, contexts):
        value = float(await metric.single_turn_ascore(SingleTurnSample(
            user_input=paper["user_input"], response=response, retrieved_contexts=contexts), timeout=timeout))
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Evaluator returned an undefined or out-of-range score")
        return value

    if "context_precision" in metrics and "context_precision" not in paper["completed_ragas_metrics"]:
        try:
            if paper["response"] == "{}" or not paper["retrieved_contexts"]:
                raise ValueError("No response or extraction context to evaluate")
            paper["context_precision"] = await score(precision, paper["response"], paper["retrieved_contexts"])
        except Exception as exc:
            paper["errors"]["context_precision"] = f"{type(exc).__name__}: {exc}"
        paper["completed_ragas_metrics"].append("context_precision")
    if "faithfulness" in metrics and "faithfulness" not in paper["completed_ragas_metrics"]:
        for claim in paper["claims"]:
            if "provenance" in claim["errors"]:
                continue
            try:
                claim["faithfulness"] = await score(faithfulness, claim["value"], [claim["source_context"]])
            except Exception as exc:
                claim["errors"]["faithfulness"] = f"{type(exc).__name__}: {exc}"
        paper["completed_ragas_metrics"].append("faithfulness")


def score_bertscore(claims, scorer):
    """Keep candidate/reference direction and refuse silently truncated pairs."""
    from transformers import GPT2Tokenizer, RobertaTokenizer

    valid = []
    for claim in claims:
        if "provenance" in claim["errors"] or claim.get("bertscore") is not None:
            continue
        limit = min(scorer._tokenizer.model_max_length, 512)
        # Match BERTScore's own sent_encode handling of RoBERTa/GPT-2 prefixes.
        prefix = {"add_prefix_space": True} if isinstance(scorer._tokenizer, (GPT2Tokenizer, RobertaTokenizer)) else {}
        if any(len(scorer._tokenizer.encode(text.strip(), add_special_tokens=True, truncation=False, **prefix)) > limit
               for text in (claim["value"], claim["reference"])):
            claim["errors"]["bertscore"] = "Pair exceeds encoder token limit; no score computed"
            continue
        valid.append(claim)
    if valid:
        precision, recall, f1 = scorer.score([c["value"] for c in valid], [c["reference"] for c in valid])
        if any(len(scores) != len(valid) for scores in (precision, recall, f1)):
            raise ValueError("BERTScore returned a different number of scores than claims")
        for claim, p, r, f in zip(valid, precision, recall, f1):
            scores = {"precision": float(p), "recall": float(r), "f1": float(f)}
            if all(math.isfinite(v) for v in scores.values()):
                claim["bertscore"] = scores
                claim["errors"].pop("bertscore", None)
            else:
                claim["errors"]["bertscore"] = "Encoder returned a non-finite score"


def aggregate(papers):
    claims = [c for p in papers for c in p["claims"]]

    def mean(values):
        valid = [v for v in values if v is not None and math.isfinite(v)]
        return {"mean": sum(valid) / len(valid) if valid else None,
                "scored": len(valid), "eligible": len(values), "unscored": len(values) - len(valid)}

    def claim_metrics(items):
        return {"faithfulness": mean([c["faithfulness"] for c in items]),
                **{f"bertscore_{key}": mean([c["bertscore"][key] if c["bertscore"] else None for c in items])
                   for key in ("precision", "recall", "f1")}}

    return {
        "papers": len(papers), "papers_with_quantitative_results": sum(bool(p["claims"]) for p in papers),
        "quantitative_claims": len(claims), "recovered_quantitative_claims": sum(c["recovered"] for c in claims),
        "invalid_provenance_claims": sum("provenance" in c["errors"] for c in claims),
        "context_precision": mean([p["context_precision"] for p in papers]),
        "quantitative_results": claim_metrics(claims),
        "recovered_results": claim_metrics([c for c in claims if c["recovered"]]),
        "papers_without_quantitative_results": sum(not p["claims"] for p in papers),
    }


def save_report(path, report):
    report["aggregate"] = aggregate(report["papers"])
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True, help="Saved run containing config.yaml and processed/")
    parser.add_argument("--output", type=Path, help="Default: RUN_DIR/evaluation.json")
    parser.add_argument("--expected-papers", type=int, default=50)
    parser.add_argument("--judge-model", help="Default: saved run's Ollama model; choose another model for independence")
    parser.add_argument("--ollama-url", help="Default: saved run's llm.base_url")
    parser.add_argument("--bert-model", default="roberta-large", help="Hugging Face model ID or local path")
    parser.add_argument("--bert-layers", type=int, help="Required for custom/local BERTScore models")
    parser.add_argument("--device", default="cpu", help="Device for BERTScore and topic embeddings")
    parser.add_argument("--timeout", type=float, default=600, help="Seconds per RAGAS metric; bounded retries")
    parser.add_argument("--paper-id", action="append", help="Score only selected IDs; retain full corpus coverage in report")
    parser.add_argument("--metrics", nargs="+", choices=METRICS, default=list(METRICS),
                        help="Default: all four metrics; selection can be extended on resume")
    parser.add_argument("--prepare-only", action="store_true", help="Validate source/retrieval inputs without model inference")
    parser.add_argument("--resume", action="store_true", help="Reuse completed metrics only if inputs and settings match")
    args = parser.parse_args(argv)
    if args.expected_papers < 1 or args.timeout <= 0:
        parser.error("expected-papers and timeout must be positive")
    import yaml

    run_dir = args.run_dir.resolve()
    processed = run_dir / "processed"
    config_path = run_dir / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    max_words = int(config["llm"].get("max_context_words", 3000))
    if max_words < 1:
        raise ValueError("Invalid extraction word budget")
    summaries, papers = prepare_corpus(processed, max_words, args.expected_papers)
    selected = set(args.paper_id or [p["paper_id"] for p in papers])
    if not selected <= {p["paper_id"] for p in papers}:
        parser.error("--paper-id contains an ID outside this corpus")
    settings = {
        "judge_model": args.judge_model or config["llm"]["model"],
        "ollama_url": args.ollama_url or config["llm"]["base_url"],
        "bert_model": args.bert_model, "bert_layers": args.bert_layers, "device": args.device,
        "embedding_model": config["embedding"]["model"], "embedding_basis": "topic",
        "judge_is_extractor": (args.judge_model or config["llm"]["model"]) == config["llm"]["model"],
        "max_context_words": max_words, "timeout": args.timeout,
        "bertscore_idf": False, "bertscore_rescaled": False, "bertscore_fast_tokenizer": False,
    }
    inputs = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        config_path, processed / "paper_summaries.json", processed / "chunks.json",
        processed / "retrieval_selection.json", Path(__file__).resolve(),
    )}
    versions = {}
    for name in ("ragas", "bert-score", "langchain-ollama", "transformers", "torch", "sentence-transformers", "scikit-learn"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    fingerprint = hashlib.sha256(json.dumps([settings, inputs, versions], sort_keys=True).encode()).hexdigest()
    output = (args.output or run_dir / "evaluation.json").resolve()
    protected = {config_path, Path(__file__).resolve(), *processed.iterdir(),
                 *(run_dir / name for name in ("manifest.json", "verification.json", "pre_gate_summaries.json", "run.py"))}
    if output in protected:
        parser.error("Evaluation output must not overwrite pipeline inputs or artifacts")
    report = {"schema_version": 1, "fingerprint": fingerprint, "inputs_sha256": inputs,
              "settings": settings, "package_versions": versions, "python": sys.version.split()[0],
              "definitions": {"context_precision": "RAGAS LLMContextPrecisionWithoutReference; extraction-order passages",
                              "faithfulness": "RAGAS Faithfulness; validated indexed source passage per returned result",
                              "bertscore": "Result candidate vs exact evidence sentence reference; similarity, not entailment",
                              "clustering": "Existing assignments; topic embeddings; no cluster fitting",
                              "aggregation": "Macro means over successful scores; nulls excluded; denominators reported"},
              "papers": papers, "topic_separation": None, "status": "prepared", "requested_metrics": args.metrics}
    if args.resume and output.exists():
        previous = read_json(output)
        if previous.get("fingerprint") != fingerprint:
            raise ValueError("Resume report has different inputs, code, dependencies, or model settings")
        report["papers"] = previous["papers"]
        report["topic_separation"] = previous.get("topic_separation")
        if "bertscore_hash" in previous:
            report["bertscore_hash"] = previous["bertscore_hash"]
    save_report(output, report)
    if args.prepare_only:
        print(json.dumps(report["aggregate"], indent=2))
        return 0
    if any(versions[name] is None for name in ("ragas", "bert-score", "langchain-ollama")):
        raise RuntimeError("Install requirements-evaluation.txt with the project's .venv Python")
    requested_ragas = set(args.metrics) & {"context_precision", "faithfulness"}
    pending_ragas = any(p["paper_id"] in selected and requested_ragas - set(p["completed_ragas_metrics"])
                        for p in report["papers"])
    judge_name = settings["judge_model"]
    if pending_ragas:
        # Fail once if the local judge is unavailable instead of repeating 50 failures.
        with urlopen(settings["ollama_url"].rstrip("/") + "/api/tags", timeout=10) as response:
            tags = json.load(response)
        names = {model["name"] for model in tags["models"]}
        if judge_name not in names and judge_name + ":latest" not in names:
            raise RuntimeError(f"Ollama evaluator model is not available: {judge_name}")

    async def evaluate():
        precision, faithfulness = build_ragas_metrics(judge_name, settings["ollama_url"], args.timeout)
        for paper in report["papers"]:
            if paper["paper_id"] not in selected or not requested_ragas - set(paper["completed_ragas_metrics"]):
                continue
            await score_ragas(paper, precision, faithfulness, args.timeout, requested_ragas)
            save_report(output, report)
            if "context_precision" in requested_ragas or paper["claims"]:
                print(f"Scored {paper['paper_id']} (RAGAS: {', '.join(sorted(requested_ragas))})", flush=True)
    if pending_ragas:
        asyncio.run(evaluate())

    claims = [c for p in report["papers"] if p["paper_id"] in selected for c in p["claims"]]
    if "bertscore" in args.metrics and any(c["bertscore"] is None and "provenance" not in c["errors"] for c in claims):
        from bert_score import BERTScorer

        scorer = BERTScorer(model_type=args.bert_model, num_layers=args.bert_layers,
                            lang="en", device=args.device, batch_size=8,
                            idf=False, rescale_with_baseline=False, use_fast_tokenizer=False)
        score_bertscore(claims, scorer)
        report["bertscore_hash"] = scorer.hash
        del scorer
        save_report(output, report)
    if "topic_separation" in args.metrics and report["topic_separation"] is None:
        from src.summarization.summarize import embed_topic_texts

        embeddings = embed_topic_texts({s["paper_id"]: s for s in summaries}, settings["embedding_model"], args.device)
        report["topic_separation"] = {
            "basis": "problem_addressed_or_summary", "normalized_embeddings": True, "max_sequence_length": 384,
            "euclidean_silhouette": calculate_topic_separation(summaries, embeddings, "euclidean"),
            "cosine_silhouette": calculate_topic_separation(summaries, embeddings, "cosine"),
        }
    report["status"] = "complete" if len(selected) == len(papers) else "partial"
    if any(p["errors"] or any(c["errors"] for c in p["claims"]) for p in report["papers"]):
        report["status"] += "_with_errors"
    save_report(output, report)
    print(json.dumps({"aggregate": report["aggregate"], "topic_separation": report["topic_separation"],
                      "status": report["status"], "output": str(output)}, indent=2))
    return 2 if report["status"].endswith("with_errors") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
