"""
Stage 4 — Summarization & Categorization.

Two independent steps:
  1. Per-paper structured extraction via a local Ollama LLM (summary, problem,
     method, datasets, metrics, key findings) — JSON-constrained output.
  2. Categorization via KMeans clustering over paper-level embeddings (mean of
     that paper's chunk embeddings from Stage 3) — NOT via LLM per paper. This
     keeps categories consistent across the corpus instead of the LLM
     inventing slightly different labels for similar papers. The LLM is only
     called once more, to name each cluster from its exemplar papers.

Speed notes (added after the first full-corpus run):
  - num_ctx is now sized dynamically per paper instead of a fixed 8192.
    Abstract-only papers (the majority of most corpora) are a few hundred
    words — forcing an 8192-token context window on them wastes VRAM
    headroom and adds unnecessary allocation overhead on a 6GB card. Full-text
    papers still get up to 8192 when they actually need it.
  - Extractions are now cached persistently by paper_id across runs
    (data/processed/extraction_cache.json). If the same paper shows up again
    in a future overlapping search, it's read from cache instead of
    re-running the LLM call — the main lever for repeated/incremental runs,
    not a single one-off corpus.

Run standalone for testing:
    python -m src.summarization.summarize --config configs/config.yaml
"""
import argparse
import hashlib
import json
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests
import yaml
from tqdm import tqdm

EXTRACTION_SYSTEM_PROMPT = """You are extracting structured information from an academic paper for a literature review, \
at the depth a PhD-level researcher would expect and cite directly in their own writing — not a one-line gloss. \
Every field below should be specific enough that someone could understand this paper's actual content without \
reading the source, not just a category label. \
Given the paper text below, respond with ONLY a JSON object with these exact keys:
- "summary": 3-4 sentences covering what the paper does, how, and what it found — enough to stand alone
- "problem_addressed": 3-4 sentences on the SPECIFIC problem, limitation, gap, or open question in prior work this paper targets — name what came before and what was missing, not just the general topic area
- "method": 4-6 sentences on the actual technical or experimental approach — architecture/algorithm steps for computational work, OR study design/conditions/procedure for empirical or behavioral research (sample, conditions, what participants/subjects did, how long, what was controlled for). Be concrete about the mechanics, not just the technique name.
- "results": the concrete outcomes reported — actual numbers, benchmark scores, or statistically/behaviorally described findings (e.g. "device use dropped in the low-accessibility condition, but total work/leisure time was unchanged") where stated. Empty string only if the paper reports no concrete outcome at all.
- "inferences": 3-4 sentences on what the AUTHORS THEMSELVES conclude, argue, or interpret their results to mean — their discussion/argument, distinct from the raw outcome in "results"
- "novelty_claim": what the paper itself claims is new — its core contribution, framed in the authors' own words/argument, not a generic restatement
- "limitations": limitations the authors explicitly state, or that are clearly evident from the method (sample size, generalizability, missing controls, etc.) — write "Not stated" only if genuinely none are discussable
- "datasets": list of the data this paper's findings are actually based on. This is MANDATORY — virtually every empirical paper, computational or behavioral, has SOME underlying data, even if it has no formal benchmark name:
  * Named public benchmarks (e.g. "ImageNet", "FeTA") — use the name as given
  * Self-collected/experimental data with no formal name — DESCRIBE it concretely using THIS paper's own actual details (sample size, population, and duration/condition IF the paper states one). Do not invent a duration or session length if the paper doesn't specify one — write "duration not stated" instead. Vary your phrasing paper to paper; if you notice yourself writing the same duration or session description across different papers, that is a signal you are copying a pattern rather than reading this specific paper's actual method — go back and check.
  * Survey, interview, or observational data — describe the source and scale, e.g. "survey responses from 200 university students"
  Only return an empty list if this is a purely theoretical, conceptual, or literature-review paper with no underlying empirical data of any kind — that should be rare.
- "metrics": list of what was measured or evaluated — formal metrics (e.g. "Dice score", "accuracy") for computational work, OR the behavioral/outcome measures for empirical work (e.g. "device pickup frequency", "self-reported distraction", "time-on-task"). Empty list only if truly nothing was measured/compared.
- "key_findings": 2-3 sentence headline takeaway — the single most important, specific result or claim, written so it could stand alone as a citation-worthy sentence

Respond with ONLY the JSON object, no other text."""

# Focused fallback prompt used ONLY when the main extraction above still comes back
# with an empty datasets list — narrows the model's attention to just this one
# question instead of re-running the full extraction, and pushes harder against
# giving up with an empty answer. Broadened to explicitly cover empirical/
# behavioral studies, not just ML papers with named benchmarks — a study's own
# collected participant/experimental data counts as its dataset.
DATASET_FALLBACK_PROMPT = """You are extracting the dataset(s) or underlying data this paper's findings are based \
on. This is MANDATORY — virtually every empirical paper (computational, behavioral, clinical, or observational) has \
SOME underlying data, even with no formal benchmark name. Search the methodology, participants/sample, procedure, \
and results sections carefully — a dataset mention is sometimes a single sentence, a table caption, or embedded in \
the description of who/what was studied. \
Respond with ONLY a JSON object: {"datasets": ["description1", "description2"]}. \
If there is no formally named benchmark, DESCRIBE what was actually used instead, based on THIS paper's actual \
text — never copy a placeholder or template format verbatim (e.g. never output literal bracket placeholders like \
"[duration/condition]" — if you don't know a specific value, omit it rather than leaving a bracket in your answer). \
Ground your answer in the specific population, sample size, and context this particular paper describes. If the \
paper genuinely doesn't state a duration or session length, don't invent one — omit that detail rather than guessing. \
Only return an empty list if you are genuinely confident, after careful reading, that this is a purely theoretical, \
conceptual, or pure literature-review paper with no underlying empirical data at all — that should be rare."""

CLUSTER_NAMING_PROMPT_METHOD = """You are naming a thematic cluster of academic papers for a literature review's category table. \
All papers in this corpus already share the same broad domain — do NOT describe that shared domain in your label \
(e.g. avoid generic labels like "Medical Image Segmentation" or "Domain Generalization"). Instead, identify the \
SPECIFIC technique or approach that distinguishes THIS cluster from the others — e.g. data augmentation, \
disentanglement, meta-learning, adversarial training, test-time adaptation, style transfer, self-supervision, etc. \
Given the titles and methods of papers in this cluster, respond with ONLY a JSON object:
{"label": "3-6 word category name naming the SPECIFIC technique", "description": "one sentence on what technically unites these papers"}"""

# Used when method-text clustering comes back with low silhouette separation —
# a sign most papers in the corpus share the same data-collection method (e.g.
# an entire survey-based behavioral literature), so there's no real
# methodological diversity to name. Naming by topic/outcome instead of
# technique matches what's actually differentiating the papers in that case.
CLUSTER_NAMING_PROMPT_TOPIC = """You are naming a thematic cluster of academic papers for a literature review's category table. \
All papers in this corpus already share the same broad domain and likely use similar data-collection methods (e.g. \
surveys or self-report questionnaires) — do NOT name clusters after that shared method. Instead, identify the \
SPECIFIC research TOPIC, POPULATION, or OUTCOME that distinguishes THIS cluster from the others — e.g. driving \
safety, sleep quality, academic performance, reproductive health, cyberbullying, mental health, workplace \
productivity, etc. Given the titles and problem statements of papers in this cluster, respond with ONLY a JSON object:
{"label": "3-6 word category name naming the SPECIFIC topic/outcome", "description": "one sentence on what topically unites these papers"}"""

# Cluster-naming prompts are short (titles + method/problem fields for ~6 exemplars) —
# no paper needs anywhere near 8192 tokens of context for this call.
CLUSTER_NAMING_NUM_CTX = 2048

# Below this silhouette score, method-based clustering is treated as having
# failed to find real structure (not just "imperfect") — triggers automatic
# fallback to topic-based clustering. 0.15 sits at the low end of "weak
# separation"; below it, clusters are closer to an arbitrary split than a
# genuine grouping.
LOW_DIVERSITY_SILHOUETTE_THRESHOLD = 0.15

# --- Deterministic dataset-mention backstop (added after faculty flagged that
# LLM-only dataset extraction can silently miss a real mention) ---
#
# Widely-used dataset names across the domains this pipeline has been run on
# so far (CV/medical imaging/NLP). Not exhaustive by design — this is a
# backstop that catches KNOWN names reliably, combined with a phrase-pattern
# scanner below that catches names not on this list. Extend this list as you
# encounter more domains.
KNOWN_DATASET_NAMES = [
    # medical imaging
    "FeTA", "BraTS", "ISIC", "CheXpert", "ChestX-ray14", "ACDC", "M&Ms", "ATLAS",
    "LIDC-IDRI", "MSD", "Medical Segmentation Decathlon", "MRBrainS", "OASIS",
    "ADNI", "CAMUS", "Kvasir", "PROMISE12", "WMH", "ISLES", "COVID-19-CT",
    # general CV
    "ImageNet", "COCO", "MS-COCO", "CIFAR-10", "CIFAR-100", "MNIST", "Fashion-MNIST",
    "PASCAL VOC", "Cityscapes", "KITTI", "nuScenes", "ADE20K", "Open Images",
    "CelebA", "LFW", "Places365", "SUN397", "Visual Genome",
    # NLP
    "SQuAD", "GLUE", "SuperGLUE", "IMDB", "SST-2", "CoNLL", "WMT", "MNLI",
    "CommonCrawl", "WikiText", "BookCorpus", "MS MARCO",
]

# Phrase patterns that typically precede or follow a dataset name in academic
# writing — catches names NOT on the curated list above. Captures a
# capitalized token/acronym adjacent to a dataset-indicating word.
_DATASET_PHRASE_PATTERNS = [
    re.compile(r"\bon\s+the\s+([A-Z][A-Za-z0-9\-]{1,24})\s+(?:dataset|benchmark|corpus)\b"),
    re.compile(r"\b([A-Z][A-Za-z0-9\-]{1,24})\s+(?:dataset|benchmark|corpus)\b"),
    re.compile(r"\b(?:evaluated|trained|tested)\s+on\s+(?:the\s+)?([A-Z][A-Za-z0-9\-]{1,24})\b"),
]

# Common capitalized words that match the pattern shape but are never dataset
# names — filters out false positives like "The Results dataset" style noise.
_DATASET_STOPWORDS = {
    "The", "This", "Our", "These", "Both", "Each", "All", "Some", "Such",
    "Table", "Figure", "Section", "Results", "Method", "Methods", "Model",
    "Training", "Test", "Validation", "Proposed", "Public", "Standard",
}

_CACHE_WRITE_LOCK = threading.Lock()


def extract_datasets_by_pattern(text: str) -> list[str]:
    """Deterministic backstop for dataset detection — scans raw text directly
    (not an LLM summarizing it), so it catches mentions that get glossed over
    or fall outside the LLM's context budget. Two passes: exact match against
    a curated list of well-known dataset names, then phrase-pattern matching
    for names not on that list."""
    found = set()

    for name in KNOWN_DATASET_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
            found.add(name)

    for pattern in _DATASET_PHRASE_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1)
            if candidate in _DATASET_STOPWORDS:
                continue
            # Require at least one digit or an uppercase letter beyond the first —
            # filters out plain capitalized English words that aren't acronyms
            # or dataset-style names (e.g. "Data", "Results").
            if not (any(c.isdigit() for c in candidate) or sum(c.isupper() for c in candidate) > 1):
                continue
            found.add(candidate)

    return sorted(found)


def merge_datasets(llm_datasets: list, pattern_datasets: list[str]) -> tuple[list[str], bool]:
    """Union of LLM-extracted and pattern-matched datasets, deduped
    case-insensitively (LLM's casing wins on a collision, since it usually has
    the fuller name). Returns (merged_list, none_found)."""
    llm_datasets = [d for d in (llm_datasets or []) if isinstance(d, str) and d.strip()]
    seen_lower = {d.lower() for d in llm_datasets}
    merged = list(llm_datasets)
    for d in pattern_datasets:
        if d.lower() not in seen_lower:
            merged.append(d)
            seen_lower.add(d.lower())
    return merged, len(merged) == 0


def should_attempt_dataset_fallback(text: str) -> bool:
    """Return True only when the paper text gives evidence of empirical work.

    The main extraction already asks the model to identify datasets; the fallback
    should not be triggered for purely conceptual or theoretical discussions that
    have zero empirical signals. This preserves the safety net without paying a
    second full LLM call on every theoretically-leaning paper.
    """
    if not isinstance(text, str) or not text.strip():
        return False

    lower = text.lower()
    empirical_patterns = [
        r"\b(?:dataset|benchmark|corpus|survey|experiment|experimental|trial|cohort|participants?|subjects?|patients?|users?|responses?|interviews?)\b",
        r"\b(?:training|validation|test)\s+(?:set|split)\b",
        r"\b(?:accuracy|precision|recall|f1|dice|auc|mse|rmse|nll|bleu|rouge|mae|mape)\b",
        r"\b\d+\s+(?:participants?|subjects?|patients?|users?|responses?)\b",
    ]
    return any(re.search(pattern, lower) for pattern in empirical_patterns)


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_chunks(processed_dir: str) -> list[dict]:
    path = Path(processed_dir) / "chunks.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reconstruct_paper_texts(chunks: list[dict], max_words: int, tail_reserve_ratio: float = 0.25) -> dict[str, dict]:
    """Group chunks back into per-paper text, word-budgeted.

    For papers that fit within max_words entirely, nothing changes — full text,
    in order. For longer papers that don't fit, this now reserves a portion of
    the budget (tail_reserve_ratio, default 25%) for the LAST chunks of the
    paper, not just the first ones. Pure front-loading was systematically
    missing results/conclusion sections on longer full-text papers — those
    sections are usually near the end, and are exactly where "results" and
    "inferences" extraction needs to look. This costs nothing extra in
    num_ctx (same total word budget), it just spends it more usefully.
    """
    by_paper = defaultdict(list)
    for c in chunks:
        by_paper[c["paper_id"]].append(c)

    papers = {}
    for paper_id, paper_chunks in by_paper.items():
        paper_chunks.sort(key=lambda c: c["chunk_index"])
        title = paper_chunks[0]["title"]
        year = paper_chunks[0]["year"]
        venue = paper_chunks[0]["venue"]

        total_words = sum(len(c["text"].split()) for c in paper_chunks)

        if total_words <= max_words:
            # Everything fits — no need to choose what to cut.
            text_parts = [c["text"] for c in paper_chunks]
        else:
            tail_budget = int(max_words * tail_reserve_ratio)
            head_budget = max_words - tail_budget

            head_parts, head_words = [], 0
            for c in paper_chunks:
                if head_words >= head_budget:
                    break
                chunk_words = c["text"].split()
                take = chunk_words[: head_budget - head_words]
                head_parts.append(" ".join(take))
                head_words += len(take)

            tail_parts, tail_words = [], 0
            for c in reversed(paper_chunks):
                if tail_words >= tail_budget:
                    break
                chunk_words = c["text"].split()
                remaining = tail_budget - tail_words
                take = chunk_words[-remaining:] if remaining < len(chunk_words) else chunk_words
                tail_parts.insert(0, " ".join(take))
                tail_words += len(take)

            text_parts = head_parts + ["\n[...middle section omitted for length...]\n"] + tail_parts

        papers[paper_id] = {
            "paper_id": paper_id,
            "title": title,
            "year": year,
            "venue": venue,
            "text": " ".join(text_parts),
        }

    return papers


# --- Stage-4 output sizing: SINGLE SOURCE OF TRUTH (see CONTEXT_BUDGET_REPORT.md) ---
# The extraction schema is 10 fields: 8 prose strings + 2 short string-lists.
# Per-field length at the depth the prompt asks for: summary / problem_addressed /
# inferences ~3-4 sentences (~60 tok each = 180), method ~4-6 sentences (~110 tok),
# results / limitations / key_findings ~2-3 sentences (~55 tok each = 165),
# novelty_claim ~1-2 sentences (~35 tok); datasets + metrics ~5 short items
# (~55 tok each = 110); JSON keys/quotes/braces ~60 tok. That is ~660 tok for a
# full, concise conforming response; a verbose-but-valid one was observed at ~556
# tok (legacy selector on 0549e2e9). 768 = that estimate + ~15% margin, on a clean
# boundary.
#
# This ONE number is used two ways and must stay one number:
#   1. num_predict  — a HARD output cap (0549e2e9 transcribed tables to 1251 tok
#      with no cap; that can no longer happen).
#   2. the output term of estimate_num_ctx — a FIXED reservation added to the input
#      estimate, NOT "window size minus input". Sizing output as the remainder
#      inversely couples the two: a short, table-dense input then buys the model a
#      huge output window and it fills it transcribing cells instead of summarising.
EXTRACTION_OUTPUT_RESERVATION = 768

# Hard per-call wall-clock deadline (seconds). Not a read-gap timeout — a total
# elapsed bound enforced client-side, because requests' `timeout` only bounds the
# gap between received bytes and cannot bound total call duration (a frozen
# process / slow drip defeats it — see DIAG_0549E2E9_REPORT.md). Normal papers
# run 14-61 s; 240 s is generous. Config: llm.extraction_deadline_seconds.
EXTRACTION_DEADLINE_SECONDS = 240


def estimate_num_ctx(user_content: str, system_prompt: str = EXTRACTION_SYSTEM_PROMPT,
                      output_reservation: int = EXTRACTION_OUTPUT_RESERVATION,
                      min_ctx: int = 2048, max_ctx: int = 8192) -> int:
    """num_ctx = (estimated input tokens) + a FIXED output reservation, rounded up
    to the next 512 and clamped to [min_ctx, max_ctx].

    The output term is a fixed reservation (EXTRACTION_OUTPUT_RESERVATION / config),
    the SAME number passed as num_predict — NOT "window minus input". See that
    constant's comment for why the remainder form is a latent failure.
    """
    input_tokens = int((len(user_content.split()) + len(system_prompt.split())) * 1.4)
    rounded = ((input_tokens + output_reservation) // 512 + 1) * 512
    return max(min_ctx, min(max_ctx, rounded))


def load_extraction_cache(processed_dir: str) -> dict:
    path = Path(processed_dir) / "extraction_cache.json"
    if path.exists():
        try:
            cache = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return cache if isinstance(cache, dict) else {}
    return {}


def save_extraction_cache(processed_dir: str, cache: dict) -> None:
    path = Path(processed_dir) / "extraction_cache.json"
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _parse_json_response(content: str) -> dict:
    """LLM JSON output isn't always perfectly clean even with format='json' —
    sometimes wrapped in markdown code fences, or with stray text after the
    closing brace. Try progressively more permissive parsing before giving up,
    instead of failing the whole paper on the first strict parse error."""
    content = content.strip()

    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("Expected a JSON object", content, 0)
        return parsed
    except json.JSONDecodeError:
        pass

    # Strip a markdown code fence if the model wrapped its output in one.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if not isinstance(parsed, dict):
                raise json.JSONDecodeError("Expected a JSON object", content, 0)
            return parsed
        except json.JSONDecodeError:
            pass

    # Last resort: grab the first {...} block, in case of trailing junk text.
    brace_match = re.search(r"\{.*\}", content, re.DOTALL)
    if brace_match:
        parsed = json.loads(brace_match.group(0))  # let this raise if still invalid — caller retries
        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("Expected a JSON object", content, 0)
        return parsed

    raise json.JSONDecodeError("No JSON object found in response", content, 0)


def call_ollama_json(base_url: str, model: str, system_prompt: str, user_content: str,
                      temperature: float, max_retries: int = 2, timeout: int = 300,
                      num_ctx: int = 8192, seed: int | None = None,
                      num_predict: int | None = None,
                      deadline_seconds: float | None = None) -> dict | None:
    """Call Ollama chat endpoint with JSON-constrained output. Returns parsed dict, None,
    or the sentinel {"_deadline_exceeded": True, "_elapsed_s": ...} when the hard
    wall-clock deadline fires.

    `timeout` is requests' connect/read-gap timeout — it bounds the gap between
    received bytes, NOT total call duration. `deadline_seconds`, when set, is a
    TRUE total wall-clock bound enforced here (the request runs in a daemon thread
    we stop waiting on); on expiry the call is abandoned and the sentinel returned.

    `num_predict`, when set, is a hard output-token cap (see EXTRACTION_OUTPUT_RESERVATION).
    """
    url = f"{base_url}/api/chat"
    options = {"temperature": temperature, "num_ctx": num_ctx}
    if num_predict is not None:
        options["num_predict"] = num_predict
    if seed is not None:
        # Reproducibility (previously NOT guaranteed): pin the RNG seed and make
        # the remaining sampling params explicit at Ollama's documented defaults,
        # so output is fully determined by (model, prompt, seed, these params) and
        # a future Ollama default change cannot silently alter results. At
        # temperature 0 decoding is greedy and the seed is inert; it matters for
        # the deliberate higher-temperature retry paths, which stay reproducible.
        options.update({"seed": seed, "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1})
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "format": "json",
        "stream": False,
        "options": options,
    }

    for attempt in range(max_retries + 1):
        try:
            if deadline_seconds is not None:
                box: dict = {}

                def _worker():  # noqa: ANN202 — local
                    try:
                        box["resp"] = requests.post(
                            url, json=payload, timeout=min(timeout, deadline_seconds))
                    except Exception as exc:  # noqa: BLE001 — re-raised on the main thread
                        box["exc"] = exc

                th = threading.Thread(target=_worker, daemon=True)
                th.start()
                th.join(timeout=deadline_seconds)
                if th.is_alive():
                    # True total-elapsed deadline hit. Abandon (daemon thread dies
                    # with the process or when the orphaned request finally
                    # resolves). Not transient -> no retry.
                    print(f"    Wall-clock deadline {deadline_seconds}s exceeded — abandoning call")
                    return {"_deadline_exceeded": True, "_elapsed_s": deadline_seconds}
                if "exc" in box:
                    raise box["exc"]
                resp = box["resp"]
            else:
                resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            response_json = resp.json()
            if not isinstance(response_json, dict):
                raise ValueError("Ollama response root is not a JSON object")
            message = response_json.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                raise ValueError("Ollama response has no message.content string")
            content = message["content"]
            return _parse_json_response(content)
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"    Timed out after {timeout}s (attempt {attempt + 1}/{max_retries + 1}) — retrying...")
                continue
            print(f"    Still timing out after {max_retries + 1} attempts — skipping this paper")
            return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                continue
            print(f"    Ollama request failed after {max_retries + 1} attempts: {e}")
            return None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            if attempt < max_retries:
                continue
            print(f"    Failed to parse LLM JSON output after {max_retries + 1} attempts: {e}")
            return None

    return None


_PRIME_SYSTEM_PROMPT = "You are a JSON echo service. Reply with exactly {\"ok\": true} and nothing else."


def prime_ollama_cache(llm_cfg: dict) -> None:
    """Issue one fixed throwaway generation so the server-side prompt cache is in a
    known state before the run's real calls.

    Ollama / llama.cpp reuse KV-cache slots across requests, so a completion is a
    function of the *previous* request as well as its own prompt (verified: identical
    calls reproduce byte-for-byte, but the first call after a different prompt can
    diverge). With a fixed seed + temperature 0 + a fixed priming call + serial
    execution, a whole extraction pass becomes byte-reproducible run-to-run. No-op
    unless a seed is configured (i.e. only when reproducibility was asked for).
    """
    if llm_cfg.get("seed") is None:
        return
    try:
        call_ollama_json(
            base_url=llm_cfg["base_url"], model=llm_cfg["model"],
            system_prompt=_PRIME_SYSTEM_PROMPT, user_content="ping",
            temperature=0.0, max_retries=0, timeout=30, num_ctx=256,
            seed=llm_cfg.get("seed"),
        )
    except Exception:
        pass  # priming is best-effort; never block a run on it


_STRING_EXTRACTION_FIELDS = [
    "summary", "problem_addressed", "method", "results", "inferences",
    "novelty_claim", "limitations", "key_findings",
]
_LIST_EXTRACTION_FIELDS = ["datasets", "metrics"]
_EXTRACTION_SCHEMA_KEYS = tuple(_STRING_EXTRACTION_FIELDS) + tuple(_LIST_EXTRACTION_FIELDS)

# Bump when EXTRACTION_SYSTEM_PROMPT*, the schema, the domain-variant routing, or
# the conformance/repair logic changes. This string + a hash of the SELECTED
# paper text form the extraction cache key (see _extract_single_paper), so a
# prompt change OR a Stage-3 selection-policy change forces a real re-extraction
# instead of silently reusing a cached result produced from different inputs.
# (Before this, the cache key was paper_id alone — a selection change would have
# shown no effect because every already-extracted paper was served from cache.)
EXTRACTION_PROMPT_VERSION = "2026-09-03.numpredict-deadline"  # +num_predict cap / wall-clock deadline change output; re-extract

# R2 — biomedical / clinical / wet-lab prompt variant. Same 10 keys, same
# "ONLY JSON" contract as EXTRACTION_SYSTEM_PROMPT; only the field DEFINITIONS
# change. Clinical case reports and wet-lab papers have no "dataset"/"benchmark"/
# "SOTA" — they have study populations, specimens, outcome measures, statistics.
EXTRACTION_SYSTEM_PROMPT_BIOMED = """You are extracting structured information from a biomedical / clinical / \
laboratory research paper for a literature review, at the depth a researcher would cite directly. Given the paper \
text below, respond with ONLY a JSON object with these exact keys (every string value is plain prose, never a \
nested object or a markdown heading):
- "summary": 3-4 sentences on what was studied, in what population or model, how, and the main finding
- "problem_addressed": 3-4 sentences on the specific clinical or biological question, gap, or unmet need this study targets
- "method": 4-6 sentences on study design and procedure — design (RCT / cohort / case-control / case report / in vitro / animal), subjects or specimens and how many, groups and conditions, interventions or exposures, assays or imaging performed, and the statistical analysis
- "results": the concrete findings actually reported — effect sizes, group differences, rates, correlation or regression coefficients, sensitivity and specificity, p-values and confidence intervals where stated. Empty string only if no concrete outcome is reported at all.
- "inferences": 3-4 sentences on what the authors themselves conclude their findings mean — their interpretation and clinical or biological implications, distinct from the raw results
- "novelty_claim": what the paper claims is new — its core contribution in the authors' own framing
- "limitations": limitations the authors state, or clearly evident ones (sample size, single centre, retrospective design, confounding, no control group)
- "datasets": the data the findings rest on — describe the STUDY POPULATION OR MATERIAL concretely from THIS paper, e.g. "retrospective cohort of 214 glioblastoma patients, single centre 2015-2021", "fetal rat brain tissue, n=24, embryonic day 21", "1,032 chest radiographs from the public NIH ChestX-ray14 set". Use a named public dataset name verbatim if one is used. Empty list only for a pure review or theoretical paper.
- "metrics": what was measured or evaluated — outcome measures, endpoints, assay readouts, and statistical tests (e.g. "overall survival", "Dice similarity coefficient", "CD39 immunoreactivity", "sensitivity and specificity", "Mann-Whitney U test"). Empty list only if nothing was measured.
- "key_findings": 2-3 sentence headline takeaway, written so it could stand alone as a citation

Respond with ONLY the JSON object, no other text."""

_BIOMED_CUES = re.compile(
    r"\b(patients?|clinical|clinician|hospital|diagnos(is|tic)|prognos(is|tic)|treatment|therapy|"
    r"in vitro|in vivo|ex vivo|assay|western blot|immunohistochem\w*|rt-?pcr|elisa|staining|"
    r"antibod(y|ies)|mice|rats|murine|rodent|specimen|biopsy|serum|plasma|cohort|"
    r"case report|retrospective|prospective|randomi[sz]ed|placebo|mg/kg|gestational|"
    r"fetal|foetal|tumou?r|carcinoma|lesion|physiolog\w*|patholog\w*|histolog\w*)\b", re.I)
_CSML_CUES = re.compile(
    r"\b(datasets?|benchmark|baselines?|state-of-the-art|sota|neural network|transformer|"
    r"training set|test set|epochs?|fine-?tun\w*|pre-?train\w*|gpu|embeddings?|hyper-?parameter|"
    r"ablation|backbone|inference time|leaderboard|precision-recall)\b", re.I)


def select_extraction_prompt(text: str) -> tuple[str, str]:
    """Cheap, deterministic domain routing for Stage-4 extraction (R2). No extra
    LLM call — vocabulary counts over text already in hand. Two variants only;
    the OUTPUT SCHEMA is identical so nothing downstream forks."""
    bio = len(_BIOMED_CUES.findall(text or ""))
    csml = len(_CSML_CUES.findall(text or ""))
    if bio >= 4 and bio > csml:
        return "biomed", EXTRACTION_SYSTEM_PROMPT_BIOMED
    return "cs_ml", EXTRACTION_SYSTEM_PROMPT


# --- R1: schema-conformance detection + repair --------------------------------
SCHEMA_REPAIR_PROMPT = """The JSON below was produced as a paper extraction but does NOT match the required schema. \
Rewrite it as a SINGLE valid JSON object with EXACTLY these keys and no others:
"summary", "problem_addressed", "method", "results", "inferences", "novelty_claim", "limitations", "key_findings" \
(each a plain string), and "datasets", "metrics" (each an array of plain strings).
Move any content that sits under a different key, a nested object, a markdown heading, or a leading-colon key into \
the closest matching field above. Flatten nested objects and tables into readable prose inside the right field. \
Do NOT add any information that is not already present in the input. Use "" (or [] for datasets/metrics) for a \
field with no content.
Respond with ONLY the JSON object, no other text."""


def check_schema_conformance(parsed: dict) -> tuple[bool, list[str]]:
    """(conformant, issues). Non-conformance is anything that makes
    normalize_extraction silently drop content: unexpected top-level keys
    (markdown headings, leading-colon keys, invented structure), a string field
    delivered as a dict/list, or a datasets/metrics list of dicts."""
    if not isinstance(parsed, dict):
        return False, ["response_not_json_object"]
    issues: list[str] = []
    unexpected = [k for k in parsed if k not in _EXTRACTION_SCHEMA_KEYS and not str(k).startswith("_")]
    if unexpected:
        issues.append(f"unexpected_top_level_keys={unexpected[:6]}")
    for f in _STRING_EXTRACTION_FIELDS:
        if isinstance(parsed.get(f), (dict, list)):
            issues.append(f"{f}_is_{type(parsed[f]).__name__}")
    for f in _LIST_EXTRACTION_FIELDS:
        v = parsed.get(f)
        if isinstance(v, dict):
            issues.append(f"{f}_is_dict")
        elif isinstance(v, list) and any(isinstance(x, dict) for x in v):
            issues.append(f"{f}_has_nested_objects")
    return (not issues), issues


def salvage_nonconformant(parsed: dict) -> dict:
    """Deterministic best-effort reshape of a non-conforming response into the
    schema. Runs only on an already-broken response, so it can never make a
    conforming one worse. A nested results table is content, not junk — it is
    flattened and kept. Records what moved in `_salvage_notes`."""
    out: dict = {}
    notes: list[str] = []
    for f in _STRING_EXTRACTION_FIELDS:
        v = parsed.get(f, "")
        if isinstance(v, (dict, list)):
            out[f] = _stringify(v)
            notes.append(f"flattened_{f}")
        else:
            out[f] = v if isinstance(v, str) else ("" if v is None else str(v))
    for f in _LIST_EXTRACTION_FIELDS:
        v = parsed.get(f, [])
        if isinstance(v, list):
            out[f] = [_stringify(x).strip() for x in v if _stringify(x).strip()]
        elif isinstance(v, dict):
            out[f] = [f"{k}: {_stringify(val)}".strip() for k, val in v.items() if _stringify(val).strip()]
            notes.append(f"flattened_{f}_dict")
        elif v:
            out[f] = [_stringify(v).strip()]
        else:
            out[f] = []
    for k, v in parsed.items():
        if k in _EXTRACTION_SCHEMA_KEYS or str(k).startswith("_"):
            continue
        name = re.sub(r"^[\s:#*=\-]+", "", str(k)).strip().lower()
        blob = _stringify(v).strip()
        if not blob:
            continue
        if any(w in name for w in ("objective", "hypothesis", "aim", "gap", "background", "introduction", "motivation")):
            target = "problem_addressed"
        elif "limitation" in name or "future work" in name:
            target = "limitations"
        elif any(w in name for w in ("conclusion", "discussion", "interpret", "implication")):
            target = "inferences"
        elif any(w in name for w in ("method", "material", "procedure", "design", "patient", "diagnosis", "system", "implementation")):
            target = "method"
        elif any(w in name for w in ("result", "finding", "outcome", "improvement", "impact", "table", "activit", "score", "performance")):
            target = "results"
        elif "summary" in name or name in ("abstract", "title"):
            target = "summary"
        else:
            target = "results"  # invented structure is usually a results breakdown
        out[target] = (f"{out.get(target, '')}\n{blob}".strip() if out.get(target) else blob)
        notes.append(f"moved '{str(k)[:40]}' -> {target}")
    if notes:
        out["_salvage_notes"] = notes
    return out


def repair_schema(parsed: dict, llm_cfg: dict) -> dict | None:
    """Ask the model to reshape a malformed extraction to the schema.

    A naive retry does NOT work: at temperature 0 with a fixed seed the same
    (system_prompt, user_content) is deterministic, so re-issuing the original
    extraction request returns the identical malformed response. The repair
    therefore feeds the malformed JSON back in as the user content with a
    reshape instruction — a different input, hence a different (hopefully
    conforming) output.
    """
    try:
        blob = json.dumps(parsed, ensure_ascii=False)[:6000]
    except (TypeError, ValueError):
        blob = str(parsed)[:6000]
    reservation = int(llm_cfg.get("extraction_output_reservation", EXTRACTION_OUTPUT_RESERVATION))
    rep = call_ollama_json(
        base_url=llm_cfg["base_url"], model=llm_cfg["model"],
        system_prompt=SCHEMA_REPAIR_PROMPT, user_content=blob,
        temperature=llm_cfg.get("temperature", 0.0),
        timeout=llm_cfg.get("timeout_seconds", 300),
        num_ctx=estimate_num_ctx(blob, system_prompt=SCHEMA_REPAIR_PROMPT,
                                 output_reservation=reservation),
        seed=llm_cfg.get("seed"),
        num_predict=reservation,
        deadline_seconds=float(llm_cfg.get("extraction_deadline_seconds", EXTRACTION_DEADLINE_SECONDS)),
    )
    return None if isinstance(rep, dict) and rep.get("_deadline_exceeded") else rep


def _has_min_content(d: dict) -> bool:
    core = sum(bool(str(d.get(f, "")).strip())
               for f in ("summary", "problem_addressed", "method", "key_findings"))
    return core >= 2 or (bool(str(d.get("results", "")).strip()) and core >= 1)


def _text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _cache_entry_reusable(cached, text: str) -> bool:
    """Reuse a cached extraction only if it was produced by the current prompt
    version from the current selected text, is usable, and is not a recorded
    non-conformance or a poisoned (junk-key) entry from before this change."""
    if not isinstance(cached, dict):
        return False
    if cached.get("_prompt_version") != EXTRACTION_PROMPT_VERSION:
        return False
    if cached.get("_text_hash") != _text_hash(text):
        return False
    if cached.get("_extraction_nonconformant") or cached.get("_extraction_failed"):
        return False
    if any(k not in _EXTRACTION_SCHEMA_KEYS and not str(k).startswith("_") for k in cached):
        return False
    return is_usable_extraction(normalize_extraction(cached))


def normalize_extraction(extraction: dict) -> dict:
    """Normalize LLM fields before caching, clustering, or downstream output."""
    normalized = dict(extraction) if isinstance(extraction, dict) else {}
    for field in _STRING_EXTRACTION_FIELDS:
        normalized[field] = _stringify(normalized.get(field, ""))
    for field in _LIST_EXTRACTION_FIELDS:
        value = normalized.get(field, [])
        if isinstance(value, list):
            normalized[field] = [_stringify(item).strip() for item in value if _stringify(item).strip()]
        elif value:
            normalized[field] = [_stringify(value).strip()]
        else:
            normalized[field] = []
    return normalized


def is_usable_extraction(extraction: dict) -> bool:
    if not isinstance(extraction, dict) or extraction.get("_extraction_failed"):
        return False
    return sum(bool(extraction.get(field, "").strip()) for field in
               ["summary", "problem_addressed", "method", "key_findings"]) >= 2


def failed_extraction() -> dict:
    return normalize_extraction({"_extraction_failed": True})


def _extract_single_paper(paper_id: str, paper: dict, llm_cfg: dict, cache: dict, processed_dir: str | None = None) -> tuple[str, dict]:
    """One paper's extraction, factored out so it can run under a small worker pool.

    Stage-4 hardening (R1/R2): route to a domain-appropriate prompt variant,
    then explicitly check the response against the schema. A non-conforming
    response (nested objects, leading-colon / markdown keys, invented top-level
    keys) is salvaged deterministically or, failing that, sent back to the model
    for a reshape. If it still will not conform, the record is FLAGGED
    (`_extraction_nonconformant`) rather than returned as a partially-empty
    result that reads like "the paper reported no metrics".
    """
    text = paper["text"]
    cached = cache.get(paper_id)
    if _cache_entry_reusable(cached, text):
        return paper_id, normalize_extraction(cached)

    reservation = int(llm_cfg.get("extraction_output_reservation", EXTRACTION_OUTPUT_RESERVATION))
    deadline = float(llm_cfg.get("extraction_deadline_seconds", EXTRACTION_DEADLINE_SECONDS))
    user_content = f"Title: {paper['title']}\n\nText:\n{text}"
    num_ctx = estimate_num_ctx(user_content, output_reservation=reservation)
    variant, sys_prompt = select_extraction_prompt(text)
    raw = call_ollama_json(
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        system_prompt=sys_prompt,
        user_content=user_content,
        temperature=llm_cfg.get("temperature", 0.0),
        timeout=llm_cfg.get("timeout_seconds", 300),
        num_ctx=num_ctx,
        seed=llm_cfg.get("seed"),
        num_predict=reservation,
        deadline_seconds=deadline,
    )

    conformance = "conformant"
    repair_used = False
    issues: list[str] = []
    if isinstance(raw, dict) and raw.get("_deadline_exceeded"):
        extraction = failed_extraction()
        extraction["_failure_reason"] = "wall_clock_exceeded"
        extraction["_elapsed_s"] = raw.get("_elapsed_s")
        conformance = "wall_clock_exceeded"
    elif raw is None:
        extraction = failed_extraction()
        extraction["_failure_reason"] = "no_response"
        conformance = "no_response"
    else:
        ok, issues = check_schema_conformance(raw)
        if ok:
            extraction = normalize_extraction(raw)
        else:
            salv = salvage_nonconformant(raw)
            if _has_min_content(salv):
                extraction = normalize_extraction(salv)
                conformance = "salvaged"
            else:
                rep = repair_schema(raw, llm_cfg)
                repair_used = True
                rep_ok = isinstance(rep, dict) and check_schema_conformance(rep)[0]
                if rep_ok and _has_min_content(rep):
                    extraction = normalize_extraction(rep)
                    conformance = "repaired"
                elif isinstance(rep, dict) and _has_min_content(salvage_nonconformant(rep)):
                    extraction = normalize_extraction(salvage_nonconformant(rep))
                    conformance = "repaired_salvaged"
                else:
                    # Keep the best partial content, but FLAG it so downstream /
                    # the UI / metrics do not read empty fields as "absent from
                    # the paper".
                    extraction = normalize_extraction(salv)
                    extraction["_extraction_nonconformant"] = True
                    conformance = "nonconformant_unrepaired"
            extraction["_conformance_issues"] = issues[:8]

        if not extraction.get("_extraction_failed"):
            pattern_datasets = extract_datasets_by_pattern(text)
            merged, none_found = merge_datasets(extraction.get("datasets"), pattern_datasets)
            if none_found and should_attempt_dataset_fallback(text):
                fallback = call_ollama_json(
                    base_url=llm_cfg["base_url"],
                    model=llm_cfg["model"],
                    system_prompt=DATASET_FALLBACK_PROMPT,
                    user_content=user_content,
                    temperature=llm_cfg.get("temperature", 0.0),
                    timeout=llm_cfg.get("timeout_seconds", 300),
                    num_ctx=num_ctx,
                    seed=llm_cfg.get("seed"),
                    num_predict=reservation,
                    deadline_seconds=deadline,
                )
                if isinstance(fallback, dict) and fallback.get("_deadline_exceeded"):
                    fallback = None
                if fallback and fallback.get("datasets"):
                    merged, none_found = merge_datasets(fallback["datasets"], [])
                    extraction["_dataset_fallback_used"] = True
            extraction["datasets"] = merged
            if none_found:
                extraction["_no_dataset_stated"] = True

    extraction["_domain_variant"] = variant
    extraction["_conformance"] = conformance
    if repair_used:
        extraction["_repair_call_made"] = True

    if not extraction.get("_extraction_failed"):
        extraction["_prompt_version"] = EXTRACTION_PROMPT_VERSION
        extraction["_text_hash"] = _text_hash(text)
        with _CACHE_WRITE_LOCK:
            cache[paper_id] = extraction
            if processed_dir is not None:
                save_extraction_cache(processed_dir, cache)

    return paper_id, extraction


def extract_paper_fields(papers: dict, llm_cfg: dict, progress_path: Path | None = None,
                          cache: dict | None = None, processed_dir: str | None = None,
                          max_workers: int | None = 2) -> dict:
    """Run structured extraction for every paper.

    The main optimization is to avoid the expensive dataset-only fallback LLM
    call for papers that give no empirical evidence in the source text, and to
    cap per-paper extraction parallelism at a modest worker count to avoid the
    Ollama saturation we saw at 4 workers without sacrificing the serial-vs-2x
    improvement.
    """
    results = {}
    cache = cache if cache is not None else {}
    max_workers = max(1, min(max_workers or 2, len(papers) or 1))
    if llm_cfg.get("seed") is not None:
        # Reproducibility: concurrent Ollama requests get non-deterministic slot /
        # prompt-cache assignment, so a configured seed forces single-worker
        # extraction (roughly 2x slower) and one fixed priming call up front.
        max_workers = 1
        prime_ollama_cache(llm_cfg)
    cached_ids = {paper_id for paper_id, value in cache.items()
                  if isinstance(value, dict)
                  and value.get("_prompt_version") == EXTRACTION_PROMPT_VERSION
                  and is_usable_extraction(value)}

    if len(papers) <= 1 or max_workers == 1:
        for paper_id, paper in tqdm(papers.items(), desc="Extracting per-paper fields"):
            paper_id, extraction = _extract_single_paper(paper_id, paper, llm_cfg, cache, processed_dir)
            results[paper_id] = extraction
            if progress_path is not None:
                progress_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_extract_single_paper, paper_id, paper, llm_cfg, cache, processed_dir): paper_id
                for paper_id, paper in papers.items()
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc="Extracting per-paper fields"):
                paper_id = futures[future]
                try:
                    paper_id, extraction = future.result()
                except Exception as exc:
                    print(f"    Extraction failed for {paper_id}: {exc}")
                    extraction = {
                        "summary": "", "problem_addressed": "", "method": "",
                        "datasets": [], "metrics": [], "key_findings": "",
                        "_extraction_failed": True,
                        "_extraction_error": str(exc),
                    }
                results[paper_id] = extraction
                if progress_path is not None:
                    progress_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    cache_hits = len(cached_ids.intersection(papers))
    if cache_hits:
        print(f"  {cache_hits}/{len(papers)} papers served from extraction cache (skipped LLM call)")

    return results


def get_paper_embeddings(chroma_dir: str, collection_name: str) -> dict[str, np.ndarray]:
    """Mean-pool each paper's chunk embeddings by pulling them back out of ChromaDB
    (reuses Stage 3's work instead of re-embedding anything)."""
    import chromadb

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)

    data = collection.get(include=["embeddings", "metadatas"])
    by_paper = defaultdict(list)
    for embedding, metadata in zip(data["embeddings"], data["metadatas"]):
        by_paper[metadata["paper_id"]].append(embedding)

    return {pid: np.mean(vecs, axis=0) for pid, vecs in by_paper.items()}


def _stringify(value) -> str:
    """Coerce an extracted field to plain text, regardless of what shape the LLM
    returned it in. format="json" only guarantees valid JSON, not that 'method'
    is always a flat string — sometimes the model nests it as a dict of
    sub-techniques instead. Flatten anything non-string into readable text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return "; ".join(_stringify(v) for v in value)
    return str(value) if value is not None else ""


def embed_method_texts(extractions: dict, model_name: str, device: str) -> dict[str, np.ndarray]:
    """Embed method + problem_addressed + key_findings per paper, not just method
    alone, and not the full chunk text.

    Whole-paper embeddings are dominated by shared domain vocabulary (this
    corpus is entirely shared-domain boilerplate), which drowns out the
    actual technique differences between papers — that's still true, so we
    don't embed full text. But method alone was too thin a signal: two papers
    with genuinely different problems/outcomes could still read as similar if
    their method descriptions happened to use similar phrasing. Combining
    method + problem + findings gives clustering AND novelty-comparison
    (which reuses this function) a fuller, more discriminative signal without
    reintroducing the shared-vocabulary noise of full chunk text.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=device)
    model.max_seq_length = 384  # combined field is longer than method alone — raised from 256

    paper_ids = list(extractions.keys())
    texts = []
    for pid in paper_ids:
        e = extractions[pid]
        method = _stringify(e.get("method") or "")
        problem = _stringify(e.get("problem_addressed") or "")
        findings = _stringify(e.get("key_findings") or "")
        combined = " ".join(part for part in [method, problem, findings] if part).strip()
        if not combined:
            combined = _stringify(e.get("summary", ""))  # fall back if all three are empty
        texts.append(combined)

    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    return {pid: vec for pid, vec in zip(paper_ids, vectors)}


def embed_topic_texts(extractions: dict, model_name: str, device: str) -> dict[str, np.ndarray]:
    """Embed problem_addressed (falling back to summary) per paper — the
    fallback basis used when method-text clustering comes back with low
    silhouette separation (see cluster_by_best_basis below).

    Some corpora have real methodological diversity to cluster on (e.g. mixup
    vs. disentanglement vs. meta-learning in a CS/ML corpus) — for those,
    embed_method_texts above works well. Others don't: an entire corpus of
    survey-based behavioral studies mostly says "we used a questionnaire" in
    its method field regardless of topic, so clustering on method just splits
    near-identical text arbitrarily. What actually differs paper to paper in
    that case is the TOPIC/OUTCOME being studied, which problem_addressed
    captures far better.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=device)
    model.max_seq_length = 384

    paper_ids = list(extractions.keys())
    texts = []
    for pid in paper_ids:
        e = extractions[pid]
        problem = _stringify(e.get("problem_addressed") or "")
        combined = problem or _stringify(e.get("summary", ""))
        texts.append(combined if combined else "unspecified topic")

    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    return {pid: vec for pid, vec in zip(paper_ids, vectors)}


def cluster_papers(paper_embeddings: dict[str, np.ndarray], k) -> tuple[dict[str, int], float]:
    """KMeans over paper-level embeddings. Returns (paper_id -> cluster_id, silhouette_score).

    k="auto" picks the cluster count (within k_min..k_max) that maximizes
    silhouette score, instead of forcing a fixed count that may not match
    the corpus's actual structure. The score is now always returned (not just
    printed for the auto case) so callers can decide whether the result is
    good enough to use, or should trigger a fallback strategy.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    def fit(candidate_k: int):
        min_size = max(2, int(np.ceil(len(paper_ids) / (candidate_k * 4))))
        best = None
        for seed in range(42, 52):
            candidate = KMeans(n_clusters=candidate_k, random_state=seed, n_init=10).fit_predict(X)
            counts = np.bincount(candidate, minlength=candidate_k)
            score = silhouette_score(X, candidate) if len(set(candidate)) > 1 else -1.0
            if best is None or score > best[0]:
                best = (score, candidate)
            if counts.min() >= min_size:
                return candidate, score
        return best[1], best[0]

    paper_ids = list(paper_embeddings.keys())
    X = np.stack([paper_embeddings[pid] for pid in paper_ids])

    if len(paper_ids) < 2:
        labels = np.zeros(1, dtype=int)
        return {pid: int(label) for pid, label in zip(paper_ids, labels)}, -1.0

    if k == "auto":
        if len(paper_ids) == 2:
            labels = np.zeros(len(paper_ids), dtype=int)
            return {pid: int(label) for pid, label in zip(paper_ids, labels)}, -1.0

        best_k, best_score, best_labels = None, -1, None
        k_min, k_max = 2, min(8, len(paper_ids) - 1)
        for candidate_k in range(k_min, k_max + 1):
            labels, score = fit(candidate_k)
            if score > best_score:
                best_k, best_score, best_labels = candidate_k, score, labels

        if best_labels is None:
            labels = np.zeros(len(paper_ids), dtype=int)
            score = -1.0
        else:
            labels, score = best_labels, best_score
        print(f"  auto-selected k={best_k} (silhouette={score:.3f})")
    else:
        k = min(k, max(1, len(paper_ids) - 1))
        labels, score = fit(k)

    return {pid: int(label) for pid, label in zip(paper_ids, labels)}, score


def cluster_by_best_basis(extractions: dict, embedding_cfg: dict, k) -> tuple[dict[str, int], str, float]:
    """Cluster papers, automatically falling back from method-based to
    topic-based embeddings if method text turns out to lack diversity across
    the corpus. Low silhouette across the auto-selected k range (not just one
    unlucky k) is the signal — it means the embedding space itself doesn't
    separate papers well, not that KMeans picked a bad k.

    Returns (cluster_assignments, basis_used, silhouette_score) — basis_used
    is "method" or "topic", needed downstream so name_clusters asks the LLM
    for the right KIND of label (technique vs. topic/outcome).
    """
    method_embeddings = embed_method_texts(extractions, embedding_cfg["model"], embedding_cfg["device"])
    method_assignments, method_score = cluster_papers(method_embeddings, k)

    if method_score >= LOW_DIVERSITY_SILHOUETTE_THRESHOLD:
        return method_assignments, "method", method_score

    print(f"  Method-based clustering silhouette={method_score:.3f} is below the "
          f"{LOW_DIVERSITY_SILHOUETTE_THRESHOLD} diversity threshold — this usually means most papers "
          f"in this corpus share the same data-collection method (e.g. a survey-heavy literature), so "
          f"method text doesn't separate them meaningfully. Falling back to topic-based clustering "
          f"(problem_addressed) instead...")
    topic_embeddings = embed_topic_texts(extractions, embedding_cfg["model"], embedding_cfg["device"])
    topic_assignments, topic_score = cluster_papers(topic_embeddings, k)
    print(f"  Topic-based clustering silhouette={topic_score:.3f}")
    return topic_assignments, "topic", topic_score


def name_clusters(cluster_assignments: dict[str, int], papers: dict, extractions: dict,
                   llm_cfg: dict, basis: str = "method", max_exemplars: int = 6) -> dict[int, dict]:
    """One LLM call per cluster to generate a human-readable label + description.

    basis picks which prompt (and which per-paper detail field) to use —
    "method" names clusters by technique, "topic" names them by research
    subject/outcome. Must match whichever embedding basis actually produced
    these cluster assignments, or the naming won't make sense against what
    the clusters actually group by.
    """
    prompt = CLUSTER_NAMING_PROMPT_METHOD if basis == "method" else CLUSTER_NAMING_PROMPT_TOPIC
    detail_field = "method" if basis == "method" else "problem_addressed"

    by_cluster = defaultdict(list)
    for paper_id, cluster_id in cluster_assignments.items():
        by_cluster[cluster_id].append(paper_id)

    cluster_info = {}
    for cluster_id, paper_ids in tqdm(sorted(by_cluster.items()), desc="Naming clusters"):
        exemplars = [pid for pid in paper_ids if pid in papers][:max_exemplars]
        if not exemplars:
            cluster_info[cluster_id] = {
                "label": f"Cluster {cluster_id}", "description": "", "paper_count": 0,
            }
            continue
        lines = []
        for pid in exemplars:
            title = papers[pid]["title"]
            detail = _stringify(extractions.get(pid, {}).get(detail_field, ""))
            lines.append(f"- {title}: {detail}")
        user_content = "\n".join(lines)

        naming = call_ollama_json(
            base_url=llm_cfg["base_url"],
            model=llm_cfg["model"],
            system_prompt=prompt,
            user_content=user_content,
            temperature=llm_cfg.get("temperature", 0.0),
            num_ctx=CLUSTER_NAMING_NUM_CTX,
            seed=llm_cfg.get("seed"),
        )
        if not isinstance(naming, dict):
            naming = {"label": f"Cluster {cluster_id}", "description": ""}

        label = _stringify(naming.get("label", "")).strip() or f"Cluster {cluster_id}"
        description = _stringify(naming.get("description", "")).strip()

        cluster_info[cluster_id] = {
            "label": label,
            "description": description,
            "paper_count": len(exemplars),
        }

    return cluster_info


_CB_ACCEPT = {"conformant", "salvaged", "repaired", "repaired_salvaged"}


def _legacy_schema_fallback_count(processed_dir: str) -> int:
    """How many papers this run's selector routed content_aware -> legacy because
    the chunk schema was legacy (visible only in retrieval_selection.json)."""
    try:
        traces = json.loads((Path(processed_dir) / "retrieval_selection.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(1 for t in traces.values() if isinstance(t, dict) and t.get("mode") == "legacy_fallback")


def _apply_selection_circuit_breaker(config: dict, extractions: dict, max_context_words: int) -> dict:
    """A paper that content_aware selection drove to a non-conforming / deadline-
    failed extraction gets ONE bounded retry under LEGACY selection. Not a loop.
    Recovered -> accepted with `_selection_fallback: true`. Still failing after
    both -> `_extraction_failed` (never an empty field). No-op unless the run is
    content_aware.
    """
    if (config.get("selection") or {}).get("mode", "legacy") != "content_aware":
        return extractions
    stuck = [pid for pid, e in extractions.items()
             if e.get("_conformance") in ("nonconformant_unrepaired", "wall_clock_exceeded")
             and not e.get("_selection_fallback")]
    if not stuck:
        return extractions
    print(f"  Circuit breaker: {len(stuck)} paper(s) non-conforming under content_aware "
          f"-> one retry under legacy selection: {[p[:10] for p in stuck]}")
    legacy_config = {**config, "selection": {**(config.get("selection") or {}), "mode": "legacy"}}
    from src.summarization.retrieval_aware import build_retrieval_aware_papers
    legacy_papers = build_retrieval_aware_papers(legacy_config, max_context_words)
    retry_set = {pid: legacy_papers[pid] for pid in stuck if pid in legacy_papers}
    retried = extract_paper_fields(retry_set, config["llm"], cache={}, processed_dir=None)
    for pid in stuck:
        e2 = retried.get(pid)
        if isinstance(e2, dict) and e2.get("_conformance") in _CB_ACCEPT:
            e2["_selection_fallback"] = True
            e2["_selection_fallback_from"] = "content_aware"
            extractions[pid] = e2
        else:
            extractions[pid]["_selection_fallback"] = True
            extractions[pid]["_extraction_failed"] = True
            extractions[pid]["_failure_reason"] = "nonconformant_both_selections"
    ok = sum(1 for pid in stuck if extractions[pid].get("_conformance") in _CB_ACCEPT
             and not extractions[pid].get("_extraction_failed"))
    print(f"  Circuit breaker: {ok}/{len(stuck)} recovered under legacy, "
          f"{len(stuck) - ok} -> _extraction_failed (nonconformant_both_selections)")
    return extractions


def run_summarization(config: dict) -> None:
    paths_cfg = config["paths"]
    llm_cfg = config["llm"]
    cat_cfg = config.get("categorization", {})

    chunks = load_chunks(paths_cfg["processed_dir"])
    max_context_words = llm_cfg.get("max_context_words", 3000)
    if config.get("summarization", {}).get("context_selection") == "retrieval_aware":
        from src.summarization.retrieval_aware import build_retrieval_aware_papers
        papers = build_retrieval_aware_papers(config, max_context_words)
    else:
        papers = reconstruct_paper_texts(chunks, max_context_words)
    print(f"Reconstructed {len(papers)} papers from {len(chunks)} chunks")

    cache = load_extraction_cache(paths_cfg["processed_dir"])
    print(f"Extracting structured fields via {llm_cfg['model']} "
          f"({len(papers)} papers, {len(cache)} already cached from prior runs)...")
    extractions = extract_paper_fields(papers, llm_cfg, cache=cache, processed_dir=paths_cfg["processed_dir"])
    extractions = _apply_selection_circuit_breaker(config, extractions, max_context_words)

    n_cb = sum(1 for e in extractions.values() if e.get("_selection_fallback"))
    n_schema_fb = _legacy_schema_fallback_count(paths_cfg["processed_dir"])
    failed = sum(1 for e in extractions.values() if e.get("_extraction_failed"))
    if n_cb or n_schema_fb:
        print(f"  Selection fallback: {n_cb} via conformance circuit-breaker, "
              f"{n_schema_fb} via legacy-schema fallback "
              f"(a run with a non-zero fallback count is PARTLY a legacy run)")
    if failed:
        print(f"  Warning: {failed}/{len(papers)} papers failed extraction "
              f"(flagged _extraction_failed, NOT emitted as empty fields)")

    print("Clustering papers (auto-selecting method vs. topic basis by diversity)...")
    k = cat_cfg.get("num_clusters", "auto")
    cluster_assignments, basis, score = cluster_by_best_basis(extractions, config["embedding"], k)
    print(f"  Using {basis}-based clustering (silhouette={score:.3f})")

    print(f"Naming {len(set(cluster_assignments.values()))} clusters via LLM ({basis} basis)...")
    cluster_info = name_clusters(cluster_assignments, papers, extractions, llm_cfg, basis=basis)

    for cid, info in sorted(cluster_info.items()):
        print(f"  [{cid}] {info['label']} ({info['paper_count']} papers) — {info['description']}")

    output = []
    for paper_id, paper in papers.items():
        cluster_id = cluster_assignments[paper_id]
        record = {
            "paper_id": paper_id,
            "title": paper["title"],
            "year": paper["year"],
            "venue": paper["venue"],
            "cluster_id": cluster_id,
            "category": cluster_info[cluster_id]["label"],
            **extractions[paper_id],
        }
        output.append(record)

    out_path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nSaved {len(output)} paper summaries to {out_path}")

    # Stage 5 — evidence gate: attribution + confidence + abstention over the
    # extracted Dataset/Metric/Result values (FINAL_REPORT.md §O change 4).
    # Rewrites paper_summaries.json so only RETURNED evidence survives, and
    # writes paper_evidence.json with full provenance. No-op unless enabled.
    if bool((config.get("evidence_grounding", {}) or {}).get("enabled")):
        from src.evidence.gate import run_evidence_gate
        run_evidence_gate(config)

    cluster_out_path = Path(paths_cfg["processed_dir"]) / "clusters.json"
    cluster_out_path.write_text(json.dumps(cluster_info, indent=2), encoding="utf-8")
    print(f"Saved cluster definitions to {cluster_out_path}")


def rerun_categorization_only(config: dict) -> None:
    """Re-cluster and re-name using an already-saved paper_summaries.json — skips the
    slow LLM extraction step entirely. Use this when only clustering/naming needs a redo."""
    paths_cfg = config["paths"]
    llm_cfg = config["llm"]
    cat_cfg = config.get("categorization", {})

    summaries_path = Path(paths_cfg["processed_dir"]) / "paper_summaries.json"
    existing = json.loads(summaries_path.read_text(encoding="utf-8"))

    papers = {r["paper_id"]: {"paper_id": r["paper_id"], "title": r["title"],
                               "year": r["year"], "venue": r["venue"]} for r in existing}
    extractions = {r["paper_id"]: {k: v for k, v in r.items()
                                    if k not in ("paper_id", "title", "year", "venue",
                                                 "cluster_id", "category")}
                   for r in existing}

    print("Clustering papers (auto-selecting method vs. topic basis by diversity)...")
    k = cat_cfg.get("num_clusters", "auto")
    cluster_assignments, basis, score = cluster_by_best_basis(extractions, config["embedding"], k)
    print(f"  Using {basis}-based clustering (silhouette={score:.3f})")

    print(f"Naming {len(set(cluster_assignments.values()))} clusters via LLM ({basis} basis)...")
    cluster_info = name_clusters(cluster_assignments, papers, extractions, llm_cfg, basis=basis)

    for cid, info in sorted(cluster_info.items()):
        print(f"  [{cid}] {info['label']} ({info['paper_count']} papers) — {info['description']}")

    for record in existing:
        cid = cluster_assignments[record["paper_id"]]
        record["cluster_id"] = cid
        record["category"] = cluster_info[cid]["label"]

    summaries_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    cluster_out_path = Path(paths_cfg["processed_dir"]) / "clusters.json"
    cluster_out_path.write_text(json.dumps(cluster_info, indent=2), encoding="utf-8")
    print(f"\nUpdated {summaries_path} and {cluster_out_path}")


def rerun_weak_extractions(config: dict) -> None:
    """Re-run LLM extraction only for papers flagged as weak/failed by validate.py.
    Much faster than reprocessing all 50, and targets the actual accuracy problem
    instead of silently accepting empty fields."""
    paths_cfg = config["paths"]
    llm_cfg = config["llm"]
    processed_dir = Path(paths_cfg["processed_dir"])

    weak_path = processed_dir / "weak_extractions.json"
    if not weak_path.exists():
        raise RuntimeError(
            "No weak_extractions.json found. Run: "
            "python -m src.summarization.validate --config configs/config.yaml --list-weak  first."
        )
    weak_ids = set(json.loads(weak_path.read_text(encoding="utf-8")))
    print(f"Re-extracting {len(weak_ids)} flagged paper(s)...")

    chunks = load_chunks(paths_cfg["processed_dir"])
    all_papers = reconstruct_paper_texts(chunks, llm_cfg.get("max_context_words", 3000))
    papers_to_redo = {pid: all_papers[pid] for pid in weak_ids if pid in all_papers}

    # A slightly higher temperature + one extra retry gives the model a better
    # chance of producing real content on a second attempt, since these are
    # cases that already failed once at the default settings. NOT read from
    # cache — these are known-weak, retrying them against a stale cached
    # (also weak) result would defeat the purpose.
    retry_llm_cfg = {**llm_cfg, "temperature": max(llm_cfg.get("temperature", 0.0), 0.4)}
    progress_path = processed_dir / "retry_progress.json"
    new_extractions = extract_paper_fields(papers_to_redo, retry_llm_cfg, progress_path=progress_path,
                                            cache={}, processed_dir=None)

    summaries_path = processed_dir / "paper_summaries.json"
    records = json.loads(summaries_path.read_text(encoding="utf-8"))

    still_weak = []
    for r in records:
        if r["paper_id"] in new_extractions:
            new_data = new_extractions[r["paper_id"]]
            empty_count = sum(1 for f in ["summary", "problem_addressed", "method", "key_findings"]
                               if not (new_data.get(f) or "").strip())
            if empty_count >= 3:
                still_weak.append(r["title"])
                continue  # keep old (empty) data rather than overwrite with equally-empty new data
            for k, v in new_data.items():
                r[k] = v
            r.pop("_extraction_failed", None)

    summaries_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Updated {summaries_path}")
    if still_weak:
        print(f"\n{len(still_weak)} paper(s) STILL weak after retry — likely a genuinely "
              f"hard case (very short/garbled source text). Worth checking manually:")
        for title in still_weak:
            print(f"  - {title[:80]}")
    else:
        print("All flagged papers now have real content.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--recluster-only", action="store_true",
                         help="Skip LLM extraction, just re-cluster/re-name using existing paper_summaries.json")
    parser.add_argument("--retry-weak", action="store_true",
                         help="Re-run extraction only for papers listed in weak_extractions.json")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.retry_weak:
        rerun_weak_extractions(cfg)
    elif args.recluster_only:
        rerun_categorization_only(cfg)
    else:
        run_summarization(cfg)