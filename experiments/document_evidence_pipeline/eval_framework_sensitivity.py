"""Evaluation-method comparison — sensitivity of an established automated RAG
evaluation framework to controlled structural evidence mutations.

RESEARCH QUESTION (hypothesis-neutral): How sensitive is an established automated
RAG evaluation framework to controlled structural evidence mutations?

This is NOT a test built to make the framework fail. Mutants are the EXISTING
gate_sensitivity suite, unchanged and unselected; the framework runs one fixed
configuration over all of them; the detection criterion is fixed below, before
any result is inspected. The experiment can falsify the paper's thesis (if the
framework detects every structural mutation, the thesis narrows — see report).

Framework: RAGAS 0.2.15, `Faithfulness` metric — decomposes the response into
atomic claims and NLI-checks each against the retrieved context. It is the RAGAS
metric whose stated purpose ("is the answer grounded in the evidence") matches
the question the structural diagnostic asks.

FIXED CONFIGURATION (every sample):
  judge LLM            qwen2.5:7b via Ollama, temperature 0, seed 42, num_ctx 8192
                       (the only LLM available in this environment; same family
                       the pipeline uses — stated as a limitation, not a strength)
  embeddings           BAAI/bge-m3 (the pipeline's embedding model)
  retrieved_contexts   top-8 chunks of the mutant's paper by cosine similarity to
                       the ORIGINAL (pre-mutation) claim — held constant within a
                       mutation family so only the response varies. For
                       support_deletion mutants the drop_chunk_ids are removed
                       from the candidate pool first (mirrors what the gate sees).
  user_input           fixed string per field

DETECTION CRITERION (fixed before inspecting results):
  should-REJECT mutant  ->  "detected"          iff  faithfulness < 0.5
  should-ACCEPT mutant  ->  "correctly passed"  iff  faithfulness >= 0.5
  secondary marker (reported alongside, not primary): strict = faithfulness < 1.0
  NaN / judge failure   ->  "no score"  (counted separately, never as detection)

Structural diagnostic result = the gate's recorded `gate_final`
(ABSTAINED = flagged as problematic; RETURNED = accepted).
Disagreement = framework flag-verdict != structural flag-verdict, per mutant.

  python -u experiments/document_evidence_pipeline/eval_framework_sensitivity.py

Reads runs/gate_sensitivity/{mutants,crossrow}.json (the existing suite) + the
per-corpus chunk files. Writes runs/eval_framework_sensitivity/.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GS = HERE / "runs" / "gate_sensitivity"
OUT = HERE / "runs" / "eval_framework_sensitivity"
OUT.mkdir(parents=True, exist_ok=True)

CHUNK_FILES = {
    "canonical60": HERE / "runs/prodab-20260902T004416Z/canonical/processed/chunks.json",
    "data_test": ROOT / "data_test/processed/chunks.json",
    "medical_jats": HERE / "runs/binding_validation/processed/chunks.json",
}
TOP_K = 8
JUDGE_MODEL = "qwen2.5:7b"
DETECT_THRESHOLD = 0.5          # primary
STRICT_THRESHOLD = 1.0         # secondary marker
QUESTION = {
    "results": "What are the main quantitative results this paper reports?",
    "metrics": "What evaluation metrics and values does this paper report?",
}
SHOULD_ACCEPT = {"paraphrase_rule", "paraphrase_llm"}


def _load_chunks():
    by_corpus = {}
    for corp, p in CHUNK_FILES.items():
        rows = json.loads(Path(p).read_text(encoding="utf-8"))
        d = defaultdict(list)
        for c in rows:
            d[c["paper_id"]].append(c)
        by_corpus[corp] = d
    return by_corpus


def _samples():
    """Every case in the existing suite -> a uniform record. No filtering."""
    mut = json.loads((GS / "mutants.json").read_text(encoding="utf-8"))
    cr = json.loads((GS / "crossrow.json").read_text(encoding="utf-8"))
    out = []
    for i, m in enumerate(mut):
        if m.get("gate_final") in (None, "SKIPPED"):
            continue
        out.append({
            "sample_id": f"mut{i:03d}", "cls": m["cls"],
            "expected": m["expected"], "corpus": m["corpus"], "paper_id": m["paper_id"],
            "field": m.get("field", "results"),
            "original_case": m.get("base_value", ""),
            "response": str(m.get("mutant_value", "")),
            "retrieval_ref": m.get("base_value") or str(m.get("mutant_value", "")),
            "drop_chunk_ids": list(m.get("drop_chunk_ids") or []),
            "gate_final": m["gate_final"],
        })
    for i, c in enumerate(cr):
        out.append({
            "sample_id": f"crx{i:03d}", "cls": "cross_row_structural",
            "expected": "ABSTAINED", "corpus": c["corpus"], "paper_id": c["paper_id"],
            "field": "results",
            "original_case": f"(row '{c.get('row_A_label')}' actual {c.get('metric_token')} "
                             f"= {c.get('row_A_number')}; row-B value {c.get('row_B_number_used')} substituted)",
            "response": c["crafted_claim"],
            "retrieval_ref": c["crafted_claim"],
            "drop_chunk_ids": [],
            "gate_final": c["gate_final"],
        })
    return out


def _retrieve(model, ref_text, paper_chunks, drop_ids):
    import numpy as np
    pool = [c for c in paper_chunks if c.get("chunk_id") not in set(drop_ids)]
    if not pool:
        return []
    qv = model.encode([ref_text], normalize_embeddings=True)[0]
    cv = model.encode([c["text"] for c in pool], normalize_embeddings=True,
                      batch_size=64, show_progress_bar=False)
    sims = cv @ qv
    order = np.argsort(-sims)[:TOP_K]
    return [pool[i]["text"] for i in order]


def main() -> int:
    from sentence_transformers import SentenceTransformer
    from ragas.metrics import Faithfulness
    from ragas.llms import LangchainLLMWrapper
    from ragas.dataset_schema import SingleTurnSample
    from langchain_ollama import ChatOllama

    by_corpus = _load_chunks()
    samples = _samples()
    print(f"existing suite: {len(samples)} scored cases  "
          f"({dict(Counter(s['cls'] for s in samples))})")

    emb = SentenceTransformer("BAAI/bge-m3", device="cuda")
    emb.max_seq_length = 512
    judge = LangchainLLMWrapper(ChatOllama(model=JUDGE_MODEL, temperature=0, seed=42, num_ctx=8192))
    faith = Faithfulness(llm=judge)

    cache_path = OUT / "scores.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    print(f"  {len(cache)} cached scores reused" if cache else "  clean run")

    t0 = time.time()
    for k, s in enumerate(samples):
        if s["sample_id"] in cache:
            continue
        ctx = _retrieve(emb, s["retrieval_ref"], by_corpus[s["corpus"]][s["paper_id"]],
                        s["drop_chunk_ids"])
        sample = SingleTurnSample(user_input=QUESTION.get(s["field"], QUESTION["results"]),
                                  response=s["response"], retrieved_contexts=ctx)
        try:
            score = asyncio.run(faith.single_turn_ascore(sample))
        except Exception as exc:  # noqa: BLE001
            score = None
            s["error"] = f"{type(exc).__name__}: {exc}"
        cache[s["sample_id"]] = {"faithfulness": score, "n_ctx": len(ctx),
                                 "error": s.get("error")}
        if (k + 1) % 5 == 0 or k + 1 == len(samples):
            cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            el = time.time() - t0
            print(f"  [{k+1:3}/{len(samples)}] {el:.0f}s  ({el/(k+1):.1f}s/sample)")
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    # ---- join + classify under the PREDEFINED criterion ----
    rows = []
    for s in samples:
        sc = cache.get(s["sample_id"], {})
        f = sc.get("faithfulness")
        has = isinstance(f, (int, float)) and not (isinstance(f, float) and math.isnan(f))
        should_reject = s["expected"] == "ABSTAINED"
        if not has:
            fw_flag = None        # no score
        elif should_reject:
            fw_flag = (f < DETECT_THRESHOLD)          # detected the problem
        else:
            fw_flag = not (f >= DETECT_THRESHOLD)     # wrongly flagged a good paraphrase
        struct_flag = (s["gate_final"] == "ABSTAINED")
        rows.append({
            "sample_id": s["sample_id"], "mutation_type": s["cls"], "corpus": s["corpus"],
            "paper_id": s["paper_id"][:10], "expected": s["expected"],
            "original_case": s["original_case"][:200], "response": s["response"][:200],
            "ragas_faithfulness": f, "n_ctx": sc.get("n_ctx"),
            "framework_flags_problem": fw_flag,
            "framework_strict_flag_lt1": (has and f < STRICT_THRESHOLD) if has else None,
            "structural_diagnostic": s["gate_final"],
            "structural_flags_problem": struct_flag,
            "disagree": (None if fw_flag is None else fw_flag != struct_flag),
            "error": sc.get("error"),
        })
    (OUT / "per_mutant.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    # ---- aggregates ----
    def agg(sub):
        scored = [r for r in sub if r["framework_flags_problem"] is not None]
        noscore = len(sub) - len(scored)
        rej = [r for r in scored if r["expected"] == "ABSTAINED"]
        acc = [r for r in scored if r["expected"] == "RETURNED"]
        fw_detect = sum(1 for r in rej if r["framework_flags_problem"])
        fw_strict = sum(1 for r in rej if r["framework_strict_flag_lt1"])
        fw_falseflag = sum(1 for r in acc if r["framework_flags_problem"])
        st_detect = sum(1 for r in rej if r["structural_flags_problem"])
        st_keep = sum(1 for r in acc if not r["structural_flags_problem"])
        disagree = sum(1 for r in scored if r["disagree"])
        return {"n": len(sub), "no_score": noscore,
                "should_reject": len(rej), "should_accept": len(acc),
                "fw_detected": fw_detect, "fw_detected_strict_lt1": fw_strict,
                "fw_false_flag_on_paraphrase": fw_falseflag,
                "struct_detected": st_detect, "struct_kept_paraphrase": st_keep,
                "disagreements": disagree}

    by_cls = {cls: agg([r for r in rows if r["mutation_type"] == cls])
              for cls in sorted({r["mutation_type"] for r in rows})}
    overall = agg(rows)
    struct_classes = ["cross_row_structural"]
    semantic_reject = ["numeric_perturbation", "fabrication",
                       "support_deletion_primary", "support_deletion_full"]
    summary = {"config": {"framework": "RAGAS 0.2.15 / Faithfulness", "judge_llm": JUDGE_MODEL,
                          "judge_params": "temperature 0, seed 42, num_ctx 8192",
                          "embeddings": "BAAI/bge-m3", "top_k_context": TOP_K,
                          "detect_threshold": DETECT_THRESHOLD, "strict_marker": STRICT_THRESHOLD},
               "overall": overall, "by_class": by_cls}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 92)
    print("EVALUATION-METHOD COMPARISON — framework (RAGAS/Faithfulness) vs structural diagnostic")
    print("=" * 92)
    c = summary["config"]
    print(f"  framework={c['framework']}  judge={c['judge_llm']} ({c['judge_params']})  "
          f"ctx=top-{c['top_k_context']} bge-m3")
    print(f"  PREDEFINED criterion: should-REJECT detected iff faithfulness < {DETECT_THRESHOLD}; "
          f"should-ACCEPT passed iff >= {DETECT_THRESHOLD}\n")
    hdr = (f"  {'mutation type':26}{'n':>4}{'noScr':>6}{'FW det':>9}{'FW<1':>7}"
           f"{'STRUCT det':>11}{'FW falseflag':>13}{'disagree':>9}")
    print(hdr)
    for cls, a in by_cls.items():
        rej = a["should_reject"]
        fwd = f"{a['fw_detected']}/{rej}" if rej else "—"
        fws = f"{a['fw_detected_strict_lt1']}/{rej}" if rej else "—"
        std = f"{a['struct_detected']}/{rej}" if rej else "—"
        ff = f"{a['fw_false_flag_on_paraphrase']}/{a['should_accept']}" if a['should_accept'] else "—"
        print(f"  {cls:26}{a['n']:>4}{a['no_score']:>6}{fwd:>9}{fws:>7}{std:>11}{ff:>13}{a['disagreements']:>9}")
    print(f"  {'—' * 88}")
    a = overall
    _fwd = f"{a['fw_detected']}/{a['should_reject']}"
    _fws = f"{a['fw_detected_strict_lt1']}/{a['should_reject']}"
    _std = f"{a['struct_detected']}/{a['should_reject']}"
    _ff = f"{a['fw_false_flag_on_paraphrase']}/{a['should_accept']}"
    print(f"  {'ALL':26}{a['n']:>4}{a['no_score']:>6}{_fwd:>9}{_fws:>7}{_std:>11}{_ff:>13}{a['disagreements']:>9}")

    # focused: the structural-mutation class vs the semantic should-reject classes
    def rate(classes):
        sub = [r for r in rows if r["mutation_type"] in classes
               and r["expected"] == "ABSTAINED" and r["framework_flags_problem"] is not None]
        fw = sum(1 for r in sub if r["framework_flags_problem"])
        st = sum(1 for r in sub if r["structural_flags_problem"])
        return len(sub), fw, st
    ns, fws, sts = rate(struct_classes)
    nse, fwse, stse = rate(semantic_reject)
    print(f"\n  cross-row STRUCTURAL mutations (n={ns}):   framework detected {fws}/{ns}   "
          f"structural diagnostic detected {sts}/{ns}")
    print(f"  semantic should-reject mutations (n={nse}): framework detected {fwse}/{nse}   "
          f"structural diagnostic detected {stse}/{nse}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
