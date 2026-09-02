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


def estimate_num_ctx(user_content: str, system_prompt: str = EXTRACTION_SYSTEM_PROMPT,
                      response_budget_tokens: int = 600, min_ctx: int = 2048, max_ctx: int = 8192) -> int:
    """Size the context window to what this specific paper actually needs, instead
    of always requesting the max. ~1.4 tokens/word is a reasonable rough estimate
    for English academic text; rounded up to the nearest 512 for clean allocation,
    clamped to [min_ctx, max_ctx].
    """
    word_count = len(user_content.split()) + len(system_prompt.split())
    estimated_tokens = int(word_count * 1.4) + response_budget_tokens
    rounded = ((estimated_tokens // 512) + 1) * 512
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
                      num_ctx: int = 8192, seed: int | None = None) -> dict | None:
    """Call Ollama chat endpoint with JSON-constrained output. Returns parsed dict or None.

    timeout defaults to 300s because full-text papers can run considerably
    longer than abstract-only ones on a 7B local model. Retries cover
    timeouts and connection drops, not just malformed JSON, since a
    slow/loaded local Ollama instance can time out transiently without the
    request itself being broken.

    num_ctx is now a parameter, not hardcoded — see estimate_num_ctx above.
    Sizing this to what the paper actually needs (rather than always 8192)
    reduces VRAM allocation pressure, which matters most on a 6GB card when
    processing the many short abstract-only papers most corpora contain.
    """
    url = f"{base_url}/api/chat"
    options = {"temperature": temperature, "num_ctx": num_ctx}
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
    """One paper's extraction, factored out so it can run under a small worker pool."""
    cached = cache.get(paper_id)
    if isinstance(cached, dict):
        cached = normalize_extraction(cached)
        if is_usable_extraction(cached):
            return paper_id, cached

    user_content = f"Title: {paper['title']}\n\nText:\n{paper['text']}"
    num_ctx = estimate_num_ctx(user_content)
    extraction = call_ollama_json(
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_content=user_content,
        temperature=llm_cfg.get("temperature", 0.0),
        timeout=llm_cfg.get("timeout_seconds", 300),
        num_ctx=num_ctx,
        seed=llm_cfg.get("seed"),
    )
    if extraction is None:
        extraction = failed_extraction()
    else:
        extraction = normalize_extraction(extraction)
        pattern_datasets = extract_datasets_by_pattern(paper["text"])
        merged, none_found = merge_datasets(extraction.get("datasets"), pattern_datasets)

        if none_found and should_attempt_dataset_fallback(paper["text"]):
            fallback = call_ollama_json(
                base_url=llm_cfg["base_url"],
                model=llm_cfg["model"],
                system_prompt=DATASET_FALLBACK_PROMPT,
                user_content=user_content,
                temperature=llm_cfg.get("temperature", 0.0),
                timeout=llm_cfg.get("timeout_seconds", 300),
                num_ctx=num_ctx,
                seed=llm_cfg.get("seed"),
            )
            if fallback and fallback.get("datasets"):
                merged, none_found = merge_datasets(fallback["datasets"], [])
                extraction["_dataset_fallback_used"] = True

        extraction["datasets"] = merged
        if none_found:
            extraction["_no_dataset_stated"] = True

    if not extraction.get("_extraction_failed"):
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
                  if isinstance(value, dict) and is_usable_extraction(value)}

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
    failed = sum(1 for e in extractions.values() if e.get("_extraction_failed"))
    if failed:
        print(f"  Warning: {failed}/{len(papers)} papers failed extraction (empty fields, flagged)")

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