"""POSITIVE CONTROL for the cross-row arm of eval_framework_sensitivity.py.

The 8 cross-row structural mutants all scored faithfulness 0.0. That is only
readable as "the framework detected the row misattribution" if the SAME sentence
template, on the SAME paper, with the SAME retrieved context, but carrying the
row's OWN correct number scores HIGH. Otherwise the 0.0 is the judge rejecting
the crafted template, not the structural error.

Interpretation, fixed before running:
  correct-cell control scores >= 0.5  AND cross-row scores < 0.5
      -> the 8/8 detection is SPECIFIC to the structural error.
  both < 0.5
      -> the detection is NOT specific; the cross-row 8/8 cannot be read as
         structural sensitivity, and the arm is uninformative either way.

Identical RAGAS configuration to the main run. Nothing about the primary result
or its criterion changes; this only tells us how to read the cross-row arm.

  python -u experiments/document_evidence_pipeline/eval_framework_control.py
"""
from __future__ import annotations
import asyncio, json, sys, time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import eval_framework_sensitivity as E  # same config, same retrieval  # noqa: E402

OUT = HERE / "runs" / "eval_framework_sensitivity"


def main() -> int:
    from sentence_transformers import SentenceTransformer
    from ragas.metrics import Faithfulness
    from ragas.llms import LangchainLLMWrapper
    from ragas.dataset_schema import SingleTurnSample
    from langchain_ollama import ChatOllama

    cr = json.loads((E.GS / "crossrow.json").read_text(encoding="utf-8"))
    by_corpus = E._load_chunks()
    emb = SentenceTransformer("BAAI/bge-m3", device="cuda")
    emb.max_seq_length = 512
    judge = LangchainLLMWrapper(ChatOllama(model=E.JUDGE_MODEL, temperature=0, seed=42, num_ctx=8192))
    faith = Faithfulness(llm=judge)

    path = OUT / "crossrow_control.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    done = {r["idx"] for r in rows}
    t0 = time.time()
    for i, c in enumerate(cr):
        if i in done:
            continue
        # identical template, identical paper/context, row A's OWN number
        correct = (f"{c['row_A_label']} reports a {c['metric_token']} of "
                   f"{c['row_A_number']} on the benchmark.")
        ctx = E._retrieve(emb, c["crafted_claim"], by_corpus[c["corpus"]][c["paper_id"]], [])
        s = SingleTurnSample(user_input=E.QUESTION["results"], response=correct,
                             retrieved_contexts=ctx)
        try:
            score = asyncio.run(faith.single_turn_ascore(s))
            err = None
        except Exception as exc:  # noqa: BLE001
            score, err = None, f"{type(exc).__name__}: {exc}"
        rows.append({"idx": i, "corpus": c["corpus"], "paper_id": c["paper_id"][:10],
                     "control_claim": correct, "mutant_claim": c["crafted_claim"],
                     "control_faithfulness": score, "error": err})
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"  [{len(rows)}/{len(cr)}] f={score}  {correct[:80]}   ({time.time()-t0:.0f}s)")

    ok = [r for r in rows if isinstance(r["control_faithfulness"], (int, float))]
    hi = sum(1 for r in ok if r["control_faithfulness"] >= E.DETECT_THRESHOLD)
    print("\n" + "=" * 78)
    print("POSITIVE CONTROL — same template, same context, row's OWN correct number")
    print("=" * 78)
    print(f"  control claims scoring >= {E.DETECT_THRESHOLD} (framework accepts the CORRECT claim): {hi}/{len(ok)}")
    print(f"  cross-row mutants scoring <  {E.DETECT_THRESHOLD} (from the main run): 8/8")
    if hi == 0:
        print("\n  => NOT SPECIFIC. The framework rejects the correct-cell claim just as it")
        print("     rejects the cross-row one. The 8/8 cross-row 'detection' cannot be read")
        print("     as sensitivity to the structural error; the cross-row arm is uninformative.")
    elif hi == len(ok):
        print("\n  => SPECIFIC. The framework accepts the correct-cell claim and rejects the")
        print("     cross-row substitution: genuine sensitivity to the structural error.")
    else:
        print(f"\n  => PARTIAL ({hi}/{len(ok)} controls accepted). Report per case; the cross-row")
        print("     arm is interpretable only for the cases whose control was accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
