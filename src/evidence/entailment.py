"""Local NLI cross-encoder inference; missing/oversized inputs fail closed.

Weights are provisioned separately in .run/models/huggingface. Gate evaluation
never downloads a model or truncates the source used to justify a claim.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

MODEL_ID = "cross-encoder/nli-deberta-v3-small"
MODEL_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
CACHE_DIR = Path(__file__).resolve().parents[2] / ".run/models/huggingface"
MIN_OVERLAP, MAX_OVERLAP, MIN_ENTAILMENT = 0.65, 0.85, 0.90
MAX_CANDIDATES = 5
_LOCK = Lock()


def model_identity() -> dict:
    path = os.environ.get('RGPT_NLI_MODEL_PATH')
    return dict(model=path or MODEL_ID, revision=None if path else MODEL_REVISION)


@lru_cache(maxsize=2)
def _load_model(path: str):
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        options = dict(local_files_only=True, trust_remote_code=False)
        if path == MODEL_ID:
            options.update(revision=MODEL_REVISION, cache_dir=str(CACHE_DIR))
        tokenizer = AutoTokenizer.from_pretrained(path, use_fast=True, **options)
        model = AutoModelForSequenceClassification.from_pretrained(
            path, use_safetensors=True, **options).to("cpu").eval()
        labels = {str(v).lower(): int(k) for k, v in model.config.id2label.items()}
        if set(labels) != {"contradiction", "entailment", "neutral"}:
            return None
        return tokenizer, model, labels["entailment"]
    except (OSError, ImportError, ValueError, RuntimeError):
        return None


def entailment_scores(pairs: list[tuple[str, str]]) -> list[float | None]:
    """Softmax P(entailment) for (source premise, extracted hypothesis) pairs.

    Return None for unavailable models, inference errors or pairs longer than
    the model's context window. CPU inference avoids sharing Ollama's VRAM.
    """
    scores: list[float | None] = [None] * len(pairs)
    if not pairs:
        return scores
    with _LOCK:
        loaded = _load_model(os.environ.get("RGPT_NLI_MODEL_PATH", MODEL_ID))
        if loaded is None:
            return scores
        tokenizer, model, entailment_id = loaded
        try:
            import torch

            maximum = min(512, model.config.max_position_embeddings)
            inputs = [tokenizer(premise, hypothesis, truncation=False)
                      for premise, hypothesis in pairs]
            indices = [i for i, item in enumerate(inputs) if len(item["input_ids"]) <= maximum]
            if not indices:
                return scores
            features = tokenizer.pad([inputs[i] for i in indices], padding=True,
                                     return_tensors="pt")
            with torch.inference_mode():
                probabilities = model(**features).logits.softmax(dim=-1)[:, entailment_id].tolist()
            for i, probability in zip(indices, probabilities):
                if math.isfinite(probability) and 0.0 <= probability <= 1.0:
                    scores[i] = probability
        except (OSError, ValueError, RuntimeError, TypeError):
            pass
    return scores
