"""PHASE 7 STEP A3 — observe only. Exactly two Ollama calls, no edits.

Builds the extraction prompt for ONE Phase 5 development paper exactly as the
product builds it at n_results=50 (production `_select_legacy` + `_assemble`,
then `_extract_single_paper`'s user_content shape), then sends the product's
exact /api/chat payload twice:

  call 1 -- as the product sends it (num_ctx = estimate_num_ctx(...))
  call 2 -- identical, except options.num_ctx = 8192

Reads prompt_eval_count from each. Nothing is modified.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from src.summarization.retrieval_aware import (  # noqa: E402
    TARGET_QUERIES, _assemble, _select_legacy,
)
from src.summarization.summarize import (  # noqa: E402
    EXTRACTION_OUTPUT_RESERVATION, estimate_num_ctx, select_extraction_prompt,
)

RUN = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
OUT = HERE / "runs" / "phase7_portability"
PAPER = "1016250721201821285c39eba5ab77eddf80812e"   # first of the Phase 5 dev set
MAX_WORDS = 2500
BASE = "http://localhost:11434"
MODEL = "qwen2.5:7b"


def post(payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def main() -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer

    OUT.mkdir(parents=True, exist_ok=True)
    chunks = json.loads((RUN / "processed" / "chunks.json").read_text(encoding="utf-8"))
    pchunks = sorted([c for c in chunks if c["paper_id"] == PAPER],
                     key=lambda c: c["chunk_index"])
    title = pchunks[0].get("title") or ""
    print(f"paper {PAPER[:12]}  chunks={len(pchunks)}  title={title[:60]!r}")

    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    model.max_seq_length = 256
    col = chromadb.PersistentClient(
        path=str(RUN / "chroma_db")).get_collection("researchgpt_papers")
    qv = model.encode(list(TARGET_QUERIES), normalize_embeddings=True, convert_to_numpy=True)

    # production selection, unmodified -- n_results is whatever src carries (50)
    text, trace = _select_legacy(pchunks, col, qv, PAPER, MAX_WORDS)
    assert text == _assemble(
        sorted([c for c in pchunks if c["chunk_id"] in set(trace["selected_chunk_ids"])],
               key=lambda c: c["chunk_index"]) or list(pchunks), MAX_WORDS)

    user_content = f"Title: {title}\n\nText:\n{text}"
    variant, sys_prompt = select_extraction_prompt(text)
    num_ctx = estimate_num_ctx(user_content, output_reservation=EXTRACTION_OUTPUT_RESERVATION)
    words = len(user_content.split())
    print(f"selected chunks={len(trace['selected_chunk_ids'])}  assembled words={len(text.split())}")
    print(f"user_content words={words}  prompt variant={variant}  "
          f"system prompt words={len(sys_prompt.split())}")
    print(f"product num_ctx = estimate_num_ctx(...) = {num_ctx}")

    def payload(nctx: int) -> dict:
        opts = {"temperature": 0.0, "num_ctx": nctx,
                "num_predict": EXTRACTION_OUTPUT_RESERVATION,
                "seed": 42, "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1}
        return {"model": MODEL,
                "messages": [{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": user_content}],
                "format": "json", "stream": False, "options": opts}

    print("\ncall 1 — exactly as the product sends it ...")
    r1 = post(payload(num_ctx))
    print("call 2 — identical plus num_ctx 8192 ...")
    r2 = post(payload(8192))

    rec = {
        "paper_id": PAPER, "title": title,
        "selected_chunks": len(trace["selected_chunk_ids"]),
        "assembled_words": len(text.split()),
        "user_content_words": words,
        "prompt_variant": variant,
        "system_prompt_words": len(sys_prompt.split()),
        "call_1": {"num_ctx": num_ctx,
                   "prompt_eval_count": r1.get("prompt_eval_count"),
                   "eval_count": r1.get("eval_count"),
                   "done_reason": r1.get("done_reason")},
        "call_2": {"num_ctx": 8192,
                   "prompt_eval_count": r2.get("prompt_eval_count"),
                   "eval_count": r2.get("eval_count"),
                   "done_reason": r2.get("done_reason")},
    }
    p1, p2 = rec["call_1"]["prompt_eval_count"], rec["call_2"]["prompt_eval_count"]
    rec["truncated_in_production"] = bool(p1 is not None and p2 is not None and p1 < p2)
    rec["tokens_lost"] = (p2 - p1) if rec["truncated_in_production"] else 0
    (OUT / "stepA3.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")

    print(f"\n  call 1: num_ctx={num_ctx:5}  prompt_eval_count={p1}  done={rec['call_1']['done_reason']}")
    print(f"  call 2: num_ctx= 8192  prompt_eval_count={p2}  done={rec['call_2']['done_reason']}")
    print(f"  truncated in production: {rec['truncated_in_production']}  "
          f"tokens lost: {rec['tokens_lost']}")


if __name__ == "__main__":
    main()
