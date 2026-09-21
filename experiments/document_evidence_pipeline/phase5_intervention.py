"""PHASE 5 — measure the selection-budget intervention (n_results 3 -> 50).

One variable. Same evaluator, same relevance criterion (target chunk OR any alternate
carrying the same value, in the delivered set), same unit (anchor), same index.

Delivery is measured TWICE:
  pre-assembly   -- the union of chunk ids, the quantity Phase 1/2 reported
  post-assembly  -- the chunks that survive _assemble's 2,500-word budget. HEADLINE.

The cleaned denominator reuses the Phase 4 detector by importing it -- not
reimplementing it. `_assemble` is imported from src and used unmodified.

Development and held-out results are written to SEPARATE files so the held-out arm
can stay unread until the development sections are written.
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

from phase4_denominator import detect, window_of          # noqa: E402  reuse
from src.summarization.retrieval_aware import (           # noqa: E402
    TARGET_QUERIES, _assemble,
)

RUN = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CHUNKS = RUN / "processed" / "chunks.json"
CHROMA = RUN / "chroma_db"
ANCHORS = HERE / "runs" / "retrieval_recall" / "anchors.json"
OUT = HERE / "runs" / "phase5_intervention"
MAX_WORDS = 2500          # configs/config.yaml:37
ARMS = {"n3": 3, "n50": 50}


def assemble_accounting(sel: list[dict], max_words: int = MAX_WORDS):
    """Replicate _assemble's loop to recover how many words each chunk contributed.

    _assemble itself returns only the joined string, so the per-chunk prefix is not
    observable from it. The word total produced here is asserted equal to the real
    _assemble output, which is what makes this an accounting of the real function
    rather than a second implementation of it.
    """
    used, taken = 0, {}
    for c in sel:
        if used >= max_words:
            break
        w = c["text"].split()
        k = len(w[: max_words - used])
        taken[c["chunk_id"]] = (k, len(w))
        used += k
    return taken, used


def main() -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer

    OUT.mkdir(parents=True, exist_ok=True)
    split = json.loads((OUT / "split.json").read_text(encoding="utf-8"))
    held = set(split["held_out"])
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    by_id = {c["chunk_id"]: c for c in chunks}
    per_paper_chunks = defaultdict(list)
    for c in chunks:
        per_paper_chunks[c["paper_id"]].append(c)
    for v in per_paper_chunks.values():
        v.sort(key=lambda c: c["chunk_index"])

    anchors = [a for a in json.loads(ANCHORS.read_text(encoding="utf-8"))
               if not a["paper_is_short"]]
    # cleaned denominator -- Phase 4 detector, applied per anchor
    for a in anchors:
        a["_malformed"] = bool(detect(a["value"], *window_of(a, by_id)))
    print(f"cleaned denominator: {sum(1 for a in anchors if a['_malformed'])}/{len(anchors)} malformed")

    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    model.max_seq_length = 256
    col = chromadb.PersistentClient(path=str(CHROMA)).get_collection("researchgpt_papers")
    qvecs = model.encode(list(TARGET_QUERIES), normalize_embeddings=True, convert_to_numpy=True)

    papers = sorted({a["paper_id"] for a in anchors})
    state = {arm: {} for arm in ARMS}
    for pid in papers:
        pchunks = per_paper_chunks[pid]
        for arm, k in ARMS.items():
            t0 = time.perf_counter()
            ids = set()
            for qv in qvecs:                       # identical to _select_legacy:252-256
                r = col.query(query_embeddings=[qv.tolist()],
                              n_results=min(k, len(pchunks)), where={"paper_id": pid})
                ids.update(r["ids"][0])
            sel = [c for c in pchunks if c["chunk_id"] in ids] or list(pchunks)
            sel.sort(key=lambda c: c["chunk_index"])
            taken, used = assemble_accounting(sel)
            text = _assemble(sel, MAX_WORDS)       # the real function
            dt = time.perf_counter() - t0
            assert len(text.split()) == used, f"{pid}/{arm}: accounting != _assemble"
            state[arm][pid] = {"union": ids, "sel_n": len(sel), "taken": taken,
                               "words": used, "latency_s": dt,
                               "truncated": any(k_ < n for k_, n in taken.values())
                                            or len(taken) < len(sel)}
        print(f"  {pid[:10]} n3 union={len(state['n3'][pid]['union']):3} "
              f"w={state['n3'][pid]['words']:5} | n50 union={len(state['n50'][pid]['union']):4} "
              f"w={state['n50'][pid]['words']:5}")

    def delivered(a, pid_state, stage):
        cand = [a["target_chunk"], *a["alt_chunks"]]
        if stage == "pre":
            return any(c in pid_state["union"] for c in cand)
        for c in cand:
            t = pid_state["taken"].get(c)
            if t is None:
                continue
            k, n = t
            if k >= n:
                return True
            if a["value"] in " ".join(by_id[c]["text"].split()[:k]):
                return True
        return False

    def budget_chunks(pid_state, stage):
        return len(pid_state["union"]) if stage == "pre" else len(pid_state["taken"])

    def block(subset, arm, stage, clean):
        sub = [a for a in subset if not (clean and a["_malformed"])]
        if not sub:
            return None
        hits = sum(1 for a in sub if delivered(a, state[arm][a["paper_id"]], stage))
        null = sum(min(budget_chunks(state[arm][a["paper_id"]], stage), a["n_chunks"])
                   / a["n_chunks"] for a in sub) / len(sub)
        d = hits / len(sub)
        return {"n": len(sub), "delivery": round(d, 4), "null": round(null, 4),
                "ratio_to_random": round(d / null, 3) if null else None,
                "mean_budget_chunks": round(st.mean(
                    [budget_chunks(state[arm][a["paper_id"]], stage) for a in sub]), 1)}

    def report_for(ids):
        sub = [a for a in anchors if a["paper_id"] in ids]
        out = {"n_papers": len(ids), "n_anchors_raw": len(sub),
               "n_anchors_cleaned": sum(1 for a in sub if not a["_malformed"])}
        for arm in ARMS:
            for stage in ("pre", "post"):
                for clean in (False, True):
                    tag = f"{arm}_{stage}_{'cleaned' if clean else 'raw'}"
                    out[tag] = block(sub, arm, stage, clean)
        # 3.5 words / truncation
        for arm in ARMS:
            w = [state[arm][p]["words"] for p in ids]
            ws = sorted(w)
            trunc = [p for p in ids if state[arm][p]["truncated"]]
            lost = sum(1 for a in sub if not a["_malformed"]
                       and delivered(a, state[arm][a["paper_id"]], "pre")
                       and not delivered(a, state[arm][a["paper_id"]], "post"))
            out[f"{arm}_words"] = {
                "mean": round(st.mean(w), 1), "p95": ws[int(0.95 * (len(ws) - 1))],
                "max": max(w), "papers_truncated": len(trunc),
                "papers_truncated_frac": round(len(trunc) / len(ids), 3),
                "cleaned_anchors_lost_to_truncation": lost}
            out[f"{arm}_latency_s"] = {
                "mean": round(st.mean([state[arm][p]["latency_s"] for p in ids]), 3),
                "median": round(st.median([state[arm][p]["latency_s"] for p in ids]), 3),
                "max": round(max(state[arm][p]["latency_s"] for p in ids), 3)}
        # 3.6 per-section, cleaned, post-assembly
        sec = {}
        for name in ("results", "references", "conclusion", "discussion",
                     "method", "experimental_setup", "abstract"):
            s = [a for a in sub if not a["_malformed"] and a["section"][:28] == name]
            if not s:
                continue
            e = {"n": len(s)}
            for arm in ARMS:
                hits = sum(1 for a in s if delivered(a, state[arm][a["paper_id"]], "post"))
                null = sum(min(budget_chunks(state[arm][a["paper_id"]], "post"), a["n_chunks"])
                           / a["n_chunks"] for a in s) / len(s)
                e[arm] = {"delivery": round(hits / len(s), 4),
                          "ratio_to_random": round((hits / len(s)) / null, 3) if null else None}
            sec[name] = e
        out["per_section_cleaned_post"] = sec
        return out

    dev_ids = set(split["development"])
    (OUT / "results_development.json").write_text(
        json.dumps(report_for(dev_ids), indent=1), encoding="utf-8")
    (OUT / "results_heldout.json").write_text(
        json.dumps(report_for(held), indent=1), encoding="utf-8")
    (OUT / "union_sizes.json").write_text(json.dumps(
        {arm: {p: len(state[arm][p]["union"]) for p in papers} for arm in ARMS},
        indent=1), encoding="utf-8")
    print("\nwrote results_development.json / results_heldout.json / union_sizes.json")


if __name__ == "__main__":
    main()
